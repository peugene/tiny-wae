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
> ⚠ **Placement à confirmer par le PO** : id hors de la séquence `l0-*` du chantier
> `lot-0-ingestion` (déclarée fermée à `l0-06`), sur le précédent d'`out-01` et de `l0-07`.
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
- ⚠ **`__main__.py` porte une interdiction explicite** : « ⭐ Ce fichier n'est PLUS JAMAIS
  modifié après l0-01.2 ». Elle vise l'ajout de **sous-commandes** (qui passent par
  `cli/discovery.py`), mais sa lettre couvre toute modification — arbitrage ci-dessous.

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
- **D8 — ⚠ à confirmer par le PO : `__main__.py` est modifié** pour porter l'option globale
  `--log-level` sur son `@app.callback()`, et son inscription est **amendée** en « aucune
  sous-commande ne s'ajoute ici » (l'intention réelle de la règle). Si le PO refuse, le repli
  est `TINY_WAE_LOG_LEVEL` seule, sans option de ligne de commande — le reste de la fiche est
  inchangé.
- **D9 — Le pourcentage est en FENÊTRES, pas en temps, et il est annoncé comme indicatif.**
  Une fenêtre sans item coûte une requête STAC ; une fenêtre à 6 items coûte 6
  téléchargements de chips. Le `%` ne prétend donc pas mesurer le temps restant.
- **D10 — Les deux tests `sites-list` passent de `result.output` à `result.stdout`.** Coût
  nul, et cela fixe leur intention réelle (ils testent une sortie de données) au lieu de les
  laisser exposés au premier log émis en amont.

### Fichiers touchés

- `src/tiny_wae/cli/logging_setup.py` — **nouveau** : `configure_logging(level: str) -> None`,
  seul endroit qui installe un handler (STDERR) et un format.
- `src/tiny_wae/__main__.py` — option globale `--log-level`, appel de `configure_logging`,
  inscription amendée (cf. D8).
- `src/tiny_wae/adapters/backfill.py` — logger de module ; ligne d'ouverture (nombre de
  sites, de fenêtres, total, workers) et une ligne par fenêtre terminée dans `_process_site`.
  Le total est déjà calculable sur place : `sum(len(w) for w in windows_by_site.values())`.
- `tests/test_logging.py` — **nouveau** : les oracles ci-dessous.
- `tests/test_cli_commands.py` — D10 (2 lignes).

### Format de ligne (figé)

```
2026-08-22 16:04:12 INFO  backfill    47/1200 ( 3.9%)  A01  2022-09-01→2022-10-01  ingested=2 skipped=4
2026-08-22 16:04:19 WARNING backfill   48/1200 ( 4.0%)  B03  2022-09-01→2022-10-01  ÉCHEC : <message>
```

Seuls les compteurs **non nuls** sont rendus, triés par clé — une ligne à 12 compteurs à zéro
est illisible et masque l'information utile.

## Définition de « terminé »

- [ ] `cli/logging_setup.py` existe et est le **seul** module qui installe un handler.
- [ ] Le niveau suit la précédence D4 ; un niveau invalide sort en `exit_codes.USAGE`, pas en
      trace Python.
- [ ] `adapters/backfill.py` émet une ligne d'ouverture puis une ligne par fenêtre terminée.
- [ ] Chaque ligne de progression porte : `n/total`, un pourcentage, l'id du site, les bornes
      de la fenêtre, et soit les compteurs non nuls, soit le message d'échec.
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
| O8 | **mutation** : retirer l'appel de log dans `_process_site`, relancer `just test -k logging` | O1 et O2 passent au **ROUGE**, puis au vert après restauration |
| O9 | `grep -rn "logging" src/tiny_wae/core/` | **0** résultat |
| O10 | non-régression | `just check` vert — **250 tests** au départ ; les 29 assertions `.stderr` et les 5 de `test_cli_backfill.py` **inchangées** ; seules les 2 lignes de D10 sont modifiées |

**Non testé par cette fiche** (chiffres honnêtes) :

- **Aucun run réel.** Le gate est hors réseau : la tenue du log sur les ~1200 lignes d'un
  backfill de 48 mois sur le NAS n'est **pas** mesurée ici. C'est à la campagne `l0-04.H` de
  le constater.
- **Le `%` n'est pas validé comme prédicteur de temps** — il ne prétend pas l'être (D9).
  Aucun ETA n'est produit (cf. Notes).
- **Les autres CLIs ne sont pas instrumentés.** `ingest`, `update`, `report`, `search`
  gardent leur unique rapport final : le **socle** est transverse, l'**instrumentation** ne
  l'est pas.
- **Rien sur le comportement sous cwltool** (capture de STDERR par le moteur) : à vérifier
  lors d'un passage PID-FLOW, hors périmètre.
- **Aucune sortie structurée** (JSON par ligne) : format texte uniquement.
- **Le niveau DEBUG n'a aucun contenu** : aucun module n'émet en DEBUG à l'issue de cette
  fiche.

## Notes / pistes

- **ETA délibérément hors périmètre.** Un temps restant extrapolé linéairement est faux tant
  que les 25 sites n'ont pas tous démarré, et devient trompeur dès qu'un site est plus lourd
  que les autres. À instruire séparément si le `%` ne suffit pas à l'usage.
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
