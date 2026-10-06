"""Tests de la génération et de son évaluation, avec un faux LLM (sans Ollama)."""

from __future__ import annotations

import json
import sys

import pytest

from volley_rag import ask as ask_module
from volley_rag import eval_generation
from volley_rag.ask import Assistant, format_context, parse_json_answer, strip_thinking
from volley_rag.documents import PROCESSED_DIR
from volley_rag.eval_generation import cites_expected_rule, judge, rule_matches, score_answers
from volley_rag.retrieval import Hit

DOCS = [
    {"id": "11.3", "texte": "Règle 11.3 – CONTACT AVEC LE FILET\n11.3.1 Le contact du filet est une faute.", "pages_imprimees": [31]},
    {"id": "19.3", "texte": "Règle 19.3 – Le Libéro ne peut ni servir, ni contrer.", "pages_imprimees": [42, 43]},
]


class FixedRetriever:
    name = "fixe"

    def search(self, query, k=5):
        return [Hit(id=d["id"], score=1.0, rank=r + 1) for r, d in enumerate(DOCS[:k])]


class FakeChat:
    def __init__(self, reply):
        self.reply = reply
        self.messages = None

    def chat(self, messages, schema=None):
        self.messages = messages
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


# --------------------------------------------------------------------------- parsing


def test_parse_json_answer_clean():
    parsed = parse_json_answer('{"reponse": "Non.", "regles": ["règle 19.3.1.3"], "hors_sujet": false}')
    assert parsed == {"reponse": "Non.", "regles": ["19.3.1.3"], "hors_sujet": False}


def test_parse_json_answer_with_surrounding_text():
    parsed = parse_json_answer('Voici : {"reponse": "Oui.", "regles": ["9.2.1"], "hors_sujet": false} fin')
    assert parsed["regles"] == ["9.2.1"]


def test_parse_json_answer_not_json():
    parsed = parse_json_answer("Je ne sais pas.")
    assert parsed["json_invalide"] and parsed["reponse"] == "Je ne sais pas."


def test_strip_thinking():
    assert strip_thinking("<think>hmm</think>\n{\"a\": 1}") == '{"a": 1}'


# --------------------------------------------------------------------------- assistant


def test_context_contains_ids_and_pages():
    context = format_context(DOCS)
    assert '<extrait id="19.3" pages="42, 43">' in context


def test_assistant_passes_context_and_returns_answer():
    chat = FakeChat({"reponse": "Non, le libéro ne peut pas servir.", "regles": ["19.3.1.3"], "hors_sujet": False})
    answer = Assistant(FixedRetriever(), chat, DOCS, k=2).ask("Le libéro peut-il servir ?")
    assert answer.reponse.startswith("Non")
    assert answer.regles == ["19.3.1.3"]
    assert answer.passages == ["11.3", "19.3"]
    user_message = chat.messages[1]["content"]
    assert "Question du joueur : Le libéro peut-il servir ?" in user_message
    assert "Le Libéro ne peut ni servir" in user_message
    assert "UNIQUEMENT à partir des extraits" in chat.messages[0]["content"]


# --------------------------------------------------------------------------- métriques


def test_rule_matches_hierarchy():
    assert rule_matches("9.2.3.2", "9.2.3")
    assert rule_matches("9.2.3", "9.2.3.2")
    assert not rule_matches("9.2.31", "9.2.3")
    assert not rule_matches("9.3", "9.2.3")
    assert cites_expected_rule(["1.1", "9.3.4"], ["9.3.4", "9.2.3"])


def test_judge_reads_verdict_and_handles_garbage():
    q = {"question": "q", "reponse_attendue": "Oui."}
    assert judge(FakeChat({"verdict": "partiel", "justification": "manque"}), q, "Oui")["verdict"] == "partiel"
    assert judge(FakeChat("n'importe quoi"), q, "Oui")["verdict"] == "faux"


def test_score_answers():
    questions = [
        {"id": "a", "statut": "officielle", "regles": ["9.3.4"]},
        {"id": "b", "statut": "officielle", "regles": ["19.3.1.3"]},
        {"id": "c", "statut": "hors_sujet", "regles": []},
    ]
    answers = [
        {"regles": ["9.3.4", "99.9"], "hors_sujet": False, "duree_s": 1.0},
        {"regles": ["11.3"], "hors_sujet": False, "duree_s": 2.0},
        {"regles": [], "hors_sujet": True, "duree_s": 3.0},
    ]
    verdicts = [{"verdict": "correct"}, {"verdict": "partiel"}, None]
    s = score_answers(questions, answers, verdicts, existing={"9.3.4", "11.3", "19.3.1.3"})
    assert s["justesse"] == pytest.approx((1 + 0.5 + 1) / 3)
    assert s["bonne_regle_citee"] == pytest.approx(0.5)
    assert s["citations_inventees"] == ["99.9"]
    assert s["hors_sujet_refuses"] == "1/1"
    assert s["refus_a_tort"] == []
    assert s["duree_moyenne_s"] == pytest.approx(2.0)


# --------------------------------------------------------------------------- bout en bout (faux LLM)


@pytest.mark.skipif(not (PROCESSED_DIR / "sections.jsonl").exists(), reason="extraction non lancée")
def test_eval_generation_end_to_end(monkeypatch, tmp_path):
    class ScriptedChat:
        def __init__(self, model, *args, **kwargs):
            self.model = model

        def chat(self, messages, schema=None):
            if "verdict" in json.dumps(schema or {}):
                return json.dumps({"verdict": "correct", "justification": "ok"})
            return json.dumps({"reponse": "Oui.", "regles": ["9.3.4"], "hors_sujet": False})

    from volley_rag.retrieval import BM25Retriever

    monkeypatch.setattr(eval_generation, "OllamaChat", ScriptedChat)
    monkeypatch.setattr(eval_generation, "build_retriever", lambda methode, docs: BM25Retriever(docs))
    monkeypatch.setattr(eval_generation, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(sys, "argv", ["eval", "--modele", "faux-a", "--modele", "faux-b", "--limite", "3"])
    eval_generation.main()

    report = (tmp_path / "generation_essai3.md").read_text(encoding="utf-8")
    assert "| faux-a |" in report and "| faux-b |" in report
    data = json.loads((tmp_path / "generation_essai3.json").read_text(encoding="utf-8"))
    assert len(data["reponses"]["faux-a"]) == 3
    assert data["scores"]["faux-a"]["citations_inventees"] == []


def test_qwen3_disables_thinking(monkeypatch):
    sent = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"message": {"content": "{}"}}).encode()

    def fake_urlopen(request, timeout=0):
        sent.update(json.loads(request.data))
        return FakeResponse()

    monkeypatch.setattr(ask_module.urllib.request, "urlopen", fake_urlopen)
    ask_module.OllamaChat("qwen3:14b").chat([{"role": "user", "content": "x"}])
    assert sent["think"] is False and sent["options"]["temperature"] == 0
    sent.clear()
    ask_module.OllamaChat("mistral-nemo").chat([{"role": "user", "content": "x"}])
    assert "think" not in sent
