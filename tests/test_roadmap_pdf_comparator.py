"""Pruebas unitarias para el extractor y comparador de syllabi en PDF."""

import json

import pytest
from aulento.models.roadmap import (
    RoadmapDetail,
    RoadmapModule,
    RoadmapTopic,
    EstadoTema,
    FuenteTema,
)
from aulento.roadmap.pdf_comparator import RoadmapPDFComparator
from conftest import cuenta_en
from ia_falsa import ia_sustituida, respuesta_de
from aulento.core.gemini_gateway import GeminiGateway
from aulento.core.ia.pasarela import PasarelaDeIA
from aulento.core.ia.tipos import MIME_PDF, CuotaAgotada


@pytest.fixture
def sample_roadmap():
    return RoadmapDetail(
        id=1,
        titulo="Data Engineer GCP",
        progreso_pct=0.0,
        total_temas=2,
        temas_completados=0,
        modulos=[
            RoadmapModule(
                id=10,
                ruta_id=1,
                titulo="Streaming",
                orden=1,
                temas=[
                    RoadmapTopic(
                        id=101,
                        modulo_id=10,
                        titulo="Kafka Brokers y Particiones",
                        orden=1,
                        estado=EstadoTema.PENDIENTE,
                        fuente=FuenteTema.CURADA,
                    ),
                    RoadmapTopic(
                        id=102,
                        modulo_id=10,
                        titulo="BigQuery Partitioning",
                        orden=2,
                        estado=EstadoTema.PENDIENTE,
                        fuente=FuenteTema.CURADA,
                    ),
                ],
            )
        ],
    )


def test_extract_text_from_pdf():
    # PDF sintético mínimo con operadores Tj
    dummy_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Length 60 >> stream\n"
        b"BT\n"
        b"/F1 12 Tf\n"
        b"(Apache Flink StateBackend) Tj\n"
        b"(Kafka Connect Debezium CDC) Tj\n"
        b"ET\n"
        b"endstream\n"
        b"endobj\n"
        b"trailer << /Root 1 0 R >>\n"
        b"%%EOF"
    )
    text = RoadmapPDFComparator.extract_text_from_pdf(dummy_pdf)
    assert "Apache Flink" in text or "Kafka" in text


def test_compare_syllabus_fallback(sample_roadmap):
    dummy_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Length 120 >> stream\n"
        b"BT\n"
        b"/F1 12 Tf\n"
        b"(BigQuery Partitioning y Clustering) Tj\n"
        b"(Apache Iceberg Time Travel) Tj\n"
        b"(dbt Cloud Orchestration) Tj\n"
        b"ET\n"
        b"endstream\n"
        b"endobj\n"
        b"%%EOF"
    )
    comparator = RoadmapPDFComparator(PasarelaDeIA.con_conexion_propia(cuenta_en()))
    with ia_sustituida(sin_clave=True):
        result = comparator.compare_syllabus(sample_roadmap, dummy_pdf, filename="blueprint_gcp.pdf")

        assert result.total_syllabus_topics > 0
        # BigQuery debería haber coincidido
        assert any("BigQuery" in m for m in result.matched_topics)
        # Iceberg o dbt deberían aparecer como gaps
        assert len(result.gap_topics) >= 1
        assert any("Iceberg" in g.titulo or "dbt" in g.titulo for g in result.gap_topics)
        assert len(result.recommendations) > 0
        assert (result.is_fallback, result.motivo_sin_ia) == (True, None)


PDF_DE_PRUEBA = b"%PDF-1.4\nstream\nBT\n(Apache Iceberg Time Travel) Tj\nET\nendstream\n%%EOF"
COMPARACION_DE_LA_IA = {
    "total_syllabus_topics": 2,
    "matched_topics": ["BigQuery Partitioning"],
    "gap_topics": [{"titulo": "Apache Iceberg", "descripcion": "Formato de tabla abierto", "modulo_sugerido": "Lakehouse"}],
    "recommendations": ["Sumar Iceberg"],
    "summary": "50% de cobertura",
}


def test_el_comparador_exige_la_pasarela_de_ia_de_la_cuenta():
    for otra_cosa in (None, "clave", GeminiGateway.con_conexion_propia(cuenta_en())):
        with pytest.raises(TypeError, match="pasarela de IA de la cuenta"):
            RoadmapPDFComparator(otra_cosa)


@pytest.mark.parametrize("proveedor", ["gemini", "anthropic", "openai"])
def test_el_pdf_viaja_como_adjunto_y_la_comparacion_se_lee_de_cualquier_proveedor(sample_roadmap, proveedor):
    comparator = RoadmapPDFComparator(PasarelaDeIA.con_conexion_propia(cuenta_en()))
    respuesta = respuesta_de("```json\n" + json.dumps(COMPARACION_DE_LA_IA) + "\n```", proveedor=proveedor, modelo="modelo-de-prueba")

    with ia_sustituida(siempre=respuesta) as modelo:
        result = comparator.compare_syllabus(sample_roadmap, PDF_DE_PRUEBA, filename="blueprint.pdf")

    pedido, endpoint_tipo, _ = modelo.call_args.args
    assert endpoint_tipo == "pdf_compare"
    assert [(adjunto.mime, adjunto.datos) for adjunto in pedido.adjuntos] == [(MIME_PDF, PDF_DE_PRUEBA)]
    assert (pedido.json, pedido.temperatura, pedido.capacidad) == (True, 0.2, "pdf")
    assert "blueprint.pdf" in pedido.usuario
    assert (result.is_fallback, result.motivo_sin_ia) == (False, None)
    assert result.matched_topics == ["BigQuery Partitioning"]
    assert [(g.titulo, g.modulo_sugerido) for g in result.gap_topics] == [("Apache Iceberg", "Lakehouse")]
    assert result.summary == "50% de cobertura"


def test_sin_ia_utilizable_compara_en_local_y_dice_el_motivo(sample_roadmap):
    comparator = RoadmapPDFComparator(PasarelaDeIA.con_conexion_propia(cuenta_en()))
    agotada = CuotaAgotada("La clave de Gemini de tu cuenta agotó su cuota.", proveedor="gemini", estado=429)

    with ia_sustituida(siempre=agotada):
        sin_cuota = comparator.compare_syllabus(sample_roadmap, PDF_DE_PRUEBA)
    with ia_sustituida(siempre=respuesta_de("no es JSON")):
        ilegible = comparator.compare_syllabus(sample_roadmap, PDF_DE_PRUEBA)
    with ia_sustituida() as sin_pedidos:
        vacio = comparator.compare_syllabus(sample_roadmap, b"")

    assert (sin_cuota.is_fallback, sin_cuota.motivo_sin_ia) == (True, "La clave de Gemini de tu cuenta agotó su cuota.")
    assert (ilegible.is_fallback, ilegible.motivo_sin_ia) == (True, "Gemini devolvió una comparación que no se pudo leer.")
    # Un archivo vacío no se le manda a nadie
    sin_pedidos.assert_not_called()
    assert (vacio.is_fallback, vacio.motivo_sin_ia) == (True, None)
