"""Clave maestra, almacén cifrado de secretos y ajustes por cuenta (034 R2, R3)."""

import logging
import os
import sqlite3
import stat
import subprocess
import sys

import pytest
from conftest import CLAVE_MAESTRA_DE_PRUEBA, cuenta_de_prueba
from cryptography.fernet import Fernet

from aulento.core import secretos
from aulento.core.secretos import (
    AjustesDeCuenta,
    AlmacenDeSecretos,
    ClaveMaestraInvalida,
    SecretoIlegible,
    clave_maestra,
)
from aulento.db.connection import get_connection
from aulento.db.schema import init_db

CLAVE_DE_IA = "clave-de-ia-de-ana-0123456789-WXYZ"
OTRA_CLAVE_DE_IA = "clave-de-ia-de-beto-9876543210-QRST"
CLAVES_MAL_FORMADAS = ["no-es-una-clave-fernet", "abcd", "ñandú" * 9, Fernet.generate_key().decode()[:-3]]
# Nombres fijos: la clave recortada es al azar y con pytest-xdist cada proceso tiene que ver los mismos tests
NOMBRES_MAL_FORMADAS = ["texto", "corta", "no-ascii", "fernet-recortada"]


@pytest.fixture
def sin_variable(monkeypatch, directorio_y_clave_de_prueba):
    """Sin `AULENTO_SECRET_KEY`: la clave maestra sale del archivo del directorio de datos de prueba."""
    monkeypatch.delenv("AULENTO_SECRET_KEY")
    return directorio_y_clave_de_prueba / "clave_maestra.key"


@pytest.fixture
def base(tmp_path):
    """Base en archivo, para poder mirar qué queda escrito en el disco."""
    conn = get_connection(tmp_path / "secretos.db")
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def ana(base) -> int:
    return cuenta_de_prueba(base, "ana").id


@pytest.fixture
def beto(base) -> int:
    return cuenta_de_prueba(base, "beto").id


def _fila(conn: sqlite3.Connection, user_id: int, nombre: str) -> tuple:
    return tuple(
        conn.execute(
            "SELECT user_id, nombre, valor_cifrado, actualizado_en FROM secretos_usuario "
            "WHERE user_id = ? AND nombre = ?;",
            (user_id, nombre),
        ).fetchone()
    )


def _avisos(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == secretos.logger.name and r.levelno == logging.WARNING]


# --- Clave maestra ---


def test_la_suite_corre_con_una_clave_maestra_de_prueba(directorio_y_clave_de_prueba):
    assert os.environ["AULENTO_SECRET_KEY"] == CLAVE_MAESTRA_DE_PRUEBA
    assert clave_maestra() == CLAVE_MAESTRA_DE_PRUEBA.encode()
    assert list(directorio_y_clave_de_prueba.iterdir()) == [], "con la variable definida no se genera ningún archivo"


def test_la_clave_maestra_sale_de_la_variable_aunque_exista_el_archivo(monkeypatch, directorio_y_clave_de_prueba):
    del_archivo, de_la_variable = Fernet.generate_key(), Fernet.generate_key()
    archivo = directorio_y_clave_de_prueba / "clave_maestra.key"
    archivo.write_bytes(del_archivo)
    monkeypatch.setenv("AULENTO_SECRET_KEY", f"  {de_la_variable.decode()}\n")

    assert clave_maestra() == de_la_variable
    assert archivo.read_bytes() == del_archivo


def test_sin_variable_se_genera_una_sola_vez_y_se_avisa(sin_variable, caplog, capsys):
    caplog.set_level(logging.WARNING)

    primera = clave_maestra()

    assert sin_variable.read_bytes() == primera
    Fernet(primera)
    assert [p.name for p in sin_variable.parent.iterdir()] == ["clave_maestra.key"], "no quedan temporales"
    (aviso,) = _avisos(caplog)
    por_stderr = capsys.readouterr().err
    for texto in (aviso, por_stderr):
        assert str(sin_variable) in texto
        assert "AULENTO_SECRET_KEY" in texto
        assert primera.decode() not in texto

    assert clave_maestra() == primera
    assert clave_maestra() == primera
    assert sin_variable.read_bytes() == primera
    assert len(_avisos(caplog)) == 1, "se avisa al generarla, no cada vez que se lee"
    assert capsys.readouterr().err == ""


@pytest.mark.skipif(os.name != "posix", reason="Windows no tiene permisos de archivo por dueño, grupo y otros")
def test_el_archivo_de_la_clave_solo_lo_lee_su_dueno(sin_variable):
    clave_maestra()

    assert stat.S_IMODE(sin_variable.stat().st_mode) == 0o600


def _entradas_de_la_acl(archivo) -> list[str]:
    """Cada entrada de la ACL del archivo como la muestra `icacls`: `principal:(permisos)`."""
    icacls = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "icacls.exe")
    salida = subprocess.run([icacls, str(archivo)], capture_output=True, text=True, check=True).stdout
    # La primera línea empieza con la ruta; las entradas siguen hasta la primera línea en blanco
    entradas = []
    for linea in salida.replace(str(archivo), "", 1).splitlines():
        if not linea.strip():
            break
        entradas.append(linea.strip())
    return entradas


@pytest.mark.skipif(sys.platform != "win32", reason="las ACL que se restringen con icacls son de Windows")
def test_en_windows_el_archivo_de_la_clave_queda_solo_para_quien_corre_el_proceso(sin_variable, caplog):
    """R2: sin entradas heredadas de la carpeta ni de otros principales (en Windows `chmod` no restringe nada)."""
    caplog.set_level(logging.WARNING)
    whoami = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "whoami.exe")
    yo = subprocess.run([whoami], capture_output=True, text=True, check=True).stdout.strip().lower()
    # Un archivo cualquiera de esa carpeta nace con las entradas heredadas de ella, para más de un principal
    testigo = sin_variable.with_name("testigo.txt")
    testigo.write_text("x", encoding="utf-8")
    heredadas = _entradas_de_la_acl(testigo)
    testigo.unlink()
    assert len(heredadas) > 1 and all("(I)" in entrada for entrada in heredadas), heredadas

    clave = clave_maestra()

    entradas = _entradas_de_la_acl(sin_variable)
    assert len(entradas) == 1, entradas
    principal, permisos = entradas[0].rsplit(":", 1)
    assert principal.lower() == yo
    assert permisos == "(F)", "control total, y sin la marca (I) de una entrada heredada"
    assert sin_variable.read_bytes() == clave, "quien corre el proceso lo sigue leyendo"
    assert [r for r in _avisos(caplog) if "permisos" in r] == []


def test_si_no_se_pueden_restringir_los_permisos_se_avisa_y_la_clave_se_genera_igual(sin_variable, monkeypatch, caplog, capsys):
    caplog.set_level(logging.WARNING)
    monkeypatch.setattr(secretos, "_restringir_permisos", lambda archivo: False)

    generada = clave_maestra()

    Fernet(generada)
    assert sin_variable.read_bytes() == generada
    de_permisos = [aviso for aviso in _avisos(caplog) if "No se pudieron restringir los permisos" in aviso]
    assert len(de_permisos) == 1, "una vez por archivo, aunque se intente sobre el temporal y sobre el definitivo"
    assert str(sin_variable) in de_permisos[0] and "icacls" in de_permisos[0]
    assert "AULENTO_SECRET_KEY" in de_permisos[0] and generada.decode() not in de_permisos[0]
    assert "No se pudieron restringir los permisos" in capsys.readouterr().err
    assert clave_maestra() == generada


@pytest.mark.skipif(sys.platform != "win32", reason="las ACL que se restringen con icacls son de Windows")
@pytest.mark.parametrize("falla", ["no arranca", "termina mal", "no responde"])
def test_en_windows_una_herramienta_que_falla_no_impide_generar_la_clave(sin_variable, monkeypatch, caplog, falla):
    caplog.set_level(logging.WARNING)

    def correr(argumentos, **opciones):
        assert isinstance(argumentos, list) and not opciones.get("shell"), "con lista de argumentos y sin shell"
        if falla == "no arranca":
            raise FileNotFoundError(argumentos[0])
        if falla == "termina mal":
            raise subprocess.CalledProcessError(5, argumentos)
        raise subprocess.TimeoutExpired(argumentos, 15)

    monkeypatch.setattr(secretos.subprocess, "run", correr)

    generada = clave_maestra()

    assert sin_variable.read_bytes() == generada
    assert any("No se pudieron restringir los permisos" in aviso for aviso in _avisos(caplog))


def test_un_archivo_de_clave_existente_se_lee_sin_avisar_ni_tocarlo(sin_variable, caplog, capsys):
    caplog.set_level(logging.WARNING)
    existente = Fernet.generate_key()
    sin_variable.write_bytes(existente + b"\n")

    assert clave_maestra() == existente
    assert sin_variable.read_bytes() == existente + b"\n"
    assert _avisos(caplog) == []
    assert capsys.readouterr().err == ""


def test_si_otro_proceso_la_genero_antes_se_usa_la_suya(sin_variable, monkeypatch, caplog):
    """Dos procesos arrancan a la vez: el que llega segundo no pisa el archivo y usa la clave del primero."""
    caplog.set_level(logging.WARNING)
    del_otro = Fernet.generate_key()

    def enlazar_tarde(origen, destino):
        sin_variable.write_bytes(del_otro)
        raise FileExistsError(destino)

    monkeypatch.setattr(os, "link", enlazar_tarde)

    assert clave_maestra() == del_otro
    assert sin_variable.read_bytes() == del_otro
    assert [p.name for p in sin_variable.parent.iterdir()] == ["clave_maestra.key"]
    assert _avisos(caplog) == [], "este proceso no generó ninguna clave"


def test_sin_enlaces_duros_tambien_se_genera_sin_pisar(sin_variable, monkeypatch):
    def sin_enlaces(origen, destino):
        raise OSError("este sistema de archivos no admite enlaces duros")

    monkeypatch.setattr(os, "link", sin_enlaces)

    generada = clave_maestra()

    Fernet(generada)
    assert sin_variable.read_bytes() == generada
    assert [p.name for p in sin_variable.parent.iterdir()] == ["clave_maestra.key"]
    assert clave_maestra() == generada


@pytest.mark.parametrize("mal_formada", CLAVES_MAL_FORMADAS, ids=NOMBRES_MAL_FORMADAS)
def test_una_variable_mal_formada_falla_con_un_mensaje_claro(monkeypatch, directorio_y_clave_de_prueba, mal_formada):
    monkeypatch.setenv("AULENTO_SECRET_KEY", mal_formada)

    with pytest.raises(ClaveMaestraInvalida) as error:
        clave_maestra()

    assert "AULENTO_SECRET_KEY" in str(error.value)
    assert "no es una clave Fernet válida" in str(error.value)
    assert mal_formada not in str(error.value)
    assert list(directorio_y_clave_de_prueba.iterdir()) == [], "no se genera otra clave para tapar el error"


@pytest.mark.parametrize("mal_formada", ["", *CLAVES_MAL_FORMADAS], ids=["vacia", *NOMBRES_MAL_FORMADAS])
def test_un_archivo_mal_formado_falla_y_queda_como_estaba(sin_variable, mal_formada):
    sin_variable.write_bytes(mal_formada.encode("utf-8"))

    for _ in range(2):
        with pytest.raises(ClaveMaestraInvalida) as error:
            clave_maestra()

        assert str(sin_variable) in str(error.value)
        assert "no es una clave Fernet válida" in str(error.value)
        assert not mal_formada or mal_formada not in str(error.value)
    assert sin_variable.read_bytes() == mal_formada.encode("utf-8")
    assert [p.name for p in sin_variable.parent.iterdir()] == ["clave_maestra.key"]


def test_con_la_clave_mal_formada_no_se_guarda_ni_se_lee_nada(base, ana, monkeypatch):
    almacen = AlmacenDeSecretos(base, ana)
    almacen.guardar("gemini_clave_gratuita", CLAVE_DE_IA)
    antes = _fila(base, ana, "gemini_clave_gratuita")
    monkeypatch.setenv("AULENTO_SECRET_KEY", "no-es-una-clave-fernet")

    with pytest.raises(ClaveMaestraInvalida):
        almacen.leer("gemini_clave_gratuita")
    with pytest.raises(ClaveMaestraInvalida):
        almacen.guardar("gemini_clave_gratuita", OTRA_CLAVE_DE_IA)
    with pytest.raises(ClaveMaestraInvalida):
        almacen.guardar("gemini_clave_paga", OTRA_CLAVE_DE_IA)

    assert _fila(base, ana, "gemini_clave_gratuita") == antes
    assert almacen.nombres() == ["gemini_clave_gratuita"]


# --- Almacén de secretos ---


def test_guardar_y_leer_un_secreto_de_la_cuenta(base, ana):
    almacen = AlmacenDeSecretos(base, ana)
    assert almacen.leer("gemini_clave_gratuita") is None
    assert almacen.tiene("gemini_clave_gratuita") is False
    assert almacen.nombres() == []

    almacen.guardar("gemini_clave_gratuita", CLAVE_DE_IA)
    almacen.guardar("gdrive_cliente", '{"installed": {"client_secret": "ñ:1:gdrive_cliente:x"}}')

    assert almacen.leer("gemini_clave_gratuita") == CLAVE_DE_IA
    assert almacen.leer("gdrive_cliente") == '{"installed": {"client_secret": "ñ:1:gdrive_cliente:x"}}'
    assert almacen.tiene("gemini_clave_gratuita") is True
    assert almacen.tiene("gemini_clave_paga") is False
    assert almacen.nombres() == ["gdrive_cliente", "gemini_clave_gratuita"]


def test_guardar_de_nuevo_reemplaza_el_valor(base, ana):
    almacen = AlmacenDeSecretos(base, ana)
    almacen.guardar("gemini_clave_paga", CLAVE_DE_IA)

    almacen.guardar("gemini_clave_paga", OTRA_CLAVE_DE_IA)

    assert almacen.leer("gemini_clave_paga") == OTRA_CLAVE_DE_IA
    assert base.execute("SELECT COUNT(*) FROM secretos_usuario;").fetchone()[0] == 1


def test_lo_guardado_persiste_y_el_archivo_de_la_base_no_tiene_el_valor_en_claro(tmp_path):
    ruta = tmp_path / "en_disco.db"
    conn = get_connection(ruta)
    init_db(conn)
    cuenta = cuenta_de_prueba(conn, "ana").id
    AlmacenDeSecretos(conn, cuenta).guardar("gemini_clave_gratuita", CLAVE_DE_IA)
    cifrado = _fila(conn, cuenta, "gemini_clave_gratuita")[2]
    conn.close()

    assert isinstance(cifrado, bytes)
    assert CLAVE_DE_IA.encode() not in cifrado
    archivos = [archivo for archivo in tmp_path.iterdir() if archivo.name.startswith("en_disco.db")]
    assert ruta in archivos
    for archivo in archivos:
        contenido = archivo.read_bytes()
        assert CLAVE_DE_IA.encode() not in contenido, archivo.name
        assert CLAVE_DE_IA[-12:].encode() not in contenido, archivo.name
    assert cifrado in ruta.read_bytes(), "el test tiene que estar mirando el archivo donde quedó el secreto"

    otra = get_connection(ruta)
    assert AlmacenDeSecretos(otra, cuenta).leer("gemini_clave_gratuita") == CLAVE_DE_IA
    otra.close()


def test_dos_cuentas_con_el_mismo_nombre_de_secreto_no_se_ven(base, ana, beto):
    de_ana, de_beto = AlmacenDeSecretos(base, ana), AlmacenDeSecretos(base, beto)
    de_ana.guardar("gemini_clave_gratuita", CLAVE_DE_IA)
    assert de_beto.leer("gemini_clave_gratuita") is None
    assert de_beto.tiene("gemini_clave_gratuita") is False
    assert de_beto.pista("gemini_clave_gratuita") is None
    assert de_beto.nombres() == []
    assert de_beto.borrar("gemini_clave_gratuita") is False

    de_beto.guardar("gemini_clave_gratuita", OTRA_CLAVE_DE_IA)

    assert de_ana.leer("gemini_clave_gratuita") == CLAVE_DE_IA
    assert de_beto.leer("gemini_clave_gratuita") == OTRA_CLAVE_DE_IA
    assert de_beto.borrar("gemini_clave_gratuita") is True
    assert de_ana.leer("gemini_clave_gratuita") == CLAVE_DE_IA


def test_borrar_un_secreto(base, ana):
    almacen = AlmacenDeSecretos(base, ana)
    almacen.guardar("gemini_clave_gratuita", CLAVE_DE_IA)
    almacen.guardar("gemini_clave_paga", OTRA_CLAVE_DE_IA)

    assert almacen.borrar("gemini_clave_gratuita") is True
    assert almacen.borrar("gemini_clave_gratuita") is False

    assert almacen.leer("gemini_clave_gratuita") is None
    assert almacen.nombres() == ["gemini_clave_paga"]


def test_una_fila_copiada_a_otra_cuenta_no_descifra(base, ana, beto):
    de_ana, de_beto = AlmacenDeSecretos(base, ana), AlmacenDeSecretos(base, beto)
    de_ana.guardar("gemini_clave_gratuita", CLAVE_DE_IA)
    base.execute(
        "INSERT INTO secretos_usuario (user_id, nombre, valor_cifrado, actualizado_en) "
        "SELECT ?, nombre, valor_cifrado, actualizado_en FROM secretos_usuario WHERE user_id = ?;",
        (beto, ana),
    )
    base.commit()
    copiada = _fila(base, beto, "gemini_clave_gratuita")

    with pytest.raises(SecretoIlegible) as error:
        de_beto.leer("gemini_clave_gratuita")
    with pytest.raises(SecretoIlegible):
        de_beto.pista("gemini_clave_gratuita")

    assert (error.value.user_id, error.value.nombre) == (beto, "gemini_clave_gratuita")
    assert CLAVE_DE_IA not in str(error.value)
    assert _fila(base, beto, "gemini_clave_gratuita") == copiada
    assert de_ana.leer("gemini_clave_gratuita") == CLAVE_DE_IA


def test_una_fila_copiada_a_otro_nombre_no_descifra(base, ana):
    almacen = AlmacenDeSecretos(base, ana)
    almacen.guardar("gemini_clave_gratuita", CLAVE_DE_IA)
    base.execute(
        "INSERT INTO secretos_usuario (user_id, nombre, valor_cifrado, actualizado_en) "
        "SELECT user_id, 'gemini_clave_paga', valor_cifrado, actualizado_en FROM secretos_usuario WHERE user_id = ?;",
        (ana,),
    )
    base.commit()

    with pytest.raises(SecretoIlegible):
        almacen.leer("gemini_clave_paga")
    assert almacen.leer("gemini_clave_gratuita") == CLAVE_DE_IA


def test_una_cuenta_cuyo_id_es_prefijo_de_otro_no_lee_sus_secretos(base):
    """El prefijo `<cuenta>:<nombre>:` se compara entero: la cuenta 1 no lee como propio lo cifrado para la 11."""
    ids = [cuenta_de_prueba(base, f"cuenta-{n}").id for n in range(11)]
    corta, larga = ids[0], ids[-1]
    assert str(larga).startswith(str(corta)) and corta != larga
    AlmacenDeSecretos(base, larga).guardar("gemini_clave_gratuita", CLAVE_DE_IA)
    base.execute("UPDATE secretos_usuario SET user_id = ? WHERE user_id = ?;", (corta, larga))
    base.commit()

    with pytest.raises(SecretoIlegible):
        AlmacenDeSecretos(base, corta).leer("gemini_clave_gratuita")


def test_con_otra_clave_maestra_leer_falla_y_la_fila_sigue_igual(base, ana, monkeypatch):
    almacen = AlmacenDeSecretos(base, ana)
    almacen.guardar("gemini_clave_gratuita", CLAVE_DE_IA)
    antes = _fila(base, ana, "gemini_clave_gratuita")
    monkeypatch.setenv("AULENTO_SECRET_KEY", Fernet.generate_key().decode())

    with pytest.raises(SecretoIlegible) as error:
        almacen.leer("gemini_clave_gratuita")
    with pytest.raises(SecretoIlegible):
        almacen.pista("gemini_clave_gratuita")

    assert "gemini_clave_gratuita" in str(error.value)
    assert "clave maestra" in str(error.value)
    assert "no se modificó" in str(error.value)
    assert CLAVE_DE_IA not in str(error.value)
    assert _fila(base, ana, "gemini_clave_gratuita") == antes
    assert almacen.tiene("gemini_clave_gratuita") is True
    assert almacen.nombres() == ["gemini_clave_gratuita"]

    # Con la clave original de vuelta, el secreto sigue ahí
    monkeypatch.setenv("AULENTO_SECRET_KEY", CLAVE_MAESTRA_DE_PRUEBA)
    assert almacen.leer("gemini_clave_gratuita") == CLAVE_DE_IA


@pytest.mark.parametrize("basura", [b"", b"no es un token", "texto en vez de bytes", b"\xff\xfe\x00"])
def test_un_valor_cifrado_roto_es_ilegible_y_no_se_toca(base, ana, basura):
    almacen = AlmacenDeSecretos(base, ana)
    base.execute(
        "INSERT INTO secretos_usuario (user_id, nombre, valor_cifrado, actualizado_en) VALUES (?, ?, ?, '2026-01-01');",
        (ana, "gdrive_autorizacion", basura),
    )
    base.commit()

    with pytest.raises(SecretoIlegible):
        almacen.leer("gdrive_autorizacion")

    assert _fila(base, ana, "gdrive_autorizacion") == (ana, "gdrive_autorizacion", basura, "2026-01-01")


def test_un_secreto_ilegible_se_puede_volver_a_cargar(base, ana, monkeypatch):
    almacen = AlmacenDeSecretos(base, ana)
    almacen.guardar("gemini_clave_gratuita", CLAVE_DE_IA)
    monkeypatch.setenv("AULENTO_SECRET_KEY", Fernet.generate_key().decode())

    almacen.guardar("gemini_clave_gratuita", OTRA_CLAVE_DE_IA)

    assert almacen.leer("gemini_clave_gratuita") == OTRA_CLAVE_DE_IA


@pytest.mark.parametrize(
    ("valor", "pista"),
    [
        (CLAVE_DE_IA, "WXYZ"),
        ("123456789", "6789"),
        ("12345678", ""),
        ("abc", ""),
        ("clave-con-eñes-ñandú", "andú"),
    ],
)
def test_la_pista_son_los_ultimos_cuatro_caracteres_salvo_en_valores_cortos(base, ana, valor, pista):
    almacen = AlmacenDeSecretos(base, ana)
    assert almacen.pista("gemini_clave_gratuita") is None

    almacen.guardar("gemini_clave_gratuita", valor)

    assert almacen.pista("gemini_clave_gratuita") == pista


@pytest.mark.parametrize("vacio", ["", "   ", "\n\t"])
def test_un_valor_vacio_se_rechaza_y_no_pisa_el_guardado(base, ana, vacio):
    almacen = AlmacenDeSecretos(base, ana)
    almacen.guardar("gemini_clave_gratuita", CLAVE_DE_IA)

    with pytest.raises(ValueError, match="no puede estar vacío"):
        almacen.guardar("gemini_clave_gratuita", vacio)
    with pytest.raises(ValueError, match="no puede estar vacío"):
        almacen.guardar("gemini_clave_paga", vacio)

    assert almacen.leer("gemini_clave_gratuita") == CLAVE_DE_IA
    assert almacen.nombres() == ["gemini_clave_gratuita"]


@pytest.mark.parametrize("valor", [None, 12345678901234, b"clave-en-bytes-0123456789", {"clave": CLAVE_DE_IA}])
def test_un_valor_que_no_es_texto_se_rechaza_sin_mostrarlo(base, ana, valor):
    almacen = AlmacenDeSecretos(base, ana)

    with pytest.raises(TypeError) as error:
        almacen.guardar("gemini_clave_gratuita", valor)

    assert "tiene que ser texto" in str(error.value)
    assert "0123456789" not in str(error.value) and "12345678901234" not in str(error.value)
    assert almacen.nombres() == []


@pytest.mark.parametrize("nombre", ["", "Gemini", "con:dos_puntos", "1:gemini", "con espacio", "ñ", "a" * 65, None, 7])
@pytest.mark.parametrize("operacion", ["guardar", "leer", "borrar", "tiene", "pista"])
def test_un_nombre_de_secreto_invalido_se_rechaza(base, ana, nombre, operacion):
    almacen = AlmacenDeSecretos(base, ana)
    argumentos = (nombre, CLAVE_DE_IA) if operacion == "guardar" else (nombre,)

    with pytest.raises(ValueError, match="Nombre de secreto inválido") as error:
        getattr(almacen, operacion)(*argumentos)

    assert CLAVE_DE_IA not in str(error.value)
    assert base.execute("SELECT COUNT(*) FROM secretos_usuario;").fetchone()[0] == 0


@pytest.mark.parametrize("cuenta", [None, 0, -3, True, "1"])
@pytest.mark.parametrize("almacen", [AlmacenDeSecretos, AjustesDeCuenta])
def test_los_almacenes_no_se_construyen_sin_cuenta(base, almacen, cuenta):
    with pytest.raises(ValueError, match="cuenta dueña"):
        almacen(base, cuenta)


def test_ni_la_representacion_ni_los_registros_muestran_el_secreto(base, ana, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    almacen = AlmacenDeSecretos(base, ana)

    almacen.guardar("gemini_clave_gratuita", CLAVE_DE_IA)
    almacen.leer("gemini_clave_gratuita")
    almacen.pista("gemini_clave_gratuita")
    almacen.tiene("gemini_clave_gratuita")

    assert repr(almacen) == f"AlmacenDeSecretos(user_id={ana})"
    assert CLAVE_DE_IA not in str(almacen)
    assert CLAVE_DE_IA not in str(vars(almacen))
    salida = capsys.readouterr()
    assert CLAVE_DE_IA not in caplog.text + salida.out + salida.err
    assert CLAVE_MAESTRA_DE_PRUEBA not in caplog.text + salida.out + salida.err


def test_los_nombres_fijos_estan_en_un_solo_lugar_y_son_validos(base, ana):
    assert secretos.NOMBRES_DE_SECRETOS == (
        "gemini_clave_gratuita",
        "gemini_clave_paga",
        "anthropic_clave",
        "openai_clave",
    )
    assert secretos.CLAVES_DE_AJUSTES == (
        "gemini_nivel_activo",
        "gemini_modelo",
        "prompt_ruta",
        "prompt_clase",
        "duolingo_usuario",
        "duolingo_cache",
        "vault_externo",
        "carpetas_del_tutor",
        "ia_proveedor_activo",
        "anthropic_modelo",
        "openai_modelo",
        "onboarding_completado",
    )
    constantes ={nombre: valor for nombre, valor in vars(secretos).items() if nombre.startswith(("SECRETO_", "AJUSTE_"))}
    assert sorted(constantes.values()) == sorted(secretos.NOMBRES_DE_SECRETOS + secretos.CLAVES_DE_AJUSTES)

    almacen, ajustes = AlmacenDeSecretos(base, ana), AjustesDeCuenta(base, ana)
    for nombre in secretos.NOMBRES_DE_SECRETOS:
        almacen.guardar(nombre, f"valor-de-{nombre}")
    for clave in secretos.CLAVES_DE_AJUSTES:
        ajustes.guardar(clave, clave)
    assert almacen.nombres() == sorted(secretos.NOMBRES_DE_SECRETOS)
    assert ajustes.claves() == sorted(secretos.CLAVES_DE_AJUSTES)


# --- Ajustes de la cuenta ---


@pytest.mark.parametrize(
    "valor",
    [
        "gemini-flash-latest",
        {"gdrive": {"enabled": True}, "onedrive": {"enabled": False, "tenant_id": None}},
        ["a", 1, 2.5, None],
        True,
        False,
        0,
        None,
        "ñandú — «texto»",
    ],
)
def test_guardar_y_leer_un_ajuste(base, ana, valor):
    ajustes = AjustesDeCuenta(base, ana)
    assert ajustes.leer("conectores") is None
    assert ajustes.leer("conectores", "por defecto") == "por defecto"

    ajustes.guardar("conectores", valor)

    leido = ajustes.leer("conectores", "por defecto")
    assert leido == valor and type(leido) is type(valor)
    assert ajustes.claves() == ["conectores"]


def test_los_ajustes_se_guardan_como_json_y_se_reemplazan(base, ana):
    ajustes = AjustesDeCuenta(base, ana)
    ajustes.guardar("gemini_modelo", "gemini-flash-lite-latest")

    ajustes.guardar("gemini_modelo", {"modelo": "gemini-pro-latest", "año": 2026})

    filas = base.execute("SELECT user_id, clave, valor FROM ajustes_usuario;").fetchall()
    assert [tuple(fila) for fila in filas] == [(ana, "gemini_modelo", '{"modelo": "gemini-pro-latest", "año": 2026}')]
    assert repr(ajustes) == f"AjustesDeCuenta(user_id={ana})"


def test_los_ajustes_de_una_cuenta_no_los_ve_la_otra(base, ana, beto):
    de_ana, de_beto = AjustesDeCuenta(base, ana), AjustesDeCuenta(base, beto)
    de_ana.guardar("duolingo_usuario", "ana-en-duolingo")
    de_ana.guardar("prompt_ruta", "prompt de ana")
    assert de_beto.leer("duolingo_usuario") is None
    assert de_beto.claves() == []
    assert de_beto.borrar("duolingo_usuario") is False

    de_beto.guardar("duolingo_usuario", "beto-en-duolingo")

    assert de_ana.leer("duolingo_usuario") == "ana-en-duolingo"
    assert de_beto.leer("duolingo_usuario") == "beto-en-duolingo"
    assert de_beto.borrar("duolingo_usuario") is True
    assert de_beto.borrar("duolingo_usuario") is False
    assert de_beto.leer("duolingo_usuario", "sin usuario") == "sin usuario"
    assert de_ana.claves() == ["duolingo_usuario", "prompt_ruta"]


def test_un_ajuste_que_no_entra_en_json_o_con_clave_invalida_no_se_guarda(base, ana):
    ajustes = AjustesDeCuenta(base, ana)
    ajustes.guardar("vault_externo", "/srv/vault")

    with pytest.raises(TypeError):
        ajustes.guardar("vault_externo", {"ruta": object()})
    for clave in ("", "Vault", "con:dos_puntos", None):
        with pytest.raises(ValueError, match="Nombre de ajuste inválido"):
            ajustes.guardar(clave, "x")
        with pytest.raises(ValueError, match="Nombre de ajuste inválido"):
            ajustes.leer(clave)
        with pytest.raises(ValueError, match="Nombre de ajuste inválido"):
            ajustes.borrar(clave)

    assert ajustes.leer("vault_externo") == "/srv/vault"
    assert ajustes.claves() == ["vault_externo"]


def test_borrar_la_cuenta_se_lleva_sus_secretos_y_ajustes(base, ana, beto):
    for cuenta in (ana, beto):
        AlmacenDeSecretos(base, cuenta).guardar("gemini_clave_gratuita", CLAVE_DE_IA)
        AjustesDeCuenta(base, cuenta).guardar("gemini_modelo", "gemini-flash-latest")

    base.execute("DELETE FROM usuarios WHERE id = ?;", (beto,))
    base.commit()

    assert [f[0] for f in base.execute("SELECT user_id FROM secretos_usuario;").fetchall()] == [ana]
    assert [f[0] for f in base.execute("SELECT user_id FROM ajustes_usuario;").fetchall()] == [ana]
    assert AlmacenDeSecretos(base, ana).leer("gemini_clave_gratuita") == CLAVE_DE_IA
