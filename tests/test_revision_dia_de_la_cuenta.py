"""Pruebas de la Fase 2: El día de la cuenta (revisión de arquitectura).

Cubre:
- `aulento.core.zona_horaria`:
  - Resolución de zona horaria de la cuenta desde `ajustes_usuario` o zona local de la máquina.
  - Conversión de marcas de tiempo en los dos formatos (ISO 8601 con zona y CURRENT_TIMESTAMP SQLite).
- Punto 6:
  - Actividad, mapa de calor y rachas calculados en la zona horaria de la cuenta.
  - Actividad nocturna (21 a 24 h locales) contada en el día local y manteniendo la racha.
  - Métricas de `FocusRepository` («minutos de hoy» y «la semana») en la zona de la cuenta sin volver a cero a las 21 h locales.
  - Semana calculada desde el lunes local (00:00 h).
- Punto 8:
  - «Páginas leídas» por día desde `avances_de_lectura` (un avance de 100 a 130 suma 30 páginas ese día, no 130).
  - `StreakInfo.total_pages_read` sigue sumando `pagina_actual` de los libros.
  - La racha no suma lectura.
"""

from datetime import date, datetime, timedelta, timezone
import sqlite3
from zoneinfo import ZoneInfo

import pytest

from conftest import administrador_de_prueba
from aulento.core.activity_tracker import ActivityTracker
from aulento.core.secretos import AjustesDeCuenta
from aulento.core.zona_horaria import (
    AJUSTE_ZONA_HORARIA,
    convertir_a_zona,
    fecha_local,
    fecha_local_str,
    zona_de_la_cuenta,
)
from aulento.db.connection import get_connection
from aulento.db.focus_repository import FocusRepository
from aulento.db.schema import init_db

ZONA_BSAS = ZoneInfo("America/Argentina/Buenos_Aires")


@pytest.fixture
def db_fase2(tmp_path, monkeypatch):
    """Inicializa una base de datos temporal con el esquema completo y cuenta administradora."""
    db_file = tmp_path / "test_fase2.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    conn = get_connection(db_file)
    init_db(conn)
    admin = administrador_de_prueba(conn)
    conn.close()
    return db_file, admin.id


# ----------------------------------------------------------------------
# 1. Módulo core/zona_horaria y conversión de formatos
# ----------------------------------------------------------------------


def test_zona_de_la_cuenta_lee_ajuste_o_cae_en_maquina(tmp_path):
    """La zona horaria de la cuenta se lee del ajuste `zona_horaria`; si falta o es inválida, usa la máquina."""
    db_file = tmp_path / "test_zona.db"
    conn = get_connection(db_file)
    init_db(conn)
    admin = administrador_de_prueba(conn)

    # 1. Sin ajuste configurado: retorna la zona de la máquina
    zona_defecto = zona_de_la_cuenta(conn, admin.id)
    assert zona_defecto is not None
    assert isinstance(zona_defecto, timezone) or hasattr(zona_defecto, "utcoffset")

    # 2. Con ajuste válido guardado
    ajustes = AjustesDeCuenta(conn, admin.id)
    ajustes.guardar(AJUSTE_ZONA_HORARIA, "America/Argentina/Buenos_Aires")
    zona_ajustada = zona_de_la_cuenta(conn, admin.id)
    assert zona_ajustada == ZoneInfo("America/Argentina/Buenos_Aires")

    # 3. Con ajuste inválido o que no carga: cae en la zona de la máquina sin fallar
    ajustes.guardar(AJUSTE_ZONA_HORARIA, "Zona/Inexistente_12345")
    zona_invalida = zona_de_la_cuenta(conn, admin.id)
    assert zona_invalida == zona_defecto

    conn.close()


def test_convertir_a_zona_los_dos_formatos_de_marca_de_tiempo():
    """`convertir_a_zona` maneja ISO con zona y CURRENT_TIMESTAMP de SQLite (asumido UTC)."""
    # Formato 1: ISO 8601 con zona (+00:00 o Z)
    # 02:30 UTC del 20 de noviembre en Buenos Aires (UTC-3) son las 23:30 del 19 de noviembre
    marca_iso = "2026-11-20T02:30:00.123456+00:00"
    dt_local = convertir_a_zona(marca_iso, ZONA_BSAS)
    assert dt_local.date() == date(2026, 11, 19)
    assert dt_local.hour == 23
    assert dt_local.minute == 30
    assert dt_local.microsecond == 123456

    marca_z = "2026-11-20T01:00:00Z"
    dt_z = convertir_a_zona(marca_z, ZONA_BSAS)
    assert dt_z.date() == date(2026, 11, 19)
    assert dt_z.hour == 22

    # Formato 2: CURRENT_TIMESTAMP de SQLite (sin zona, interpretado como UTC)
    marca_sqlite = "2026-11-20 01:00:00"
    dt_sqlite = convertir_a_zona(marca_sqlite, ZONA_BSAS)
    assert dt_sqlite.date() == date(2026, 11, 19)
    assert dt_sqlite.hour == 22
    assert dt_sqlite.minute == 0

    # Funciones ayudantes de fecha directa
    assert fecha_local(marca_sqlite, ZONA_BSAS) == date(2026, 11, 19)
    assert fecha_local_str(marca_sqlite, ZONA_BSAS) == "2026-11-19"


def test_schedule_importa_ajuste_zona_horaria():
    """`web.routes.schedule` importa `AJUSTE_ZONA_HORARIA` del módulo nuevo sin romper compatibilidad."""
    from aulento.web.routes.schedule import AJUSTE_ZONA_HORARIA as AJUSTE_SCHEDULE

    assert AJUSTE_SCHEDULE == "zona_horaria"


# ----------------------------------------------------------------------
# 2. Punto 6: Actividad, mapa de calor y rachas en días locales
# ----------------------------------------------------------------------


def test_actividad_nocturna_cuenta_en_dia_local(db_fase2):
    """La actividad de 21 a 24 h locales (00 a 03 h UTC del día siguiente) suma al día local."""
    db_file, user_id = db_fase2
    conn = get_connection(db_file)

    # Fijamos la zona de la cuenta en Buenos Aires (UTC-3)
    AjustesDeCuenta(conn, user_id).guardar(AJUSTE_ZONA_HORARIA, "America/Argentina/Buenos_Aires")

    dia_local = date(2026, 11, 19)

    # 1. Sesión de estudio a las 21:30 local del 19 (00:30 UTC del 20) -> 45 minutos
    conn.execute(
        "INSERT INTO sesiones_estudio (user_id, duracion_minutos, tipo, fecha_hora) VALUES (?, ?, ?, ?);",
        (user_id, 45, "pomodoro", "2026-11-20T00:30:00+00:00"),
    )
    # 2. Repaso FSRS a las 23:30 local del 19 (02:30 UTC del 20)
    conn.execute(
        "INSERT INTO fsrs_items (id, user_id, item_pregunta, respuesta_esperada) VALUES (1, ?, 'P', 'R');",
        (user_id,),
    )
    conn.execute(
        "INSERT INTO fsrs_review_logs (card_id, rating, state, review_datetime) VALUES (?, ?, ?, ?);",
        (1, 3, 2, "2026-11-20T02:30:00.000000+00:00"),
    )
    # 3. Tema completado con CURRENT_TIMESTAMP a las 22:00 local del 19 (01:00:00 UTC del 20)
    conn.execute(
        "INSERT INTO rutas_aprendizaje (id, user_id, titulo, descripcion) VALUES (1, ?, 'Python', 'Desc');",
        (user_id,),
    )
    conn.execute(
        "INSERT INTO ruta_modulos (id, ruta_id, titulo, orden) VALUES (1, 1, 'Módulo 1', 1);",
    )
    conn.execute(
        """
        INSERT INTO ruta_temas (id, modulo_id, titulo, orden, estado, fecha_actualizacion)
        VALUES (1, 1, 'Asyncio', 1, 'completado', '2026-11-20 01:00:00');
        """,
    )
    conn.commit()

    tracker = ActivityTracker(user_id, conn=conn)
    res = tracker.get_heatmap(days=5, reference_date=dia_local)

    # Verificamos que el día 2026-11-19 tenga toda la actividad nocturna
    dia_item = next(d for d in res.days if d.date == "2026-11-19")
    assert dia_item.study_minutes == 45
    assert dia_item.fsrs_reviews == 1
    assert dia_item.topics_completed == 1

    # Y que no haya caído erróneamente en el 2026-11-20
    conn.close()


def test_racha_se_mantiene_con_actividad_nocturna_y_no_suma_lectura(db_fase2):
    """Estudiar a las 23:15 locales mantiene y avanza la racha del día; los avances de lectura no suman racha."""
    db_file, user_id = db_fase2
    conn = get_connection(db_file)

    ref_date = date(2026, 11, 19)

    # Actividad de ayer: 2026-11-18 a las 15:00 UTC (12:00 local)
    conn.execute(
        "INSERT INTO sesiones_estudio (user_id, duracion_minutos, tipo, fecha_hora) VALUES (?, ?, ?, ?);",
        (user_id, 30, "pomodoro", "2026-11-18T15:00:00+00:00"),
    )
    # Actividad de hoy a las 23:15 local (02:15 UTC del día siguiente)
    conn.execute(
        "INSERT INTO sesiones_estudio (user_id, duracion_minutos, tipo, fecha_hora) VALUES (?, ?, ?, ?);",
        (user_id, 30, "pomodoro", "2026-11-20T02:15:00+00:00"),
    )
    # Avance de lectura hace 2 días (el día 17): NO debe alargar la racha (decisión 5)
    conn.execute(
        "INSERT INTO libros_lectura (id, user_id, titulo, capitulo_actual, total_capitulos, total_paginas, pagina_actual) VALUES (1, ?, 'Libro', 1, 1, 200, 50);",
        (user_id,),
    )
    conn.execute(
        "INSERT INTO avances_de_lectura (user_id, libro_id, paginas, registrado_en) VALUES (?, 1, 50, '2026-11-17T12:00:00+00:00');",
        (user_id,),
    )
    conn.commit()

    # Inyectamos directamente la zona de Buenos Aires en el constructor
    tracker = ActivityTracker(user_id, conn=conn, zona=ZONA_BSAS)
    res = tracker.get_heatmap(days=7, reference_date=ref_date)

    # La racha debe ser exactamente 2 días (hoy 19 y ayer 18), sin incluir el día 17
    assert res.streak.current_streak == 2
    assert res.streak.longest_streak == 2
    assert res.streak.total_active_days == 2

    conn.close()


# ----------------------------------------------------------------------
# 3. Punto 6: «Hoy» y «la semana» de FocusRepository en la zona local
# ----------------------------------------------------------------------


def test_focus_minutos_de_hoy_no_vuelven_a_cero_a_las_21_locales(db_fase2):
    """En Buenos Aires, las sesiones pasadas las 21 h locales suman a «hoy» y no se resetean a las 00 UTC."""
    db_file, user_id = db_fase2
    conn = get_connection(db_file)

    repo = FocusRepository(conn, user_id, zona=ZONA_BSAS)

    # Sesión 1: a las 20:30 locales del jueves 19 (23:30 UTC del 19) -> 30 min
    conn.execute(
        "INSERT INTO sesiones_estudio (user_id, duracion_minutos, tipo, fecha_hora) VALUES (?, ?, ?, ?);",
        (user_id, 30, "pomodoro", "2026-11-19T23:30:00+00:00"),
    )
    # Sesión 2: a las 22:00 locales del jueves 19 (01:00 UTC del viernes 20) -> 45 min
    conn.execute(
        "INSERT INTO sesiones_estudio (user_id, duracion_minutos, tipo, fecha_hora) VALUES (?, ?, ?, ?);",
        (user_id, 45, "curso", "2026-11-20T01:00:00+00:00"),
    )
    conn.commit()

    # Simulamos consultar a las 22:30 locales del jueves 19 (01:30 UTC del viernes 20)
    now_simulado = datetime(2026, 11, 20, 1, 30, tzinfo=timezone.utc)
    stats = repo.get_weekly_stats(now_utc=now_simulado)

    # Las dos sesiones pertenecen a «hoy» (jueves 19 local)
    assert stats["minutos_hoy"] == 75
    assert stats["horas_hoy"] == round(75 / 60.0, 1)
    assert stats["minutos_semana"] == 75
    assert stats["horas_semana"] == round(75 / 60.0, 1)
    assert stats["sesiones_semana"] == 2
    assert stats["por_tipo_minutos"]["pomodoro"] == 30
    assert stats["por_tipo_minutos"]["curso"] == 45

    conn.close()


def test_focus_semana_desde_el_lunes_local(db_fase2):
    """La semana se cuenta desde el lunes 00:00 h local: una sesión del domingo 22:00 no entra en la semana que inicia."""
    db_file, user_id = db_fase2
    conn = get_connection(db_file)

    # La semana va del lunes 16 de noviembre al domingo 22 de noviembre de 2026
    repo = FocusRepository(conn, user_id, zona=ZONA_BSAS)

    # Sesión del domingo 15 a las 22:00 local (lunes 16 a las 01:00 UTC):
    # En UTC es lunes, pero en Buenos Aires sigue siendo domingo de la semana previa.
    conn.execute(
        "INSERT INTO sesiones_estudio (user_id, duracion_minutos, tipo, fecha_hora) VALUES (?, ?, ?, ?);",
        (user_id, 60, "pomodoro", "2026-11-16T01:00:00+00:00"),
    )
    # Sesión del lunes 16 a las 09:00 local (lunes 16 a las 12:00 UTC):
    conn.execute(
        "INSERT INTO sesiones_estudio (user_id, duracion_minutos, tipo, fecha_hora) VALUES (?, ?, ?, ?);",
        (user_id, 40, "pomodoro", "2026-11-16T12:00:00+00:00"),
    )
    conn.commit()

    # Consultamos el lunes 16 al mediodía (15:00 UTC)
    now_lunes = datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc)
    stats = repo.get_weekly_stats(now_utc=now_lunes)

    # Solo la sesión de las 09:00 local cuenta en la semana nueva (40 min, no 100 min)
    assert stats["minutos_semana"] == 40
    assert stats["sesiones_semana"] == 1
    assert stats["minutos_hoy"] == 40

    conn.close()


# ----------------------------------------------------------------------
# 4. Punto 8: Páginas leídas por día desde `avances_de_lectura`
# ----------------------------------------------------------------------


def test_paginas_por_dia_desde_avances_de_lectura(db_fase2):
    """Un libro que avanza de la página 100 a la 130 suma 30 páginas ese día, no 130."""
    db_file, user_id = db_fase2
    conn = get_connection(db_file)

    ref_date = date(2026, 11, 19)

    # Libro en la página 130
    conn.execute(
        "INSERT INTO libros_lectura (id, user_id, titulo, capitulo_actual, total_capitulos, pagina_actual, total_paginas, fecha_actualizacion) "
        "VALUES (1, ?, 'Designing Data-Intensive Applications', 3, 12, 130, 500, '2026-11-20 01:00:00');",
        (user_id,),
    )
    # Avances registrados en `avances_de_lectura`:
    # Ayer (18): avanzó 50 páginas (de 50 a 100)
    conn.execute(
        "INSERT INTO avances_de_lectura (user_id, libro_id, paginas, registrado_en) VALUES (?, 1, 50, '2026-11-18T14:00:00+00:00');",
        (user_id,),
    )
    # Hoy (19): avanzó 30 páginas a las 22:00 locales (01:00 UTC del 20) (de 100 a 130)
    conn.execute(
        "INSERT INTO avances_de_lectura (user_id, libro_id, paginas, registrado_en) VALUES (?, 1, 30, '2026-11-20T01:00:00+00:00');",
        (user_id,),
    )
    conn.commit()

    tracker = ActivityTracker(user_id, conn=conn, zona=ZONA_BSAS)
    res = tracker.get_heatmap(days=5, reference_date=ref_date)

    dia_18 = next(d for d in res.days if d.date == "2026-11-18")
    dia_19 = next(d for d in res.days if d.date == "2026-11-19")

    # Cada día tiene sus páginas leídas reales
    assert dia_18.pages_read == 50
    assert dia_19.pages_read == 30  # ¡Suma 30 páginas ese día, NO 130!

    # Días sin avances quedan en 0
    dia_17 = next(d for d in res.days if d.date == "2026-11-17")
    assert dia_17.pages_read == 0

    # `StreakInfo.total_pages_read` sigue siendo la suma de `pagina_actual` (las páginas totales leídas)
    assert res.streak.total_pages_read == 130

    conn.close()


def test_resolucion_de_zona_horaria_por_ajuste_de_cuenta(db_fase2):
    """`ActivityTracker` y `FocusRepository` resuelven la zona automáticamente desde `AjustesDeCuenta`."""
    db_file, user_id = db_fase2
    conn = get_connection(db_file)

    # Fijamos el ajuste de la cuenta en Buenos Aires
    AjustesDeCuenta(conn, user_id).guardar(AJUSTE_ZONA_HORARIA, "America/Argentina/Buenos_Aires")

    tracker = ActivityTracker(user_id, conn=conn)
    assert tracker.zona == ZoneInfo("America/Argentina/Buenos_Aires")

    repo = FocusRepository(conn, user_id)
    assert repo.zona == ZoneInfo("America/Argentina/Buenos_Aires")

    conn.close()
