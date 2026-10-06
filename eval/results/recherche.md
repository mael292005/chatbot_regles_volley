# Évaluation de la recherche

*Générée le 2026-10-06 par `python -m volley_rag.eval_retrieval`.*

34 questions du jeu de test (hors sujet exclues). Un succès = au moins une section attendue parmi les k premiers résultats.

| Méthode | Recall@1 | Recall@3 | Recall@5 | MRR |
| --- | ---: | ---: | ---: | ---: |
| bm25 | 59% | 85% | 88% | 0.72 |

## Échecs de bm25 (bonne section absente du top 5)

| Question | Attendu | Obtenu (top 5) | Rang |
| --- | --- | --- | ---: |
| q009 – Après mon smash, ma main passe au-dessus du filet chez l'adversaire. C'est faute ? | 11.1 | 12.6, 13.3, 23.3, 9.1, 12.5 | 6 |
| q010 – Qu'est-ce qui est considéré comme un ballon porté ? | 13.1, 9.2, 9.3 | 11.4, 10.1, 4.5, 3.3, 14.4 | 6 |
| q014 – J'ai le droit de jouer le ballon avec le pied ? | 9.2 | 11.4, 7.4, 4.4, 29.2, 11.2 | > 10 |
| q025 – Combien de temps j'ai pour servir ? | 12.4 | 7.6, 6.1, 12.2, 22.2, 15 | > 10 |
