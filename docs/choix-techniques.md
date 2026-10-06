# Choix techniques

*Décidé le 6 octobre 2026*

## LLM : interchangeable, choisi par l'évaluation

Le code doit permettre de changer de modèle par la configuration, sans toucher au code. Le modèle retenu sera celui qui obtient le meilleur score sur `eval/questions.yaml`.

| Candidat | Où | Pourquoi |
| --- | --- | --- |
| Modèle local 7-14B (Mistral, Qwen…) via Ollama | PC (RTX 5070 Ti, 16 Go de VRAM) | Gratuit, hors ligne, tient entièrement en mémoire vidéo |
| Modèle local ~24B quantifié (Q4) via Ollama | PC | Meilleur en français, mais tient tout juste dans 16 Go avec un contexte court |
| Mistral via API (formule gratuite « Experiment ») | Cloud | Bon en français, gratuit pour développer |
| Claude Haiku 4.5 via API | Cloud | Référence de qualité, payant mais peu coûteux sur 37 questions |

Contrainte matérielle : 16 Go de RAM système. Le modèle doit tenir entièrement en mémoire vidéo, sinon le débordement en RAM le rend très lent.

## Embeddings

- Par défaut : **bge-m3** en local (multilingue, gratuit, rapide sur GPU).
- Comparaison : modèle d'embeddings de Mistral.

## Mesures

Pour chaque combinaison LLM × embeddings, on mesure :

- la **recherche** : le bon article figure-t-il parmi les passages retrouvés ?
- la **réponse** : est-elle juste, et cite-t-elle la bonne règle ?
- le **refus** : les questions hors sujet sont-elles bien refusées ?
- la **latence** et le **coût**.
