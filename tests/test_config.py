"""Directorio de datos único (034 R1): sale de `config.py` y ningún otro módulo de `src/` lo arma por su cuenta."""

import os
import re
from pathlib import Path

import pytest
from conftest import cuenta_en

from aulento import config
from aulento.config import dir_de_cuenta, get_data_dir, get_db_path

RAIZ_DEL_CODIGO = Path(__file__).resolve().parents[1] / "src"
UNICO_QUE_RESUELVE = "aulento/config.py"

# Maneras de armar el directorio de datos sin pasar por `get_data_dir()`
RESOLUCIONES_PROPIAS = {
    "la carpeta por nombre": re.compile(r"\.study-engine|\.aulento(?![\w.])"),
    "la carpeta personal": re.compile(r"\bhome\s*\(|expanduser|USERPROFILE|environ\b[^\n]*\bHOME\b|getenv\(\s*[\"']HOME\b"),
    "la variable del directorio": re.compile(r"AULENTO_DATA_DIR"),
    "el valor por defecto": re.compile(r"\bDEFAULT_DATA_DIR\b"),
}


def resoluciones_propias_en(texto: str) -> list[str]:
    """Qué maneras de armar el directorio de datos por cuenta propia aparecen en un texto de código."""
    return [nombre for nombre, patron in RESOLUCIONES_PROPIAS.items() if patron.search(texto)]


# --- De dónde sale el directorio ---


def test_el_directorio_sale_de_la_variable_y_se_crea(monkeypatch, tmp_path):
    elegido = tmp_path / "todavia" / "no-existe"
    monkeypatch.setenv("AULENTO_DATA_DIR", str(elegido))

    assert get_data_dir() == elegido
    assert elegido.is_dir()


@pytest.mark.parametrize("variable", [None, "", "   "], ids=["sin variable", "vacía", "en blanco"])
def test_sin_variable_el_directorio_es_el_valor_por_defecto(monkeypatch, tmp_path, variable):
    assert config.DEFAULT_DATA_DIR == Path.home() / ".aulento"
    # El valor por defecto se sustituye: el test no crea la carpeta real de quien corre la suite
    por_defecto = tmp_path / "hogar" / ".aulento"
    monkeypatch.setattr(config, "DEFAULT_DATA_DIR", por_defecto)
    if variable is None:
        monkeypatch.delenv("AULENTO_DATA_DIR")
    else:
        monkeypatch.setenv("AULENTO_DATA_DIR", variable)

    assert get_data_dir() == por_defecto
    assert por_defecto.is_dir()


def test_la_base_vive_en_el_directorio_de_datos_salvo_que_se_indique_otra(monkeypatch, tmp_path):
    elegido = tmp_path / "datos"
    monkeypatch.setenv("AULENTO_DATA_DIR", str(elegido))
    monkeypatch.delenv("AULENTO_DB_PATH")

    assert get_db_path() == elegido / "study_engine.db"
    assert not elegido.exists(), "pedir la ruta de la base no crea nada: la crea `ensure_data_dir` al conectar"

    monkeypatch.setenv("AULENTO_DB_PATH", str(tmp_path / "otra" / "base.db"))
    assert get_db_path() == tmp_path / "otra" / "base.db"


def test_cada_cuenta_tiene_su_carpeta_dentro_del_directorio_de_datos(directorio_y_clave_de_prueba):
    de_la_7, de_la_8 = dir_de_cuenta(7), dir_de_cuenta(8)

    assert de_la_7 == directorio_y_clave_de_prueba / "usuarios" / "7"
    assert de_la_8 == directorio_y_clave_de_prueba / "usuarios" / "8"
    assert de_la_7.is_dir() and de_la_8.is_dir()


@pytest.mark.parametrize("cuenta", [None, 0, -1, True, "7", 7.0, "../7"])
def test_sin_una_cuenta_valida_no_hay_carpeta(directorio_y_clave_de_prueba, cuenta):
    with pytest.raises(ValueError, match="cuenta dueña"):
        dir_de_cuenta(cuenta)

    assert list(directorio_y_clave_de_prueba.iterdir()) == []


# --- La suite no toca el directorio real ---


def test_la_suite_corre_con_un_directorio_de_datos_de_prueba(directorio_y_clave_de_prueba, tmp_path_factory):
    assert os.environ["AULENTO_DATA_DIR"] == str(directorio_y_clave_de_prueba)
    assert get_data_dir() == directorio_y_clave_de_prueba
    assert directorio_y_clave_de_prueba.is_relative_to(tmp_path_factory.getbasetemp())
    assert not get_data_dir().is_relative_to(config.DEFAULT_DATA_DIR)
    assert list(directorio_y_clave_de_prueba.iterdir()) == [], "cada test recibe un directorio de datos vacío"


def test_los_archivos_del_sistema_se_resuelven_dentro_del_directorio_de_prueba(directorio_y_clave_de_prueba, monkeypatch):
    """Los módulos que antes armaban la ruta por su cuenta caen ahora en el directorio de la suite."""
    from aulento.vault import rutas as rutas_del_vault

    monkeypatch.delenv("AULENTO_DUOLINGO_CACHE", raising=False)

    # La configuración de conectores y la autorización de Drive ya no son archivos: viven en la base, por cuenta (034)
    rutas = [
        rutas_del_vault.vault_propio(cuenta_en()),
    ]

    fuera = [str(ruta) for ruta in rutas if not Path(ruta).is_relative_to(directorio_y_clave_de_prueba)]
    assert fuera == []


# --- Nadie más arma la ruta (estático) ---


def test_ningun_modulo_arma_el_directorio_de_datos_por_su_cuenta():
    archivos = sorted(RAIZ_DEL_CODIGO.rglob("*.py"))
    assert len(archivos) > 50, "el recorrido tiene que encontrar el código"

    hallazgos = {
        archivo.relative_to(RAIZ_DEL_CODIGO).as_posix(): resoluciones_propias_en(archivo.read_text(encoding="utf-8"))
        for archivo in archivos
    }

    assert set(hallazgos.pop(UNICO_QUE_RESUELVE)) == {
        "la carpeta por nombre",
        "la carpeta personal",
        "la variable del directorio",
        "el valor por defecto",
    }, "`config.py` es el lugar donde se resuelve: si dejó de hacerlo, este test ya no vigila nada"
    assert {archivo: formas for archivo, formas in hallazgos.items() if formas} == {}, (
        "Estos módulos arman el directorio de datos por su cuenta: tienen que usar `config.get_data_dir()`."
    )


@pytest.mark.parametrize(
    "codigo",
    [
        'ruta = Path.home() / ".study-engine" / "gdrive_token.json"',
        "base = pathlib.Path.home()",
        'base = os.path.expanduser("~/datos")',
        'base = os.getenv("AULENTO_DATA_DIR")',
        'base = Path(os.environ["USERPROFILE"]) / "datos"',
        'base = os.environ.get("HOME")',
        "from aulento.config import DEFAULT_DATA_DIR",
        "# los datos viven en ~/.study-engine/",
    ],
)
def test_el_recorrido_marca_cada_manera_de_armar_la_ruta(codigo):
    assert resoluciones_propias_en(codigo) != []


@pytest.mark.parametrize(
    "codigo",
    [
        "base = get_data_dir()",
        'archivo = config.get_data_dir() / "mcp_config.json"',
        'ruta = os.getenv("AULENTO_DB_PATH")',
        "carpeta = dir_de_cuenta(self.user_id)",
        'pagina = "home"',
    ],
)
def test_el_recorrido_deja_pasar_el_codigo_que_usa_el_directorio_unico(codigo):
    assert resoluciones_propias_en(codigo) == []
