"""Adaptador de OpenAI (chat completions y embeddings)."""

from typing import Any

from aulento.core.ia.base import (
    ProveedorHTTP,
    con_instruccion_json,
    en_base64,
    entero,
    esquema_estricto,
    vector_unitario,
)
from aulento.core.ia.tarifas import costo_estimado
from aulento.core.ia.tipos import (
    CARACTERES_A_EMBEBER,
    DIMENSIONES_DE_EMBEDDING,
    EMBEDDINGS,
    OPENAI,
    PDF,
    TEXTO,
    FaltaElegirModelo,
    Pedido,
    Respuesta,
    RespuestaRechazada,
)

URL_DE_CHAT = "https://api.openai.com/v1/chat/completions"
URL_DE_EMBEDDINGS = "https://api.openai.com/v1/embeddings"
URL_DE_MODELOS = "https://api.openai.com/v1/models"
MODELO_DE_EMBEDDINGS = "text-embedding-3-small"
SEGUNDOS_PARA_EMBEBER = 15.0
NOMBRE_DEL_ESQUEMA = "respuesta"
NOMBRE_DEL_PDF = "documento.pdf"
# Lo que distingue, en el identificador, a un modelo que no es de chat
NO_SON_DE_CHAT = ("embedding", "whisper", "tts", "audio", "transcribe", "realtime", "dall-e", "image", "moderation")
MENSAJE_FALTA_ELEGIR_MODELO = (
    "Todavía no elegiste un modelo de OpenAI. Elegilo de la lista o escribilo en Configuración para usar la IA."
)


class ProveedorOpenAI(ProveedorHTTP):
    nombre = OPENAI
    capacidades = frozenset({TEXTO, PDF, EMBEDDINGS})
    modelo_de_embeddings = MODELO_DE_EMBEDDINGS

    def _cabeceras(self, clave: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {clave}"}

    def _codigo_de_error(self, datos: dict[str, Any]) -> Any:
        error = datos.get("error")
        return (error.get("code") or error.get("type")) if isinstance(error, dict) else None

    @staticmethod
    def cuerpo(pedido: Pedido, modelo: str) -> dict[str, Any]:
        """El pedido en el formato de chat completions.

        No fija `temperature` ni `max_tokens`, que varios modelos actuales rechazan; el tope, si el pedido lo trae,
        va en `max_completion_tokens`.
        """
        contenido: str | list[dict[str, Any]] = pedido.usuario
        if pedido.adjuntos:
            contenido = [
                {
                    "type": "file",
                    "file": {
                        "filename": NOMBRE_DEL_PDF,
                        "file_data": f"data:{adjunto.mime};base64,{en_base64(adjunto.datos)}",
                    },
                }
                for adjunto in pedido.adjuntos
            ]
            contenido.append({"type": "text", "text": pedido.usuario})

        sistema = pedido.sistema if pedido.sistema and pedido.sistema.strip() else None
        formato: dict[str, Any] | None = None
        if pedido.esquema is not None:
            formato = {
                "type": "json_schema",
                "json_schema": {"name": NOMBRE_DEL_ESQUEMA, "schema": esquema_estricto(pedido.esquema), "strict": True},
            }
        elif pedido.json:
            # El modo `json_object` exige que el pedido nombre el formato en alguno de sus mensajes
            sistema = con_instruccion_json(sistema)
            formato = {"type": "json_object"}

        mensajes: list[dict[str, Any]] = [{"role": "system", "content": sistema}] if sistema else []
        mensajes.append({"role": "user", "content": contenido})
        cuerpo: dict[str, Any] = {"model": modelo, "messages": mensajes}
        if formato is not None:
            cuerpo["response_format"] = formato
        if pedido.max_tokens:
            cuerpo["max_completion_tokens"] = pedido.max_tokens
        return cuerpo

    def generar(self, pedido: Pedido, clave: str, modelo: str | None) -> Respuesta:
        self._exigir_capacidad(pedido)
        if not modelo or not modelo.strip():
            raise FaltaElegirModelo(MENSAJE_FALTA_ELEGIR_MODELO, proveedor=OPENAI)
        modelo = modelo.strip()
        http = self._post(URL_DE_CHAT, self.cuerpo(pedido, modelo), clave, modelo=modelo, timeout=pedido.timeout)
        datos = http.datos
        uso = datos.get("usage") or {}
        entrada, salida = entero(uso.get("prompt_tokens")), entero(uso.get("completion_tokens"))
        opciones = datos.get("choices") if isinstance(datos.get("choices"), list) else []
        opcion = opciones[0] if opciones and isinstance(opciones[0], dict) else {}
        mensaje = opcion.get("message") if isinstance(opcion.get("message"), dict) else {}
        motivo = opcion.get("finish_reason")
        if motivo == "content_filter" or mensaje.get("refusal"):
            raise RespuestaRechazada(
                "El modelo de OpenAI se negó a responder este pedido.",
                proveedor=OPENAI,
                modelo=modelo,
                estado=200,
                latencia_ms=http.latencia_ms,
                tokens_entrada=entrada,
                tokens_salida=salida,
            )
        contenido = mensaje.get("content")
        return Respuesta(
            texto=contenido if isinstance(contenido, str) else "",
            proveedor=OPENAI,
            modelo=modelo,
            tokens_entrada=entrada,
            tokens_salida=salida,
            costo_usd=costo_estimado(OPENAI, modelo, entrada, salida),
            latencia_ms=http.latencia_ms,
            truncada=motivo == "length",
        )

    def embeber(self, texto: str, clave: str, tarea: str = "documento") -> tuple[list[float], str]:
        cuerpo = {
            "model": MODELO_DE_EMBEDDINGS,
            "input": texto[:CARACTERES_A_EMBEBER],
            "dimensions": DIMENSIONES_DE_EMBEDDING,
        }
        http = self._post(URL_DE_EMBEDDINGS, cuerpo, clave, modelo=MODELO_DE_EMBEDDINGS, timeout=SEGUNDOS_PARA_EMBEBER)
        filas = http.datos.get("data") if isinstance(http.datos.get("data"), list) else []
        valores = filas[0].get("embedding") if filas and isinstance(filas[0], dict) else None
        return vector_unitario(valores, OPENAI, MODELO_DE_EMBEDDINGS), MODELO_DE_EMBEDDINGS

    def modelos(self, clave: str) -> list[str]:
        """Los modelos de la cuenta de OpenAI que parecen de chat, en orden alfabético."""
        datos = self._get(URL_DE_MODELOS, clave).datos
        ids = (str(modelo["id"]) for modelo in datos.get("data") or [] if isinstance(modelo, dict) and modelo.get("id"))
        return sorted(modelo for modelo in ids if not any(marca in modelo.lower() for marca in NO_SON_DE_CHAT))
