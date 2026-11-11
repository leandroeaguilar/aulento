"""Estudio de generación, importación y exportación bimodal de Clases (FSRS v5 y Obsidian Vault)."""

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from aulento.core.ia.lectura import respuesta_inutil
from aulento.core.ia.pasarela import PasarelaDeIA
from aulento.core.ia.tipos import IANoDisponibleError, Pedido, motivo_sin_ia
from aulento.db.connection import get_connection
from aulento.db.cuenta import exigir_repositorio_de_cuenta
from aulento.db.roadmap_repository import RoadmapRepository
from aulento.models.roadmap import (
    LessonPromptRequest,
    OrigenClase,
    PerfilPedagogico,
    RoadmapLesson,
    RoadmapLessonCreate,
)
from aulento.roadmap.lesson_parser import LessonParser
from aulento.roadmap.pedagogical_profiles import perfil_de_ruta, una_linea
from aulento.roadmap.prompt_builder import LessonPromptBuilder
from aulento.roadmap.system_prompt_manager import SystemPromptManager
from aulento.vault.rutas import RutaFueraDelVaultError, resolver_en_vault

logger = logging.getLogger(__name__)


def nombre_seguro(nombre: str) -> str:
    """Nombre de carpeta o archivo sin separadores ni caracteres reservados; nunca vacío ni solo puntos."""
    limpio = re.sub(r'[\\/*?:"<>|\x00-\x1f]', "", nombre or "").strip().rstrip(". ")
    return limpio or "Sin título"


def _sin_fecha_de_generacion(texto: str) -> str:
    """Contenido de una nota sin las líneas `at:` y `by:` del frontmatter, sin líneas en blanco ni diferencias de fin de línea.

    El `by:` se ignora porque cambió con la marca (`process:study-engine` → `process:aulento`, ADR 021): una nota
    exportada antes no es una edición a mano.
    """
    lineas = texto.replace("\r", "\n").split("\n")
    return "\n".join(ln.rstrip() for ln in lineas if ln.strip() and not re.fullmatch(r"\s+(at|by): \S+", ln))


TIMEOUT_GENERACION_CLASE = 120.0


class ClaseNoGeneradaError(RuntimeError):
    """La IA no devolvió una clase y el tema ya tiene una: no se reemplaza por la plantilla de reserva."""


def _huella_de_nota(texto: str) -> str:
    """Huella del contenido de una nota, estable ante la fecha de generación y los fines de línea."""
    return hashlib.sha256(_sin_fecha_de_generacion(texto).encode("utf-8")).hexdigest()


_CAMINOS_PARA_LA_CLASE_COMPLETA = (
    "> - **Con tu clave de API** (Gemini, Claude u OpenAI): cargala en Configuración y la app genera la clase sola.\n"
    "> - **Con tu asistente por MCP** (Claude Desktop, Claude Code u otro cliente MCP): creá un token con "
    "`aulento mcp token create` y conectalo; el asistente escribe la clase con tu suscripción, sin clave de API.\n"
    "> - **A mano:** copiá el **[📋 Prompt Maestro]**, pegalo en Gemini, Claude o NotebookLM e importá la respuesta.\n"
)


def banner_de_reserva(motivo: str | None, cuenta_compartida: bool = False) -> str:
    """Aviso al pie del título de una clase de reserva: por qué no hubo IA y cómo obtener la clase completa.

    Tres casos: una cuenta compartida (no tiene IA y no se le puede cargar), una cuenta sin clave (`motivo` None,
    como lo define `motivo_sin_ia`) y una IA que no respondió (con su `motivo`: cuota, clave rechazada, conexión).
    """
    plantilla = "Esta es la plantilla que arma el motor local, sin IA: trae la estructura de la clase, no su contenido.\n"
    # La cuenta compartida sin clave tiene su propio aviso; si tiene clave y la IA falló, vale el motivo real
    if cuenta_compartida and motivo is None:
        return (
            "> [!warning] Generación en Modo Reserva Local: estás en una cuenta compartida\n"
            f"> {plantilla}"
            "> Esta cuenta la comparten varias personas y no tiene IA. **Para generar la clase completa necesitás tu propia cuenta "
            "de Aulento**, con una de estas opciones:\n"
            + _CAMINOS_PARA_LA_CLASE_COMPLETA
        )
    if motivo is None:
        return (
            "> [!warning] Generación en Modo Reserva Local: no hay clave de IA cargada\n"
            f"> {plantilla}"
            "> Para generar la clase completa:\n"
            + _CAMINOS_PARA_LA_CLASE_COMPLETA
        )
    return (
        "> [!warning] Generación en Modo Reserva Local: la IA no respondió\n"
        f"> **Motivo:** {una_linea(motivo)}\n"
        f"> {plantilla}"
        "> Podés volver a generarla más tarde, o:\n"
        + _CAMINOS_PARA_LA_CLASE_COMPLETA
    )


class LessonStudio:
    """Gestor integral para generar, importar y sincronizar clases con FSRS y Obsidian.

    Opera sobre la cuenta del repositorio que recibe (`repo.user_id`) y escribe las notas en el vault de
    esa cuenta; `vault_path` lo reemplaza por una carpeta dada.
    """

    def __init__(
        self,
        repo: RoadmapRepository,
        vault_path: Path | str | None = None,
        cuenta_compartida: bool = False,
    ) -> None:
        exigir_repositorio_de_cuenta(repo)
        self.repo = repo
        # Una cuenta compartida no tiene IA: su plantilla de reserva explica cómo generar la clase en una cuenta propia
        self.cuenta_compartida = cuenta_compartida
        self.pasarela = PasarelaDeIA.de_repositorio(repo)
        self.prompts = SystemPromptManager.de_repositorio(repo)
        self.vault_path = Path(vault_path) if vault_path else None
        self.last_backup_path: str | None = None
        # Lo mismo que devuelve la última exportación, relativo al vault: es lo que se le informa a la cuenta
        self.last_relative_path: str | None = None
        self.last_backup_relative_path: str | None = None

    def generate_lesson_in_app(
        self, topic_id: int, options: LessonPromptRequest | None = None
    ) -> RoadmapLesson:
        """Genera una clase pedagógica con la IA de la cuenta usando el Prompt Maestro.

        Respeta las opciones de contenido recibidas, pero la generación in-app nunca pide
        búsquedas (el modelo no tiene herramientas) y siempre pide las flashcards FSRS.
        Sin IA utilizable guarda la plantilla de reserva (que dice el motivo cuando no es la falta de clave)
        o, si el tema ya tiene una clase, levanta `ClaseNoGeneradaError` y la conserva.
        """
        ctx = self.repo.get_topic_with_context(topic_id)
        if not ctx:
            raise ValueError(f"Tema con ID {topic_id} no encontrado.")

        topic_title = ctx["topic_title"]
        roadmap_title = ctx["roadmap_title"]

        builder = LessonPromptBuilder(repo=self.repo)
        req = (options or LessonPromptRequest()).model_copy(
            update={"target_llm": "gemini", "sin_herramientas": True, "include_fsrs_cards": True}
        )
        prompt_res = builder.build_prompt(topic_id, req)

        markdown_output = None
        motivo: str | None = None
        try:
            respuesta = self.pasarela.generar(
                Pedido(
                    sistema=self.prompts.get_lesson_system_prompt(),
                    usuario=prompt_res.master_prompt,
                    timeout=TIMEOUT_GENERACION_CLASE,
                    temperatura=0.3,
                ),
                "lesson_gen",
                self.repo,
            )
        except IANoDisponibleError as error:
            motivo = motivo_sin_ia(error)
        else:
            markdown_output = respuesta.texto
            if not markdown_output:
                motivo = str(respuesta_inutil(respuesta, "devolvió una clase vacía"))

        if not markdown_output:
            if self.repo.get_lesson_by_topic_id(topic_id):
                if self.cuenta_compartida and motivo is None:
                    causa = (
                        "Estás en una cuenta compartida, que no tiene IA: no se puede generar una clase nueva. "
                        "Para generar clases necesitás tu propia cuenta, con tu clave de API o tu asistente conectado por MCP."
                    )
                elif motivo is None:
                    causa = "No hay clave de IA cargada: cargala en Configuración o conectá tu asistente por MCP."
                else:
                    causa = motivo
                raise ClaseNoGeneradaError(causa + " Se conservó la clase que el tema ya tenía.")
            perfil = perfil_de_ruta(ctx.get("metadata_json"), ctx.get("categoria"), roadmap_title)
            markdown_output = self._build_reserve_lesson(
                topic_title, ctx["module_title"], roadmap_title, perfil, motivo, cuenta_compartida=self.cuenta_compartida
            )

        parsed = LessonParser.parse_markdown(markdown_output, default_title=topic_title)

        lesson_create = RoadmapLessonCreate(
            tema_id=topic_id,
            titulo=parsed["title"],
            contenido_markdown=parsed["markdown_content"],
            diagramas_mermaid=parsed["diagramas_mermaid"],
            flashcards_json=parsed["flashcards"],
            origen=OrigenClase.GEMINI_IN_APP,
        )
        return self.repo.save_lesson(lesson_create)

    @staticmethod
    def _build_reserve_lesson(
        topic_title: str,
        module_title: str,
        roadmap_title: str,
        perfil: PerfilPedagogico,
        motivo: str | None = None,
        cuenta_compartida: bool = False,
    ) -> str:
        """Arma la plantilla local de reserva con las secciones del perfil pedagógico de la ruta.

        No contiene contenido generado: es un esqueleto con la consigna de cada sección, el banner
        de aviso y un bloque `cards-fsrs` válido derivado de datos reales de la ruta. `motivo`, si se
        pasa, es por qué no hubo IA y queda en el banner.
        """

        titulos = [una_linea(sec.titulo) for sec in perfil.secciones]
        partes = [f"# {topic_title}\n", banner_de_reserva(motivo, cuenta_compartida)]

        for idx, seccion in enumerate(perfil.secciones, start=1):
            partes.append(
                f"### {idx}. {titulos[idx - 1]}\n"
                f"*Pendiente de desarrollar. Consigna de esta sección:*\n{seccion.instruccion.strip()}\n"
            )

        if perfil.usa_diagramas:
            nodos = "\n".join(
                f'    Tema --> S{idx}["{idx}. {titulo.replace(chr(34), chr(39))}"]' for idx, titulo in enumerate(titulos, start=1)
            )
            partes.append(
                "### Mapa de la clase\n"
                "```mermaid\n"
                "graph TD\n"
                f'    Tema["{una_linea(topic_title).replace(chr(34), chr(39))}"]\n'
                f"{nodos}\n"
                "```\n"
            )

        partes.append(
            "```cards-fsrs\n"
            f"Q: ¿Qué aspectos hay que cubrir al estudiar «{una_linea(topic_title)}» ({una_linea(perfil.disciplina)})?\n"
            f"A: {'; '.join(titulos)}.\n\n"
            f"Q: ¿En qué módulo y ruta de aprendizaje se ubica «{una_linea(topic_title)}»?\n"
            f"A: En el módulo «{una_linea(module_title)}» de la ruta «{una_linea(roadmap_title)}».\n"
            "```\n"
        )
        return "\n".join(partes)

    def import_external_lesson(
        self,
        topic_id: int,
        markdown_text: str,
        origen: OrigenClase = OrigenClase.NOTEBOOKLM,
    ) -> RoadmapLesson:
        """Importa el resultado de NotebookLM, Claude con MCP o ChatGPT."""
        ctx = self.repo.get_topic_with_context(topic_id)
        default_title = ctx["topic_title"] if ctx else "Clase Magistral"

        parsed = LessonParser.parse_markdown(markdown_text, default_title=default_title)

        lesson_create = RoadmapLessonCreate(
            tema_id=topic_id,
            titulo=parsed["title"],
            contenido_markdown=parsed["markdown_content"],
            diagramas_mermaid=parsed["diagramas_mermaid"],
            flashcards_json=parsed["flashcards"],
            origen=origen,
        )
        return self.repo.save_lesson(lesson_create)

    def export_flashcards_to_fsrs(self, lesson_id: int) -> int:
        """Inyecta con 1 clic las flashcards de una clase a la tabla fsrs_items."""
        conn = get_connection(self.repo.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT c.flashcards_json, t.titulo as topic_title, r.id as roadmap_id, r.titulo as roadmap_title
                FROM ruta_clases c
                JOIN ruta_temas t ON t.id = c.tema_id
                JOIN ruta_modulos m ON m.id = t.modulo_id
                JOIN rutas_aprendizaje r ON r.id = m.ruta_id
                WHERE c.id = ? AND r.user_id = ?;
                """,
                (lesson_id, self.repo.user_id),
            )
            row = cursor.fetchone()
            if not row or not row["flashcards_json"]:
                return 0

            cards = json.loads(row["flashcards_json"])
            categoria = f"roadmap_{row['roadmap_id']}"
            contexto = f"Clase: {row['topic_title']} ({row['roadmap_title']})"
            now_iso = datetime.now(UTC).isoformat()

            inserted = 0
            for card in cards:
                q = card.get("pregunta", "").strip()
                a = card.get("respuesta", "").strip()
                if not q or not a:
                    continue

                cursor.execute(
                    """
                    INSERT INTO fsrs_items (user_id, categoria, item_pregunta, respuesta_esperada, contexto_uso, state, step, due)
                    VALUES (?, ?, ?, ?, ?, 1, 0, ?)
                    ON CONFLICT(user_id, categoria, item_pregunta) DO UPDATE SET
                        respuesta_esperada = excluded.respuesta_esperada,
                        contexto_uso = excluded.contexto_uso;
                    """,
                    (self.repo.user_id, categoria, q, a, contexto, now_iso),
                )
                inserted += 1

            conn.commit()
            return inserted
        finally:
            conn.close()

    def _fila_de_nota(self, conn, lesson_id: int):
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT c.id, c.titulo as class_title, c.contenido_markdown, c.vault_hash,
                   t.titulo as topic_title, m.titulo as module_title, r.titulo as roadmap_title
            FROM ruta_clases c
            JOIN ruta_temas t ON t.id = c.tema_id
            JOIN ruta_modulos m ON m.id = t.modulo_id
            JOIN rutas_aprendizaje r ON r.id = m.ruta_id
            WHERE c.id = ? AND r.user_id = ?;
            """,
            (lesson_id, self.repo.user_id),
        )
        return cursor.fetchone()

    def _destino_en_vault(self, row) -> tuple[Path, str]:
        """Archivo de la nota y su ruta relativa al vault, validados antes de escribir nada.

        Levanta `RutaFueraDelVaultError` si quedaría fuera de la carpeta de cursos del vault de la cuenta.
        """
        folder_name = nombre_seguro(row["roadmap_title"])
        file_name = nombre_seguro(row["topic_title"]) + ".md"
        rel_path = f"04 Knowledge/Cursos/{folder_name}/{file_name}"

        cursos = resolver_en_vault(self._vault_de_la_cuenta(), "04 Knowledge/Cursos")
        target_file = (cursos / folder_name / file_name).resolve()
        if target_file.parent.parent != cursos:
            raise RutaFueraDelVaultError(
                f"La nota de la clase quedaría fuera de la carpeta de cursos del vault: {rel_path}"
            )
        return target_file, rel_path

    def _vault_de_la_cuenta(self) -> Path:
        """Carpeta dada al construir (se crea) o el vault de la cuenta del repositorio."""
        if self.vault_path is not None:
            self.vault_path.mkdir(parents=True, exist_ok=True)
            return self.vault_path
        from aulento.vault.rutas import vault_de_la_cuenta_con_conexion_propia

        return vault_de_la_cuenta_con_conexion_propia(self.repo.user_id, self.repo.db_path)

    @staticmethod
    def _contenido_de_nota(row) -> str:
        return LessonParser.build_vault_note_content(
            title=row["class_title"],
            topic_title=row["topic_title"],
            module_title=row["module_title"],
            roadmap_title=row["roadmap_title"],
            markdown_body=(row["contenido_markdown"] or "").replace("\r\n", "\n").replace("\r", "\n"),
        )

    def clase_existe(self, lesson_id: int) -> bool:
        """Indica si la clase existe y cuelga de una ruta de la cuenta."""
        conn = get_connection(self.repo.db_path)
        try:
            return self._fila_de_nota(conn, lesson_id) is not None
        finally:
            conn.close()

    def vault_note_was_edited(self, lesson_id: int) -> bool:
        """Indica si en el destino de la nota de una clase hay un archivo distinto del que el sistema
        generaría para ella: apuntes a mano, o la nota de otro tema con el mismo nombre."""
        conn = get_connection(self.repo.db_path)
        try:
            row = self._fila_de_nota(conn, lesson_id)
        finally:
            conn.close()
        if not row:
            return False
        target_file, _ = self._destino_en_vault(row)
        return self._nota_ajena(row, target_file)

    def _nota_ajena(self, row, target_file: Path) -> bool:
        """El archivo del destino existe y no es el último que el sistema escribió para esta clase."""
        if not target_file.is_file():
            return False
        en_disco = target_file.read_text(encoding="utf-8", errors="replace")
        if row["vault_hash"]:
            return _huella_de_nota(en_disco) != row["vault_hash"]
        # Notas escritas antes de guardar la huella: se comparan con la que generaría la clase vigente
        return _sin_fecha_de_generacion(en_disco) != _sin_fecha_de_generacion(self._contenido_de_nota(row))

    def export_lesson_to_vault(self, lesson_id: int, backup_existing: bool | None = None) -> str:
        """Guarda la clase como un apunte canónico en el Vault de Obsidian respetando el SOP Cursos.

        Si en el destino hay un archivo que el sistema no escribió para esta clase (apuntes a mano,
        una nota propia, otro tema con el mismo nombre), se copia a un archivo de respaldo en la misma
        carpeta antes de reescribirlo; su ruta queda en `last_backup_path`. `backup_existing` fuerza
        (True) o impide (False) ese respaldo; con None se decide por la huella guardada.

        Devuelve la ruta del archivo en el disco del servidor. Lo que se le muestra a la cuenta son las
        rutas relativas al vault: `last_relative_path` y `last_backup_relative_path`.
        """
        self.last_backup_path = None
        self.last_relative_path = None
        self.last_backup_relative_path = None
        conn = get_connection(self.repo.db_path)
        try:
            row = self._fila_de_nota(conn, lesson_id)
            if not row:
                raise ValueError(f"Clase con ID {lesson_id} no encontrada.")

            target_file, rel_path = self._destino_en_vault(row)
            target_file.parent.mkdir(parents=True, exist_ok=True)

            if backup_existing is None:
                backup_existing = self._nota_ajena(row, target_file)
            if backup_existing and target_file.is_file():
                marca = datetime.now().strftime("%Y-%m-%d %H%M%S")
                respaldo = target_file.with_name(f"{target_file.stem} (respaldo {marca}).md")
                n = 2
                while respaldo.exists():
                    respaldo = target_file.with_name(f"{target_file.stem} (respaldo {marca} {n}).md")
                    n += 1
                respaldo.write_bytes(target_file.read_bytes())
                self.last_backup_path = str(respaldo)
                self.last_backup_relative_path = f"{rel_path.rsplit('/', 1)[0]}/{respaldo.name}"

            contenido = self._contenido_de_nota(row)
            target_file.write_text(contenido, encoding="utf-8")

            conn.execute(
                "UPDATE ruta_clases SET vault_path = ?, vault_hash = ? WHERE id = ?;",
                (rel_path, _huella_de_nota(contenido), lesson_id),
            )
            conn.commit()

            self.last_relative_path = rel_path
            return str(target_file)
        finally:
            conn.close()
