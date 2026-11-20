"""Nettoyage et découpage des documents institutionnels en passages indexables."""
from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from app.generation.interface import RetrievedPassage
from app.schemas import Source

from .registry import CorpusSourceEntry, MedicalCategory, SourcesRegistry


class KnowledgePassage(BaseModel):
    """Passage découpé d'une source officielle avec toutes ses métadonnées."""

    passage_id: str = Field(min_length=3)
    source_id: str = Field(min_length=3)
    title: str
    organisme: str
    url: str
    published_date: str | None = None
    categories: list[MedicalCategory] = Field(min_length=1)
    themes: list[str] = Field(default_factory=list)
    text: str = Field(min_length=1)

    def to_retrieved_passage(self, score: float | None = None) -> RetrievedPassage:
        """Convertit ce passage vers le format attendu par `app/generation/`."""
        return RetrievedPassage(
            passage_id=self.passage_id,
            source=Source(
                source_id=self.source_id,
                title=self.title,
                organisme=self.organisme,
                url=self.url,
                date=self.published_date,
            ),
            excerpt=self.text,
            score=score,
        )


def clean_document_text(raw_text: str) -> str:
    """Normalise les sauts de ligne et supprime les espaces superflus."""
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [
        re.sub(r"[ \t]+", " ", block).strip()
        for block in re.split(r"\n\s*\n", normalized)
    ]
    return "\n\n".join(p for p in paragraphs if p)


def _split_long_block(block: str, max_chars: int) -> list[str]:
    """Découpe un paragraphe trop long en segments <= max_chars."""
    if len(block) <= max_chars:
        return [block]

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", block) if s.strip()]
    pieces: list[str] = []

    for sentence in sentences:
        if len(sentence) <= max_chars:
            pieces.append(sentence)
            continue

        words = sentence.split(" ")
        current = ""
        for word in words:
            if len(word) > max_chars:
                if current:
                    pieces.append(current)
                    current = ""
                for i in range(0, len(word), max_chars):
                    pieces.append(word[i : i + max_chars])
            elif not current:
                current = word
            elif len(current) + 1 + len(word) <= max_chars:
                current = f"{current} {word}"
            else:
                pieces.append(current)
                current = word
        if current:
            pieces.append(current)

    return pieces


def chunk_text(
    text: str,
    max_chars: int = 700,
    overlap_chars: int = 100,
) -> list[str]:
    """Découpe un texte nettoyé en passages cohérents avec chevauchement."""
    if max_chars <= 0:
        raise ValueError("max_chars doit être strictement positif.")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars doit être compris entre 0 et max_chars - 1.")

    cleaned = clean_document_text(text)
    if not cleaned:
        return []

    pieces: list[str] = []
    for paragraph in cleaned.split("\n\n"):
        pieces.extend(_split_long_block(paragraph, max_chars))

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for piece in pieces:
        sep = 1 if current else 0
        if current and current_len + sep + len(piece) > max_chars:
            chunks.append("\n".join(current))

            overlap_items: list[str] = []
            overlap_len = 0
            for prev in reversed(current):
                added = len(prev) + (1 if overlap_items else 0)
                if overlap_len + added > overlap_chars:
                    break
                overlap_items.insert(0, prev)
                overlap_len += added

            while overlap_items and (overlap_len + 1 + len(piece) > max_chars):
                overlap_items.pop(0)
                overlap_len = sum(len(x) for x in overlap_items) + max(
                    0, len(overlap_items) - 1
                )

            current = overlap_items
            current_len = overlap_len

        current.append(piece)
        current_len = sum(len(x) for x in current) + max(0, len(current) - 1)

    if current:
        chunks.append("\n".join(current))

    return chunks


def chunk_source_entry(
    entry: CorpusSourceEntry,
    raw_text: str,
    max_chars: int = 700,
    overlap_chars: int = 100,
) -> list[KnowledgePassage]:
    """Découpe le texte d'une source du registre en objets KnowledgePassage."""
    texts = chunk_text(raw_text, max_chars=max_chars, overlap_chars=overlap_chars)
    return [
        KnowledgePassage(
            passage_id=f"{entry.source_id}#{idx:03d}",
            source_id=entry.source_id,
            title=entry.title,
            organisme=entry.organisme,
            url=entry.url,
            published_date=entry.published_date,
            categories=entry.categories,
            themes=entry.themes,
            text=chunk,
        )
        for idx, chunk in enumerate(texts, start=1)
    ]


def build_passages_from_registry(
    registry: SourcesRegistry,
    sources_dir: Path,
    max_chars: int = 700,
    overlap_chars: int = 100,
) -> list[KnowledgePassage]:
    """Charge toutes les sources 'collected' et produit la liste des passages."""
    all_passages: list[KnowledgePassage] = []

    for entry in registry.collected_sources():
        assert entry.local_filename is not None
        file_path = sources_dir / entry.local_filename
        raw_text = file_path.read_text(encoding="utf-8")
        all_passages.extend(
            chunk_source_entry(
                entry=entry,
                raw_text=raw_text,
                max_chars=max_chars,
                overlap_chars=overlap_chars,
            )
        )

    return all_passages


def save_passages_jsonl(passages: list[KnowledgePassage], output_path: Path) -> None:
    """Enregistre les passages au format JSONL (UTF-8)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [p.model_dump_json() for p in passages]
    content = "\n".join(lines) + ("\n" if lines else "")
    output_path.write_text(content, encoding="utf-8")


def load_passages_jsonl(input_path: Path) -> list[KnowledgePassage]:
    """Relit un fichier JSONL de passages."""
    if not input_path.is_file():
        return []
    lines = [
        line.strip()
        for line in input_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [KnowledgePassage.model_validate_json(line) for line in lines]