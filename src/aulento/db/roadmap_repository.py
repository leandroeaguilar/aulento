"""Repositorio SQLite para Rutas de Aprendizaje, Módulos, Temas y Clases."""

import json
import logging
import sqlite3
from collections.abc import Sequence
from typing import Any

from aulento.core import permisos
from aulento.db.connection import get_connection
from aulento.db.cuenta import exigir_cuenta
from aulento.db.schema import create_schema
from aulento.models.roadmap import (
    EstadoTema,
    FuenteTema,
    GapTopicItem,
    OrigenClase,
    PrerequisiteCreate,
    PrerequisiteEdge,
    Roadmap,
    RoadmapCreate,
    RoadmapDetail,
    RoadmapLesson,
    RoadmapLessonCreate,
    RoadmapLessonVersion,
    RoadmapModule,
    RoadmapTopic,
    RoadmapTopicCreate,
    TokenLogItem,
    TokenUsageSummary,
)

TIPOS_DE_PRELACION = ("estricta", "recomendada")
MAX_VERSIONES_POR_TEMA = 10


logger = logging.getLogger(__name__)

class PrerequisiteCycleError(ValueError):
    """La prelación cerraría un ciclo con las prelaciones ya guardadas de la ruta."""


class RoadmapNotFoundError(ValueError):
    """La ruta indicada no existe."""


def registrar_consumo_de_ia(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    provider: str,
    model: str,
    endpoint_tipo: str,
    api_tier: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    estimated_cost_usd: float | None,
    status_code: int,
    latency_ms: float,
) -> int:
    """Anota en `conn` una llamada a un proveedor de IA a nombre de la cuenta; devuelve el id de la fila."""
    cursor = conn.execute(
        """
        INSERT INTO api_usage_logs (
            user_id, provider, model, endpoint_tipo, api_tier, prompt_tokens,
            completion_tokens, total_tokens, estimated_cost_usd, status_code, latency_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            exigir_cuenta(user_id),
            provider,
            model,
            endpoint_tipo,
            api_tier,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            estimated_cost_usd,
            status_code,
            latency_ms,
        ),
    )
    conn.commit()
    return cursor.lastrowid


# Ajuste de la cuenta: la siembra automática de plantillas ya corrió una vez
AJUSTE_PLANTILLAS_SEMBRADAS = "plantillas_sembradas"


class RoadmapRepository:
    """Acceso a datos persistentes y cálculo reactivo de avance para las Rutas de Estudio de una cuenta.

    Un módulo, tema, clase, versión o prelación es de la cuenta si lo es la ruta de la que cuelga: todo
    acceso por uno de esos ids se resuelve hasta `rutas_aprendizaje.user_id`.
    """

    def __init__(
        self,
        user_id: int,
        db_path: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        self.user_id = exigir_cuenta(user_id)
        self.db_path = db_path
        self.conn = conn

    def _get_conn(self) -> sqlite3.Connection:
        conn = get_connection(self.db_path)
        create_schema(conn)
        return conn

    def _ruta_es_propia(self, conn: sqlite3.Connection, ruta_id: int) -> bool:
        fila = conn.execute(
            "SELECT 1 FROM rutas_aprendizaje WHERE id = ? AND user_id = ?;", (ruta_id, self.user_id)
        ).fetchone()
        return fila is not None

    def _ruta_de_modulo(self, conn: sqlite3.Connection, module_id: int) -> int | None:
        """Ruta de la cuenta a la que pertenece el módulo, o None si no existe o es de otra cuenta."""
        fila = conn.execute(
            """
            SELECT m.ruta_id FROM ruta_modulos m
            JOIN rutas_aprendizaje r ON r.id = m.ruta_id
            WHERE m.id = ? AND r.user_id = ?;
            """,
            (module_id, self.user_id),
        ).fetchone()
        return fila["ruta_id"] if fila else None

    def _ruta_de_tema(self, conn: sqlite3.Connection, topic_id: int) -> int | None:
        """Ruta de la cuenta a la que pertenece el tema, o None si no existe o es de otra cuenta."""
        fila = conn.execute(
            """
            SELECT m.ruta_id FROM ruta_temas t
            JOIN ruta_modulos m ON m.id = t.modulo_id
            JOIN rutas_aprendizaje r ON r.id = m.ruta_id
            WHERE t.id = ? AND r.user_id = ?;
            """,
            (topic_id, self.user_id),
        ).fetchone()
        return fila["ruta_id"] if fila else None

    def _recalculate_progress(self, conn: sqlite3.Connection, ruta_id: int) -> float:
        """Calcula el porcentaje de temas completados y actualiza rutas_aprendizaje."""
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                COUNT(t.id) as total,
                SUM(CASE WHEN t.estado = 'completado' THEN 1 ELSE 0 END) as completados
            FROM ruta_modulos m
            JOIN ruta_temas t ON t.modulo_id = m.id
            WHERE m.ruta_id = ?;
            """,
            (ruta_id,),
        )
        row = cursor.fetchone()
        total = row["total"] if row and row["total"] else 0
        completados = row["completados"] if row and row["completados"] else 0
        pct = round((completados / total) * 100.0, 1) if total > 0 else 0.0

        cursor.execute(
            """
            UPDATE rutas_aprendizaje 
            SET progreso_pct = ?, fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?;
            """,
            (pct, ruta_id, self.user_id),
        )
        return pct

    def create_roadmap(self, data: RoadmapCreate, conn: sqlite3.Connection | None = None) -> RoadmapDetail:
        """Crea una ruta completa con sus módulos y temas de forma atómica."""
        propia = conn is None and self.conn is None
        conn = conn or self.conn or self._get_conn()
        iniciada = False
        try:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE;")
                iniciada = True
            permisos.exigir(self.user_id, permisos.CREAR_RUTA, conn)
            cursor = conn.cursor()
            enfoque = getattr(data, "enfoque_estudio", "profesional") or "profesional"
            cursor.execute(
                """
                INSERT INTO rutas_aprendizaje (user_id, titulo, descripcion, categoria, nivel_objetivo, enfoque_estudio, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    self.user_id,
                    data.titulo,
                    data.descripcion,
                    data.categoria,
                    data.nivel_objetivo,
                    enfoque,
                    json.dumps(data.metadata_json or {}),
                ),
            )
            ruta_id = cursor.lastrowid
            created_modules: list[RoadmapModule] = []
            ids_por_titulo: dict[str, int] = {}
            prerrequisitos_pendientes: list[tuple[int, list[str]]] = []

            for mod_idx, mod_data in enumerate(data.modulos, start=1):
                cursor.execute(
                    """
                    INSERT INTO ruta_modulos (ruta_id, titulo, descripcion, orden)
                    VALUES (?, ?, ?, ?);
                    """,
                    (ruta_id, mod_data.titulo, mod_data.descripcion, mod_data.orden or mod_idx),
                )
                modulo_id = cursor.lastrowid
                created_topics: list[RoadmapTopic] = []

                for top_idx, top_data in enumerate(mod_data.temas, start=1):
                    cursor.execute(
                        """
                        INSERT INTO ruta_temas (modulo_id, titulo, descripcion, orden, estado, fuente)
                        VALUES (?, ?, ?, ?, ?, ?);
                        """,
                        (
                            modulo_id,
                            top_data.titulo,
                            top_data.descripcion,
                            top_data.orden or top_idx,
                            top_data.estado.value if hasattr(top_data.estado, "value") else top_data.estado,
                            top_data.fuente.value if hasattr(top_data.fuente, "value") else top_data.fuente,
                        ),
                    )
                    tema_id = cursor.lastrowid
                    ids_por_titulo.setdefault(top_data.titulo.strip().lower(), tema_id)
                    if top_data.prerrequisitos:
                        prerrequisitos_pendientes.append((tema_id, top_data.prerrequisitos))
                    created_topics.append(
                        RoadmapTopic(
                            id=tema_id,
                            modulo_id=modulo_id,
                            titulo=top_data.titulo,
                            descripcion=top_data.descripcion,
                            orden=top_data.orden or top_idx,
                            estado=top_data.estado,
                            fuente=top_data.fuente,
                        )
                    )

                created_modules.append(
                    RoadmapModule(
                        id=modulo_id,
                        ruta_id=ruta_id,
                        titulo=mod_data.titulo,
                        descripcion=mod_data.descripcion,
                        orden=mod_data.orden or mod_idx,
                        temas=created_topics,
                    )
                )

            self._insert_prerequisites_by_title(cursor, ruta_id, ids_por_titulo, prerrequisitos_pendientes)
            self._recalculate_progress(conn, ruta_id)
            if iniciada:
                conn.commit()

            return RoadmapDetail(
                id=ruta_id,
                titulo=data.titulo,
                descripcion=data.descripcion,
                categoria=data.categoria,
                nivel_objetivo=data.nivel_objetivo,
                enfoque_estudio=enfoque,
                progreso_pct=0.0,
                metadata_json=data.metadata_json or {},
                total_temas=sum(len(m.temas) for m in created_modules),
                temas_completados=0,
                modulos=created_modules,
            )
        except Exception:
            if iniciada:
                conn.rollback()
            raise
        finally:
            if propia:
                conn.close()

    @staticmethod
    def _insert_prerequisites_by_title(
        cursor: sqlite3.Cursor,
        ruta_id: int,
        ids_por_titulo: dict[str, int],
        pendientes: list[tuple[int, list[str]]],
    ) -> int:
        """Persiste como prelaciones los prerrequisitos declarados por título de tema.

        Ignora títulos sin coincidencia exacta (insensible a mayúsculas), auto-referencias,
        repetidas y aristas que cerrarían un ciclo con las ya aceptadas.

        Solo se guardan las declaradas: la secuencia de los temas que quedan sin prerrequisito
        la infiere el grafo al leer (ver `PrerequisiteGraphEngine`).
        """
        from aulento.roadmap.graph_engine import detecta_ciclo

        aceptadas: list[tuple[int, int]] = []
        for destino_id, titulos in pendientes:
            for titulo in titulos:
                origen_id = ids_por_titulo.get(titulo.strip().lower())
                if origen_id is None or origen_id == destino_id:
                    continue
                if (origen_id, destino_id) in aceptadas or detecta_ciclo(aceptadas, origen_id, destino_id):
                    continue
                cursor.execute(
                    """
                    INSERT INTO ruta_prelaciones (ruta_id, tema_origen_id, tema_destino_id, tipo)
                    VALUES (?, ?, ?, 'estricta');
                    """,
                    (ruta_id, origen_id, destino_id),
                )
                aceptadas.append((origen_id, destino_id))
        return len(aceptadas)

    def get_roadmaps(self) -> list[Roadmap]:
        """Obtiene la lista de rutas con conteos de temas y progreso."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 
                    r.id, r.titulo, r.descripcion, r.categoria, r.nivel_objetivo, r.enfoque_estudio,
                    r.progreso_pct, r.metadata_json, r.fecha_creacion, r.fecha_actualizacion,
                    COUNT(t.id) as total_temas,
                    SUM(CASE WHEN t.estado = 'completado' THEN 1 ELSE 0 END) as temas_completados
                FROM rutas_aprendizaje r
                LEFT JOIN ruta_modulos m ON m.ruta_id = r.id
                LEFT JOIN ruta_temas t ON t.modulo_id = m.id
                WHERE r.user_id = ?
                GROUP BY r.id
                ORDER BY r.id ASC;
                """,
                (self.user_id,),
            )
            rows = cursor.fetchall()
            roadmaps: list[Roadmap] = []
            for row in rows:
                meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
                enfoque = dict(row).get("enfoque_estudio") or "profesional"
                roadmaps.append(
                    Roadmap(
                        id=row["id"],
                        titulo=row["titulo"],
                        descripcion=row["descripcion"],
                        categoria=row["categoria"],
                        nivel_objetivo=row["nivel_objetivo"],
                        enfoque_estudio=enfoque,
                        progreso_pct=float(row["progreso_pct"] or 0.0),
                        metadata_json=meta,
                        total_temas=row["total_temas"] or 0,
                        temas_completados=row["temas_completados"] or 0,
                        fecha_creacion=row["fecha_creacion"],
                        fecha_actualizacion=row["fecha_actualizacion"],
                    )
                )
            return roadmaps
        finally:
            conn.close()

    def exigir_poder_crear_una_ruta(self) -> None:
        """Corta antes de un trabajo caro (generar con IA, leer un temario) si la cuenta no puede crear otra ruta."""
        conn = self._get_conn()
        try:
            permisos.exigir(self.user_id, permisos.CREAR_RUTA, conn)
        finally:
            conn.close()

    def ensure_curated_templates(self, solo_la_primera_vez: bool = False) -> list[RoadmapDetail]:
        """Asegura que las 4 plantillas canónicas de la industria estén entre las rutas de la cuenta.

        `solo_la_primera_vez` es la siembra automática de la pantalla: corre una sola vez por cuenta. Si la persona
        borra una plantilla, no vuelve sola a ocupar su lugar (con un tope de rutas, le dejaría el cupo tomado), y
        si un tope la frena, no es un error: devuelve lo que entró (062).
        """
        from aulento.core.secretos import AjustesDeCuenta
        from aulento.roadmap.templates import get_curated_templates

        if solo_la_primera_vez:
            conn = self._get_conn()
            try:
                ajustes = AjustesDeCuenta(conn, self.user_id)
                if ajustes.leer(AJUSTE_PLANTILLAS_SEMBRADAS, False):
                    return []
                ajustes.guardar(AJUSTE_PLANTILLAS_SEMBRADAS, True)
                conn.commit()
            finally:
                conn.close()

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT titulo FROM rutas_aprendizaje WHERE user_id = ?;", (self.user_id,))
            existing_titles = {row["titulo"] for row in cursor.fetchall()}
        finally:
            conn.close()

        created: list[RoadmapDetail] = []
        for tmpl in get_curated_templates():
            if tmpl.titulo not in existing_titles:
                try:
                    created.append(self.create_roadmap(tmpl))
                except permisos.AccionNoPermitida:
                    # Un tope de rutas: se devuelven las que se crearon; si no entró ninguna y la pidió la persona,
                    # se avisa cuál tope
                    if not created and not solo_la_primera_vez:
                        raise
                    break
        return created

    def get_roadmap(self, roadmap_id: int) -> RoadmapDetail | None:
        """Obtiene el detalle completo y jerárquico de una ruta (módulos, temas y clases)."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, titulo, descripcion, categoria, nivel_objetivo, enfoque_estudio, progreso_pct,
                       metadata_json, fecha_creacion, fecha_actualizacion
                FROM rutas_aprendizaje
                WHERE id = ? AND user_id = ?;
                """,
                (roadmap_id, self.user_id),
            )
            r_row = cursor.fetchone()
            if not r_row:
                return None

            # Cargar módulos
            cursor.execute(
                """
                SELECT id, ruta_id, titulo, descripcion, orden, fecha_creacion
                FROM ruta_modulos
                WHERE ruta_id = ?
                ORDER BY orden ASC, id ASC;
                """,
                (roadmap_id,),
            )
            mod_rows = cursor.fetchall()
            modules: list[RoadmapModule] = []
            total_temas = 0
            completados = 0

            for m_row in mod_rows:
                modulo_id = m_row["id"]
                cursor.execute(
                    """
                    SELECT t.id, t.modulo_id, t.titulo, t.descripcion, t.orden, t.estado, t.fuente,
                           t.fecha_creacion, t.fecha_actualizacion,
                           c.id as clase_id, c.titulo as clase_titulo, c.contenido_markdown,
                           c.diagramas_mermaid, c.flashcards_json, c.origen as clase_origen, c.vault_path
                    FROM ruta_temas t
                    LEFT JOIN ruta_clases c ON c.tema_id = t.id
                    WHERE t.modulo_id = ?
                    ORDER BY t.orden ASC, t.id ASC;
                    """,
                    (modulo_id,),
                )
                t_rows = cursor.fetchall()
                topics: list[RoadmapTopic] = []

                for tr in t_rows:
                    total_temas += 1
                    if tr["estado"] == "completado":
                        completados += 1

                    clase: RoadmapLesson | None = None
                    if tr["clase_id"]:
                        mermaid_list = json.loads(tr["diagramas_mermaid"]) if tr["diagramas_mermaid"] else []
                        cards_list = json.loads(tr["flashcards_json"]) if tr["flashcards_json"] else []
                        clase = RoadmapLesson(
                            id=tr["clase_id"],
                            tema_id=tr["id"],
                            titulo=tr["clase_titulo"],
                            contenido_markdown=tr["contenido_markdown"],
                            diagramas_mermaid=mermaid_list,
                            flashcards_json=cards_list,
                            origen=OrigenClase(tr["clase_origen"]) if tr["clase_origen"] else OrigenClase.GEMINI_IN_APP,
                            vault_path=tr["vault_path"],
                        )

                    topics.append(
                        RoadmapTopic(
                            id=tr["id"],
                            modulo_id=modulo_id,
                            titulo=tr["titulo"],
                            descripcion=tr["descripcion"],
                            orden=tr["orden"],
                            estado=EstadoTema(tr["estado"]),
                            fuente=FuenteTema(tr["fuente"]),
                            clase=clase,
                            fecha_creacion=tr["fecha_creacion"],
                            fecha_actualizacion=tr["fecha_actualizacion"],
                        )
                    )

                modules.append(
                    RoadmapModule(
                        id=modulo_id,
                        ruta_id=roadmap_id,
                        titulo=m_row["titulo"],
                        descripcion=m_row["descripcion"],
                        orden=m_row["orden"],
                        temas=topics,
                        fecha_creacion=m_row["fecha_creacion"],
                    )
                )

            meta = json.loads(r_row["metadata_json"]) if r_row["metadata_json"] else {}
            pct = round((completados / total_temas) * 100.0, 1) if total_temas > 0 else 0.0

            return RoadmapDetail(
                id=r_row["id"],
                titulo=r_row["titulo"],
                descripcion=r_row["descripcion"],
                categoria=r_row["categoria"],
                nivel_objetivo=r_row["nivel_objetivo"],
                enfoque_estudio=dict(r_row).get("enfoque_estudio") or "profesional",
                progreso_pct=pct,
                metadata_json=meta,
                total_temas=total_temas,
                temas_completados=completados,
                modulos=modules,
                fecha_creacion=r_row["fecha_creacion"],
                fecha_actualizacion=r_row["fecha_actualizacion"],
            )
        finally:
            conn.close()

    def get_roadmap_by_title(self, titulo: str) -> RoadmapDetail | None:
        """Busca una ruta por título exacto."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM rutas_aprendizaje WHERE titulo = ? AND user_id = ?;", (titulo, self.user_id)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self.get_roadmap(row["id"])
        finally:
            conn.close()

    def delete_roadmap(self, roadmap_id: int) -> bool:
        """Elimina una ruta y todos sus módulos/temas asociados."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM rutas_aprendizaje WHERE id = ? AND user_id = ?;", (roadmap_id, self.user_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def update_topic_status(self, topic_id: int, estado: EstadoTema | str) -> RoadmapTopic | None:
        """Actualiza el estado de un tema y recalcula de inmediato el progreso de la ruta."""
        estado_str = estado.value if hasattr(estado, "value") else str(estado)
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            if self._ruta_de_tema(conn, topic_id) is None:
                return None
            cursor.execute(
                """
                UPDATE ruta_temas
                SET estado = ?, fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (estado_str, topic_id),
            )
            if cursor.rowcount == 0:
                return None

            # Obtener el ruta_id para recalcular
            cursor.execute(
                """
                SELECT m.ruta_id, t.modulo_id, t.titulo, t.descripcion, t.orden, t.estado, t.fuente
                FROM ruta_temas t
                JOIN ruta_modulos m ON m.id = t.modulo_id
                WHERE t.id = ?;
                """,
                (topic_id,),
            )
            row = cursor.fetchone()
            if row:
                self._recalculate_progress(conn, row["ruta_id"])
                if estado_str == "completado":
                    try:
                        from aulento.roadmap.macro_fsrs import MacroFSRSRepository
                        MacroFSRSRepository(self.user_id, conn=conn).init_topic_retention(topic_id)
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"No se pudo inicializar Macro-FSRS para tema {topic_id}: {e}")

            conn.commit()

            return RoadmapTopic(
                id=topic_id,
                modulo_id=row["modulo_id"],
                titulo=row["titulo"],
                descripcion=row["descripcion"],
                orden=row["orden"],
                estado=EstadoTema(row["estado"]),
                fuente=FuenteTema(row["fuente"]),
            )
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_topic_with_context(self, topic_id: int) -> dict[str, Any] | None:
        """Obtiene un tema con el contexto de su módulo y ruta (para prompts).

        Incluye el enfoque de estudio, el `metadata_json` de la ruta ya decodificado y los
        títulos del tema anterior y siguiente en el orden módulo → tema.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    t.id as topic_id, t.titulo as topic_title, t.descripcion as topic_desc, t.estado as topic_status,
                    m.id as module_id, m.titulo as module_title,
                    r.id as roadmap_id, r.titulo as roadmap_title, r.categoria, r.nivel_objetivo,
                    r.enfoque_estudio, r.metadata_json
                FROM ruta_temas t
                JOIN ruta_modulos m ON m.id = t.modulo_id
                JOIN rutas_aprendizaje r ON r.id = m.ruta_id
                WHERE t.id = ? AND r.user_id = ?;
                """,
                (topic_id, self.user_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            ctx = dict(row)
            ctx["enfoque_estudio"] = ctx.get("enfoque_estudio") or "profesional"
            ctx["metadata_json"] = self._decode_metadata(ctx.get("metadata_json"))

            cursor.execute(
                """
                SELECT t.id, t.titulo
                FROM ruta_temas t
                JOIN ruta_modulos m ON m.id = t.modulo_id
                WHERE m.ruta_id = ?
                ORDER BY m.orden ASC, m.id ASC, t.orden ASC, t.id ASC;
                """,
                (ctx["roadmap_id"],),
            )
            ordenados = cursor.fetchall()
            posicion = next(i for i, fila in enumerate(ordenados) if fila["id"] == topic_id)
            ctx["prev_topic_title"] = ordenados[posicion - 1]["titulo"] if posicion > 0 else None
            ctx["next_topic_title"] = ordenados[posicion + 1]["titulo"] if posicion + 1 < len(ordenados) else None
            return ctx
        finally:
            conn.close()

    @staticmethod
    def _decode_metadata(raw: str | None) -> dict[str, Any]:
        try:
            meta = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            return {}
        return meta if isinstance(meta, dict) else {}

    def get_module_with_context(self, module_id: int) -> dict[str, Any] | None:
        """Obtiene un módulo con el contexto de su ruta, sus temas y los títulos de los demás módulos."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    m.id as module_id, m.titulo as module_title, m.descripcion as module_desc,
                    r.id as roadmap_id, r.titulo as roadmap_title, r.categoria, r.nivel_objetivo,
                    r.enfoque_estudio, r.metadata_json
                FROM ruta_modulos m
                JOIN rutas_aprendizaje r ON r.id = m.ruta_id
                WHERE m.id = ? AND r.user_id = ?;
                """,
                (module_id, self.user_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            ctx = dict(row)
            ctx["enfoque_estudio"] = ctx.get("enfoque_estudio") or "profesional"
            ctx["metadata_json"] = self._decode_metadata(ctx.get("metadata_json"))

            cursor.execute(
                "SELECT titulo FROM ruta_temas WHERE modulo_id = ? ORDER BY orden ASC, id ASC;",
                (module_id,),
            )
            ctx["topic_titles"] = [fila["titulo"] for fila in cursor.fetchall()]

            cursor.execute(
                "SELECT titulo FROM ruta_modulos WHERE ruta_id = ? AND id != ? ORDER BY orden ASC, id ASC;",
                (ctx["roadmap_id"], module_id),
            )
            ctx["other_module_titles"] = [fila["titulo"] for fila in cursor.fetchall()]
            return ctx
        finally:
            conn.close()

    def add_topics_to_module(self, module_id: int, temas: list[RoadmapTopicCreate]) -> list[RoadmapTopic]:
        """Agrega temas al final de un módulo, omitiendo títulos ya presentes (insensible a mayúsculas)."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            ruta_id = self._ruta_de_modulo(conn, module_id)
            if ruta_id is None:
                raise ValueError(f"Módulo con ID {module_id} no encontrado.")

            cursor.execute("SELECT titulo, orden FROM ruta_temas WHERE modulo_id = ?;", (module_id,))
            existentes = cursor.fetchall()
            titulos_presentes = {fila["titulo"].strip().lower() for fila in existentes}
            orden = max((fila["orden"] or 0 for fila in existentes), default=0)

            agregados: list[RoadmapTopic] = []
            for tema in temas:
                clave = tema.titulo.strip().lower()
                if clave in titulos_presentes:
                    continue
                titulos_presentes.add(clave)
                orden += 1
                cursor.execute(
                    """
                    INSERT INTO ruta_temas (modulo_id, titulo, descripcion, orden, estado, fuente)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (module_id, tema.titulo, tema.descripcion, orden, tema.estado.value, tema.fuente.value),
                )
                agregados.append(
                    RoadmapTopic(
                        id=cursor.lastrowid,
                        modulo_id=module_id,
                        titulo=tema.titulo,
                        descripcion=tema.descripcion,
                        orden=orden,
                        estado=tema.estado,
                        fuente=tema.fuente,
                    )
                )

            self._recalculate_progress(conn, ruta_id)
            conn.commit()
            return agregados
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def update_roadmap_metadata(self, roadmap_id: int, metadata: dict[str, Any]) -> bool:
        """Reemplaza el `metadata_json` de una ruta. Devuelve False si la ruta no existe."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE rutas_aprendizaje
                SET metadata_json = ?, fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?;
                """,
                (json.dumps(metadata or {}), roadmap_id, self.user_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def update_graph_settings(self, ruta_id: int, secuencia_implicita: bool) -> bool:
        """Guarda los ajustes del grafo en `metadata_json["grafo"]` sin tocar el resto del metadata.

        Devuelve False si la ruta no existe.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            actualizado = self._guardar_ajuste_de_secuencia(cursor, ruta_id, secuencia_implicita)
            conn.commit()
            return actualizado
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _guardar_ajuste_de_secuencia(self, cursor: sqlite3.Cursor, ruta_id: int, secuencia_implicita: bool) -> bool:
        """Lee y reescribe el metadata en la misma transacción. Un metadata que no sea un objeto se reemplaza."""
        cursor.execute(
            "SELECT metadata_json FROM rutas_aprendizaje WHERE id = ? AND user_id = ?;", (ruta_id, self.user_id)
        )
        row = cursor.fetchone()
        if not row:
            return False
        try:
            metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        except ValueError:
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        ajustes = metadata.get("grafo")
        metadata["grafo"] = {**(ajustes if isinstance(ajustes, dict) else {}), "secuencia_implicita": secuencia_implicita}
        cursor.execute(
            "UPDATE rutas_aprendizaje SET metadata_json = ?, fecha_actualizacion = CURRENT_TIMESTAMP "
            "WHERE id = ? AND user_id = ?;",
            (json.dumps(metadata), ruta_id, self.user_id),
        )
        return True

    def save_lesson(self, lesson: RoadmapLessonCreate) -> RoadmapLesson:
        """Guarda o actualiza la clase de un tema en SQLite."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            ruta_id = self._ruta_de_tema(conn, lesson.tema_id)
            if ruta_id is None:
                # Un tema de otra cuenta falla igual que uno que no existe
                raise sqlite3.IntegrityError("FOREIGN KEY constraint failed")
            diagramas_str = json.dumps(lesson.diagramas_mermaid or [])
            cards_str = json.dumps(lesson.flashcards_json or [])
            origen_str = lesson.origen.value if hasattr(lesson.origen, "value") else str(lesson.origen)

            # La clase que se reemplaza queda como versión (si el contenido cambia)
            cursor.execute(
                """
                SELECT titulo, contenido_markdown, diagramas_mermaid, flashcards_json, origen
                FROM ruta_clases WHERE tema_id = ?;
                """,
                (lesson.tema_id,),
            )
            vigente = cursor.fetchone()
            if vigente and (vigente["contenido_markdown"] or "") != (lesson.contenido_markdown or ""):
                cursor.execute(
                    """
                    INSERT INTO ruta_clases_versiones (tema_id, titulo, contenido_markdown, diagramas_mermaid, flashcards_json, origen)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (
                        lesson.tema_id,
                        vigente["titulo"],
                        vigente["contenido_markdown"],
                        vigente["diagramas_mermaid"],
                        vigente["flashcards_json"],
                        vigente["origen"],
                    ),
                )
                cursor.execute(
                    """
                    DELETE FROM ruta_clases_versiones
                    WHERE tema_id = ? AND id NOT IN (
                        SELECT id FROM ruta_clases_versiones WHERE tema_id = ? ORDER BY id DESC LIMIT ?
                    );
                    """,
                    (lesson.tema_id, lesson.tema_id, MAX_VERSIONES_POR_TEMA),
                )

            cursor.execute(
                """
                INSERT INTO ruta_clases (tema_id, titulo, contenido_markdown, diagramas_mermaid, flashcards_json, origen, vault_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tema_id) DO UPDATE SET
                    titulo = excluded.titulo,
                    contenido_markdown = excluded.contenido_markdown,
                    diagramas_mermaid = excluded.diagramas_mermaid,
                    flashcards_json = excluded.flashcards_json,
                    origen = excluded.origen,
                    vault_path = excluded.vault_path,
                    fecha_actualizacion = CURRENT_TIMESTAMP;
                """,
                (
                    lesson.tema_id,
                    lesson.titulo,
                    lesson.contenido_markdown,
                    diagramas_str,
                    cards_str,
                    origen_str,
                    lesson.vault_path,
                ),
            )
            # El id se lee siempre: tras un UPDATE, `lastrowid` es el de la última inserción de la
            # conexión (la versión recién guardada), no el de la clase
            cursor.execute("SELECT id FROM ruta_clases WHERE tema_id = ?;", (lesson.tema_id,))
            row = cursor.fetchone()
            lesson_id = row["id"] if row else 0

            # Marcar el tema como en_progreso o completado si tiene contenido
            cursor.execute(
                """
                UPDATE ruta_temas
                SET estado = 'completado', fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (lesson.tema_id,),
            )

            self._recalculate_progress(conn, ruta_id)

            conn.commit()

            return RoadmapLesson(
                id=lesson_id,
                tema_id=lesson.tema_id,
                titulo=lesson.titulo,
                contenido_markdown=lesson.contenido_markdown,
                diagramas_mermaid=lesson.diagramas_mermaid,
                flashcards_json=lesson.flashcards_json,
                origen=lesson.origen,
                vault_path=lesson.vault_path,
            )
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _version_de_fila(row: sqlite3.Row) -> RoadmapLessonVersion:
        return RoadmapLessonVersion(
            id=row["id"],
            tema_id=row["tema_id"],
            titulo=row["titulo"],
            contenido_markdown=row["contenido_markdown"],
            diagramas_mermaid=json.loads(row["diagramas_mermaid"]) if row["diagramas_mermaid"] else [],
            flashcards_json=json.loads(row["flashcards_json"]) if row["flashcards_json"] else [],
            origen=OrigenClase(row["origen"]) if row["origen"] else OrigenClase.GEMINI_IN_APP,
            fecha_version=row["fecha_version"],
        )

    def get_lesson_versions(self, topic_id: int) -> list[RoadmapLessonVersion]:
        """Versiones anteriores de la clase de un tema, de la más reciente a la más antigua."""
        conn = self._get_conn()
        try:
            if self._ruta_de_tema(conn, topic_id) is None:
                return []
            rows = conn.execute(
                "SELECT * FROM ruta_clases_versiones WHERE tema_id = ? ORDER BY id DESC;", (topic_id,)
            ).fetchall()
            return [self._version_de_fila(r) for r in rows]
        finally:
            conn.close()

    def restore_lesson_version(self, version_id: int) -> RoadmapLesson | None:
        """Vuelve a poner como vigente una versión anterior; la clase vigente queda a su vez como versión."""
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM ruta_clases_versiones WHERE id = ?;", (version_id,)).fetchone()
            if not row or self._ruta_de_tema(conn, row["tema_id"]) is None:
                return None
            version = self._version_de_fila(row)
            tema = conn.execute("SELECT estado FROM ruta_temas WHERE id = ?;", (version.tema_id,)).fetchone()
        finally:
            conn.close()

        restaurada = self.save_lesson(
            RoadmapLessonCreate(
                tema_id=version.tema_id,
                titulo=version.titulo,
                contenido_markdown=version.contenido_markdown,
                diagramas_mermaid=version.diagramas_mermaid,
                flashcards_json=version.flashcards_json,
                origen=version.origen,
            )
        )
        # Guardar una clase marca el tema como completado: restaurar no cambia su estado
        if tema and tema["estado"] != "completado":
            self.update_topic_status(version.tema_id, tema["estado"])
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM ruta_clases_versiones WHERE id = ?;", (version_id,))
            conn.commit()
        finally:
            conn.close()
        return restaurada

    def get_lesson_by_topic_id(self, topic_id: int) -> RoadmapLesson | None:
        """Obtiene la clase vinculada a un tema."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, tema_id, titulo, contenido_markdown, diagramas_mermaid, flashcards_json, origen, vault_path, fecha_creacion, fecha_actualizacion
                FROM ruta_clases
                WHERE tema_id = ?;
                """,
                (topic_id,),
            )
            row = cursor.fetchone()
            if not row or self._ruta_de_tema(conn, topic_id) is None:
                return None
            return RoadmapLesson(
                id=row["id"],
                tema_id=row["tema_id"],
                titulo=row["titulo"],
                contenido_markdown=row["contenido_markdown"],
                diagramas_mermaid=json.loads(row["diagramas_mermaid"]) if row["diagramas_mermaid"] else [],
                flashcards_json=json.loads(row["flashcards_json"]) if row["flashcards_json"] else [],
                origen=OrigenClase(row["origen"]) if row["origen"] else OrigenClase.GEMINI_IN_APP,
                vault_path=row["vault_path"],
                fecha_creacion=row["fecha_creacion"],
                fecha_actualizacion=row["fecha_actualizacion"],
            )
        finally:
            conn.close()

    def merge_gap_topics(
        self,
        roadmap_id: int,
        gap_topics: list[GapTopicItem],
        default_module_title: str = "Especialización & Brechas Detectadas",
    ) -> int:
        """Inserta los temas identificados en un PDF de syllabus en la ruta actual."""
        if not gap_topics:
            return 0

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            if not self._ruta_es_propia(conn, roadmap_id):
                # Una ruta de otra cuenta falla igual que una que no existe
                raise sqlite3.IntegrityError("FOREIGN KEY constraint failed")

            # Buscar o crear módulo de destino
            cursor.execute(
                """
                SELECT id FROM ruta_modulos
                WHERE ruta_id = ? AND titulo = ?;
                """,
                (roadmap_id, default_module_title),
            )
            mod_row = cursor.fetchone()
            if mod_row:
                modulo_id = mod_row["id"]
            else:
                cursor.execute(
                    "SELECT COALESCE(MAX(orden), 0) + 1 as next_orden FROM ruta_modulos WHERE ruta_id = ?;",
                    (roadmap_id,),
                )
                next_orden = cursor.fetchone()["next_orden"]
                cursor.execute(
                    """
                    INSERT INTO ruta_modulos (ruta_id, titulo, descripcion, orden)
                    VALUES (?, ?, 'Módulo generado automáticamente por Gap Analysis de syllabus externo.', ?);
                    """,
                    (roadmap_id, default_module_title, next_orden),
                )
                modulo_id = cursor.lastrowid

            # Obtener el orden máximo dentro del módulo
            cursor.execute(
                "SELECT COALESCE(MAX(orden), 0) as max_ord FROM ruta_temas WHERE modulo_id = ?;",
                (modulo_id,),
            )
            current_ord = cursor.fetchone()["max_ord"]

            inserted_count = 0
            for item in gap_topics:
                # Comprobar que no exista ya un tema con ese nombre en este módulo
                cursor.execute(
                    "SELECT id FROM ruta_temas WHERE modulo_id = ? AND LOWER(titulo) = LOWER(?);",
                    (modulo_id, item.titulo),
                )
                if cursor.fetchone():
                    continue

                current_ord += 1
                cursor.execute(
                    """
                    INSERT INTO ruta_temas (modulo_id, titulo, descripcion, orden, estado, fuente)
                    VALUES (?, ?, ?, ?, 'pendiente', 'pdf_gap');
                    """,
                    (modulo_id, item.titulo, item.descripcion, current_ord),
                )
                inserted_count += 1

            self._recalculate_progress(conn, roadmap_id)
            conn.commit()
            return inserted_count
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ==========================================
    # PRELACIONES Y PRERREQUISITOS (DAG)
    # ==========================================

    def add_prerequisite(
        self,
        ruta_id: int,
        tema_origen_id: int,
        tema_destino_id: int,
        tipo: str = "estricta",
    ) -> dict[str, Any]:
        """Registra una dependencia o prelación entre temas: tema_origen_id prela a tema_destino_id.

        Lanza `ValueError` si algún tema no pertenece a la ruta o si origen y destino coinciden, y
        `PrerequisiteCycleError` si cerraría un ciclo. Si la prelación ya existe, actualiza su tipo.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            temas, guardadas = self._contexto_de_prelaciones(cursor, ruta_id)
            self._upsert_prerequisite_validado(
                cursor, ruta_id, temas, guardadas, tema_origen_id, tema_destino_id, tipo
            )
            cursor.execute(
                "SELECT id FROM ruta_prelaciones WHERE tema_origen_id = ? AND tema_destino_id = ?;",
                (tema_origen_id, tema_destino_id),
            )
            prel_id = cursor.fetchone()["id"]
            conn.commit()
            return {
                "id": prel_id,
                "ruta_id": ruta_id,
                "tema_origen_id": tema_origen_id,
                "tema_destino_id": tema_destino_id,
                "tipo": tipo,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def add_prerequisites_bulk(
        self,
        ruta_id: int,
        prelaciones: Sequence[PrerequisiteCreate],
        secuencia_implicita: bool | None = None,
    ) -> int:
        """Guarda un conjunto de prelaciones en una sola transacción y devuelve cuántas se procesaron.

        Cada una se valida como en `add_prerequisite`, contra las guardadas más las anteriores del
        lote. Si alguna es inválida se lanza la excepción y no se guarda ninguna. Si viene
        `secuencia_implicita`, el ajuste del grafo se guarda en la misma transacción.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            temas, guardadas = self._contexto_de_prelaciones(cursor, ruta_id)
            for prelacion in prelaciones:
                self._upsert_prerequisite_validado(
                    cursor,
                    ruta_id,
                    temas,
                    guardadas,
                    prelacion.tema_origen_id,
                    prelacion.tema_destino_id,
                    prelacion.tipo,
                )
            if secuencia_implicita is not None:
                self._guardar_ajuste_de_secuencia(cursor, ruta_id, secuencia_implicita)
            conn.commit()
            return len(prelaciones)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _contexto_de_prelaciones(self, cursor: sqlite3.Cursor, ruta_id: int) -> tuple[set[int], list[tuple[int, int]]]:
        """Ids de los temas de la ruta y pares (origen, destino) de sus prelaciones guardadas.

        Los temas salen de la propia ruta: una prelación con un tema de otra ruta, o de otra cuenta, se rechaza.
        """
        cursor.execute("SELECT 1 FROM rutas_aprendizaje WHERE id = ? AND user_id = ?;", (ruta_id, self.user_id))
        if not cursor.fetchone():
            raise RoadmapNotFoundError(f"Ruta con ID {ruta_id} no encontrada.")
        cursor.execute(
            """
            SELECT t.id FROM ruta_temas t
            JOIN ruta_modulos m ON m.id = t.modulo_id
            WHERE m.ruta_id = ?;
            """,
            (ruta_id,),
        )
        temas = {row["id"] for row in cursor.fetchall()}
        cursor.execute(
            "SELECT tema_origen_id, tema_destino_id FROM ruta_prelaciones WHERE ruta_id = ? ORDER BY id ASC;",
            (ruta_id,),
        )
        guardadas = [(row["tema_origen_id"], row["tema_destino_id"]) for row in cursor.fetchall()]
        return temas, guardadas

    @staticmethod
    def _upsert_prerequisite_validado(
        cursor: sqlite3.Cursor,
        ruta_id: int,
        temas_de_la_ruta: set[int],
        guardadas: list[tuple[int, int]],
        tema_origen_id: int,
        tema_destino_id: int,
        tipo: str,
    ) -> None:
        """Valida una prelación contra `guardadas` y la inserta, o actualiza su tipo si ya existe.

        Agrega la arista nueva a `guardadas`, para que un lote valide cada una contra las anteriores.
        """
        from aulento.roadmap.graph_engine import detecta_ciclo

        if tipo not in TIPOS_DE_PRELACION:
            raise ValueError(f"Tipo de prelación desconocido: '{tipo}'.")
        if tema_origen_id == tema_destino_id:
            raise ValueError("Un tema no puede ser prerrequisito de sí mismo.")
        for tema_id in (tema_origen_id, tema_destino_id):
            if tema_id not in temas_de_la_ruta:
                raise ValueError(f"El tema con ID {tema_id} no pertenece a la ruta {ruta_id}.")

        arista = (tema_origen_id, tema_destino_id)
        if arista not in guardadas:
            if detecta_ciclo(guardadas, tema_origen_id, tema_destino_id):
                raise PrerequisiteCycleError(
                    f"La prelación del tema {tema_origen_id} al tema {tema_destino_id} cerraría un ciclo "
                    "con las prelaciones guardadas."
                )
            guardadas.append(arista)

        cursor.execute(
            """
            INSERT INTO ruta_prelaciones (ruta_id, tema_origen_id, tema_destino_id, tipo)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(tema_origen_id, tema_destino_id) DO UPDATE SET tipo = excluded.tipo;
            """,
            (ruta_id, tema_origen_id, tema_destino_id, tipo),
        )

    def delete_prerequisite(self, ruta_id: int, tema_origen_id: int, tema_destino_id: int) -> bool:
        """Elimina una prelación entre temas."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM ruta_prelaciones
                WHERE ruta_id = ? AND tema_origen_id = ? AND tema_destino_id = ?
                  AND ruta_id IN (SELECT id FROM rutas_aprendizaje WHERE user_id = ?);
                """,
                (ruta_id, tema_origen_id, tema_destino_id, self.user_id),
            )
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted
        finally:
            conn.close()

    def get_prerequisites(self, ruta_id: int) -> list[PrerequisiteEdge]:
        """Obtiene todas las prelaciones explícitas de una ruta con los títulos de los temas."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT p.id, p.ruta_id, p.tema_origen_id, p.tema_destino_id, p.tipo,
                       t1.titulo as origen_titulo, t2.titulo as destino_titulo
                FROM ruta_prelaciones p
                JOIN ruta_temas t1 ON t1.id = p.tema_origen_id
                JOIN ruta_temas t2 ON t2.id = p.tema_destino_id
                JOIN rutas_aprendizaje r ON r.id = p.ruta_id
                WHERE p.ruta_id = ? AND r.user_id = ?
                ORDER BY p.id ASC;
                """,
                (ruta_id, self.user_id),
            )
            rows = cursor.fetchall()
            return [
                PrerequisiteEdge(
                    id=row["id"],
                    ruta_id=row["ruta_id"],
                    tema_origen_id=row["tema_origen_id"],
                    tema_destino_id=row["tema_destino_id"],
                    tipo=row["tipo"],
                    origen_titulo=row["origen_titulo"],
                    destino_titulo=row["destino_titulo"],
                )
                for row in rows
            ]
        finally:
            conn.close()

    # ==========================================
    # REGISTRO Y ANALÍTICA DE TOKENS Y COSTOS
    # ==========================================

    def log_api_usage(
        self,
        model: str,
        endpoint_tipo: str,
        api_tier: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        estimated_cost_usd: float | None,
        status_code: int = 200,
        latency_ms: float = 0.0,
        provider: str = "gemini",
    ) -> int:
        """Registra una llamada a un proveedor de IA: proveedor, modelo, tokens, latencia y costo.

        `estimated_cost_usd` va en `None` cuando no se conoce la tarifa del modelo: queda vacío, no en cero.
        """
        conn = self._get_conn()
        try:
            return registrar_consumo_de_ia(
                conn,
                self.user_id,
                provider=provider,
                model=model,
                endpoint_tipo=endpoint_tipo,
                api_tier=api_tier,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                estimated_cost_usd=estimated_cost_usd,
                status_code=status_code,
                latency_ms=latency_ms,
            )
        finally:
            conn.close()

    def get_token_usage_summary(self, days: int = 30) -> TokenUsageSummary:
        """Agrega el consumo de tokens y costos por modelo, endpoint y tier en los últimos N días."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            # Totales globales
            cursor.execute(
                """
                SELECT 
                    COUNT(id) as total_requests,
                    COALESCE(SUM(prompt_tokens), 0) as total_prompt,
                    COALESCE(SUM(completion_tokens), 0) as total_comp,
                    COALESCE(SUM(total_tokens), 0) as total_tok,
                    COALESCE(SUM(estimated_cost_usd), 0.0) as total_cost
                FROM api_usage_logs
                WHERE user_id = ? AND timestamp >= datetime('now', ? || ' days');
                """,
                (self.user_id, f"-{days}"),
            )
            tot_row = cursor.fetchone()
            total_requests = tot_row["total_requests"] if tot_row and tot_row["total_requests"] else 0
            total_prompt = tot_row["total_prompt"] if tot_row and tot_row["total_prompt"] else 0
            total_comp = tot_row["total_comp"] if tot_row and tot_row["total_comp"] else 0
            total_tok = tot_row["total_tok"] if tot_row and tot_row["total_tok"] else 0
            total_cost = round(float(tot_row["total_cost"] or 0.0), 5) if tot_row else 0.0

            # Desglose por modelo
            cursor.execute(
                """
                SELECT model, COUNT(id) as reqs, SUM(total_tokens) as tokens, SUM(estimated_cost_usd) as cost
                FROM api_usage_logs
                WHERE user_id = ? AND timestamp >= datetime('now', ? || ' days')
                GROUP BY model;
                """,
                (self.user_id, f"-{days}"),
            )
            by_model = {
                r["model"]: {
                    "requests": r["reqs"],
                    "tokens": r["tokens"] or 0,
                    "cost_usd": round(float(r["cost"] or 0.0), 5),
                }
                for r in cursor.fetchall()
            }

            # Desglose por endpoint
            cursor.execute(
                """
                SELECT endpoint_tipo, COUNT(id) as reqs, SUM(total_tokens) as tokens, SUM(estimated_cost_usd) as cost
                FROM api_usage_logs
                WHERE user_id = ? AND timestamp >= datetime('now', ? || ' days')
                GROUP BY endpoint_tipo;
                """,
                (self.user_id, f"-{days}"),
            )
            by_endpoint = {
                r["endpoint_tipo"]: {
                    "requests": r["reqs"],
                    "tokens": r["tokens"] or 0,
                    "cost_usd": round(float(r["cost"] or 0.0), 5),
                }
                for r in cursor.fetchall()
            }

            # Desglose por tier
            cursor.execute(
                """
                SELECT api_tier, COUNT(id) as reqs, SUM(total_tokens) as tokens, SUM(estimated_cost_usd) as cost
                FROM api_usage_logs
                WHERE user_id = ? AND timestamp >= datetime('now', ? || ' days')
                GROUP BY api_tier;
                """,
                (self.user_id, f"-{days}"),
            )
            by_tier = {
                r["api_tier"]: {
                    "requests": r["reqs"],
                    "tokens": r["tokens"] or 0,
                    "cost_usd": round(float(r["cost"] or 0.0), 5),
                }
                for r in cursor.fetchall()
            }

            # Últimos 15 logs
            cursor.execute(
                """
                SELECT id, timestamp, provider, model, endpoint_tipo, api_tier,
                       prompt_tokens, completion_tokens, total_tokens, estimated_cost_usd,
                       status_code, latency_ms
                FROM api_usage_logs
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT 15;
                """,
                (self.user_id,),
            )
            recent_rows = cursor.fetchall()
            recent_logs = [
                TokenLogItem(
                    id=r["id"],
                    timestamp=r["timestamp"],
                    provider=r["provider"],
                    model=r["model"],
                    endpoint_tipo=r["endpoint_tipo"],
                    api_tier=r["api_tier"],
                    prompt_tokens=r["prompt_tokens"] or 0,
                    completion_tokens=r["completion_tokens"] or 0,
                    total_tokens=r["total_tokens"] or 0,
                    estimated_cost_usd=round(float(r["estimated_cost_usd"] or 0.0), 5),
                    status_code=r["status_code"] or 200,
                    latency_ms=round(float(r["latency_ms"] or 0.0), 1),
                )
                for r in recent_rows
            ]

            return TokenUsageSummary(
                total_requests=total_requests,
                total_prompt_tokens=total_prompt,
                total_completion_tokens=total_comp,
                total_tokens=total_tok,
                total_estimated_cost_usd=total_cost,
                by_model=by_model,
                by_endpoint=by_endpoint,
                by_tier=by_tier,
                recent_logs=recent_logs,
            )
        finally:
            conn.close()

    def get_recent_api_logs(self, limit: int = 50) -> list[TokenLogItem]:
        """Retorna los registros de consumo de API más recientes."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, timestamp, provider, model, endpoint_tipo, api_tier,
                       prompt_tokens, completion_tokens, total_tokens, estimated_cost_usd,
                       status_code, latency_ms
                FROM api_usage_logs
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?;
                """,
                (self.user_id, limit),
            )
            rows = cursor.fetchall()
            return [
                TokenLogItem(
                    id=r["id"],
                    timestamp=r["timestamp"],
                    provider=r["provider"],
                    model=r["model"],
                    endpoint_tipo=r["endpoint_tipo"],
                    api_tier=r["api_tier"],
                    prompt_tokens=r["prompt_tokens"] or 0,
                    completion_tokens=r["completion_tokens"] or 0,
                    total_tokens=r["total_tokens"] or 0,
                    estimated_cost_usd=round(float(r["estimated_cost_usd"] or 0.0), 5),
                    status_code=r["status_code"] or 200,
                    latency_ms=round(float(r["latency_ms"] or 0.0), 1),
                )
                for r in rows
            ]
        finally:
            conn.close()
