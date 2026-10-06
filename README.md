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

## Structure du dépôt

```
chatbot_regles_volley/
├── data/
│   ├── sources.yaml      # liste des documents officiels
│   ├── raw/              # PDF téléchargés (ignorés par git)
│   └── processed/        # textes découpés, index (ignorés par git)
├── docs/
│   └── analyse-marche.md # étude préalable
├── eval/
│   └── questions.yaml    # jeu de test (questions + réponse attendue + règle)
├── scripts/
│   └── download_sources.py
├── src/                  # code du chatbot (à venir)
└── tests/                # tests automatisés (à venir)
```

## Feuille de route

- [x] Analyse de marché et de l'existant
- [ ] Jeu de test : 20 questions de terrain + cas du casebook + questions pièges
- [ ] Mesure de départ : réponses d'un chatbot généraliste sur le jeu de test
- [ ] Extraction et découpage du règlement (par article, avec numéro et page)
- [ ] Recherche (embeddings + éventuellement reranking)
- [ ] Génération avec citation obligatoire et refus hors sujet
- [ ] Évaluation chiffrée et publication des résultats ici
- [ ] Interface web simple
- [ ] Extensions : visualiseur de rotations, beach, anglais

## Avertissement

Projet personnel et non officiel. Il ne remplace ni le texte des règles ni les décisions des arbitres. Non affilié à la FIVB ni à la FFVB.
