"""Chargement des documents indexés : les sections du règlement et les définitions."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_documents(processed_dir: Path = PROCESSED_DIR) -> list[dict]:
    """Retourne la liste des documents à indexer.

    Chaque document a au moins : ``id``, ``type`` (``section`` ou ``definition``),
    ``texte`` et ``pages_imprimees``. L'id d'une section est son numéro (``7.4``),
    celui d'une définition est ``def:<terme>``.
    """
    sections_path = processed_dir / "sections.jsonl"
    if not sections_path.exists():
        raise FileNotFoundError(
            f"{sections_path} introuvable : lance d'abord `python -m volley_rag.extraction`."
        )
    docs = []
    for s in read_jsonl(sections_path):
        docs.append({**s, "type": "section"})

    definitions_path = processed_dir / "definitions.jsonl"
    if definitions_path.exists():
        for d in read_jsonl(definitions_path):
            docs.append(
                {
                    "id": f"def:{slugify(d['terme'])}",
                    "type": "definition",
                    "terme": d["terme"],
                    "texte": f"Définition – {d['terme']}\n{d['texte']}",
                    "pages_imprimees": [d["page_imprimee"]] if d.get("page_imprimee") else [],
                    "source": d.get("source"),
                }
            )
    return docs
