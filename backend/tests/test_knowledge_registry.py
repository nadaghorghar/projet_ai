from pathlib import Path

import pytest
from pydantic import ValidationError

from app.knowledge import (
    CorpusSourceEntry,
    MedicalCategory,
    SourceCollectionStatus,
    SourcesRegistry,
    load_sources_registry,
    validate_registry_consistency,
)
from app.schemas import Source

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_REGISTRY_PATH = REPO_ROOT / "knowledge_corpus" / "metadata" / "sources_registry.json"
REAL_SOURCES_DIR = REPO_ROOT / "knowledge_corpus" / "sources"


def test_real_repository_registry_is_valid_and_consistent():
    assert REAL_REGISTRY_PATH.is_file(), f"Registre introuvable : {REAL_REGISTRY_PATH}"
    registry = load_sources_registry(REAL_REGISTRY_PATH)

    categories_covered = {
        cat for entry in registry.sources for cat in entry.categories
    }
    assert set(MedicalCategory).issubset(categories_covered)
    assert validate_registry_consistency(registry, REAL_SOURCES_DIR) == []


def test_collected_source_requires_date_filename_and_specific_url():
    with pytest.raises(ValidationError):
        CorpusSourceEntry(
            source_id="ameli-test-01",
            title="Fiche test",
            organisme="Assurance Maladie",
            url="https://www.ameli.fr/",
            published_date="2025-01-10",
            categories=[MedicalCategory.nfs],
            reuse_conditions="Licence ouverte",
            local_filename="ameli_test.txt",
            status=SourceCollectionStatus.collected,
        )

    with pytest.raises(ValidationError):
        CorpusSourceEntry(
            source_id="ameli-test-02",
            title="Fiche test",
            organisme="Assurance Maladie",
            url="https://www.ameli.fr/assure/sante/examen/hemogramme",
            published_date=None,
            categories=[MedicalCategory.nfs],
            reuse_conditions="Licence ouverte",
            local_filename="ameli_test.txt",
            status=SourceCollectionStatus.collected,
        )


def test_duplicate_source_ids_rejected():
    entry = CorpusSourceEntry(
        source_id="dup-01",
        title="Source A",
        organisme="Inserm",
        url="https://www.inserm.fr/",
        categories=[MedicalCategory.bilan_martial],
        reuse_conditions="À vérifier",
        status=SourceCollectionStatus.pending_collection,
    )
    with pytest.raises(ValidationError):
        SourcesRegistry(version="1.0", sources=[entry, entry])


def test_validate_registry_consistency_checks_disk_file_and_traversal(tmp_path):
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    valid_file = sources_dir / "inserm_fer.txt"
    valid_file.write_text("Le fer participe au transport de l'oxygène.", encoding="utf-8")

    ok_entry = CorpusSourceEntry(
        source_id="inserm-fer-2025",
        title="Métabolisme du fer",
        organisme="Inserm",
        url="https://www.inserm.fr/dossier/anemie-fer/",
        published_date="2025-02-01",
        categories=[MedicalCategory.bilan_martial],
        reuse_conditions="Usage pédagogique cité",
        local_filename="inserm_fer.txt",
        status=SourceCollectionStatus.collected,
    )
    missing_entry = CorpusSourceEntry(
        source_id="has-rein-2025",
        title="Maladie rénale",
        organisme="HAS",
        url="https://www.has-sante.fr/jcms/p_12345/fr/mrc",
        published_date="2024-11-15",
        categories=[MedicalCategory.bilan_renal],
        reuse_conditions="Usage pédagogique cité",
        local_filename="absent.txt",
        status=SourceCollectionStatus.collected,
    )

    registry = SourcesRegistry(version="1.0", sources=[ok_entry, missing_entry])
    errors = validate_registry_consistency(registry, sources_dir)

    assert len(errors) == 1
    assert "has-rein-2025" in errors[0]

    api_source = ok_entry.to_api_source()
    assert isinstance(api_source, Source)
    assert api_source.source_id == "inserm-fer-2025"
    assert api_source.date == "2025-02-01"