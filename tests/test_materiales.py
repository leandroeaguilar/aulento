"""Almacén de materiales subidos desde la PC y migración 7 (048, T1: R1 a R7 y la limpieza de R12)."""

import sqlite3

import pytest
from materiales_de_prueba import (
    pdf_con_lineas,
    pdf_de_varias_paginas,
    pdf_sin_texto,
    texto_largo,
)

from aulento.config import get_data_dir
from aulento.core import materiales as modulo
from aulento.core.materiales import (
    CUOTA_POR_CUENTA,
    MAX_BYTES_POR_ARCHIVO,
    AlmacenDeMateriales,
    MaterialDemasiadoGrande,
    MaterialIlegible,
    MaterialNoEncontrado,
    MaterialRepetido,
    TipoNoAdmitido,
    palabras_clave,
)
from aulento.db import migrations
from aulento.db.connection import get_connection
from aulento.db.migrations import MIGRACIONES, migrar, version_actual

# El tope que tenía el tutor con Drive: un material leído entero tiene que pasarlo
TOPE_ANTERIOR = 15_000
PASAJE_DEL_FINAL = "Pasaje final sobre zookeeper y la eleccion de lider."


@pytest.fixture
def almacen(cuenta) -> AlmacenDeMateriales:
    return AlmacenDeMateriales.con_conexion_propia(cuenta)


@pytest.fixture
def ajeno(otra_cuenta) -> AlmacenDeMateriales:
    return AlmacenDeMateriales.con_conexion_propia(otra_cuenta)


def _archivos(almacen: AlmacenDeMateriales) -> list[str]:
    return sorted(p.name for p in almacen.carpeta().iterdir())


def _todo_lo_guardado() -> list[str]:
    """Todos los archivos del directorio de datos de todas las cuentas, fuera de la base."""
    raiz = get_data_dir() / "usuarios"
    if not raiz.exists():
        return []
    return sorted(p.relative_to(raiz).as_posix() for p in raiz.rglob("*") if p.is_file())


def _pdf_largo() -> bytes:
    lineas = texto_largo(TOPE_ANTERIOR * 2).split("\n")
    mitad = len(lineas) // 2
    return pdf_de_varias_paginas(lineas[:mitad], [*lineas[mitad:], PASAJE_DEL_FINAL])


# --- R1: se guarda con su texto completo ---


def test_r1_un_pdf_se_guarda_con_su_texto_completo(almacen):
    datos = _pdf_largo()

    material = almacen.guardar("Apunte largo.pdf", datos)

    assert material["nombre"] == "Apunte largo.pdf"
    assert (material["extension"], material["tipo_mime"], material["bytes"]) == (".pdf", "application/pdf", len(datos))
    assert material["caracteres"] > TOPE_ANTERIOR and material["creado_en"]
    texto = almacen.obtener(material["id"])["texto"]
    assert len(texto) == material["caracteres"]
    assert "zookeeper" in texto[TOPE_ANTERIOR:]
    [guardado] = _archivos(almacen)
    assert guardado.endswith(".pdf") and (almacen.carpeta() / guardado).read_bytes() == datos


@pytest.mark.parametrize("nombre", ["notas.md", "notas.markdown", "notas.TXT"])
def test_r1_un_texto_se_guarda_entero_con_su_tipo(almacen, nombre):
    contenido = texto_largo(TOPE_ANTERIOR * 3, al_final=PASAJE_DEL_FINAL)

    material = almacen.guardar(nombre, ("\ufeff" + contenido).encode("utf-8"))

    assert material["caracteres"] == len(contenido) > TOPE_ANTERIOR * 3
    assert almacen.obtener(material["id"])["texto"] == contenido
    assert material["tipo_mime"] == ("text/plain" if nombre.endswith("TXT") else "text/markdown")


def test_r1_un_texto_que_no_es_utf8_se_lee_como_latin1(almacen):
    material = almacen.guardar("viejo.txt", "Introducción a la programación".encode("latin-1"))

    assert almacen.obtener(material["id"])["texto"] == "Introducción a la programación"


# --- R2: topes por archivo y por cuenta, sin dejar nada guardado ---


def test_r2_un_archivo_de_mas_de_25_mb_se_rechaza_sin_guardar_nada(almacen):
    with pytest.raises(MaterialDemasiadoGrande) as rechazo:
        almacen.guardar("enorme.txt", b"a" * (MAX_BYTES_POR_ARCHIVO + 1))

    assert rechazo.value.codigo == 413
    assert "25 MB" in str(rechazo.value) and "200 MB libres" in str(rechazo.value)
    assert _todo_lo_guardado() == [] and almacen.listar() == []


def test_r2_un_archivo_de_25_mb_justos_entra(almacen, monkeypatch):
    # Sin extraer 25 MB de texto: lo que se prueba es el borde del tope
    monkeypatch.setattr(modulo, "extraer_texto", lambda extension, datos: "texto")

    material = almacen.guardar("justo.txt", b"a" * MAX_BYTES_POR_ARCHIVO)

    assert material["bytes"] == MAX_BYTES_POR_ARCHIVO


def test_r2_lo_que_pasa_la_cuota_de_la_cuenta_se_rechaza_y_dice_cuanto_queda(almacen, monkeypatch):
    monkeypatch.setattr(modulo, "CUOTA_POR_CUENTA", 3 * 1024 * 1024)
    primero = almacen.guardar("uno.txt", b"x" * (2 * 1024 * 1024))
    antes = _todo_lo_guardado()

    with pytest.raises(MaterialDemasiadoGrande) as rechazo:
        almacen.guardar("dos.txt", b"y" * (1024 * 1024 + 1))

    assert rechazo.value.codigo == 413
    assert "3 MB" in str(rechazo.value) and "quedan 1 MB libres" in str(rechazo.value)
    assert _todo_lo_guardado() == antes
    assert [m["id"] for m in almacen.listar()] == [primero["id"]]
    assert almacen.uso() == {"usado": 2 * 1024 * 1024, "tope": 3 * 1024 * 1024, "libre": 1024 * 1024}


def test_r2_la_cuota_se_vuelve_a_comprobar_al_registrar_y_el_archivo_no_queda(almacen, monkeypatch):
    """Dos subidas a la vez pasan la primera comprobación: la sentencia que registra frena a la que no entra."""
    monkeypatch.setattr(modulo, "CUOTA_POR_CUENTA", 1000)
    almacen.guardar("uno.txt", b"x" * 600)
    monkeypatch.setattr(AlmacenDeMateriales, "limite_de_subida", lambda self: MAX_BYTES_POR_ARCHIVO)

    with pytest.raises(MaterialDemasiadoGrande):
        almacen.guardar("dos.txt", b"y" * 500)

    assert len(_archivos(almacen)) == 1 and len(almacen.listar()) == 1


def test_r2_la_cuota_por_cuenta_es_de_200_mb():
    assert (CUOTA_POR_CUENTA, MAX_BYTES_POR_ARCHIVO) == (200 * 1024 * 1024, 25 * 1024 * 1024)


# --- R3: tipo, contenido y PDFs ilegibles ---


@pytest.mark.parametrize(
    ("nombre", "datos", "error"),
    [
        ("informe.docx", b"PK\x03\x04 contenido", TipoNoAdmitido),
        ("sin-extension", b"texto", TipoNoAdmitido),
        ("disfrazado.pdf", b"<html>no soy un pdf</html>", TipoNoAdmitido),
        ("imagen.txt", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", TipoNoAdmitido),
        ("escaneo.pdf", pdf_sin_texto(), MaterialIlegible),
        ("roto.pdf", b"%PDF-1.4\nesto no es un pdf de verdad", MaterialIlegible),
        ("vacio.md", b"", MaterialIlegible),
        ("espacios.md", b"   \n\n  ", MaterialIlegible),
    ],
)
def test_r3_lo_que_no_es_un_material_legible_se_rechaza_sin_guardar_nada(almacen, nombre, datos, error):
    with pytest.raises(error) as rechazo:
        almacen.guardar(nombre, datos)

    assert rechazo.value.codigo == (415 if error is TipoNoAdmitido else 422)
    assert str(rechazo.value)
    assert _todo_lo_guardado() == [] and almacen.listar() == []


# --- R4: el mismo contenido no se guarda dos veces ---


def test_r4_el_mismo_contenido_con_otro_nombre_es_repetido(almacen):
    primero = almacen.guardar("original.md", b"# Kafka\n\nParticiones y offsets.")

    with pytest.raises(MaterialRepetido) as rechazo:
        almacen.guardar("copia.md", b"# Kafka\n\nParticiones y offsets.")

    assert rechazo.value.codigo == 409
    assert rechazo.value.material == primero
    assert "original.md" in str(rechazo.value)
    assert len(_archivos(almacen)) == 1 and len(almacen.listar()) == 1


# --- R5: el nombre del navegador no es una ruta ---


@pytest.mark.parametrize("nombre", ["../../x.pdf", "..\\..\\x.pdf", "/etc/x.pdf", "C:\\Windows\\x.pdf"])
def test_r5_el_nombre_que_manda_el_navegador_no_sale_de_la_carpeta_de_materiales(almacen, nombre):
    material = almacen.guardar(nombre, pdf_con_lineas(["Contenido del material"]))

    assert material["nombre"] == "x.pdf"
    [generado] = _archivos(almacen)
    assert _todo_lo_guardado() == [f"{almacen.user_id}/materiales/{generado}"]
    assert generado != "x.pdf" and len(generado) == 32 + len(".pdf") and generado.endswith(".pdf")


# --- R6: listar, leer y borrar ---


def test_r6_listar_trae_los_materiales_sin_el_texto_y_el_uso(almacen):
    viejo = almacen.guardar("viejo.md", b"# Uno")
    nuevo = almacen.guardar("nuevo.txt", b"Dos")

    lista = almacen.listar()

    assert [m["id"] for m in lista] == [nuevo["id"], viejo["id"]]
    assert all("texto" not in m for m in lista)
    assert almacen.uso() == {"usado": 8, "tope": CUOTA_POR_CUENTA, "libre": CUOTA_POR_CUENTA - 8}


def test_r6_borrar_quita_el_archivo_y_el_texto_y_libera_el_espacio(almacen):
    queda = almacen.guardar("queda.md", b"# Se queda")
    sale = almacen.guardar("sale.md", b"# Se va con su archivo")
    antes = almacen.uso()["usado"]

    almacen.borrar(sale["id"])

    assert almacen.uso()["usado"] == antes - sale["bytes"]
    assert [m["id"] for m in almacen.listar()] == [queda["id"]]
    assert len(_archivos(almacen)) == 1
    with pytest.raises(MaterialNoEncontrado):
        almacen.obtener(sale["id"])
    with pytest.raises(MaterialNoEncontrado):
        almacen.borrar(sale["id"])


# --- R7: cada cuenta, lo suyo ---


def test_r7_una_cuenta_no_ve_lee_busca_ni_borra_los_materiales_de_otra(almacen, ajeno):
    propio = almacen.guardar("kafka.md", b"# Kafka\n\nParticiones replicadas.")

    assert ajeno.listar() == [] and ajeno.uso()["usado"] == 0
    assert ajeno.buscar("particiones replicadas") == []
    for operacion in (ajeno.obtener, ajeno.borrar, lambda i: ajeno.fragmentos_relevantes(i, "kafka", 100)):
        with pytest.raises(MaterialNoEncontrado) as rechazo:
            operacion(propio["id"])
        assert rechazo.value.codigo == 404
    assert [m["id"] for m in almacen.listar()] == [propio["id"]]
    assert len(_archivos(almacen)) == 1


def test_r7_el_mismo_archivo_en_dos_cuentas_son_dos_materiales(almacen, ajeno):
    datos = b"# Mismo apunte"

    uno, otro = almacen.guardar("a.md", datos), ajeno.guardar("a.md", datos)

    assert uno["id"] != otro["id"]
    assert almacen.carpeta() != ajeno.carpeta()
    almacen.borrar(uno["id"])
    assert [m["id"] for m in ajeno.listar()] == [otro["id"]]


# --- Búsqueda por palabras clave y fragmentos (base de R9) ---


def test_buscar_ordena_por_coincidencias_y_no_trae_lo_que_no_coincide(almacen):
    poco = almacen.guardar("poco.md", b"Kubernetes aparece una vez.")
    mucho = almacen.guardar("mucho.md", b"Kubernetes, kubernetes y KUBERNETES por todos lados.")
    almacen.guardar("nada.md", b"Solo hablo de cocina.")

    encontrados = almacen.buscar("explicame kubernetes")

    assert [m["id"] for m in encontrados] == [mucho["id"], poco["id"]]
    assert all("texto" not in m for m in encontrados)
    assert almacen.buscar("de la") == []


def test_fragmentos_relevantes_toma_el_pasaje_del_medio_del_documento(almacen):
    principio = texto_largo(30_000)
    contenido = f"{principio}\nEl algoritmo Raft elige un lider por votacion.\n{texto_largo(30_000)}"
    material = almacen.guardar("consenso.md", contenido.encode("utf-8"))

    fragmento = almacen.fragmentos_relevantes(material["id"], "¿Cómo funciona Raft?", 2_000)

    assert "El algoritmo Raft elige un lider por votacion." in fragmento
    assert len(fragmento) <= 2_000
    assert not contenido.startswith(fragmento[:200])


def test_fragmentos_relevantes_junta_pasajes_de_varias_partes_sin_pasar_el_tope(almacen):
    relleno = texto_largo(10_000)
    contenido = f"raft al principio\n{relleno}\nraft en el medio\n{relleno}\nraft al final"
    material = almacen.guardar("raft.md", contenido.encode("utf-8"))

    fragmento = almacen.fragmentos_relevantes(material["id"], "raft", 3_000)

    assert "raft al principio" in fragmento and "raft en el medio" in fragmento and "raft al final" in fragmento
    assert len(fragmento) <= 3_000
    assert fragmento.count(modulo.SEPARADOR_DE_FRAGMENTOS) == 2


def test_fragmentos_relevantes_sin_coincidencias_devuelve_el_principio(almacen):
    contenido = texto_largo(5_000)
    material = almacen.guardar("relleno.md", contenido.encode("utf-8"))

    assert almacen.fragmentos_relevantes(material["id"], "zanahoria", 300) == contenido[:300]


def test_palabras_clave_se_movio_al_almacen_y_el_tutor_la_usa():
    import inspect

    from aulento.mcp import agent

    assert palabras_clave("¿Qué temas tengo sobre machine learning?") == ["learning", "machine"]
    # El tutor busca con el almacén, que usa esta función: ya no tiene una propia
    assert "def palabras_clave" not in inspect.getsource(agent)
    assert "self.materiales.buscar(" in inspect.getsource(agent.TutorDeMateriales)


# --- Migración 7: tabla de materiales y limpieza de Drive y OneDrive ---


def _secretos_y_ajustes(conn: sqlite3.Connection) -> tuple[set, set]:
    secretos = {tuple(f) for f in conn.execute("SELECT user_id, nombre FROM secretos_usuario;").fetchall()}
    ajustes = {tuple(f) for f in conn.execute("SELECT user_id, clave FROM ajustes_usuario;").fetchall()}
    return secretos, ajustes


def test_la_migracion_7_crea_materiales_y_borra_drive_y_onedrive_salvo_el_cliente_de_google(tmp_path):
    conn = get_connection(tmp_path / "v6.db")
    for numero, nombre, funcion, *opciones in MIGRACIONES[:6]:
        migrations._aplicar(conn, numero, nombre, funcion, sin_claves_foraneas=bool(opciones and opciones[0]))
    assert version_actual(conn) == 6
    cuentas = []
    for nombre in ("ana", "beto"):
        cursor = conn.execute(
            "INSERT INTO usuarios (nombre_usuario, contrasena_hash, rol, activo, creado_en) "
            "VALUES (?, 'x', 'usuario', 1, '2026-01-01');",
            (nombre,),
        )
        cuentas.append(cursor.lastrowid)
    for cuenta in cuentas:
        for secreto in ("gdrive_cliente", "gdrive_autorizacion", "onedrive_cliente", "onedrive_autorizacion", "gemini_clave_paga"):
            conn.execute(
                "INSERT INTO secretos_usuario (user_id, nombre, valor_cifrado, actualizado_en) VALUES (?, ?, X'00', '2026');",
                (cuenta, secreto),
            )
        for ajuste in (
            "conectores",
            "gdrive_carpeta_raiz",
            "gdrive_autorizacion_rechazada",
            "onedrive_carpeta_raiz",
            "onedrive_autorizacion_rechazada",
            "gemini_modelo",
        ):
            conn.execute(
                "INSERT INTO ajustes_usuario (user_id, clave, valor, actualizado_en) VALUES (?, ?, '1', '2026');",
                (cuenta, ajuste),
            )
    conn.commit()

    assert migrar(conn) == len(MIGRACIONES)

    secretos, ajustes = _secretos_y_ajustes(conn)
    assert secretos == {(c, n) for c in cuentas for n in ("gdrive_cliente", "gemini_clave_paga")}
    assert ajustes == {(c, "gemini_modelo") for c in cuentas}
    columnas = {fila[1] for fila in conn.execute("PRAGMA table_info(materiales);").fetchall()}
    assert columnas == {
        "id", "user_id", "nombre", "extension", "tipo_mime", "bytes", "sha256", "archivo", "texto", "caracteres", "creado_en"
    }
    indices = {fila[1] for fila in conn.execute("PRAGMA index_list(materiales);").fetchall()}
    assert "idx_materiales_user" in indices
    conn.close()


def test_los_materiales_se_van_con_la_cuenta(tmp_path):
    conn = get_connection(tmp_path / "base.db")
    migrar(conn)
    cuenta = conn.execute(
        "INSERT INTO usuarios (nombre_usuario, contrasena_hash, rol, activo, creado_en) VALUES ('c', 'x', 'usuario', 1, '2026');"
    ).lastrowid
    conn.execute(
        "INSERT INTO materiales (user_id, nombre, extension, tipo_mime, bytes, sha256, archivo, texto, caracteres, creado_en) "
        "VALUES (?, 'a.md', '.md', 'text/markdown', 1, 'h', 'f.md', 't', 1, '2026');",
        (cuenta,),
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO materiales (user_id, nombre, extension, tipo_mime, bytes, sha256, archivo, texto, caracteres, creado_en) "
            "VALUES (?, 'b.md', '.md', 'text/markdown', 1, 'h', 'g.md', 't', 1, '2026');",
            (cuenta,),
        )

    conn.execute("DELETE FROM usuarios WHERE id = ?;", (cuenta,))
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM materiales;").fetchone()[0] == 0
    conn.close()
