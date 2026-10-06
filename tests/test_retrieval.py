"""Tests de la recherche et de son évaluation, sans Ollama (modèle d'embeddings factice)."""

from __future__ import annotations

import numpy as np
import pytest

from volley_rag.embeddings import normalize
from volley_rag.eval_retrieval import evaluate, load_questions
from volley_rag.retrieval import (
    BM25Retriever,
    DenseRetriever,
    Hit,
    HybridRetriever,
    load_index,
    save_index,
    tokenize,
)

DOCS = [
    {"id": "11.3", "texte": "Règle 11.3 – CONTACT AVEC LE FILET. Le contact du filet entre les antennes est une faute."},
    {"id": "19.3", "texte": "Règle 19.3 – Le Libéro ne peut ni servir, ni contrer."},
    {"id": "12.4", "texte": "Règle 12.4 – EXÉCUTION DU SERVICE. Le joueur au service doit frapper le ballon en 8 secondes."},
]


class FakeEmbedder:
    """Sac de mots haché : deux textes qui partagent des mots ont des vecteurs proches."""

    def __init__(self, dim: int = 64):
        self.dim = dim

    def embed(self, texts):
        matrix = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in tokenize(text):
                matrix[row, sum(map(ord, token)) % self.dim] += 1
        return normalize(matrix)


def test_tokenize_removes_accents_stopwords_and_plurals():
    assert tokenize("Le Libéro peut-il servir les ballons ?") == ["libero", "servir", "ballon"]


def test_bm25_finds_the_matching_section():
    hits = BM25Retriever(DOCS).search("toucher le filet c'est une faute ?", k=3)
    assert hits[0].id == "11.3"
    assert [h.rank for h in hits] == [1, 2, 3]


def test_bm25_is_accent_insensitive():
    assert BM25Retriever(DOCS).search("libero servir", k=1)[0].id == "19.3"


def test_dense_retriever_with_fake_embedder():
    embedder = FakeEmbedder()
    matrix = embedder.embed([d["texte"] for d in DOCS])
    dense = DenseRetriever([d["id"] for d in DOCS], matrix, embedder)
    assert dense.search("secondes pour le service", k=1)[0].id == "12.4"


def test_hybrid_rrf_rewards_agreement():
    class Fixed:
        def __init__(self, name, order):
            self.name, self.order = name, order

        def search(self, query, k=5):
            return [Hit(id=i, score=0.0, rank=r + 1) for r, i in enumerate(self.order[:k])]

    hybrid = HybridRetriever([Fixed("a", ["x", "y", "z"]), Fixed("b", ["y", "z", "x"])])
    assert [h.id for h in hybrid.search("q", 3)] == ["y", "x", "z"]


def test_index_roundtrip(tmp_path):
    path = tmp_path / "index.npz"
    matrix = np.eye(3, dtype=np.float32)
    save_index(path, ["a", "b", "c"], matrix, "bge-m3")
    ids, loaded, model = load_index(path)
    assert ids == ["a", "b", "c"] and model == "bge-m3"
    assert np.array_equal(loaded, matrix)


def test_evaluate_metrics():
    class Fixed:
        name = "fixe"

        def search(self, query, k=5):
            order = {"q1": ["11.3", "19.3"], "q2": ["19.3", "12.4"], "q3": ["19.3", "11.3"]}[query]
            return [Hit(id=i, score=0.0, rank=r + 1) for r, i in enumerate(order)]

    questions = [
        {"id": "a", "question": "q1", "gold": ["11.3"]},  # rang 1
        {"id": "b", "question": "q2", "gold": ["12.4"]},  # rang 2
        {"id": "c", "question": "q3", "gold": ["12.4"]},  # absent
    ]
    result = evaluate(Fixed(), questions)
    assert result.recall == {1: pytest.approx(1 / 3), 3: pytest.approx(2 / 3), 5: pytest.approx(2 / 3)}
    assert result.mrr == pytest.approx((1 + 0.5 + 0) / 3)
    assert [m["id"] for m in result.misses] == ["c"]


def test_eval_questions_have_gold_sections():
    questions = load_questions()
    assert questions and all(q["gold"] for q in questions)
    q = next(q for q in questions if q["id"] == "q001")
    assert q["gold"] == ["9.2", "9.3"]
