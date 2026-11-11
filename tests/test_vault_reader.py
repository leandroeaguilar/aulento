"""Pruebas unitarias para el parser y lector seguro del Vault de Obsidian."""

import pytest
from pathlib import Path

from aulento.vault.parser import (
    parse_simple_yaml,
    extract_frontmatter,
    extract_wikilinks,
    extract_tags,
    extract_headings,
    parse_note,
)
from aulento.vault.reader import VaultReader, sembrar_notas_de_muestra
from aulento.vault.rutas import RutaFueraDelVaultError


@pytest.fixture
def temp_vault_dir(tmp_path):
    """Vault temporal con las notas de muestra ya copiadas."""
    vault = tmp_path / "test_vault"
    vault.mkdir(parents=True, exist_ok=True)
    sembrar_notas_de_muestra(vault)
    return vault


def test_parse_simple_yaml():
    yaml_text = """
    title: "Notas de Machine Learning"
    tags: [ia, ml, deep-learning]
    sdd: true
    count: 42
    """
    res = parse_simple_yaml(yaml_text)
    assert res["title"] == "Notas de Machine Learning"
    assert res["tags"] == ["ia", "ml", "deep-learning"]
    assert res["sdd"] is True
    assert res["count"] == 42


def test_extract_wikilinks_and_tags():
    md = """
    # Título Principal
    En este documento vinculamos a [[Redes Neuronales]] y a [[Transformers|Modelos Modernos]].
    También usamos #nlp y #deep-learning.
    """
    links = extract_wikilinks(md)
    assert len(links) == 2
    assert links[0].target == "Redes Neuronales"
    assert links[0].alias is None
    assert links[1].target == "Transformers"
    assert links[1].alias == "Modelos Modernos"

    tags = extract_tags(md, frontmatter={"tags": ["machine-learning"]})
    assert "nlp" in tags
    assert "deep-learning" in tags
    assert "machine-learning" in tags


def test_extract_headings():
    md = """
    # Encabezado 1
    Texto
    ## Subencabezado 2
    Más texto
    ### Nivel 3
    """
    headings = extract_headings(md)
    assert headings == ["Encabezado 1", "Subencabezado 2", "Nivel 3"]


def test_leer_un_vault_vacio_no_le_agrega_nada(tmp_path):
    """Las notas de muestra no aparecen por leer: un vault vacío sigue vacío en disco y en el listado."""
    vault = tmp_path / "vacio"
    vault.mkdir()
    reader = VaultReader(vault)

    assert reader.list_notes() == []
    assert reader.search_notes("star") == []
    assert reader.get_note("Star Schema y Modelado Dimensional") is None
    assert reader.get_vault_stats()["total_notes"] == 0
    assert list(vault.iterdir()) == []


def test_sembrar_las_notas_de_muestra_no_pisa_las_que_ya_estan(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    assert sembrar_notas_de_muestra(vault) == 5

    editada = vault / "02 MOCs" / "MOC Inteligencia Artificial y Datos.md"
    editada.write_text("# Mi versión\n", encoding="utf-8")
    (vault / "04 Knowledge" / "IA" / "Transformers y Mecanismos de Atencion.md").unlink()

    assert sembrar_notas_de_muestra(vault) == 1
    assert editada.read_text(encoding="utf-8") == "# Mi versión\n"


def test_el_lector_exige_la_carpeta_del_vault():
    """Sin carpeta no hay vault por defecto al que caer."""
    with pytest.raises(TypeError):
        VaultReader()
    with pytest.raises(TypeError, match="vault de la cuenta"):
        VaultReader(None)


def test_un_vault_bajo_una_carpeta_oculta_lista_sus_notas(tmp_path):
    """El directorio de datos por defecto empieza con punto: solo cuentan las carpetas ocultas de adentro del vault."""
    vault = tmp_path / ".datos-ocultos" / "usuarios" / "1" / "vault"
    vault.mkdir(parents=True)
    sembrar_notas_de_muestra(vault)
    oculta = vault / "04 Knowledge" / ".trash"
    oculta.mkdir()
    (oculta / "Borrada.md").write_text("# Borrada\n", encoding="utf-8")

    titulos = [n.title for n in VaultReader(vault).list_notes()]

    assert len(titulos) == 5
    assert "Borrada" not in titulos


def test_vault_reader_seeds_samples_and_lists(temp_vault_dir):
    """Verifica que el lector liste las notas de muestra una vez copiadas al vault."""
    reader = VaultReader(temp_vault_dir)
    notes = reader.list_notes()

    assert len(notes) >= 4
    titles = [n.title for n in notes]
    assert "Star Schema y Modelado Dimensional" in titles
    assert "BigQuery Dremel y Separación de Cómputo" in titles
    assert "Transformers y Mecanismos de Atención" in titles
    assert "Webhooks y Arquitectura Orientada a Eventos" in titles


def test_vault_reader_search_and_get(temp_vault_dir):
    """Verifica la búsqueda y recuperación individual de notas."""
    reader = VaultReader(temp_vault_dir)

    # get_note por slug o título
    note = reader.get_note("Star Schema y Modelado Dimensional")
    assert note is not None
    assert len(note.wikilinks) >= 2
    assert "bi" in note.tags

    # search_notes
    results = reader.search_notes("dremel")
    assert len(results) >= 1
    assert "BigQuery" in results[0].title

    # Estadísticas
    stats = reader.get_vault_stats()
    assert stats["total_notes"] >= 4
    assert stats["total_wikilinks"] > 0
    assert stats["total_unique_tags"] > 0


def test_vault_reader_path_traversal_prevention(temp_vault_dir, tmp_path):
    """Verifica que intentos de path traversal hacia arriba del vault sean bloqueados."""
    reader = VaultReader(temp_vault_dir)

    # Crear archivo externo que no debe ser accesible
    external_file = tmp_path / "secret_external.md"
    external_file.write_text("# Secreto Externo\nContenido confidencial", encoding="utf-8")

    # Una carpeta que sube fuera del vault no es «sin notas»: se rechaza
    for carpeta in ("../../..", "../", str(tmp_path), "C:secret", "/"):
        with pytest.raises(RutaFueraDelVaultError):
            reader.list_notes(folder=carpeta)
    for identificador in ("../secret_external", str(external_file), "C:secret_external", "/secret_external"):
        with pytest.raises(RutaFueraDelVaultError):
            reader.get_note(identificador)
