"""Motor de generación y evolución de Rutas de Aprendizaje con la IA de la cuenta."""

import logging
from typing import Any

from aulento.db.cuenta import exigir_repositorio_de_cuenta
from aulento.core.ia.lectura import leer_json, leer_json_de, respuesta_inutil
from aulento.core.ia.pasarela import PasarelaDeIA
from aulento.core.ia.tipos import IANoDisponibleError, Pedido, motivo_sin_ia
from aulento.db.roadmap_repository import RoadmapRepository
from aulento.models.roadmap import (
    AlcanceRuta,
    RoadmapCreate,
    RoadmapModuleCreate,
    RoadmapTopic,
    RoadmapTopicCreate,
    GapTopicItem,
    SuggestNextTopicsResponse,
    EnfoqueEstudio,
    FuenteTema,
)
from aulento.roadmap.pedagogical_profiles import (
    CLAVE_PERFIL,
    esqueleto_de_arquetipo,
    parsear_perfil,
    perfil_de_ruta,
    perfil_desde_arquetipo,
    perfil_resuelto,
    resolver_arquetipo,
    tokenizar,
    variante_de_arquetipo,
)
from aulento.roadmap.system_prompt_manager import SystemPromptManager
from aulento.roadmap.templates import get_curated_templates, get_template_by_title

logger = logging.getLogger(__name__)

TAMANO_POR_ALCANCE: dict[str, str] = {
    AlcanceRuta.CURSO.value: (
        "Tamaño (alcance 'curso'): diseña entre 3 y 5 módulos, con 3 a 4 temas cada uno, "
        "ordenados de menor a mayor complejidad."
    ),
    AlcanceRuta.ESPECIALIZACION.value: (
        "Tamaño (alcance 'especializacion'): diseña entre 5 y 8 módulos, con 4 a 6 temas cada uno, "
        "ordenados de menor a mayor complejidad."
    ),
    AlcanceRuta.CARRERA.value: (
        "Tamaño (alcance 'carrera'): diseña entre 8 y 14 módulos. Cada módulo es una MATERIA de la carrera, "
        "con su descripción y una lista \"correlativas\" con los títulos exactos de las materias previas que requiere. "
        "NO incluyas temas (deja \"temas\": []): se generan después, materia por materia."
    ),
}

AVISO_FALLBACK = (
    "Ruta generada sin IA (sin clave configurada, cuota agotada o respuesta inválida). "
    "Es una estructura base genérica del arquetipo «{arquetipo}», no un plan diseñado para tu objetivo. "
    "Configura una clave de Gemini y vuelve a generarla para obtener una ruta a medida."
)
# Cuando la causa no es la falta de clave, el aviso la dice
AVISO_FALLBACK_CON_MOTIVO = (
    "Ruta generada sin IA. Motivo: {motivo} "
    "Es una estructura base genérica del arquetipo «{arquetipo}», no un plan diseñado para tu objetivo. "
    "Resolvé el motivo y volvé a generarla para obtener una ruta a medida."
)
CLAVE_MOTIVO_SIN_IA = "motivo_sin_ia"

MIN_TEMAS_EXPANSION = 4
MAX_TEMAS_EXPANSION = 8


def _texto_o_none(valor: Any) -> str | None:
    """Acepta solo texto no vacío: un campo de la IA con otro tipo no debe invalidar la ruta entera."""
    return valor.strip() if isinstance(valor, str) and valor.strip() else None


def normalizar_alcance(alcance: AlcanceRuta | str | None) -> str:
    """Devuelve el valor de alcance válido; cualquier valor desconocido cae en `curso`."""
    try:
        return AlcanceRuta(alcance).value
    except ValueError:
        return AlcanceRuta.CURSO.value


class RoadmapEngine:
    """Orquestador de diseño curricular asistido por IA y evolución de habilidades."""

    def __init__(self, repo: RoadmapRepository) -> None:
        exigir_repositorio_de_cuenta(repo)
        self.repo = repo
        self.pasarela = PasarelaDeIA.de_repositorio(repo)
        self.prompts = SystemPromptManager.de_repositorio(repo)

    def get_templates(self) -> list[RoadmapCreate]:
        """Retorna las plantillas curadas disponibles."""
        return get_curated_templates()

    def generate_roadmap_with_ai(
        self,
        prompt: str,
        target_role: str = "Data Engineer",
        experience_level: str = "Senior",
        category: str = "general",
        enfoque_estudio: str = "profesional",
        alcance: AlcanceRuta | str = AlcanceRuta.CURSO,
    ) -> RoadmapCreate:
        """Diseña una ruta curricular con la IA de la cuenta (módulos, temas y perfil pedagógico).

        Sin IA utilizable devuelve una ruta base marcada con un aviso; si la causa no es la falta de clave,
        el aviso y `metadata_json["motivo_sin_ia"]` la dicen.
        """
        alcance_valor = normalizar_alcance(alcance)

        # 1. Plantilla curada solo por elección explícita (título completo)
        matched_template = get_template_by_title(target_role) or get_template_by_title(prompt)
        if matched_template and not prompt.lower().startswith("personalizado:"):
            logger.info("Usando plantilla canónica curada para %s", target_role)
            return matched_template

        # 2. Generación con la IA de la cuenta (su proveedor, su clave y su modelo) y el system prompt configurable
        pedido = Pedido(
            sistema=self.prompts.get_roadmap_system_instruction(),
            usuario=(
                f"Crea una ruta de aprendizaje adaptada al objetivo: '{prompt}'.\n"
                f"Área/Tema: '{target_role}'. Nivel o Profundidad: '{experience_level}'. "
                f"Categoría: '{category}'. Enfoque de Estudio: '{enfoque_estudio}'.\n"
                f"{TAMANO_POR_ALCANCE[alcance_valor]}"
            ),
            json=True,
            temperatura=0.2,
        )
        motivo: str | None = None
        try:
            respuesta = self.pasarela.generar(pedido, "roadmap_gen", self.repo)
        except IANoDisponibleError as error:
            motivo = motivo_sin_ia(error)
        else:
            try:
                roadmap = self._roadmap_desde_respuesta_ia(
                    leer_json(respuesta.texto),
                    prompt=prompt,
                    target_role=target_role,
                    experience_level=experience_level,
                    category=category,
                    enfoque_estudio=enfoque_estudio,
                    alcance=alcance_valor,
                )
            except Exception as e:
                logger.warning("Error leyendo la ruta que devolvió la IA: %s", e)
                roadmap = None
            if roadmap:
                return roadmap
            motivo = str(respuesta_inutil(respuesta, "devolvió una ruta sin módulos utilizables"))
            logger.warning("La respuesta de la IA no trae módulos utilizables; se usa el fallback.")

        # 3. Fallback sin IA, construido desde el arquetipo de la disciplina y marcado con aviso
        return self._build_domain_fallback(
            prompt, target_role, experience_level, category, enfoque_estudio, alcance_valor, motivo=motivo
        )

    @staticmethod
    def _roadmap_desde_respuesta_ia(
        parsed: Any,
        prompt: str,
        target_role: str,
        experience_level: str,
        category: str,
        enfoque_estudio: str,
        alcance: str,
    ) -> RoadmapCreate | None:
        """Convierte el JSON de la IA en una ruta. Devuelve None si no trae módulos utilizables."""
        if not isinstance(parsed, dict):
            return None

        es_carrera = alcance == AlcanceRuta.CARRERA.value
        modules: list[RoadmapModuleCreate] = []
        raw_modules = parsed.get("modulos")
        for m in raw_modules if isinstance(raw_modules, list) else []:
            if not isinstance(m, dict):
                continue
            topics: list[RoadmapTopicCreate] = []
            raw_topics = m.get("temas")
            for t in raw_topics if isinstance(raw_topics, list) else []:
                if not isinstance(t, dict):
                    continue
                raw_prereqs = t.get("prerrequisitos")
                topics.append(
                    RoadmapTopicCreate(
                        titulo=str(t.get("titulo") or f"Tema {len(topics) + 1}")[:200],
                        descripcion=_texto_o_none(t.get("descripcion")),
                        orden=len(topics) + 1,
                        prerrequisitos=[
                            p for p in (raw_prereqs if isinstance(raw_prereqs, list) else []) if isinstance(p, str)
                        ],
                    )
                )

            descripcion = _texto_o_none(m.get("descripcion"))
            raw_correlativas = m.get("correlativas")
            correlativas = [c for c in (raw_correlativas if isinstance(raw_correlativas, list) else []) if isinstance(c, str) and c.strip()]
            if es_carrera and correlativas:
                descripcion = f"{descripcion or ''} Correlativas: {', '.join(correlativas)}.".strip()

            modules.append(
                RoadmapModuleCreate(
                    titulo=str(m.get("titulo") or f"Módulo {len(modules) + 1}")[:200],
                    descripcion=descripcion,
                    orden=len(modules) + 1,
                    temas=topics,
                )
            )

        utilizable = bool(modules) if es_carrera else any(mod.temas for mod in modules)
        if not utilizable:
            return None

        titulo = str(parsed.get("titulo") or f"Ruta: {target_role}")[:200]
        perfil = parsear_perfil(parsed.get(CLAVE_PERFIL))
        if perfil:
            perfil.origen = "ia"
        else:
            perfil = perfil_resuelto(category, f"{target_role} {titulo}", prompt, target_role or titulo)

        return RoadmapCreate(
            titulo=titulo,
            descripcion=_texto_o_none(parsed.get("descripcion")) or f"Ruta generada para {target_role}",
            categoria=(category or _texto_o_none(parsed.get("categoria")) or "general")[:50],
            nivel_objetivo=(_texto_o_none(parsed.get("nivel_objetivo")) or experience_level)[:50],
            enfoque_estudio=enfoque_estudio,
            metadata_json={
                "origen": "ia",
                "alcance": alcance,
                "prompt": prompt,
                CLAVE_PERFIL: perfil.model_dump(),
            },
            modulos=modules,
        )

    @staticmethod
    def _nivel_cefr(prompt: str, target_role: str, category: str, experience_level: str) -> str:
        tokens = set(tokenizar(f"{category} {prompt} {target_role}"))
        nivel = experience_level.lower()
        if "a2" in tokens:
            return "A2 - Elemental & Trabajo Diario"
        if "b1" in tokens or nivel == "semi-senior":
            return "B1 - Autonomía Laboral"
        if "b2" in tokens or nivel == "senior":
            return "B2 - Profesional & Negocios"
        if "c1" in tokens or "staff" in nivel:
            return "C1 - Consultoría & Liderazgo Global"
        if "a1" in tokens or nivel == "junior":
            return "A1 - Fundamentos"
        return "A2 - Elemental & Trabajo Diario"

    def _build_domain_fallback(
        self,
        prompt: str,
        target_role: str,
        experience_level: str,
        category: str,
        enfoque_estudio: str = "profesional",
        alcance: str = AlcanceRuta.CURSO.value,
        motivo: str | None = None,
    ) -> RoadmapCreate:
        """Construye una ruta base sin IA desde el arquetipo de la disciplina y la marca con un aviso visible.

        `motivo` es por qué no hubo IA cuando la causa no es la falta de clave.
        """
        clean_title = " ".join((target_role or prompt.title()).split())[:100]
        arquetipo = resolver_arquetipo(category, target_role, prompt)
        variante = variante_de_arquetipo(arquetipo, category, target_role, prompt)
        perfil = perfil_desde_arquetipo(variante, clean_title)

        categoria = category or "general"
        if variante == "idiomas":
            nivel = self._nivel_cefr(prompt, target_role, category, experience_level)
            titulo = f"Inglés Profesional: {clean_title} ({nivel})"
            descripcion = (
                f"Ruta integral de inglés orientada a la práctica comunicativa real en {prompt}, "
                "colocaciones laborales, fonética y fluidez."
            )
            categoria = "english_communication"
        elif arquetipo == "idiomas":
            titulo = f"Idioma: {clean_title}"
            descripcion = f"Estructura base para estudiar {prompt}: gramática en contexto, vocabulario, pronunciación y práctica comunicativa."
        elif arquetipo == "negocio":
            titulo = f"Especialización: {clean_title} ({experience_level})"
            descripcion = (
                f"Ruta orientada a visión de producto, analítica de métricas clave, marcos ágiles y valor de negocio en {prompt}."
            )
        elif arquetipo == "tech":
            titulo = f"Ruta Especializada: {clean_title} ({experience_level})"
            descripcion = (
                f"Ruta curricular focalizada en dominar {prompt} con estándares de la industria y resolución de casos reales."
            )
        else:
            titulo = f"Ruta de Estudio: {clean_title}"
            descripcion = f"Estructura base para estudiar {prompt}, organizada según la forma de enseñar propia de la disciplina."

        return RoadmapCreate(
            titulo=titulo[:200],
            descripcion=descripcion,
            categoria=categoria,
            nivel_objetivo=experience_level,
            enfoque_estudio=enfoque_estudio,
            metadata_json={
                "origen": "domain_fallback",
                "aviso": (
                    AVISO_FALLBACK_CON_MOTIVO.format(arquetipo=arquetipo, motivo=motivo)
                    if motivo
                    else AVISO_FALLBACK.format(arquetipo=arquetipo)
                ),
                **({CLAVE_MOTIVO_SIN_IA: motivo} if motivo else {}),
                "alcance": alcance,
                "prompt": prompt,
                CLAVE_PERFIL: perfil.model_dump(),
            },
            modulos=esqueleto_de_arquetipo(variante, clean_title),
        )

    def expand_module(self, module_id: int) -> list[RoadmapTopic]:
        """Genera con IA entre 4 y 8 temas para un módulo (materia) y los agrega sin duplicar títulos.

        Lanza `ValueError` si el módulo no existe e `IANoDisponibleError` si no hay IA utilizable
        (`FaltaClaveDeIA` cuando la cuenta no cargó la clave de su proveedor, y el error propio de cada falla
        del proveedor): en ese caso no se inserta ningún tema enlatado.
        """
        ctx = self.repo.get_module_with_context(module_id)
        if not ctx:
            raise ValueError(f"Módulo con ID {module_id} no encontrado.")

        perfil = perfil_de_ruta(ctx["metadata_json"], ctx.get("categoria"), ctx["roadmap_title"])
        system_instruction = (
            "Eres un Diseñador Curricular experto en la disciplina indicada. Desglosas una materia o módulo "
            "en temas atómicos, ordenados de menor a mayor complejidad, propios de esa disciplina.\n"
            "Responde EXCLUSIVAMENTE con un objeto JSON válido con la estructura:\n"
            '{"temas": [{"titulo": "Nombre del tema", "descripcion": "Qué aprenderá y por qué es necesario"}]}'
        )
        user_prompt = (
            f"Ruta: '{ctx['roadmap_title']}' (disciplina: {perfil.disciplina}; nivel: {ctx.get('nivel_objetivo') or 'Senior'}; "
            f"enfoque de estudio: {ctx['enfoque_estudio']}).\n"
            f"Materia o módulo a expandir: '{ctx['module_title']}'."
            + (f" Descripción: {ctx['module_desc']}" if ctx.get("module_desc") else "")
            + "\nSecciones con las que se enseña cada clase de esta ruta: "
            + "; ".join(sec.titulo for sec in perfil.secciones)
            + ".\nOtros módulos de la ruta (no repitas su contenido): "
            + ("; ".join(ctx["other_module_titles"]) or "ninguno")
            + ".\nTemas que el módulo ya tiene (no los repitas): "
            + ("; ".join(ctx["topic_titles"]) or "ninguno")
            + f".\nGenera entre {MIN_TEMAS_EXPANSION} y {MAX_TEMAS_EXPANSION} temas nuevos para este módulo."
        )
        respuesta = self.pasarela.generar(
            Pedido(sistema=system_instruction, usuario=user_prompt, json=True, temperatura=0.2),
            "module_expand",
            self.repo,
        )
        parsed = leer_json_de(respuesta, "No se agregaron temas.")

        raw_topics = parsed.get("temas") if isinstance(parsed, dict) else None
        titulos_vistos = {titulo.strip().lower() for titulo in ctx["topic_titles"]}
        temas: list[RoadmapTopicCreate] = []
        for t in raw_topics if isinstance(raw_topics, list) else []:
            if not isinstance(t, dict) or not isinstance(t.get("titulo"), str) or not t["titulo"].strip():
                continue
            clave = t["titulo"].strip().lower()
            if clave in titulos_vistos:
                continue
            titulos_vistos.add(clave)
            descripcion = t.get("descripcion")
            temas.append(
                RoadmapTopicCreate(
                    titulo=t["titulo"].strip()[:200],
                    descripcion=descripcion if isinstance(descripcion, str) else None,
                    fuente=FuenteTema.AI_GENERADA,
                )
            )

        if len(temas) < MIN_TEMAS_EXPANSION:
            raise respuesta_inutil(
                respuesta,
                f"devolvió menos de {MIN_TEMAS_EXPANSION} temas nuevos y válidos para la materia",
                "No se agregaron temas.",
            )

        return self.repo.add_topics_to_module(module_id, temas[:MAX_TEMAS_EXPANSION])

    def suggest_next_topics(self, roadmap_id: int) -> SuggestNextTopicsResponse:
        """Analiza los temas completados y sugiere 3 a 5 temas de profundización ($i+1$)."""
        detail = self.repo.get_roadmap(roadmap_id)
        if not detail:
            return SuggestNextTopicsResponse(
                completed_topics_count=0,
                suggested_topics=[],
                reasoning="Ruta no encontrada.",
            )

        completed_titles = []
        pending_titles = []
        for mod in detail.modulos:
            for t in mod.temas:
                if t.estado.value == "completado":
                    completed_titles.append(t.titulo)
                else:
                    pending_titles.append(t.titulo)

        motivo: str | None = None
        if completed_titles:
            system_instruction = (
                "Eres un Mentor de Aprendizaje Adaptativo. Tu objetivo es proponer el siguiente nivel ($i+1$) "
                "de evolución curricular a un profesional técnico que ya dominó ciertos temas.\n"
                "Devuelve un JSON con:\n"
                "{\n"
                '  "reasoning": "Breve explicación de por qué estos temas amplían su maestría",\n'
                '  "suggested_topics": [\n'
                '    {"titulo": "Nombre del tema avanzado", "descripcion": "Por qué es relevante", "modulo_sugerido": "Especialización"}\n'
                '  ]\n'
                "}"
            )
            user_prompt = (
                f"Ruta: '{detail.titulo}'.\n"
                f"Temas ya dominados por el estudiante ({len(completed_titles)}):\n"
                + "\n".join(f"- {t}" for t in completed_titles[:15])
                + f"\nTemas aún pendientes en la ruta: {len(pending_titles)}.\n"
                "Sugiere 3 a 5 temas de vanguardia para profundizar sus conocimientos."
            )
            try:
                respuesta = self.pasarela.generar(
                    Pedido(sistema=system_instruction, usuario=user_prompt, json=True, temperatura=0.3),
                    "suggest_next",
                    self.repo,
                )
            except IANoDisponibleError as error:
                motivo = motivo_sin_ia(error)
            else:
                try:
                    parsed = leer_json(respuesta.texto)
                    items = [
                        GapTopicItem(
                            titulo=st.get("titulo", "Tema avanzado"),
                            descripcion=st.get("descripcion"),
                            modulo_sugerido=st.get("modulo_sugerido", "Especialización Avanzada"),
                        )
                        for st in parsed.get("suggested_topics", [])
                    ]
                    return SuggestNextTopicsResponse(
                        completed_topics_count=len(completed_titles),
                        suggested_topics=items,
                        reasoning=parsed.get("reasoning", f"Sugerencias generadas con {respuesta.modelo}."),
                    )
                except Exception as e:
                    logger.warning("Error leyendo las sugerencias de la IA: %s", e)
                    motivo = str(respuesta_inutil(respuesta, "devolvió sugerencias que no se pudieron leer"))

        # Fallback de sugerencia heurística
        categoria = detail.categoria or "data_ai"
        if "data" in categoria.lower() or "engineer" in detail.titulo.lower():
            suggested = [
                GapTopicItem(
                    titulo="Data Mesh & Arquitectura de Productos de Datos Descentralizados",
                    descripcion="Dominios de datos independientes con federated governance",
                    modulo_sugerido="Especialización Avanzada",
                ),
                GapTopicItem(
                    titulo="Continuous Data Testing & Drift Detection en Producción",
                    descripcion="Validación de esquemas y distribución estadística en tiempo real",
                    modulo_sugerido="Especialización Avanzada",
                ),
                GapTopicItem(
                    titulo="Zero-Copy Clones & Storage Optimization en Lakehouses",
                    descripcion="Aislamiento seguro de ambientes dev/staging sin duplicar datos",
                    modulo_sugerido="Especialización Avanzada",
                ),
            ]
        elif "ai" in categoria.lower() or "llm" in detail.titulo.lower():
            suggested = [
                GapTopicItem(
                    titulo="Speculative Decoding & Optimización de Latencia en Inferencia",
                    descripcion="Aceleración de generación sin pérdida de calidad",
                    modulo_sugerido="Especialización Avanzada",
                ),
                GapTopicItem(
                    titulo="DSPy: Optimización Algorítmica de Prompts y Pipelines de LLMs",
                    descripcion="Sustitución de prompts manuales por compiladores de modelos",
                    modulo_sugerido="Especialización Avanzada",
                ),
                GapTopicItem(
                    titulo="Guardrails de Seguridad y Detección de Prompt Injection",
                    descripcion="Filtrado en tiempo de ejecución para despliegues empresariales",
                    modulo_sugerido="Especialización Avanzada",
                ),
            ]
        else:
            suggested = [
                GapTopicItem(
                    titulo=f"Optimización y Rendimiento de {detail.titulo}",
                    descripcion="Técnicas avanzadas de profiling y reducción de cuellos de botella",
                    modulo_sugerido="Especialización Avanzada",
                ),
                GapTopicItem(
                    titulo=f"Automatización y Testing E2E en {detail.titulo}",
                    descripcion="Pruebas continuas e integración en pipelines CI/CD",
                    modulo_sugerido="Especialización Avanzada",
                ),
            ]

        return SuggestNextTopicsResponse(
            completed_topics_count=len(completed_titles),
            suggested_topics=suggested,
            reasoning=f"Basado en tus {len(completed_titles)} temas dominados, estos tópicos aceleran tu consolidación profesional.",
            is_fallback=True,
            motivo_sin_ia=motivo,
        )
