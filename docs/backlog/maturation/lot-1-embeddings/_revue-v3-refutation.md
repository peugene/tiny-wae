# Réfutation indépendante — revue v3 du Lot 1 (32 clusters)

**Date** : 25/08/2026 · **Rôle** : réfuteur indépendant · **Base** : les 31 fiches relues sur
disque le 25/08 (état postérieur à la revue), le dépôt réel (`justfile`, `pyproject.toml`,
`.gitignore`, `.github/`, `tests/`, `src/`, `.claude/commands/run.md`), et le code source amont
de `Clay-foundation/model`.

**Méthode** : graphe de dépendances **recalculé depuis les frontmatters** (script ad hoc, 26
nœuds dispatchables) ; chaque correction proposée re-simulée sur ce graphe avant d'être
retenue ; sources amont lues au fichier, pas aux cartes HF.

---

## 1. Verdicts par cluster

| # | Verdict | Preuve (fichier:ligne / source) | Correction retenue |
|---|---|---|---|
| **V-01** | CONFIRMÉ-CORRECTION-À-AMENDER | `l1-02.1.md:65` (DoD `tests/test_embed_clay.py`), `:71-78` (O1→O8, O8 = « `just check` vert, hors ligne (cache peuplé) ») ; `depends_on` = `[l1-00, l1-01.2, l1-01.3]` (`:7`) ; `pyproject.toml` `addopts = "-q --disable-socket"` | `l1-07` dans `depends_on` de `l1-02.1` **et** `l1-02.2`. **Vérifié par recalcul : profondeur 8 et largeur 3,25 inchangées, aucun cycle.** ⚠ **Amendement** : l'arête directe `l1-03.4 → l1-07` devient alors **transitivement redondante** (via `l1-02.3 → l1-02.1 → l1-07`) — la garder ou la retirer, mais le dire. Et `l1-07.md:16-17` (« dès la livraison de `l1-03.4` ») devient « dès la livraison de `l1-02.1` » |
| **V-02** | CONFIRMÉ-CORRECTION-À-AMENDER | Fait re-prouvé : `.gitignore` ligne `.env` (section Environments) ; **aucun `set dotenv-load` dans le `justfile`** (grep exhaustif : 0 occurrence) ; `ci.yml` ne source pas `.env` ; `chips.py:43` porte la doctrine D4 (« aucune variable d'environnement… recopiée dans le justfile, un `.env` ou la doc ») ; `CLAUDE.md` § Worktrees : la copie de `.env` n'est décrite que pour le **repli manuel**, pas pour le worktree natif | **Arbitrage tranché en §2** : défaut absolu **`~/.cache/tiny-wae/models`** dans `settings.yaml` versionné, `TINY_WAE_HF_HOME` en surcharge seulement. `HF_HUB_DISABLE_SYMLINKS` **retiré du défaut**, conservé comme note conditionnelle |
| **V-03** | CONFIRMÉ-CORRECTION-À-AMENDER | `l1-00.md:40-41` déclare `claymodel @ git+https://…` comme « référence directe PEP 508 » et `:49-55` la met dans l'extra PEP 621. hatchling refuse les direct references sans `[tool.hatch.metadata] allow-direct-references = true` (⚠ vérifié **de mémoire du comportement de hatchling**, permalien non récupérable — proxy sortant bloqué sur `raw.githubusercontent.com` en shell ; à reconfirmer par un `just install` d'essai) | ⚠ **Amendement fort** : la voie proposée par F (`[tool.pixi.feature.models.pypi-dependencies]` avec `{git=…, rev=…}`) **casse `deptry`** — `deptry` lit le PEP 621, pas `[tool.pixi.*]` ; `embed_clay.py` importerait `claymodel` non déclaré → **DEP001**, et `just deptry` est dans le gate (`justfile:96-97,118`). Retenir **`allow-direct-references = true` + l'extra**, pas la voie pixi-native |
| **V-04** | CONFIRMÉ (allégé) | Multi-confirmé F-2/A-10. Fait admis : `huggingface_hub.constants` calcule `HF_HUB_OFFLINE` et `HF_HUB_CACHE` **à l'import** | ⚠ **Amendement de priorité** : l'assertion runtime **détecte** le défaut, elle ne le **prévient** pas. Ordre à écrire : (1) `cache_dir=` + `local_files_only=True` **explicites** sur nos appels (seul mécanisme robuste, indépendant de l'ordre d'import) ; (2) `HF_HOME`/`HF_HUB_OFFLINE` posés **avant l'interpréteur** (activation pixi + `ci.yml`) — c'est le seul levier sur les appels **internes** de `timm`/`terratorch`, qui ne prennent pas nos kwargs ; (3) l'assertion en filet. Sur A-9 : l'oracle doit porter sur `import tiny_wae.__main__` **dans un sous-processus frais** (sous `pytest`, `torch` peut déjà être dans `sys.modules` via un autre test — sans le sous-processus l'oracle est faussement rouge) |
| **V-05** | CONFIRMÉ | `l1-02.4.md:42` « les dimensions diffèrent (1024 contre **768**) » contre `l1-02.4.md:60` (O2) « dimensions **1024 · 384** » | Une ligne : `768` → `384`, avec renvoi à la table du chapeau `l1-02.md:27` |
| **V-06** | CONFIRMÉ | `l1-07.md:66` : case à cocher « La question de zone `.github/` **actée par Philippe** » dans la DoD d'une fiche d'agent ; `l1-07.md:51-54`. Précédent vérifié : `.github/workflows/codeql.yml` et `.github/dependabot.yml` existent dans le dépôt, et `CLAUDE.md` limite la zone équipe à `src/`, `tests/`, `scripts/` | Acter la zone **maintenant**, retirer la case. **DÉCISION PHILIPPE REQUISE** (c'est `CLAUDE.md`) |
| **V-07** | CONFIRMÉ | `l1-07.md:72-73` (O1/O2 = « CI sur une branche de test », lecture des logs Actions) ; `:74` (O3 exige un `.env` copié, cf. V-02) ; O1/O2 sont verts par construction tant que `l1-03.4` n'existe pas | Critères statiques locaux (contenu YAML) + consommateur provisoire `scripts/check_cache.py` + population du cache depuis la **branche par défaut** + clé dérivée des **révisions HF épinglées**, jamais de `pixi.lock` |
| **V-08** | CONFIRMÉ | `l1-05.3a.md:41-44` (invariant 5 termes, dont `embedded + skipped == fichiers vecteurs sur disque`) ; `l1-05.3.H.md:43-45` (« Embedder AUSSI C08 sans filtre ») ; `l1-05.4.md:68` (O3 consomme ces vecteurs). Le second membre est lu **du disque** : les vecteurs C08 hors filtre le gonflent, l'égalité rougit sur données légitimes | Filtre `cloud_pct ≤ seuil` par défaut dans les rapports ; seul `l1-05.4`/O3 le lève. À écrire dans `l1-05.3a`/`l1-05.4`, pas dans la checklist humaine |
| **V-09** | CONFIRMÉ | `l1-04.3a.md:41` « le protocole de stabilité est celui de `l1-04.3b`/O4, **partagé** » — or `l1-04.3a.depends_on = [l1-04.1, l1-02.4]` : **aucune arête**. Et le « partagé » est faux : `l1-04.2` n'a **pas** de protocole de stabilité (le sien est anti-cache, `l1-04.2.md:37-39`/O2) et `l1-04.4`/O1 (`:68`) n'a **aucun** seuil ni passe répétée | Le protocole (fonction `stability` + barème CV) remonte chez `l1-04.1` — **ancêtre commun vérifié des quatre** (`.2`, `.3a`, `.3b`, `.4` dépendent toutes de `l1-04.1`). + D-10 : échantillon de banc (liste d'`item_id`) **gelé une fois** par `l1-04.1` (aujourd'hui : 50 / 50 / 20 / 20 / 20 selon les fiches) |
| **V-10** | CONFIRMÉ-CORRECTION-À-AMENDER | `_roadmap.md:237-245` (c'est le **§5 point 6**, pas le §6 — corriger la référence du cluster) : « `settings.yaml` → `l1-00` puis `l1-03.2` puis `l1-03.3`, **séquentiels au graphe** ». Faux : `l1-03.2.depends_on = [l1-01.2, l1-01.3, l1-01.4, l1-03.1]`, **pas `l1-00`**. Substance réelle : `config_io.py:30-43` `_INT_FIELDS` et `settings.py:50` `validate()` ne sont cités par aucune fiche — `TINY_WAE_EMBED_CLOUD_PCT_MAX=20` donnerait la **chaîne** `"20"`, et `validate()` lèverait un `TypeError` sur `0 <= "20" <= 100` | Arête `l1-00 → l1-03.2` (**coût recalculé : zéro**, `l1-00` est N0 et `l1-03.2` N2) ; `l1-00` pré-pose les 3 clés ; les fiches citent explicitement `_INT_FIELDS` **et** l'ajout des bornes dans `Settings.validate()` |
| **V-11** | CONFIRMÉ | `l1-05.3a.md:27` : sortie = **`similarity-report.md`** seule ; `l1-04.5.md:24` « Il **agrège les JSON** » et `:41-45` réclame la durée réelle de la campagne + la marge de séparabilité ; `l1-05.3.H.md:50` ne produit que de la prose | Double sortie `similarity-report.{md,json}` + `campaign.json` produit par la checklist humaine |
| **V-12** | CONFIRMÉ | Re-prouvé moi-même, 4/4 : `test_packaging.py:49` ne lit que `projet["dependencies"]` ; `:63` `_SRC.rglob("*.py")` balaie **tout** `src/` → `import claymodel` dans `embed_clay.py` ⇒ test rouge ; `:89` `assert distributions` échoue **en dur** si le paquet n'est pas installé dans l'env courant ; `pyproject.toml` `[tool.pixi.environments] default = { features = ["dev"] }` ⇒ feature `models` **absente** de l'env par défaut ; `grep huggingface pyproject.toml` ⇒ **0 résultat** | `l1-00` étend `test_packaging` aux `optional-dependencies` (décision à écrire) ; `default = { features = ["dev","models"] }` ; `huggingface_hub` ajouté à l'énumération |
| **V-13** | CONFIRMÉ (allégé) | `docs/lots/` = zone PO exclusive (`CLAUDE.md`) ; `l1-05.3a.md:27`, `l1-04.5.md:28`, `l1-05.4.md:29` y écrivent tous les trois ; `l1-02.3.md:54` et `l1-07.md:64` touchent README/`CLAUDE.md` | **DÉCISION PHILIPPE REQUISE** en un point unique : `.github/`, `docs/lots/lot-1/`, `README`, `CLAUDE.md`, `config/`, `.env.example` |
| **V-14** | CONFIRMÉ | `l1-04.4.md:47` « la **fidélité** : **distance** cosinus » contre O2 `:69` « **similarité** cosinus » · `l1-05.2.md:45` « **distance** cosinus au vecteur de référence » contre O3 `:70` « **similarité** cosinus » (localisation exacte : § « Ce que le script mesure », point 2 — pas « §3 ») | Une ligne chacune, alignées sur la convention normative `l1-05.md:27-31` |
| **V-15** | CONFIRMÉ | `l1-05.3a.md:30` « sur les vecteurs présents dans `data_root` » — aucune sélection `(model_id, spec_hash)` ; `l1-03.2.md:78` (O5) **exige** la coexistence de deux specs ; `l1-03.1.md:42` `write_vector(dir, model_id, vector, meta)` alors que `meta` porte déjà `spec_hash` (`:54`) ; pas de `list_vectors` | `list_vectors(dir)` chez `l1-03.1` ; sélection explicite chez les 3 lecteurs + oracle « deux specs → n'agrège qu'une, **nommée dans le rapport** » ; `write_vector(dir, vector, meta)` dérive le nom |
| **V-16** | CONFIRMÉ | `--cloud-max` exposée en `l1-03.2.md:35` et `l1-03.3.md:35`, utilisée en `l1-05.3.H.md:43` — **aucun** des 8 oracles de `l1-03.2` ne l'exerce (O4 `:77` passe par `embed_cloud_pct_max=100`, donc settings/env). Précédence option > env > settings jamais testée. `.error.json` : `l1-03.2.md:79` l'écrit, **aucune fiche** ne dit ce qu'un run suivant en fait | Oracle sur l'**option** + précédence à 3 niveaux ; sémantique de reprise écrite : un `.error.json` **se rejoue**, il n'est jamais un marqueur de skip |
| **V-17** | CONFIRMÉ-CORRECTION-À-AMENDER | **Arbitrage détaillé en §2** — vérifié au code source Clay | O6 réécrit en deux temps (invariance annuelle **consignée** + témoin temporel réellement discriminant) |
| **V-18** | CONFIRMÉ-CORRECTION-À-AMENDER | `l1-05.2.md:60-62` (DoD : « la fiche n'est PAS terminable ») + O1 `:68` ; `l1-06.H.md:7` `depends_on` contient `l1-05.2` ⇒ une fiche jamais en `fait/` rend l'arbitre **inatteignable**. Interblocage réel | Terminée en **ROUGE DÉCLARÉ** (`determinism_violated` dans le JSON), passage en `fait/`, point 6 de `l1-06.H` devient bloquant pour la recette. ⚠ **Amendement sur E-16** : le **0,999** est le plancher de **quantification** (`_roadmap.md:98`), acté pour `l1-04.4`. Le réutiliser pour l'écart entre threads serait **un nouveau seuil non acté** introduit par la porte de service. Soit il est acté explicitement par Philippe, soit O3 se qualifie sur son propre barème à 3 états |
| **V-19** | CONFIRMÉ | `l1-05.3a.md:41-44` + O3 `:65`. Le rapport n'a **aucune source** pour `embedded` / `skipped` autre que le disque : retirer un fichier décrémente les deux membres, l'égalité tient. Témoin non discriminant, et aucun témoin positif | Invariant recalculé depuis disque **+ manifestes**, avec `unexplained_missing` **jamais dérivé** du comptage de fichiers ; ajouter un témoin positif |
| **V-20** | CONFIRMÉ-CORRECTION-À-AMENDER | Fait **re-calculé** : N4 = 7 nœuds, dont **exactement 5 fiches de mesure CPU** (`l1-04.2`, `l1-04.3a`, `l1-04.3b`, `l1-04.4`, `l1-05.2`). Aggravant non cité par la revue : `.claude/commands/run.md:27-28` retient comme critère de parallélisme « **zones de code / fichiers disjoints** » — les 5 écrivent `bench_io.py`, `bench_levers_a.py`, `bench_levers_b.py`, `bench_quant.py`, `bench_determinism.py`, **disjoints** : le critère les déclare sûres | ⚠ **Amendement (proportionnalité)** : **pas** de champ `exclusive_run` — il faudrait modifier `scripts/backlog.py`, hors des deux zones. Retenir : (a) `_tools/CLAUDE.md` pose déjà « un seul à la fois » — le **citer** ; (b) une ligne dans `_roadmap.md` §4 : « ⛔ les 5 fiches de banc CPU de N4 ne se dispatchent ni entre elles ni avec une autre charge CPU » ; (c) bandeau dans chacune des 5 ; (d) champ `concurrent_load` dans chaque JSON de banc, pour que la contamination soit **lisible a posteriori** |
| **V-21** | **NON-PROUVÉ** | Le **contre-fait** : `src/tiny_wae/adapters/backfill.py:56` et `:441` — le patron du Lot 0 que `l1-03.3.md:28` ordonne de reprendre est un **`ThreadPoolExecutor`**, donc **le même processus**. `torch.set_num_threads` est **global au processus** : il s'applique bien aux threads-workers. La prémisse d'E-9 (pool de **processus**, non-héritage) n'est **pas établie** — `l1-03.3` ne fixe nulle part le type de pool | Ne **pas** retenir « la contention mesurée serait un artefact ». Retenir le résidu, qui est réel et pas cher : (a) `l1-03.3` **fixe explicitement** le type de pool (threads, par reprise du patron Lot 0) ; (b) `l1-04.3b`/O1 **relève depuis un worker** `torch.get_num_threads()` et `OMP_NUM_THREADS` et les écrit dans le JSON — c'est cette mesure qui tranche, pas une hypothèse. Le mécanisme « env hérité » ne devient nécessaire que si un pool de **processus** est choisi |
| **V-22** | CONFIRMÉ | `l1-04.3a.md:56` : O1 = `(4 × forward 256²) / (1 × forward 256²)` — **4,0 par construction**, tautologie. Et **aucun CLI n'expose `--batch`** : vérifié sur les trois interfaces (`l1-03.2.md:35`, `l1-03.3.md:35`, `l1-04.1.md:46`) ⇒ le « Batch retenu » du Résumé (`:71`) n'a aucune surface d'application | Coût **absolu** extrapolé (heures sur 4 959 chips) + écart séquentiel/batch ; retrait de l'arête `l1-05.3.H → l1-04.3a` (**recalculé : zéro coût de profondeur**) — la campagne ne consomme que le réglage de `l1-04.3b` (`l1-05.3.H.md:30`) |
| **V-23** | CONFIRMÉ | Re-prouvé au fichier : `tests/test_smoke.py:46` charge le module au **niveau import**, `:110-117` `test_main_replay_exit_code_zero` appelle **`smoke.main()`** sous pytest. `l1-03.4.md:30,42` ajoute l'étape modèle réel à ce même `main()` ⇒ étape payée **2×** par `just check` (`just test` **puis** `just smoke`), et la règle de budget des 30 s (`l1-03.4.md:75`) n'est écrite que pour `just smoke` | Nommer `tests/test_smoke.py` **au périmètre de `l1-03.4`** (aujourd'hui la table des zones `_roadmap.md:243` ne cite que `scripts/smoke.py`) ; étape modèle exposée en fonction séparée, ou test restreint aux étapes Lot 0 |
| **V-24** | CONFIRMÉ (allégé) | `l1-00` est propriétaire exclusif de `pyproject.toml` + `pixi.lock` + `.gitignore` + `settings.yaml` + `scripts/fetch_models.py` + recette `justfile`, avec 4 oracles dont une mesure d'install — et il absorbe les inconnues V-03 et V-12. `l1-04.3b` porte une dépendance de plus que `l1-04.3a`, un protocole de contention via un vrai CLI, et **le protocole de stabilité partagé** | `l1-00` → **M** · `l1-04.3b` → **M** |
| **V-25** | CONFIRMÉ | `l1-05.4.md:67` (O2) « le second consigné par `l1-05.3.H` » ; `l1-05.3.H.md:46-48` = champ libre humain. K-16 à moitié appliqué (le premier témoin, C02, est nommé ; le second ne l'est pas) | Nommer le second site **au chapeau `l1-05` maintenant** ; la checklist confirme ou remplace **avec motif écrit** |
| **V-26** | CONFIRMÉ | 4/4, re-comptés : `lot-1-embeddings.md:128-129` « **25** fiches agent » — **le décompte réel est 24** (énumération vérifiée) · `:38` « Clay v1.5 et **TerraMind** » sans `small` · `:87-93` livrables sans `trajectory-report` ni `core/similarity.py` / `adapters/vectors.py` / `cli/similarity_report.py` / `cli/trajectory_report.py` / `cli/bench.py` / `cli/bench_report.py` · `:132-137` tableau des phases sans `l1-00` ni `l1-07` | Les 4 corrections, telles que proposées |
| **V-27** | CONFIRMÉ-CORRECTION-À-AMENDER | `_roadmap.md:210` « les **24** fiches agent s'enchaînent jusqu'à la campagne » — faux, `l1-04.5` et `l1-05.4` sont **après** (N6) ⇒ **22** · `:212-213` chemin critique **invalide** : l'arête `l1-02.4 → l1-04.1` **n'existe pas** (`l1-04.1.depends_on = ['l1-03.2']`, vérifié), et le chemin énoncé compte **9** nœuds pour une profondeur annoncée de 8 · `:209` « largeur moyenne ~3,1 » — **26/8 = 3,25** · `:52` §2bis-a omet « **et dans le nom du fichier** » (présent en `l1-01.md:32` et `l1-03.1.md:29-31`) · `l1-07` rangée dans la table O2 sans la mention « fiche à plat » dont bénéficie `l1-00` · `l1-07.md:33` « **Deux** volets » suivi de **3** items | ⚠ **Un sous-item RÉFUTÉ** : « 3 chaînes de longueur 8 **disjointes** » est faux — l'énumération exhaustive donne **48 chaînes maximales de longueur 8**. La bonne correction est de **cesser de nommer « le » chemin critique** : écrire « profondeur 8, atteinte par de nombreux chemins ; les trois **goulots** réels sont `l1-05.3.H` (N5, humain), puis `l1-04.5`/`l1-05.4` (N6), puis `l1-06.H` ». Les 5 autres sous-items : retenus tels quels |
| **V-28** | CONFIRMÉ | 7 des 9 sous-items re-prouvés : E-11 (`l1-00.md:82` — « les 3 se chargent sans aucune requête » est satisfait par un `local_files_only=True` qui rend un chemin **sans rien charger**) · D-8 (`:83` — la clause d'échappement « sinon, configuration deptry à documenter » rend O3 **infalsifiable**) · E-29/A-11 (`:84` — delta publié, **aucun** consommateur ni conséquence) · E-28 (`:65` verdict 256 affirmé, aucun oracle de `l1-00` ne le couvre ; le seul témoin mécanique est `l1-02.2`/O5) · F-3 (`:57` `hf_home` défaut `./models` — **relatif au CWD**, exactement la classe de bug déjà attrapée sur `metadata_path` en `l1-02.1.md:39-40`) · F-5 (commit `claymodel` et version `terratorch` épinglés, **pas les révisions des repos HF** — prérequis de la clé de cache de V-07) · F-9 (`:81` O1/O4 : sans `local_files_only`, `hf_hub_download` émet un **HEAD de vérification d'etag** même sur cache chaud ⇒ « ne télécharge rien » ≠ « zéro requête ») | Les 7 corrections retenues. **F-11** (`TIMM_USE_OLD_CACHE`) et la **ventilation hub/xet de F-12** : voir §4 — non vérifiables ici, à conserver comme *note d'implémentation*, pas comme exigence. Sur F-12 le fond est juste : `HF_HOME` **est** la racine, `HF_HUB_CACHE = $HF_HOME/hub` |
| **V-29** | CONFIRMÉ | E-19 : `l1-02.1.md:74` (O4) asserte `unmsk_patch.shape[1] == 1025` — grandeur **interne à l'encodeur**, inatteignable depuis le port qui ne rend que `(1024,)` ⇒ assertion **dans l'adapter** + témoin monkeypatch. *(La **valeur** 1025, elle, est correcte : vérifiée à la source, cf. §3.)* · A-13 : `pyproject.toml` `ignore_missing_imports = true` ⇒ torch/claymodel/terratorch rendent `Any`, `strict` ne mord pas ⇒ `np.asarray` à la frontière, l'interdiction de `cast` de `l1-02.4`/O1 ne portant que sur le **consommateur** · D-9/S-7 : `l1-04.4.md:38-40` a besoin d'`onnxruntime` mais `l1-00` est **propriétaire exclusif** de `pyproject.toml` (`l1-00.md:16`, `_roadmap.md:237`) ⇒ feature `bench` pré-posée par `l1-00` · C-9/E-22 : `l1-02.3.md:52-53` grep **non scopé** contre O2 `:61` « Grep sur `src/` », alors que `scripts/fetch_models.py` appelle légitimement `hf_hub_download` (`l1-00.md:60-62`) ; et rien n'écrit que `fetch_models` **échappe** à la garde | ⚠ **Amendement sur C-24 — contradiction interne à la revue** : V-28/E-11 et V-07/E-4 veulent un `check_cache` **conservé et versionné** ; C-24 veut le script de contrôle de `l1-00` déclaré **non versionné**. Arbitrage : **un seul `scripts/check_cache.py` versionné**, et le grep de `l1-02.3` **scopé à `src/`** avec `scripts/fetch_models.py` et `scripts/check_cache.py` nommés comme exceptions légitimes |
| **V-30** | CONFIRMÉ | E-23 : `l1-03.2.md:75` — « vecteurs identiques au bit près » après « 0 recalcul » est **tautologique** · C-18 : `l1-03.4.md:61` (O1 = « **2** vecteurs ») contre `:75` (« réduire d'office à **1** fixture ») · A-14 : `__main__.py:14-17` déclare une « taxonomie **fermée** du lot (9 sous-commandes) » que le Lot 1 porte à 15 — **aucun test ne l'asserte** (vérifié : pas de test de la liste fermée), c'est une dérive de docstring **sans impact gate** · D-14/E-14 : `l1-03.4.md:64` (O4 « cache **vidé** ») détruirait le cache **partagé** posé par `l1-07` · A-12 : `core/geometry.py:52` `chip_bounds(grid, settings)` **existe déjà** et n'est pas cité par `l1-01.2.md:40-41` · C-19 : `l1-01.2.md:63` « les **10** champs ci-dessus » — la liste `:38-47` en compte **11** · D-16/E-27 : `l1-01.4.md:69` (O3) référence `embed_cloud_pct_max`, créée par `l1-03.2` (N2), alors que `l1-01.4` est **N0** · C-20 : `l1-04.1.md:72` (O1) consomme le `delay_s` du double sans figurer parmi les consommateurs listés en `l1-01.3.md:38-41` | Les 8 corrections retenues. Sur A-14, préciser le **propriétaire** de la mise à jour (`l1-03.2`, premier CLI ajouté). Sur D-14/E-14, la bonne forme est **`HF_HOME` pointé sur un `tmpdir` vide**, jamais un `rm` du cache |
| **V-31** | CONFIRMÉ-CORRECTION-À-AMENDER | E-6 : `l1-05.1.md:40-42` — `silhouette` « indicateur classique », **distance non définie**, alors que `cosine` est une similarité et `trajectory_drift` vaut `1 − cosine` · E-5 : le **0,2** et la baseline n'apparaissent que dans la prose (`l1-05.3a.md:46`), **dans aucune** des tables d'oracle · E-17 : `l1-05.3a.md:34-37` calcule la baseline « **depuis les mêmes chips** » alors que `:56-57` impose des tests « sur **vecteurs de fixture fabriqués** » — **il n'y a pas de chips derrière un vecteur fabriqué** : contradiction réelle ; et une passe baseline sur corpus complet = une **seconde lecture de ~16 Gio**, non budgétée · D-17 : `l1-05.3.H.md:34` puis `:49` régénèrent le **même** `similarity-report.md` (`l1-05.3a.md:27`) — le verdict du sous-échantillon est **écrasé** · E-30 : `l1-05.2.md:71` (O4 « similarité < 0,999999 ») sans issue si la valeur mesurée est 0,9999995 · C-15 : `l1-06.H.md:44-45` « que la **fidélité tient** » (sans seuil) et `:51` « **dépasse 0,5** » au lieu de `\|r\| > 0,5` (`l1-05.4.md:68`) | ⚠ **Deux amendements.** (1) D-19/C-14 « `l1-05.md` tronque 2 seuils sur 4 » : sur les 2 manquants, **la fidélité ≥ 0,999 appartient légitimement à `l1-04`** — seule la **corrélation nuage 0,5** manque vraiment à `l1-05`. Et le remède n'est **pas** de recopier : c'est un **renvoi** à `_roadmap.md` §2ter, sinon on recrée la divergence qu'on corrige. (2) C-16 « `VectorMeta` ré-énuméré dans `l1-03.md` » : **RÉFUTÉ** — `l1-03.md:43-46` dit explicitement « défini **UNE** fois, dans `l1-03.1` — les autres fiches y renvoient sans énumérer », puis cite 2 champs **comme motif**, pas comme définition. Ce n'est pas une ré-énumération |
| **V-32** | CONFIRMÉ-CORRECTION-À-AMENDER | S-11 : `l1-03.4.md:78` remonte la bascule à `l1-06.H`, dont `depends_on` (`l1-06.H.md:7`) ne contient pas `l1-03.4` · S-12 : `l1-05.3a.depends_on = [l1-05.1, l1-03.3]` alors que la fiche se teste **sur vecteurs fabriqués** (`:56-57`) · S-8 : `l1-04.2.md:49` mesure « **et sur le total** » sans qu'aucune arête ne garantisse l'existence d'un adapter réel · S-9 : `l1-03.1.md:54` renvoie le format `scl_summary` à `l1-01.2` — or **`l1-03.1` est N0 et `l1-01.2` est N1** : l'amont référence l'aval · S-10 : `lot-1-embeddings.md:139-140` mentionne `docs/lots/lot-1/` mais n'y **lie** rien · E-20 : `l1-01.2.md:76` (O6) borne les DN à `[0, 20000]` alors que `l1-01.4.md:38` **impose** une fixture nuageuse · E-24 : `l1-04.4.md:71` (O4) « champ `reason` **non vide** » · E-25 : `l1-03.4.md:42` (« Clay par défaut ») contre `:79-80` (« TerraMind… est **la première chose à essayer** ») · S-15 : `_roadmap.md:243-244` nomme `tests/fixtures/reports/` mais **aucun propriétaire** pour les fixtures de **vecteurs** | ⚠ **Deux amendements.** (1) **S-11 : ne PAS ajouter l'arête.** Elle rendrait **permanente** une contrainte **conditionnelle** (la bascule peut ne jamais avoir lieu). Bon mécanisme : un **point 8** dans la liste de décisions de `l1-06.H` (« si `l1-03.4` a basculé sur le double, statuer sur la garde permanente ») + le drapeau porté par le Résumé de `l1-03.4`. (2) **S-12 : la bonne dépendance est `l1-03.1`, pas `l1-03.2`** — `l1-05.3a` ne consomme que le **format** (`read_vector`/`VectorMeta`). **Recalculé : `l1-05.3a` passe de N4 à N1, et N4 tombe de 7 à 6 nœuds — ce qui désengorge aussi V-20.** Décision PO, car cela change la structure des niveaux. Les 7 autres sous-items : retenus. S-8 : arête `l1-04.2 → l1-02.4`, **coût de profondeur recalculé : zéro** |

---

## 2. Arbitrages tranchés

### V-02 — Où vit le cache des poids partagé entre worktrees

**Le fait est établi, et il est pire que dit.** `.env` est gitignoré (`.gitignore`, section
« Environments »), **et n'est lu par rien** : le `justfile` ne porte **aucun `set dotenv-load`**
(vérifié par grep exhaustif sur les 119 lignes), `ci.yml` ne le source pas, et `chips.py:43`
énonce la doctrine D4 qui l'interdit explicitement comme véhicule de configuration. Le volet 2
de `l1-07` (`l1-07.md:42-47`) repose donc sur un fichier **absent** d'un worktree natif et
**inerte** là où il existe. L'oracle O3 (`:74`, « `just check` dans un worktree neuf avec `.env`
copié ») valide un scénario qui n'est **pas** celui du worktree natif décrit par `CLAUDE.md` — la
copie de `.env` n'y est prescrite que pour le **repli manuel**.

**Tranché : `~/.cache/tiny-wae/models` (ext4), défaut absolu dans `settings.yaml` versionné.**

Cinq raisons, dans l'ordre de poids :

1. **Contamination de la mesure.** Les poids sont relus **à chaque démarrage de processus** —
   et `l1-04.1` chronomètre `setup_s` séparément, `l1-05.2` lance « deux processus distincts »,
   `l1-04.3b` en lance un par configuration. Mettre les poids sur `/mnt/d` injecte la **taxe
   drvfs** dans chacun de ces démarrages — exactement la taxe que `l1-04.2` existe pour isoler.
   On mesurerait le montage en croyant mesurer le modèle. C'est l'argument décisif.
2. **Symlinks.** Le cache HF est adressé par hash avec `blobs/` + `snapshots/` **en liens
   symboliques**. Sur drvfs, `huggingface_hub` détecte l'absence de support et **duplique les
   fichiers** : ~1,5–3 Go de poids deviennent le double, écrits à travers le montage. Sur ext4,
   le mécanisme nominal fonctionne, sans dédoublement et **sans avoir besoin de
   `HF_HUB_DISABLE_SYMLINKS`**.
3. **Coût mesuré du drvfs, déjà au dossier** : `CLAUDE.md` chiffre `just install` à **1 min 5 s
   et 696 Mo réels** faute de liens durs sur `/mnt/d`. Le même mécanisme s'appliquerait à la
   population du cache.
4. **La visibilité Windows n'est pas un besoin** : aucune fiche ne lit les poids depuis Windows.
   Le corpus, lui, reste sur `D:` — et c'est voulu, c'est l'objet de `l1-04.2`.
5. **Le partage entre worktrees est acquis dans les deux cas** — le vrai levier est le **chemin
   absolu**, pas le volume.

**Contrepartie, dite franchement** : l'ext4 de WSL2 vit dans un VHDX qui croît et ne se rétracte
pas ; un reset de la distribution impose un `just fetch-models`. ~3 Go et une recharge occasionnelle :
acceptable pour un POC.

**Mécanisme retenu, précisément** :
- `settings.yaml` versionné : `hf_home: "~/.cache/tiny-wae/models"` — **expansé et rendu absolu
  au chargement** (`Path(...).expanduser().resolve()`), ce qui règle F-3 dans le même geste.
- `TINY_WAE_HF_HOME` reste la **surcharge**, lue par `config_io.load_settings` (mécanisme déjà en
  place, `config_io.py:84-88`) — jamais par un `.env`.
- **`.env.example` documente, ne configure pas** : `l1-07`/DoD (`:63`) doit dire « documenté »,
  pas « recommandé comme mécanisme ».
- `HF_HUB_DISABLE_SYMLINKS=1` : **retiré du défaut**, conservé comme **note conditionnelle** —
  « si un jour `hf_home` pointe sur `/mnt/d`, cette variable devient obligatoire ». F-8 avait
  raison sur le mécanisme, mais son déclencheur disparaît avec le choix ci-dessus.
- **Conséquence sur V-30/D-14** : l'oracle O4 de `l1-03.4` (« cache vidé ») ne doit **jamais**
  vider ce cache — il pointe `HF_HOME` sur un `tmpdir` vide. Avec un cache sous `~/`, un `rm`
  malencontreux coûterait un re-téléchargement complet à **tous** les worktrees à la fois.

### V-17 / E-1 — L'encodage temporel de Clay porte-t-il l'année ?

**Verdict : E-1 a raison sur le fait. L'oracle O6 de `l1-02.1` est faux. Mais la correction
qu'il propose est un témoin faible, et doit être amendée.**

**Preuve, au code source de `Clay-foundation/model` (branche `main`, lue le 25/08/2026)** :

1. `claymodel/datamodule.py`, `EODataset.__getitem__` :
   ```text
   time_tensor = torch.tensor(
       np.hstack((chip["week_norm"], chip["hour_norm"]), dtype=np.float32)
   )
   ```
   Le tenseur `time` est construit **exclusivement** de `week_norm` et `hour_norm`.
   *(https://raw.githubusercontent.com/Clay-foundation/model/main/claymodel/datamodule.py)*

2. `docs/tutorials/embeddings.ipynb` — celui-là même que `l1-02.1.md:18` désigne comme source
   faisant foi. Cellule markdown « INPUT » :
   > `time:    batch x 4` - horizontally stacked `week_norm` & `hour_norm`

   et la sortie exécutée de la cellule d'inspection : `chips["time"].shape ==
   torch.Size([128, 4])`, avec les clés du `.npz` : `pixels, lon_norm, lat_norm, week_norm,
   hour_norm`.

**Conclusion mécanique.** L'entrée temporelle du modèle est faite de **4 scalaires** :
sin/cos d'une position **dans l'année** (semaine) et sin/cos d'une position **dans la journée**
(heure). **Ni l'année, ni aucune époque absolue n'y figure.** Un `datetime` décalé d'un an, à
date calendaire identique, produit le **même** couple (semaine, heure) — donc le **même**
`time`, le même `latlon`, les mêmes `pixels`, `waves` et `gsd` : le datacube est **identique**,
et `l1-05.2`/O1 exige par ailleurs l'identité bit à bit à configuration fixée. **O6 (« vecteurs
différents ») est donc faux**, ou au mieux non déterministe si la date choisie tombe sur un
basculement de numéro de semaine ISO d'une année à l'autre.

**Ce que je n'ai PAS vu, et que je ne prétends pas** : la formule exacte de `week_norm` (ISO
`isocalendar().week` ou jour-de-l'année ÷ 7) vit dans le **prétraitement** qui produit les
`.npz`, hors du dépôt `model/` — je n'ai pas pu la fetcher. **Mais la démonstration n'en dépend
pas** : quelle que soit la formule, « semaine » est une grandeur **intra-annuelle** et « heure »
une grandeur **intra-journalière**. Un décalage d'un an ne peut donc changer le vecteur que de
zéro, ou d'un cran de semaine dans le cas limite. Dans les deux cas, l'oracle **n'est pas
déterministe** — ce qui suffit à le disqualifier comme oracle.

**Correction retenue — amendée.** Remplacer O6 par **deux** critères, parce que la correction
d'E-1 seule (« +1 an → identiques ») ne prouverait plus rien de l'intention initiale (« la date
**est** une entrée du modèle ») :

| # | Critère | Seuil |
|---|---|---|
| O6a | Même chip, `datetime` décalé d'**un an jour pour jour** (dates choisies et **gelées dans le test** de façon à ce que la semaine ISO soit identique — à vérifier dans le test lui-même) | vecteurs **identiques**. ⭐ **Fait à consigner pour le Lot 2 : l'encodage temporel de Clay ne porte PAS l'année** — deux acquisitions à un an d'écart sont indiscernables pour le modèle sur ce canal |
| O6b | Même chip, `datetime` décalé d'environ **six mois** (p. ex. semaine 31 → semaine 5) | vecteurs **différents** — c'est **ce** témoin qui prouve que la date est réellement une entrée du modèle, ce que l'ancien O6 croyait prouver |

Et corriger `l1-02.1.md:76` : le commentaire « la date est une entrée du modèle, le Lot 2 doit le
savoir » reste juste, mais **la conséquence à consigner est l'inverse de celle écrite** — ce
n'est pas la date qui entre, c'est la **phase saisonnière**. Pour le Lot 2, c'est une
information de premier ordre : une dérive d'embeddings ne peut pas confondre « un an plus tard »
avec « un changement », mais elle **confond structurellement** deux dates à même semaine de deux
années différentes. C'est exactement le confondant saisonnier que `l1-05.4` cherche à isoler
(A02 contre C08) — le noter dans les deux fiches.

---

## 3. Findings additionnels du réfuteur

**A-1 (majeur) — `l1-03.1` (N0) ne peut pas remplir `torch_version` sans casser la garde
d'import paresseux.** `l1-03.1.md:55` impose `torch_version` (et `blas_threads`) dans
`VectorMeta`, alors que `l1-03.1` a `depends_on: []` (N0) et s'écrit **avant** que torch existe
dans l'environnement (`l1-00` l'installe). Pire : si A-9 est retenu (V-04) et que l'oracle
devient `import tiny_wae.__main__` ⇒ `"torch" not in sys.modules`, un `import torch` au niveau
module dans `adapters/vectors.py` **rendrait le gate rouge**. Correction : `torch_version` se lit
par **`importlib.metadata.version("torch")`** — qui n'importe pas torch — avec repli `None` si
absent, et c'est à écrire dans `l1-03.1`. Personne n'a relevé cette collision entre deux
corrections de la revue.

**A-2 (majeur) — piège de test dormant dans `l1-00` : où déclarer torch côté pixi.**
`test_packaging.py:101-118` exige que **tout** ce que déclare `[tool.pixi.dependencies]` (hors
`python`) figure aussi dans `[project.dependencies]`. Si `l1-00` déclare `torch` dans la table
**de base** `[tool.pixi.dependencies]`, ce test devient rouge **ou** force à gonfler le contrat
de la wheel — contredisant la décision « la wheel du worker reste légère » (`l1-00.md:50-51`). Le
test ne lit **pas** les tables de *feature*. À écrire explicitement dans `l1-00` : **torch,
claymodel et terratorch vont dans `[tool.pixi.feature.models.*]`, jamais dans la table de base.**

**A-3 (mineur, mais c'est la fiche qui se réclame de la source) — la recette Clay de `l1-02.1`
est incomplète par rapport au tutoriel qu'elle cite.** `l1-02.1.md:38` affirme « le tutoriel
officiel pose **exactement ces deux arguments** ». Le tutoriel (`embeddings.ipynb`, cellule 4) en
pose **quatre** :
```text
module = ClayMAEModule.load_from_checkpoint(
    checkpoint_path=CHECKPOINT_PATH, model_size="large", metadata_path=METADATA_PATH,
    dolls=[16, 32, 64, 128, 256, 768, 1024], doll_weights=[1, 1, 1, 1, 1, 1, 1],
    mask_ratio=0.0, shuffle=False,
)
```
Comme les kwargs de `load_from_checkpoint` **priment** sur les hyperparamètres restaurés par
`save_hyperparameters()`, l'omission de `dolls`/`doll_weights` n'est neutre que si le ckpt v1.5
les stocke identiques. À reconfirmer à l'implémentation, et à corriger dans la phrase.

**A-4 — vérifications POSITIVES, à ne pas rouvrir.** Trois affirmations des fiches que j'ai
re-vérifiées **à la source** et qui **tiennent** — la revue ne les avait pas contrôlées :
- `l1-02.1`/O4 : `unmsk_patch.shape[1] == 1025` est **exact**. Sortie exécutée du tutoriel :
  `unmsk_patch_s2.shape == torch.Size([128, 1025, 1024])` pour `CHIP_SIZE = 256`, patch 8 →
  32×32 = 1024 patchs + 1 CLS. *(Seule son **accessibilité** depuis le port est en cause —
  V-29/E-19.)*
- `l1-02.1`/§4 : `CLS = out[0][:, 0, :]` est conforme — le tutoriel fait
  `unmsk_patch, *_ = module.model.encoder(batch)`.
- `l1-02.1`/§3 : `waves` en µm est conforme — le tutoriel passe
  `wavelengths = list(metadata.bands.wavelength.values())` de `configs/metadata.yaml`.

**A-5 — contradiction interne à la revue, tranchée** : E-11/E-4 veulent `check_cache`
**versionné**, C-24 veut le script de contrôle de `l1-00` **non versionné**. Voir V-29 :
**un seul `scripts/check_cache.py` versionné**, grep de `l1-02.3` scopé à `src/`, les deux
scripts nommés comme exceptions.

---

## 4. Décompte honnête

**32 clusters traités. 0 laissé sans verdict.**

| Verdict | Nombre | Clusters |
|---|---|---|
| CONFIRMÉ | **20** | V-05, V-06, V-07, V-08, V-09, V-11, V-12, V-13, V-14, V-15, V-16, V-19, V-22, V-23, V-24, V-25, V-26, V-28, V-29, V-30 |
| CONFIRMÉ-CORRECTION-À-AMENDER | **11** | V-01, V-02, V-03, V-04, V-10, V-17, V-18, V-20, V-27, V-31, V-32 |
| NON-PROUVÉ | **1** | V-21 |
| RÉFUTÉ (cluster entier) | **0** | — |
| RÉFUTÉ (sous-item) | **2** | « 3 chaînes de longueur 8 disjointes » (dans V-27 — il y en a **48**) · C-16 « `VectorMeta` ré-énuméré » (dans V-31) |

**Régime de vérification appliqué**

- **Vérification pleine (fait re-prouvé par moi, au fichier:ligne du dépôt ou à la source
  amont)** : **29 clusters** — V-01, V-02, V-03 (partiel), V-05 à V-12, V-14 à V-23, V-25 à V-32.
  Les 31 fiches ont été relues intégralement sur disque, ainsi que `justfile`, `pyproject.toml`,
  `.gitignore`, `ci.yml`, `.github/`, `.claude/settings.json`, `.claude/commands/run.md`,
  `tests/test_smoke.py`, `tests/test_packaging.py`, `adapters/config_io.py`,
  `adapters/backfill.py`, `core/settings.py`, `core/geometry.py`, `__main__.py`,
  `docs/lots/lot-1-embeddings.md`.
- **Vérification allégée (correction + impact graphe seulement, fait admis sur convergence)** :
  **3 clusters** — V-04, V-13, V-24.
- **Graphe** : recalculé intégralement depuis les 26 frontmatters dispatchables. Chaque
  correction structurante (V-01, V-10, V-22, V-32/S-8, V-32/S-12) a été **re-simulée** :
  profondeur 8 et largeur 3,25 préservées dans tous les cas ; aucun cycle ; seule S-12 modifie
  la répartition (N4 : 7 → 6).
- **Sources amont** : 3 fichiers de `Clay-foundation/model` récupérés et lus
  (`claymodel/datamodule.py`, `claymodel/utils.py`, `docs/tutorials/embeddings.ipynb`).

**Ce que je n'ai PAS pu vérifier, et pourquoi**

1. **Formule exacte de `week_norm`** (ISO vs jour-de-l'année) — vit dans le prétraitement hors du
   dépôt `model/`. **Sans effet sur le verdict V-17** : la démonstration ne repose que sur la
   nature intra-annuelle de la grandeur, établie au code.
2. **Permalien hatchling `allow-direct-references`** (V-03) — `curl` sortant bloqué par le proxy
   de l'atelier ; l'API GitHub et `pypi.org` renvoient vide via le fetch. Affirmé de mémoire du
   comportement de hatchling ; **à reconfirmer par un `just install` d'essai**, ce qui coûte une
   minute.
3. **Cloisonnement des caches GitHub Actions par branche** (V-07/F-7) — comportement documenté de
   `actions/cache`, non re-vérifié par permalien pour la même raison.
4. **`TIMM_USE_OLD_CACHE`** (V-28/F-11) et **ventilation hub/xet des tailles** (V-28/F-12) —
   dépendent de la version de `timm`/`huggingface_hub` réellement résolue par pixi ; ni l'une ni
   l'autre n'est installée ici. À traiter en **note d'implémentation**, pas en exigence de fiche.
5. **Valeurs numériques de deux oracles** : `l1-05.2`/O4 (le cas 0,9999995 est-il atteint ?) et
   `l1-01.2`/O6 (les DN d'un chip nuageux dépassent-ils 20000 ?). Les deux exigent une exécution
   réelle. Les findings E-30 et E-20 restent **plausibles et bien argumentés**, mais leur
   déclenchement effectif n'est pas prouvé — la correction proposée (paliers · borne élargie +
   distribution publiée) est de toute façon la bonne : elle rend l'oracle **mesurable** au lieu
   de le laisser deviné.
6. **`scripts/backlog.py lots` face à un sous-répertoire `docs/lots/lot-1/`** (extension de S-10)
   — je n'ai pas lu `backlog.py`. Le commit `156cb3d` mentionne un « garde-fou md2html sur les
   fiches de lot » : à contrôler avant que trois fiches d'agent y déposent des `.md`.

**Motif d'inquiétude résiduel, hors cluster** : sur 32 clusters, **31 sont confirmés au moins
sur le fait**. Un taux de survie aussi élevé après réfutation indique soit une revue v3 de très
bonne tenue, soit un corpus de fiches encore loin de la maturité de dispatch. Les deux lectures
sont compatibles — et les trois findings additionnels (A-1, A-2, A-3), tous trouvés en
re-vérifiant plutôt qu'en cherchant, penchent pour la seconde.
