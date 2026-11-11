"""Adaptador de Gemini (Google AI Studio): generación con conmutación gratuita → paga y rotación de modelos."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from aulento.core.ia.base import (
    ProveedorHTTP,
    RespuestaHTTP,
    en_base64,
    entero,
    vector_unitario,
)
from aulento.core.ia.tarifas import costo_de_un_error, costo_estimado
from aulento.core.ia.tipos import (
    AUDIO,
    CARACTERES_A_EMBEBER,
    DIMENSIONES_DE_EMBEDDING,
    EMBEDDINGS,
    GEMINI,
    PDF,
    TEXTO,
    CuotaAgotada,
    FaltaClaveDeIA,
    IANoDisponibleError,
    Pedido,
    Respuesta,
    RespuestaRechazada,
)

URL_DE_MODELOS = "https://generativelanguage.googleapis.com/v1beta/models"
MODELO_POR_DEFECTO = "gemini-flash-lite-latest"
# Tras el modelo preferido de la cuenta se prueban estos, en este orden
MODELOS_DE_ROTACION = (
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
    "gemini-3.8-flash",
    "gemini-pro-latest",
)
MODELO_DE_EMBEDDINGS = "gemini-embedding-001"
SEGUNDOS_PARA_EMBEBER = 15.0
NIVEL_GRATUITO = "free"
NIVEL_PAGO = "paid"
# Motivos de fin con los que Gemini corta una respuesta por su contenido
MOTIVOS_DE_RECHAZO = frozenset({"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"})


@dataclass(frozen=True)
class Intento:
    """Un pedido que salió hacia Gemini con una clave y un modelo, haya respondido bien o no.

    `estado` es el código HTTP, o `None` si no hubo respuesta. `ok` es que de ahí salió la respuesta que se devuelve.
    """

    nivel: str
    modelo: str
    estado: int | None
    ok: bool
    tokens_entrada: int = 0
    tokens_salida: int = 0
    tokens_totales: int = 0
    costo_usd: float | None = None
    latencia_ms: float = 0.0


def modelos_candidatos(preferido: str) -> list[str]:
    """El modelo preferido y, detrás, los de rotación que no son ese."""
    return [preferido, *(modelo for modelo in MODELOS_DE_ROTACION if modelo != preferido)]


class ProveedorGemini(ProveedorHTTP):
    nombre = GEMINI
    capacidades = frozenset({TEXTO, PDF, AUDIO, EMBEDDINGS})
    modelo_por_defecto = MODELO_POR_DEFECTO
    modelos_sugeridos = MODELOS_DE_ROTACION
    modelo_de_embeddings = MODELO_DE_EMBEDDINGS

    def _cabeceras(self, clave: str) -> dict[str, str]:
        return {"x-goog-api-key": clave}

    def _codigo_de_error(self, datos: dict[str, Any]) -> Any:
        error = datos.get("error")
        return error.get("status") if isinstance(error, dict) else None

    @staticmethod
    def cuerpo(pedido: Pedido) -> dict[str, Any]:
        """El pedido en el formato de `generateContent`. El esquema no se envía: Gemini recibe solo el pedido de JSON.

        Es el único proveedor que recibe la temperatura del pedido.
        """
        partes: list[dict[str, Any]] = [
            {"inlineData": {"mimeType": adjunto.mime, "data": en_base64(adjunto.datos)}} for adjunto in pedido.adjuntos
        ]
        partes.append({"text": pedido.usuario})
        cuerpo: dict[str, Any] = {"contents": [{"role": "user", "parts": partes}]}
        if pedido.sistema and pedido.sistema.strip():
            cuerpo["systemInstruction"] = {"parts": [{"text": pedido.sistema}]}
        configuracion: dict[str, Any] = {}
        if pedido.pide_json:
            configuracion["responseMimeType"] = "application/json"
        if pedido.max_tokens:
            configuracion["maxOutputTokens"] = pedido.max_tokens
        if pedido.temperatura is not None:
            configuracion["temperature"] = pedido.temperatura
        if configuracion:
            cuerpo["generationConfig"] = configuracion
        return cuerpo

    def generar(self, pedido: Pedido, clave: str, modelo: str | None, nivel: str | None = None) -> Respuesta:
        """Un pedido con una clave y un modelo, sin conmutación ni rotación."""
        self._exigir_capacidad(pedido)
        modelo = modelo or MODELO_POR_DEFECTO
        http = self._post(self._url(modelo, "generateContent"), self.cuerpo(pedido), clave, modelo=modelo, timeout=pedido.timeout)
        return self._leer(http, modelo, nivel)

    def generar_con_conmutacion(
        self,
        cuerpo: dict[str, Any],
        claves: Sequence[tuple[str, str]],
        modelos: Sequence[str],
        timeout: float | None = None,
        al_intentar: Callable[[Intento], None] | None = None,
    ) -> tuple[Respuesta, dict[str, Any]]:
        """Prueba cada clave (`(nivel, clave)`, en orden) con cada modelo hasta que uno responde.

        Ante un límite de cuota con la clave gratuita, si hay otra clave detrás, pasa a ella sin probar más modelos;
        cualquier otra falla sigue con el modelo siguiente. Devuelve la respuesta y el cuerpo crudo que la trajo.
        Si nada respondió levanta el primer error de la última clave probada. `al_intentar` recibe cada intento.
        """
        if not claves:
            raise FaltaClaveDeIA(proveedor=GEMINI)
        avisar = al_intentar or (lambda intento: None)
        error_de_la_clave: IANoDisponibleError | None = None
        for nivel, clave in claves:
            error_de_la_clave = None
            for modelo in modelos:
                try:
                    http = self._post(self._url(modelo, "generateContent"), cuerpo, clave, modelo=modelo, timeout=timeout)
                    respuesta = self._leer(http, modelo, nivel)
                except IANoDisponibleError as error:
                    error_de_la_clave = error_de_la_clave or error
                    avisar(
                        Intento(
                            nivel=nivel,
                            modelo=modelo,
                            estado=error.estado,
                            ok=False,
                            tokens_entrada=error.tokens_entrada,
                            tokens_salida=error.tokens_salida,
                            tokens_totales=error.tokens_entrada + error.tokens_salida,
                            costo_usd=costo_de_un_error(error),
                            latencia_ms=error.latencia_ms,
                        )
                    )
                    if isinstance(error, CuotaAgotada) and nivel == NIVEL_GRATUITO and len(claves) > 1:
                        break
                    continue
                uso = http.datos.get("usageMetadata") or {}
                avisar(
                    Intento(
                        nivel=nivel,
                        modelo=modelo,
                        estado=200,
                        ok=True,
                        tokens_entrada=respuesta.tokens_entrada,
                        tokens_salida=respuesta.tokens_salida,
                        tokens_totales=entero(uso.get("totalTokenCount"))
                        or respuesta.tokens_entrada + respuesta.tokens_salida,
                        costo_usd=respuesta.costo_usd,
                        latencia_ms=respuesta.latencia_ms,
                    )
                )
                return respuesta, http.datos
        raise error_de_la_clave or IANoDisponibleError("Gemini no respondió con ningún modelo.", proveedor=GEMINI)

    def embeber(self, texto: str, clave: str, tarea: str = "documento") -> tuple[list[float], str]:
        tipo_tarea = "RETRIEVAL_QUERY" if tarea == "consulta" else "RETRIEVAL_DOCUMENT"
        cuerpo = {
            "model": f"models/{MODELO_DE_EMBEDDINGS}",
            "content": {"parts": [{"text": texto[:CARACTERES_A_EMBEBER]}]},
            "outputDimensionality": DIMENSIONES_DE_EMBEDDING,
            "taskType": tipo_tarea,
        }
        http = self._post(
            self._url(MODELO_DE_EMBEDDINGS, "embedContent"),
            cuerpo,
            clave,
            modelo=MODELO_DE_EMBEDDINGS,
            timeout=SEGUNDOS_PARA_EMBEBER,
            cabeceras={"Content-Type": "application/json"},
        )
        valores = (http.datos.get("embedding") or {}).get("values")
        return vector_unitario(valores, GEMINI, MODELO_DE_EMBEDDINGS), MODELO_DE_EMBEDDINGS

    def modelos(self, clave: str) -> list[str]:
        """Los modelos que la clave puede usar para generar contenido, sin el prefijo `models/`."""
        datos = self._get(URL_DE_MODELOS, clave).datos
        return sorted(
            str(modelo["name"]).removeprefix("models/")
            for modelo in datos.get("models") or []
            if isinstance(modelo, dict)
            and modelo.get("name")
            and "generateContent" in (modelo.get("supportedGenerationMethods") or [])
        )

    @staticmethod
    def _url(modelo: str, metodo: str) -> str:
        return f"{URL_DE_MODELOS}/{modelo}:{metodo}"

    def _leer(self, http: RespuestaHTTP, modelo: str, nivel: str | None) -> Respuesta:
        datos = http.datos
        uso = datos.get("usageMetadata") or {}
        entrada, salida = entero(uso.get("promptTokenCount")), entero(uso.get("candidatesTokenCount"))
        del_pedido = {
            "proveedor": GEMINI,
            "modelo": modelo,
            "estado": 200,
            "latencia_ms": http.latencia_ms,
            "tokens_entrada": entrada,
            "tokens_salida": salida,
        }
        candidatos = datos.get("candidates") or []
        if not candidatos:
            if (datos.get("promptFeedback") or {}).get("blockReason"):
                raise RespuestaRechazada("Gemini bloqueó el pedido por su contenido y no generó una respuesta.", **del_pedido)
            raise IANoDisponibleError("Gemini no devolvió ninguna respuesta para este pedido.", **del_pedido)

        candidato = candidatos[0]
        partes = (candidato.get("content") or {}).get("parts") or []
        texto = "".join(
            str(parte.get("text") or "") for parte in partes if isinstance(parte, dict) and not parte.get("thought")
        )
        motivo = candidato.get("finishReason")
        if not texto and motivo in MOTIVOS_DE_RECHAZO:
            raise RespuestaRechazada("Gemini se negó a responder este pedido por su contenido.", **del_pedido)
        return Respuesta(
            texto=texto,
            proveedor=GEMINI,
            modelo=modelo,
            tokens_entrada=entrada,
            tokens_salida=salida,
            costo_usd=costo_estimado(GEMINI, modelo, entrada, salida),
            latencia_ms=http.latencia_ms,
            nivel=nivel,
            truncada=motivo == "MAX_TOKENS",
        )
