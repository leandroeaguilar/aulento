"""El asistente de inicio de la CLI crea la cuenta local, sin nombre ni contraseña que pedir (051, R6 y R7)."""

import sqlite3

import pytest
from typer.testing import CliRunner

from aulento.auth import servicio
from aulento.cli import contexto
from aulento.cli.app import cli

runner = CliRunner()


@pytest.fixture
def base(tmp_path, monkeypatch):
    """Base propia y todavía sin crear, sin cuenta indicada por opción ni por variable."""
    archivo = tmp_path / "asistente.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(archivo))
    monkeypatch.delenv(contexto.VARIABLE_DE_CUENTA, raising=False)
    monkeypatch.setenv("AULENTO_DATA_DIR", str(tmp_path / "datos"))
    contexto.indicar_cuenta(None)
    yield archivo
    contexto.indicar_cuenta(None)


def test_r7_sin_ninguna_cuenta_el_asistente_crea_la_cuenta_local_con_el_mazo(base):
    # Opción 2 (con el mazo), sin clave de IA, sin abrir el servidor
    resultado = runner.invoke(cli, ["onboarding"], input="2\n\nn\n", env={"COLUMNS": "200"})

    assert resultado.exit_code == 0, resultado.output
    assert "Cuenta local lista" in resultado.output
    conexion = sqlite3.connect(base)
    try:
        cuentas = conexion.execute("SELECT id, nombre_usuario, rol, activo FROM usuarios;").fetchall()
        tarjetas = conexion.execute("SELECT COUNT(*) FROM fsrs_items WHERE user_id = ?;", (servicio.ID_DE_LA_CUENTA_LOCAL,))
        assert cuentas == [(servicio.ID_DE_LA_CUENTA_LOCAL, servicio.NOMBRE_DE_LA_CUENTA_LOCAL, "admin", 1)]
        assert tarjetas.fetchone()[0] > 100
        # Sin contraseña con la que ingresar: el modo local no tiene ingreso
        hash_guardado = conexion.execute("SELECT contrasena_hash FROM usuarios;").fetchone()[0]
        assert hash_guardado == servicio.SIN_CONTRASENA
    finally:
        conexion.close()
