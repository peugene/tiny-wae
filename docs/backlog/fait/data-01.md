---
id: data-01
titre: "Un asset inaccessible ne fait plus perdre la fenêtre entière"
effort: S
categorie: robustesse
phase:
depends_on: [l0-02.1]
parent:
subtasks: []
---

# [data-01] — Un asset inaccessible ne fait plus perdre la fenêtre entière

> Fiche de backlog : sert de **brief (prompt)** pour l'IA.
> Avancement = dossier : `maturation/` → `a-faire/` → `en-cours/` → `fait/`.

## Objectif

Sur la campagne d'historique du 2026-08-23, **5 items** du catalogue exposaient leurs assets
sur `s3://sentinel-s2-l2a` (les JP2 d'origine, bucket *requester-pays*) au lieu du bucket
public de COG. La garde du chapeau `l0-02` les refuse — **et elle a raison** : ce bucket est
inaccessible sans identifiants et facturé au demandeur.

Le défaut n'est pas le refus, c'est sa **portée**. La garde lève pendant le parsing de la
recherche, donc l'item fautif emporte **toute la fenêtre**, puis le site, puis le code de
sortie du run. Cinq items sur 14 967 ont suffi à faire sortir une campagne de 6 heures en
`FAILURE`.

## Contexte et périmètre

### ⚠ Ancrage dans le code réel (vérifié le 2026-08-23, HEAD `690e899`)

- **La garde** est dans `adapters/stac.py::parse_item` (l. 102-125) : pour chaque clé
  d'asset **mappée**, un href commençant par `s3://` lève `StacSourceError`. Les assets non
  mappés (`cloud`, `snow` des items S2C, eux aussi en `s3://`) ne sont jamais lus, donc
  jamais soumis à la garde — comportement voulu, à conserver.
- **La portée du dégât** vient de l'appelant : `parse_item` est appelé l. 169, **dans la
  boucle qui construit l'enveloppe**. L'exception n'est pas rattrapée : elle remonte à
  `search()`, puis à `ingest_from_source`, et `adapters/backfill.py::_process_site` compte
  la fenêtre entière en `TaskFailure`. Tous les autres items de la fenêtre sont perdus avec.
- **Mesure exacte de l'impact** (campagne du 2026-08-23) : **5 fenêtres** sur 1200 (0,4 %),
  **5 items** sur 14 967 (0,03 %), **5 sites** marqués en échec (A01, A03, B01, B07, C03),
  **exit 1** sur l'ensemble du run. Les items fautifs sont
  `S2A_31UCT_20240123`, `S2B_31TGJ_20241204`, `S2A_36RYS_20240901`, `S2A_19KEQ_20240123`,
  `S2B_31TFJ_20241204` — les dates se répètent d'un site à l'autre, ce qui confirme un
  défaut de **catalogue**, pas de site.
- ⭐ **La portée est plus large que le backfill — constaté le 2026-08-23 en exécution.**
  `report --check-completeness` échoue sur le MÊME défaut, avec le même item
  (`S2B_31TGJ_20241204_0_L2A`), et sort en exit 1. Or ce contrôle est **un critère de recette
  du Lot 0** (checklist de `l0-04.H`) : tant que ce défaut est là, la recette est
  inexécutable. Le chemin d'appel est identique — `cli/report.py:95` -> `search()` ->
  `build_envelope` (l. 232) -> `parse_item` (l. 169) — donc le correctif de cette fiche le
  couvre **sans travail supplémentaire**. À vérifier après merge en rejouant la commande
  réelle, pas seulement les tests.
- ⚠ **Une identité comptable protège l'enveloppe** (`core/envelope.py`, l. 59-78) :
  `found_stac == skipped_scene_cloud + off_tile + found_tile`, **et**
  `found_tile == len(items)`. Toute violation lève `ConservationError`. Un item écarté sans
  être compté casserait donc l'invariant — c'est le vrai point technique de la fiche.
- **`ENVELOPE_COUNTERS`** (`core/envelope.py`, l. 29-34) est l'énumération normative des 4
  compteurs d'enveloppe. `adapters/manifests.py:48` en dérive
  `_COUNTER_KEYS = (*ENVELOPE_COUNTERS, *RUN_STATUSES)`.
- ⛔ **PIÈGE CONFIRMÉ — la validation s'applique aussi à la LECTURE.**
  `manifests.py::_validate_counters` (l. 247) exige la présence de **toutes** les clés de
  `_COUNTER_KEYS` et lève `ConservationError` sinon. Elle est appelée par `write_run`
  (l. 280) **mais AUSSI par `aggregate_counters` (l. 314), qui itère sur les runs relus**.
  Ajouter naïvement `skipped_asset_scheme` à `ENVELOPE_COUNTERS` rendrait donc les
  **1404 `run.json` déjà écrits** (16 Go de campagne) illisibles par `aggregate_counters`,
  et casserait `report`. Vérifié par lecture le 2026-08-23, ce n'est pas une hypothèse.
- ⚠ **L'identité comptable est DUPLIQUÉE** : elle est écrite dans `core/envelope.py`
  (l. 63-72) **et** dans `manifests.py::_validate_counters` (l. 256). Les deux devront être
  modifiées de façon cohérente — c'est exactement le défaut que la méthode nomme
  (« une énumération normative n'existe qu'à UN endroit »), déjà présent dans le code.

### ⭐ Décisions actées

- **D1 — L'item fautif est ÉCARTÉ et COMPTÉ, la fenêtre continue.** `parse_item` garde son
  comportement (elle lève : c'est un parseur, il signale), et c'est **l'appelant**, dans la
  boucle de construction de l'enveloppe, qui rattrape, compte et passe au suivant.
- **D2 — Un nouveau compteur d'enveloppe : `skipped_asset_scheme`**, ajouté à
  `ENVELOPE_COUNTERS`. Ce n'est pas un statut de manifeste : aucun manifeste n'est écrit
  pour un item qu'on n'a jamais pu lire. ⛔ Ne pas toucher à `RUN_STATUSES`.
- **D3 — L'identité comptable est ÉTENDUE, pas contournée** :
  `found_stac == skipped_scene_cloud + off_tile + found_tile + skipped_asset_scheme`.
  Elle est modifiée **au point de définition** (`core/envelope.py`), jamais dupliquée.
- **D4 — La garde n'est pas assouplie.** On ne tente **pas** de traduire `s3://` en `https://` :
  `sentinel-s2-l2a` est un bucket *requester-pays* et les objets y sont des JP2, pas des COG.
  Une traduction produirait des accès facturés, ou des échecs plus tardifs et plus obscurs.
- **D6 — ⭐ Rétrocompatibilité à la LECTURE, obligatoire.** Un compteur neuf est toléré
  **absent** d'un journal existant et vaut alors `0` ; l'invariant de conservation ne
  s'applique STRICTEMENT qu'à l'**écriture**. Même principe que la décision de `l0-07` sur
  `read_manifest` : on ne refuse pas de relire des données qu'on a soi-même produites.
  ⛔ Aucune migration des 1404 journaux : c'est le code qui s'adapte, pas le corpus.
- **D5 — L'écart reste visible.** Un item écarté est loggué en **WARNING** (le logging
  d'`obs-01` est en place), avec l'id de l'item et la clé d'asset fautive. Un rejet
  silencieux serait pire que l'échec actuel : on croirait la campagne complète.

### Fichiers touchés

- `src/tiny_wae/core/envelope.py` — `ENVELOPE_COUNTERS` + identité comptable (D2, D3).
- `src/tiny_wae/adapters/stac.py` — rattrapage dans la boucle de construction (l. ~169),
  comptage, log WARNING.
- `src/tiny_wae/adapters/manifests.py` — vérifier que `_COUNTER_KEYS` suit automatiquement
  (elle dérive d'`ENVELOPE_COUNTERS`) ; ne rien y écrire en dur.
- `tests/test_envelope.py`, `tests/test_stac.py` — les oracles ci-dessous.

## Définition de « terminé »

- [ ] Une fenêtre contenant un item à asset mappé `s3://` **aboutit**, avec les autres items
      ingérés normalement.
- [ ] L'item écarté est compté dans `skipped_asset_scheme` et loggué en WARNING avec son id.
- [ ] L'identité comptable inclut le nouveau compteur et reste vérifiée.
- [ ] `RUN_STATUSES` est inchangée ; aucun manifeste n'est écrit pour un item écarté.
- [ ] Les manifestes et `run.json` existants restent relisibles (le compteur est neuf, donc
      absent des anciens journaux — cf. non-testé).
- [ ] `just check` vert au commit de la fiche.

## Oracle / recette (figé AVANT implémentation)

| # | Critère mesuré | Seuil de succès |
|---|---|---|
| O1 | enveloppe construite sur un lot d'items dont **1** porte un asset mappé `s3://` et 4 sont sains | l'appel **aboutit** ; `found_tile == 4` ; `skipped_asset_scheme == 1` ; aucune exception |
| O2 | identité comptable sur ce même cas | `found_stac == skipped_scene_cloud + off_tile + found_tile + skipped_asset_scheme`, et `found_tile == len(items)` — aucun `ConservationError` |
| O3 | un item dont seul un asset **NON mappé** (`cloud`) est en `s3://` | il est **ingéré normalement** : `skipped_asset_scheme == 0`. La garde ne s'élargit pas |
| O4 | log de l'item écarté | **1** ligne WARNING contenant l'id de l'item et la clé d'asset fautive |
| O5 | les 5 items réels de la campagne (ids de l'ancrage), rejoués depuis une fixture | **5/5** écartés, **0** exception, les fenêtres aboutissent |
| O6 | `RUN_STATUSES` et les statuts de manifeste | **inchangés** (diff vide sur `core/statuses.py`) |
| O7 | **`aggregate_counters` sur un `run.json` SANS la nouvelle clé** (le cas des 1404 existants) | **aucune exception** ; la clé absente compte pour `0`. C'est l'oracle qui garde D6, et le seul qui protège les 16 Go de campagne |
| O8 | `_validate_counters` à l'ÉCRITURE, sur des compteurs privés de la nouvelle clé | lève toujours `ConservationError` — la tolérance vaut à la lecture, pas à l'écriture |
| O9 | non-régression | `just check` vert — **276 tests** au départ ; le smoke passe ; les fixtures STAC existantes donnent les **mêmes** compteurs qu'avant (aucune ne contient d'asset mappé `s3://`) |

**Non testé par cette fiche** (chiffres honnêtes) :

- **La rétrocompatibilité est testée (O7), la campagne réelle ne l'est pas.** O7 s'exerce
  sur un journal fabriqué, pas sur les 1404 journaux du NAS. Un passage de `report` sur le
  corpus réel reste à faire par l'humain après livraison — c'est cinq secondes, et c'est la
  seule preuve qui porte sur les vraies données.
- **Les 5 fenêtres perdues ne sont pas rattrapées** : la fiche corrige le comportement, elle
  ne relance pas la campagne. Il faudra un `backfill` ciblé sur les 5 couples site/fenêtre.
- **Aucun autre schéma d'href n'est traité** (`ftp://`, `gs://`…) : seul `s3://` est
  rencontré dans les faits.
- **Aucune vérification que l'asset est réellement lisible** : un `https://` mort échouera
  toujours plus loin, à l'ouverture, comme aujourd'hui.

---

## Résumé de réalisation

- **Ce qui a été fait** : `skipped_asset_scheme` ajouté à `ENVELOPE_COUNTERS` et à
  l'identité comptable ; `AssetSchemeError(StacSourceError)` **dédiée** levée par
  `parse_item` et rattrapée **spécifiquement** par `build_envelope`, qui compte, loggue en
  WARNING et poursuit. `_with_read_tolerant_defaults` en **liste blanche** d'une seule clé,
  appliquée uniquement dans `aggregate_counters` : `write_run` reste strict (D6).

- **Verdict de l'oracle** : O1 à O9 **tous verts**. `just check` vert sur `develop` après
  merge — **293 tests** (281 après `perf-01`, +12).

- ⭐ **Vérifié sur les DONNÉES RÉELLES, pas seulement en test** (ce que l'agent ne pouvait
  pas faire, son corpus étant hors dépôt) :
  1. `report` relit les **1404 `run.json`** de la campagne, qui ne portent pas la clé neuve :
     **exit 0**, 25 sites. Le risque n°1 de la fiche est levé sur les vraies données.
  2. `report --check-completeness --sites A01,C07,A03 --from 2022-09-01 --to 2026-08-23`,
     la commande qui **échouait** avant : elle **aboutit** désormais, les 2 items `s3://`
     rencontrés sont écartés avec un WARNING nommant l'item et l'asset, et le contrôle va
     à son terme sur les 3 sites.

- ⚠ **Ce que ce contrôle réel a révélé, et qui n'était pas dans la fiche** : la complétude
  ressort **ROUGE sur A01 (7 manquants) et A03 (8 manquants)**, C07 à 0 écart. Ce ne sont
  pas des régressions : ce sont **les items des fenêtres perdues par la campagne** du
  2026-08-23, que cette fiche ne rattrape pas (dit dans son « non testé »).
  **Le cas d'A03 mesure exactement le coût du défaut corrigé** : l'item fautif
  (`S2A_31UCT_20240123`) était sur la tuile **31UCT**, alors que la tuile de référence du
  site est **31UDT**. Il aurait donc été écarté en `off_tile` sans jamais être ingéré — mais
  comme il faisait échouer le parsing **avant** le filtrage, il a emporté **8 items
  parfaitement valides**. Un item qui ne comptait pas a fait perdre huit items qui
  comptaient.

- **Écarts de périmètre, déclarés par l'agent et acceptés** :
  1. **`adapters/ingestion.py`** (mécanique, sévère) : `_run_ingestion` recopiait 4 clés à
     la main ; sans correctif, `write_run` aurait levé `ConservationError` sur **chaque**
     run. Corrigé en `**envelope_counters, **status_counts`.
  2. **`core/report.py`** (mécanique, **trouvé par l'agent**) : `check_conservation` est une
     **TROISIÈME** copie de l'identité comptable, que l'ancrage de la fiche n'avait pas
     recensée — il n'en citait que deux. Sans elle, `report` aurait rendu
     `conservation: ROUGE` à tort sur tout site ayant un item écarté, c'est-à-dire un faux
     positif sur l'instrument de recette du projet.
  3. **`cli/backfill.py`, `cli/ingest.py`, `cli/search.py`** (⚠ **opportunistes, assumés
     comme tels par l'agent**) : ajout du compteur aux lignes STDERR, dans l'esprit de D5.
     Rien ne l'imposait. Celui de `cli/ingest.py` a provoqué une cascade dans
     `tests/test_vocabulary.py` — un effet que l'agent s'est infligé lui-même, et qu'il a
     signalé plutôt que de le noyer.
  4. Six fichiers de tests touchés mécaniquement : leurs helpers construisent des
     `Envelope`/`Run` littéraux, dont `__post_init__` exige désormais 5 clés.

- **Non vérifié** : les 5 fenêtres perdues ne sont **pas** rattrapées (un backfill ciblé
  reste à lancer) ; aucun autre schéma d'href (`ftp://`, `gs://`) n'est traité.

- **Commit(s)** : `01d6cd2` (implémentation), merge `--no-ff` sur `develop`.
- **Date** : 2026-08-23
