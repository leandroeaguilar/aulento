import json

import pytest
from typer.testing import CliRunner
from fastapi.testclient import TestClient

from conftest import administrador_de_prueba, cuenta_de_prueba
from ia_falsa import ia_sustituida, respuesta_de
from aulento.core.ia.pasarela import PasarelaDeIA
from aulento.core.ia.tipos import ClaveRechazada, CuotaAgotada, IANoDisponibleError
from aulento.fsrs.harvester import OmniHarvester, HarvestCandidateCard
from aulento.web.app import app
from aulento.cli.app import cli
from aulento.db.connection import get_connection
from aulento.db.schema import init_db
from aulento.fsrs.deck_seed import seed_fsrs_deck
from aulento.db.fsrs_repository import FSRSRepository

runner = CliRunner()
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_deck(monkeypatch, tmp_path):
    """Configura base de datos temporal con esquema y tarjetas sembradas."""
    db_file = tmp_path / "test_harvester.db"
    monkeypatch.setenv("AULENTO_DB_PATH", str(db_file))
    conn = get_connection(db_file)
    init_db(conn)
    seed_fsrs_deck(conn, administrador_de_prueba(conn).id)
    conn.close()


def test_harvest_from_vault(tmp_path):
    """Verifica la extracción de conceptos y Q&A desde notas del Vault."""
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    knowledge_dir = vault_dir / "04 Knowledge" / "Cursos"
    knowledge_dir.mkdir(parents=True)

    note_file = knowledge_dir / "Kafka-Streaming.md"
    note_file.write_text(
        """# Kafka Streaming Architecture
**Consumer Lag**: Difference between the last produced offset and consumer current offset.
Q: How to handle backpressure in streaming consumers?
A: backpressure mitigation strategy
""",
        encoding="utf-8",
    )

    harvester = OmniHarvester(vault_path=vault_dir)
    candidates = harvester.harvest_from_vault(limit=10)

    assert len(candidates) >= 1
    answers = [c.respuesta_esperada for c in candidates]
    assert any("Consumer Lag" in a or "backpressure mitigation strategy" in a for a in answers)


def test_harvest_from_ai_curated_and_arbitrary():
    """Verifica generación de tarjetas a partir de temas curados (Kafka, FinOps) y temas arbitrarios."""
    harvester = OmniHarvester()

    # 1. Curado
    kafka_cards = harvester.harvest_from_ai(topic="Kafka Event Sourcing", count=5)
    assert len(kafka_cards) >= 4
    assert any("commit offsets" in c.respuesta_esperada for c in kafka_cards)

    # 2. Arbitrario
    custom_cards = harvester.harvest_from_ai(topic="Vector Indexing", count=3)
    assert len(custom_cards) == 3
    assert all("Vector Indexing" in c.item_pregunta for c in custom_cards)


def test_check_duplicates_and_commit():
    """Verifica detección de duplicados contra fsrs_items y guardado selectivo."""
    conn = get_connection()
    try:
        harvester = OmniHarvester()
        repo = FSRSRepository(conn, administrador_de_prueba(conn).id)
        initial_cards = len(repo.list_cards())

        # Un candidato que ya existe en DECK_100_ITEMS ("idempotent job") y uno totalmente nuevo
        candidates = [
            HarvestCandidateCard(
                item_pregunta="¿Cómo decir 'trabajo idempotente' (que puede reintentarse sin duplicar)?",
                respuesta_esperada="idempotent job",
                contexto_uso="Make sure it is an idempotent job.",
                categoria="data_engineering",
                source="test",
            ),
            HarvestCandidateCard(
                item_pregunta="¿Cómo decir 'estrategia de partición en frío'?",
                respuesta_esperada="cold partition tiering",
                contexto_uso="We implemented cold partition tiering in BigQuery.",
                categoria="b2_tech_data_ai",
                source="test",
            ),
        ]

        checked = harvester.check_duplicates(conn, administrador_de_prueba(conn).id, candidates)
        assert checked[0].is_duplicate is True
        assert checked[1].is_duplicate is False

        # Guardar en SQLite
        saved_count = harvester.commit_harvest(conn, administrador_de_prueba(conn).id, checked)
        assert saved_count == 1

        new_total = len(repo.list_cards())
        assert new_total == initial_cards + 1
    finally:
        conn.close()


def test_api_harvest_endpoints():
    """Verifica los endpoints REST POST /api/fsrs/harvest/preview y POST /api/fsrs/harvest/commit."""
    # 1. Preview
    res_preview = client.post(
        "/api/fsrs/harvest/preview",
        json={"source": "ai", "topic": "FastAPI", "level": "b2_tech_data_ai", "limit": 4},
    )
    assert res_preview.status_code == 200
    data_preview = res_preview.json()
    assert isinstance(data_preview, list)
    assert len(data_preview) >= 3

    # 2. Commit
    res_commit = client.post(
        "/api/fsrs/harvest/commit",
        json={"cards": data_preview},
    )
    assert res_commit.status_code == 200
    data_commit = res_commit.json()
    assert "imported_count" in data_commit
    assert data_commit["imported_count"] >= 1


def test_cli_harvest_command():
    """Verifica el comando CLI aulento fsrs harvest con flags --source y --commit."""
    result = runner.invoke(cli, [
        "fsrs",
        "harvest",
        "--source", "ai",
        "--topic", "FinOps",
        "--limit", "3",
        "--commit",
    ])
    assert result.exit_code == 0
    assert "Harvester Omnicanal" in result.output
    assert "importaron exitosamente" in result.output or "ya existen" in result.output


TARJETAS_DE_LA_IA = [
    {
        "item_pregunta": "¿Cómo decir 'desacoplamiento de cómputo y almacenamiento'?",
        "respuesta_esperada": "decoupling of compute and storage",
        "contexto_uso": "Modern lakehouse architectures rely on decoupling of compute and storage.",
    },
    {
        "item_pregunta": "¿Cómo decir 'política de retención de particiones'?",
        "respuesta_esperada": "partition retention policy",
        "contexto_uso": "Set an explicit partition retention policy to minimize storage costs.",
    },
]


@pytest.fixture
def pasarela(memory_db) -> PasarelaDeIA:
    return PasarelaDeIA(memory_db, cuenta_de_prueba(memory_db).id)


@pytest.mark.parametrize(
    ("proveedor", "nombre"), [("gemini", "Gemini"), ("anthropic", "Anthropic"), ("openai", "OpenAI")]
)
@pytest.mark.parametrize("forma", ["lista", "objeto", "bloque de código"])
def test_harvest_with_ai_lee_las_tarjetas_de_cualquier_proveedor(pasarela, proveedor, nombre, forma):
    """Las tarjetas llegan como lista, como objeto con `tarjetas` o dentro de un bloque de código: se leen igual."""
    texto = {
        "lista": json.dumps(TARJETAS_DE_LA_IA),
        "objeto": json.dumps({"tarjetas": TARJETAS_DE_LA_IA}),
        "bloque de código": "Acá van:\n```json\n" + json.dumps({"tarjetas": TARJETAS_DE_LA_IA}) + "\n```",
    }[forma]
    with ia_sustituida(siempre=respuesta_de(texto, proveedor=proveedor, modelo="modelo-de-prueba")) as modelo:
        cards = OmniHarvester().harvest_with_ai(topic="BigQuery Lakehouse", level="b2_tech_data_ai", count=2, pasarela=pasarela)

    assert [c.respuesta_esperada for c in cards] == ["decoupling of compute and storage", "partition retention policy"]
    assert cards[0].source == f"{nombre}: BigQuery Lakehouse"
    assert not cards[0].is_fallback and cards[0].motivo_sin_ia is None
    pedido, endpoint_tipo, _ = modelo.call_args.args
    assert (endpoint_tipo, pedido.json, pedido.temperatura) == ("fsrs_harvest_ai", True, 0.3)
    assert "<topic>BigQuery Lakehouse</topic>" in pedido.usuario


def test_harvest_from_vault_with_ai_mocked(pasarela):
    """Verifica la generación de tarjetas a partir de una nota de Obsidian con la IA de la cuenta."""
    mock_items = [
        {
            "item_pregunta": "¿Cómo decir 'tabla de hechos'?",
            "respuesta_esperada": "fact table",
            "contexto_uso": "Fact tables store transactional metrics.",
        }
    ]
    with ia_sustituida(siempre=respuesta_de(mock_items)) as modelo:
        cards = OmniHarvester().harvest_from_vault_with_ai(
            note_content="Star schema Fact tables store transactional metrics.",
            note_title="Star Schema",
            level="b2_tech_data_ai",
            count=1,
            pasarela=pasarela,
        )
    assert len(cards) == 1
    assert cards[0].respuesta_esperada == "fact table"
    assert cards[0].source == "Gemini (Vault: Star Schema)"
    assert modelo.call_args.args[1] == "fsrs_harvest_vault"


@pytest.mark.parametrize("texto", ["no es JSON", "[]", '{"tarjetas": [{"item_pregunta": "", "respuesta_esperada": "x"}]}', '"texto"'])
def test_una_respuesta_sin_tarjetas_utilizables_es_un_error_de_ia(pasarela, texto):
    with ia_sustituida(siempre=respuesta_de(texto)), pytest.raises(IANoDisponibleError, match="^Gemini "):
        OmniHarvester().harvest_with_ai(topic="Kafka", pasarela=pasarela)


def test_harvest_from_ai_sin_ia_sale_del_banco_local_y_dice_el_motivo_si_no_es_la_falta_de_clave(pasarela):
    agotada = CuotaAgotada("La clave de Gemini de tu cuenta agotó su cuota.", proveedor="gemini", estado=429)
    cosechador = OmniHarvester()

    with ia_sustituida(sin_clave=True):
        sin_clave = cosechador.harvest_from_ai(topic="Kafka", count=3, pasarela=pasarela)
    with ia_sustituida(siempre=agotada):
        sin_cuota = cosechador.harvest_from_ai(topic="Kafka", count=3, pasarela=pasarela)
        arbitrario = cosechador.harvest_from_ai(topic="Vector Indexing", count=3, pasarela=pasarela)
    sin_pasarela = cosechador.harvest_from_ai(topic="Kafka", count=3)

    for tarjetas in (sin_clave, sin_cuota, arbitrario, sin_pasarela):
        assert len(tarjetas) == 3 and all(t.is_fallback for t in tarjetas)
    assert {t.motivo_sin_ia for t in sin_clave} == {None} == {t.motivo_sin_ia for t in sin_pasarela}
    assert {t.motivo_sin_ia for t in sin_cuota} == {"La clave de Gemini de tu cuenta agotó su cuota."}
    assert {t.motivo_sin_ia for t in arbitrario} == {"La clave de Gemini de tu cuenta agotó su cuota."}


def test_la_cosecha_del_vault_dice_por_que_no_hubo_ia_y_no_insiste_con_un_error_de_la_cuenta(pasarela, tmp_path):
    notas = tmp_path / "vault" / "04 Knowledge" / "Cursos"
    notas.mkdir(parents=True)
    for n in (1, 2, 3):
        (notas / f"Nota {n}.md").write_text(f"# Nota {n}\n\n**Consumer Lag {n}**: retraso del consumidor número {n}.\n", encoding="utf-8")
    cosechador = OmniHarvester(tmp_path / "vault")
    rechazada = ClaveRechazada("Gemini rechazó la clave de tu cuenta.", proveedor="gemini", estado=401)
    agotada = CuotaAgotada("La clave de Gemini de tu cuenta agotó su cuota.", proveedor="gemini", estado=429)

    with ia_sustituida(siempre=rechazada) as con_clave_rechazada:
        por_la_clave = cosechador.harvest_from_vault(limit=10, pasarela=pasarela)
    with ia_sustituida(siempre=agotada) as con_cuota_agotada:
        por_la_cuota = cosechador.harvest_from_vault(limit=10, pasarela=pasarela)
    with ia_sustituida(sin_clave=True):
        sin_clave = cosechador.harvest_from_vault(limit=10, pasarela=pasarela)

    # Una clave rechazada falla igual con cualquier nota: se prueba una sola vez; la cuota se prueba nota por nota
    assert (con_clave_rechazada.call_count, con_cuota_agotada.call_count) == (1, 3)
    for tarjetas in (por_la_clave, por_la_cuota, sin_clave):
        assert len(tarjetas) == 3 and all(t.source.startswith("Vault: ") for t in tarjetas)
    assert {t.motivo_sin_ia for t in por_la_clave} == {"Gemini rechazó la clave de tu cuenta."}
    assert {t.motivo_sin_ia for t in por_la_cuota} == {"La clave de Gemini de tu cuenta agotó su cuota."}
    assert {t.motivo_sin_ia for t in sin_clave} == {None}


def test_la_cosecha_del_vault_con_ia_antepone_sus_tarjetas_y_las_locales_no_llevan_motivo(pasarela, tmp_path):
    notas = tmp_path / "vault" / "04 Knowledge" / "Cursos"
    notas.mkdir(parents=True)
    (notas / "Nota.md").write_text("# Nota\n\n**Consumer Lag**: retraso del consumidor frente al productor.\n", encoding="utf-8")

    with ia_sustituida(siempre=respuesta_de({"tarjetas": TARJETAS_DE_LA_IA[:1]}, proveedor="anthropic", modelo="claude-opus-5-5")):
        tarjetas = OmniHarvester(tmp_path / "vault").harvest_from_vault(limit=10, pasarela=pasarela)

    assert [t.source.split(":")[0] for t in tarjetas] == ["Anthropic (Vault", "Vault"]
    assert {t.motivo_sin_ia for t in tarjetas} == {None}


def test_export_cards_to_anki():
    """Verifica el endpoint GET /api/fsrs/export/anki para exportar tarjetas a Anki Desktop."""
    res = client.get("/api/fsrs/export/anki")
    assert res.status_code == 200
    assert "text/tab-separated-values" in res.headers["content-type"]
    assert "aulento_anki_deck.tsv" in res.headers["content-disposition"]
    text = res.text
    assert "#separator:tab" in text
    assert len(text.splitlines()) > 50
