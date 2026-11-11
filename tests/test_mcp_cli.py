"""Comandos CLI de MCP: sin Google Drive ni OneDrive quedan el servidor y sus tokens (048, R12)."""

import pytest
from typer.testing import CliRunner

from aulento.cli.app import cli

runner = CliRunner()


@pytest.mark.parametrize(
    "comando",
    [
        ["mcp", "status"],
        ["mcp", "toggle", "gdrive"],
        ["mcp", "config", "gdrive"],
        ["mcp", "search", "Machine Learning"],
        ["mcp", "inspect", "un-archivo"],
        ["mcp", "auth-gdrive"],
        ["mcp", "disconnect-gdrive"],
        ["vault", "list-cloud-materials"],
        ["vault", "note-from-cloud", "--file-id", "un-archivo"],
    ],
)
def test_los_comandos_de_drive_y_onedrive_ya_no_existen(cuenta, comando):
    res = runner.invoke(cli, comando)

    assert res.exit_code == 2
    assert "No such command" in res.output


def test_quedan_el_servidor_y_los_tokens():
    res = runner.invoke(cli, ["mcp", "--help"])

    assert res.exit_code == 0
    assert "serve" in res.output and "token" in res.output
    assert "drive" not in res.output.lower()
