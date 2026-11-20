"""Registre et validation des sources documentaires officielles de LabMind.

Ce module ne stocke aucune connaissance médicale : il valide les métadonnées
des documents collectés et garantit qu'aucune source non vérifiée ou sans fichier
local ne peut être déclarée prête pour l'indexation RAG.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from app.schemas import Source


class MedicalCategory(str, Enum):
    """Catégories biologiques cibles de LabMind plus repères généraux."""

    nfs = "nfs"
    bilan_martial = "bilan_martial"
    bilan_glycemique = "bilan_glycemique"
    bilan_lipidique = "bilan_lipidique"
    bilan_hepatique = "bilan_hepatique"
    bilan_renal = "bilan_renal"
    hygiene_de_vie = "hygiene_de_vie"


class SourceCollectionStatus(str, Enum):
    """État de collecte réel d'une source dans knowledge_corpus/."""

    pending_collection = "pending_collection"
    collected = "collected"
    rejected = "rejected"


class CorpusSourceEntry(BaseModel):
    """Description complète d'une source documentaire du corpus."""

    source_id: str = Field(min_length=3)
    title: str = Field(min_length=3)
    organisme: str = Field(min_length=2)
    url: str = Field(min_length=10)
    published_date: str | None = None
    categories: list[MedicalCategory] = Field(min_length=1)
    themes: list[str] = Field(default_factory=list)
    reuse_conditions: str = Field(min_length=3)
    local_filename: str | None = None
    status: SourceCollectionStatus
    notes: str | None = None

    @model_validator(mode="after")
    def check_url_and_collected_requirements(self) -> CorpusSourceEntry:
        if not self.url.startswith("https://"):
            raise ValueError(
                f"Source '{self.source_id}' : l'URL doit utiliser HTTPS ({self.url})."
            )

        if self.status == SourceCollectionStatus.collected:
            if not self.published_date:
                raise ValueError(
                    f"Source '{self.source_id}' : 'published_date' est obligatoire quand status='collected'."
                )
            if not self.local_filename:
                raise ValueError(
                    f"Source '{self.source_id}' : 'local_filename' est obligatoire quand status='collected'."
                )
            stripped_path = self.url.removeprefix("https://").rstrip("/")
            if "/" not in stripped_path:
                raise ValueError(
                    f"Source '{self.source_id}' : une source collectée doit pointer vers la page/PDF exact, pas uniquement la racine du domaine."
                )

        return self

    def to_api_source(self) -> Source:
        """Convertit cette entrée en schéma `Source` du contrat API v1."""
        return Source(
            source_id=self.source_id,
            title=self.title,
            organisme=self.organisme,
            url=self.url,
            date=self.published_date,
        )


class SourcesRegistry(BaseModel):
    """Conteneur racine du fichier metadata/sources_registry.json."""

    version: str = Field(min_length=1)
    sources: list[CorpusSourceEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_unique_source_ids(self) -> SourcesRegistry:
        seen: set[str] = set()
        for entry in self.sources:
            if entry.source_id in seen:
                raise ValueError(f"Identifiant de source en double : '{entry.source_id}'.")
            seen.add(entry.source_id)
        return self

    def collected_sources(self) -> list[CorpusSourceEntry]:
        """Retourne uniquement les sources prêtes à être indexées."""
        return [
            entry
            for entry in self.sources
            if entry.status == SourceCollectionStatus.collected
        ]


def load_sources_registry(registry_path: Path) -> SourcesRegistry:
    """Charge et valide un fichier JSON de registre de sources."""
    raw = registry_path.read_text(encoding="utf-8")
    return SourcesRegistry.model_validate_json(raw)


def validate_registry_consistency(
    registry: SourcesRegistry,
    sources_dir: Path,
) -> list[str]:
    """Vérifie que chaque source marquée 'collected' a bien un fichier non vide sur disque."""
    errors: list[str] = []

    for entry in registry.collected_sources():
        assert entry.local_filename is not None
        candidate = (sources_dir / entry.local_filename).resolve()
        try:
            candidate.relative_to(sources_dir.resolve())
        except ValueError:
            errors.append(
                f"Source '{entry.source_id}' : chemin invalide hors du dossier sources/ ({entry.local_filename})."
            )
            continue

        if not candidate.is_file():
            errors.append(
                f"Source '{entry.source_id}' : fichier introuvable dans sources/ ({entry.local_filename})."
            )
        elif candidate.stat().st_size == 0:
            errors.append(
                f"Source '{entry.source_id}' : le fichier '{entry.local_filename}' est vide."
            )

    return errors