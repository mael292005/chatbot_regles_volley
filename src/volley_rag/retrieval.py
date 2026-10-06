"""Recherche des passages du règlement les plus pertinents pour une question.

Trois méthodes, comparées dans ``volley_rag.eval_retrieval`` :

* ``BM25Retriever``   : par mots-clés (aucun modèle nécessaire) ;
* ``DenseRetriever``  : par le sens, avec des embeddings (bge-m3 via Ollama) ;
* ``HybridRetriever`` : fusion des deux classements (Reciprocal Rank Fusion).

Usage ::

    python -m volley_rag.retrieval "Est-ce que je peux toucher le filet ?"
    python -m volley_rag.retrieval --methode bm25 "le libéro peut-il servir"
"""

from __future__ import annotations

import argparse
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from volley_rag.documents import PROCESSED_DIR, load_documents
from volley_rag.embeddings import DEFAULT_MODEL, OllamaEmbedder

# Mots trop fréquents pour aider à distinguer les articles.
STOPWORDS = set(
    """
    a au aux avec ce ces cet cette dans de des du elle en est et etre il ils je la le les leur lui
    ma mais me meme mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses si son sur
    ta te tes toi ton tu un une vos votre vous y c d j l m n s t qu est-ce ca cela ceci
    peut peux faut faire fait sont ont avoir ai as avez avons quand quoi comment combien
    """.split()
)


@dataclass
class Hit:
    id: str
    score: float
    rank: int


class Retriever(Protocol):
    name: str

    def search(self, query: str, k: int = 5) -> list[Hit]: ...


# --------------------------------------------------------------------------- texte


def strip_accents(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def tokenize(text: str) -> list[str]:
    """Minuscules, sans accents, sans mots vides, pluriels simples ramenés au singulier."""
    text = strip_accents(text.lower()).replace("’", "'")
    tokens = []
    for token in re.findall(r"[a-z0-9]+", text):
        if token in STOPWORDS or len(token) < 2:
            continue
        if len(token) > 4 and token.endswith(("s", "x")) and not token.endswith("ss"):
            token = token[:-1]
        tokens.append(token)
    return tokens


def _ranked(scores: np.ndarray, ids: list[str], k: int) -> list[Hit]:
    order = np.argsort(-scores, kind="stable")[:k]
    return [Hit(id=ids[i], score=float(scores[i]), rank=r + 1) for r, i in enumerate(order)]


# --------------------------------------------------------------------------- BM25


class BM25Retriever:
    name = "bm25"

    def __init__(self, docs: list[dict], k1: float = 1.5, b: float = 0.75):
        self.ids = [d["id"] for d in docs]
        self.k1, self.b = k1, b
        self.tfs = [Counter(tokenize(d["texte"])) for d in docs]
        self.lengths = np.array([sum(tf.values()) for tf in self.tfs], dtype=np.float32)
        self.avg_length = float(self.lengths.mean()) if len(docs) else 0.0
        df = Counter(term for tf in self.tfs for term in tf)
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> np.ndarray:
        scores = np.zeros(len(self.ids), dtype=np.float32)
        for term in set(tokenize(query)):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, tf in enumerate(self.tfs):
                f = tf.get(term)
                if f:
                    norm = self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avg_length)
                    scores[i] += idf * f * (self.k1 + 1) / (f + norm)
        return scores

    def search(self, query: str, k: int = 5) -> list[Hit]:
        return _ranked(self.scores(query), self.ids, k)


# --------------------------------------------------------------------------- embeddings


class DenseRetriever:
    def __init__(self, ids: list[str], matrix: np.ndarray, embedder, name: str = "dense"):
        self.ids = ids
        self.matrix = matrix
        self.embedder = embedder
        self.name = name

    def search(self, query: str, k: int = 5) -> list[Hit]:
        q = self.embedder.embed([query])[0]
        return _ranked(self.matrix @ q, self.ids, k)


def index_path(model: str, processed_dir: Path = PROCESSED_DIR) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", model)
    return processed_dir / f"index_{safe}.npz"


def save_index(path: Path, ids: list[str], matrix: np.ndarray, model: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, ids=np.array(ids), matrix=matrix.astype(np.float32), model=np.array(model))


def load_index(path: Path) -> tuple[list[str], np.ndarray, str]:
    data = np.load(path)
    return [str(i) for i in data["ids"]], data["matrix"], str(data["model"])


def load_dense(model: str = DEFAULT_MODEL, processed_dir: Path = PROCESSED_DIR, embedder=None) -> DenseRetriever:
    path = index_path(model, processed_dir)
    if not path.exists():
        raise FileNotFoundError(f"{path} introuvable : lance d'abord `python -m volley_rag.index --modele {model}`.")
    ids, matrix, stored_model = load_index(path)
    return DenseRetriever(ids, matrix, embedder or OllamaEmbedder(stored_model), name=f"dense:{stored_model}")


# --------------------------------------------------------------------------- hybride


class HybridRetriever:
    """Reciprocal Rank Fusion : chaque méthode vote 1 / (k_rrf + rang) pour ses premiers résultats."""

    def __init__(self, retrievers: list, k_rrf: int = 60, depth: int = 50):
        self.retrievers = retrievers
        self.k_rrf = k_rrf
        self.depth = depth
        self.name = "hybride(" + "+".join(r.name for r in retrievers) + ")"

    def search(self, query: str, k: int = 5) -> list[Hit]:
        fused: dict[str, float] = {}
        for retriever in self.retrievers:
            for hit in retriever.search(query, self.depth):
                fused[hit.id] = fused.get(hit.id, 0.0) + 1.0 / (self.k_rrf + hit.rank)
        ordered = sorted(fused.items(), key=lambda item: -item[1])[:k]
        return [Hit(id=i, score=s, rank=r + 1) for r, (i, s) in enumerate(ordered)]


# --------------------------------------------------------------------------- CLI


def build_retriever(methode: str, docs: list[dict], model: str = DEFAULT_MODEL):
    if methode == "bm25":
        return BM25Retriever(docs)
    if methode == "dense":
        return load_dense(model)
    if methode == "hybride":
        return HybridRetriever([BM25Retriever(docs), load_dense(model)])
    raise ValueError(f"méthode inconnue : {methode}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cherche les articles du règlement liés à une question.")
    parser.add_argument("question")
    parser.add_argument("--methode", choices=["bm25", "dense", "hybride"], default="hybride")
    parser.add_argument("--modele", default=DEFAULT_MODEL, help="modèle d'embeddings Ollama")
    parser.add_argument("-k", type=int, default=5)
    args = parser.parse_args()

    docs = load_documents()
    by_id = {d["id"]: d for d in docs}
    retriever = build_retriever(args.methode, docs, args.modele)
    print(f"Méthode : {retriever.name}\n")
    for hit in retriever.search(args.question, args.k):
        doc = by_id[hit.id]
        title = doc["texte"].split("\n", 1)[0]
        pages = ", ".join(str(p) for p in doc.get("pages_imprimees", []))
        print(f"{hit.rank}. {title}  (p. {pages}, score {hit.score:.3f})")


if __name__ == "__main__":
    main()
