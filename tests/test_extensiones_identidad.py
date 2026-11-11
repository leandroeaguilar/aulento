"""Enganches de la 051 en el core: identidad de una extensión, cuenta compartida, «antes de la IA» y la cuenta local."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from aulento.auth import servicio
from aulento.auth.modelos import ROL_USUARIO, Usuario
from aulento.core.eventos import IA_ANTES, bus
from aulento.core.extensiones import Extension, ExtensionInvalida
from aulento.core.ia.pasarela import PasarelaDeIA, Pedido
from aulento.core.identity import IIdentityProvider, LocalIdentityProvider
from aulento.db.connection import get_connection
from aulento.db.schema import init_db
from aulento.web.app import create_app

pytestmark = pytest.mark.sin_sesion


class _SiempreLaMisma(IIdentityProvider):
    """Proveedor de prueba: todo pedido es de la cuenta que se le dio."""

    def __init__(self, usuario: Usuario) -> None:
        self.usuario = usuario

    @property
    def modo(self) -> str:
        return "saas"

    def get_usuario(self) -> Usuario:
        return self.usuario

    def get_usuario_opcional(self) -> Usuario | None:
        return self.usuario

    def es_admin(self) -> bool:
        return self.usuario.es_admin

    def es_autenticado(self) -> bool:
        return True


def _cuenta(nombre: str) -> Usuario:
    conn = get_connection()
    try:
        init_db(conn)
        conn.execute(
            "INSERT INTO usuarios (nombre_usuario, contrasena_hash, rol, activo, creado_en) VALUES (?, 'x', ?, 1, 'hoy');",
            (nombre, ROL_USUARIO),
        )
        conn.commit()
        fila = conn.execute("SELECT id FROM usuarios WHERE nombre_usuario = ?;", (nombre,)).fetchone()
        return Usuario(id=fila[0], nombre_usuario=nombre, rol=ROL_USUARIO, activo=True)
    finally:
        conn.close()


# ---------------------------------------------------------------- R1: identidad de una extensión


def test_r1_en_saas_la_identidad_sale_de_la_extension():
    carla = _cuenta("carla")
    app = create_app(extensiones=[Extension(nombre="identidad_de_prueba", identidad=lambda r, c: _SiempreLaMisma(carla))])

    yo = TestClient(app).get("/api/auth/me")

    assert yo.status_code == 200, yo.text
    assert yo.json()["nombre_usuario"] == "carla"


def test_r1_dos_extensiones_no_pueden_aportar_la_identidad():
    def fabrica(request, conn):
        raise AssertionError("no se llama")

    with pytest.raises(ExtensionInvalida, match="Solo una extensión"):
        create_app(
            extensiones=[
                Extension(nombre="una", identidad=fabrica),
                Extension(nombre="otra", identidad=fabrica),
            ]
        )


def test_r1_en_local_manda_la_cuenta_local_aunque_una_extension_aporte_identidad(monkeypatch):
    monkeypatch.setenv("AULENTO_MODE", "local")
    _cuenta("la-primera")
    carla = _cuenta("carla")
    app = create_app(extensiones=[Extension(nombre="identidad_de_prueba", identidad=lambda r, c: _SiempreLaMisma(carla))])

    yo = TestClient(app).get("/api/auth/me").json()

    assert yo["id"] == servicio.ID_DE_LA_CUENTA_LOCAL and yo["nombre_usuario"] != "carla"


# ---------------------------------------------------------------- R3: cuenta compartida


def test_r3_la_cuenta_compartida_no_guarda_claves_y_la_comun_si(monkeypatch):
    monkeypatch.setenv("AULENTO_MODE", "saas")
    compartida, propia = _cuenta("compartida"), _cuenta("propia")
    quien = {"cuenta": compartida}
    app = create_app(
        extensiones=[
            Extension(
                nombre="identidad_de_prueba",
                identidad=lambda r, c: _SiempreLaMisma(quien["cuenta"]),
                cuenta_compartida=lambda u: u.nombre_usuario == "compartida",
            )
        ]
    )
    cliente = TestClient(app)

    frenada = cliente.post("/api/mcp/tokens", json={"nombre": "x"})
    quien["cuenta"] = propia
    permitida = cliente.post("/api/mcp/tokens", json={"nombre": "x"})

    assert frenada.status_code == 403
    assert frenada.headers["X-Cuenta-Compartida"] == "1"
    assert "demo" not in frenada.json()["detail"].lower()
    assert permitida.status_code == 201


def test_r3_sin_extension_que_la_declare_ninguna_cuenta_es_compartida(monkeypatch):
    """El core no conoce a la demo por su nombre: sin extensión, una cuenta llamada «demo» es una más."""
    monkeypatch.setenv("AULENTO_MODE", "local")
    conn = get_connection()
    try:
        init_db(conn)
        conn.execute("UPDATE usuarios SET nombre_usuario = 'demo' WHERE id = 1;")
        conn.commit()
    finally:
        conn.close()

    assert TestClient(create_app()).post("/api/mcp/tokens", json={"nombre": "x"}).status_code == 201


def test_r3_el_core_no_nombra_a_la_cuenta_demo_para_frenar():
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1] / "src" / "aulento"
    for archivo in (raiz / "web" / "dependencies.py", raiz / "roadmap" / "lesson_studio.py"):
        texto = archivo.read_text(encoding="utf-8")
        assert "NOMBRE_USUARIO_DEMO" not in texto and "es_demo" not in texto, archivo


# ---------------------------------------------------------------- R10: antes de la IA


def test_r10_un_suscriptor_de_ia_antes_que_rechaza_evita_la_llamada():
    cuenta = _cuenta("ana")

    def sin_saldo(**datos):
        assert datos["user_id"] == cuenta.id and datos["endpoint_tipo"] == "prueba"
        raise HTTPException(status_code=402, detail="Sin saldo.")

    bus.suscribir(IA_ANTES, sin_saldo)
    try:
        with (
            patch.object(PasarelaDeIA, "_generar_con_gemini") as gemini,
            patch.object(PasarelaDeIA, "_generar_con") as otro,
            pytest.raises(HTTPException) as error,
        ):
            PasarelaDeIA.con_conexion_propia(cuenta.id).generar(Pedido(sistema="s", usuario="u"), "prueba")
    finally:
        bus.desuscribir(IA_ANTES, sin_saldo)

    assert error.value.status_code == 402
    gemini.assert_not_called()
    otro.assert_not_called()


def test_r10_sin_suscriptores_la_verificacion_no_hace_nada():
    bus.verificar("evento.sin.suscriptores", dato=1)


# ---------------------------------------------------------------- R7: cuenta local


def test_r7_la_cuenta_local_hereda_los_datos_sin_dueno_y_anula_el_codigo_inicial(monkeypatch):
    monkeypatch.setenv("AULENTO_MODE", "local")
    conn = get_connection()
    try:
        init_db(conn)
        conn.execute("DELETE FROM usuarios;")
        conn.execute("INSERT INTO libros_lectura (titulo, total_capitulos) VALUES ('Libro sin dueño', 10);")
        conn.commit()
        # El código inicial pendiente que habría dejado la nube antes de pasar a local: la tabla es de la nube (051)
        conn.execute(
            "CREATE TABLE invitaciones (id INTEGER PRIMARY KEY, codigo_hash TEXT, tipo TEXT, rol TEXT, usuario_id INTEGER, "
            "creado_por INTEGER, creada_en TEXT, expira_en TEXT, usada_en TEXT, inicial INTEGER NOT NULL DEFAULT 0);"
        )
        conn.execute(
            "INSERT INTO invitaciones (codigo_hash, tipo, rol, usuario_id, creado_por, creada_en, expira_en, inicial) "
            "VALUES ('h', 'registro', 'admin', NULL, NULL, 'hoy', '2999-01-01', 1);"
        )
        conn.commit()

        usuario = LocalIdentityProvider(conn).get_usuario()

        assert usuario.id == servicio.ID_DE_LA_CUENTA_LOCAL and usuario.es_admin
        assert conn.execute("SELECT user_id FROM libros_lectura WHERE titulo = 'Libro sin dueño';").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM invitaciones WHERE inicial = 1 AND usada_en IS NULL;").fetchone()[0] == 0
        # Otra vez no hace nada nuevo
        assert LocalIdentityProvider(conn).get_usuario().id == usuario.id
    finally:
        conn.close()


def test_r3_me_dice_si_la_cuenta_es_compartida(monkeypatch):
    """La interfaz avisa lo que una cuenta compartida no guarda sin conocerla por su nombre: se lo dice `/me`."""
    monkeypatch.setenv("AULENTO_MODE", "local")
    comun = TestClient(create_app())
    compartida = TestClient(
        create_app(extensiones=[Extension(nombre="todas_compartidas", cuenta_compartida=lambda usuario: True)])
    )

    assert comun.get("/api/auth/me").json()["compartida"] is False
    assert compartida.get("/api/auth/me").json()["compartida"] is True


def test_r7_la_cuenta_local_se_crea_en_una_base_sin_las_tablas_de_la_nube(monkeypatch):
    monkeypatch.setenv("AULENTO_MODE", "local")
    conn = get_connection()
    try:
        init_db(conn)
        conn.execute("DELETE FROM usuarios;")
        conn.commit()

        usuario = LocalIdentityProvider(conn).get_usuario()

        assert usuario.id == servicio.ID_DE_LA_CUENTA_LOCAL
        assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'invitaciones';").fetchone() is None
    finally:
        conn.close()


def test_r7_la_cuenta_local_se_prepara_al_arrancar_y_no_en_el_primer_pedido(monkeypatch):
    monkeypatch.setenv("AULENTO_MODE", "local")
    conn = get_connection()
    try:
        init_db(conn)
        conn.execute("DELETE FROM usuarios;")
        conn.commit()
    finally:
        conn.close()

    with TestClient(create_app()):
        conn = get_connection()
        try:
            fila = conn.execute("SELECT nombre_usuario, rol FROM usuarios WHERE id = 1;").fetchone()
        finally:
            conn.close()

    assert tuple(fila) == (servicio.NOMBRE_DE_LA_CUENTA_LOCAL, "admin")


def test_r7_sin_la_cuenta_1_y_con_el_nombre_tomado_el_error_lo_explica(monkeypatch):
    monkeypatch.setenv("AULENTO_MODE", "local")
    conn = get_connection()
    try:
        init_db(conn)
        conn.execute("DELETE FROM usuarios;")
        conn.execute(
            "INSERT INTO usuarios (id, nombre_usuario, contrasena_hash, rol, activo, creado_en) "
            "VALUES (7, ?, 'x', 'usuario', 1, 'hoy');",
            (servicio.NOMBRE_DE_LA_CUENTA_LOCAL,),
        )
        conn.commit()

        with pytest.raises(servicio.CuentaLocalImposible, match="ya se llama"):
            servicio.crear_cuenta_local(conn)
    finally:
        conn.close()


def test_r1_en_saas_sin_una_extension_de_identidad_el_core_no_arranca(monkeypatch):
    """El core solo trae el modo local: el multiusuario necesita una extensión que aporte las cuentas (051, R1)."""
    import aulento.web.app as modulo_de_la_app
    from aulento.core.identity import SinProveedorDeIdentidad

    monkeypatch.setenv("AULENTO_MODE", "saas")

    with pytest.raises(SinProveedorDeIdentidad, match="Extension.identidad"):
        create_app()
    with pytest.raises(SinProveedorDeIdentidad):
        create_app(extensiones=[Extension(nombre="sin_identidad")])
    # La app del módulo (la que arranca `uvicorn aulento.web.app:app`) también se niega
    monkeypatch.setattr(modulo_de_la_app, "_app", None, raising=False)
    with pytest.raises(SinProveedorDeIdentidad):
        modulo_de_la_app.app  # noqa: B018


def test_r10_el_enganche_frena_tambien_los_embeddings():
    from aulento.core.ia import pasarela as modulo_de_la_pasarela

    cuenta = _cuenta("beto")
    vistos = []

    def sin_saldo(**datos):
        vistos.append(datos["endpoint_tipo"])
        raise HTTPException(status_code=402, detail="Sin saldo.")

    from contextlib import ExitStack

    bus.suscribir(IA_ANTES, sin_saldo)
    try:
        with ExitStack() as parches, pytest.raises(HTTPException) as error:
            proveedores = [
                parches.enter_context(patch.object(adaptador, "embeber"))
                for adaptador in modulo_de_la_pasarela.ADAPTADORES.values()
            ]
            PasarelaDeIA.con_conexion_propia(cuenta.id).embeber("un texto")
    finally:
        bus.desuscribir(IA_ANTES, sin_saldo)

    assert error.value.status_code == 402
    assert vistos == [modulo_de_la_pasarela.ENDPOINT_DE_EMBEDDINGS]
    for proveedor in proveedores:
        proveedor.assert_not_called()
