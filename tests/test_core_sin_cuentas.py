"""El core es de una sola persona: no trae contraseñas, sesiones, invitaciones, administración ni demo (051, R2, R6)."""

import re
from pathlib import Path

from typer.main import get_command

from aulento.cli.app import cli
from tests.front import archivos_del_front, js_del_front

SRC_DEL_CORE = Path(__file__).resolve().parent.parent / "src" / "aulento"

MODULOS_MUDADOS = ("auth/contrasenas.py", "auth/demo.py", "web/routes/auth.py", "web/routes/admin.py")

# Lo que solo existe con cuentas multiusuario. Las tablas viejas siguen en las migraciones hasta la T5.
SENALES_DE_CUENTAS = re.compile(
    r"hashlib\.scrypt|se_sesion|CloudIdentityProvider|/api/auth/(login|register|demo|reset)|/api/admin/"
    r"|NOMBRE_USUARIO_DEMO|nombre_usuario\s*==\s*['\"]demo['\"]"
    r"|aulento user (create|invite|reset-password|activate|deactivate)"
    r"|def (ingresar|registrar|crear_invitacion|crear_sesion|cerrar_sesion)\b"
)
EXCEPTUADOS = {"db/migrations.py"}


def test_r2_los_modulos_de_cuentas_ya_no_estan_en_el_core():
    presentes = [ruta for ruta in MODULOS_MUDADOS if (SRC_DEL_CORE / ruta).exists()]
    assert not presentes, f"Se mudaron a las cuentas de la nube (051): {presentes}"


def test_r2_ningun_modulo_del_core_define_contrasenas_sesiones_invitaciones_ni_demo():
    hallazgos = []
    for archivo in sorted(SRC_DEL_CORE.rglob("*.py")):
        relativa = archivo.relative_to(SRC_DEL_CORE).as_posix()
        if relativa in EXCEPTUADOS:
            continue
        for numero, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), start=1):
            if SENALES_DE_CUENTAS.search(linea):
                hallazgos.append(f"{relativa}:{numero}: {linea.strip()}")
    assert not hallazgos, "Lo multiusuario vive en la nube (051):\n" + "\n".join(hallazgos)


def test_r6_la_cli_del_core_no_administra_cuentas():
    comandos_de_user = set(get_command(cli).commands["user"].commands)
    assert comandos_de_user == {"list", "import-files"}


# --- La página del core (051, R4) ---

ESTATICOS_DEL_CORE = SRC_DEL_CORE / "web" / "static"
SENALES_DE_CUENTAS_EN_LA_PAGINA = (
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/password",
    "/api/auth/demo",
    "/api/admin/",
    'id="tab-admin"',
    'id="change-password-modal"',
    'id="btn-logout"',
    "nombre_usuario === 'demo'",
)


def test_r4_la_pagina_del_core_no_tiene_ingreso_ni_administracion():
    assert not (ESTATICOS_DEL_CORE / "login.html").exists()
    assert not (ESTATICOS_DEL_CORE / "login.js").exists()
    archivos = [ESTATICOS_DEL_CORE / "index.html", ESTATICOS_DEL_CORE / "mcp-remoto.js", *archivos_del_front()]
    for arch in archivos:
        texto = arch.read_text(encoding="utf-8")
        presentes = [senal for senal in SENALES_DE_CUENTAS_EN_LA_PAGINA if senal in texto]
        assert not presentes, f"{arch.name}: {presentes}"


def test_r4_la_pagina_deja_ranuras_para_el_menu_de_cuenta_y_avisa_la_cuenta_leida():
    html = (ESTATICOS_DEL_CORE / "index.html").read_text(encoding="utf-8")
    js = js_del_front()
    assert 'id="menu-cuenta-ranura-arriba"' in html and 'id="menu-cuenta-ranura-abajo"' in html
    assert "'aulento:cuenta'" in js and "'aulento:pestana'" in js


# --- La base del core (051, R5) ---


def test_r5_una_base_nueva_del_core_no_crea_las_tablas_de_las_cuentas_multiusuario(tmp_path):
    from aulento.db.connection import get_connection
    from aulento.db.migrations import migrar

    conn = get_connection(str(tmp_path / "nueva.db"))
    try:
        migrar(conn)
        tablas = {fila[0] for fila in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table';")}
    finally:
        conn.close()
    assert "usuarios" in tablas
    assert not tablas & {"sesiones", "invitaciones", "intentos_login", "demo_siembra"}


def test_r3_el_aviso_de_cuenta_compartida_reconoce_el_mensaje_del_servidor():
    """El recuadro de un formulario se pinta como aviso, no como error, cuando el 403 es por la cuenta compartida."""
    import re as expresiones

    from aulento.web.dependencies import MENSAJE_CUENTA_COMPARTIDA

    js = js_del_front()
    patron = expresiones.search(r"const esDeLaDemo = /([^/]+)/i\.test", js)
    assert patron, "pintarErrorEnFeedback dejó de reconocer el rechazo por la cuenta compartida"
    assert expresiones.search(patron.group(1), MENSAJE_CUENTA_COMPARTIDA, flags=expresiones.IGNORECASE)


def test_r3_ningun_texto_de_la_pagina_del_core_nombra_a_la_demo():
    """Los avisos hablan de una cuenta compartida: cuál es (la demo de la nube u otra) lo decide una extensión."""
    import re as expresiones

    demo = expresiones.compile(r"est[aá]s en la demo|la demo es compartida|\ben la demo\b|cuenta demo", expresiones.IGNORECASE)
    hallazgos = []
    for archivo in sorted(ESTATICOS_DEL_CORE.glob("*")):
        if archivo.suffix not in {".js", ".html"}:
            continue
        for numero, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), start=1):
            if demo.search(linea) and not linea.strip().startswith("//"):
                hallazgos.append(f"{archivo.name}:{numero}: {linea.strip()[:120]}")
    assert not hallazgos, "\n".join(hallazgos)
