# Analyse de marché — Assistant règles volley

*Mise à jour : 6 octobre 2026*

## Résumé

Le créneau existe : aucun outil grand public ne répond en français, en conversation, sur les règles du volley en salle en citant l'article officiel.

- **Le besoin est réel** : les règles ont changé en 2025 et les sites qui les résument se contredisent, parfois sur des points que le texte officiel tranche clairement.
- **Le corpus est là** : règles FIVB 2025-2028 en français (PDF officiel), casebook FIVB 2025 et consignes d'arbitrage (en anglais).
- **L'existant est éclaté** : simulateurs de rotation, apps de feuille de match, lecteurs de PDF de règles, et quelques prototypes RAG sur GitHub, tous en anglais ou en thaï.
- **Notre angle** : un assistant français, pour joueur amateur, qui cite l'article, sait dire « je ne sais pas », et dont la fiabilité est mesurée sur un jeu de test publié.
- **Ce qui manque encore** : la voix des joueurs français eux-mêmes, à recueillir par un questionnaire.

## Le besoin

| Aspect | Ce qu'on sait |
| --- | --- |
| Profil | Joueur amateur, en salle, sans formation d'arbitrage |
| Langue | Français d'abord, anglais plus tard |
| Déjà connu | Les postes (passeur, central, réceptionneur-attaquant, pointu, libéro) |
| Flou | Rotations, fautes de position, fautes au filet, rôle du libéro |
| Moment d'usage | Avant ou après un match, pour comprendre une action ou un coup de sifflet |
| Extensions possibles | Beach-volley, version anglaise, petite app avec choix de la langue |

Le bot doit répondre simplement, donner le numéro de règle pour vérifier, et dire quand une question sort du règlement (tactique, technique).

## Le corpus officiel disponible

La FFVB ne réécrit pas les règles du jeu : elle diffuse celles de la FIVB.

| Document | Langue | Rôle dans le projet |
| --- | --- | --- |
| [Règles officielles de volleyball 2025-2028 (FIVB)](https://www.fivb.com/wp-content/uploads/2025/06/FIVB-Volleyball_Rules2025_2028-FR-v04.pdf) | FR | Source principale : 30 règles en 8 chapitres, figures, définitions, index |
| [Official Volleyball Rules 2025-2028](https://www.fivb.com/wp-content/uploads/2025/01/FIVB-Volleyball_Rules2025_2028-EN-v05.pdf) | EN | Version anglaise |
| [Casebook FIVB 2025](https://inside.cev.eu/media/n40ey4ap/casebook-2025.pdf) | EN | Cas concrets avec décision : idéal pour le jeu de test |
| [Refereeing Guidelines 2025](https://inside.cev.eu/media/bm4jik3r/new-guidelines-instructions-2025.pdf) | EN | Interprétations d'arbitrage, tests en cours |
| [Documents d'arbitrage FFVB](https://extranet.ffvb.org/documents-ffvb/arbitrage/) | FR | Confirme la diffusion des règles FIVB 2025-2028 |
| [Règlements FFVB](https://extranet.ffvb.org/196-37-1-Statuts-et-Reglements-FFVB) | FR | Spécificités françaises de compétition, à trier plus tard |

- **Deux niveaux dans le texte** : les passages en gras ne valent que pour les compétitions FIVB et mondiales. Il faut les étiqueter à l'indexation.
- **Renvois entre articles** : la marge « Voir Règles » relie les articles entre eux et peut enrichir la recherche.

## Constat clé : le web se contredit sur les règles 2025-2028

| Ce qu'on lit en ligne | Où | Ce que dit le texte officiel 2025-2028 |
| --- | --- | --- |
| La double touche sur la passe n'est plus sanctionnée | [Volley Urbain](https://volleyurbain.com/nouvelles-regles-de-volley-ball-2025-2028/), [Supporters En Volley Vous](https://www.supporters-envolley-vous.fr/nouvelles-regles-du-volley-2025/) | Toujours une faute (9.3.4). Seule la première touche d'équipe tolère des contacts successifs (9.2.3.2). |
| Le placement libre de l'équipe au service n'est qu'un essai VNL 2025 | [PlayingVolley](https://www.playingvolley.com/fivb-rulebook-2025-2028/) | C'est dans la règle 7.4 : seule l'équipe en réception doit respecter l'ordre de rotation. |
| L'équipe au service doit aussi respecter le chevauchement | [Volleyball Vault](https://volleyballvault.com/volleyball-rotations/), [Volleyball Blaze](https://volleyballblaze.com/volleyball-rotations-guide/) | Vrai avant 2025, périmé depuis (7.4). |
| Le moment de la faute de position en réception change | [Consignes d'arbitrage 2025](https://inside.cev.eu/media/bm4jik3r/new-guidelines-instructions-2025.pdf) | Test autorisé sur les épreuves FIVB, sans modifier le texte des règles. |

Conséquence : chaque réponse doit préciser le statut de ce qu'elle affirme (règle officielle, test international, ancienne règle).

## L'existant : apps et outils

| Outil | Type | Ce qu'il fait | Ce qui manque |
| --- | --- | --- | --- |
| [Volleyball Rotations](https://volleyballrotations.app/) | App iOS/Android | Planifie les 6 rotations, vérifie les chevauchements | Pour coachs, n'explique pas les règles |
| [Volleylete](https://volleylete.com/tools/rotations), [volleyball-rotations.com](https://volleyball-rotations.com/), [Rotate123](https://www.rotate123.com/5-1-volleyball-rotation) | Simulateurs web | Visualisent systèmes et placements | En anglais, sans questions-réponses |
| [volley-5-1](https://github.com/VincentGvr/volley-5-1) | Page web open source | Quiz de placement en 5-1, en français | Un seul système, pas de règles |
| [VolleyRef](https://volleyref.app/), [Volleyball Scoreboard & Ref](https://apps.apple.com/us/app/volleyball-scorekeeper/id6769718057) | Apps de marque | Score, remplacements, libéro | Pour arbitrer, pas pour comprendre |
| [Volleyball Referee Signals](https://apps.apple.com/in/app/volleyball-referee-signals/id6785905702) | App iOS | Gestes d'arbitre + quiz | Uniquement les gestes, en anglais |
| [Read Volley](https://mwm.ai/apps/read-volley/6744039773) | App iOS | Règles, casebook et consignes | Lecture de PDF, pas de réponse directe |

Le vrai concurrent reste un chatbot généraliste : gratuit et en français, mais sans garantie d'utiliser l'édition 2025-2028.

## L'existant : projets RAG volley sur GitHub

| Dépôt | Stack | Points forts | Limites |
| --- | --- | --- | --- |
| [Anneta17/volleyball-knowledge-rag](https://github.com/Anneta17/volleyball-knowledge-rag) | FAISS, Sentence Transformers, reranker, Ollama | Cite les pages, local | Anglais, prototype CLI, pas d'évaluation chiffrée |
| [thiarat/chatVolley](https://github.com/thiarat/chatVolley) | FastAPI, Angular, PostgreSQL | Application complète | En thaï, dépend d'API tierces |
| [nad11ng/game-rules-rag-chatbot](https://github.com/nad11ng/game-rules-rag-chatbot) | ChromaDB, Streamlit, pytest | 50 questions de test, dont pièges | Pas sur le volley |

## Positionnement

L'assistant français des règles du volley en salle, qui cite l'article et dont on peut vérifier la fiabilité.

1. Français d'abord, à partir du texte officiel français.
2. Chaque réponse cite sa règle (article et page).
3. Statut explicite : officielle, test, ancienne.
4. Refus clair hors règlement ou hors volley.
5. Fiabilité mesurée et publiée.
6. Plus tard : visualiseur de rotations branché sur les règles 7.4 à 7.7.

## Risques et contraintes

| Risque | Parade |
| --- | --- |
| Droits sur les PDF (« © FIVB 2025 ») | Ne pas versionner les PDF : script de téléchargement. Vérifier les conditions avant toute mise en ligne publique. |
| Réponses inventées | Citation obligatoire, refus sans source, taux d'erreur mesuré |
| Casebook en anglais | Traduire les cas pour le jeu de test |
| Règles qui bougent | Dater chaque source, afficher l'édition utilisée |
| Questions tactiques | Trancher le périmètre au cadrage |
| Besoin non validé | Questionnaire auprès du club |

## Prochaines étapes

- [ ] Lister 20 questions déjà posées sur un terrain (début du jeu de test)
- [ ] Questionnaire court dans le club
- [ ] Tester 10 questions pièges sur un chatbot généraliste (point de départ)
- [ ] Trancher le périmètre : règles seules, ou règles + placement tactique
- [ ] Attaquer la partie technique
