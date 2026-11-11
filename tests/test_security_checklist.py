"""La matriz de `docs/SECURITY_CHECKLIST.md` no nombra pruebas que no existen."""

import re
from pathlib import Path

import pytest

TESTS = Path(__file__).parent
CHECKLIST = TESTS.parent / "docs" / "SECURITY_CHECKLIST.md"
# Un control que nombra la prueba sin archivo vive en la suite de auditoría original
ARCHIVO_POR_DEFECTO = "test_deep_security_audit.py"
FILA = re.compile(r"^\| \*\*(CHK-\d{2}\.\d+)\*\* \| ([^|]+) \| [^|]+ \| [^|]+ \| `([^`|]+)` \|$", flags=re.MULTILINE)

# Una cita de un test en cualquier parte del documento: `tests/archivo.py::test`, `archivo.py::test`, un archivo
# de tests solo (`tests/test_x.py`) o un nombre suelto (`test_x`)
CITA = re.compile(r"`(?:tests/)?(?:(test_\w+\.py)(?:::(test_\w+))?|(test_\w+))`")


def _controles() -> list[tuple[str, str, str, str]]:
    """Filas de la matriz como (id, dominio, archivo, prueba)."""
    controles = []
    for id_control, dominio, referencia in FILA.findall(CHECKLIST.read_text(encoding="utf-8")):
        archivo, _, prueba = referencia.rpartition("::")
        controles.append((id_control, dominio.strip(), archivo or ARCHIVO_POR_DEFECTO, prueba))
    return controles


def _define(archivo: str, prueba: str) -> bool:
    ruta = TESTS / archivo
    if not ruta.is_file():
        return False
    return re.search(rf"^def {re.escape(prueba)}\(", ruta.read_text(encoding="utf-8"), flags=re.MULTILINE) is not None


def test_la_matriz_se_lee_entera_y_sin_controles_repetidos():
    texto = CHECKLIST.read_text(encoding="utf-8")
    controles = _controles()

    ids = [id_control for id_control, *_ in controles]

    # Toda fila que empieza como un control tiene la forma que este test sabe leer
    assert len(ids) == len(re.findall(r"^\| \*\*CHK-", texto, flags=re.MULTILINE))
    assert len(ids) == len(set(ids))
    assert f"Todos los {len(ids)} controles" in texto


@pytest.mark.parametrize(("id_control", "dominio", "archivo", "prueba"), _controles(), ids=lambda valor: valor)
def test_cada_control_nombra_una_prueba_que_existe(id_control, dominio, archivo, prueba):
    assert prueba.startswith("test_"), f"{id_control} no nombra una prueba"
    assert _define(archivo, prueba), f"{id_control} nombra {archivo}::{prueba}, que no existe"


def _citas(texto: str) -> list[tuple[str, str]]:
    """Cada test citado en el texto como (archivo, prueba); el archivo vacío es un nombre suelto y la prueba vacía, un archivo solo."""
    return [(archivo, prueba or suelto) for archivo, prueba, suelto in CITA.findall(texto)]


def _existe(archivo: str, prueba: str) -> bool:
    if not archivo:
        # Un nombre suelto vale si lo define algún archivo de la suite
        return any(_define(ruta.name, prueba) for ruta in TESTS.glob("test_*.py"))
    return _define(archivo, prueba) if prueba else (TESTS / archivo).is_file()


def test_ninguna_cita_del_documento_nombra_un_test_que_no_existe():
    """No solo la matriz: el detalle por dominio, los riesgos y los comandos de verificación también citan tests."""
    texto = CHECKLIST.read_text(encoding="utf-8")
    citas = _citas(texto)
    # Los archivos que se pasan a `pytest` en los bloques de comandos también son citas
    de_los_comandos = [(nombre, "") for nombre in re.findall(r"tests/(test_\w+\.py)", texto)]

    # Cada control cita su prueba y cada bloque de comandos nombra archivos: con menos, la búsqueda se rompió.
    # La cifra depende del checklist: el que se publica con el core trae menos controles (051, R8).
    assert len(citas) >= len(_controles()) > 40 and len(de_los_comandos) > 5, (
        "la búsqueda de citas dejó de encontrar el documento"
    )
    assert sorted({cita for cita in citas + de_los_comandos if not _existe(*cita)}) == []


def test_la_busqueda_de_citas_reconoce_cada_forma_y_muerde():
    citas = _citas(
        "`tests/test_secretos.py::test_no_existe` y `test_secretos.py::test_tampoco`, `tests/test_no_hay.py`, "
        "`test_suelto_que_no_existe`, `tests/test_secretos.py` y `test_security_checklist.py::test_la_busqueda_de_citas_reconoce_cada_forma_y_muerde`"
    )

    assert citas == [
        ("test_secretos.py", "test_no_existe"),
        ("test_secretos.py", "test_tampoco"),
        ("test_no_hay.py", ""),
        ("", "test_suelto_que_no_existe"),
        ("test_secretos.py", ""),
        ("test_security_checklist.py", "test_la_busqueda_de_citas_reconoce_cada_forma_y_muerde"),
    ]
    assert [_existe(*cita) for cita in citas] == [False, False, False, False, True, True]
    assert _existe("", "test_la_matriz_se_lee_entera_y_sin_controles_repetidos")
