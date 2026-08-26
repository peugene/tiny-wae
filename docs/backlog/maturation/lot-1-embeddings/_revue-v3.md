# Revue v3 — Lot 1 (Banc d'embeddings GFM sur CPU)

> **Troisième passe adversariale** sur les 31 fiches du chantier, après la v1 (116 findings,
> 24 clusters) et la v2 externe (5/5 confirmés). Première revue à **6 angles** : le nouvel
> angle ⭐ **« fiches × infrastructure du dépôt »** (ancrage code), ajouté après que la v2 a
> trouvé un bloquant invisible des 5 angles classiques.
> **Date** : 25/08/2026 · **Protocole** : 6 angles Opus en aveugle → déduplication →
> réfuteur indépendant avec obligation de preuve.

**Bilan brut** : 117 findings (Découpage 20 · Séquençage 15 · Ancrage 14 · Faits 12 ·
Décisions 26 · Oracles 30), dédupliqués en **32 clusters** V-01→V-32.
**Verdict du réfuteur** : 20 CONFIRMÉS · 11 CONFIRMÉS avec correction à amender ·
1 NON-PROUVÉ (V-21) · 0 cluster réfuté en bloc · 2 sous-items réfutés. Le réfuteur a relu
les 31 fiches sur disque, recalculé le graphe depuis les frontmatters, re-simulé chaque
correction structurante, et lu le code source amont (`Clay-foundation/model`) — plus
3 findings additionnels de son cru (A-1, A-2, A-3).

---

## 1. Verdict global

Le chantier est **structurellement sain** — profondeur 8 et largeur ~3,25 préservées par
toutes les corrections, aucun cycle, aucune fiche à créer ni à fusionner — mais il n'est
**pas dispatchable en l'état**. Trois familles de défauts l'empêchent :

1. **Le gate rougirait avant la fin du premier niveau réel.** `l1-07` (gate avec poids) est
   branchée sur `l1-03.4` alors que `just test` charge des poids dès `l1-02.1` (V-01, trouvé
   par 3 angles avec 3 preuves indépendantes) ; `test_packaging.py` ne lit pas les extras
   PEP 621 (V-12) ; hatchling refuse la référence git de claymodel sans
   `allow-direct-references` (V-03) ; le volet worktrees repose sur un `.env` que rien ne
   lit (V-02).
2. **Des oracles faux ou non discriminants ont survécu aux deux premières passes.** O6 de
   `l1-02.1` est démontré faux au code source Clay (V-17) ; l'invariant 5 termes de
   `l1-05.3a` reste vert après mutation (V-19) ; le facteur 4-tuiles vaut 4,0 par
   construction (V-22) ; l'interblocage `l1-05.2` → `l1-06.H` rendrait l'arbitre
   inatteignable (V-18).
3. **Le motif systémique des passes de correction** : le correctif se pose au symptôme cité,
   pas au premier consommateur réel (V-01) ; il corrige les tables d'oracle, pas les
   paragraphes qui les précèdent (V-05, V-14). Les deux mécanismes sont désormais des points
   de contrôle explicites de la passe v3.

À noter, la mise en garde du réfuteur : 31 clusters sur 32 confirmés au moins sur le fait,
et ses 3 findings additionnels trouvés *en re-vérifiant* — le corpus n'était pas encore à
maturité de dispatch au moment de la revue. C'est le résultat attendu d'une troisième passe,
pas une anomalie.

## 2. Ce que chaque angle a vu que les autres ne pouvaient pas voir

| Angle | Apport propre |
|---|---|
| Découpage (D) | `l1-07` branchée trop tard (D-1) · gate humain dans une DoD d'agent (D-3) · protocole de stabilité « partagé » défini chez une sœur sans arête (D-6) |
| Séquençage (S) | même V-01 par la voie du dispatch glouton · `.env` gitignoré (S-2) · `l1-00`/`l1-03.2` non ordonnés (S-5) · amont référençant l'aval (S-9) |
| ⭐ Ancrage (A) | `test_packaging.py:49` ne lit que `[project.dependencies]` (A-1) · `.env` lu par rien + doctrine D4 de `chips.py:43` (A-3) · `tests/test_smoke.py:110-117` rejoue `smoke.main()` dans pytest (A-4) · `config_io._INT_FIELDS` ignoré (A-5) · `chip_bounds` existant non réutilisé (A-12) |
| Faits (F) | hatchling vs direct references (F-1) · `HF_HUB_OFFLINE` lu à l'import (F-2) · caches Actions cloisonnés par branche (F-7) · symlinks HF sur drvfs (F-8) · etag même sur cache chaud (F-9) |
| Décisions (C) | résidus corps-vs-oracle « distance cosinus » (C-2, C-3) · `--cloud-max` sans oracle (C-6) · sélection `(model_id, spec_hash)` non déclarée par les lecteurs (C-5) |
| Oracles (E) | O6 datetime faux (E-1) · interblocage `l1-05.2` (E-2) · invariant non rougissable (E-3) · tautologie 4,0 (E-12) · contamination des bancs parallèles (E-8) |

## 3. Issues consolidées — verdicts de réfutation

Le détail complet (preuves fichier:ligne, permaliens amont) vit dans le rapport de
réfutation. Ici : le verdict et la correction **retenue** (celle du réfuteur quand elle
amende celle de la revue).

### Bloquants

| # | Clusters | Problème | Correction retenue |
|---|---|---|---|
| V-01 | D-1, S-1, A-2, E-13 | `l1-07` branchée sur `l1-03.4` alors que `just test` charge des poids dès `l1-02.1` | `l1-07` dans `depends_on` de `l1-02.1` **et** `l1-02.2` (coût profondeur : zéro, re-simulé) ; l'arête `l1-03.4 → l1-07` devient redondante — retirée ; `l1-07.md` reformulé « dès la livraison de `l1-02.1` » ; fixture pytest scope session + durée publiée (E-13) |
| V-02 | S-2, A-3, F-8 | Volet worktrees de `l1-07` fondé sur `.env`, gitignoré et **lu par rien** | ⭐ **Arbitré par le réfuteur : cache sous `~/.cache/tiny-wae/models` (ext4)**, défaut absolu dans `settings.yaml` versionné, expansé `expanduser().resolve()` (règle F-3 au passage) ; `TINY_WAE_HF_HOME` en surcharge ; `.env.example` documente, ne configure pas ; `HF_HUB_DISABLE_SYMLINKS` rétrogradé en note conditionnelle. Argument décisif : les poids sont relus à chaque démarrage de processus — sur `/mnt/d`, la taxe drvfs contaminerait `setup_s` de `l1-04.1`, `l1-05.2`, `l1-04.3b`, celle que `l1-04.2` existe pour isoler |
| V-03 | F-1 | hatchling refuse `claymodel @ git+…` par défaut → `just install` rouge | ⚠ Correction de la revue **amendée** : la voie pixi-native casserait deptry (qui lit le PEP 621, et est dans le gate). Retenu : **`[tool.hatch.metadata] allow-direct-references = true` + l'extra**. À reconfirmer par un `just install` d'essai |
| V-04 | F-2, A-10, A-9 | `HF_HOME`/`HF_HUB_OFFLINE` lus **à l'import** de huggingface_hub — pose tardive = no-op | Ordre de priorité réécrit : (1) `cache_dir=` + `local_files_only=True` explicites sur nos appels ; (2) env posé **avant l'interpréteur** (activation pixi + CI) — seul levier sur les appels internes de timm/terratorch ; (3) assertion runtime en filet. Oracle A-9 : `import tiny_wae.__main__` en **sous-processus frais** |
| V-06 | D-3, E-21 | Gate humain (« zone `.github/` actée par Philippe ») dans la DoD d'une fiche d'agent | Acter la zone **avant dispatch**, retirer la case — **décision Philippe requise** (voir §5) |
| V-07 | D-4, E-4, F-7, F-5, F-6 | O1/O2 de `l1-07` inexécutables par l'agent et verts par construction | Critères statiques locaux + consommateur provisoire `scripts/check_cache.py` **versionné** (tranche aussi la contradiction C-24, cf. V-29) + population du cache depuis la branche par défaut + clé dérivée des **révisions HF épinglées**, jamais de `pixi.lock` |
| V-08 | D-5, C-4 | C08 sans filtre contamine séparabilité et invariants | Filtre `cloud_pct ≤ seuil` par défaut dans les rapports ; seul `l1-05.4`/O3 le lève ; écrit dans `l1-05.3a`/`l1-05.4`, pas dans la checklist humaine |
| V-09 | D-6, S-3, E-26, D-10 | Protocole de stabilité « partagé » sans arête, faux sur son périmètre | Le protocole (fonction `stability` + barème CV) **remonte chez `l1-04.1`**, ancêtre commun vérifié des quatre fiches de banc ; échantillon d'`item_id` gelé une fois par `l1-04.1` |
| V-10 | S-5, A-5 | `l1-00`/`l1-03.2` non ordonnés ; `_INT_FIELDS`/`validate()` ignorés (surcharge env → `TypeError`) | Arête `l1-00 → l1-03.2` (coût zéro) ; `l1-00` pré-pose les 3 clés ; les fiches citent `config_io._INT_FIELDS` **et** les bornes dans `Settings.validate()` |
| V-11 | S-4, E-7 | Marge/durées sans source machine-lisible pour `l1-04.5` | Double sortie `similarity-report.{md,json}` + `campaign.json` produit par la checklist humaine |
| V-18 | E-2, C-22, E-16 | Interblocage : `l1-05.2` « non terminable si échec » alors que `l1-06.H` en dépend | Terminée en **rouge déclaré** (`determinism_violated` dans le JSON), passe en `fait/` ; point 6 de `l1-06.H` bloquant pour la recette. ⚠ E-16 amendé : le 0,999 est le plancher de **quantification** — le réutiliser pour les threads serait un seuil non acté (voir §5) |

### Majeurs

| # | Clusters | Problème | Correction retenue |
|---|---|---|---|
| V-05 | 5 angles | Résidu « 1024 contre 768 » dans le corps de `l1-02.4` | `768` → `384` + renvoi à la table du chapeau |
| V-12 | A-1, F-4, C-7, F-10, C-8 | `test_packaging.py` ne lit que `[project.dependencies]` ; feature `models` absente de l'env default ; `huggingface_hub` déclaré nulle part | `l1-00` étend `test_packaging` aux extras (décision écrite) ; `default = {features=["dev","models"]}` ; `huggingface_hub` ajouté |
| V-13 | A-8, C-10, D-13, C-11 | `docs/lots/lot-1/`, README, `CLAUDE.md`, `config/` hors zones | **Décision Philippe requise** — point unique, voir §5 |
| V-14 | C-2, C-3 | « distance cosinus » résiduel dans les corps (`l1-04.4`, `l1-05.2`) | Une ligne chacune, alignées sur la convention du chapeau `l1-05` |
| V-15 | C-5, C-17, D-15 | Sélection `(model_id, spec_hash)` non déclarée par les lecteurs ; pas de `list_vectors` | `list_vectors(dir)` chez `l1-03.1` ; sélection explicite + oracle « deux specs → n'agrège qu'une, nommée » ; `write_vector(dir, vector, meta)` dérive le nom |
| V-16 | C-6, E-15 | `--cloud-max` sans oracle ; précédence non testée ; `.error.json` sans sémantique de reprise | Oracle sur l'option + précédence à 3 niveaux ; un `.error.json` **se rejoue**, jamais un marqueur de skip |
| V-17 | E-1 | O6 de `l1-02.1` **faux** — l'encodage temporel Clay = sin/cos semaine+heure, **pas l'année** (vérifié au code : `datamodule.py`, `np.hstack((week_norm, hour_norm))`) | ⚠ Amendé en **deux témoins** : O6a « +1 an jour pour jour → identiques » (consigné pour le Lot 2) + **O6b « ~6 mois → différents »** — seul témoin qui prouve que la date entre. Conséquence Lot 2 **inversée** : c'est la phase saisonnière qui entre, pas la date — le confondant que `l1-05.4` isole (à noter dans les deux fiches) |
| V-19 | E-3 | Invariant 5 termes vert après mutation (les deux membres lus du disque) | Recalcul depuis disque **+ manifestes**, `unexplained_missing` jamais dérivé du comptage de fichiers ; témoin positif ajouté |
| V-20 | E-8 | 5 fiches de mesure CPU en N4 : contamination si dispatch parallèle — aggravé par `run.md:27-28` (« fichiers disjoints » les déclare sûres) | ⚠ Amendé (proportionnalité) : **pas** de champ `exclusive_run` (toucherait `backlog.py`, hors zones). Retenu : règle ⛔ dans `_roadmap.md` §4 + bandeau dans les 5 fiches + champ `concurrent_load` dans chaque JSON de banc |
| V-21 | E-9 | « threads non propagés aux workers » | **NON-PROUVÉ** : le patron Lot 0 repris par `l1-03.3` est un `ThreadPoolExecutor` (`backfill.py:56,441`) — `set_num_threads` est process-global, il s'applique. Résidu retenu : `l1-03.3` **fixe** le type de pool ; `l1-04.3b`/O1 relève les threads effectifs **depuis un worker** |
| V-22 | E-12, D-18, S-6 | Facteur 4-tuiles = 4,0 par construction ; « batch retenu » sans surface (`--batch` n'existe nulle part) | Coût **absolu** extrapolé (heures sur 4 959 chips) + écart séquentiel/batch ; retrait de l'arête `l1-05.3.H → l1-04.3a` |
| V-23 | A-4 | `tests/test_smoke.py:110-117` rejoue `smoke.main()` dans pytest → étape modèle payée 2× | `tests/test_smoke.py` nommé au périmètre de `l1-03.4` ; étape modèle en fonction séparée ou test restreint aux étapes Lot 0 |
| V-24 | E-18 | Efforts sous-estimés | `l1-00` → **M** · `l1-04.3b` → **M** |
| V-25 | D-7 | Second témoin de `l1-05.4` resté champ libre humain | Second site nommé **au chapeau `l1-05` maintenant** ; la checklist confirme ou remplace avec motif écrit |

### Mineurs (V-26 → V-32, consolidés)

Tous confirmés, corrections retenues avec quatre amendements du réfuteur :

- **V-26** fiche de lot : « 25 » → **24** fiches agent · « TerraMind » → « TerraMind small » ·
  livrables complétés (trajectory-report, modules) · tableau des phases avec `l1-00`/`l1-07`.
- **V-27** roadmap : « 24 s'enchaînent » → 22 · largeur 26/8 = **3,25** · §2bis-a complété
  (« et dans le nom du fichier ») · ⚠ sous-item **réfuté** : « 3 chaînes disjointes de
  longueur 8 » est faux (il y en a **48**) → on cesse de nommer « le » chemin critique ;
  les goulots réels sont `l1-05.3.H` (N5), `l1-04.5`/`l1-05.4` (N6), `l1-06.H`.
- **V-28** `l1-00` : O2 identité par sha256/tailles + `check_cache.py` conservé · O3 scindé
  (la clause d'échappement le rendait infalsifiable) · O4 qualifié + conséquence dispatch ·
  verdict 256 partagé explicitement avec `l1-02.2`/O5 · `hf_home` absolu · révisions HF
  épinglées · « ne télécharge rien » ≠ « zéro requête » (etag) — un run `HF_HUB_OFFLINE=1`.
  `TIMM_USE_OLD_CACHE` et ventilation hub/xet : rétrogradés en notes d'implémentation.
- **V-29** `l1-02.x` : assertion 1025 **dans l'adapter** + témoin monkeypatch (la valeur
  1025 elle-même est confirmée à la source) · `np.asarray` à la frontière des libs non
  typées · feature `bench` (onnxruntime) pré-posée par `l1-00` · grep de `l1-02.3` scopé
  à `src/`, `fetch_models.py` et `check_cache.py` nommés comme exceptions — tranche la
  contradiction interne C-24 vs E-11/E-4.
- **V-30** `l1-03.x` : 3ᵉ passage `--force` (le « bit près » après « 0 recalcul » était
  tautologique) · N de fixtures publié · taxonomie de `__main__.py` mise à jour par
  `l1-03.2` · ⚠ O4 de `l1-03.4` : **jamais un `rm` du cache partagé** — `HF_HOME` pointé
  sur un tmpdir vide · `chip_bounds` existant réutilisé · « 10 champs » → 11 ·
  `l1-01.4`/O3 en littéral 10 % · oracles du double chez son propriétaire, `l1-04.1`
  listé consommateur.
- **V-31** `l1-05.x` : distance 1−cos figée + valeur littérale · seuil 0,2+baseline entre
  dans les tables d'oracle (qualification à 3 états) · baseline : `--no-baseline` +
  coût de la passe corpus budgété · `--out` + 2 noms (sample vs complet) · paliers pour
  O4 + `min_detectable` publié · ⚠ seuils : **renvoi** à `_roadmap.md` §2ter, pas de
  recopie (seule la corrélation nuage 0,5 manque réellement à `l1-05`) · sous-item C-16
  **réfuté** (`l1-03.md` cite 2 champs comme motif, pas comme définition).
- **V-32** graphe : ⚠ S-11 **sans arête** `l1-03.4 → l1-06.H` (elle rendrait permanente une
  contrainte conditionnelle) → point 8 dans `l1-06.H` + drapeau au Résumé de `l1-03.4` ·
  ⚠ S-12 : la bonne dépendance de `l1-05.3a` est **`l1-03.1`** (le format), pas `l1-03.3` —
  `l1-05.3a` passe de N4 à N1, **N4 tombe de 7 à 6** (désengorge V-20) · arête
  `l1-04.2 → l1-02.4` (coût zéro) · `scl_summary` défini inline chez `l1-03.1`, `l1-01.2`
  s'y conforme · borne DN élargie + distribution publiée · `reason` nomme un objet
  mesurable · smoke : TerraMind au périmètre, cascade 30 s dans l'oracle · fixtures
  `vectors/` : propriétaire `l1-05.3a`.

## 4. Findings additionnels du réfuteur

- **A-1 (majeur)** — collision entre deux corrections de la revue : `l1-03.1` (N0) impose
  `torch_version` dans `VectorMeta`, mais un `import torch` au niveau module rendrait rouge
  l'oracle d'import paresseux (A-9). → `importlib.metadata.version("torch")`, repli `None`.
- **A-2 (majeur)** — piège dormant : `test_packaging.py:101-118` exige que tout
  `[tool.pixi.dependencies]` figure au contrat de la wheel. → torch/claymodel/terratorch
  vont dans `[tool.pixi.feature.models.*]`, **jamais** dans la table de base — à écrire
  dans `l1-00`.
- **A-3 (mineur)** — `l1-02.1` : le tutoriel Clay pose **quatre** kwargs, pas deux
  (`dolls`, `doll_weights` en plus), et les kwargs priment sur les hparams restaurés.
  Phrase corrigée, vérification à l'implémentation.
- **A-4 — re-vérifications positives** (à ne pas rouvrir) : le 1025 de `l1-02.1`/O4,
  l'extraction du CLS, les `waves` en µm — exacts à la source.

## 5. Décisions de Philippe — prises le 25/08/2026

### 1. Zones d'écriture (V-06 + V-13)

| Zone | Décision | Conséquence dans les fiches |
|---|---|---|
| `.github/workflows/` | **ouverte équipe** | `l1-07` la modifie ; la case à cocher « zone actée par Philippe » est **retirée** de sa DoD (un gate humain n'a rien à faire dans une DoD d'agent) |
| `config/` · `.env.example` | **ouvertes équipe** | `l1-00` pré-pose les 3 clés de `settings.yaml` ; `l1-07` documente `TINY_WAE_HF_HOME` dans `.env.example` |
| `docs/lots/lot-1/` | **ouverte en création** | `l1-05.3a` crée le répertoire ; `l1-04.5` et `l1-05.4` y déposent. Le reste de `docs/lots/` (les fiches de lot) demeure **zone PO** |
| `README.md` · `CLAUDE.md` | ⛔ **fermées** | `l1-02.3` et `l1-07` **rédigent leur ligne au Résumé** ; Philippe la reporte. Aucune fiche ne les édite |

⚠ **Le report dans `CLAUDE.md` reste à faire, et il n'est ni de ma zone ni de celle de
l'équipe.** Le texte à insérer dans la section « Multi-instances : zones d'écriture »,
prêt à coller :

> L'équipe d'implémentation écrit aussi dans **`.github/`** (workflows et configuration
> CI — précédent de fait : `codeql.yml` et `dependabot.yml`), **`config/`** et
> **`.env.example`**, et peut **créer des fichiers** sous `docs/lots/<lot>/` (rapports
> décisionnels produits par les fiches). Les **fiches de lot** elles-mêmes
> (`docs/lots/*.md`) restent zone PO. **`README.md` et `CLAUDE.md` ne se modifient pas
> depuis une fiche** : la fiche rédige la ligne à ajouter dans son Résumé, Philippe la
> reporte.

### 2. Seuil de déterminisme entre threads (V-18/E-16)

**Pas de nouveau seuil.** `l1-05.2`/O3 publie un état parmi trois — `identical`,
`negligible` (min ≥ 0,9999), `significant` — **sans seuil de passage** : c'est une mesure
décisionnelle pour `l1-06.H`, pas un gate. Le 0,999 reste ce qu'il est : le plancher de
**fidélité de quantification** de `l1-04.4`, et rien d'autre.

### 3. Restructuration S-12 *(information — décision PO)*

`l1-05.3a` redescend de N4 à **N1** : elle ne consomme que le **format** des vecteurs
(`l1-03.1`), et se teste sur fixtures fabriquées. N4 passe de 7 à **6** fiches, dont
exactement les 5 fiches de banc CPU plus `l1-03.4`.

## 6. État après la passe de correction (25/08/2026)

**Faite.** Les 32 clusters et les 3 findings additionnels sont traités, avec les corrections
**retenues par le réfuteur** partout où elles divergeaient de celles de la revue. Deux
points de contrôle systématiques ont été appliqués, hérités des motifs identifiés :
chaque correctif est posé chez le **premier consommateur réel** (pas chez le symptôme
cité), et les **corps de fiche** ont été relus après les tables d'oracle.

**Graphe recalculé depuis les frontmatters** — 26 fiches dispatchables, **profondeur 8**,
**largeur 26/8 = 3,25**, aucun cycle, aucune arête vers une fiche inconnue :

```
N0  l1-00 · l1-01.1 · l1-01.4 · l1-03.1 · l1-05.1
N1  l1-01.2 · l1-01.3 · l1-05.3a · l1-07
N2  l1-02.1 · l1-02.2 · l1-03.2
N3  l1-02.3 · l1-02.4 · l1-03.3 · l1-04.1
N4  l1-03.4 · l1-04.2 · l1-04.3a · l1-04.3b · l1-04.4 · l1-05.2
N5  ⛔ l1-05.3.H
N6  l1-04.5 · l1-05.4
N7  ⛔ l1-06.H
```

Efforts après recalibrage : 13 M · 11 S · 2 H (`l1-00` et `l1-04.3b` passent de S à M).

**Ce qui reste ouvert** :

- le report du paragraphe de zones dans `CLAUDE.md` (§5.1) — geste de Philippe ;
- les **revues externes par équipe dev** annoncées, avant descente en `a-faire/` ;
- rien n'est commité : les fiches restent en **maturation**.
