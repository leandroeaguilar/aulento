"""Módulo de seguridad, autenticación, sandboxing de archivos y auditoría para el servidor MCP."""

from collections.abc import Callable
from contextvars import ContextVar, Token
import functools
import inspect
import json
import logging
from pathlib import Path
import threading
import time
from typing import Any

from aulento.auth import servicio
from aulento.auth.modelos import Usuario
from aulento.auth.repositorio import REGISTRO_DE_RECHAZO_MCP
from aulento.db.connection import get_connection
from aulento.db.cuenta import exigir_cuenta
from aulento.db.repository import MCPAuditRepository

logger = logging.getLogger(__name__)


class SecurityViolationError(Exception):
    """Excepción lanzada cuando se detecta un intento de path traversal o violación de seguridad."""
    pass


class CuentaMcpNoFijada(RuntimeError):
    """Una herramienta MCP intentó operar sin que el transporte hubiera fijado la cuenta del pedido."""


# Cuenta como la que opera el pedido en curso: la del token (red) o la resuelta al arrancar (stdio).
# Las herramientas se registran una vez y la cuenta cambia en cada pedido; no tiene valor por defecto.
_cuenta_mcp: ContextVar[int | None] = ContextVar("mcp_cuenta", default=None)


def fijar_cuenta_mcp(user_id: int) -> Token:
    """Fija la cuenta del pedido o del proceso en curso; devuelve la marca para `restablecer_cuenta_mcp`."""
    return _cuenta_mcp.set(exigir_cuenta(user_id))


def restablecer_cuenta_mcp(marca: Token) -> None:
    """Deja la cuenta como estaba antes del `fijar_cuenta_mcp` que devolvió esa marca."""
    _cuenta_mcp.reset(marca)


def cuenta_mcp_actual() -> int:
    """Cuenta dueña de los datos que puede tocar el pedido en curso; levanta si nadie la fijó."""
    user_id = _cuenta_mcp.get()
    if user_id is None:
        raise CuentaMcpNoFijada("El servidor MCP no tiene una cuenta fijada para este pedido.")
    return user_id


def resolver_token_mcp(provided_token: str | None, db_path: Path | str | None = None) -> Usuario | None:
    """Cuenta activa dueña del token MCP suministrado (con o sin prefijo `Bearer`); None si no vale."""
    if not provided_token:
        return None
    clean_token = provided_token.strip()
    if clean_token.lower().startswith("bearer "):
        clean_token = clean_token[7:].strip()
    conn = get_connection(db_path)
    try:
        return servicio.resolver_token_mcp(conn, clean_token)
    finally:
        conn.close()


def validate_vault_path_sandbox(target_path: Path | str, vault_root: Path | str) -> Path:
    """Valida que target_path resuelva estrictamente dentro del árbol de directorios de vault_root.
    
    Previene inyecciones de path traversal (../../...) y escapes hacia el sistema operativo.
    """
    resolved_vault = Path(vault_root).resolve()
    resolved_target = Path(target_path).resolve()

    try:
        # relative_to lanzará ValueError si resolved_target no desciende de resolved_vault
        resolved_target.relative_to(resolved_vault)
    except ValueError:
        raise SecurityViolationError(
            f"Violación de seguridad (Path Traversal): La ruta '{target_path}' intenta escapar del directorio permitido '{resolved_vault}'."
        )

    return resolved_target


_audit_transport = "stdio"
# IP del cliente que abrió la sesión SSE en curso; en stdio no hay
_audit_client_ip: ContextVar[str | None] = ContextVar("mcp_audit_client_ip", default=None)


def set_audit_client_ip(client_ip: str | None) -> None:
    """Fija la IP del cliente para los registros de auditoría de la petición o sesión en curso."""
    _audit_client_ip.set(client_ip)


def set_audit_transport(transport: str) -> None:
    """Fija el transporte con el que corre el servidor, para que la auditoría lo registre."""
    global _audit_transport
    _audit_transport = transport


def _registrar_auditoria(
    tool_name: str,
    params: dict[str, Any],
    user_id: int | None,
    transport: str | None,
    client_ip: str | None,
    status: str,
    error_message: str | None,
    db_path: Path | str | None,
) -> None:
    try:
        # Sanitizar parámetros para no guardar blobs gigantescos
        sanitized_params = {}
        for k, v in params.items():
            if isinstance(v, str) and len(v) > 500:
                sanitized_params[k] = f"{v[:100]}... [truncado {len(v)} chars]"
            else:
                sanitized_params[k] = v

        params_json = json.dumps(sanitized_params, ensure_ascii=False)
        conn = get_connection(db_path)
        try:
            repo = MCPAuditRepository(conn)
            repo.log(
                tool_name=tool_name,
                params_json=params_json,
                transport=transport or _audit_transport,
                client_ip=client_ip or _audit_client_ip.get(),
                status=status,
                error_message=error_message,
                user_id=user_id,
            )
        finally:
            conn.close()
    except Exception as e:
        logger.error("Error al registrar log de auditoría MCP para %s: %s", tool_name, e)


def log_mcp_tool_execution(
    tool_name: str,
    params: dict[str, Any],
    transport: str | None = None,
    client_ip: str | None = None,
    status: str = "success",
    error_message: str | None = None,
    db_path: Path | str | None = None,
) -> None:
    """Registra una ejecución de herramienta MCP en la auditoría, a nombre de la cuenta del pedido en curso."""
    ejecucion = _ejecucion_en_curso.get()
    if ejecucion is not None:
        ejecucion["auditada"] = True
    _registrar_auditoria(tool_name, params, _cuenta_mcp.get(), transport, client_ip, status, error_message, db_path)


# Ejecución de herramienta en curso, para saber al terminar si ya dejó su registro de auditoría
_ejecucion_en_curso: ContextVar[dict[str, bool] | None] = ContextVar("mcp_ejecucion_en_curso", default=None)
LARGO_DEL_ERROR_AUDITADO = 500


def _parametros_auditables(funcion: Callable[..., Any], args: tuple, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Los argumentos con los que se llamó a la herramienta, dejando solo lo que se puede guardar como JSON."""
    try:
        recibidos = inspect.signature(funcion).bind_partial(*args, **kwargs).arguments
    except TypeError:
        recibidos = dict(kwargs)
    simples = (str, int, float, bool, type(None))
    return {nombre: valor if isinstance(valor, simples) else type(valor).__name__ for nombre, valor in recibidos.items()}


def herramienta_auditada(server: Any, db_path: Path | str | None = None) -> Callable[..., Any]:
    """Devuelve un `tool()` como el del servidor que garantiza un registro de auditoría por ejecución.

    Cada herramienta audita por su cuenta el camino que conoce; si su ejecución termina sin haber
    auditado (una salida temprana porque no hay resultados, un dato que no se encontró, una excepción),
    el registro lo deja este envoltorio a nombre de la cuenta del pedido: `error` si la respuesta
    empieza con «Error» o si hubo una excepción, `success` en cualquier otro caso.
    """

    def tool(*opciones: Any, **mas_opciones: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        registrar = server.tool(*opciones, **mas_opciones)

        def decorar(funcion: Callable[..., Any]) -> Callable[..., Any]:
            if inspect.iscoroutinefunction(funcion):
                raise TypeError(f"herramienta_auditada solo envuelve herramientas síncronas: {funcion.__name__}")
            nombre = mas_opciones.get("name") or funcion.__name__

            @functools.wraps(funcion)
            def auditada(*args: Any, **kwargs: Any) -> Any:
                ejecucion = {"auditada": False}
                marca = _ejecucion_en_curso.set(ejecucion)
                try:
                    try:
                        resultado = funcion(*args, **kwargs)
                    except Exception as error:
                        if not ejecucion["auditada"]:
                            log_mcp_tool_execution(
                                nombre,
                                _parametros_auditables(funcion, args, kwargs),
                                status="error",
                                error_message=str(error)[:LARGO_DEL_ERROR_AUDITADO],
                                db_path=db_path,
                            )
                        raise
                    if not ejecucion["auditada"]:
                        fallo = isinstance(resultado, str) and resultado.lstrip().startswith("Error")
                        log_mcp_tool_execution(
                            nombre,
                            _parametros_auditables(funcion, args, kwargs),
                            status="error" if fallo else "success",
                            error_message=resultado[:LARGO_DEL_ERROR_AUDITADO] if fallo else None,
                            db_path=db_path,
                        )
                    return resultado
                finally:
                    _ejecucion_en_curso.reset(marca)

            registrar(auditada)
            return funcion

        return decorar

    return tool


REGISTRO_DE_RECHAZO = REGISTRO_DE_RECHAZO_MCP


def registrar_rechazo_mcp(motivo: str, client_ip: str | None = None, db_path: Path | str | None = None) -> None:
    """Registra un pedido rechazado por la autenticación: no tiene cuenta y nunca guarda el token presentado."""
    _registrar_auditoria(REGISTRO_DE_RECHAZO, {}, None, None, client_ip, "error", motivo, db_path)


MAX_RECHAZOS_POR_IP = 10
VENTANA_DE_RECHAZOS_SEGUNDOS = 60.0
MAX_IPS_RECORDADAS = 1000


class FrenoDeRechazos:
    """Tope de rechazos de autenticación que se auditan por IP y por minuto, en la memoria del proceso.

    Sin él, quien manda pedidos sin token escribe una fila por pedido. Recuerda como mucho
    `MAX_IPS_RECORDADAS` direcciones: con la memoria llena y ninguna ventana vencida, los rechazos
    de una dirección nueva no se auditan, así que el total de filas por minuto también queda acotado.
    """

    def __init__(self, reloj: Callable[[], float] = time.monotonic) -> None:
        self._reloj = reloj
        self._ventanas: dict[str, tuple[float, int]] = {}
        self._cerrojo = threading.Lock()

    def permite(self, client_ip: str | None) -> bool:
        """Cuenta un rechazo de esa IP y dice si todavía entra en el tope de su minuto."""
        ip = client_ip or ""
        ahora = self._reloj()
        with self._cerrojo:
            inicio, cuenta = self._ventanas.get(ip, (ahora, 0))
            if ahora - inicio >= VENTANA_DE_RECHAZOS_SEGUNDOS:
                inicio, cuenta = ahora, 0
            if ip not in self._ventanas and len(self._ventanas) >= MAX_IPS_RECORDADAS:
                self._olvidar_vencidas(ahora)
                if len(self._ventanas) >= MAX_IPS_RECORDADAS:
                    return False
            self._ventanas[ip] = (inicio, cuenta + 1)
            return cuenta < MAX_RECHAZOS_POR_IP

    def _olvidar_vencidas(self, ahora: float) -> None:
        self._ventanas = {
            ip: ventana
            for ip, ventana in self._ventanas.items()
            if ahora - ventana[0] < VENTANA_DE_RECHAZOS_SEGUNDOS
        }

    def ips_recordadas(self) -> int:
        """Cuántas direcciones tiene en memoria."""
        return len(self._ventanas)
