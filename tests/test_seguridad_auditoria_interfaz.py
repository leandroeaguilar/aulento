"""Tests de seguridad para la interfaz y modelos de curso (066: R13, R14, R15).

Verifica:
- R13: escapeHtml en todos los títulos y campos de texto en planificador adaptativo y macro-FSRS.
- R14: Ningún onclick en app.js interpola texto guardado en strings de JS (uso de data-* y listeners).
- R15: formatObsidianUri codifica para atributo HTML y el servidor rechaza ruta_obsidian y ruta_local
  con comillas, '<', '>' o caracteres de control al crear y actualizar.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from aulento.models.curso import CursoCreate, CursoUpdate
from tests.front import js_del_front

APP_JS_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "aulento"
    / "web"
    / "static"
    / "app.js"
)


# ==============================================================================
# R13: Planificador adaptativo y macro-FSRS usan escapeHtml
# ==============================================================================


def test_r13_planificador_adaptativo_escapa_titulos_y_descripciones() -> None:
    """R13: generateAdaptiveStudyPlan DEBE escapar b.titulo, b.meta_especifica, b.descripcion y horas."""
    contenido = js_del_front().replace("\r\n", "\n")

    # Extraer el cuerpo de generateAdaptiveStudyPlan
    m = re.search(
        r"async function generateAdaptiveStudyPlan\(\)\s*\{([\s\S]*?)\n\}\n\nasync function",
        contenido,
    )
    assert m is not None, "No se encontró generateAdaptiveStudyPlan en app.js"
    cuerpo = m.group(1)

    # Verificar que los campos no se interpolan en crudo dentro de card.innerHTML
    assert "${b.titulo}" not in cuerpo, (
        "b.titulo se interpola sin escapeHtml en generateAdaptiveStudyPlan (hallazgo R13)"
    )
    assert "${b.meta_especifica" not in cuerpo or "${escapeHtml(b.meta_especifica" in cuerpo, (
        "b.meta_especifica se interpola sin escapeHtml en generateAdaptiveStudyPlan (hallazgo R13)"
    )
    assert "${b.descripcion}" not in cuerpo, (
        "b.descripcion se interpola sin escapeHtml en generateAdaptiveStudyPlan (hallazgo R13)"
    )

    # Verificar que se usa escapeHtml
    assert "${escapeHtml(b.titulo" in cuerpo
    assert "${escapeHtml(b.descripcion" in cuerpo


def test_r13_macro_fsrs_escapa_titulos() -> None:
    """R13: loadMacroFsrsTopics DEBE escapar t.ruta_titulo y t.tema_titulo."""
    contenido = js_del_front().replace("\r\n", "\n")

    m = re.search(
        r"async function loadMacroFsrsTopics\(\)\s*\{([\s\S]*?)\n\}\n\nasync function",
        contenido,
    )
    assert m is not None, "No se encontró loadMacroFsrsTopics en app.js"
    cuerpo = m.group(1)

    assert "${t.ruta_titulo || 'Ruta'}" not in cuerpo, (
        "t.ruta_titulo se interpola sin escapeHtml en loadMacroFsrsTopics (hallazgo R13)"
    )
    assert "${t.tema_titulo || `Tema #${t.tema_id}`}" not in cuerpo, (
        "t.tema_titulo se interpola sin escapeHtml en loadMacroFsrsTopics (hallazgo R13)"
    )

    # Ruta y tema se escapan: con escapeHtml, o pasando por Au.insignia, que escapa todo texto (072)
    assert "escapeHtml(t.ruta_titulo" in cuerpo or "Au.insignia({ texto: t.ruta_titulo" in cuerpo
    assert "escapeHtml(t.tema_titulo" in cuerpo


# ==============================================================================
# R14: Ningún onclick con texto guardado / escapeHtml en strings JS
# ==============================================================================


def test_r14_ningun_onclick_con_escapehtml_en_string_literal() -> None:
    """R14: Ningún handler onclick en app.js debe llevar '${escapeHtml(...)}' dentro de comillas simples."""
    contenido = js_del_front().replace("\r\n", "\n")

    # Patrón del hallazgo: onclick="... '${escapeHtml(...)}' ..."
    hallazgos = re.findall(
        r'onclick="[^"]*\'\s*\$\{\s*escapeHtml\([^)]+\)\s*\}\s*\'[^"]*"',
        contenido,
    )
    assert not hallazgos, (
        "Se encontraron handlers onclick con escapeHtml en literales de string JS:\n"
        + "\n".join(hallazgos)
    )


def test_r14_handlers_con_nombres_guardados_usan_data_atributos() -> None:
    """R14: Las acciones de borrado y apertura de ruta local no deben llevar strings en onclick."""
    contenido = js_del_front().replace("\r\n", "\n")

    # Verificar que no existen llamadas inline con parámetros de texto guardado
    assert "deletePlatform(${Number(p.id)}," not in contenido, (
        "deletePlatform todavía recibe p.nombre en atributo onclick (hallazgo R14)"
    )
    assert "openCourseLocalFolder(${Number(c.id)}," not in contenido, (
        "openCourseLocalFolder todavía recibe c.ruta_local en atributo onclick (hallazgo R14)"
    )
    assert "deleteCourse(${Number(c.id)}," not in contenido, (
        "deleteCourse todavía recibe c.nombre_curso en atributo onclick (hallazgo R14)"
    )
    assert "openBookActiveRecallModal(${Number(b.id)}," not in contenido, (
        "openBookActiveRecallModal todavía recibe b.titulo en atributo onclick (hallazgo R14)"
    )
    assert "openBookHarvestModal(${Number(b.id)}," not in contenido, (
        "openBookHarvestModal todavía recibe b.titulo en atributo onclick (hallazgo R14)"
    )
    assert "deleteBook(${Number(b.id)}," not in contenido, (
        "deleteBook todavía recibe b.titulo en atributo onclick (hallazgo R14)"
    )
    assert "deleteRoadmap(${r.id}," not in contenido, (
        "deleteRoadmap todavía recibe r.titulo en atributo onclick (hallazgo R14)"
    )


# ==============================================================================
# R15: formatObsidianUri codifica para atributo y servidor rechaza caracteres peligrosos
# ==============================================================================


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js no está instalado")
def test_r15_format_obsidian_uri_codifica_para_atributo_html(tmp_path) -> None:
    """R15: formatObsidianUri debe escapar comillas en URI obsidian:// para prevenir inyección de atributos."""
    node_bin = shutil.which("node")
    assert node_bin is not None

    archivo_js = tmp_path / "front.js"
    archivo_js.write_text(js_del_front().replace("\r\n", "\n"), encoding="utf-8")
    script = f"""
    const fs = require('fs');
    const code = fs.readFileSync({json.dumps(archivo_js.as_posix())}, 'utf8');
    // Extraer escapeHtml y formatObsidianUri
    const fnEscape = code.match(/function escapeHtml\\([\\s\\S]*?\\n\\}}/)[0];
    const fnObsidian = code.match(/function formatObsidianUri\\([\\s\\S]*?\\n\\}}/)[0];
    eval(fnEscape);
    eval(fnObsidian);

    const payload = 'obsidian://open?vault=mi-vault" onmouseover="alert(1)';
    const res = formatObsidianUri(payload);
    if (res.includes('"')) {{
        console.error("formatObsidianUri no escapó las comillas:", res);
        process.exit(1);
    }}
    if (!res.includes('&quot;')) {{
        console.error("formatObsidianUri no contiene &quot;:", res);
        process.exit(2);
    }}
    process.exit(0);
    """
    proc = subprocess.run([node_bin, "-e", script], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"formatObsidianUri falla validación: {proc.stderr or proc.stdout}"


@pytest.mark.parametrize("payload", [
    'obsidian://open?vault=v" onmouseover="alert(1)',
    "obsidian://open?vault=v' onmouseover='alert(1)",
    "obsidian://open?<script>",
    "obsidian://open?>",
    "obsidian://open?\x00bad",
    "obsidian://open?\x1fbad",
    "obsidian://open?\x7fbad",
    "obsidian://open?\nbad",
    "obsidian://open?\rbad",
])
def test_r15_curso_create_rechaza_ruta_obsidian_invalida(payload: str) -> None:
    """R15: CursoCreate DEBE rechazar ruta_obsidian con comillas, '<', '>' o caracteres de control."""
    with pytest.raises(ValidationError):
        CursoCreate(
            plataforma_id=1,
            nombre_curso="Curso Test",
            url_aula="https://example.com/aula",
            ruta_obsidian=payload,
        )


@pytest.mark.parametrize("payload", [
    '/local/path" onmouseover="alert(1)',
    "/local/path' onmouseover='alert(1)",
    "/local/path/<script>",
    "/local/path/>",
    "/local/path/\x00bad",
    "/local/path/\x1fbad",
    "/local/path/\x7fbad",
    "/local/path/\nbad",
    "/local/path/\rbad",
])
def test_r15_curso_create_rechaza_ruta_local_invalida(payload: str) -> None:
    """R15: CursoCreate DEBE rechazar ruta_local con comillas, '<', '>' o caracteres de control."""
    with pytest.raises(ValidationError):
        CursoCreate(
            plataforma_id=1,
            nombre_curso="Curso Test",
            url_aula="https://example.com/aula",
            ruta_local=payload,
        )


@pytest.mark.parametrize("payload", [
    'obsidian://open?vault=v" onmouseover="alert(1)',
    "/local/path/<script>",
    "/local/path/\x00bad",
])
def test_r15_curso_update_rechaza_rutas_invalidas(payload: str) -> None:
    """R15: CursoUpdate DEBE rechazar ruta_obsidian y ruta_local inválidas."""
    with pytest.raises(ValidationError):
        CursoUpdate(ruta_obsidian=payload)

    with pytest.raises(ValidationError):
        CursoUpdate(ruta_local=payload)


def test_r15_curso_acepta_rutas_seguras() -> None:
    """R15: Rutas normales sin comillas, ángulos ni controles son aceptadas."""
    c = CursoCreate(
        plataforma_id=1,
        nombre_curso="Curso Test",
        url_aula="https://example.com/aula",
        ruta_obsidian="obsidian://open?vault=estudios&file=tema1",
        ruta_local="C:/Users/test/dev/aulento",
    )
    assert c.ruta_obsidian == "obsidian://open?vault=estudios&file=tema1"
    assert c.ruta_local == "C:/Users/test/dev/aulento"

    u = CursoUpdate(
        ruta_obsidian="obsidian://open?vault=estudios&file=tema2",
        ruta_local="/home/user/code/python",
    )
    assert u.ruta_obsidian == "obsidian://open?vault=estudios&file=tema2"
    assert u.ruta_local == "/home/user/code/python"
