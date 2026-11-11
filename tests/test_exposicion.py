"""Reglas para escuchar fuera de la máquina: clave maestra, cifrado y proxies de confianza (039, R1, R2, R3)."""

import pytest
from conftest import CLAVE_MAESTRA_DE_PRUEBA
from cryptography.fernet import Fernet

from aulento.config import get_data_dir
from aulento.core.exposicion import (
    AVISO_HTTP_SIN_CIFRAR,
    VARIABLE_DE_PROXIES_DE_CONFIANZA,
    ExposicionRechazada,
    ProxyDeConfianzaInvalido,
    es_bucle_local,
    exigir_condiciones_para_exponerse,
    proxies_de_confianza,
)
from aulento.core.secretos import (
    ARCHIVO_DE_LA_CLAVE_MAESTRA,
    VARIABLE_DE_LA_CLAVE_MAESTRA,
)

CLAVE_MAL_FORMADA = "no-es-una-clave-fernet-de-verdad"
EXPUESTOS = ["0.0.0.0", "192.168.1.20", "::"]


@pytest.fixture(autouse=True)
def sin_proxies(monkeypatch):
    monkeypatch.delenv(VARIABLE_DE_PROXIES_DE_CONFIANZA, raising=False)


def _archivo_de_clave():
    return get_data_dir() / ARCHIVO_DE_LA_CLAVE_MAESTRA


# --- Bucle local ---


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "[::1]", "localhost", "LocalHost", " 127.0.0.1 "])
def test_las_direcciones_de_bucle_local_no_exponen(host):
    assert es_bucle_local(host) is True


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.20", "::", "10.0.0.5", "mi-pc.local"])
def test_cualquier_otra_direccion_expone(host):
    assert es_bucle_local(host) is False


# --- Proxies de confianza (R3) ---


def test_sin_la_variable_ningun_proxy_es_de_confianza_tampoco_127_0_0_1():
    assert proxies_de_confianza() == []


@pytest.mark.parametrize("valor", ["", " ", " , ,"])
def test_la_variable_vacia_deja_la_lista_vacia(monkeypatch, valor):
    monkeypatch.setenv(VARIABLE_DE_PROXIES_DE_CONFIANZA, valor)
    assert proxies_de_confianza() == []


def test_se_aceptan_direcciones_redes_e_ipv6_con_espacios(monkeypatch):
    monkeypatch.setenv(VARIABLE_DE_PROXIES_DE_CONFIANZA, " 172.30.0.2 , 10.0.0.0/24,::1, 192.168.1.7/24 ")
    assert proxies_de_confianza() == ["172.30.0.2/32", "10.0.0.0/24", "::1/128", "192.168.1.0/24"]


@pytest.mark.parametrize("invalido", ["*", "proxy.local", "300.1.1.1", "10.0.0.0/99", "127.0.0.1:8000"])
def test_un_valor_que_no_es_direccion_ni_red_levanta_el_error_con_el_valor(monkeypatch, invalido):
    monkeypatch.setenv(VARIABLE_DE_PROXIES_DE_CONFIANZA, f"172.30.0.2,{invalido}")
    with pytest.raises(ProxyDeConfianzaInvalido) as error:
        proxies_de_confianza()
    assert error.value.valor == invalido
    assert f"«{invalido}»" in str(error.value) and VARIABLE_DE_PROXIES_DE_CONFIANZA in str(error.value)


@pytest.mark.parametrize("host", ["127.0.0.1", "0.0.0.0"])
def test_una_lista_invalida_frena_el_arranque_en_cualquier_direccion(monkeypatch, host):
    monkeypatch.setenv(VARIABLE_DE_PROXIES_DE_CONFIANZA, "proxy.local")
    with pytest.raises(ProxyDeConfianzaInvalido):
        exigir_condiciones_para_exponerse(host, cifrado=True, insecure_http=True)


# --- En bucle local no se exige nada ---


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "[::1]"])
def test_en_bucle_local_no_exige_clave_ni_cifrado(monkeypatch, host):
    monkeypatch.delenv(VARIABLE_DE_LA_CLAVE_MAESTRA, raising=False)
    assert exigir_condiciones_para_exponerse(host, cifrado=False, insecure_http=False) == []
    assert not _archivo_de_clave().exists()


# --- Fuera del bucle local: clave maestra (R1) ---


@pytest.mark.parametrize("host", EXPUESTOS)
@pytest.mark.parametrize("valor", [None, "", "   "])
def test_sin_clave_se_rechaza_nombrando_la_variable_y_sin_crear_el_archivo(monkeypatch, host, valor):
    if valor is None:
        monkeypatch.delenv(VARIABLE_DE_LA_CLAVE_MAESTRA, raising=False)
    else:
        monkeypatch.setenv(VARIABLE_DE_LA_CLAVE_MAESTRA, valor)

    with pytest.raises(ExposicionRechazada) as error:
        # Aun con certificado: la clave se exige siempre que el servidor se expone
        exigir_condiciones_para_exponerse(host, cifrado=True, insecure_http=False)

    assert VARIABLE_DE_LA_CLAVE_MAESTRA in str(error.value)
    assert not _archivo_de_clave().exists()


def test_con_clave_mal_formada_se_rechaza_sin_mostrarla_ni_crear_el_archivo(monkeypatch):
    monkeypatch.setenv(VARIABLE_DE_LA_CLAVE_MAESTRA, CLAVE_MAL_FORMADA)

    with pytest.raises(ExposicionRechazada) as error:
        exigir_condiciones_para_exponerse("0.0.0.0", cifrado=True, insecure_http=False)

    assert VARIABLE_DE_LA_CLAVE_MAESTRA in str(error.value)
    assert CLAVE_MAL_FORMADA not in str(error.value)
    assert not _archivo_de_clave().exists()


def test_un_archivo_de_clave_existente_no_reemplaza_a_la_variable(monkeypatch):
    archivo = _archivo_de_clave()
    clave_del_archivo = Fernet.generate_key()
    archivo.write_bytes(clave_del_archivo)
    monkeypatch.delenv(VARIABLE_DE_LA_CLAVE_MAESTRA, raising=False)

    with pytest.raises(ExposicionRechazada) as error:
        exigir_condiciones_para_exponerse("0.0.0.0", cifrado=True, insecure_http=False)

    assert clave_del_archivo.decode("ascii") not in str(error.value)
    # El archivo queda como estaba: ni se lee para validar ni se toca
    assert archivo.read_bytes() == clave_del_archivo


# --- Fuera del bucle local: cifrado (R2) ---


@pytest.mark.parametrize("host", EXPUESTOS)
def test_con_clave_y_sin_cifrado_proxies_ni_insecure_http_se_rechaza(host):
    with pytest.raises(ExposicionRechazada) as error:
        exigir_condiciones_para_exponerse(host, cifrado=False, insecure_http=False)

    mensaje = str(error.value)
    for alternativa in ("--ssl-certfile", "--ssl-keyfile", VARIABLE_DE_PROXIES_DE_CONFIANZA, "--insecure-http"):
        assert alternativa in mensaje


def test_con_certificado_pasa_sin_avisos():
    assert exigir_condiciones_para_exponerse("0.0.0.0", cifrado=True, insecure_http=False) == []


def test_con_un_proxy_de_confianza_pasa_sin_aviso_de_http(monkeypatch):
    monkeypatch.setenv(VARIABLE_DE_PROXIES_DE_CONFIANZA, "172.30.0.2")
    assert exigir_condiciones_para_exponerse("0.0.0.0", cifrado=False, insecure_http=False) == []


def test_con_insecure_http_pasa_y_avisa_que_va_sin_cifrar():
    avisos = exigir_condiciones_para_exponerse("0.0.0.0", cifrado=False, insecure_http=True)
    assert avisos == [AVISO_HTTP_SIN_CIFRAR]
    assert "sin cifrar" in AVISO_HTTP_SIN_CIFRAR


def test_insecure_http_no_reemplaza_a_la_clave(monkeypatch):
    monkeypatch.delenv(VARIABLE_DE_LA_CLAVE_MAESTRA, raising=False)
    with pytest.raises(ExposicionRechazada):
        exigir_condiciones_para_exponerse("0.0.0.0", cifrado=False, insecure_http=True)
    assert not _archivo_de_clave().exists()


# --- Ningún mensaje lleva el valor de la clave ---


def test_ningun_mensaje_ni_aviso_contiene_la_clave(monkeypatch):
    mensajes = []
    with pytest.raises(ExposicionRechazada) as error:
        exigir_condiciones_para_exponerse("0.0.0.0", cifrado=False, insecure_http=False)
    mensajes.append(str(error.value))
    mensajes.extend(exigir_condiciones_para_exponerse("0.0.0.0", cifrado=False, insecure_http=True))

    monkeypatch.setenv(VARIABLE_DE_LA_CLAVE_MAESTRA, CLAVE_MAL_FORMADA)
    with pytest.raises(ExposicionRechazada) as error:
        exigir_condiciones_para_exponerse("0.0.0.0", cifrado=True, insecure_http=False)
    mensajes.append(str(error.value))

    assert len(mensajes) == 3
    for mensaje in mensajes:
        assert CLAVE_MAESTRA_DE_PRUEBA not in mensaje
        assert CLAVE_MAL_FORMADA not in mensaje
