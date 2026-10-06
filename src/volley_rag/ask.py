"""Génération des réponses : un LLM local (via Ollama) répond à partir des passages retrouvés.

Le modèle doit :

* répondre en français simple, uniquement à partir des extraits fournis ;
* citer les numéros de règle utilisés ;
* signaler les passages réservés aux compétitions FIVB ;
* refuser les questions hors du règlement du volley en salle.

La sortie est contrainte en JSON (sorties structurées d'Ollama) pour être exploitable par l'évaluation.

Usage ::

    python -m volley_rag.ask "Si je touche le filet, c'est faute ?"
    python -m volley_rag.ask --modele mistral-nemo "Le libéro peut-il servir ?"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from volley_rag.documents import load_documents
from volley_rag.embeddings import DEFAULT_HOST

DEFAULT_CHAT_MODEL = os.environ.get("VOLLEY_RAG_MODEL", "qwen3:14b")

SYSTEM_PROMPT = """Tu es un assistant qui explique les règles officielles du volley-ball en salle \
(Règles officielles FIVB 2025-2028) à des joueurs amateurs francophones.

Règles impératives :
1. Réponds UNIQUEMENT à partir des extraits du règlement fournis. N'utilise pas tes connaissances \
personnelles : elles peuvent être fausses ou périmées (les règles ont changé en 2025).
2. Cite les numéros des articles qui justifient ta réponse (par exemple 9.3.4), dans le champ "regles". \
Ne cite que des numéros présents dans les extraits.
3. Les passages marqués [Compétitions FIVB, mondiales et officielles uniquement] ne s'appliquent pas \
en club : précise-le si tu t'appuies dessus.
4. Si la question ne porte pas sur les règles du volley-ball en salle (tactique, technique, matériel, \
beach-volley, autre sport…), mets "hors_sujet" à true, laisse "regles" vide et explique en une phrase \
que tu ne réponds qu'aux questions sur le règlement du volley en salle.
5. Si les extraits ne permettent pas de répondre, dis-le clairement au lieu d'inventer.
6. Réponse courte (3 à 6 phrases), en langage simple, en tutoyant. Commence par la réponse \
(oui / non / ça dépend), puis explique."""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "reponse": {"type": "string"},
        "regles": {"type": "array", "items": {"type": "string"}},
        "hors_sujet": {"type": "boolean"},
    },
    "required": ["reponse", "regles", "hors_sujet"],
}


# --------------------------------------------------------------------------- client Ollama


class OllamaChat:
    """Appel à l'API ``/api/chat`` d'Ollama, sans streaming, température 0."""

    def __init__(self, model: str = DEFAULT_CHAT_MODEL, host: str = DEFAULT_HOST, num_ctx: int = 8192):
        self.model = model
        self.host = host.rstrip("/") if host.startswith("http") else f"http://{host.rstrip('/')}"
        self.num_ctx = num_ctx

    def chat(self, messages: list[dict], schema: dict | None = None) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0, "num_ctx": self.num_ctx},
        }
        if schema is not None:
            payload["format"] = schema
        if self.model.startswith("qwen3"):
            payload["think"] = False  # pas de raisonnement visible : réponses plus rapides
        request = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                content = json.loads(response.read())["message"]["content"]
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            if exc.code == 404:
                raise RuntimeError(
                    f"Le modèle « {self.model} » n'est pas installé : lance `ollama pull {self.model}`."
                ) from exc
            raise RuntimeError(f"Erreur Ollama {exc.code} : {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Impossible de joindre Ollama sur {self.host}. Est-il lancé ?") from exc
        return strip_thinking(content)


def strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def parse_json_answer(text: str) -> dict:
    """Lit la réponse JSON du modèle, avec un repli si le JSON est entouré de texte."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {"reponse": text.strip(), "regles": [], "hors_sujet": False, "json_invalide": True}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {"reponse": text.strip(), "regles": [], "hors_sujet": False, "json_invalide": True}
    regles = [str(r).strip().removeprefix("règle ").removeprefix("Règle ") for r in data.get("regles", [])]
    return {
        "reponse": str(data.get("reponse", "")).strip(),
        "regles": [r for r in regles if r],
        "hors_sujet": bool(data.get("hors_sujet", False)),
    }


# --------------------------------------------------------------------------- assistant


@dataclass
class Answer:
    question: str
    reponse: str
    regles: list[str]
    hors_sujet: bool
    passages: list[str] = field(default_factory=list)  # ids des sections fournies au modèle
    pages: dict[str, list[int]] = field(default_factory=dict)
    duree_s: float = 0.0
    json_invalide: bool = False


def format_context(docs: list[dict]) -> str:
    blocks = []
    for doc in docs:
        pages = ", ".join(str(p) for p in doc.get("pages_imprimees", []))
        blocks.append(f"<extrait id=\"{doc['id']}\" pages=\"{pages}\">\n{doc['texte']}\n</extrait>")
    return "\n\n".join(blocks)


class Assistant:
    def __init__(self, retriever, chat, docs: list[dict], k: int = 5):
        self.retriever = retriever
        self.chat = chat
        self.by_id = {d["id"]: d for d in docs}
        self.k = k

    def ask(self, question: str) -> Answer:
        start = time.perf_counter()
        hits = self.retriever.search(question, self.k)
        docs = [self.by_id[h.id] for h in hits]
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Extraits du règlement :\n\n{format_context(docs)}\n\nQuestion du joueur : {question}",
            },
        ]
        parsed = parse_json_answer(self.chat.chat(messages, schema=ANSWER_SCHEMA))
        return Answer(
            question=question,
            reponse=parsed["reponse"],
            regles=parsed["regles"],
            hors_sujet=parsed["hors_sujet"],
            passages=[d["id"] for d in docs],
            pages={d["id"]: d.get("pages_imprimees", []) for d in docs},
            duree_s=time.perf_counter() - start,
            json_invalide=parsed.get("json_invalide", False),
        )


def build_assistant(model: str = DEFAULT_CHAT_MODEL, methode: str = "dense", k: int = 5) -> Assistant:
    from volley_rag.retrieval import build_retriever

    docs = load_documents()
    return Assistant(build_retriever(methode, docs), OllamaChat(model), docs, k=k)


# --------------------------------------------------------------------------- CLI


def main() -> None:
    parser = argparse.ArgumentParser(description="Pose une question sur les règles du volley.")
    parser.add_argument("question")
    parser.add_argument("--modele", default=DEFAULT_CHAT_MODEL, help="modèle Ollama (défaut : qwen3:14b)")
    parser.add_argument("--methode", choices=["bm25", "dense", "hybride"], default="dense")
    parser.add_argument("-k", type=int, default=5, help="nombre de passages fournis au modèle")
    args = parser.parse_args()

    assistant = build_assistant(args.modele, args.methode, args.k)
    answer = assistant.ask(args.question)
    print(answer.reponse)
    if answer.regles:
        refs = []
        for r in answer.regles:
            section = next((s for s in answer.passages if r == s or r.startswith(s + ".")), None)
            pages = answer.pages.get(section, []) if section else []
            refs.append(f"{r} (p. {', '.join(map(str, pages))})" if pages else r)
        print(f"\nRègles : {' · '.join(refs)}")
    print(f"\n[{args.modele} · {answer.duree_s:.1f} s · passages : {', '.join(answer.passages)}]")


if __name__ == "__main__":
    main()
