# Revue v4 — Chantier Lot 1, l'angle de l'implémenteur

**Date** : 26/08/2026 · **Revueur** : équipe d'implémentation (Claude Code, Opus) — **revue
solo, non adversariale**, à la demande de Philippe, comme la post-revue 1 du Lot 0.
**Base** : `cfd09cb` (branche `develop`), fiches lues dans leur état de travail (l'instance
PO écrivait au même moment — aucune fiche n'a été modifiée par cette revue).
**Position** : celle qui a livré le Lot 0 et qui devra exécuter ces 24 fiches d'agent. C'est
la seule chose que j'apporte que les v1, v2 et v3 ne pouvaient pas apporter — l'accès au
**code réel**, au **gate réel** et au **corpus réel**.

## Protocole

Aucun agent délégué. Trois passes, toutes fondées sur des preuves exécutables :

1. **Graphe** — les 31 frontmatters reparsés, niveaux recalculés, appariements vérifiés.
2. **Ancrage** — chaque affirmation des fiches qui parle du code du Lot 0 confrontée au
   fichier, cité `fichier:ligne`.
3. **Faits chiffrés** — chaque nombre du chantier recompté sur les 9 873 manifestes et les
   5 793 chips de `D:\datas\tiny-wae`, et deux mécanismes d'outillage **sondés** plutôt que
   déduits (deptry face aux extras, ruff face à un `assert` dans `scripts/`).

**Chiffres de la revue** : 12 issues — **1 bloquante · 6 majeures · 5 mineures** — plus
**1 fait chiffré faux**. 23 affirmations d'ancrage contre-vérifiées, **22 exactes**.

---

## 1. Verdict global

**Le chantier est prêt, et il est d'une qualité que je n'ai pas vue au Lot 0.** Les trois
revues précédentes ont fait leur travail : la table des faits des deux modèles est juste,
les oracles ont des témoins dans les deux sens, la politique de test est cadrée, et le
graphe publié dans `_roadmap.md` §4 est **exact au fiche près** — je l'ai recalculé, les
huit niveaux tombent à l'identique.

Mon verdict tient en une phrase : **les fiches sont justes entre elles et justes vis-à-vis
du code ; ce qui casse encore, c'est leur rencontre avec le HARNAIS.** C'est le même motif
que le finding B1 de la revue v2, appliqué cette fois non plus au cache de poids mais aux
règles de lint, aux zones d'écriture et à l'ordre d'import. Aucune de ces choses ne se voit
en lisant les fiches ; toutes se voient en essayant de les exécuter.

Une seule issue est **bloquante**, et elle rendrait le gate rouge sur cinq fiches
consécutives. Les six majeures sont des trous de spécification qui produiraient chacun un
résultat plausible et faux — le risque nommé par la v1, toujours le bon.

**Rien ne justifie de retarder la descente en `a-faire/`.** Douze corrections, toutes
locales, aucune ne rouvre une décision.

## 2. Synthèse par objectif

| Phase | Verdict | Ce qui reste |
|---|---|---|
| **O1 — Socle** (`l1-00`, `l1-01.x`, `l1-07`) | **solide, deux trous mécaniques** | l'expansion de `~` n'a pas d'ancrage (M1) ; `scl_summary` a deux définitions contradictoires (M5) |
| **O2 — Modèles & exécution** (`l1-02.x`, `l1-03.x`) | **le mieux tenu du lot** | l'atomicité porte sur les fichiers, pas sur la paire (M2) ; l'issue anti-double-coût du smoke est à moitié écrite (M6) |
| **O3 — Banc & qualité** (`l1-04.x`, `l1-05.x`) | **bloqué par le lint** | `assert` interdit dans `scripts/` alors que cinq oracles l'exigent (B1) ; le contrôle nuage repose sur 14 points (m4) ; un chiffre faux dans deux fiches (F1) |
| **O4 — Décision** (`l1-06.H`) | **rien à redire** | la fiche liste ses entrées, nomme ses huit décisions, et refuse de trancher à la place de l'humain |

## 3. Issues consolidées

| Sév. | Fiche(s) | Problème | Action |
|---|---|---|---|
| **bloquant** | `l1-04.2` `l1-04.3a` `l1-04.3b` `l1-04.4` `l1-05.2` | `assert` dans `scripts/` → `S101` → `just lint` rouge. Cinq oracles l'exigent explicitement | `l1-00` pré-pose la ligne `per-file-ignores`, **ou** les fiches disent « exception typée, jamais `assert` » |
| majeur | `l1-00` `l1-07` | l'expansion de `~` dans `hf_home` n'a aucun point d'ancrage nommé, et son échec est **silencieux** | nommer le mécanisme dans `config_io`, ajouter un oracle « même chemin depuis deux CWD » |
| majeur | `l1-03.1` (+ `l1-03.3` `l1-05.3a`) | l'atomicité est spécifiée fichier par fichier, jamais sur la **paire** `.npy` + `.json` | le `.json` s'écrit en dernier et fait foi ; un `.npy` orphelin est un déchet ignoré |
| majeur | `l1-05.3a` `l1-03.2` | `unexplained_missing` comptera comme inexpliqués les items qui portent un `.error.json` | deux listes : `failed_missing` et `unexplained_missing` |
| majeur | `l1-05.3a` `l1-04.5` `l1-05.4` | les trois fiches écrivent dans `docs/lots/lot-1/`, que `CLAUDE.md` attribue **explicitement** à l'architecte | porter l'exception dans `CLAUDE.md` **avant** le dispatch de `l1-05.3a` (N1) |
| majeur | `l1-01.2` `l1-03.1` | `scl_summary` : l'oracle O6 contredit le format défini par la fiche qui fait foi | trancher la forme et l'unité dans `l1-03.1`, réécrire O6 |
| majeur | `l1-03.4` | l'issue proposée pour ne pas payer le smoke deux fois est **incomplète** | ajouter la condition manquante : import **paresseux** de l'adapter |
| fait faux | `l1-05.1` `l1-05.3a` | « 43 à 300 chips par site » — mesuré : **63 à 579** (49 à 563 après filtre) | corriger les deux occurrences |
| mineur | `l1-04.4` | O5 (`deptry` + `test_packaging`) est **vert par construction** | le dire, ou déplacer la garde là où elle mord |
| mineur | 7 scripts neufs | `mypy --strict` couvre `scripts/`, et un commentaire du Lot 0 affirme le contraire | une ligne dans les fiches de banc ; corriger le commentaire périmé |
| mineur | `l1-02.3` | le **code de sortie** du cas « poids absent » n'est fixé nulle part | trancher en une ligne |
| mineur | `l1-05.4` `l1-05.3.H` | le contrôle de corrélation aux nuages repose sur **14 points** | élargir à C02, ou déclarer non concluant sous un `n` minimal |
| mineur | `l1-04.5` `l1-05.3a` `l1-05.4` | les trois rapports décisionnels n'auront **pas de vue HTML** ; rien ne borne le volume des PNG | une ligne par fiche |

---

## 4. Le détail, avec les preuves

### B1 — `assert` dans `scripts/` fait rougir le gate, et cinq oracles l'exigent

`pyproject.toml` sélectionne la famille `S` (flake8-bandit) et **n'exempte `S101` que pour
deux périmètres** : `"tests/**"` et `"scripts/smoke.py"` — nommément, et avec un commentaire
qui explique pourquoi le smoke seul y a droit. Les sept scripts que le Lot 1 ajoute n'y
sont pas.

Or les oracles exigent la vérification **dans le script**, pas à côté :

- `l1-04.2`/O1 — « ensembles **identiques** — vérifié **dans le script**, pas supposé » ;
- `l1-04.3a`/O3, `l1-04.3b`/O3, `l1-04.4`/O3 — même formulation ;
- `l1-05.2`/O1 — « **assertion DURE** : 100 % de `array_equal` ».

**Sonde exécutée** (jetable, supprimée) : un fichier `scripts/` contenant un `assert a == b`
avec message → `ruff check` rend `S101 Use of assert detected`, une erreur. `just lint` étant
`ruff format --check . && ruff check .`, le gate est rouge, et `just check` avec lui.

L'agent aura trois issues, et deux sont mauvaises : semer des `# noqa: S101` (bruit
permanent), ou ajouter la ligne d'exemption dans `pyproject.toml` — **fichier dont `l1-00`
est propriétaire exclusif pour tout le lot**. La seconde casse le patron « table pré-posée »
qui protège le chantier, et elle le casse au moment le plus tardif, quand `l1-00` est déjà
close. La troisième, la bonne, est de lever une exception typée.

⚠ Cette issue est la seule que je classe **bloquante**, et pas parce qu'elle serait difficile
à contourner : parce que la règle d'autonomie du `/run` dit qu'après trois tentatives sur un
gate rouge, **on diffère la fiche**. Cinq fiches de banc différées, c'est O3 qui ne se fait
pas.

→ **`l1-00` pré-pose `"scripts/bench_*.py" = ["S101"]`** dans `per-file-ignores`, dans le
même geste qui pré-pose la feature `bench` et les trois clés de settings. C'est le patron du
lot, appliqué à ce qui lui manquait. Alternative défendable : chaque fiche de banc écrit
« lever une exception typée, jamais `assert` » — plus propre, mais il faut alors le dire
**cinq fois**, et une fiche oubliée redevient rouge.

### M1 — L'expansion de `~` n'a pas d'ancrage, et son échec ne se voit pas

`l1-00` point 3 demande `hf_home: "~/.cache/tiny-wae/models"`, « expansé et rendu absolu au
chargement ». La fiche nomme précisément le point d'ancrage des deux **autres** clés
qu'elle pré-pose — `config_io._INT_FIELDS` pour la coercition, `Settings.validate()` pour les
bornes. Pour la troisième, la plus subtile, elle ne nomme rien.

Et il n'y a rien à copier : `core/settings.py` définit `Settings` en `@dataclass(frozen=True,
slots=True)` où **tous les chemins sont des `str`** (`data_root: str = "./data"`), et
`adapters/config_io.py:30` ne connaît que `_INT_FIELDS` et `_LIST_FIELDS`. Le Lot 0 n'a
jamais eu de champ-chemin à expanser — il n'offre donc **aucun patron**.

Le mode d'échec est le pire qui soit : `Path("~/.cache/tiny-wae/models")` non expansé n'est
pas une erreur, c'est un **répertoire nommé `~`** créé dans le CWD. Chaque worktree
d'agent se fabrique alors son propre cache, et re-télécharge plusieurs Go — c'est-à-dire
exactement la propriété que `l1-07`/O4 existe pour garantir (« `just check` dans un worktree
neuf, vert **sans aucun téléchargement** »). O4 tomberait, mais **après** que le mal est
fait, et en désignant `l1-07` alors que la cause est dans `l1-00`.

→ Nommer le mécanisme dans `l1-00` (un `_PATH_FIELDS` dans `config_io`, symétrique de
`_INT_FIELDS`) et ajouter un oracle discriminant : **`hf_home` chargé depuis deux CWD
différents rend le même chemin absolu**. Sans témoin de ce genre, la garde n'est pas
exercée.

*Note* : `resolve()` sur un chemin relatif l'ancre au CWD, ce qui serait le même bug déguisé.
Avec un `~` en tête, `expanduser()` suffit et donne déjà un absolu.

### M2 — L'atomicité porte sur les fichiers, jamais sur la paire

`l1-03.1` spécifie « écriture **atomique** (fichier temporaire puis `Path.replace`), comme
`write_manifest` du Lot 0 ». Le renvoi est juste : `adapters/manifests.py:184-203` fait
exactement ça, et son nom de temporaire porte **PID *et* identifiant de thread** parce que
le `ThreadPoolExecutor` du Lot 0 a produit la collision en vrai.

Mais un vecteur, c'est **deux** fichiers : le `.npy` et son compagnon `.json`. Rendre chacun
atomique ne rend pas la **paire** atomique. Rien ne dit l'ordre d'écriture, ni ce que vaut un
`.npy` sans compagnon. Or trois fiches en aval supposent l'indissociabilité :

- `l1-03.3`/O4 — SIGINT : « `read_vector` réussit sur **≥ 2** vecteurs ; aucun temporaire
  visible » — c'est précisément le scénario d'interruption entre les deux écritures ;
- `l1-05.3a` — l'invariant `vecteurs_sur_disque == len(list_vectors(...))` ;
- `l1-04.5` et `l1-05.4` — sélection par `list_vectors`.

Et le contrat de `read_vector` ne couvre pas le cas : « `None` si absent, erreur typée si
corrompu ». Un `.npy` orphelin n'est **ni absent ni corrompu**.

→ Le Lot 0 a déjà la réponse, et elle est élégante : `list_for_site`
(`adapters/manifests.py:241-247`) **ne globe que les fichiers nommés exactement
`manifest.json`**, ce qui rend les temporaires et les résidus structurellement invisibles.
Transposer : **écrire le `.json` en dernier**, en faire le marqueur de complétude, ancrer
`read_vector` et `list_vectors` dessus, et traiter un `.npy` sans compagnon comme un déchet.
Un oracle de plus dans `l1-03.1` : `.npy` seul déposé à la main → invisible de
`list_vectors`, `read_vector` rend `None`.

### M3 — Le contrôle de complétude criera dès le premier échec

`l1-03.2` écrit `embeddings/<model_id>.<spec_hash[:8]>.error.json` pour tout item en échec —
choix justifié (E-1 : ne jamais réécrire le manifeste du Lot 0) et sémantique claire
(« une erreur se rejoue »).

`l1-05.3a` définit `unexplained_missing` comme « la liste nommée des `item_id` **éligibles
sans vecteur** ». Un item qui a échoué est éligible, il n'a pas de vecteur, et il **porte sa
propre explication à côté** — il tombera pourtant dans la liste des inexpliqués. Aucune
fiche ne relie les deux mécanismes.

La conséquence n'est pas une fausse valeur, c'est pire : un contrôle qui crie sans raison
finit par être ignoré, et c'est le jour où il crie pour la bonne raison qu'on ne le regarde
plus. La revue v3 a eu raison de refaire cet invariant (E-3, « un témoin qu'on ne peut pas
rendre rouge n'est pas un témoin ») ; il lui manque le pendant — **un témoin qui rougit tout
le temps n'en est pas un non plus**.

→ `l1-05.3a` publie **deux** listes : `failed_missing` (un `.error.json` est présent — c'est
un incident connu, avec sa cause) et `unexplained_missing` (rien du tout — c'est le vrai
signal). O3 exerce les deux sens sur chacune.

### M4 — Trois fiches écrivent dans une zone que `CLAUDE.md` attribue à l'architecte

`_roadmap.md` §5 et `l1-05.3a` actent que `docs/lots/lot-1/` est « ouverte à l'équipe en
création » par décision de Philippe du 25/08. La décision est prise, je ne la rouvre pas.

Mais `CLAUDE.md`, qui écrit de lui-même « **Ces instructions priment** », dit toujours :
« L'architecte/PO écrit UNIQUEMENT dans `docs/backlog/` […] et `docs/lots/` […]. L'équipe
d'implémentation écrit dans `src/`, `tests/`, `scripts/` ». Un agent d'implémentation
consciencieux — celui qu'on veut — lira la contradiction et fera ce que la méthode lui dit
de faire dans ce cas : **signaler plutôt qu'écrire**. `l1-05.3a` est en **N1**, très tôt
dans le run.

Et `l1-07`/`l1-02.3` ont fermé la seule porte de sortie : `CLAUDE.md` est hors zone, les
fiches **rédigent** la ligne au Résumé et Philippe la reporte — c'est-à-dire **après** le
run.

→ Les trois exceptions (`docs/lots/lot-1/`, `.github/workflows/`, `config/`) doivent être
portées dans `CLAUDE.md` **avant le dispatch**, pas après. C'est un geste de Philippe, de
deux minutes, et c'est un pré-requis de run au même titre que la sonde de worktree.

### M5 — `scl_summary` : l'oracle contredit la définition qui fait foi

`l1-03.1` — la fiche N0, celle qui définit : « un `dict[str, float]` : les classes SCL
converties en **fractions** — somme ≈ 1 — **plus une clé `valid_pct`** ».
`l1-01.2`/O6 — la fiche N1, qui déclare pourtant s'y conformer : « `scl_summary` **somme à
~1** ».

Avec `valid_pct` dans le même dict, `sum(values())` vaut ≈ 1 + `valid_pct`. L'oracle rougit
sur une implémentation **conforme** au format qui fait foi.

S'y ajoute une unité non tranchée : `valid_pct` est-il une fraction (0,98) ou un pourcentage
(98,0) ? Le nom dit « pct », ses voisins sont des fractions. Un dict qui mélange les deux
est exactement l'ambiguïté que ce lot traque partout ailleurs — et le Lot 0 en a déjà payé
une, sur `ratio` contre `pct`.

→ Trancher la forme dans `l1-03.1` — je recommande `{"classes": {...}, "valid_pct": 98.0}`,
qui rend la somme vérifiable sans convention implicite — et réécrire O6 en « la somme des
**fractions de classes** ≈ 1 ».

### M6 — L'anti-double-coût du smoke ne suffit pas s'il reste un import en tête

La revue v3 (V-23) a vu juste : `tests/test_smoke.py` rejoue `smoke.main()` sous pytest,
donc l'étape embed serait payée deux fois par `just check`. Elle offre deux issues : exposer
l'étape en fonction séparée que le test n'appelle pas, ou restreindre le test.

**Aucune des deux ne suffit.** `tests/test_smoke.py:47` fait, **au niveau module** :

    smoke = _load_smoke_module()

C'est-à-dire que `scripts/smoke.py` est chargé et **exécuté à la collecte pytest**, avant
tout test. Si l'import de l'adapter TerraMind reste **en tête** de `smoke.py` — comme le sont
tous les imports du fichier aujourd'hui, et comme c'est le style dominant du dépôt —
terratorch (lightning, timm, diffusers, torchgeo) est importé à chaque collecte. Y compris
pour un simple `just test`, y compris pour un `-k` d'une seule fonction.

→ Ajouter la condition manquante à `l1-03.4` : **l'import de l'adapter doit être paresseux,
dans le corps de la fonction d'étape**. Le lot connaît déjà ce geste et l'a oraclé ailleurs
(`l1-01.3`/O4, `l1-03.1`/O6) ; il faut juste l'écrire ici aussi. Sans ça, V-23 n'est corrigé
qu'à moitié, et le budget des 30 s est calculé sur un coût qu'on paie toujours.

### F1 — « 43 à 300 chips par site » : mesuré, c'est 63 à 579

Recompté sur les 9 873 manifestes :

| Population | min | médiane | max |
|---|---|---|---|
| chips `ingested` par site | **63** (B08) | 219 | **579** (B01) |
| après filtre `cloud_pct ≤ 10` | **49** (B08) | 178 | **563** (B01) |

Le chiffre « 43 à ~300 » figure dans `l1-05.1` (Contexte) et `l1-05.3a` (§5), où il justifie
le choix de la silhouette. Le fait qualitatif — des groupes très inégaux — est non seulement
préservé mais **renforcé** : le rapport réel est de 9,2× et non de 7×. Ce sont les bornes
qui sont fausses, dans les deux fiches.

⚠ Ce qui compte ici n'est pas l'écart, c'est ce qu'il révèle : **c'est le seul chiffre du
chantier que j'aie trouvé faux**, et il l'est parce qu'aucune des trois revues précédentes
ne pouvait ouvrir le corpus. Tous les autres sont exacts (voir §5).

## 5. Ce qui a été contre-vérifié — et qui tient

Ancrages **exacts**, chacun cité :

- `core/geometry.py:52` — `chip_bounds(grid, settings)` existe, et il ne faut pas le
  réécrire : `l1-01.2` a raison sur les deux points.
- `core/bands.py` — `BAND_ORDER_10M | BAND_ORDER_20M` donne **exactement** les 10 bandes de
  `BAND_ORDER_EMBED`, et `nir` y est en **4ᵉ** position contre **7ᵉ** chez Clay. Le piège que
  `l1-01.1` a écrit en toutes lettres est réel.
- `adapters/manifests.py:101-105` — `Manifest` porte bien `scl_class_counts`, `cloud_pct`,
  `grid_hash`, `radiometry`, `boa_offset_applied`.
- `tests/test_packaging.py` — lit `[project.dependencies]` et balaie **tout `src/` par
  AST** : `import claymodel` le rendra rouge (V-12 exact). Et son second test lit
  `[tool.pixi.dependencies]`, table de base — donc y **ne pas** mettre torch/terratorch le
  laisse vert (A-2 exact).
- `pyproject.toml` — `addopts = "-q --disable-socket"` : sans cache, c'est bien un
  `SocketBlockedError` et pas une erreur réseau lisible (`l1-07` exact) ;
  `ignore_missing_imports = true` (`l1-02.4`/O1 exact, y compris sa nuance sur la portée).
- `adapters/backfill.py:441` — c'est bien un `ThreadPoolExecutor` (V-21 exact), donc
  `torch.set_num_threads` atteindra les workers.
- `adapters/chips.py:88` — `_is_offline()` est relu à chaque appel : la leçon que `l1-02.3`
  transpose est la bonne.
- `justfile` — `just script <nom>` existe (`l1-04.2`, `l1-05.2` peuvent s'y adosser) ;
  `just check` = `lint && types && deptry && test && smoke && cwl` ; `just deptry` porte
  bien `src` seul.
- `.github/workflows/ci.yml` — une seule étape `just check` derrière `just install`, et le
  commentaire « le smoke est déterministe et hors ligne » est bien celui que `l1-07` doit
  corriger.
- `.gitignore` — `data/` est ignoré (`l1-04.5` a raison de sortir les rapports de là) ;
  `.claude/settings.json` porte `worktree.baseRef: "head"`.
- `config/sites.yaml` — versionné, **25 grilles calculées** : `l1-01.2` pourra résoudre le
  `Grid` de n'importe quel site sans fixture supplémentaire.
- `scripts/backlog.py:939` — `cmd_lots` globe `docs/lots/*.md` **non récursivement** : les
  rapports déposés dans `docs/lots/lot-1/` n'entreront pas en collision avec `just lots`. Et
  le garde-fou `md2html` (`backlog.py:700`) ne se déclenche que si le parent s'appelle
  `lots`, donc `just md2html` reste utilisable sur eux.

Faits chiffrés **exacts** :

| Fait annoncé | Mesuré |
|---|---|
| 5 793 chips · 9 873 manifestes · 25 sites | **exact** |
| ~4 959 chips sous le seuil de 10 % (86 %) | **4 959** (85,6 %) |
| `chip.tif` 2,1 Mo · `chip_20m.tif` 0,79 Mo · `scl.tif` 0,07 Mo | **2,10 · 0,79 · 0,07** — 4 fixtures ≈ 11,8 Mo, sous les 15 Mo d'O1 |
| `chip.tif` 512²×4 et `chip_20m.tif` 256²×6, uint16 | **exact** (`scl.tif` est en 256², uint8 — sans conséquence, `scl_summary` vient du manifeste) |
| graphe : 5 chapeaux · 24 fiches agent · 2 humaines, profondeur 8 | **exact** — aucun cycle, aucun `depends_on` orphelin, parent/subtasks tous appariés, aucun chapeau qui ordonne, et les **huit niveaux publiés tombent à l'identique** |

Mécanismes **sondés** plutôt que déduits :

- ⭐ **`deptry` lit bien les `[project.optional-dependencies]`.** C'est le mécanisme central
  de `l1-00`, affirmé « vérifié en revue » sans preuve reproductible — je l'ai testé sur un
  projet jouet dans l'environnement pixi réel : extra déclarant `pyyaml` + `import yaml` →
  « No dependency issues found » ; extra retiré → `DEP003`. **Le témoin joue dans les deux
  sens.** La stratégie de l'extra tient.
- **`assert` dans `scripts/` fait rougir ruff** — voir B1.

## 6. Les mineures

**m1 — `l1-04.4`/O5 est vert par construction.** « `deptry` vert **et** `test_packaging.py`
vert : `onnxruntime` vit dans la feature `bench`, pas au contrat de la wheel ». Mais
`just deptry` = `deptry src` — le `justfile` dit même explicitement pourquoi (« `src` SEUL :
`scripts/` n'est pas dans la wheel ») — et `test_packaging.py` ne balaie que `_SRC`.
`scripts/bench_quant.py` n'est vu par **ni l'un ni l'autre**. L'oracle serait vert si
`onnxruntime` n'était déclaré nulle part. Ce n'est pas faux, c'est **non discriminant** — le
contraire de ce que ce lot exige de ses oracles. Le dire, ou l'assumer comme un contrôle de
non-régression sur le contrat de la wheel (ce qu'il est réellement).

**m2 — `mypy --strict` couvre `scripts/`, et un commentaire du Lot 0 dit l'inverse.**
`pyproject.toml:146` : `files = ["src", "tests", "scripts"]`. Les **sept** scripts neufs du
lot (cinq bancs, `fetch_models`, `check_cache`) devront passer le strict ; aucune fiche de
banc ne le mentionne, et toutes disent « aucun test unitaire, c'est un script de mesure » —
formulation qui laisse croire que `scripts/` est hors du filet.
⚠ Pire : `tests/test_smoke.py` l'affirme en docstring — « `scripts/` […] mypy ne le couvre
pas non plus, `pyproject.toml` : `files = ["src"]` ». **Ce commentaire est périmé** (corrigé
par `out-01`, jamais mis à jour) et il se trouve exactement sur le chemin que `l1-03.4`
demande à l'implémenteur de lire. Une ligne à corriger, et un piège documentaire en moins.

**m3 — le code de sortie du cas « poids absent » n'est fixé nulle part.** Le Lot 0 a figé ses
quatre codes en chapeau (`cli/exit_codes.py`). Le Lot 1 introduit un cas neuf — poids
manquant du cache — qui traverse `l1-02.3`, `l1-07` et `l1-03.4` sans qu'aucune ne dise s'il
vaut `1` (métier), `2` (config/usage) ou `3` (non concluant). Comme `embed` n'a pas d'amont
réseau, `3` est libre ; `2` me paraît juste (c'est un défaut d'environnement). Une ligne dans
`l1-02.3`, qui possède le chemin commun.

**m4 — le contrôle de corrélation aux nuages repose sur 14 points.** Mesuré sur C08 :
119 chips `ingested`, `cloud_pct` de 0,0 à 26,1, médiane 0,0 — **88 sont à ≤ 1 %** et
**14 seulement dépassent 10 %**. La correction K-14 (mesurer sur la plage complète) était
juste, mais elle n'apporte que ces 14 points, et `l1-06.H` point 5 traite `|r| > 0,5` comme
un déclencheur de décision. Sur 14 points, ce seuil s'atteint par accident.
→ Deux remèdes, cumulables : embedder **C02 aussi sans filtre** (21 points de plus,
soit 35 — C02 a 126 chips `ingested` dont 105 sous le seuil), et **exiger un `n` minimal**
au-dessus du seuil sous lequel le contrôle est déclaré **non concluant** au lieu d'être
publié comme un `r`. `l1-05.4`/O3 publie déjà `n` et l'étendue effective — il ne manque que
la conduite à tenir.

**m5 — les trois rapports décisionnels n'auront pas de vue HTML, et rien ne borne les PNG.**
`l1-06.H` liste `bench-report.md`, `similarity-report.md` et `trajectory-report.md` comme
« ce que tu auras sous les yeux », dans un projet où tout le reste a sa page rendue. Une
ligne par fiche (`just md2html`, qui fonctionne sur eux — vérifié). Et `l1-05.4` produit des
courbes Pillow « pour les deux modèles » plus une annexe « tous les sites » dans un
répertoire **versionné**, alors que le lot borne scrupuleusement ses fixtures à 15 Mo. Une
borne, même large.

*(Deux renvois inexacts, sans conséquence, signalés pour l'hygiène : `l1-07` dit que la
taille du cache est « publiée par `l1-00`/O4 » — O4 mesure le delta d'installation, ce sont
les trois tailles d'artefacts d'**O1** qui portent l'information. Et `l1-01.2` ne nomme pas
`config/sites.yaml` parmi ses entrées, alors que `chip_bounds` exige un `Grid` **calculé** —
`core/sites.py:35-37` les met à `None` par défaut, `_require_computed` lève. Non bloquant :
le fichier est versionné et complet.)*

## 7. Fiches à créer / scinder / requalifier

**Aucune.** Le découpage tient, les efforts sont plausibles, et les deux scissions faites en
revue v1 (`l1-04.3` → `a`/`b`, `l1-05.3` → `a`/`.H`) se lisent comme les bonnes. Les douze
corrections ci-dessus sont toutes **locales à une fiche existante** ; aucune ne demande de
créer, scinder ou fusionner.

Deux requalifications d'oracle, en revanche :

- `l1-04.4`/O5 — le dire non discriminant, ou le déplacer ;
- `l1-01.2`/O6 — réécrire la clause `scl_summary` (M5).

## 8. Questions ouvertes — décisions recommandées

1. **`assert` dans les scripts de banc** — pré-poser l'exemption dans `l1-00`, ou interdire
   `assert` dans les cinq fiches ? *Recommandation : pré-poser.* Une ligne dans le fichier
   dont `l1-00` est déjà propriétaire, contre cinq formulations qu'un oubli suffit à casser.
2. **Forme de `scl_summary`** — `{"classes": {...}, "valid_pct": …}` ou un dict plat ?
   *Recommandation : imbriqué*, et `valid_pct` en pourcentage puisque son nom le dit.
3. **`CLAUDE.md`** — les trois exceptions de zone sont-elles portées **avant** le run ?
   *Recommandation : oui, c'est un pré-requis de dispatch.* Sinon `l1-05.3a` (N1) rencontre
   la contradiction au deuxième niveau du graphe.
4. **Contrôle nuage** — élargir à C02 (coût : ~21 chips de plus à embedder, quelques
   minutes) ou se contenter d'un seuil de non-concluance ? *Recommandation : les deux.*

## 9. Prochaines actions

1. **Philippe** — porter les trois exceptions de zone dans `CLAUDE.md` (M4) et trancher les
   quatre questions du §8. C'est le seul travail qui ne peut pas être délégué.
2. **PO** — appliquer les douze corrections. Aucune ne rouvre une décision ; la plus longue
   est M2 (l'ordre d'écriture de la paire et l'oracle qui va avec).
3. **Descente en `a-faire/`** — la vague N0 est mûre dès les corrections appliquées :
   `l1-00`, `l1-01.1`, `l1-01.4`, `l1-03.1`, `l1-05.1`. ⚠ `l1-00` **avant tout le reste** :
   B1, M1 et la feature `models` sont toutes chez elle.
4. ⚠ **Conséquence de dispatch à anticiper** — le worktree d'un agent du Lot 0 coûtait
   **1 min 5 s et 696 Mo** (`CLAUDE.md`, drvfs sans liens durs, donc recopie intégrale).
   Avec la feature `models`, `l1-00`/O4 mesurera un ordre de grandeur au-dessus. Trois agents
   en parallèle deviendront coûteux en disque autant qu'en temps. **C'est le Résumé de
   `l1-00` qui donnera le chiffre — attendre qu'il soit là avant de fixer la largeur des
   vagues suivantes**, et non l'inverse.
5. **Rappel de la règle ⛔** — les cinq fiches de banc de N4 (`l1-04.2`, `l1-04.3a`,
   `l1-04.3b`, `l1-04.4`, `l1-05.2`) ne se dispatchent **jamais** en parallèle. Le critère
   habituel de `/run` (« fichiers disjoints ») les déclarerait sûres, et il aurait tort :
   elles se disputent les cœurs, qui sont la grandeur mesurée.

---

## Limite de cette revue

Elle est **solo et non adversariale** : aucun réfuteur n'a repris mes findings, et je suis à
la fois celui qui les trouve et celui qui les exécutera. Sa force est ailleurs — elle est la
première à avoir **ouvert le code, lancé le linter et compté le corpus**. C'est ce qui
explique la forme de ses résultats : presque rien sur le fond des fiches, où trois revues
sont déjà passées, et tout sur leur rencontre avec le harnais, où personne n'était encore
allé.

**Non couvert, et déclaré** : la justesse des faits externes sur Clay et TerraMind (je n'ai
lu ni `claymodel/model.py` ni `terramind_vit.py` — la v1 et la v3 les ont vérifiés à la
source, je m'appuie sur elles) · le comportement réel du cache Actions · les temps de calcul,
qui sont l'objet du lot · la pertinence des seuils décisionnels, qui sont des arbitrages.

---

# Verdict du PO — contre-vérification et suite donnée (26/08/2026)

**Revue acceptée, douze corrections appliquées, avec trois amendements.** J'ai contre-vérifié
moi-même tout ce qui était mécanique : **sept affirmations sur sept sont exactes**.

| Affirmation | Contrôle PO |
|---|---|
| B1 — `S101` non exempté pour les scripts neufs | `pyproject.toml:133-138` : `"scripts/**" = ["T201"]` seul, `"scripts/smoke.py" = ["S101"]` nommément. **Exact** |
| m1 — `deptry src` seul | `justfile:97`, avec le commentaire qui l'explique. **Exact** |
| m2 — mypy couvre `scripts/` | `pyproject.toml:146` : `files = ["src", "tests", "scripts"]`, et `tests/test_smoke.py:5` affirme l'inverse. **Exact** |
| M6 — chargement à la collecte pytest | `tests/test_smoke.py:46` : `smoke = _load_smoke_module()` au niveau module. **Exact** |
| F1 — bornes par site | Recompté sur les 9 873 manifestes : **63 (B08) à 579 (B01)**, médiane 219 ; **49 à 563** après filtre. **Exact** |
| m4 — C08 au-dessus de 10 % | **119** chips, **14** au-dessus, 88 à ≤ 1 %, max 26,1. C02 : **126** dont **21**. **Exact** |
| 5 793 · 9 873 · 4 959 | **Exact**, recompté. |

## Trois amendements

1. **M1 — la règle est durcie.** La revue note qu'un `resolve()` sur chemin relatif « serait
   le même bug déguisé » mais laisse la conduite floue. Retenu : **`expanduser()`, puis
   ERREUR si le résultat n'est pas absolu** — pas de `resolve()` de rattrapage. Un `hf_home`
   relatif est une faute de configuration ; elle se signale, elle ne se répare pas en
   silence.
2. **B1 — le mode d'échec probable est nuancé.** La revue classe bloquant en invoquant la
   règle « trois tentatives puis fiche différée », donc cinq fiches perdues. En pratique un
   agent sèmera plutôt des `# noqa: S101` ou ira éditer `pyproject.toml` — bruit permanent,
   ou violation de zone. La correction et la priorité sont les mêmes ; c'est la
   dramatisation qui est nuancée.
3. **m4 — l'argument est chiffré.** « Sur 14 points, ce seuil s'atteint par accident » est
   juste et se quantifie : à **n = 14**, le `r` critique à 5 % vaut **≈ 0,53** — le seuil
   acté de 0,5 est **sous** le seuil de significativité. Avec C02 (**n = 35**), il tombe à
   **≈ 0,34** et redevient lisible. Le chiffre est écrit dans `l1-05.4`, `l1-05.3.H` et
   `l1-06.H`, avec une **règle de non-concluance sous 25 points**.

## Le trou de la revue, comblé

La revue a sondé **deux** mécanismes (`deptry` face aux extras, `assert` face à ruff) et
laissé le **troisième** — celui que le réfuteur v3 avait explicitement signalé comme reposant
sur ma seule parole, en notant qu'un `just install` d'essai coûtait une minute. Sondé le
26/08, dans la configuration exacte de `l1-00` (extra `models` + `claymodel @ git+…@commit`) :

- **sans** `allow-direct-references` → `ValueError: Dependency #1 of option 'models' of field
  'project.optional-dependencies' cannot be a direct reference…` — le build échoue ;
- **avec** → la wheel se construit, et la référence git est **confinée à l'extra** :
  `Requires-Dist: claymodel @ git+… ; extra == 'models'`, la ligne de base restant propre.

⭐ **Le témoin joue dans les deux sens, et il apporte une preuve que personne n'avait** : la
décision « la wheel du worker reste légère » est vérifiée, pas supposée — qui installe sans
l'extra n'hérite d'aucune dépendance git.

## ⭐ Un treizième défaut, trouvé en appliquant le critère « Prêt à faire »

Trouvé le 26/08, **après** la passe de correction, en confrontant `l1-00` à la clause
« **gate vert à son propre commit** » du critère de descente — et **sondé**, pas déduit.

`deptry` signale toute dépendance **déclarée mais non importée** :
`DEP002 '<paquet>' defined as a dependency but not used in the codebase`. Or `l1-00`
déclare torch, claymodel, terratorch et `huggingface_hub` **avant** que le moindre code ne
les importe — les adapters arrivent en `l1-02.x`. **À son propre commit, `l1-00` livrait un
`just deptry` rouge**, ce que le critère interdit explicitement.

Deux corrections, toutes deux vérifiées par sonde :

- `l1-00` pose `[tool.deptry.per_rule_ignores] DEP002 = [...]` sur les quatre paquets.
  ⭐ **Garde ciblée, témoin dans les deux sens** : avec elle, `deptry` est vert sur le
  paquet ignoré ; **et** un import non déclaré reste attrapé (`DEP003`). On suspend une
  règle sur quatre noms, on n'aveugle pas l'outil.
- Le bloc est **temporaire**, et son retrait a un propriétaire nommé : **`l1-02.3`**, la
  première fiche où les quatre paquets sont réellement importés depuis `src/` (O6).
- Au passage : `onnxruntime` se déclare **côté pixi seulement**. Importé uniquement depuis
  `scripts/bench_quant.py`, que `deptry src` ne scanne jamais, il serait sinon `DEP002`
  **à perpétuité**. C'est le précédent du Lot 0, déjà écrit dans le `justfile`.

*Ce que ce défaut dit de la méthode : le critère « Prêt à faire » n'est pas une formalité de
passage de dossier — il attrape ce que quatre revues n'avaient pas vu, à condition d'être
appliqué clause par clause **et** avec une sonde plutôt qu'un raisonnement.*

## Ce qui reste, et qui n'est pas de mon ressort

⛔ **Le report des trois exceptions de zone dans `CLAUDE.md`** (M4). La revue a raison de le
classer majeur, et elle voit un effet de bord que j'avais manqué : en fermant `CLAUDE.md` aux
fiches, j'ai fait que la seule issue est « signaler au Résumé », donc **après** le run —
alors que `l1-05.3a` rencontre la contradiction dès **N1**. C'est devenu un **prérequis de
dispatch**, écrit comme tel dans `_roadmap.md` §5bis ; le paragraphe prêt à coller est dans
`_revue-v3.md` §5.1.
