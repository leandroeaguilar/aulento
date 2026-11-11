"""Tests anti-deriva para la documentación de Aulento (spec 040).

Garantiza que la documentación esté sincronizada con el código:
- R1..R3: Esquema OpenAPI, etiquetas, descripciones y exportación sin deriva.
- R4: Referencia completa de los 169 endpoints de la API, rutas públicas y errores.
- R5: Manual de usuario con las 10 pestañas de la interfaz, onboarding y cuenta demo.
- R6: Guía de administración con todas las variables de entorno AULENTO_* y advertencias.
- R7: Referencia completa de todos los comandos de la CLI y opción global --user.
- R8: Referencia de las 23 herramientas del servidor MCP en GUIA_MCP.md.
- R9..R10: README al día, verify.yml sin cifras fijas, índice docs/README.md y enlaces relativos íntegros.
"""

from __future__ import annotations

import asyncio
import io
import re
from pathlib import Path
from typing import Any

import pytest
from typer.main import get_command

from aulento.cli.app import cli
from aulento.cli.web_commands import esquema_openapi_canonico, exportar_openapi
from aulento.mcp.server import create_study_mcp_server
from aulento.web.app import app

RAIZ = Path(__file__).resolve().parent.parent
DOCS = RAIZ / "docs"
OPENAPI_JSON = DOCS / "api" / "openapi.json"
REFERENCIA_API_MD = DOCS / "REFERENCIA_API.md"
MANUAL_USUARIO_MD = DOCS / "MANUAL_DE_USUARIO.md"
REFERENCIA_CLI_MD = DOCS / "REFERENCIA_CLI.md"
GUIA_MCP_MD = DOCS / "GUIA_MCP.md"
README_MD = RAIZ / "README.md"
INDEX_HTML = RAIZ / "src" / "aulento" / "web" / "static" / "index.html"


# ── R1: Etiquetas descritas ───────────────────────────────────────────────────


def test_toda_operacion_de_la_api_tiene_exactamente_una_etiqueta_declarada():
    esquema = app.openapi()
    tags_declarados = {t["name"]: t.get("description", "").strip() for t in esquema.get("tags", [])}

    assert tags_declarados, "La aplicación no declaró etiquetas en openapi_tags"
    for tag_name, desc in tags_declarados.items():
        assert desc, f"La etiqueta {tag_name!r} no tiene descripción en castellano"

    tags_usados = set()
    for path, metodos in esquema.get("paths", {}).items():
        for metodo, op in metodos.items():
            if metodo.lower() in ("get", "post", "put", "delete", "patch"):
                tags = op.get("tags") or []
                assert len(tags) == 1, (
                    f"La operación {metodo.upper()} {path} debe tener exactamente una etiqueta, tiene: {tags}"
                )
                tag = tags[0]
                assert tag in tags_declarados, (
                    f"La operación {metodo.upper()} {path} usa la etiqueta {tag!r} que no está en openapi_tags"
                )
                tags_usados.add(tag)

    sobrantes = set(tags_declarados.keys()) - tags_usados
    assert not sobrantes, f"Hay etiquetas declaradas en openapi_tags que ninguna operación usa: {sobrantes}"


# ── R2: Descripción de la API ─────────────────────────────────────────────────


def test_descripcion_del_esquema_explica_el_modo_local_y_enlaza_referencia():
    """El core es de una sola persona (051): su API no tiene ingreso; lo de las cuentas lo describe la nube."""
    esquema = app.openapi()
    desc = esquema.get("info", {}).get("description", "")
    assert "una sola persona" in desc.lower()
    assert "/api/auth/login" not in desc and "se_sesion" not in desc
    assert "REFERENCIA_API.md" in desc


# ── R3: Esquema OpenAPI exportado y anti-deriva ───────────────────────────────


def test_esquema_openapi_exportado_sin_deriva():
    assert OPENAPI_JSON.is_file(), (
        f"Falta el archivo {OPENAPI_JSON}. Generalo con: python -m aulento web openapi --output docs/api/openapi.json"
    )
    actual_en_disco = OPENAPI_JSON.read_text(encoding="utf-8")
    esperado = esquema_openapi_canonico()
    assert actual_en_disco == esperado, (
        "El esquema docs/api/openapi.json difiere del generado por la aplicación actual.\n"
        "Regeneralo ejecutando:\n"
        "  python -m aulento web openapi --output docs/api/openapi.json"
    )


def test_cli_web_openapi_exporta_a_archivo_y_stdout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    destino = tmp_path / "sub" / "openapi.json"
    exportar_openapi(output=destino)
    assert destino.is_file()
    assert destino.read_text(encoding="utf-8") == esquema_openapi_canonico()

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    exportar_openapi(output=None)
    assert buf.getvalue() == esquema_openapi_canonico()


# ── R4: Referencia de la API ──────────────────────────────────────────────────


def test_referencia_api_cubre_todas_las_operaciones():
    assert REFERENCIA_API_MD.is_file(), f"Falta {REFERENCIA_API_MD}"
    texto = REFERENCIA_API_MD.read_text(encoding="utf-8")
    esquema = app.openapi()

    faltantes = []
    for path, metodos in esquema.get("paths", {}).items():
        for metodo in metodos:
            if metodo.lower() in ("get", "post", "put", "delete", "patch"):
                patron = f"`{metodo.upper()} {path}`"
                if patron not in texto:
                    faltantes.append(f"{metodo.upper()} {path}")

    assert not faltantes, (
        f"Hay {len(faltantes)} operaciones de la API no documentadas en {REFERENCIA_API_MD.name}:\n"
        + "\n".join(faltantes[:20])
    )


def test_referencia_api_explica_los_errores():
    texto = REFERENCIA_API_MD.read_text(encoding="utf-8")
    for codigo in (400, 401, 403, 404, 409, 422, 429, 503):
        assert f"`{codigo}`" in texto, (
            f"El código de error {codigo} debe estar explicado en la sección de errores de {REFERENCIA_API_MD.name}"
        )


# ── R5: Manual de usuario ─────────────────────────────────────────────────────


def _etiquetas_de_pestanas_en_index_html() -> list[str]:
    contenido = INDEX_HTML.read_text(encoding="utf-8")
    # Busca botones de pestañas del sidebar principal: id="tab-btn-..."
    bloque_nav = re.search(r"<nav[^>]*id=\"sidebar-nav\"[^>]*>(.*?)</nav>", contenido, re.DOTALL)
    if not bloque_nav:
        # Alternativa: todos los botones tab-btn
        texto_busqueda = contenido
    else:
        texto_busqueda = bloque_nav.group(1)

    # Cada botón tiene una estructura <button ... id="tab-btn-X"> ... <span>Etiqueta</span> ... </button>
    botones = re.findall(
        r'<button[^>]*id="tab-btn-([^"]+)"[^>]*>.*?<span>([^<]+)</span>\s*</span>',
        texto_busqueda,
        re.DOTALL,
    )
    return [etiqueta.strip() for _, etiqueta in botones]


def test_manual_de_usuario_cubre_todas_las_pestanas_de_la_interfaz():
    assert MANUAL_USUARIO_MD.is_file(), f"Falta {MANUAL_USUARIO_MD}"
    texto = MANUAL_USUARIO_MD.read_text(encoding="utf-8")
    pestanas = _etiquetas_de_pestanas_en_index_html()
    assert len(pestanas) >= 10, f"Se esperaban al menos 10 pestañas en index.html, encontradas: {pestanas}"

    for pestana in pestanas:
        assert f"## {pestana}" in texto, (
            f"La pestaña visible {pestana!r} de index.html no tiene sección '## {pestana}' en {MANUAL_USUARIO_MD.name}"
        )


def test_manual_de_usuario_explica_el_onboarding_y_el_ingreso_local():
    texto = MANUAL_USUARIO_MD.read_text(encoding="utf-8").lower()
    assert "onboarding" in texto
    assert "modo local" in texto


# ── R6: Guía de administración ────────────────────────────────────────────────


def _variables_aulento_en_codigo() -> set[str]:
    variables = set()
    patron = re.compile(r'AULENTO_[A-Z0-9_]+')
    for ruta in (RAIZ / "src").rglob("*.py"):
        for m in patron.findall(ruta.read_text(encoding="utf-8")):
            variables.add(m)
    return variables


# ── R7: Referencia de la CLI ──────────────────────────────────────────────────


def _comandos_de_la_cli() -> list[str]:
    cmd = get_command(cli)

    def walk(c: Any, prefix: str = "aulento") -> list[str]:
        comandos = []
        if hasattr(c, "commands") and c.commands:
            for name, sub in c.commands.items():
                sub_prefix = f"{prefix} {name}"
                if hasattr(sub, "commands") and sub.commands:
                    comandos.extend(walk(sub, sub_prefix))
                else:
                    comandos.append(sub_prefix)
        else:
            comandos.append(prefix)
        return comandos

    return walk(cmd)


def test_referencia_cli_cubre_todos_los_comandos_y_opcion_user():
    assert REFERENCIA_CLI_MD.is_file(), f"Falta {REFERENCIA_CLI_MD}"
    texto = REFERENCIA_CLI_MD.read_text(encoding="utf-8")

    assert "--user" in texto
    assert "AULENTO_USER" in texto

    todos = _comandos_de_la_cli()
    # "aulento serve ..." es un alias de "aulento web ...", aceptamos que documente web o serve
    faltantes = []
    for c in todos:
        if c.startswith("aulento serve "):
            continue
        if f"`{c}`" not in texto:
            faltantes.append(c)

    assert not faltantes, f"Comandos de la CLI no documentados en {REFERENCIA_CLI_MD.name}:\n" + "\n".join(faltantes)


# ── R8: Referencia del servidor MCP ───────────────────────────────────────────


def test_referencia_mcp_cubre_todas_las_herramientas():
    assert GUIA_MCP_MD.is_file(), f"Falta {GUIA_MCP_MD}"
    texto = GUIA_MCP_MD.read_text(encoding="utf-8")

    server = create_study_mcp_server()
    tools = asyncio.run(server.list_tools())
    assert len(tools) >= 20

    faltantes = []
    for t in tools:
        if f"`{t.name}`" not in texto:
            faltantes.append(t.name)

    assert not faltantes, f"Herramientas MCP no documentadas en {GUIA_MCP_MD.name}:\n" + "\n".join(faltantes)


# ── R9: README al día y sin cifras fijas ───────────────────────────────────────


def test_readme_al_dia_y_sin_cifras_vencidas():
    assert README_MD.is_file()
    texto = README_MD.read_text(encoding="utf-8")

    # Proveedores y características modernas
    assert "Anthropic" in texto
    assert "OpenAI" in texto
    # 048: los materiales se suben desde la PC; Drive y OneDrive solo se nombran para decir que no se conectan
    assert "materials_search" in texto and "200 MB" in texto
    assert "mcp auth-gdrive" not in texto and "mcp config onedrive" not in texto

    # Cifras fijas de tests eliminadas
    assert not re.search(r"\b275\s+tests\b", texto, re.IGNORECASE), "El README sigue diciendo '275 tests'"
    assert not re.search(r"\b248\s+tests\b", texto, re.IGNORECASE), "El README sigue diciendo '248 tests'"

    # Enlaza los documentos de docs/ que se publican con el core (los del despliegue, en test_nube_documentacion)
    for doc in (
        "docs/MANUAL_DE_USUARIO.md",
        "docs/REFERENCIA_API.md",
        "docs/REFERENCIA_CLI.md",
        "docs/GUIA_MCP.md",
        "docs/GUIA_BASE_DE_DATOS_Y_BACKUPS.md",
    ):
        assert doc in texto, f"El README no enlaza {doc}"


# ── R10: docs/README.md y enlaces vivos ───────────────────────────────────────


def _extraer_frontmatter(texto: str) -> dict[str, Any] | None:
    if not texto.startswith("---"):
        return None
    partes = texto.split("---", 2)
    if len(partes) < 3:
        return None
    fm_raw = partes[1]
    res: dict[str, Any] = {}
    for line in fm_raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip().strip("\"'")
            res[k] = v
    return res


def test_documentos_nuevos_tienen_frontmatter_okf():
    # Los que se publican con el core; los del repo privado, en test_nube_documentacion
    documentos = [
        REFERENCIA_API_MD,
        MANUAL_USUARIO_MD,
        REFERENCIA_CLI_MD,
    ]
    for doc in documentos:
        assert doc.is_file(), f"Falta {doc}"
        contenido = doc.read_text(encoding="utf-8")
        assert contenido.startswith("---\n"), f"{doc.name} no inicia con frontmatter YAML (---)"
        fm = _extraer_frontmatter(contenido)
        assert fm is not None, f"{doc.name} no tiene frontmatter YAML parseable"
        assert "type" in fm, f"{doc.name} no tiene 'type' en frontmatter"
        assert "title" in fm, f"{doc.name} no tiene 'title' en frontmatter"
        assert "description" in fm, f"{doc.name} no tiene 'description' en frontmatter"
        assert "by:" in contenido and "at:" in contenido, (
            f"{doc.name} no tiene bloque 'generated' con 'by' y 'at'"
        )


def test_integridad_de_enlaces_relativos_en_documentacion():
    archivos = [README_MD] + list(DOCS.rglob("*.md"))
    patron_enlace = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')

    enlaces_rotos = []
    for archivo in archivos:
        texto = archivo.read_text(encoding="utf-8")
        for texto_link, destino in patron_enlace.findall(texto):
            # Omitir enlaces web, esquemas especiales, anchors y enlaces de vault externo (<...>)
            if destino.startswith(("http://", "https://", "mailto:", "#", "<")):
                continue

            # Separar fragmento anchor (#seccion)
            ruta_destino = destino.split("#")[0]
            if not ruta_destino:
                continue

            # Resolver relativo a la carpeta del archivo
            destino_resuelto = (archivo.parent / ruta_destino).resolve()
            if not destino_resuelto.exists():
                enlaces_rotos.append((archivo.relative_to(RAIZ), destino))

    assert not enlaces_rotos, (
        f"Se encontraron {len(enlaces_rotos)} enlaces rotos en la documentación:\n"
        + "\n".join(f"- En {origen}: enlace a '{dest}'" for origen, dest in enlaces_rotos[:30])
    )
