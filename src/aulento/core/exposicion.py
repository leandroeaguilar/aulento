"""Reglas para escuchar fuera de la máquina: clave maestra, cifrado y proxies de confianza (ADR 013)."""

import ipaddress
import os

from aulento.core.secretos import (
    VARIABLE_DE_LA_CLAVE_MAESTRA,
    ClaveMaestraInvalida,
    _validar_clave,
)

VARIABLE_DE_PROXIES_DE_CONFIANZA = "AULENTO_TRUSTED_PROXIES"
HOSTS_DE_BUCLE_LOCAL = frozenset({"127.0.0.1", "::1", "[::1]", "localhost"})

AVISO_HTTP_SIN_CIFRAR = (
    "Acceso remoto sin cifrar: el servidor acepta conexiones de otros equipos por HTTP, así que contraseñas, "
    "cookies y tokens viajan en claro. Usalo solo en una red de confianza o detrás de un túnel cifrado."
)


class ExposicionRechazada(RuntimeError):
    """El servidor no puede escuchar fuera de la máquina con la configuración actual."""


class ProxyDeConfianzaInvalido(ValueError):
    """Un valor de `AULENTO_TRUSTED_PROXIES` no es una dirección IP ni una red."""

    def __init__(self, valor: str) -> None:
        self.valor = valor
        super().__init__(
            f"{VARIABLE_DE_PROXIES_DE_CONFIANZA} trae un valor que no es una dirección IP ni una red: «{valor}». "
            "Indicá direcciones o redes separadas por comas, por ejemplo 172.30.0.2 o 10.0.0.0/24."
        )


def es_bucle_local(host: str) -> bool:
    """Indica si `host` es una dirección de bucle local: escuchar ahí no expone el servidor a otros equipos."""
    return host.strip().lower() in HOSTS_DE_BUCLE_LOCAL


def proxies_de_confianza() -> list[str]:
    """Redes de los proxies cuyas cabeceras `X-Forwarded-*` se creen; sin la variable, ninguna.

    Cada valor se devuelve como red (`172.30.0.2` queda `172.30.0.2/32`). Un valor que no es una dirección
    ni una red levanta `ProxyDeConfianzaInvalido`: no se descarta en silencio, porque cambiaría a quién se cree.
    """
    redes: list[str] = []
    for valor in os.getenv(VARIABLE_DE_PROXIES_DE_CONFIANZA, "").split(","):
        valor = valor.strip()
        if not valor:
            continue
        try:
            redes.append(str(ipaddress.ip_network(valor, strict=False)))
        except ValueError:
            raise ProxyDeConfianzaInvalido(valor) from None
    return redes


def exigir_modo_compatible_con_la_exposicion(host: str | None = None) -> None:
    """En modo local no hay login: se niega a exponerse fuera de la máquina (ADR 017).

    Cuenta como exposición un `host` que no es de bucle local (lo que recibe la CLI) o un proxy de confianza
    declarado (señal de que hay un proxy público delante, aunque Uvicorn se haya lanzado sin la CLI).
    Levanta `ExposicionRechazada` si hay que frenar; el modo inválido propaga `ModoInvalido`.
    """
    from aulento.config import is_local_mode

    if not is_local_mode():
        return
    expuesto_por_host = host is not None and not es_bucle_local(host)
    expuesto_por_proxy = bool(os.getenv(VARIABLE_DE_PROXIES_DE_CONFIANZA, "").strip())
    if not (expuesto_por_host or expuesto_por_proxy):
        return
    motivo = f"escuchar en {host}" if expuesto_por_host else f"declarar {VARIABLE_DE_PROXIES_DE_CONFIANZA}"
    raise ExposicionRechazada(
        f"El modo local no tiene login: cualquiera que llegue al servidor entra como administrador, y {motivo} "
        "lo expone a otros equipos. Para usarlo solo vos, escuchá en 127.0.0.1. Para abrirlo a otras personas, "
        "definí AULENTO_MODE=saas (cuentas con login)."
    )


def _exigir_clave_maestra_por_variable() -> None:
    """La clave maestra tiene que venir de la variable: nunca se genera ni se lee el archivo junto a los datos."""
    de_la_variable = (os.getenv(VARIABLE_DE_LA_CLAVE_MAESTRA) or "").strip()
    if not de_la_variable:
        raise ExposicionRechazada(
            f"Para escuchar fuera de esta máquina hay que definir {VARIABLE_DE_LA_CLAVE_MAESTRA} con la clave "
            "maestra: sin ella la clave se guardaría junto a los datos, y quien copie ese directorio leería todos "
            "los secretos. Si ya tenés un archivo de clave maestra, usá su contenido como valor de la variable."
        )
    try:
        _validar_clave(de_la_variable.encode("utf-8"), f"la variable {VARIABLE_DE_LA_CLAVE_MAESTRA}")
    except ClaveMaestraInvalida as error:
        raise ExposicionRechazada(str(error)) from None


def exigir_condiciones_para_exponerse(host: str, *, cifrado: bool, insecure_http: bool) -> list[str]:
    """Comprueba que se pueda escuchar en `host` y devuelve los avisos que hay que mostrar al arrancar.

    La lista de proxies de confianza se valida siempre (`ProxyDeConfianzaInvalido`). Fuera del bucle local se
    exige además la clave maestra por variable y una de tres cosas: certificado propio (`cifrado`), al menos un
    proxy de confianza o `insecure_http`; si falta algo levanta `ExposicionRechazada`.
    """
    proxies = proxies_de_confianza()
    if es_bucle_local(host):
        return []
    _exigir_clave_maestra_por_variable()
    if not cifrado and not proxies and not insecure_http:
        raise ExposicionRechazada(
            f"Escuchar en {host} expone el servidor a otros equipos y sin cifrado la conexión (contraseñas, cookies "
            "y tokens incluidos) viaja en claro. Indicá --ssl-certfile y --ssl-keyfile, declará el proxy con HTTPS "
            f"que tenés delante en {VARIABLE_DE_PROXIES_DE_CONFIANZA}, o agregá --insecure-http si es una red de "
            "confianza o hay un túnel cifrado delante."
        )
    if insecure_http and not cifrado:
        return [AVISO_HTTP_SIN_CIFRAR]
    return []
