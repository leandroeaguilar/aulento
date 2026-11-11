"""Motor analítico de Grafo de Prelaciones y DAG (Directed Acyclic Graph) para Rutas de Aprendizaje.

Calcula ordenamiento topológico, detección de ciclos, ruta crítica,
bloqueos por dependencias insatisfechas y exportación a Mermaid.
"""

from __future__ import annotations

import heapq
import html
import json
import logging
from collections import defaultdict
from collections.abc import Iterable
from itertools import pairwise
from typing import TYPE_CHECKING, Any

from aulento.models.roadmap import (
    EstadoTema,
    PrerequisiteEdge,
    RoadmapDetail,
    RoadmapGraphData,
    RoadmapGraphNode,
)

if TYPE_CHECKING:
    from aulento.db.roadmap_repository import RoadmapRepository

logger = logging.getLogger(__name__)

CLAVE_GRAFO = "grafo"
CLAVE_SECUENCIA_IMPLICITA = "secuencia_implicita"
TIPO_ESTRICTA = "estricta"

# El `#` va primero: los demás reemplazos introducen `#` que no deben volver a escaparse.
_ENTIDADES_MERMAID = (
    ("#", "#35;"),
    ('"', "#quot;"),
    ("[", "#91;"),
    ("]", "#93;"),
    ("<", "#lt;"),
    (">", "#gt;"),
    ("`", "#96;"),
    # `%%{…}%%` es una directiva de configuración: Mermaid la busca en todo el texto, también dentro de una etiqueta.
    ("%", "#37;"),
    ("{", "#123;"),
    ("}", "#125;"),
    ("'", "#39;"),
)
ETIQUETA_VACIA = "(sin título)"


def detecta_ciclo(aristas_existentes: Iterable[tuple[int, int]], origen: int, destino: int) -> bool:
    """Indica si agregar la arista `origen → destino` cerraría un ciclo con las aristas dadas.

    Lo cierra cuando `destino` ya alcanza a `origen` (o cuando son el mismo tema).
    """
    sucesores: dict[int, list[int]] = defaultdict(list)
    for desde, hasta in aristas_existentes:
        sucesores[desde].append(hasta)

    pila: list[int] = [destino]
    vistos: set[int] = set()
    while pila:
        actual = pila.pop()
        if actual == origen:
            return True
        if actual in vistos:
            continue
        vistos.add(actual)
        pila.extend(sucesores.get(actual, ()))
    return False


def secuencia_implicita_activa(metadata_json: dict[str, Any] | None) -> bool:
    """Lee de `metadata_json` si la ruta infiere la secuencia curricular (activada por defecto)."""
    ajustes = (metadata_json or {}).get(CLAVE_GRAFO)
    if not isinstance(ajustes, dict):
        return True
    return ajustes.get(CLAVE_SECUENCIA_IMPLICITA) is not False


def _etiqueta(texto: str | None) -> str:
    """Escapa un título para usarlo dentro de una etiqueta Mermaid entre comillas, en una sola línea."""
    limpio = " ".join((texto or "").split()) or ETIQUETA_VACIA
    for caracter, entidad in _ENTIDADES_MERMAID:
        limpio = limpio.replace(caracter, entidad)
    return limpio


class PrerequisiteGraphEngine:
    """Motor de análisis de grafos curriculares y dependencias de aprendizaje."""

    def __init__(self, repo: RoadmapRepository) -> None:
        self.repo = repo

    def get_graph_data(self, ruta_id: int) -> RoadmapGraphData:
        """Construye y analiza el DAG completo de la ruta de aprendizaje."""
        roadmap = self.repo.get_roadmap(ruta_id)
        if not roadmap:
            raise ValueError(f"Ruta con ID {ruta_id} no encontrada.")

        # 1. Temas en orden curricular (módulo, luego tema): es el desempate de todo el análisis
        topics_map: dict[int, dict] = {}
        orden_curricular: list[int] = []
        for mod in roadmap.modulos:
            for t in mod.temas:
                orden_curricular.append(t.id)
                topics_map[t.id] = {
                    "modulo_id": mod.id,
                    "modulo_titulo": mod.titulo,
                    "titulo": t.titulo,
                    "estado": t.estado.value if isinstance(t.estado, EstadoTema) else str(t.estado),
                }
        posicion = {tid: idx for idx, tid in enumerate(orden_curricular)}

        # 2. Aristas efectivas: las guardadas más la secuencia inferida por tema
        secuencia_implicita = secuencia_implicita_activa(roadmap.metadata_json)
        edges = [
            e
            for e in self.repo.get_prerequisites(ruta_id)
            if e.tema_origen_id in posicion and e.tema_destino_id in posicion
        ]
        if secuencia_implicita:
            edges.extend(self._aristas_inferidas(ruta_id, orden_curricular, topics_map, edges))

        # 3. Listas de adyacencia (todas las aristas, y aparte solo las estrictas)
        adj: dict[int, list[int]] = defaultdict(list)
        in_edges: dict[int, list[int]] = defaultdict(list)
        adj_estrictas: dict[int, list[int]] = defaultdict(list)
        in_estrictas: dict[int, list[int]] = defaultdict(list)
        for edge in edges:
            adj[edge.tema_origen_id].append(edge.tema_destino_id)
            in_edges[edge.tema_destino_id].append(edge.tema_origen_id)
            if edge.tipo == TIPO_ESTRICTA:
                adj_estrictas[edge.tema_origen_id].append(edge.tema_destino_id)
                in_estrictas[edge.tema_destino_id].append(edge.tema_origen_id)

        # 4. Orden topológico (Kahn) con cola de prioridad por posición curricular
        in_degrees = {tid: len(in_edges[tid]) for tid in orden_curricular}
        cola = [(posicion[tid], tid) for tid in orden_curricular if in_degrees[tid] == 0]
        heapq.heapify(cola)
        topo_order: list[int] = []
        while cola:
            _, curr = heapq.heappop(cola)
            topo_order.append(curr)
            for neighbor in adj[curr]:
                in_degrees[neighbor] -= 1
                if in_degrees[neighbor] == 0:
                    heapq.heappush(cola, (posicion[neighbor], neighbor))

        has_cycle = len(topo_order) != len(orden_curricular)
        if has_cycle:
            topo_order = list(orden_curricular)

        # 5. Bloqueo: solo por prerrequisitos estrictos sin completar. Un tema que ya se está
        # estudiando no se bloquea: el estudiante decidió empezarlo y sigue siendo lo que tiene entre manos.
        completado = EstadoTema.COMPLETADO.value
        pendiente = EstadoTema.PENDIENTE.value
        blocked_nodes = {
            tid
            for tid in orden_curricular
            if topics_map[tid]["estado"] == pendiente
            and any(topics_map[p]["estado"] != completado for p in in_estrictas[tid])
        }
        disponibles = [
            tid for tid in orden_curricular if topics_map[tid]["estado"] != completado and tid not in blocked_nodes
        ]
        disponibles_set = set(disponibles)

        # 6. Niveles y ruta crítica: cadena más larga de prelaciones estrictas
        niveles: dict[int, int] = dict.fromkeys(orden_curricular, 0)
        critical_path: list[int] = []
        if not has_cycle:
            niveles, critical_path = self._niveles_y_ruta_critica(topo_order, adj_estrictas, posicion)
        critical_set = set(critical_path)

        # 7. Construir nodos de grafo enriquecidos
        nodes: list[RoadmapGraphNode] = []
        for idx, tid in enumerate(topo_order, start=1):
            t_info = topics_map[tid]
            nodes.append(
                RoadmapGraphNode(
                    id=tid,
                    modulo_id=t_info["modulo_id"],
                    modulo_titulo=t_info["modulo_titulo"],
                    titulo=t_info["titulo"],
                    orden=idx,
                    estado=t_info["estado"],
                    nivel_topologico=niveles[tid],
                    is_blocked=tid in blocked_nodes,
                    disponible=tid in disponibles_set,
                    in_degree=len(in_edges[tid]),
                    out_degree=len(adj[tid]),
                    is_critical_path=(tid in critical_set),
                    prerequisites=sorted(set(in_edges[tid]), key=posicion.__getitem__),
                    dependents=sorted(set(adj[tid]), key=posicion.__getitem__),
                )
            )

        # 8. Generar exportación Mermaid
        mermaid_code = self.generate_mermaid(roadmap, nodes, edges)

        return RoadmapGraphData(
            ruta_id=ruta_id,
            ruta_titulo=roadmap.titulo,
            nodes=nodes,
            edges=edges,
            topological_order=topo_order,
            critical_path=critical_path,
            has_cycle=has_cycle,
            mermaid_code=mermaid_code,
            disponibles=disponibles,
            secuencia_implicita=secuencia_implicita,
        )

    @staticmethod
    def _aristas_inferidas(
        ruta_id: int,
        orden_curricular: list[int],
        topics_map: dict[int, dict],
        guardadas: list[PrerequisiteEdge],
    ) -> list[PrerequisiteEdge]:
        """Secuencia implícita: cada tema sin prelación estricta guardada entrante depende del tema anterior.

        Una prelación `recomendada` no reemplaza la secuencia: no bloquea, así que quitarle al tema su
        dependencia del anterior lo dejaría disponible antes de tiempo.
        Las aristas inferidas no se persisten. Se omite la que cerraría un ciclo con las aristas
        guardadas y las inferidas ya acumuladas.
        """
        con_estricta_entrante = {e.tema_destino_id for e in guardadas if e.tipo == TIPO_ESTRICTA}
        sucesores: dict[int, list[int]] = defaultdict(list)
        for e in guardadas:
            sucesores[e.tema_origen_id].append(e.tema_destino_id)

        def alcanza(desde: int, hasta: int) -> bool:
            pila, vistos = [desde], set()
            while pila:
                actual = pila.pop()
                if actual == hasta:
                    return True
                if actual in vistos:
                    continue
                vistos.add(actual)
                pila.extend(sucesores[actual])
            return False

        inferidas: list[PrerequisiteEdge] = []
        for anterior_id, tema_id in pairwise(orden_curricular):
            if tema_id in con_estricta_entrante or alcanza(tema_id, anterior_id):
                continue
            sucesores[anterior_id].append(tema_id)
            inferidas.append(
                PrerequisiteEdge(
                    id=None,
                    ruta_id=ruta_id,
                    tema_origen_id=anterior_id,
                    tema_destino_id=tema_id,
                    tipo=TIPO_ESTRICTA,
                    origen_titulo=topics_map[anterior_id]["titulo"],
                    destino_titulo=topics_map[tema_id]["titulo"],
                    inferida=True,
                )
            )
        return inferidas

    @staticmethod
    def _niveles_y_ruta_critica(
        topo_order: list[int],
        adj_estrictas: dict[int, list[int]],
        posicion: dict[int, int],
    ) -> tuple[dict[int, int], list[int]]:
        """Nivel de cada tema (largo de su cadena estricta más larga) y Ruta Crítica del DAG.

        La ruta crítica es la cadena más larga de prelaciones estrictas; sin ninguna, queda vacía.
        Los empates se resuelven por posición curricular.
        """
        niveles: dict[int, int] = dict.fromkeys(topo_order, 0)
        parent: dict[int, int | None] = dict.fromkeys(topo_order)

        for u in topo_order:
            for v in adj_estrictas[u]:
                if niveles[u] + 1 > niveles[v]:
                    niveles[v] = niveles[u] + 1
                    parent[v] = u

        if not topo_order:
            return niveles, []

        final = min(topo_order, key=lambda tid: (-niveles[tid], posicion[tid]))
        if niveles[final] == 0:
            return niveles, []

        path: list[int] = []
        curr: int | None = final
        while curr is not None:
            path.append(curr)
            curr = parent[curr]
        path.reverse()
        return niveles, path

    def generate_mermaid(
        self,
        roadmap: RoadmapDetail,
        nodes: list[RoadmapGraphNode],
        edges: list[PrerequisiteEdge],
    ) -> str:
        """Genera el diagrama Mermaid que dibuja la Web UI y que se copia a Obsidian."""
        lines = [
            "graph TD",
            "    %% Estilos de Nodos y Estados de Aprendizaje",
            "    classDef completed fill:#16a34a,stroke:#15803d,stroke-width:2px,color:#ffffff;",
            "    classDef in_progress fill:#2563eb,stroke:#1d4ed8,stroke-width:2px,color:#ffffff;",
            "    classDef blocked fill:#374151,stroke:#4b5563,stroke-width:1px,color:#9ca3af;",
            "    classDef pending fill:#1e293b,stroke:#334155,stroke-width:1px,color:#e2e8f0;",
            "    classDef available stroke:#38bdf8,stroke-width:2px;",
            "    classDef critical stroke:#f59e0b,stroke-width:3px;",
            "",
        ]

        # Un subgrafo por módulo, con módulos y temas en orden curricular
        nodes_by_id = {n.id: n for n in nodes}
        for mod in roadmap.modulos:
            m_nodes = [nodes_by_id[t.id] for t in mod.temas if t.id in nodes_by_id]
            if not m_nodes:
                continue
            lines.append(f'    subgraph M_{mod.id} ["{_etiqueta(mod.titulo)}"]')
            for node in m_nodes:
                icon = "🔒 " if node.is_blocked else ("✅ " if node.estado == EstadoTema.COMPLETADO.value else "")
                lines.append(f'        T_{node.id}["{icon}{_etiqueta(node.titulo)}"]')
            lines.append("    end")
            lines.append("")

        # Conexiones: `linkStyle` usa el índice de la arista en el orden en que se emite
        lines.append("    %% Conexiones y Prelaciones")
        estilos_inferidas: list[str] = []
        emitidas = 0
        for e in edges:
            if e.tema_origen_id not in nodes_by_id or e.tema_destino_id not in nodes_by_id:
                continue
            arrow = "-->" if e.tipo == TIPO_ESTRICTA else "-.->"
            lines.append(f"    T_{e.tema_origen_id} {arrow} T_{e.tema_destino_id}")
            if e.inferida:
                estilos_inferidas.append(f"    linkStyle {emitidas} stroke:#475569,stroke-dasharray:4 3")
            emitidas += 1
        lines.extend(estilos_inferidas)

        lines.append("")
        lines.append("    %% Asignación de Clases")
        for node in nodes:
            if node.estado == EstadoTema.COMPLETADO.value:
                lines.append(f"    class T_{node.id} completed;")
            elif node.is_blocked:
                lines.append(f"    class T_{node.id} blocked;")
            elif node.estado == EstadoTema.EN_PROGRESO.value:
                lines.append(f"    class T_{node.id} in_progress;")
            else:
                lines.append(f"    class T_{node.id} pending;")

            if node.disponible:
                lines.append(f"    class T_{node.id} available;")
            if node.is_critical_path:
                lines.append(f"    class T_{node.id} critical;")

        return "\n".join(lines)

    @staticmethod
    def _split_topic_title(titulo: str) -> tuple[str, str]:
        """Divide el título de un tema en dos líneas legibles (máx 28 y 32 caracteres)."""
        limpio = " ".join((titulo or "").split()) or ETIQUETA_VACIA
        words = limpio.split()
        line1: list[str] = []
        rest: list[str] = []
        for w in words:
            candidate_line = " ".join(line1 + [w])
            if not rest and len(candidate_line) <= 28:
                line1.append(w)
            else:
                rest.append(w)
        if not line1:
            first = words[0]
            label = first[:27] + "…"
            rest = words[1:]
        else:
            label = " ".join(line1)
        sub_raw = " ".join(rest)
        sub = (sub_raw[:31] + "…" if len(sub_raw) > 32 else sub_raw) if sub_raw else ""
        return label, sub

    def render_interactive_map_html(self, ruta_id: int) -> str:
        """Renderiza en memoria (<2ms, cero procesos externos) el Mapa Interactivo SVG de la ruta."""
        roadmap = self.repo.get_roadmap(ruta_id)
        if not roadmap:
            raise ValueError(f"Ruta con ID {ruta_id} no encontrada.")

        graph = self.get_graph_data(ruta_id)
        nodes_by_id = {n.id: n for n in graph.nodes}
        topo_rank = {tid: idx + 1 for idx, tid in enumerate(graph.topological_order)}

        valid_mods = [
            mod for mod in roadmap.modulos
            if any(t.id in nodes_by_id for t in mod.temas)
        ]

        titulo_esc = html.escape(roadmap.titulo)
        if not valid_mods:
            return (
                "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
                "<style>body{margin:0;background:#020617;color:#94a3b8;font-family:system-ui,sans-serif;"
                "display:flex;align-items:center;justify-content:center;height:100vh;text-align:center;}</style>"
                f"</head><body><div><p style='font-size:15px;color:#f8fafc;font-weight:700;'>{titulo_esc}</p>"
                "<p style='font-size:12px;'>Esta ruta todavía no tiene temas para dibujar en el mapa interactivo.</p>"
                "</div></body></html>"
            )

        col_w = 290
        col_gap = 76
        card_w = 254
        card_h = 84
        row_step = 118
        margin_x = 48
        margin_y = 44
        header_h = 68

        max_topics = max(
            sum(1 for t in mod.temas if t.id in nodes_by_id)
            for mod in valid_mods
        )
        svg_w = max(980, margin_x * 2 + len(valid_mods) * col_w + max(0, len(valid_mods) - 1) * col_gap)
        svg_h = max(560, margin_y * 2 + header_h + max_topics * row_step + 40)

        coords: dict[int, tuple[int, int, int, int]] = {}
        svg_lanes: list[str] = []
        svg_nodes: list[str] = []

        for m_idx, mod in enumerate(valid_mods):
            m_topics = [nodes_by_id[t.id] for t in mod.temas if t.id in nodes_by_id]
            gx = margin_x + m_idx * (col_w + col_gap)
            gy = margin_y
            gh = header_h + len(m_topics) * row_step + 16
            completed_mod = sum(1 for n in m_topics if n.estado == EstadoTema.COMPLETADO.value)
            mod_title_short = mod.titulo[:30] + ("…" if len(mod.titulo) > 30 else "")
            mod_title_esc = html.escape(mod_title_short)
            accent_stroke = "#38bdf8" if m_idx % 2 == 0 else "#818cf8"

            svg_lanes.append(
                f'<g class="module-lane">'
                f'<rect x="{gx}" y="{gy}" width="{col_w}" height="{gh}" rx="20" '
                f'fill="rgba(15,23,42,0.72)" stroke="rgba(51,65,85,0.85)" stroke-width="1.5"/>'
                f'<rect x="{gx}" y="{gy}" width="{col_w}" height="54" rx="20" '
                f'fill="rgba(30,41,59,0.55)"/>'
                f'<text x="{gx + 18}" y="{gy + 22}" fill="{accent_stroke}" font-size="10" font-weight="800" letter-spacing="0.08em">'
                f'MÓDULO {m_idx + 1} · {completed_mod}/{len(m_topics)} DOMINADOS</text>'
                f'<text x="{gx + 18}" y="{gy + 41}" fill="#f1f5f9" font-size="13" font-weight="700">{mod_title_esc}</text>'
                f'</g>'
            )

            for t_idx, node in enumerate(m_topics):
                nx = gx + 18
                ny = gy + header_h + t_idx * row_step
                coords[node.id] = (nx, ny, m_idx, t_idx)

                if node.estado == EstadoTema.COMPLETADO.value:
                    fill = "rgba(6, 78, 59, 0.55)"
                    stroke = "#10b981"
                    badge_bg = "rgba(16, 185, 129, 0.2)"
                    badge_fg = "#6ee7b7"
                    status_txt = "✔ Dominado"
                elif node.estado == EstadoTema.EN_PROGRESO.value:
                    fill = "rgba(30, 58, 138, 0.55)"
                    stroke = "#3b82f6"
                    badge_bg = "rgba(59, 130, 246, 0.22)"
                    badge_fg = "#93c5fd"
                    status_txt = "⚡ En progreso"
                elif node.is_blocked:
                    fill = "rgba(15, 23, 42, 0.85)"
                    stroke = "#475569"
                    badge_bg = "rgba(71, 85, 105, 0.3)"
                    badge_fg = "#94a3b8"
                    status_txt = "🔒 Bloqueado"
                elif node.disponible:
                    fill = "rgba(8, 47, 73, 0.65)"
                    stroke = "#38bdf8"
                    badge_bg = "rgba(56, 189, 248, 0.2)"
                    badge_fg = "#7dd3fc"
                    status_txt = "🚀 Disponible"
                else:
                    fill = "rgba(30, 41, 59, 0.75)"
                    stroke = "#64748b"
                    badge_bg = "rgba(100, 116, 139, 0.25)"
                    badge_fg = "#cbd5e1"
                    status_txt = "Pendiente"

                if node.is_critical_path and node.estado != EstadoTema.COMPLETADO.value:
                    stroke = "#f59e0b"

                line1, line2 = self._split_topic_title(node.titulo)
                line1_esc = html.escape(line1)
                line2_esc = html.escape(line2)
                full_title_esc = html.escape(node.titulo)
                rank = topo_rank.get(node.id, t_idx + 1)

                crit_pill = ""
                if node.is_critical_path:
                    crit_pill = (
                        f'<rect x="{nx + card_w - 78}" y="{ny + 10}" width="66" height="18" rx="9" '
                        f'fill="rgba(245,158,11,0.18)" stroke="#f59e0b" stroke-width="1"/>'
                        f'<text x="{nx + card_w - 45}" y="{ny + 22}" text-anchor="middle" fill="#fcd34d" font-size="9.5" font-weight="800">⚡ Crítico</text>'
                    )

                svg_nodes.append(
                    f'<g id="node-t_{node.id}" class="dag-node" data-node-id="t_{node.id}" '
                    f'data-topic-id="{node.id}" data-title="{full_title_esc}" '
                    f'data-critical="{1 if node.is_critical_path else 0}" '
                    f'data-available="{1 if node.disponible else 0}" '
                    f'tabindex="0" role="button">'
                    f'<title>{full_title_esc} ({status_txt})</title>'
                    f'<rect class="node-card" x="{nx}" y="{ny}" width="{card_w}" height="{card_h}" rx="14" '
                    f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
                    f'<rect x="{nx + 12}" y="{ny + 10}" width="34" height="18" rx="6" fill="rgba(2,6,23,0.7)" stroke="rgba(148,163,184,0.25)"/>'
                    f'<text x="{nx + 29}" y="{ny + 22}" text-anchor="middle" fill="#38bdf8" font-size="10" font-weight="800" font-family="monospace">#{rank}</text>'
                    f'<rect x="{nx + 52}" y="{ny + 10}" width="92" height="18" rx="9" fill="{badge_bg}"/>'
                    f'<text x="{nx + 98}" y="{ny + 22}" text-anchor="middle" fill="{badge_fg}" font-size="10" font-weight="700">{status_txt}</text>'
                    f'{crit_pill}'
                    f'<text x="{nx + 14}" y="{ny + 48}" fill="#f8fafc" font-size="12.5" font-weight="700">{line1_esc}</text>'
                    f'<text x="{nx + 14}" y="{ny + 66}" fill="#94a3b8" font-size="11.5" font-weight="500">{line2_esc}</text>'
                    f'</g>'
                )

        svg_edges: list[str] = []
        seen_pairs: set[tuple[int, int]] = set()
        edges_json_list: list[dict[str, Any]] = []

        for e in graph.edges:
            u, v = e.tema_origen_id, e.tema_destino_id
            if u not in coords or v not in coords:
                continue
            if (u, v) in seen_pairs:
                continue
            seen_pairs.add((u, v))
            edges_json_list.append({"from": u, "to": v, "tipo": e.tipo, "inferida": e.inferida})

            ux, uy, u_mod, u_row = coords[u]
            vx, vy, v_mod, v_row = coords[v]

            if u_mod == v_mod and v_row == u_row + 1:
                x1 = ux + card_w / 2
                y1 = uy + card_h
                x2 = vx + card_w / 2
                y2 = vy - 6
                path_d = f"M {x1:.1f} {y1:.1f} L {x2:.1f} {y2:.1f}"
            elif u_mod == v_mod:
                x1 = ux + card_w
                y1 = uy + card_h / 2
                x2 = vx + card_w
                y2 = vy + card_h / 2
                span = max(36, abs(v_row - u_row) * 22)
                path_d = f"M {x1:.1f} {y1:.1f} C {x1 + span:.1f} {y1:.1f}, {x2 + span:.1f} {y2:.1f}, {x2 + 4:.1f} {y2:.1f}"
            elif u_mod < v_mod:
                x1 = ux + card_w
                y1 = uy + card_h / 2
                x2 = vx - 6
                y2 = vy + card_h / 2
                dx = max(40, (x2 - x1) * 0.5)
                path_d = f"M {x1:.1f} {y1:.1f} C {x1 + dx:.1f} {y1:.1f}, {x2 - dx:.1f} {y2:.1f}, {x2:.1f} {y2:.1f}"
            else:
                x1 = ux
                y1 = uy + card_h / 2
                x2 = vx + card_w + 6
                y2 = vy + card_h / 2
                dx = max(40, abs(x1 - x2) * 0.5)
                path_d = f"M {x1:.1f} {y1:.1f} C {x1 - dx:.1f} {y1:.1f}, {x2 + dx:.1f} {y2:.1f}, {x2:.1f} {y2:.1f}"

            u_node = nodes_by_id[u]
            v_node = nodes_by_id[v]
            both_crit = u_node.is_critical_path and v_node.is_critical_path
            if both_crit:
                stroke_col = "#f59e0b"
                marker = "url(#arrow-crit)"
                width = "2.4"
            elif e.tipo == TIPO_ESTRICTA and not e.inferida:
                stroke_col = "#38bdf8"
                marker = "url(#arrow-strict)"
                width = "2.1"
            else:
                stroke_col = "#64748b"
                marker = "url(#arrow-muted)"
                width = "1.7"

            dash = 'stroke-dasharray="6 4"' if (e.inferida or e.tipo != TIPO_ESTRICTA) else ""
            anim_cls = "edge-flow" if not e.inferida else "edge-infer"

            svg_edges.append(
                f'<path class="dag-edge {anim_cls}" data-from="{u}" data-to="{v}" '
                f'd="{path_d}" fill="none" stroke="{stroke_col}" stroke-width="{width}" '
                f'{dash} marker-end="{marker}" stroke-linecap="round"/>'
            )

        edges_json = json.dumps(edges_json_list, ensure_ascii=False)
        lanes_markup = "\n".join(svg_lanes)
        edges_markup = "\n".join(svg_edges)
        nodes_markup = "\n".join(svg_nodes)

        return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{titulo_esc} · Mapa Interactivo</title>
<!-- aulento-dag-bridge-v2 -->
<style>
  :root {{
    color-scheme: dark;
  }}
  * {{ box-sizing: border-box; user-select: none; }}
  body {{
    margin: 0;
    height: 100vh;
    width: 100vw;
    overflow: hidden;
    background-color: #020617;
    background-image:
      radial-gradient(rgba(56, 189, 248, 0.14) 1.25px, transparent 1.25px),
      radial-gradient(circle at 15% 15%, rgba(30, 58, 138, 0.28) 0%, transparent 55%),
      radial-gradient(circle at 85% 85%, rgba(88, 28, 135, 0.2) 0%, transparent 55%);
    background-size: 24px 24px, 100% 100%, 100% 100%;
    font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: #f8fafc;
    display: flex;
    flex-direction: column;
  }}
  .hud-top {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 10px 14px;
    background: rgba(15, 23, 42, 0.88);
    border-bottom: 1px solid rgba(51, 65, 85, 0.8);
    backdrop-filter: blur(10px);
    z-index: 20;
  }}
  .hud-title-group {{
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }}
  .hud-title {{
    font-size: 13px;
    font-weight: 800;
    color: #f8fafc;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 320px;
  }}
  .hud-meta {{
    font-size: 11px;
    color: #94a3b8;
    background: rgba(2, 6, 23, 0.7);
    padding: 3px 9px;
    border-radius: 999px;
    border: 1px solid rgba(51, 65, 85, 0.8);
    white-space: nowrap;
  }}
  .hud-controls {{
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }}
  .hud-btn {{
    background: rgba(30, 41, 59, 0.9);
    color: #e2e8f0;
    border: 1px solid rgba(71, 85, 105, 0.8);
    border-radius: 10px;
    padding: 5px 10px;
    font-size: 11px;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.15s ease;
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }}
  .hud-btn:hover {{
    background: rgba(51, 65, 85, 0.95);
    color: #ffffff;
    border-color: #38bdf8;
  }}
  .hud-btn.active {{
    background: rgba(2, 132, 199, 0.35);
    color: #7dd3fc;
    border-color: #38bdf8;
  }}
  .viewport {{
    flex: 1 1 auto;
    position: relative;
    overflow: hidden;
    cursor: grab;
  }}
  .viewport.dragging {{
    cursor: grabbing;
  }}
  svg#map-svg {{
    width: 100%;
    height: 100%;
    display: block;
  }}
  g.dag-node {{
    cursor: pointer;
    transition: opacity 0.2s ease, filter 0.2s ease;
  }}
  g.dag-node:hover rect.node-card {{
    stroke: #38bdf8;
    stroke-width: 3px;
    filter: drop-shadow(0 0 16px rgba(56, 189, 248, 0.55));
  }}
  g.dag-node.is-selected rect.node-card {{
    stroke: #a5b4fc !important;
    stroke-width: 3.5px !important;
    filter: drop-shadow(0 0 22px rgba(129, 140, 248, 0.9)) !important;
  }}
  g.dag-node.is-prereq rect.node-card {{
    stroke: #f97316 !important;
    stroke-width: 3px !important;
    filter: drop-shadow(0 0 18px rgba(249, 115, 22, 0.8)) !important;
  }}
  g.dag-node.is-dependent rect.node-card {{
    stroke: #10b981 !important;
    stroke-width: 3px !important;
    filter: drop-shadow(0 0 18px rgba(16, 185, 129, 0.8)) !important;
  }}
  g.dag-node.is-dimmed {{
    opacity: 0.22;
    filter: grayscale(70%);
  }}
  path.dag-edge {{
    transition: opacity 0.2s ease, stroke-width 0.2s ease, stroke 0.2s ease;
  }}
  path.dag-edge.is-dimmed {{
    opacity: 0.12;
  }}
  path.dag-edge.is-prereq {{
    stroke: #f97316 !important;
    stroke-width: 3px !important;
    opacity: 1 !important;
  }}
  path.dag-edge.is-dependent {{
    stroke: #10b981 !important;
    stroke-width: 3px !important;
    opacity: 1 !important;
  }}
  body.flow-active path.dag-edge {{
    stroke-dasharray: 8 6 !important;
    animation: flowDash 1.2s linear infinite;
  }}
  @keyframes flowDash {{
    to {{ stroke-dashoffset: -28; }}
  }}
  .hud-bottom {{
    position: absolute;
    left: 14px;
    bottom: 12px;
    right: 14px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    pointer-events: none;
    z-index: 15;
  }}
  .selection-pill {{
    pointer-events: auto;
    background: rgba(15, 23, 42, 0.92);
    border: 1px solid rgba(99, 102, 241, 0.5);
    border-radius: 12px;
    padding: 6px 12px;
    font-size: 11.5px;
    color: #e2e8f0;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    gap: 10px;
  }}
</style>
</head>
<body class="flow-active">
  <div class="hud-top">
    <div class="hud-title-group">
      <span class="hud-title" title="{titulo_esc}">🗺️ {titulo_esc}</span>
      <span class="hud-meta">{len(graph.nodes)} temas · {len(valid_mods)} módulos · ⚡ {len(graph.critical_path)} críticos</span>
    </div>
    <div class="hud-controls">
      <button type="button" class="hud-btn active" id="btn-filter-all" onclick="setMapFilter('all')">Todos</button>
      <button type="button" class="hud-btn" id="btn-filter-critical" onclick="setMapFilter('critical')">⚡ Ruta Crítica</button>
      <button type="button" class="hud-btn" id="btn-filter-available" onclick="setMapFilter('available')">🚀 Disponibles</button>
      <button type="button" class="hud-btn active" id="btn-toggle-flow" onclick="toggleFlowAnim()">🌊 Flujo</button>
      <button type="button" class="hud-btn" onclick="zoomBy(1.08)" title="Acercar suavemente">＋</button>
      <button type="button" class="hud-btn" onclick="zoomBy(0.925)" title="Alejar suavemente">－</button>
      <button type="button" class="hud-btn" onclick="fitToScreen()" title="Encuadrar mapa completo">⟲ Ajustar</button>
      <button type="button" class="hud-btn" onclick="exportMapSvg()" title="Descargar diagrama SVG">📥 SVG</button>
    </div>
  </div>

  <div class="viewport" id="viewport">
    <svg id="map-svg" viewBox="0 0 {svg_w} {svg_h}" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <marker id="arrow-strict" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 1.5 L 8.5 5 L 0 8.5 z" fill="#38bdf8"/>
        </marker>
        <marker id="arrow-crit" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
          <path d="M 0 1.5 L 8.5 5 L 0 8.5 z" fill="#f59e0b"/>
        </marker>
        <marker id="arrow-muted" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="5.5" markerHeight="5.5" orient="auto-start-reverse">
          <path d="M 0 1.5 L 8.5 5 L 0 8.5 z" fill="#64748b"/>
        </marker>
      </defs>
      <g id="pan-zoom-stage">
        {lanes_markup}
        {edges_markup}
        {nodes_markup}
      </g>
    </svg>
    <div class="hud-bottom">
      <div class="selection-pill" id="selection-status">
        <span>💡 Arrastra para mover · Rueda para zoom · Haz clic en un tema para inspeccionar sus prelaciones</span>
      </div>
    </div>
  </div>

<script>
(function() {{
  const EDGES = {edges_json};
  const viewport = document.getElementById('viewport');
  const stage = document.getElementById('pan-zoom-stage');
  const statusEl = document.getElementById('selection-status');
  const SVG_W = {svg_w};
  const SVG_H = {svg_h};

  let scale = 1;
  let tx = 0;
  let ty = 0;
  let isDragging = false;
  let startX = 0;
  let startY = 0;
  let dragMoved = false;

  function applyTransform() {{
    stage.setAttribute('transform', `translate(${{tx}}, ${{ty}}) scale(${{scale}})`);
  }}

  window.fitToScreen = function() {{
    scale = 1;
    tx = 0;
    ty = 0;
    applyTransform();
  }};

  const MIN_SCALE = 0.5;
  const MAX_SCALE = 2.5;

  // Convierte un punto de pantalla a coordenadas del viewBox del SVG
  function toSvgPoint(clientX, clientY) {{
    const svgEl = document.getElementById('map-svg');
    const pt = svgEl.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    const ctm = svgEl.getScreenCTM();
    return ctm ? pt.matrixTransform(ctm.inverse()) : {{ x: SVG_W / 2, y: SVG_H / 2 }};
  }}

  // Zoom anclado a un punto: lo que está bajo el cursor se queda quieto
  function zoomAt(factor, px, py) {{
    const next = Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale * factor));
    const real = next / scale;
    if (real === 1) return;
    tx = px - (px - tx) * real;
    ty = py - (py - ty) * real;
    scale = next;
    applyTransform();
  }}

  window.zoomBy = function(factor) {{
    zoomAt(factor, SVG_W / 2, SVG_H / 2);
  }};

  window.toggleFlowAnim = function() {{
    const active = document.body.classList.toggle('flow-active');
    const btn = document.getElementById('btn-toggle-flow');
    if (btn) btn.classList.toggle('active', active);
  }};

  window.setMapFilter = function(mode) {{
    ['all', 'critical', 'available'].forEach(m => {{
      const b = document.getElementById('btn-filter-' + m);
      if (b) b.classList.toggle('active', m === mode);
    }});
    document.querySelectorAll('g.dag-node').forEach(g => {{
      g.classList.remove('is-selected', 'is-prereq', 'is-dependent', 'is-dimmed');
      if (mode === 'critical' && g.dataset.critical !== '1') g.classList.add('is-dimmed');
      else if (mode === 'available' && g.dataset.available !== '1') g.classList.add('is-dimmed');
    }});
    document.querySelectorAll('path.dag-edge').forEach(p => {{
      p.classList.remove('is-prereq', 'is-dependent', 'is-dimmed');
      if (mode !== 'all') p.classList.add('is-dimmed');
    }});
  }};

  window.exportMapSvg = function() {{
    const svgEl = document.getElementById('map-svg');
    const source = new XMLSerializer().serializeToString(svgEl);
    const blob = new Blob([source], {{ type: 'image/svg+xml;charset=utf-8' }});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'mapa-aprendizaje.svg';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }};

  function selectTopic(topicId, notifyParent) {{
    const nodes = document.querySelectorAll('g.dag-node');
    const edges = document.querySelectorAll('path.dag-edge');
    if (!topicId) {{
      nodes.forEach(g => g.classList.remove('is-selected', 'is-prereq', 'is-dependent', 'is-dimmed'));
      edges.forEach(p => p.classList.remove('is-prereq', 'is-dependent', 'is-dimmed'));
      statusEl.innerHTML = '<span>💡 Arrastra para mover · Rueda para zoom · Haz clic en un tema para inspeccionar sus prelaciones</span>';
      return;
    }}

    const prereqs = new Set();
    const dependents = new Set();
    EDGES.forEach(e => {{
      if (e.to === topicId) prereqs.add(e.from);
      if (e.from === topicId) dependents.add(e.to);
    }});

    let selectedTitle = 'Tema #' + topicId;
    nodes.forEach(g => {{
      const id = Number(g.dataset.topicId);
      g.classList.remove('is-selected', 'is-prereq', 'is-dependent', 'is-dimmed');
      if (id === topicId) {{
        g.classList.add('is-selected');
        selectedTitle = g.dataset.title || selectedTitle;
      }} else if (prereqs.has(id)) {{
        g.classList.add('is-prereq');
      }} else if (dependents.has(id)) {{
        g.classList.add('is-dependent');
      }} else {{
        g.classList.add('is-dimmed');
      }}
    }});

    edges.forEach(p => {{
      const u = Number(p.dataset.from);
      const v = Number(p.dataset.to);
      p.classList.remove('is-prereq', 'is-dependent', 'is-dimmed');
      if (v === topicId) p.classList.add('is-prereq');
      else if (u === topicId) p.classList.add('is-dependent');
      else p.classList.add('is-dimmed');
    }});

    statusEl.innerHTML = `<span>🎯 <strong>${{escaparHtml(selectedTitle)}}</strong> · <span style="color:#fb923c">🟠 ${{prereqs.size}} requisito(s)</span> · <span style="color:#34d399">🟢 Desbloquea ${{dependents.size}}</span> <button onclick="window._clearSel(event)" style="margin-left:8px;background:#1e293b;border:1px solid #475569;color:#cbd5e1;border-radius:6px;padding:2px 7px;cursor:pointer;font-size:10px;">Limpiar ✕</button></span>`;

    if (notifyParent && window.parent && window.parent !== window) {{
      window.parent.postMessage({{ type: 'dag-select-topic', topicId: topicId }}, window.location.origin);
    }}
  }}

  // El título viene de dataset (el navegador ya deshizo el escape): se vuelve a escapar antes de usarlo como HTML
  function escaparHtml(texto) {{
    return String(texto).replace(/[&<>"']/g, c => ({{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }}[c]));
  }}

  window._clearSel = function(ev) {{
    if (ev) ev.stopPropagation();
    selectTopic(null, false);
  }};

  viewport.addEventListener('pointerdown', e => {{
    // Un clic nuevo arranca sin arrastre previo, también sobre un tema: si no, tras mover el mapa el clic se ignora
    dragMoved = false;
    if (e.target.closest('g.dag-node') || e.target.closest('button')) return;
    isDragging = true;
    const p0 = toSvgPoint(e.clientX, e.clientY);
    startX = p0.x - tx;
    startY = p0.y - ty;
    viewport.classList.add('dragging');
  }});

  window.addEventListener('pointermove', e => {{
    if (!isDragging) return;
    const p = toSvgPoint(e.clientX, e.clientY);
    const nx = p.x - startX;
    const ny = p.y - startY;
    if (Math.abs(nx - tx) > 3 || Math.abs(ny - ty) > 3) dragMoved = true;
    tx = nx;
    ty = ny;
    applyTransform();
  }});

  window.addEventListener('pointerup', () => {{
    if (!isDragging) return;
    isDragging = false;
    viewport.classList.remove('dragging');
  }});

  viewport.addEventListener('click', e => {{
    if (dragMoved) return;
    const nodeEl = e.target.closest('g.dag-node');
    if (nodeEl) {{
      selectTopic(Number(nodeEl.dataset.topicId), true);
    }} else if (!e.target.closest('button')) {{
      selectTopic(null, false);
    }}
  }});

  window.centerOnTopic = function(topicId) {{
    const nodeEl = document.querySelector(`g.dag-node[data-topic-id="${{topicId}}"]`);
    if (!nodeEl) return;
    const card = nodeEl.querySelector('.node-card');
    if (!card) return;
    const cx = parseFloat(card.getAttribute('x')) + parseFloat(card.getAttribute('width')) / 2;
    const cy = parseFloat(card.getAttribute('y')) + parseFloat(card.getAttribute('height')) / 2;
    const targetScale = Math.max(0.85, Math.min(1.25, scale));
    tx = (SVG_W / 2) - cx * targetScale;
    ty = (SVG_H / 2) - cy * targetScale;
    scale = targetScale;
    applyTransform();
  }};

  viewport.addEventListener('wheel', e => {{
    e.preventDefault();
    // Zoom ultrasuave amortiguado para evitar saltos bruscos
    const rawDelta = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
    const clampedDelta = Math.max(-80, Math.min(80, rawDelta));
    const factor = Math.exp(-clampedDelta * 0.0006);
    const p = toSvgPoint(e.clientX, e.clientY);
    zoomAt(factor, p.x, p.y);
  }}, {{ passive: false }});

  window.addEventListener('message', ev => {{
    if (ev.origin !== window.location.origin || !ev.data || ev.data.type !== 'dag-highlight-topic') return;
    const tid = Number(ev.data.topicId);
    selectTopic(tid, false);
    if (ev.data.center && window.centerOnTopic) {{
      window.centerOnTopic(tid);
    }}
  }});
}})();
</script>
</body>
</html>"""
