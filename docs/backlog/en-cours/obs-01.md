---
id: obs-01
titre: "Système de logging + progression du backfill"
effort: M
categorie: observabilite
phase:
depends_on: [l0-04.1]
parent:
subtasks: []
---

# [obs-01] — Système de logging + progression du backfill

> Fiche de backlog : sert de **brief (prompt)** pour l'IA.
> Avancement = dossier : `maturation/` → `a-faire/` → `en-cours/` → `fait/`.
> ✅ **Placement validé par le PO le 2026-08-22** (lancement du run) : id hors de la
> séquence `l0-*` du chantier `lot-0-ingestion` (déclarée fermée à `l0-06`), sur le
> précédent d'`out-01` et de `l0-07`.
> Le `depends_on: [l0-04.1]` n'est pas décoratif : c'est cette fiche qui a créé le pool de
> workers et `_process_site`, seul point d'où une progression peut être émise. Elle est en
> `fait/`, la dépendance est donc satisfaite.

## Objectif

Un `backfill --sites all --months 48` porte **1200 fenêtres** (25 sites × 48 mois) et tourne
**plusieurs heures**. Aujourd'hui il n'écrit **rien** avant d'avoir terminé : l'opérateur ne
peut ni savoir où il en est, ni distinguer un run qui avance d'un run bloqué sur un amont
muet. C'est le défaut qui a motivé cette fiche, constaté sur un lancement réel.

Deux objectifs, dans cet ordre :

1. **Poser un véritable système de logging dans l'application** — un canal de diagnostic
   normalisé (niveaux, horodatage, destination, niveau réglable), utilisable par n'importe
   quel module d'`adapters/`, là où il n'existe **aucun** mécanisme aujourd'hui.
2. **Instrumenter le backfill** pour qu'un run long soit suivable en direct, avec un
   **pourcentage d'avancement indicatif**.

## Contexte et périmètre

### ⚠ Ancrage dans le code réel (vérifié le 2026-08-22, HEAD `a6724e0`)

- **Il n'existe aucun logging.** `grep -rn "import logging\|logger" src/ scripts/` → **0
  résultat**. Toute la sortie du projet passe par **38 `typer.echo`** répartis dans 9 modules
  de `cli/`.
- **`adapters/` et `core/` n'écrivent rien sur console** (mesuré : 0 `typer.echo`, 0
  `print`). La règle de couche est tenue aujourd'hui — cette fiche ne doit pas la desserrer
  au-delà de ce qu'elle acte explicitement ci-dessous.
- **Le backfill ne parle qu'à la fin** : `cli/backfill.py::_report_counters` (l. 72-96) est
  appelé **après** le retour de `run_backfill`. Aucune sortie intermédiaire n'existe.
- **Le point d'émission naturel existe déjà** : `adapters/backfill.py::_process_site` boucle
  sur les fenêtres d'un site et dispose sur place de `site.id`, de la `Window`, et de
  l'`IngestOutcome` retourné (donc de `outcome.run.counters`) ou de l'exception capturée.
- **L'ordonnancement rend l'ETA non trivial** (mesuré par simulation le 2026-08-22) : une
  tâche = un site, donc avec 6 workers seuls 6 sites tournent à un instant donné, un 7e ne
  démarrant qu'à la fin complète d'un autre. Conséquences chiffrées sur un run
  `--sites all --months 48 --workers 6` : le 25e site ne démarre qu'à **77 %** du run, et
  la **fin du run se déroule à parallélisme dégradé** (moins de 6 sites actifs). C'est ce
  qui dicte le critère du `?` (D11).
- **La concurrence est réelle** : `_process_site` s'exécute dans N threads d'un
  `ThreadPoolExecutor` (`workers`, défaut `settings.backfill_workers` = **6** dans
  `config/settings.yaml`). Toute écriture console émise depuis ce point est **concurrente**.
  `logging` sérialise par un verrou de handler ; un `print` ne garantit rien.
- **STDOUT est un canal de DONNÉES, pas de diagnostic** : `cli/search.py:110` et
  `cli/sites_list.py:48` y écrivent du JSON destiné à être parsé, et 4 tests de
  `tests/test_cli_search.py` (l. 162, 177, 206, 229) assertent `result.stdout == ""`.
- ⚠ **Piège mesuré, à ne pas découvrir en cours d'implémentation** : sous les versions
  réellement installées (**click 8.4.2 / typer 0.27.1**), `result.output` du `CliRunner`
  **inclut STDERR** (vérifié ; `result.stdout`, lui, ne l'inclut pas). Deux tests en
  dépendent par leur forme et casseraient sur la moindre ligne de log émise pendant
  `sites-list` : `tests/test_cli_commands.py:67` (`len(lines) == 25` sur `result.output`)
  et `test_sites_list_json` (`json.loads(result.output)`).
- **Ailleurs, l'ajout de lignes sur STDERR est non régressif** : les 29 assertions `.stderr`
  (`test_cli_ingest.py` 12, `test_cli_search.py` 4, `test_cli_update.py` 13) et les 5
  assertions de `test_cli_backfill.py` sont **toutes** des tests d'inclusion (`in`) — aucune
  égalité stricte, aucun comptage de lignes.
- **Aucune dépendance à ajouter** : `logging` est dans la stdlib, et
  `tests/test_packaging.py:73` filtre les imports par `sys.stdlib_module_names` — un
  `import logging` n'entre donc pas au contrat de la wheel et ne casse pas ce test.
- ✅ **Verrou levé le 2026-08-22 (décision PO)** : `__main__.py` portait « ⭐ Ce fichier
  n'est PLUS JAMAIS modifié après l0-01.2 ». Cette phrase **disait plus que l'invariant
  réel**, qui est testé mécaniquement par
  `tests/test_cli_discovery.py::test_main_module_has_no_per_command_wiring` : le fichier ne
  doit référencer **aucun module de commande par son nom**. Une option globale ne viole pas
  cet invariant. L'inscription a été reformulée en conséquence — le fichier peut évoluer,
  le câblage par commande reste interdit et vérifié.

  Re-vérifié à `3cd90e2` au moment du dispatch : les 6 emplacements cités ci-dessus sont
  inchangés (seul `__main__.py` a bougé, cf. la puce « verrou levé »).

### ⭐ Décisions actées

- **D1 — `logging` de la stdlib, pas de dépendance nouvelle, pas de mécanisme maison.**
  « Un véritable système de logging » = celui que tout opérateur sait déjà configurer et
  rediriger. Un callback de progression injecté a été écarté : il ferait porter au projet un
  verrou de sérialisation que `logging` fournit déjà.
- **D2 — STDERR exclusivement.** Jamais STDOUT, qui porte des données machine (ancrage
  ci-dessus). Aucun fichier de log, aucune rotation : la redirection est l'affaire de
  l'opérateur (`2> run.log`).
- **D3 — `logging.getLogger(__name__)` par module ; la CONFIGURATION ne vit que dans
  `cli/`.** Un module de bibliothèque n'installe jamais de handler. ⛔ **`core/` reste
  vierge de tout logging** (métier pur, testable à sec) — c'est vérifié par un oracle.
- **D4 — Niveau réglable, précédence : `--log-level` > `TINY_WAE_LOG_LEVEL` > `INFO`.**
  La variable d'environnement n'est pas un luxe : sous PID-FLOW, l'invocation est produite
  par le moteur et la ligne de commande n'est pas modifiable — c'est le même raisonnement
  que `TINY_WAE_DATA_ROOT`.
- **D5 — Les 38 `typer.echo` existants RESTENT.** Le log est un canal **additionnel** de
  progression, pas un remplacement des rapports finaux : 29 assertions de tests en
  dépendent, et un rapport de fin destiné à l'utilisateur n'est pas un événement de
  diagnostic. ⛔ Ne pas « uniformiser » en convertissant l'existant.
- **D6 — Granularité : une ligne par fenêtre TERMINÉE**, succès ou échec — soit ~1200 lignes
  sur un run complet. C'est le grain le plus fin disponible sans instrumenter l'ingestion
  item par item (hors périmètre).
- **D7 — `adapters/backfill.py` loggue directement via son logger de module.** C'est de
  l'I/O, donc la couche `adapters/` y a droit ; `core/` n'y a pas droit (D3).
- **D8 — `__main__.py` porte l'option globale `--log-level`** sur son `@app.callback()`.
  Tranché par le PO le 2026-08-22 : l'inscription qui semblait l'interdire a été corrigée
  (cf. ancrage). ⛔ Le câblage d'une sous-commande y reste interdit — c'est l'invariant
  testé, il ne bouge pas.
- **D9 — Le pourcentage est en FENÊTRES, pas en temps, et il est annoncé comme indicatif.**
  Une fenêtre sans item coûte une requête STAC ; une fenêtre à 6 items coûte 6
  téléchargements de chips. Le `%` ne prétend donc pas mesurer le temps restant.
- **D11 — Un ETA est affiché, et son incertitude est PORTÉE PAR L'AFFICHAGE.** Extrapolation
  linéaire : `restant = (total − done) × elapsed / done`, valant `—` **avant** la première
  fenêtre terminée **et sur la dernière ligne** (`done == total` : il n'y a plus rien à
  attendre, `ETA 0min00` serait du bruit). Il est suffixé d'un `?` sous **deux** conditions, dont l'une suffit :
  1. `done < 5 % du total` (60 fenêtres sur 1200) — l'échantillon est trop court ;
  2. **ou** le nombre de sites encore actifs est **inférieur au nombre de workers** : c'est
     la phase de queue, où le parallélisme s'effondre et où l'ETA devient mécaniquement
     optimiste. **Mesuré sur la simulation** : à 89,8 % du run, l'ETA annonce 18 min alors
     qu'il reste 43 min de C07 seul — une sous-estimation d'un facteur **2,4**, que le `?`
     est précisément là pour signaler.

  ⚠ **Le critère « tous les sites ont démarré » a été essayé puis ÉCARTÉ SUR MESURE.** Une
  tâche = un site (l0-04.1), donc avec 6 workers le 25e site ne démarre qu'après la fin de
  19 autres. Simulation de l'ordonnancement réel (25 sites × 48 fenêtres, 6 workers,
  coûts de fenêtre tirés entre 21 s et 117 s) : le 25e site démarre à **77 % du run**. Un
  `?` présent sur 77 % des lignes ne signale plus rien. Avec le critère retenu, il tombe à
  la 60e ligne. Demandé explicitement par le PO le 2026-08-22, en connaissance du biais.
- **D13 — AUCUN emoji dans le code ni dans les sorties console** (règle projet, posée par
  le PO le 2026-08-22 : « arrêter de mettre des emojis dans le code »). Le niveau de log
  porte déjà la gravité, un pictogramme y est redondant. ⛔ Ne pas écrire `⚠`, `⭐`, `⛔`
  dans un message affiché. Au passage, les **2** occurrences déjà présentes dans les
  messages de `cli/backfill.py` (l. 86 et 91) sont retirées — aucun test ne s'y accroche
  (vérifié). Les accents et flèches (`ÉCHEC`, `→`) ne sont pas concernés : ce sont des
  caractères de texte.
- **D12 — Le calcul de l'ETA est une fonction PURE de `adapters/backfill.py`**
  (`_eta_seconds(done, total, elapsed_s) -> float | None`), testée par appel direct. ⛔ Aucun
  oracle statistique sur sa justesse prédictive : mesurer « l'ETA était-il bon ? » sur des
  fixtures qui tournent en millisecondes ne prouverait rien.
- **D10 — Les deux tests `sites-list` passent de `result.output` à `result.stdout`.** Coût
  nul, et cela fixe leur intention réelle (ils testent une sortie de données) au lieu de les
  laisser exposés au premier log émis en amont.

### Fichiers touchés

- `src/tiny_wae/cli/logging_setup.py` — **nouveau** : `configure_logging(level: str) -> None`,
  seul endroit qui installe un handler (STDERR) et un format.
- `src/tiny_wae/__main__.py` — option globale `--log-level` et appel de
  `configure_logging`. L'inscription du docstring a **déjà** été corrigée (commit du
  2026-08-22) : ne pas la rétablir.
- `src/tiny_wae/adapters/backfill.py` — logger de module ; ligne d'ouverture (nombre de
  sites, de fenêtres, total, workers) et une ligne par fenêtre terminée dans `_process_site`.
  Le total est déjà calculable sur place : `sum(len(w) for w in windows_by_site.values())`.
  Plus les deux fonctions pures `_eta_seconds` / `_format_eta` (D12).
- `tests/test_logging.py` — **nouveau** : les oracles ci-dessous.
- `tests/test_cli_commands.py` — D10 (2 lignes).

### Format de ligne (figé)

```
2026-08-22 16:04:12 INFO     backfill    47/1200 (  3.9%) ETA 2h11?  A01  2022-09-01→2022-10-01  found_stac=3 ingested=2 rejected_clouds=1
2026-08-22 16:04:19 WARNING  backfill    48/1200 (  4.0%) ETA 2h11?  B03  2022-09-01→2022-10-01  ÉCHEC : <message>
```

**Colonnes fixes à gauche, charge utile variable à droite** : l'avancement, le pourcentage
et l'ETA occupent des positions constantes, ce qui les rend lisibles en colonne dans un flux
de 1200 lignes ; les compteurs, de longueur variable, ferment la ligne.

Seuls les compteurs **non nuls** sont rendus, triés par clé — une ligne à 12 compteurs à zéro
est illisible et masque l'information utile.

`ETA` vaut `—` avant la première fenêtre terminée, et porte un `?` tant que les 25 sites
n'ont pas chacun produit au moins une fenêtre (D11).

## Définition de « terminé »

- [ ] `cli/logging_setup.py` existe et est le **seul** module qui installe un handler.
- [ ] Le niveau suit la précédence D4 ; un niveau invalide sort en `exit_codes.USAGE`, pas en
      trace Python.
- [ ] `adapters/backfill.py` émet une ligne d'ouverture puis une ligne par fenêtre terminée.
- [ ] Chaque ligne de progression porte : `n/total`, un pourcentage, un **ETA**, l'id du
      site, les bornes de la fenêtre, et soit les compteurs non nuls, soit le message d'échec.
- [ ] L'ETA vaut `—` avant la première fenêtre terminée et porte un `?` selon les deux
      conditions de D11 (échantillon < 5 %, ou phase de queue).
- [ ] Aucun emoji dans le code ni dans une sortie console ; les 2 de `cli/backfill.py` sont
      retirés (D13).
- [ ] Une fenêtre en échec est loguée en **WARNING**, jamais en INFO.
- [ ] `grep -rn "logging" src/tiny_wae/core/` → **0 résultat**.
- [ ] Les 38 `typer.echo` existants sont **inchangés** (D5).
- [ ] `just check` vert au commit de la fiche.

## Oracle / recette (figé AVANT implémentation)

> Tout se joue sur `FixtureSource` (aucun réseau), comme `tests/test_cli_backfill.py`.

| # | Critère mesuré | Seuil de succès |
|---|---|---|
| O1 | `backfill --sites A01,B09 --months 1 --workers 2`, lignes de progression sur STDERR | **1 ligne par fenêtre traitée**, chacune portant `n/total`, un `%`, l'id du site et les deux bornes de la fenêtre |
| O2 | les `n` de toutes les lignes d'un run | forment exactement une **permutation de `1..total`** — aucun doublon, aucun trou ; le `total` annoncé à l'ouverture == nombre de fenêtres soumises |
| O3 | STDOUT du même run | `result.stdout == ""` — le log ne touche jamais le canal de données |
| O4 | source qui lève sur un site (patron de `test_backfill_echec_sur_1_site_isole_lautre_o2`) | ≥ 1 ligne **WARNING** nommant le site, la fenêtre et le message d'erreur ; le run continue |
| O5 | `--log-level WARNING` sur le run d'O1 | **0** ligne de progression ; les lignes d'échec d'O4 subsistent |
| O6 | `TINY_WAE_LOG_LEVEL=WARNING` sans `--log-level`, puis les deux ensemble | même résultat qu'O5 ; l'option de ligne de commande **gagne** sur la variable |
| O7 | concurrence : run à `--workers 6` sur ≥ 50 fenêtres, chaque ligne confrontée au motif figé | **100 %** des lignes bien formées — aucune ligne entrelacée, tronquée ou fusionnée |
| O8 | `_eta_seconds` par appel direct : `(done=10, total=100, elapsed_s=30.0)`, puis `(done=0, …)`, puis `(done=total, …)` | **`270.0` exactement**, puis `None`, puis `0.0` — aucune division par zéro, aucun négatif |
| O9 | rendu de l'ETA sur une ligne : avant la 1re fenêtre · sites partiellement démarrés · 25 sites démarrés | `ETA —` · `ETA <durée>?` · `ETA <durée>` — le `?` disparaît **exactement** quand le 25e site a produit sa 1re fenêtre |
| O10 | **mutation** : retirer l'appel de log dans `_process_site`, relancer `just test -k logging` | O1 et O2 passent au **ROUGE**, puis au vert après restauration |
| O11 | `grep -rn "logging" src/tiny_wae/core/` | **0** résultat |
| O11bis | recherche d'emoji sur `src/`, `tests/`, `scripts/` restreinte aux **chaînes affichées** | **0** occurrence — et le compte global sur `src/` a **diminué** de 2 par rapport à HEAD `a6724e0` |
| O12 | non-régression | `just check` vert — **250 tests** au départ ; les 29 assertions `.stderr` et les 5 de `test_cli_backfill.py` **inchangées** ; seules les 2 lignes de D10 sont modifiées |

**Non testé par cette fiche** (chiffres honnêtes) :

- **Aucun run réel.** Le gate est hors réseau : la tenue du log sur les ~1200 lignes d'un
  backfill de 48 mois sur le NAS n'est **pas** mesurée ici. C'est à la campagne `l0-04.H` de
  le constater.
- **Ni le `%` ni l'ETA ne sont validés comme prédicteurs de temps.** L'ETA est produit
  (D11) et son **calcul** est testé exactement (O8/O9), mais sa **justesse prédictive ne
  l'est pas** : sur des fixtures qui tournent en millisecondes, un tel oracle ne mesurerait
  que le bruit. L'ETA est faux par construction tant que les 25 sites n'ont pas démarré —
  c'est assumé, signalé par le `?`, et accepté par le PO en connaissance de cause.
- **Les autres CLIs ne sont pas instrumentés.** `ingest`, `update`, `report`, `search`
  gardent leur unique rapport final : le **socle** est transverse, l'**instrumentation** ne
  l'est pas.
- **Rien sur le comportement sous cwltool** (capture de STDERR par le moteur) : à vérifier
  lors d'un passage PID-FLOW, hors périmètre.
- **Aucune sortie structurée** (JSON par ligne) : format texte uniquement.
- **Le niveau DEBUG n'a aucun contenu** : aucun module n'émet en DEBUG à l'issue de cette
  fiche.

## Notes / pistes

- **L'ETA a d'abord été écarté, puis remis au périmètre par le PO** (2026-08-22) : le `%`
  seul ne répond pas à la vraie question d'un run de plusieurs heures (« j'attends ou je
  reviens demain ? »). Le compromis retenu n'est pas de le rendre juste — il ne peut pas
  l'être tôt — mais de **rendre son incertitude visible** (D11).
- Extensions possibles, non retenues ici : `--log-format json`, `--progress-every N` pour
  raréfier les lignes, instrumentation des autres CLIs, ligne de synthèse périodique
  (« 6 sites en cours, 3 terminés »).
- **Ce qui est déjà observable sans cette fiche**, pour un run en cours : chaque fenêtre
  traitée écrit un `<data_root>/<site_id>/runs/<run_id>.json`
  (`adapters/manifests.py:162`) — les compter donne l'avancement d'un run déjà lancé.

---

## Résumé de réalisation

*(à remplir avant de déplacer la fiche dans `fait/`)*

- **Ce qui a été fait** : …
- **Verdict de l'oracle** : [chiffres obtenus, y compris défavorables]
- **Commit(s)** : …
- **Date** : AAAA-MM-JJ
