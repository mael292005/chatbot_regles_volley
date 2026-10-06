"""Évalue la recherche sur le jeu de test : le bon article remonte-t-il parmi les premiers résultats ?

Pour chaque question qui cite des règles (les questions hors sujet sont ignorées), la
« bonne réponse » est l'ensemble des sections qui contiennent ces règles (``9.3.4`` -> ``9.3``).
Un résultat est un succès si au moins une de ces sections figure dans les k premiers.

Métriques :

* ``Recall@k`` : part des questions dont une bonne section est dans les k premiers résultats ;
* ``MRR``      : moyenne de 1 / rang de la première bonne section (0 si absente des 10 premiers).

Usage ::

    python -m volley_rag.eval_retrieval                  # BM25 + bge-m3 + hybride si l'index existe
    python -m volley_rag.eval_retrieval --modele bge-m3 --modele qwen3-embedding
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from volley_rag.documents import load_documents
from volley_rag.embeddings import DEFAULT_MODEL
from volley_rag.extraction import section_of
from volley_rag.retrieval import BM25Retriever, HybridRetriever, index_path, load_dense

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = ROOT / "eval" / "questions.yaml"
RESULTS_DIR = ROOT / "eval" / "results"
KS = (1, 3, 5)
MRR_DEPTH = 10


@dataclass
class MethodResult:
    name: str
    recall: dict[int, float] = field(default_factory=dict)
    mrr: float = 0.0
    misses: list[dict] = field(default_factory=list)  # questions sans bonne section dans le top 5
    per_question: list[dict] = field(default_factory=list)


def load_questions(path: Path = QUESTIONS) -> list[dict]:
    questions = yaml.safe_load(path.read_text(encoding="utf-8"))["questions"]
    usable = []
    for q in questions:
        if q["statut"] == "hors_sujet" or not q["regles"]:
            continue
        usable.append({**q, "gold": sorted({section_of(r) for r in q["regles"]})})
    return usable


def evaluate(retriever, questions: list[dict]) -> MethodResult:
    result = MethodResult(name=retriever.name)
    hits_at = {k: 0 for k in KS}
    reciprocal_ranks = []
    for q in questions:
        ranking = [h.id for h in retriever.search(q["question"], MRR_DEPTH)]
        gold = set(q["gold"])
        first = next((i + 1 for i, doc_id in enumerate(ranking) if doc_id in gold), None)
        for k in KS:
            hits_at[k] += first is not None and first <= k
        reciprocal_ranks.append(1.0 / first if first else 0.0)
        result.per_question.append({"id": q["id"], "rang": first, "top5": ranking[:5], "attendu": q["gold"]})
        if first is None or first > max(KS):
            result.misses.append(
                {"id": q["id"], "question": q["question"], "attendu": q["gold"], "obtenu": ranking[:5], "rang": first}
            )
    n = len(questions)
    result.recall = {k: hits_at[k] / n for k in KS}
    result.mrr = sum(reciprocal_ranks) / n
    return result


def render_markdown(results: list[MethodResult], n_questions: int) -> str:
    lines = [
        "# Évaluation de la recherche",
        "",
        f"*Générée le {date.today().isoformat()} par `python -m volley_rag.eval_retrieval`.*",
        "",
        f"{n_questions} questions du jeu de test (hors sujet exclues). Un succès = au moins une section "
        "attendue parmi les k premiers résultats.",
        "",
        "| Méthode | " + " | ".join(f"Recall@{k}" for k in KS) + " | MRR |",
        "| --- | " + " | ".join("---:" for _ in KS) + " | ---: |",
    ]
    for r in results:
        cells = " | ".join(f"{r.recall[k]:.0%}" for k in KS)
        lines.append(f"| {r.name} | {cells} | {r.mrr:.2f} |")
    for r in results:
        lines += ["", f"## Échecs de {r.name} (bonne section absente du top 5)", ""]
        if not r.misses:
            lines.append("Aucun.")
            continue
        lines += ["| Question | Attendu | Obtenu (top 5) | Rang |", "| --- | --- | --- | ---: |"]
        for m in r.misses:
            rang = m["rang"] if m["rang"] else f"> {MRR_DEPTH}"
            lines.append(f"| {m['id']} – {m['question']} | {', '.join(m['attendu'])} | {', '.join(m['obtenu'])} | {rang} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Évalue les méthodes de recherche sur eval/questions.yaml.")
    parser.add_argument(
        "--modele", action="append", help="modèle(s) d'embeddings à évaluer (défaut : bge-m3 si son index existe)"
    )
    parser.add_argument("--bm25-seul", action="store_true", help="n'évaluer que BM25 (sans Ollama)")
    args = parser.parse_args()

    docs = load_documents()
    questions = load_questions()
    bm25 = BM25Retriever(docs)
    retrievers = [bm25]

    if not args.bm25_seul:
        models = args.modele or [DEFAULT_MODEL]
        for model in models:
            if not index_path(model).exists():
                print(f"(index absent pour {model} : lance `python -m volley_rag.index --modele {model}` — ignoré)")
                continue
            dense = load_dense(model)
            retrievers += [dense, HybridRetriever([bm25, dense])]

    results = [evaluate(r, questions) for r in retrievers]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report = render_markdown(results, len(questions))
    (RESULTS_DIR / "recherche.md").write_text(report, encoding="utf-8")
    (RESULTS_DIR / "recherche.json").write_text(
        json.dumps(
            [{"methode": r.name, "recall": r.recall, "mrr": r.mrr, "questions": r.per_question} for r in results],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    width = max(len(r.name) for r in results)
    print(f"{len(questions)} questions\n")
    print(f"{'Méthode':<{width}}  " + "  ".join(f"R@{k}" for k in KS) + "   MRR")
    for r in results:
        print(f"{r.name:<{width}}  " + "  ".join(f"{r.recall[k]:>3.0%}" for k in KS) + f"  {r.mrr:.2f}")
    print(f"\nDétail et échecs : {RESULTS_DIR / 'recherche.md'}")


if __name__ == "__main__":
    main()
