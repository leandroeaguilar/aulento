"""Lector seguro y de solo lectura para el Vault de Obsidian."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Dict, List, Optional

from aulento.vault.models import VaultNote
from aulento.vault.parser import parse_note
from aulento.vault.rutas import resolver_en_vault

ALLOWED_FOLDERS = ["04 Knowledge", "06 Raw", "02 MOCs"]

SAMPLE_VAULT_NOTES: List[Dict[str, Any]] = [
    {
        "subpath": "04 Knowledge/Conceptos/Star Schema y Modelado Dimensional.md",
        "folder": "04 Knowledge",
        "title": "Star Schema y Modelado Dimensional",
        "content": (
            "---\n"
            "type: Concepto\n"
            "title: Star Schema y Modelado Dimensional\n"
            "tags: [bi, data-warehouse, kimball, sql]\n"
            "sources: [Ralph Kimball - The Data Warehouse Toolkit]\n"
            "---\n\n"
            "# Star Schema y Modelado Dimensional\n\n"
            "El **Star Schema** (Esquema en Estrella) es un estilo de diseño de base de datos relacional "
            "optimizado para consultas analíticas masivas (OLAP) propuesto por [[Ralph Kimball]].\n\n"
            "## Componentes Fundamentales\n"
            "1. **[[Fact Tables]] (Tablas de Hechos):** Almacenan métricas cuantitativas del negocio "
            "(ej. monto de venta, cantidad de ítems) y claves foráneas hacia las dimensiones.\n"
            "2. **[[Dimension Tables]] (Tablas de Dimensiones):** Contienen atributos descriptivos del contexto "
            "(ej. cliente, fecha, sucursal, producto). Suelen estar desnormalizadas para evitar múltiples JOINs.\n"
            "3. **Surrogate Keys:** Claves artificiales autoincrementales que desacoplan el almacén analítico "
            "de las claves operacionales transaccionales (Natural Keys).\n\n"
            "## Ventajas frente a Snowflake Schema\n"
            "- Consultas SQL más sencillas y rápidas con menos JOINs.\n"
            "- Alta compatibilidad con herramientas modernas de BI como Looker, PowerBI y Tableau.\n"
            "- Facilidad para gestionar cambios históricos mediante técnicas de [[SCD]] (Slowly Changing Dimensions)."
        ),
    },
    {
        "subpath": "04 Knowledge/Arquitectura/BigQuery Dremel y Separacion de Computo.md",
        "folder": "04 Knowledge",
        "title": "BigQuery Dremel y Separación de Cómputo",
        "content": (
            "---\n"
            "type: Arquitectura\n"
            "title: BigQuery Dremel y Separación de Cómputo\n"
            "tags: [gcp, bigquery, cloud-architecture, analytics]\n"
            "sources: [Google Cloud Documentation, Dremel Paper 2010]\n"
            "---\n\n"
            "# BigQuery Dremel y Separación de Cómputo\n\n"
            "Google BigQuery es un data warehouse empresarial completamente administrado y serverless, "
            "cuyo núcleo se basa en la separación radical de cómputo y almacenamiento a través de la red [[Jupiter]].\n\n"
            "## Arquitectura Modular\n"
            "1. **Motor de Cómputo (Dremel):** Un árbol de ejecución masivamente distribuido compuesto por "
            "un nodo raíz (Root Server), servidores intermediarios y miles de trabajadores llamados [[Slots]].\n"
            "2. **Almacenamiento (Colossus):** Sistema de archivos distribuido global de Google donde los datos "
            "se almacenan en formato columnar optimizado [[Capacitor]].\n"
            "3. **In-Memory Shuffle Engine:** Permite redistribuir terabytes de datos entre slots en milisegundos "
            "sin escribir resultados intermedios en disco.\n\n"
            "## Buenas Prácticas de Optimización\n"
            "- Particionamiento por fecha o timestamp para podar bloques durante el escaneo.\n"
            "- [[Clustering por Claves]] para ordenar datos relacionados físicamente en el mismo slot.\n"
            "- Evitar `SELECT *` para reducir costos de slots y datos procesados."
        ),
    },
    {
        "subpath": "04 Knowledge/IA/Transformers y Mecanismos de Atencion.md",
        "folder": "04 Knowledge",
        "title": "Transformers y Mecanismos de Atención",
        "content": (
            "---\n"
            "type: Teoria\n"
            "title: Transformers y Mecanismos de Atención\n"
            "tags: [ia, deep-learning, nlp, transformers]\n"
            "sources: [Vaswani et al. 2017 - Attention Is All You Need]\n"
            "---\n\n"
            "# Transformers y Mecanismos de Atención\n\n"
            "La arquitectura **Transformer** eliminó la necesidad de redes neuronales recurrentes (RNN y LSTM) "
            "para procesar secuencias de lenguaje, permitiendo un paralelismo total mediante [[Self-Attention]].\n\n"
            "## Mecanismo de Scaled Dot-Product Attention\n"
            "Cada token de entrada se proyecta mediante matrices de pesos entrenables en tres vectores:\n"
            "- **Query (Q):** Lo que el token está buscando.\n"
            "- **Key (K):** La etiqueta de contenido que ofrece cada token.\n"
            "- **Value (V):** La información real transmitida por el token.\n\n"
            "La fórmula matemática fundamental es:\n"
            "$$\\text{Attention}(Q, K, V) = \\text{softmax}\\left(\\frac{QK^T}{\\sqrt{d_k}}\\right)V$$\n\n"
            "El factor de escala $\\sqrt{d_k}$ previene que el producto punto crezca excesivamente en dimensiones altas, "
            "evitando gradientes extremadamente pequeños en la función softmax.\n\n"
            "## Componentes Adicionales\n"
            "- **[[Multi-Head Attention]]:** Múltiples cabezas de atención que aprenden relaciones sintácticas y semánticas en paralelo.\n"
            "- **[[Positional Encoding]]:** Inyección de vectores sinusoidales para que el modelo reconozca el orden relativo de las palabras."
        ),
    },
    {
        "subpath": "04 Knowledge/Ingenieria/Webhooks y Event-Driven Architecture.md",
        "folder": "04 Knowledge",
        "title": "Webhooks y Arquitectura Orientada a Eventos",
        "content": (
            "---\n"
            "type: Ingenieria\n"
            "title: Webhooks y Arquitectura Orientada a Eventos\n"
            "tags: [backend, api, arquitectura, eventos]\n"
            "sources: [Microservice Patterns - Chris Richardson]\n"
            "---\n\n"
            "# Webhooks y Arquitectura Orientada a Eventos\n\n"
            "Un **Webhook** es un patrón de comunicación HTTP asíncrono e invertido (Reverse API) "
            "donde un sistema emisor notifica a un receptor enviando un payload JSON ante la ocurrencia de un evento.\n\n"
            "## Diferencia con Polling Tradicional\n"
            "- En [[Polling]], el cliente consulta repetidamente cada N segundos (`GET /status`), generando sobrecarga y latencia.\n"
            "- En Webhooks, el servidor emisor envía una petición `POST` inmediata apenas ocurre la acción.\n\n"
            "## Patrones de Resiliencia Obligatorios\n"
            "1. **[[Idempotencia]]:** Uso de identificadores únicos (`Event-ID`) para evitar procesar dos veces el mismo evento si hay reintentos.\n"
            "2. **Firma Criptográfica (HMAC SHA-256):** Validación de autenticidad en el encabezado `X-Hub-Signature` mediante un secreto compartido.\n"
            "3. **Buffer Asíncrono y [[Dead Letter Queue]]:** El endpoint receptor responde HTTP 200 inmediatamente y encola el evento a un message broker (ej. RabbitMQ, Pub/Sub, Kafka) para desacoplar el procesamiento pesado."
        ),
    },
    {
        "subpath": "02 MOCs/MOC Inteligencia Artificial y Datos.md",
        "folder": "02 MOCs",
        "title": "MOC Inteligencia Artificial y Datos",
        "content": (
            "---\n"
            "type: MOC\n"
            "title: MOC Inteligencia Artificial y Datos\n"
            "tags: [moc, data, ia, hub]\n"
            "---\n\n"
            "# MOC — Inteligencia Artificial, BI y Arquitectura\n\n"
            "Mapa de Contenido (Map of Content) que centraliza las conexiones neuronales del conocimiento personal.\n\n"
            "## Modelado de Datos y Analytics\n"
            "- [[Star Schema y Modelado Dimensional]]: Principios fundamentales de modelado OLAP y almacenes analíticos.\n"
            "- [[BigQuery Dremel y Separacion de Computo]]: Arquitectura de data warehouse serverless a escala petabyte.\n\n"
            "## Inteligencia Artificial y Deep Learning\n"
            "- [[Transformers y Mecanismos de Atencion]]: Arquitectura de modelos de lenguaje modernos y atención multicabezal.\n\n"
            "## Arquitectura de Software y Sistemas Distribuidos\n"
            "- [[Webhooks y Event-Driven Architecture]]: Comunicación asíncrona reactiva y resiliencia en APIs."
        ),
    },
]


def sembrar_notas_de_muestra(vault_path: Path) -> int:
    """Copia al vault las notas de muestra que todavía no tiene; devuelve cuántas escribió.

    Solo se llama cuando la cuenta lo pide: leer un vault vacío no le agrega nada.
    """
    escritas = 0
    for note_data in SAMPLE_VAULT_NOTES:
        file_path = resolver_en_vault(vault_path, note_data["subpath"])
        if file_path.exists():
            continue
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(note_data["content"], encoding="utf-8")
        escritas += 1
    return escritas


class VaultReader:
    """Lector de solo lectura del vault de una cuenta: no ve nada fuera de la carpeta que recibe.

    `carpetas` son las que lee cuando no se le pide una en particular: las que la cuenta eligió para el tutor
    o, si no se indican, las de siempre (`ALLOWED_FOLDERS`).
    """

    def __init__(self, vault_path: Path, carpetas: Sequence[str] | None = None):
        if not isinstance(vault_path, Path):
            raise TypeError("VaultReader necesita la carpeta del vault de la cuenta.")
        self.vault_path = vault_path
        self.carpetas = list(carpetas) if carpetas else list(ALLOWED_FOLDERS)

    def list_notes(self, folder: Optional[str] = None) -> List[VaultNote]:
        """Lista las notas de las carpetas del lector, o de `folder` si se indica; cada nota una sola vez.

        Levanta `RutaFueraDelVaultError` si `folder` apunta fuera del vault.
        """
        notes: List[VaultNote] = []
        if folder:
            # Una carpeta que sale del vault no es «sin notas»
            resolver_en_vault(self.vault_path, folder)
        if not self.vault_path.exists():
            return notes

        vault_root = self.vault_path.resolve()
        # Una carpeta elegida puede estar dentro de otra también elegida: sus notas no se repiten
        vistas: set[Path] = set()

        for target_folder in [folder] if folder else self.carpetas:
            folder_dir = (self.vault_path / target_folder).resolve()
            if not folder_dir.is_relative_to(vault_root) or not folder_dir.exists():
                continue

            for file_path in folder_dir.rglob("*.md"):
                try:
                    # Confinamiento contra ataques de symlink
                    resolved_file = file_path.resolve()
                    if not resolved_file.is_relative_to(vault_root) or file_path in vistas:
                        continue
                    vistas.add(file_path)

                    # Carpetas de sistema u ocultas del vault (.obsidian, .trash); las de más arriba no cuentan
                    if any(part.startswith(".") for part in resolved_file.relative_to(vault_root).parts):
                        continue

                    note = parse_note(file_path, relative_to=vault_root)
                    notes.append(note)
                except Exception:
                    continue

        return notes

    def get_note(self, note_id: str) -> Optional[VaultNote]:
        """Obtiene una nota específica por su identificador o título.

        Levanta `RutaFueraDelVaultError` si el identificador apunta fuera del vault.
        """
        resolver_en_vault(self.vault_path, note_id)
        normalized_id = note_id.replace("\\", "/").lower().strip()
        all_notes = self.list_notes()

        for note in all_notes:
            if note.id.lower() == normalized_id:
                return note
            if note.title.lower() == normalized_id:
                return note
            if note.path.replace("\\", "/").lower().endswith(normalized_id + ".md"):
                return note

        return None

    def search_notes(self, query: str) -> List[VaultNote]:
        """Busca notas por coincidencia en título, contenido, tags o wikilinks."""
        q = query.lower().strip()
        if not q:
            return self.list_notes()

        matched: List[VaultNote] = []
        for note in self.list_notes():
            title_match = q in note.title.lower()
            tag_match = any(q in t.lower() for t in note.tags)
            wikilink_match = any(q in wl.target.lower() for wl in note.wikilinks)
            content_match = q in note.clean_text.lower()

            if title_match or tag_match or wikilink_match or content_match:
                matched.append(note)

        return matched

    def get_vault_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas generales del vault indexado."""
        notes = self.list_notes()
        all_tags = set()
        all_wikilinks = 0
        folder_counts: Dict[str, int] = {}

        for n in notes:
            all_tags.update(n.tags)
            all_wikilinks += len(n.wikilinks)
            folder_counts[n.folder] = folder_counts.get(n.folder, 0) + 1

        return {
            "total_notes": len(notes),
            "folder_distribution": folder_counts,
            "total_wikilinks": all_wikilinks,
            "total_unique_tags": len(all_tags),
            "tags": sorted(list(all_tags)),
        }
