"""Pruebas unitarias e integrales para el conector y sincronizador de Duolingo (Feature 010), por cuenta (034)."""

import json
import re
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from conftest import cuenta_de_prueba, cuenta_en
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import aulento
from aulento.cli import contexto
from aulento.cli.app import cli
from aulento.connectors.duolingo import (
    MENSAJE_SIN_USUARIO,
    DuolingoClient,
    DuolingoSinConfigurar,
    DuolingoSyncResult,
)
from aulento.core.secretos import (
    AJUSTE_DUOLINGO_CACHE,
    AJUSTE_DUOLINGO_USUARIO,
    AjustesDeCuenta,
)
from aulento.db.connection import get_connection
from aulento.vault.weekly_digest import WeeklyDigestExporter
from aulento.web.app import create_app

cli_runner = CliRunner()

USUARIO = "estudiante_duo"


def _respuesta_de_duolingo(usuario: str = USUARIO, racha: int = 5, xp: int = 1250) -> MagicMock:
    cuerpo = {
        "users": [
            {
                "id": 655723656,
                "username": usuario,
                "name": f"Nombre de {usuario}",
                "streak": racha,
                "totalXp": xp,
                "learningLanguage": "en",
                "courses": [
                    {
                        "id": "DUOLINGO_EN_ES",
                        "title": "English",
                        "learningLanguage": "en",
                        "fromLanguage": "es",
                        "xp": xp,
                        "crowns": 10,
                    }
                ],
                "streakData": {"currentStreak": {"length": racha, "startDate": "2026-09-20", "endDate": "2026-09-24"}},
                "hasRecentActivity15": True,
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(cuerpo).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    return mock_resp


def _red_por_usuario(pedidos: list[str]):
    """Doble de `urlopen`: anota cada URL pedida y responde el perfil del usuario de la consulta."""

    def abrir(req, timeout=None):
        pedidos.append(req.full_url)
        usuario = req.full_url.split("username=")[1]
        return _respuesta_de_duolingo(usuario, racha=len(usuario), xp=100 * len(usuario))

    return abrir


@pytest.fixture
def cliente_duo(memory_db) -> DuolingoClient:
    return DuolingoClient(memory_db, cuenta_de_prueba(memory_db).id)


@pytest.fixture(autouse=True)
def cli_sin_cuenta_indicada():
    contexto.indicar_cuenta(None)
    yield
    contexto.indicar_cuenta(None)


def test_duolingo_client_fetch_and_cache(cliente_duo):
    """Verifica que el cliente procese la respuesta pública y persista la caché de la cuenta."""
    cliente_duo.fijar_usuario(USUARIO)

    with patch("urllib.request.urlopen", return_value=_respuesta_de_duolingo()):
        profile = cliente_duo.get_profile(USUARIO)

    assert profile.username == USUARIO
    assert profile.name == f"Nombre de {USUARIO}"
    assert profile.streak == 5
    assert profile.total_xp == 1250
    assert profile.learning_language == "en"
    assert not profile.is_cached
    assert cliente_duo.ajustes.leer(AJUSTE_DUOLINGO_CACHE)["username"] == USUARIO

    # Segunda lectura simulando corte de red (debe leer desde la caché)
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Network unreachable")):
        cached_profile = cliente_duo.get_profile(USUARIO)

    assert cached_profile.username == USUARIO
    assert cached_profile.streak == 5
    assert cached_profile.is_cached


def test_duolingo_client_sync_result(cliente_duo):
    """Verifica que el método sync retorne un resultado tipado."""
    with patch("urllib.request.urlopen", return_value=_respuesta_de_duolingo()):
        res = cliente_duo.sync(USUARIO)

    assert isinstance(res, DuolingoSyncResult)
    assert res.status == "ok"
    assert res.streak == 5
    assert res.total_xp == 1250
    assert "1,250" in res.message or "1250" in res.message


def test_duolingo_web_api():
    """Verifica los endpoints REST de FastAPI para Duolingo."""
    client = TestClient(create_app())

    with patch("urllib.request.urlopen", return_value=_respuesta_de_duolingo()):
        # 1. GET /api/duolingo/profile
        res_profile = client.get(f"/api/duolingo/profile?username={USUARIO}")
        assert res_profile.status_code == 200
        data = res_profile.json()
        assert data["username"] == USUARIO
        assert data["streak"] == 5

        # 2. POST /api/duolingo/sync
        res_sync = client.post("/api/duolingo/sync", json={"username": USUARIO})
        assert res_sync.status_code == 200
        sync_data = res_sync.json()
        assert sync_data["status"] == "ok"
        assert sync_data["streak"] == 5


def test_duolingo_cli():
    """Verifica los comandos de terminal de Duolingo (status y sync)."""
    cuenta_en()

    with patch("urllib.request.urlopen", return_value=_respuesta_de_duolingo()):
        # 1. status
        res_status = cli_runner.invoke(cli, ["duolingo", "status", "--username", USUARIO])
        assert res_status.exit_code == 0
        assert f"Nombre de {USUARIO}" in res_status.stdout
        assert "5 días" in res_status.stdout

        # 2. sync
        res_sync = cli_runner.invoke(cli, ["duolingo", "sync", "--username", USUARIO])
        assert res_sync.exit_code == 0
        assert "Sincronización exitosa" in res_sync.stdout


def test_weekly_digest_includes_duolingo(memory_db, tmp_path):
    """Verifica que el Weekly Digest de Obsidian incluya la sección de Duolingo y hábitos."""
    cuenta = cuenta_de_prueba(memory_db).id
    DuolingoClient(memory_db, cuenta).fijar_usuario(USUARIO)

    with patch("urllib.request.urlopen", return_value=_respuesta_de_duolingo()):
        exporter = WeeklyDigestExporter(cuenta, conn=memory_db, vault_path=tmp_path)
        digest = exporter.build_digest("2026-W39")

    assert f"Duolingo (@{USUARIO})" in digest["content"]
    assert "Google Labs (LLL)" in digest["content"]
    assert "5 días de racha" in digest["content"]


# --- 034, R7: el usuario y la caché son de cada cuenta ---


def test_r7_sin_usuario_configurado_no_se_consulta_nada(cliente_duo):
    with patch("urllib.request.urlopen") as red:
        resultado = cliente_duo.sync()
        with pytest.raises(DuolingoSinConfigurar):
            cliente_duo.get_profile()

    assert red.call_count == 0
    assert (resultado.status, resultado.username, resultado.source) == ("sin_configurar", "", "none")
    assert resultado.message == MENSAJE_SIN_USUARIO
    assert cliente_duo.ajustes.claves() == []


def test_r7_el_resumen_semanal_sin_usuario_lo_dice_y_no_consulta(memory_db, tmp_path):
    with patch("urllib.request.urlopen") as red:
        exporter = WeeklyDigestExporter(cuenta_de_prueba(memory_db).id, conn=memory_db, vault_path=tmp_path)
        digest = exporter.build_digest("2026-W39")

    assert red.call_count == 0
    assert "- **Duolingo:** Sin usuario configurado." in digest["content"]


def test_r7_cada_cuenta_tiene_su_usuario_y_su_cache(memory_db):
    ana = DuolingoClient(memory_db, cuenta_de_prueba(memory_db, "ana").id)
    beto = DuolingoClient(memory_db, cuenta_de_prueba(memory_db, "beto").id)
    pedidos: list[str] = []

    with patch("urllib.request.urlopen", side_effect=_red_por_usuario(pedidos)):
        assert ana.sync("duo_de_ana").username == "duo_de_ana"
        sin_usuario = beto.sync()
        assert beto.sync("el_duo_de_beto").username == "el_duo_de_beto"
        assert ana.sync().username == "duo_de_ana"

    assert sin_usuario.status == "sin_configurar"
    assert [url.split("username=")[1] for url in pedidos] == ["duo_de_ana", "el_duo_de_beto", "duo_de_ana"]
    assert (ana.usuario_configurado(), beto.usuario_configurado()) == ("duo_de_ana", "el_duo_de_beto")
    assert ana.ajustes.leer(AJUSTE_DUOLINGO_CACHE)["username"] == "duo_de_ana"
    assert beto.ajustes.leer(AJUSTE_DUOLINGO_CACHE)["username"] == "el_duo_de_beto"

    # Sin red, cada una lee su propia caché
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("sin red")):
        assert ana.get_profile().streak == len("duo_de_ana")
        assert beto.get_profile().streak == len("el_duo_de_beto")


def test_r7_quitar_o_cambiar_el_usuario_descarta_la_cache_solo_de_esa_cuenta(memory_db):
    ana = DuolingoClient(memory_db, cuenta_de_prueba(memory_db, "ana").id)
    beto = DuolingoClient(memory_db, cuenta_de_prueba(memory_db, "beto").id)
    with patch("urllib.request.urlopen", side_effect=_red_por_usuario([])):
        ana.sync("duo_de_ana")
        beto.sync("el_duo_de_beto")

    assert ana.fijar_usuario("  Otro_Usuario ") == "otro_usuario"
    assert ana.ajustes.leer(AJUSTE_DUOLINGO_CACHE) is None
    assert beto.fijar_usuario("") is None

    assert beto.ajustes.claves() == []
    assert ana.ajustes.claves() == [AJUSTE_DUOLINGO_USUARIO]


def test_r7_consultar_a_otro_usuario_no_pisa_la_cache_ni_el_usuario_de_la_cuenta(cliente_duo):
    with patch("urllib.request.urlopen", side_effect=_red_por_usuario([])):
        cliente_duo.sync(USUARIO)
        ajeno = cliente_duo.get_profile("otro_cualquiera")

    assert ajeno.username == "otro_cualquiera"
    assert cliente_duo.usuario_configurado() == USUARIO
    assert cliente_duo.ajustes.leer(AJUSTE_DUOLINGO_CACHE)["username"] == USUARIO


def test_r7_las_variables_de_entorno_no_fijan_el_usuario_ni_la_cache(cliente_duo, tmp_path, monkeypatch):
    archivo = tmp_path / "cache_global.json"
    monkeypatch.setenv("AULENTO_DUOLINGO_CACHE", str(archivo))
    monkeypatch.setenv("DUOLINGO_USERNAME", "usuario_de_toda_la_instalacion")

    with patch("urllib.request.urlopen", side_effect=_red_por_usuario(pedidos := [])):
        assert cliente_duo.sync().status == "sin_configurar"
        cliente_duo.sync(USUARIO)

    assert [url.split("username=")[1] for url in pedidos] == [USUARIO]
    assert not archivo.exists()


def test_r7_la_cli_fija_el_usuario_de_su_cuenta_y_sin_usuario_no_consulta():
    cuenta = cuenta_en()
    pedidos: list[str] = []

    with patch("urllib.request.urlopen", side_effect=_red_por_usuario(pedidos)):
        sin_usuario = cli_runner.invoke(cli, ["duolingo", "sync"])
        estado_sin_usuario = cli_runner.invoke(cli, ["duolingo", "status"])
        fijado = cli_runner.invoke(cli, ["duolingo", "set-user", "Duo_Por_CLI"])
        sincronizado = cli_runner.invoke(cli, ["duolingo", "sync"])
        solo_pedidos_con_usuario = list(pedidos)
        quitado = cli_runner.invoke(cli, ["duolingo", "set-user", "--clear"])
        otra_vez_sin_usuario = cli_runner.invoke(cli, ["duolingo", "sync"])
        ambiguo = cli_runner.invoke(cli, ["duolingo", "set-user"])

    assert (sin_usuario.exit_code, estado_sin_usuario.exit_code) == (1, 1)
    assert "Falta configurar tu usuario de Duolingo" in " ".join(sin_usuario.stdout.split())
    assert "Falta configurar tu usuario de Duolingo" in " ".join(estado_sin_usuario.stdout.split())
    assert fijado.exit_code == 0 and "duo_por_cli" in fijado.stdout
    assert sincronizado.exit_code == 0 and "Sincronización exitosa" in sincronizado.stdout
    assert [url.split("username=")[1] for url in solo_pedidos_con_usuario] == ["duo_por_cli"]
    assert quitado.exit_code == 0
    assert otra_vez_sin_usuario.exit_code == 1
    assert ambiguo.exit_code == 1
    assert pedidos == solo_pedidos_con_usuario
    conn = get_connection()
    try:
        assert AjustesDeCuenta(conn, cuenta).claves() == []
    finally:
        conn.close()


# --- 034, R11: el código no trae el usuario de nadie ---


def test_r11_el_codigo_no_contiene_el_usuario_de_duolingo_del_dueno():
    """Ni el core ni sus tests nombran el usuario que antes venía fijo como valor por defecto.

    La nube (su paquete y sus tests `test_nube_*`) queda afuera: enlaza al sitio del autor,
    que se llama igual que ese usuario, y no tiene nada de Duolingo.
    """
    usuario_del_dueno = "raliugaeordnael"[::-1]
    raiz = Path(aulento.__file__).parents[2]
    hallados = [
        str(archivo.relative_to(raiz))
        for carpeta in (raiz / "src" / "aulento", raiz / "tests")
        for archivo in carpeta.rglob("*")
        if archivo.is_file()
        and not archivo.name.startswith("test_nube_")
        and archivo.suffix in {".py", ".js", ".html", ".css", ".json", ".md", ".txt", ".toml"}
        and usuario_del_dueno in archivo.read_text(encoding="utf-8", errors="ignore").lower()
    ]

    assert hallados == []


def test_r11_el_conector_no_trae_ningun_usuario_por_defecto():
    """Ningún parámetro `username` del conector, la ruta ni los comandos tiene un texto como valor por defecto."""
    raiz = Path(aulento.__file__).parent
    archivos = ["connectors/duolingo.py", "web/routes/duolingo.py", "cli/duolingo_commands.py", "vault/weekly_digest.py"]
    con_defecto = [
        (nombre, hallado)
        for nombre in archivos
        for hallado in re.findall(
            r'username[^=\n]*=\s*(?:Query\(|typer\.(?:Option|Argument)\(\s*)?["\'][^"\']+["\']',
            (raiz / nombre).read_text(encoding="utf-8"),
        )
    ]

    assert con_defecto == []
    assert "get_profile(\"" not in (raiz / "vault/weekly_digest.py").read_text(encoding="utf-8")
