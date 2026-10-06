"""Calcul des embeddings via un serveur Ollama local (par défaut : bge-m3)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import numpy as np

DEFAULT_MODEL = "bge-m3"
DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


class OllamaEmbedder:
    """Transforme des textes en vecteurs normalisés avec l'API ``/api/embed`` d'Ollama."""

    def __init__(self, model: str = DEFAULT_MODEL, host: str = DEFAULT_HOST, batch_size: int = 16):
        self.model = model
        self.host = host.rstrip("/")
        if not self.host.startswith("http"):
            self.host = f"http://{self.host}"
        self.batch_size = batch_size

    def _post(self, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{self.host}/api/embed",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            if exc.code == 404 and "not found" in detail:
                raise RuntimeError(
                    f"Le modèle « {self.model} » n'est pas installé dans Ollama : lance `ollama pull {self.model}`."
                ) from exc
            raise RuntimeError(f"Erreur Ollama {exc.code} : {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Impossible de joindre Ollama sur {self.host}. Vérifie qu'il est lancé (icône Ollama ou `ollama serve`)."
            ) from exc

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            vectors.extend(self._post({"model": self.model, "input": batch})["embeddings"])
        matrix = np.asarray(vectors, dtype=np.float32)
        return normalize(matrix)


def normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms
