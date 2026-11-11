"""Sugerencias de prelaciones con IA para una ruta existente: propone, filtra y no persiste nada."""

from __future__ import annotations

import re
from typing import Any

from aulento.core.ia.lectura import leer_json_de, respuesta_inutil
from aulento.core.ia.pasarela import PasarelaDeIA
from aulento.core.ia.tipos import Pedido
from aulento.db.cuenta import exigir_repositorio_de_cuenta
from aulento.db.roadmap_repository import TIPOS_DE_PRELACION, RoadmapRepository
from aulento.models.roadmap import (
    PrerequisiteSuggestion,
    PrerequisiteSuggestionResponse,
)
from aulento.roadmap.graph_engine import detecta_ciclo
from aulento.roadmap.pedagogical_profiles import perfil_de_ruta

MAX_TEMAS_SUGERENCIA = 150
MAX_LARGO_MOTIVO = 300
# Tope del alta en bloque (`PrerequisiteBulkCreate`): no se propone más de lo que se puede aceptar de una vez.
MAX_SUGERENCIAS = 300
_CODIGO_TEMA = re.compile(r"T(\d+)", re.IGNORECASE)


class PrerequisiteAdvisor:
    """Pide a la IA las dependencias conceptuales entre los temas de una ruta."""

    def __init__(self, repo: RoadmapRepository) -> None:
        exigir_repositorio_de_cuenta(repo)
        self.repo = repo
        self.pasarela = PasarelaDeIA.de_repositorio(repo)

    def suggest(self, ruta_id: int) -> PrerequisiteSuggestionResponse:
        """Devuelve prelaciones propuestas por la IA, ya filtradas, sin guardar ninguna.

        Lanza `ValueError` si la ruta no existe o no se puede analizar (menos de dos temas o más de
        `MAX_TEMAS_SUGERENCIA`) e `IANoDisponibleError` si no hay IA o su respuesta no es utilizable
        (`FaltaClaveDeIA` sin clave del proveedor de la cuenta, y el error propio de cada falla del proveedor).
        """
        roadmap = self.repo.get_roadmap(ruta_id)
        if not roadmap:
            raise ValueError(f"Ruta con ID {ruta_id} no encontrada.")

        temas = [(tema.id, modulo.titulo, tema.titulo) for modulo in roadmap.modulos for tema in modulo.temas]
        if len(temas) < 2:
            raise ValueError("La ruta necesita al menos dos temas para sugerir prelaciones.")
        if len(temas) > MAX_TEMAS_SUGERENCIA:
            raise ValueError(
                f"La ruta tiene {len(temas)} temas: las sugerencias con IA admiten hasta {MAX_TEMAS_SUGERENCIA}."
            )

        perfil = perfil_de_ruta(roadmap.metadata_json, roadmap.categoria, roadmap.titulo)
        system_instruction = (
            "Eres un Diseñador Curricular experto en la disciplina indicada. Identificas qué temas de una "
            "ruta de aprendizaje son prerrequisito conceptual de otros.\n"
            "Cada tema se identifica por un código (por ejemplo T12). Usa SIEMPRE esos códigos, nunca los títulos.\n"
            "Propón solo dependencias conceptuales reales: no encadenes temas por el simple orden en que aparecen. "
            "Usa tipo 'estricta' cuando el destino no se entiende sin el origen y 'recomendada' cuando solo ayuda. "
            "No propongas ciclos.\n"
            "Responde EXCLUSIVAMENTE con un objeto JSON válido con la estructura:\n"
            '{"prelaciones": [{"origen": "T12", "destino": "T15", "tipo": "estricta|recomendada", '
            '"motivo": "Por qué el origen es necesario para el destino"}]}'
        )
        user_prompt = (
            f"Ruta: '{roadmap.titulo}' (disciplina: {perfil.disciplina}; nivel: {roadmap.nivel_objetivo}; "
            f"enfoque de estudio: {roadmap.enfoque_estudio}).\n"
            "Temas de la ruta, en orden curricular, con el formato `código | módulo | título`:\n"
            + "\n".join(f"T{tema_id} | {modulo} | {titulo}" for tema_id, modulo, titulo in temas)
        )
        respuesta = self.pasarela.generar(
            Pedido(sistema=system_instruction, usuario=user_prompt, json=True, temperatura=0.1),
            "prerequisite_suggest",
            self.repo,
        )
        parsed = leer_json_de(respuesta, "No hay sugerencias.")

        propuestas = parsed.get("prelaciones") if isinstance(parsed, dict) else None
        if not isinstance(propuestas, list):
            raise respuesta_inutil(respuesta, "devolvió una respuesta sin la lista de prelaciones", "No hay sugerencias.")

        titulos = {tema_id: titulo for tema_id, _, titulo in temas}
        guardadas = [(e.tema_origen_id, e.tema_destino_id) for e in self.repo.get_prerequisites(ruta_id)]
        return self._filtrar(propuestas, titulos, guardadas)

    @staticmethod
    def _id_de_codigo(codigo: Any) -> int | None:
        coincidencia = _CODIGO_TEMA.fullmatch(codigo.strip()) if isinstance(codigo, str) else None
        return int(coincidencia.group(1)) if coincidencia else None

    @classmethod
    def _filtrar(
        cls,
        propuestas: list[Any],
        titulos: dict[int, str],
        guardadas: list[tuple[int, int]],
    ) -> PrerequisiteSuggestionResponse:
        """Descarta, en el orden recibido, las propuestas que no se podrían guardar.

        Caen las que apuntan a temas inexistentes, las auto-referencias, las repetidas, las ya
        guardadas y las que cerrarían un ciclo con las guardadas o con las propuestas anteriores.
        """
        ya_guardadas = set(guardadas)
        aceptadas: list[tuple[int, int]] = []
        sugerencias: list[PrerequisiteSuggestion] = []

        for propuesta in propuestas:
            if not isinstance(propuesta, dict):
                continue
            origen_id = cls._id_de_codigo(propuesta.get("origen"))
            destino_id = cls._id_de_codigo(propuesta.get("destino"))
            if origen_id not in titulos or destino_id not in titulos or origen_id == destino_id:
                continue
            arista = (origen_id, destino_id)
            if arista in ya_guardadas or arista in aceptadas:
                continue
            if len(sugerencias) >= MAX_SUGERENCIAS or detecta_ciclo(guardadas + aceptadas, origen_id, destino_id):
                continue

            tipo = propuesta.get("tipo")
            motivo = propuesta.get("motivo")
            aceptadas.append(arista)
            sugerencias.append(
                PrerequisiteSuggestion(
                    tema_origen_id=origen_id,
                    tema_destino_id=destino_id,
                    origen_titulo=titulos[origen_id],
                    destino_titulo=titulos[destino_id],
                    # Un tipo desconocido se propone como recomendada: no bloquea ni reemplaza la secuencia implícita.
                    tipo=tipo if tipo in TIPOS_DE_PRELACION else "recomendada",
                    motivo=" ".join(motivo.split())[:MAX_LARGO_MOTIVO] if isinstance(motivo, str) else "",
                )
            )

        return PrerequisiteSuggestionResponse(sugerencias=sugerencias, descartadas=len(propuestas) - len(sugerencias))
