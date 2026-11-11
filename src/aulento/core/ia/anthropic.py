"""Adaptador de Anthropic (API de mensajes)."""

from typing import Any

from aulento.core.ia.base import (
    ProveedorHTTP,
    con_instruccion_json,
    en_base64,
    entero,
    esquema_estricto,
)
from aulento.core.ia.tarifas import costo_estimado
from aulento.core.ia.tipos import (
    ANTHROPIC,
    PDF,
    TEXTO,
    Pedido,
    Respuesta,
    RespuestaRechazada,
)

URL_DE_MENSAJES = "https://api.anthropic.com/v1/messages"
URL_DE_MODELOS = "https://api.anthropic.com/v1/models"
VERSION_DE_LA_API = "2023-06-01"
MODELO_POR_DEFECTO = "claude-opus-5-5"
MODELOS_OFRECIDOS = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")
# Los modelos en los que el proveedor puede atender el pedido con otro modelo si el elegido no está disponible
MODELOS_CON_REEMPLAZO = frozenset({"claude-opus-5-5", "claude-sonnet-5-5"})
BETA_DE_REEMPLAZO = "server-side-fallback-2026-07-01"
MAX_TOKENS_POR_DEFECTO = 16000
# Estos modelos razonan siempre antes de responder: un pedido largo tarda bastante más que en otros proveedores
SEGUNDOS_POR_DEFECTO = 180.0


class ProveedorAnthropic(ProveedorHTTP):
    nombre = ANTHROPIC
    capacidades = frozenset({TEXTO, PDF})
    modelo_por_defecto = MODELO_POR_DEFECTO
    modelos_sugeridos = MODELOS_OFRECIDOS
    segundos_por_defecto = SEGUNDOS_POR_DEFECTO

    def _cabeceras(self, clave: str) -> dict[str, str]:
        return {"content-type": "application/json", "x-api-key": clave, "anthropic-version": VERSION_DE_LA_API}

    def _codigo_de_error(self, datos: dict[str, Any]) -> Any:
        error = datos.get("error")
        return error.get("type") if isinstance(error, dict) else None

    @staticmethod
    def cuerpo(pedido: Pedido, modelo: str) -> dict[str, Any]:
        """El pedido en el formato de la API de mensajes.

        No lleva `temperature`, `top_p`, `top_k`, `thinking` ni un turno de asistente precargado: los modelos
        actuales responden 400 a cualquiera de ellos.
        """
        contenido: str | list[dict[str, Any]] = pedido.usuario
        if pedido.adjuntos:
            contenido = [
                {
                    "type": "document",
                    "source": {"type": "base64", "media_type": adjunto.mime, "data": en_base64(adjunto.datos)},
                }
                for adjunto in pedido.adjuntos
            ]
            contenido.append({"type": "text", "text": pedido.usuario})

        cuerpo: dict[str, Any] = {"model": modelo, "max_tokens": pedido.max_tokens or MAX_TOKENS_POR_DEFECTO}
        sistema = pedido.sistema if pedido.sistema and pedido.sistema.strip() else None
        if pedido.esquema is not None:
            cuerpo["output_config"] = {"format": {"type": "json_schema", "schema": esquema_estricto(pedido.esquema)}}
        elif pedido.json:
            sistema = con_instruccion_json(sistema)
        if sistema:
            cuerpo["system"] = sistema
        cuerpo["messages"] = [{"role": "user", "content": contenido}]
        if modelo in MODELOS_CON_REEMPLAZO:
            cuerpo["fallbacks"] = "default"
        return cuerpo

    def generar(self, pedido: Pedido, clave: str, modelo: str | None) -> Respuesta:
        self._exigir_capacidad(pedido)
        modelo = modelo or MODELO_POR_DEFECTO
        http = self._post(
            URL_DE_MENSAJES,
            self.cuerpo(pedido, modelo),
            clave,
            modelo=modelo,
            timeout=pedido.timeout,
            cabeceras={"anthropic-beta": BETA_DE_REEMPLAZO} if modelo in MODELOS_CON_REEMPLAZO else None,
        )
        datos = http.datos
        # Con reemplazo del lado del proveedor puede haber respondido otro modelo: se informa y se cobra ese
        respondio = datos.get("model") if isinstance(datos.get("model"), str) and datos.get("model") else modelo
        uso = datos.get("usage") or {}
        entrada, salida = entero(uso.get("input_tokens")), entero(uso.get("output_tokens"))
        motivo = datos.get("stop_reason")
        # Una negativa llega con HTTP 200: se mira antes de leer el contenido
        if motivo == "refusal":
            raise RespuestaRechazada(
                "El modelo de Anthropic se negó a responder este pedido.",
                proveedor=ANTHROPIC,
                modelo=respondio,
                estado=200,
                latencia_ms=http.latencia_ms,
                tokens_entrada=entrada,
                tokens_salida=salida,
            )
        bloques = datos.get("content") if isinstance(datos.get("content"), list) else []
        texto = "".join(
            str(bloque.get("text") or "") for bloque in bloques if isinstance(bloque, dict) and bloque.get("type") == "text"
        )
        return Respuesta(
            texto=texto,
            proveedor=ANTHROPIC,
            modelo=respondio,
            tokens_entrada=entrada,
            tokens_salida=salida,
            costo_usd=costo_estimado(ANTHROPIC, respondio, entrada, salida),
            latencia_ms=http.latencia_ms,
            truncada=motivo == "max_tokens",
        )

    def modelos(self, clave: str) -> list[str]:
        todos: list[str] = []
        url = URL_DE_MODELOS
        while url:
            datos = self._get(url, clave).datos
            items = datos.get("data") or []
            for modelo in items:
                if isinstance(modelo, dict) and modelo.get("id"):
                    todos.append(str(modelo["id"]))
            if datos.get("has_more"):
                last_id = datos.get("last_id") or (items[-1]["id"] if items and isinstance(items[-1], dict) and items[-1].get("id") else None)
                if last_id:
                    url = f"{URL_DE_MODELOS}?after_id={last_id}"
                else:
                    break
            else:
                break
        return todos


