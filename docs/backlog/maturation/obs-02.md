---
id: obs-02
titre: "Arrêt du backfill : accusé de réception et interruption immédiate"
effort: S
categorie: exploitation
phase:
depends_on: [obs-01]
parent:
subtasks: []
---

# [obs-02] — Arrêt du backfill : accusé de réception et interruption immédiate

> Fiche de backlog : sert de **brief (prompt)** pour l'IA.
> Avancement = dossier : `maturation/` → `a-faire/` → `en-cours/` → `fait/`.
> ⚠ **Placement à confirmer par le PO** : même arbitrage que `obs-01`, dont elle dépend.
> Le `depends_on: [obs-01]` est réel : `obs-01` fige le canal (STDERR), le format et le
> niveau de sortie. Les inverser ferait définir deux fois, différemment, où et comment
> l'application parle à l'opérateur.

## Objectif

Le Ctrl+C **fonctionne déjà** sur le backfill — mais il est **muet**. L'opérateur qui
interrompt un run de plusieurs heures n'a strictement aucun retour : ni au moment où il tape,
ni pendant l'attente des fenêtres en vol. Rien ne lui dit que sa demande a été prise en
compte, et rien ne lui permet de forcer un arrêt s'il ne veut pas attendre.

Deux ajouts, aucun changement de la sémantique d'arrêt existante :

1. **Un accusé de réception immédiat** au premier Ctrl+C, disant ce qui va se passer.
2. **Une porte de sortie** : un second Ctrl+C interrompt immédiatement.

## Contexte et périmètre

### ⚠ Ancrage dans le code réel (vérifié le 2026-08-22, HEAD `a6724e0`)

- **L'arrêt propre existe et est correct** (l0-04.1, décision d'ancrage n°5) :
  `adapters/backfill.py::_request_stop` (l. 122) est une fonction **pure** qui ne fait que
  `stop_event.set()` ; les handlers sont posés sur `SIGINT` et `SIGBREAK` (Windows) dans
  `run_backfill` (l. 204-212) et **restaurés dans un `finally`**. `_process_site` teste
  `stop_event.is_set()` **en tête de boucle** : la fenêtre en cours va à son terme, les
  suivantes du site sont abandonnées, et les futures non démarrées sont annulées.
  ⛔ **Cette sémantique ne change pas** — elle est validée par l'oracle O3 de `l0-04.1`.
- **Ce qui manque est le retour à l'écran, pas le mécanisme.** Le seul message d'interruption
  existant est `cli/backfill.py:91` (« ⚠ backfill interrompu (SIGINT) : soumissions
  arrêtées ») — écrit par `_report_counters`, donc **après** le retour de `run_backfill`,
  c'est-à-dire une fois toutes les fenêtres en vol terminées. Sur des chips Sentinel-2, cela
  peut représenter plusieurs minutes de silence complet.
- **Il n'existe aujourd'hui AUCUN moyen d'obtenir un arrêt immédiat** : un second Ctrl+C
  ne fait que re-positionner le même `Event` déjà positionné. La seule issue est un `kill`
  depuis un autre terminal.
- ⚠ **Une exception ne rendrait PAS la main non plus** — c'est le point technique de la
  fiche. Le thread principal est bloqué dans `as_completed`, à l'intérieur d'un
  `with ThreadPoolExecutor(...)` ; son `__exit__` appelle `shutdown(wait=True)` et **attend
  la fin de tous les workers**. Lever `KeyboardInterrupt` depuis le handler produirait donc
  exactement l'attente que l'utilisateur cherche à éviter.
- **Un arrêt brutal est SÛR pour les données, et c'est vérifiable** :
  `adapters/ingestion.py` écrit les chips (`write_chips`) **avant** le manifeste (l. 352 et
  372), et `manifests._write_json_atomic` (l. 167) écrit un fichier temporaire puis
  `replace`. Un process tué ne peut donc pas produire un item faussement « ingéré ». Au pire
  il laisse des **chips orphelins sans manifeste** — réingérés au run suivant, jamais lus — et
  un résidu `.<nom>.<pid>.<tid>.tmp` qu'aucun `glob` du projet ne voit (garantie explicite du
  docstring de `_write_json_atomic`).
- **Un test existant est à adapter** : `tests/test_backfill.py:354` appelle
  `_request_stop(stop_event, 0, None)` — trois arguments positionnels. Toute évolution de
  signature le touche. Il est importé l. 34.

### ⭐ Décisions actées

- **D1 — Le handler reste PUR.** `_request_stop` gagne un paramètre
  `on_stop_requested: Callable[[bool], None] | None`, appelé avec `already_requested` (vrai
  si `stop_event` était **déjà** positionné). Il ne décide de rien : « que faire du second
  Ctrl+C » est une politique, elle appartient à `cli/`, pas à `adapters/`. La fonction reste
  testable par appel direct, comme aujourd'hui.
- **D2 — Premier Ctrl+C : message immédiat**, disant les trois choses que l'opérateur a
  besoin de savoir : la demande est prise en compte, les fenêtres en cours vont à leur terme
  (rien de nouveau n'est lancé), et un second Ctrl+C interrompt immédiatement.
- **D3 — Second Ctrl+C : `os._exit(130)`**, après avoir vidé STDERR. `130` = `128 + SIGINT`,
  la convention shell. `os._exit` et non une exception, pour la raison ancrée ci-dessus
  (`shutdown(wait=True)` annulerait l'effet recherché).
- **D4 — L'arrêt brutal s'annonce.** Le message du second Ctrl+C dit qu'il peut laisser des
  fichiers partiels sans manifeste, réingérés au run suivant. Une surprise documentée n'en
  est plus une ; le run suivant les corrige par idempotence (oracle O4 de `l0-04.1`).
- **D5 — ⚠ Le message du handler s'écrit par `os.write(2, ...)`, PAS par `logging`.**
  Motif : un handler de signal s'exécute dans le thread principal entre deux bytecodes ;
  passer par `logging` prendrait un verrou de handler et expose à un **interblocage** si le
  signal frappe pendant que ce même thread le détient. `os.write` sur le descripteur 2 est
  sûr en contexte de signal, et reste sur le canal figé par `obs-01` (STDERR). C'est une
  exception **motivée** à `obs-01`, pas un canal concurrent : elle est limitée aux deux
  messages du handler.
- **D6 — Le message final existant (`cli/backfill.py:91`) est conservé** : il joue un rôle
  différent (bilan après arrêt, avec les compteurs), et un test l'atteste.

### Fichiers touchés

- `src/tiny_wae/adapters/backfill.py` — signature de `_request_stop` (D1) et câblage du
  `functools.partial` dans `run_backfill` ; nouveau paramètre `on_stop_requested` de
  `run_backfill`, transmis au handler.
- `src/tiny_wae/cli/backfill.py` — la politique : les deux messages, et `os._exit(130)`.
- `tests/test_backfill.py` — l. 354 adaptée à la nouvelle signature ; **ne pas la supprimer**,
  l'oracle O3 de `l0-04.1` doit continuer de passer à l'identique.
- `tests/test_cli_backfill.py` — les oracles ci-dessous.

## Définition de « terminé »

- [ ] Un premier Ctrl+C produit un message **avant** toute attente, portant les trois
      informations de D2.
- [ ] Un second Ctrl+C termine le process **immédiatement**, code de sortie **130**.
- [ ] La sémantique d'arrêt de `l0-04.1` est **inchangée** : fenêtre en cours menée à terme,
      tâches en file annulées, `interrupted` vrai, manifestes tous relisibles.
- [ ] `_request_stop` reste une fonction pure, testable par appel direct.
- [ ] Le message du second Ctrl+C mentionne les résidus possibles (D4).
- [ ] `just check` vert au commit de la fiche.

## Oracle / recette (figé AVANT implémentation)

| # | Critère mesuré | Seuil de succès |
|---|---|---|
| O1 | `_request_stop` appelé directement, 1re fois, avec un espion | l'espion est appelé **exactement une fois** avec `already=False` ; `stop_event` positionné |
| O2 | 2e appel direct sur le même `stop_event` | l'espion reçoit `already=True` ; `stop_event` toujours positionné |
| O3 | **rejeu à l'identique de l'oracle O3 de `l0-04.1`** (`test_backfill_sigint_arrete_soumissions_et_attend_en_cours_o3`) | passe **sans modification de son corps** hors adaptation de signature : tâche en cours menée à terme, tâches en file annulées, `interrupted` vrai, **100 %** des manifestes relus par `read_manifest` |
| O4 | texte du message de 1er Ctrl+C, sur **STDERR** | contient les 3 informations de D2 ; **rien** sur STDOUT |
| O5 | **sous-processus réel** : `backfill` sur fixtures, `SIGINT` envoyé une fois | le message d'O4 apparaît **avant** que le process ne se termine (mesuré sur le flux, pas a posteriori) |
| O6 | même sous-processus, **second** `SIGINT` | le process rend la main ; code de sortie **130** |
| O7 | état du `data_root` après O6 | **0** manifeste illisible ; `list_for_site` ne retourne aucun résidu `.tmp` |
| O8 | **mutation** : neutraliser l'appel à `on_stop_requested` dans `_request_stop` | O1, O2 et O4 passent au **ROUGE**, puis au vert après restauration |
| O9 | non-régression | `just check` vert — **250 tests** au départ (+ ceux d'`obs-01`) ; `cli/backfill.py:91` toujours couvert |

**Non testé par cette fiche** (chiffres honnêtes) :

- **O5/O6 ne tournent pas sous Windows** : l'envoi d'un vrai signal n'est pas portable
  linux-64/win-64 — c'est déjà la décision d'ancrage n°5 de `l0-04.1`, qui teste le handler
  par appel direct pour cette raison. Ces deux oracles sont marqués `skipif` sous
  `win32` : **le comportement Windows n'est donc vérifié que par O1-O4**, et
  `CTRL_BREAK_EVENT` n'est pas exercé du tout.
- **L'atomicité des chips n'est pas garantie et n'est pas visée.** Ce qui est garanti, c'est
  l'absence de **manifeste** fantôme : un chip partiel sans manifeste n'est jamais lu, et il
  est réécrit au run suivant. O7 mesure la relisibilité des manifestes, pas l'intégrité des
  GeoTIFF.
- **Aucune reprise n'est ajoutée.** L'idempotence par `grid_hash` fait déjà office de
  reprise ; elle est couverte par l'oracle O4 de `l0-04.1` et n'est pas rejouée ici.
- **Rien sur le comportement du signal sous cwltool / PID-FLOW** : le moteur peut ne pas
  propager `SIGINT` au job. Hors périmètre.
- **Aucun `SIGTERM`** : seuls `SIGINT` et `SIGBREAK` sont traités, comme aujourd'hui. Un
  `kill` ordinaire reste brutal et non annoncé.

## Notes / pistes

Origine : lancement réel d'un `backfill --sites all --months 48 --workers 6`, sur lequel les
deux manques sont apparus ensemble — ne rien voir pendant le run (`obs-01`) et ne rien voir
en l'arrêtant (cette fiche).

Piste écartée : compter les Ctrl+C dans l'`Event` lui-même (un `Event` ne compte pas) ou via
un compteur dans `adapters/`. La politique d'arrêt appartient au CLI (D1) ; l'état
« déjà demandé » se lit sur `stop_event` avant de le positionner, sans état supplémentaire.

---

## Résumé de réalisation

*(à remplir avant de déplacer la fiche dans `fait/`)*

- **Ce qui a été fait** : …
- **Verdict de l'oracle** : [chiffres obtenus, y compris défavorables]
- **Commit(s)** : …
- **Date** : AAAA-MM-JJ
