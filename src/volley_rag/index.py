"""Calcule et enregistre les embeddings de tous les documents (sections + définitions).

Usage ::

    python -m volley_rag.index                  # bge-m3 par défaut
    python -m volley_rag.index --modele qwen3-embedding
"""

from __future__ import annotations

import argparse
import time

from volley_rag.documents import load_documents
from volley_rag.embeddings import DEFAULT_MODEL, OllamaEmbedder
from volley_rag.retrieval import index_path, save_index


def build_index(model: str = DEFAULT_MODEL, embedder=None):
    docs = load_documents()
    embedder = embedder or OllamaEmbedder(model)
    start = time.perf_counter()
    matrix = embedder.embed([d["texte"] for d in docs])
    elapsed = time.perf_counter() - start
    path = index_path(model)
    save_index(path, [d["id"] for d in docs], matrix, model)
    return path, len(docs), matrix.shape[1], elapsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Construit l'index d'embeddings du règlement.")
    parser.add_argument("--modele", default=DEFAULT_MODEL, help="modèle d'embeddings Ollama (défaut : bge-m3)")
    args = parser.parse_args()
    path, n, dim, elapsed = build_index(args.modele)
    print(f"{n} documents indexés avec {args.modele} (dimension {dim}) en {elapsed:.1f} s")
    print(f"écrit dans {path}")


if __name__ == "__main__":
    main()
