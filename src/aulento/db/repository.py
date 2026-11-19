"""Repositorios de acceso a datos para Plataformas, Cursos, Libros y Horarios."""

import sqlite3
from datetime import UTC, datetime

from aulento.core import permisos
from aulento.db.cuenta import exigir_cuenta
from aulento.models.curso import (
    Curso,
    CursoCreate,
    CursoUpdate,
    EstadoCurso,
)
from aulento.models.horario import (
    BloqueHorario,
    BloqueHorarioCreate,
    BloqueHorarioUpdate,
)
from aulento.models.libro import EstadoLibro, Libro, LibroCreate, LibroUpdate
from aulento.models.plataforma import (
    Plataforma,
    PlataformaCreate,
    PlataformaUpdate,
)


class PlataformaRepository:
    def __init__(self, conn: sqlite3.Connection, user_id: int):
        self.conn = conn
        self.user_id = exigir_cuenta(user_id)

    def create(self, p: PlataformaCreate) -> Plataforma:
        cursor = self.conn.cursor()
        query = """
        INSERT INTO plataformas (user_id, nombre, url_acceso, icono_color)
        VALUES (?, ?, ?, ?)
        RETURNING id, nombre, url_acceso, icono_color, fecha_creacion;
        """
        cursor.execute(query, (self.user_id, p.nombre, p.url_acceso, p.icono_color))
        row = cursor.fetchone()
        self.conn.commit()
        return Plataforma(**dict(row))

    def get_by_id(self, id: int) -> Plataforma | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM plataformas WHERE id = ? AND user_id = ?;", (id, self.user_id))
        row = cursor.fetchone()
        return Plataforma(**dict(row)) if row else None

    def get_by_name(self, nombre: str) -> Plataforma | None:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM plataformas WHERE nombre = ? COLLATE NOCASE AND user_id = ?;", (nombre, self.user_id)
        )
        row = cursor.fetchone()
        return Plataforma(**dict(row)) if row else None

    def list_all(self) -> list[Plataforma]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM plataformas WHERE user_id = ? ORDER BY nombre ASC;", (self.user_id,))
        return [Plataforma(**dict(row)) for row in cursor.fetchall()]

    def delete(self, id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM plataformas WHERE id = ? AND user_id = ?;", (id, self.user_id))
        self.conn.commit()
        return cursor.rowcount > 0

    def update(self, id: int, p: PlataformaUpdate) -> Plataforma | None:
        plat = self.get_by_id(id)
        if not plat:
            return None
        new_nom = p.nombre if p.nombre is not None else plat.nombre
        new_url = p.url_acceso if p.url_acceso is not None else plat.url_acceso
        new_color = p.icono_color if p.icono_color is not None else plat.icono_color
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE plataformas SET nombre = ?, url_acceso = ?, icono_color = ? WHERE id = ? AND user_id = ?;",
            (new_nom, new_url, new_color, id, self.user_id),
        )
        self.conn.commit()
        return self.get_by_id(id)


class CursoRepository:
    def __init__(self, conn: sqlite3.Connection, user_id: int):
        self.conn = conn
        self.user_id = exigir_cuenta(user_id)

    def create(self, c: CursoCreate) -> Curso:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT nombre FROM plataformas WHERE id = ? AND user_id = ?;", (c.plataforma_id, self.user_id)
        )
        plat_row = cursor.fetchone()
        if not plat_row:
            # Una plataforma de otra cuenta falla igual que una que no existe
            raise sqlite3.IntegrityError("FOREIGN KEY constraint failed")
        iniciada = False
        if not self.conn.in_transaction:
            self.conn.execute("BEGIN IMMEDIATE;")
            iniciada = True
        try:
            permisos.exigir(self.user_id, permisos.CREAR_CURSO, self.conn)
            query = """
            INSERT INTO cursos_externos (
                plataforma_id, nombre_curso, url_aula, progreso_pct, estado, prioridad,
                url_drive, ruta_local, url_notion, ruta_obsidian,
                external_id, fuente_sincronizacion, ultima_sincronizacion, sync_config_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id, plataforma_id, nombre_curso, url_aula, progreso_pct, estado, prioridad,
                      url_drive, ruta_local, url_notion, ruta_obsidian,
                      external_id, fuente_sincronizacion, ultima_sincronizacion, sync_config_json,
                      fecha_creacion, fecha_actualizacion;
            """
            cursor.execute(
                query,
                (
                    c.plataforma_id,
                    c.nombre_curso,
                    c.url_aula,
                    c.progreso_pct,
                    c.estado.value,
                    c.prioridad.value,
                    c.url_drive,
                    c.ruta_local,
                    c.url_notion,
                    c.ruta_obsidian,
                    c.external_id,
                    c.fuente_sincronizacion or "manual",
                    c.ultima_sincronizacion,
                    c.sync_config_json or "{}",
                ),
            )
            row = cursor.fetchone()
            if iniciada:
                self.conn.commit()
        except Exception:
            if iniciada:
                self.conn.rollback()
            raise
        curso = Curso(**dict(row))
        curso.nombre_plataforma = plat_row["nombre"]
        return curso

    def get_by_id(self, id: int) -> Curso | None:
        cursor = self.conn.cursor()
        query = """
        SELECT c.*, p.nombre as nombre_plataforma
        FROM cursos_externos c
        JOIN plataformas p ON c.plataforma_id = p.id
        WHERE c.id = ? AND p.user_id = ?;
        """
        cursor.execute(query, (id, self.user_id))
        row = cursor.fetchone()
        return Curso(**dict(row)) if row else None

    def list_all(
        self,
        plataforma_id: int | None = None,
        estado: EstadoCurso | None = None,
    ) -> list[Curso]:
        cursor = self.conn.cursor()
        query = """
        SELECT c.*, p.nombre as nombre_plataforma
        FROM cursos_externos c
        JOIN plataformas p ON c.plataforma_id = p.id
        WHERE p.user_id = ?
        """
        params: list = [self.user_id]
        if plataforma_id is not None:
            query += " AND c.plataforma_id = ?"
            params.append(plataforma_id)
        if estado is not None:
            query += " AND c.estado = ?"
            params.append(estado.value)

        query += " ORDER BY CASE c.prioridad WHEN 'alta' THEN 0 WHEN 'media' THEN 1 WHEN 'baja' THEN 2 ELSE 3 END, c.progreso_pct DESC;"
        cursor.execute(query, params)
        return [Curso(**dict(row)) for row in cursor.fetchall()]

    def update_progress(
        self,
        id: int,
        nuevo_progreso: float,
        nuevo_estado: EstadoCurso | str | None = None,
    ) -> Curso | None:
        if nuevo_progreso < 0.0 or nuevo_progreso > 100.0:
            raise ValueError("El progreso debe estar entre 0.0 y 100.0")

        cursor = self.conn.cursor()
        if nuevo_estado:
            st = nuevo_estado.value if isinstance(nuevo_estado, EstadoCurso) else str(nuevo_estado)
            query = """
            UPDATE cursos_externos
            SET progreso_pct = ?,
                estado = ?,
                fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE id = ? AND plataforma_id IN (SELECT id FROM plataformas WHERE user_id = ?);
            """
            cursor.execute(query, (nuevo_progreso, st, id, self.user_id))
        else:
            query = """
            UPDATE cursos_externos
            SET progreso_pct = ?,
                estado = CASE WHEN ? >= 100.0 THEN 'completado' ELSE estado END,
                fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE id = ? AND plataforma_id IN (SELECT id FROM plataformas WHERE user_id = ?);
            """
            cursor.execute(query, (nuevo_progreso, nuevo_progreso, id, self.user_id))
        self.conn.commit()
        return self.get_by_id(id)

    def find_by_url_or_name(self, identifier: str) -> Curso | None:
        """Busca un curso por ID numérico, URL exacta, URL parcial o nombre aproximado."""
        ident = identifier.strip()
        if not ident:
            return None

        # 1. Por ID si es puramente numérico
        if ident.isdigit():
            c = self.get_by_id(int(ident))
            if c:
                return c

        cursor = self.conn.cursor()
        base_select = """
        SELECT c.*, p.nombre as nombre_plataforma
        FROM cursos_externos c
        JOIN plataformas p ON c.plataforma_id = p.id
        WHERE p.user_id = ?
        """

        # 2. Por URL exacta
        cursor.execute(base_select + " AND c.url_aula = ? LIMIT 1;", (self.user_id, ident))
        row = cursor.fetchone()
        if row:
            return Curso(**dict(row))

        # 3. Por URL parcial (ej. contiene la URL o slug)
        cursor.execute(base_select + " AND c.url_aula LIKE ? LIMIT 1;", (self.user_id, f"%{ident}%"))
        row = cursor.fetchone()
        if row:
            return Curso(**dict(row))

        # 4. Por nombre exacto (case-insensitive)
        cursor.execute(base_select + " AND LOWER(c.nombre_curso) = LOWER(?) LIMIT 1;", (self.user_id, ident))
        row = cursor.fetchone()
        if row:
            return Curso(**dict(row))

        # 5. Por nombre parcial
        cursor.execute(
            base_select + " AND LOWER(c.nombre_curso) LIKE LOWER(?) LIMIT 1;", (self.user_id, f"%{ident}%")
        )
        row = cursor.fetchone()
        if row:
            return Curso(**dict(row))

        return None

    def delete(self, id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM cursos_externos WHERE id = ? AND plataforma_id IN (SELECT id FROM plataformas WHERE user_id = ?);",
            (id, self.user_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def update(self, id: int, c: CursoUpdate) -> Curso | None:
        curso = self.get_by_id(id)
        if not curso:
            return None
        new_nom = c.nombre_curso if c.nombre_curso is not None else curso.nombre_curso
        new_url = c.url_aula if c.url_aula is not None else curso.url_aula
        new_prog = c.progreso_pct if c.progreso_pct is not None else curso.progreso_pct
        new_st = c.estado.value if c.estado else (curso.estado.value if hasattr(curso.estado, "value") else str(curso.estado))
        new_prio = c.prioridad.value if c.prioridad else (curso.prioridad.value if hasattr(curso.prioridad, "value") else str(curso.prioridad))
        
        fields_set = getattr(c, "model_fields_set", set())
        new_drive = c.url_drive if "url_drive" in fields_set else curso.url_drive
        new_local = c.ruta_local if "ruta_local" in fields_set else curso.ruta_local
        new_notion = c.url_notion if "url_notion" in fields_set else curso.url_notion
        new_obsidian = c.ruta_obsidian if "ruta_obsidian" in fields_set else curso.ruta_obsidian
        new_ext = c.external_id if "external_id" in fields_set else curso.external_id
        new_fuente = c.fuente_sincronizacion if "fuente_sincronizacion" in fields_set else curso.fuente_sincronizacion
        new_ultima = c.ultima_sincronizacion if "ultima_sincronizacion" in fields_set else curso.ultima_sincronizacion
        new_sync_cfg = c.sync_config_json if "sync_config_json" in fields_set else curso.sync_config_json

        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE cursos_externos
            SET nombre_curso = ?, url_aula = ?, progreso_pct = ?, estado = ?, prioridad = ?,
                url_drive = ?, ruta_local = ?, url_notion = ?, ruta_obsidian = ?,
                external_id = ?, fuente_sincronizacion = ?, ultima_sincronizacion = ?, sync_config_json = ?,
                fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE id = ? AND plataforma_id IN (SELECT id FROM plataformas WHERE user_id = ?);
            """,
            (new_nom, new_url, new_prog, new_st, new_prio, new_drive, new_local, new_notion, new_obsidian,
             new_ext, new_fuente, new_ultima, new_sync_cfg, id, self.user_id),
        )
        self.conn.commit()
        return self.get_by_id(id)

    def find_by_external_id(self, external_id: str, plataforma_id: int | None = None) -> Curso | None:
        if not external_id or not external_id.strip():
            return None
        cursor = self.conn.cursor()
        query = """
        SELECT c.*, p.nombre as nombre_plataforma
        FROM cursos_externos c
        JOIN plataformas p ON c.plataforma_id = p.id
        WHERE p.user_id = ? AND c.external_id = ?
        """
        params = [self.user_id, external_id.strip()]
        if plataforma_id is not None:
            query += " AND c.plataforma_id = ?"
            params.append(plataforma_id)
        query += " LIMIT 1;"
        cursor.execute(query, params)
        row = cursor.fetchone()
        return Curso(**dict(row)) if row else None

    def find_by_name(self, nombre: str, plataforma_id: int | None = None) -> Curso | None:
        nom = nombre.strip()
        if not nom:
            return None
        cursor = self.conn.cursor()
        query = """
        SELECT c.*, p.nombre as nombre_plataforma
        FROM cursos_externos c
        JOIN plataformas p ON c.plataforma_id = p.id
        WHERE p.user_id = ? AND LOWER(c.nombre_curso) = LOWER(?)
        """
        params = [self.user_id, nom]
        if plataforma_id is not None:
            query += " AND c.plataforma_id = ?"
            params.append(plataforma_id)
        query += " LIMIT 1;"
        cursor.execute(query, params)
        row = cursor.fetchone()
        return Curso(**dict(row)) if row else None

    def update_sync_progress(
        self,
        id: int,
        nuevo_progreso: float,
        nuevo_estado: EstadoCurso | str | None = None,
        fuente: str = "manual",
        external_id: str | None = None,
        sync_config_json: str | None = None,
    ) -> Curso | None:
        if nuevo_progreso < 0.0 or nuevo_progreso > 100.0:
            raise ValueError("El progreso debe estar entre 0.0 y 100.0")

        curso = self.get_by_id(id)
        if not curso:
            return None

        st = nuevo_estado.value if isinstance(nuevo_estado, EstadoCurso) else (str(nuevo_estado) if nuevo_estado else None)
        if st is None:
            st = "completado" if nuevo_progreso >= 100.0 else curso.estado.value

        ext_id = external_id if external_id is not None else curso.external_id
        cfg_json = sync_config_json if sync_config_json is not None else curso.sync_config_json

        cursor = self.conn.cursor()
        query = """
        UPDATE cursos_externos
        SET progreso_pct = ?,
            estado = ?,
            fuente_sincronizacion = ?,
            ultima_sincronizacion = CURRENT_TIMESTAMP,
            external_id = ?,
            sync_config_json = ?,
            fecha_actualizacion = CURRENT_TIMESTAMP
        WHERE id = ? AND plataforma_id IN (SELECT id FROM plataformas WHERE user_id = ?);
        """
        cursor.execute(query, (nuevo_progreso, st, fuente, ext_id, cfg_json, id, self.user_id))
        self.conn.commit()
        return self.get_by_id(id)

    def get_sync_status(self) -> dict:
        cursor = self.conn.cursor()
        query = """
        SELECT
            COUNT(*) as total_cursos,
            SUM(CASE WHEN fuente_sincronizacion IS NOT NULL AND fuente_sincronizacion != 'manual' THEN 1 ELSE 0 END) as cursos_sincronizados,
            MAX(ultima_sincronizacion) as ultima_sincronizacion_global
        FROM cursos_externos c
        JOIN plataformas p ON c.plataforma_id = p.id
        WHERE p.user_id = ?;
        """
        cursor.execute(query, (self.user_id,))
        row = cursor.fetchone()
        return {
            "total_cursos": row["total_cursos"] or 0,
            "cursos_sincronizados": row["cursos_sincronizados"] or 0,
            "ultima_sincronizacion": row["ultima_sincronizacion_global"],
        }


def _validar_progreso_libro(
    pagina: int,
    total_paginas: int | None,
    capitulo: int,
    total_capitulos: int | None,
) -> None:
    """Valida la coherencia de páginas y capítulos antes de escribir en la base."""
    if pagina < 0 or capitulo < 0:
        raise ValueError("La página y el capítulo no pueden ser negativos.")
    if total_paginas is not None and total_paginas <= 0:
        raise ValueError("El total de páginas debe ser mayor a 0.")
    if total_capitulos is None or total_capitulos <= 0:
        raise ValueError("El total de capítulos debe ser mayor a 0.")
    if total_paginas is not None and pagina > total_paginas:
        raise ValueError(f"La página {pagina} supera el total de páginas del libro ({total_paginas}).")
    if capitulo > total_capitulos:
        raise ValueError(f"El capítulo {capitulo} supera el total de capítulos del libro ({total_capitulos}).")


def _esta_completado(
    pagina: int,
    total_paginas: int | None,
    capitulo: int,
    total_capitulos: int | None,
) -> bool:
    """Calcula si un libro alcanzó el 100% de lectura según páginas si se conocen, o capítulos si no."""
    if total_paginas and total_paginas > 0:
        return pagina >= total_paginas
    if total_capitulos and total_capitulos > 0:
        return capitulo >= total_capitulos
    return False


class LibroRepository:
    def __init__(self, conn: sqlite3.Connection, user_id: int):
        self.conn = conn
        self.user_id = exigir_cuenta(user_id)

    def create(self, l: LibroCreate) -> Libro:
        cursor = self.conn.cursor()
        query = """
        INSERT INTO libros_lectura (
            user_id, titulo, autor, capitulo_actual, total_capitulos, pagina_actual, total_paginas,
            ruta_vault, estado, google_books_id, fuente_sincronizacion, ultima_sincronizacion
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING *;
        """
        cursor.execute(
            query,
            (
                self.user_id,
                l.titulo,
                l.autor,
                l.capitulo_actual,
                l.total_capitulos,
                l.pagina_actual,
                l.total_paginas,
                l.ruta_vault,
                l.estado.value,
                l.google_books_id,
                l.fuente_sincronizacion or "manual",
                str(l.ultima_sincronizacion) if l.ultima_sincronizacion else None,
            ),
        )
        row = cursor.fetchone()
        self.conn.commit()
        return Libro(**dict(row))

    def get_by_id(self, id: int) -> Libro | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM libros_lectura WHERE id = ? AND user_id = ?;", (id, self.user_id))
        row = cursor.fetchone()
        return Libro(**dict(row)) if row else None

    def find_by_title(self, title: str) -> Libro | None:
        """Busca un libro por título exacto o parcial (case-insensitive)."""
        t_clean = title.strip()
        if not t_clean:
            return None

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM libros_lectura WHERE LOWER(titulo) = LOWER(?) AND user_id = ?;", (t_clean, self.user_id)
        )
        row = cursor.fetchone()
        if not row:
            cursor.execute(
                "SELECT * FROM libros_lectura WHERE LOWER(titulo) LIKE LOWER(?) AND user_id = ? ORDER BY id ASC LIMIT 1;",
                (f"%{t_clean}%", self.user_id),
            )
            row = cursor.fetchone()
        return Libro(**dict(row)) if row else None

    def buscar_por_titulo(self, titulo: str) -> list[Libro]:
        """Busca libros por coincidencias exactas (case-insensitive) o, si no hay ninguna, parciales."""
        t_clean = (titulo or "").strip()
        if not t_clean:
            return []

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM libros_lectura WHERE LOWER(titulo) = LOWER(?) AND user_id = ? ORDER BY id ASC;",
            (t_clean, self.user_id),
        )
        exactas = [Libro(**dict(row)) for row in cursor.fetchall()]
        if exactas:
            return exactas

        t_escapado = t_clean.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        cursor.execute(
            "SELECT * FROM libros_lectura WHERE LOWER(titulo) LIKE LOWER(?) ESCAPE '\\' AND user_id = ? ORDER BY id ASC;",
            (f"%{t_escapado}%", self.user_id),
        )
        return [Libro(**dict(row)) for row in cursor.fetchall()]

    def find_by_google_books_id(self, google_books_id: str) -> Libro | None:
        """Busca un libro por su ID de volumen de Google Books."""
        g_id = (google_books_id or "").strip()
        if not g_id:
            return None
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM libros_lectura WHERE google_books_id = ? AND user_id = ?;",
            (g_id, self.user_id),
        )
        row = cursor.fetchone()
        return Libro(**dict(row)) if row else None

    def vincular_google_books(self, id: int, google_books_id: str) -> Libro | None:
        """Asocia un libro a un volumen de Google Books."""
        g_id = (google_books_id or "").strip()
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE libros_lectura
            SET google_books_id = ?, fuente_sincronizacion = 'google_books', fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?;
            """,
            (g_id or None, id, self.user_id),
        )
        self.conn.commit()
        return self.get_by_id(id)

    def list_all(self, estado: EstadoLibro | None = None) -> list[Libro]:
        cursor = self.conn.cursor()
        query = "SELECT * FROM libros_lectura WHERE user_id = ?"
        params: list = [self.user_id]
        if estado is not None:
            query += " AND estado = ?"
            params.append(estado.value)
        query += " ORDER BY fecha_actualizacion DESC;"
        cursor.execute(query, params)
        return [Libro(**dict(row)) for row in cursor.fetchall()]

    def update_progress(
        self,
        id: int,
        pagina_actual: int | None = None,
        total_paginas: int | None = None,
        capitulo_actual: int | None = None,
        total_capitulos: int | None = None,
        estado: EstadoLibro | str | None = None,
        fuente_sincronizacion: str | None = None,
        ultima_sincronizacion: str | None = None,
        google_books_id: str | None = None,
    ) -> Libro | None:
        """Actualiza el progreso de lectura de un libro por páginas y/o capítulos."""
        libro = self.get_by_id(id)
        if not libro:
            return None

        new_pag = pagina_actual if pagina_actual is not None else libro.pagina_actual
        new_total_pag = total_paginas if total_paginas is not None else libro.total_paginas
        new_cap = capitulo_actual if capitulo_actual is not None else libro.capitulo_actual
        new_total_cap = total_capitulos if total_capitulos is not None else libro.total_capitulos

        # Validar antes de escribir: un valor inválido dejaría la fila ilegible para el modelo
        _validar_progreso_libro(new_pag, new_total_pag, new_cap, new_total_cap)

        # Determinar estado
        if estado:
            new_estado = estado.value if isinstance(estado, EstadoLibro) else str(estado)
        else:
            is_complete = _esta_completado(new_pag, new_total_pag, new_cap, new_total_cap)
            new_estado = EstadoLibro.COMPLETADO.value if is_complete else libro.estado.value

        new_fuente = fuente_sincronizacion if fuente_sincronizacion is not None else libro.fuente_sincronizacion
        new_sync = ultima_sincronizacion if ultima_sincronizacion is not None else libro.ultima_sincronizacion
        new_gbooks = google_books_id if google_books_id is not None else libro.google_books_id

        cursor = self.conn.cursor()
        query = """
        UPDATE libros_lectura
        SET pagina_actual = ?,
            total_paginas = ?,
            capitulo_actual = ?,
            total_capitulos = ?,
            estado = ?,
            fuente_sincronizacion = ?,
            ultima_sincronizacion = ?,
            google_books_id = ?,
            fecha_actualizacion = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?;
        """
        cursor.execute(
            query,
            (new_pag, new_total_pag, new_cap, new_total_cap, new_estado, new_fuente, new_sync, new_gbooks, id, self.user_id),
        )
        if new_pag > libro.pagina_actual:
            cursor.execute(
                """
                INSERT INTO avances_de_lectura (user_id, libro_id, paginas, registrado_en)
                VALUES (?, ?, ?, ?);
                """,
                (self.user_id, id, new_pag - libro.pagina_actual, datetime.now(UTC).isoformat()),
            )
        self.conn.commit()
        return self.get_by_id(id)

    def advance_chapter(self, id: int, chapters: int = 1) -> Libro | None:
        libro = self.get_by_id(id)
        if not libro:
            return None

        nuevo_cap = libro.capitulo_actual + chapters
        nuevo_cap = min(nuevo_cap, libro.total_capitulos)

        is_complete = _esta_completado(libro.pagina_actual, libro.total_paginas, nuevo_cap, libro.total_capitulos)
        nuevo_estado = EstadoLibro.COMPLETADO.value if is_complete else libro.estado.value

        cursor = self.conn.cursor()
        query = """
        UPDATE libros_lectura
        SET capitulo_actual = ?,
            estado = ?,
            fecha_actualizacion = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?;
        """
        cursor.execute(query, (nuevo_cap, nuevo_estado, id, self.user_id))
        self.conn.commit()
        return self.get_by_id(id)

    def delete(self, id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM libros_lectura WHERE id = ? AND user_id = ?;", (id, self.user_id))
        self.conn.commit()
        return cursor.rowcount > 0

    def update(self, id: int, l: LibroUpdate) -> Libro | None:
        libro = self.get_by_id(id)
        if not libro:
            return None

        # Campos no anulables: siguen ignorando null
        new_tit = l.titulo if l.titulo is not None else libro.titulo
        new_cap = l.capitulo_actual if l.capitulo_actual is not None else libro.capitulo_actual
        new_tot_cap = l.total_capitulos if l.total_capitulos is not None else libro.total_capitulos
        new_pag = l.pagina_actual if l.pagina_actual is not None else libro.pagina_actual
        new_st = (
            l.estado.value
            if l.estado
            else (libro.estado.value if hasattr(libro.estado, "value") else str(libro.estado))
        )

        # Campos anulables: se actualizan si vinieron en el pedido aunque su valor sea None
        fields_set = getattr(l, "model_fields_set", set())
        new_aut = l.autor if "autor" in fields_set else libro.autor
        new_tot_pag = l.total_paginas if "total_paginas" in fields_set else libro.total_paginas
        new_vault = l.ruta_vault if "ruta_vault" in fields_set else libro.ruta_vault
        new_gbooks = l.google_books_id if "google_books_id" in fields_set else libro.google_books_id
        new_fuente = l.fuente_sincronizacion if "fuente_sincronizacion" in fields_set else libro.fuente_sincronizacion
        if "ultima_sincronizacion" in fields_set:
            new_sync = str(l.ultima_sincronizacion) if l.ultima_sincronizacion is not None else None
        else:
            new_sync = libro.ultima_sincronizacion

        _validar_progreso_libro(new_pag, new_tot_pag, new_cap, new_tot_cap)

        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE libros_lectura
            SET titulo = ?, autor = ?, capitulo_actual = ?, total_capitulos = ?, pagina_actual = ?, total_paginas = ?,
                ruta_vault = ?, estado = ?, google_books_id = ?, fuente_sincronizacion = ?,
                ultima_sincronizacion = ?, fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?;
            """,
            (
                new_tit,
                new_aut,
                new_cap,
                new_tot_cap,
                new_pag,
                new_tot_pag,
                new_vault,
                new_st,
                new_gbooks,
                new_fuente,
                new_sync,
                id,
                self.user_id,
            ),
        )
        if new_pag > libro.pagina_actual:
            cursor.execute(
                """
                INSERT INTO avances_de_lectura (user_id, libro_id, paginas, registrado_en)
                VALUES (?, ?, ?, ?);
                """,
                (self.user_id, id, new_pag - libro.pagina_actual, datetime.now(UTC).isoformat()),
            )
        self.conn.commit()
        return self.get_by_id(id)


class MCPAuditRepository:
    """Repositorio para auditar acciones ejecutadas a través del protocolo MCP.

    No se ata a una cuenta al construirse: también registra los rechazos de autenticación, que no tienen dueño.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def log(
        self,
        tool_name: str,
        params_json: str = "{}",
        transport: str = "stdio",
        client_ip: str | None = None,
        status: str = "success",
        error_message: str | None = None,
        user_id: int | None = None,
    ) -> int:
        """Registra una acción. `user_id` es la cuenta que la originó; None para un rechazo de autenticación."""
        if user_id is not None:
            exigir_cuenta(user_id)
        cursor = self.conn.cursor()
        query = """
        INSERT INTO mcp_audit_logs (user_id, tool_name, params_json, transport, client_ip, status, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        RETURNING id;
        """
        cursor.execute(query, (user_id, tool_name, params_json, transport, client_ip, status, error_message))
        row = cursor.fetchone()
        self.conn.commit()
        return row[0] if row else 0

    def get_recent_logs(self, user_id: int, limit: int = 50) -> list[dict]:
        """Últimos registros de auditoría de una cuenta. Los rechazos sin cuenta no se listan."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM mcp_audit_logs WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?;",
            (exigir_cuenta(user_id), limit),
        )
        return [dict(row) for row in cursor.fetchall()]


class BloqueHorarioRepository:
    def __init__(self, conn: sqlite3.Connection, user_id: int):
        self.conn = conn
        self.user_id = exigir_cuenta(user_id)

    def create(self, b: BloqueHorarioCreate) -> BloqueHorario:
        cursor = self.conn.cursor()
        query = """
        INSERT INTO bloques_horarios (user_id, dia_semana, hora_inicio, hora_fin, tipo, descripcion, url_acceso)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        RETURNING id, dia_semana, hora_inicio, hora_fin, tipo, descripcion, url_acceso;
        """
        cursor.execute(
            query,
            (self.user_id, b.dia_semana, b.hora_inicio, b.hora_fin, b.tipo.value, b.descripcion, b.url_acceso),
        )
        row = cursor.fetchone()
        self.conn.commit()
        return BloqueHorario(**dict(row))

    def list_all(self, dia_semana: int | None = None) -> list[BloqueHorario]:
        cursor = self.conn.cursor()
        query = "SELECT * FROM bloques_horarios WHERE user_id = ?"
        params: list = [self.user_id]
        if dia_semana is not None:
            query += " AND dia_semana = ?"
            params.append(dia_semana)
        query += " ORDER BY dia_semana ASC, hora_inicio ASC;"
        cursor.execute(query, params)
        return [BloqueHorario(**dict(row)) for row in cursor.fetchall()]

    def get(self, id: int) -> BloqueHorario | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM bloques_horarios WHERE id = ? AND user_id = ?;", (id, self.user_id))
        row = cursor.fetchone()
        if not row:
            return None
        return BloqueHorario(**dict(row))

    def update(self, id: int, b: BloqueHorarioUpdate) -> BloqueHorario | None:
        current = self.get(id)
        if not current:
            return None

        dia_semana = b.dia_semana if b.dia_semana is not None else current.dia_semana
        hora_inicio = b.hora_inicio if b.hora_inicio is not None else current.hora_inicio
        hora_fin = b.hora_fin if b.hora_fin is not None else current.hora_fin
        tipo = b.tipo.value if b.tipo is not None else (current.tipo.value if hasattr(current.tipo, 'value') else current.tipo)
        descripcion = b.descripcion if b.descripcion is not None else current.descripcion
        url_acceso = b.url_acceso if b.url_acceso is not None else current.url_acceso

        if hora_inicio >= hora_fin:
            raise ValueError(f"hora_inicio ({hora_inicio}) debe ser menor que hora_fin ({hora_fin})")

        cursor = self.conn.cursor()
        query = """
        UPDATE bloques_horarios
        SET dia_semana = ?, hora_inicio = ?, hora_fin = ?, tipo = ?, descripcion = ?, url_acceso = ?
        WHERE id = ? AND user_id = ?
        RETURNING id, dia_semana, hora_inicio, hora_fin, tipo, descripcion, url_acceso;
        """
        cursor.execute(query, (dia_semana, hora_inicio, hora_fin, tipo, descripcion, url_acceso, id, self.user_id))
        row = cursor.fetchone()
        self.conn.commit()
        if not row:
            return None
        return BloqueHorario(**dict(row))

    def delete(self, id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM bloques_horarios WHERE id = ? AND user_id = ?;", (id, self.user_id))
        self.conn.commit()
        return cursor.rowcount > 0
