"""Évalue les réponses générées sur tout le jeu de test (hors sujet compris).

Mesures, par modèle :

* **Justesse** : un LLM juge compare la réponse à la réponse attendue (correct / partiel / faux).
  Score = correct + 0,5 × partiel, rapporté au nombre de questions.
* **Bonne règle citée** : au moins une règle citée correspond à une règle attendue
  (même article, ou article parent / enfant : 9.2.3 ↔ 9.2.3.2).
* **Citations inventées** : numéros cités qui n'existent pas dans le règlement.
* **Refus** : questions hors sujet bien refusées, et questions valides refusées à tort.
* **Durée** moyenne par question.

Les réponses de tous les modèles sont générées d'abord, puis jugées ensemble : cela évite de
recharger les modèles dans la carte graphique à chaque question.

Usage ::

    python -m volley_rag.eval_generation                              # qwen3:14b et mistral-nemo
    python -m volley_rag.eval_generation --modele qwen3:14b --limite 5  # essai rapide
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

import yaml

from volley_rag.ask import Assistant, OllamaChat
from volley_rag.documents import PROCESSED_DIR, load_documents, read_jsonl
from volley_rag.retrieval import build_retriever

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = ROOT / "eval" / "questions.yaml"
RESULTS_DIR = ROOT / "eval" / "results"
DEFAULT_MODELS = ["qwen3:14b", "mistral-nemo"]
DEFAULT_JUDGE = "qwen3:14b"

JUDGE_PROMPT = """Tu évalues la réponse d'un assistant sur les règles du volley-ball.
La RÉPONSE ATTENDUE fait foi. Les POINTS ESSENTIELS sont les seuls éléments exigés.

Remplis le JSON ainsi :
- "justification" : compare brièvement les deux réponses.
- "conclusion_juste" : true si la conclusion principale de l'assistant (oui / non / ça dépend, \
ou la valeur demandée) est la même que celle de la réponse attendue.
- "erreur_factuelle" : true si l'assistant affirme quelque chose qui contredit la réponse attendue. \
Une information supplémentaire exacte, ou absente de la réponse attendue sans la contredire, \
n'est PAS une erreur.
- "points_presents" : pour chaque point essentiel, dans l'ordre, true s'il est exprimé dans la \
réponse de l'assistant, même avec d'autres mots, sinon false.

N'exige ni date, ni numéro d'article, ni formulation particulière."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "justification": {"type": "string"},
        "conclusion_juste": {"type": "boolean"},
        "erreur_factuelle": {"type": "boolean"},
        "points_presents": {"type": "array", "items": {"type": "boolean"}},
    },
    "required": ["justification", "conclusion_juste", "erreur_factuelle", "points_presents"],
}


def verdict_from_judgement(data: dict, n_points: int) -> str:
    """Verdict calculé par le code à partir des cases cochées par le juge (plus reproductible)."""
    if not data.get("conclusion_juste") or data.get("erreur_factuelle"):
        return "faux"
    present = list(data.get("points_presents") or [])[:n_points]
    present += [False] * (n_points - len(present))
    return "correct" if all(present) else "partiel"


# --------------------------------------------------------------------------- métriques


def rule_matches(cited: str, expected: str) -> bool:
    """Même article, ou l'un est un sous-article de l'autre (9.2.3 ↔ 9.2.3.2)."""
    return cited == expected or cited.startswith(expected + ".") or expected.startswith(cited + ".")


def cites_expected_rule(cited: list[str], expected: list[str]) -> bool:
    return any(rule_matches(c, e) for c in cited for e in expected)


def judge(chat, question: dict, answer_text: str) -> dict:
    points = question.get("essentiel") or [question["reponse_attendue"]]
    numbered = "\n".join(f"{i}. {p}" for i, p in enumerate(points, 1))
    messages = [
        {"role": "system", "content": JUDGE_PROMPT},
        {
            "role": "user",
            "content": (
                f"QUESTION : {question['question']}\n\n"
                f"RÉPONSE ATTENDUE : {question['reponse_attendue']}\n\n"
                f"POINTS ESSENTIELS :\n{numbered}\n\n"
                f"RÉPONSE DE L'ASSISTANT : {answer_text}"
            ),
        },
    ]
    raw = chat.chat(messages, schema=JUDGE_SCHEMA)
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or "conclusion_juste" not in data:
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        return {"verdict": "faux", "justification": f"jugement illisible : {raw[:200]}", "points_presents": []}
    return {
        "verdict": verdict_from_judgement(data, len(points)),
        "justification": str(data.get("justification", "")),
        "points_presents": list(data.get("points_presents") or [])[: len(points)],
    }


def score_answers(questions: list[dict], answers: list[dict], verdicts: list[dict | None], existing: set[str]) -> dict:
    on_topic = [i for i, q in enumerate(questions) if q["statut"] != "hors_sujet"]
    off_topic = [i for i, q in enumerate(questions) if q["statut"] == "hors_sujet"]

    points = 0.0
    counts = {"correct": 0, "partiel": 0, "faux": 0}
    for i in on_topic:
        v = verdicts[i]["verdict"] if verdicts[i] else "faux"
        counts[v] += 1
        points += {"correct": 1.0, "partiel": 0.5, "faux": 0.0}[v]
    refused_ok = sum(answers[i]["hors_sujet"] for i in off_topic)
    points += refused_ok  # une question hors sujet bien refusée compte comme correcte

    cited_all = [r for a in answers for r in a["regles"]]
    invented = [r for r in cited_all if r not in existing]
    with_expected = [i for i in on_topic if questions[i]["regles"]]
    good_citation = sum(cites_expected_rule(answers[i]["regles"], questions[i]["regles"]) for i in with_expected)

    return {
        "n_questions": len(questions),
        "justesse": points / len(questions),
        "verdicts": counts,
        "bonne_regle_citee": good_citation / len(with_expected) if with_expected else 0.0,
        "citations_total": len(cited_all),
        "citations_inventees": invented,
        "hors_sujet_refuses": f"{refused_ok}/{len(off_topic)}",
        "refus_a_tort": [questions[i]["id"] for i in on_topic if answers[i]["hors_sujet"]],
        "json_invalides": sum(a.get("json_invalide", False) for a in answers),
        "duree_moyenne_s": sum(a["duree_s"] for a in answers) / len(answers),
    }


# --------------------------------------------------------------------------- rapport


def render_markdown(models: list[str], judge_model: str, questions, results, scores, methode, k) -> str:
    lines = [
        "# Évaluation des réponses",
        "",
        f"*Générée le {date.today().isoformat()} par `python -m volley_rag.eval_generation`.*",
        "",
        f"{len(questions)} questions (dont hors sujet). Recherche : {methode}, {k} passages. "
        f"Juge : {judge_model} (température 0).",
        "",
        "| Modèle | Justesse | Correct / partiel / faux | Bonne règle citée | Citations inventées | "
        "Hors sujet refusés | Refus à tort | Durée moy. |",
        "| --- | ---: | :---: | ---: | ---: | :---: | ---: | ---: |",
    ]
    for m in models:
        s = scores[m]
        v = s["verdicts"]
        lines.append(
            f"| {m} | **{s['justesse']:.0%}** | {v['correct']} / {v['partiel']} / {v['faux']} | "
            f"{s['bonne_regle_citee']:.0%} | {len(s['citations_inventees'])} / {s['citations_total']} | "
            f"{s['hors_sujet_refuses']} | {len(s['refus_a_tort'])} | {s['duree_moyenne_s']:.1f} s |"
        )

    lines += ["", "## Verdict par question", ""]
    lines.append("| Question | " + " | ".join(models) + " |")
    lines.append("| --- | " + " | ".join(":---:" for _ in models) + " |")
    for i, q in enumerate(questions):
        cells = []
        for m in models:
            entry = results[m][i]
            if q["statut"] == "hors_sujet":
                cells.append("refusé ✓" if entry["hors_sujet"] else "non refusé ✗")
            else:
                cells.append(entry["verdict"]["verdict"] if entry.get("verdict") else "—")
        lines.append(f"| {q['id']} – {q['question']} | " + " | ".join(cells) + " |")

    for m in models:
        lines += ["", f"## Réponses fausses ou partielles de {m}", ""]
        bad = [
            (q, results[m][i])
            for i, q in enumerate(questions)
            if q["statut"] != "hors_sujet" and results[m][i].get("verdict", {}).get("verdict") in {"faux", "partiel"}
        ]
        if not bad:
            lines.append("Aucune.")
        for q, entry in bad:
            points = q.get("essentiel") or []
            present = entry["verdict"].get("points_presents") or []
            missing = [p for i, p in enumerate(points) if i >= len(present) or not present[i]]
            lines += [
                f"**{q['id']} – {q['question']}** ({entry['verdict']['verdict']})",
                "",
                f"- Attendu : {q['reponse_attendue']}",
                f"- Points manquants : {' ; '.join(missing) or 'aucun'}",
                f"- Analyse du modèle : {entry.get('analyse') or '—'}",
                f"- Réponse : {entry['reponse']}",
                f"- Règles citées : {', '.join(entry['regles']) or 'aucune'} · passages reçus : {', '.join(entry['passages'])}",
                f"- Juge : {entry['verdict']['justification']}",
                "",
            ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- CLI


def main() -> None:
    parser = argparse.ArgumentParser(description="Évalue les réponses des LLM sur le jeu de test.")
    parser.add_argument("--modele", action="append", help=f"modèle(s) à évaluer (défaut : {', '.join(DEFAULT_MODELS)})")
    parser.add_argument("--juge", default=DEFAULT_JUDGE, help=f"modèle juge (défaut : {DEFAULT_JUDGE})")
    parser.add_argument("--methode", choices=["bm25", "dense", "hybride"], default="dense")
    parser.add_argument("-k", type=int, default=5)
    parser.add_argument("--limite", type=int, help="n'évaluer que les N premières questions (essai rapide)")
    args = parser.parse_args()

    models = args.modele or DEFAULT_MODELS
    questions = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    if args.limite:
        questions = questions[: args.limite]
    docs = load_documents()
    retriever = build_retriever(args.methode, docs)
    existing = {a["id"] for a in read_jsonl(PROCESSED_DIR / "articles.jsonl")}

    # 1) Génération : un modèle après l'autre.
    results: dict[str, list[dict]] = {}
    for model in models:
        assistant = Assistant(retriever, OllamaChat(model), docs, k=args.k)
        results[model] = []
        for n, q in enumerate(questions, 1):
            answer = assistant.ask(q["question"])
            results[model].append(asdict(answer))
            print(f"[{model}] {n}/{len(questions)} {q['id']} ({answer.duree_s:.1f} s)", flush=True)

    # 2) Jugement : toutes les réponses d'un coup, avec le même modèle juge.
    judge_chat = OllamaChat(args.juge)
    for model in models:
        for n, q in enumerate(questions, 1):
            entry = results[model][n - 1]
            if q["statut"] == "hors_sujet":
                continue
            entry["verdict"] = judge(judge_chat, q, entry["reponse"])
            print(f"[juge → {model}] {n}/{len(questions)} {q['id']} : {entry['verdict']['verdict']}", flush=True)

    scores = {
        m: score_answers(questions, results[m], [results[m][i].get("verdict") for i in range(len(questions))], existing)
        for m in models
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "" if not args.limite else f"_essai{args.limite}"
    report = render_markdown(models, args.juge, questions, results, scores, args.methode, args.k)
    (RESULTS_DIR / f"generation{suffix}.md").write_text(report, encoding="utf-8")
    (RESULTS_DIR / f"generation{suffix}.json").write_text(
        json.dumps({"scores": scores, "reponses": results}, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print()
    for m in models:
        s = scores[m]
        print(
            f"{m:<16} justesse {s['justesse']:.0%} · bonne règle {s['bonne_regle_citee']:.0%} · "
            f"inventées {len(s['citations_inventees'])}/{s['citations_total']} · hors sujet refusés "
            f"{s['hors_sujet_refuses']} · refus à tort {len(s['refus_a_tort'])} · {s['duree_moyenne_s']:.1f} s/question"
        )
    print(f"\nDétail : {RESULTS_DIR / f'generation{suffix}.md'}")


if __name__ == "__main__":
    main()
