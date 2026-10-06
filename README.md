# 🏐 Chatbot Règles Volley

Un assistant conversationnel **en français** qui répond aux questions sur les **règles du volley-ball en salle**, en s'appuyant uniquement sur les textes officiels et en **citant l'article** utilisé pour chaque réponse.

> Statut : **phase de cadrage**. Aucune ligne de code technique pour l'instant — voir la [feuille de route](#feuille-de-route).

---

## Pourquoi ce projet

Les règles du volley ont changé avec l'édition **FIVB 2025-2028**, et les résumés qu'on trouve en ligne se contredisent. Exemples relevés pendant l'analyse de marché :

| Ce qu'on lit en ligne | Ce que dit le texte officiel |
| --- | --- |
| « La double touche sur la passe n'est plus sanctionnée » | Toujours une faute (règle 9.3.4). Seule la 1re touche d'équipe tolère des contacts successifs (9.2.3.2). |
| « Le placement libre au service n'est qu'un test VNL » | C'est dans la règle 7.4 : seule l'équipe en réception doit respecter l'ordre de rotation. |
| « L'équipe au service doit respecter le chevauchement » | Vrai avant 2025, périmé depuis (7.4). |

Un joueur amateur n'a ni le temps ni l'envie de lire 90 pages de règlement. Il a besoin d'une réponse simple **et vérifiable**.

👉 Analyse complète : [`docs/analyse-marche.md`](docs/analyse-marche.md)

## Pour qui

- **Cible principale** : joueur·euse amateur de volley en salle, francophone, qui connaît les postes par la pratique mais pas les règles fines (rotations, fautes de position, filet, libéro).
- **Plus tard** : beach-volley, version anglaise, petite application avec choix de la langue.

## Ce qui le différencie

1. **Français d'abord**, construit sur le texte officiel français.
2. **Chaque réponse cite sa règle** (numéro d'article + page).
3. **Statut explicite** : règle officielle · test en compétition internationale · ancienne règle.
4. **Refus clair** quand la question sort du règlement ou du volley.
5. **Fiabilité mesurée** : jeu de test public et comparaison chiffrée avec un chatbot généraliste.

## Sources officielles

Les PDF ne sont **pas** versionnés dans ce dépôt (droits FIVB). Ils se téléchargent avec :

```bash
python scripts/download_sources.py
```

| Document | Langue | Usage |
| --- | --- | --- |
| Règles officielles de volleyball 2025-2028 (FIVB) | FR | Corpus principal |
| Official Volleyball Rules 2025-2028 (FIVB) | EN | Future version bilingue |
| Casebook FIVB 2025 | EN | Cas concrets → jeu de test |
| Refereeing Guidelines & Instructions 2025 | EN | Interprétations, tests en cours |

La liste exacte (URL, date de consultation) est dans [`data/sources.yaml`](data/sources.yaml).

## Installation

```bash
git clone https://github.com/mael292005/chatbot_regles_volley
cd chatbot_regles_volley
python -m venv .venv && source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install -e ".[dev]"
python scripts/download_sources.py                  # télécharge les PDF officiels
```

## Extraction du règlement

```bash
python -m volley_rag.extraction
```

Le PDF officiel est découpé en **542 articles** (les 30 règles, du niveau `7` au niveau `7.4.3.1`), regroupés en **122 sections** prêtes à indexer (ex. `7.4 – POSITIONS` avec tous ses sous-articles), plus **12 définitions**. Pour chaque article :

- le numéro, le titre, le chapitre et la **page imprimée** (pour citer la source) ;
- le texte, avec les passages réservés aux compétitions FIVB marqués comme tels (ils sont en gras dans le PDF) ;
- les **renvois** de la marge « Voir Règles » vers d'autres articles et figures.

Les fichiers produits (`data/processed/*.jsonl`) ne sont pas versionnés, car ils reprennent le texte officiel.

```bash
pytest   # 34 tests, dont : chaque règle citée dans le jeu de test existe bien dans le règlement
```

## Recherche des articles

Avant de générer une réponse, il faut retrouver les bons passages du règlement. Trois méthodes sont comparées :

| Méthode | Principe | Besoin |
| --- | --- | --- |
| BM25 | mots-clés communs entre la question et l'article | rien |
| Dense | proximité de sens, via les embeddings **bge-m3** | Ollama |
| Hybride | fusion des deux classements (Reciprocal Rank Fusion) | Ollama |

```bash
ollama pull bge-m3
python -m volley_rag.index                                   # embeddings des 122 sections + 12 définitions
python -m volley_rag.retrieval "Si je touche le filet, c'est faute ?"
python -m volley_rag.eval_retrieval                          # mesure sur le jeu de test
```

### Résultats

34 questions du jeu de test (hors sujet exclues). Succès = une section attendue parmi les k premiers résultats.

| Méthode | Recall@1 | Recall@3 | Recall@5 | MRR |
| --- | ---: | ---: | ---: | ---: |
| BM25 | 59 % | 85 % | 88 % | 0,72 |
| Dense (bge-m3) | 65 % | **94 %** | **97 %** | 0,79 |
| Hybride (BM25 + bge-m3) | **82 %** | 91 % | 91 % | **0,87** |

*Mesuré le 6 octobre 2026 sur RTX 5070 Ti (indexation des 134 documents : 51 s).*

- **BM25** échoue sur les écarts de vocabulaire : un joueur dit « porté », le règlement dit « tenu » ; « avec le pied » ne correspond à aucun mot de « n'importe quelle partie du corps ».
- **bge-m3** comble ces écarts : le bon article est dans les 5 premiers pour 33 questions sur 34.
- **L'hybride** place bien plus souvent le bon article en tête, mais perd un peu en Recall@5 : quand BM25 se trompe franchement, il fait descendre la bonne réponse.
- Pour la génération, le modèle recevra les 5 premiers passages : c'est le **Recall@5** qui compte le plus, donc la recherche dense est le meilleur choix par défaut.

Limites : 34 questions seulement (une question = 3 points de pourcentage), rédigées en connaissant le règlement. Le jeu de test doit grandir avec de vraies questions de joueurs. Détail : [`eval/results/recherche.md`](eval/results/recherche.md).

## Poser une question

Le LLM local reçoit les 5 passages trouvés par bge-m3 et doit répondre **uniquement à partir d'eux**, en citant les articles, en signalant les passages réservés aux compétitions FIVB et en refusant le hors sujet. La sortie est contrainte en JSON pour être vérifiable.

```bash
ollama pull qwen3:14b
python -m volley_rag.ask "Si je touche le filet, c'est faute ?"
python -m volley_rag.ask --modele mistral-nemo "Le libéro peut-il servir ?"
```

## Évaluation des réponses

```bash
python -m volley_rag.eval_generation --limite 5    # essai rapide
python -m volley_rag.eval_generation               # qwen3:14b et mistral-nemo, 37 questions
```

| Mesure | Définition |
| --- | --- |
| Justesse | Un LLM juge compare chaque réponse à la réponse attendue : correct (1), partiel (0,5), faux (0). Une question hors sujet bien refusée compte comme correcte. |
| Bonne règle citée | Au moins une règle citée correspond à une règle attendue (même article, ou parent / enfant) |
| Citations inventées | Numéros cités qui n'existent pas dans le règlement |
| Refus | Hors sujet bien refusés ; questions valides refusées à tort |

Résultats : *à mesurer*.

## Structure du dépôt

```
chatbot_regles_volley/
├── data/
│   ├── sources.yaml          # liste des documents officiels
│   ├── raw/                  # PDF téléchargés (ignorés par git)
│   └── processed/            # articles, sections, définitions (ignorés par git)
├── docs/
│   ├── analyse-marche.md     # étude préalable
│   └── choix-techniques.md   # LLM, embeddings, mesures
├── eval/
│   └── questions.yaml        # jeu de test (questions + réponse attendue + règle)
├── scripts/
│   └── download_sources.py
├── eval/results/             # résultats des évaluations (générés)
├── src/volley_rag/
│   ├── extraction.py         # PDF → articles structurés
│   ├── documents.py          # sections + définitions à indexer
│   ├── embeddings.py         # embeddings via Ollama
│   ├── index.py              # construction de l'index
│   ├── retrieval.py          # BM25, dense, hybride
│   ├── eval_retrieval.py     # Recall@k, MRR
│   ├── ask.py                # génération avec citations (Ollama)
│   └── eval_generation.py    # justesse, citations, refus
└── tests/
```

## Feuille de route

- [x] Analyse de marché et de l'existant
- [x] Jeu de test v1 : 37 questions (dont 7 de terrain), 9 catégories, pièges et hors sujet — [`eval/questions.yaml`](eval/questions.yaml)
- [ ] Jeu de test v2 : ajouter les cas du casebook FIVB 2025 et d'autres questions de terrain
- [ ] Mesure de départ : réponses d'un chatbot généraliste sur le jeu de test
- [x] Extraction et découpage du règlement (par article, avec numéro, page, renvois et passages FIVB)
- [x] Recherche : BM25, dense (bge-m3) et hybride, avec évaluation Recall@k / MRR
- [ ] Mesurer dense et hybride sur GPU, puis tester un reranker
- [x] Génération avec citation obligatoire et refus hors sujet (sortie JSON)
- [x] Évaluation des réponses (juge LLM, citations, refus)
- [ ] Mesurer qwen3:14b et mistral-nemo, publier les résultats ici
- [ ] Interface web simple
- [ ] Extensions : visualiseur de rotations, beach, anglais

## Avertissement

Projet personnel et non officiel. Il ne remplace ni le texte des règles ni les décisions des arbitres. Non affilié à la FIVB ni à la FFVB.
