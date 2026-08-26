# Roadmap — Lot 1 : Banc d'embeddings GFM (v5, post-revues v1 à v4)

**Date** : 26/08/2026 · **Auteur** : architecte/PO · **Statut** : **v5, corrigée des 12
issues de la revue v4** — la revue de l'**équipe d'implémentation**, la première à avoir
ouvert le code, lancé le linter et **recompté le corpus** (cf. `_revue-v4.md`). Après la v3
(32 clusters, 6 angles dont l'ancrage, plus réfutation — `_revue-v3.md`,
`_revue-v3-refutation.md`), la v1 (24 clusters, `_revue.md`) et la v2 externe (5 findings,
`_revue-v2.md` — dont B1, le gate avec poids → fiche `l1-07`).
Arbitrages Philippe A-D intégrés, plus les décisions du 25/08 : **zones d'écriture** et
**pas de seuil de passage sur le déterminisme entre threads**. Les fiches restent en
maturation jusqu'au GO de descente.

**Ce que la v3 a changé de structurel** : `l1-07` passe **devant `l1-02.1`** (le gate charge
des poids dès `just test`, pas au smoke) · `l1-05.3a` redescend de **N4 à N1** (elle ne
consomme que le format des vecteurs) · le **protocole de stabilité** et l'**échantillon de
banc** remontent chez `l1-04.1` · les cinq fiches de banc de N4 sont déclarées **non
parallélisables** · l'oracle temporel de Clay était **faux** (vérifié au code source).

**Ce que la v4 a changé** — rien de structurel, **le graphe est inchangé** ; douze
corrections locales, toutes nées de la rencontre des fiches avec le **harnais réel** :
`l1-00` pré-pose l'exemption `S101` sans laquelle cinq fiches de banc rendraient `just lint`
rouge · l'expansion de `~` a enfin un mécanisme nommé (`_PATH_FIELDS`) et un oracle ·
l'atomicité porte désormais sur la **paire** `.npy`+`.json` · `scl_summary` change de forme
(son oracle contredisait sa définition) · l'import de l'adapter dans le smoke doit être
**paresseux** · et **un chiffre était faux** : 63-579 chips par site, pas 43-300.
⭐ Deux mécanismes du socle sont désormais **sondés, dans les deux sens** : `deptry` face aux
extras (revue v4) et **`hatchling` face à la référence git** (sonde PO du 26/08).

**Source du lot** : [`docs/lots/lot-1-embeddings.md`](../../../lots/lot-1-embeddings.md).

---

## 1. Ce que ce lot doit trancher

Pas un achat — **un périmètre**. Combien de chips, de sites et de mois sont embeddables sur
la machine existante, et quels leviers permettent d'en embedder plus avant de renoncer.

Deux conséquences qui traversent tout le chantier :

- le critère de comparaison des modèles est **le pouvoir discriminant par seconde de CPU**,
  pas le débit seul ni la qualité seule — d'où O3 qui porte les deux ;
- le banc doit **mesurer des leviers**, pas seulement constater une lenteur. Quatre sont
  identifiés (I/O, résolution d'entrée, batch/threads, quantification) ; chacun a sa fiche,
  chacun rend un chiffre ou une raison motivée de ne pas conclure.

## 2. Décisions actées (ne pas rouvrir)

- **Modèles** : Clay v1.5 (⚠ de facto **large** — seule variante publiée, ~302 M params
  d'encodeur) et **TerraMind small** (~21 M ; repli `tiny` = point d'arbitrage de
  `l1-06.H`). ⭐ **L'asymétrie est subie et déclarée** (réfuteur K-01bis) : rapport de coût
  attendu ~50×, dominé par la taille de modèle autant que par les tokens (1024 contre 256).
  Licences : **apache-2.0 pour les deux**, vérifiées à la source (API HF + cartes).
- **CPU seul.** Pas de GPU sur la machine, **pas d'achat prévu** — le lot décide d'un
  périmètre, pas d'une dépense.
- **Stockage fichier.** pgvector ouvre le Lot 2, il n'entre pas ici.
- **Corpus** : `D:\datas\tiny-wae`, local — 5 793 chips, 9 873 manifestes.
- **Aucune détection de changement**, aucun entraînement.

### 2bis. Les quatre questions de cadrage, TRANCHÉES le 23/08 (Philippe)

**a. Unité d'embedding → UN vecteur par chip, entrée montée en 20 m.**
Les 10 bandes vivent sur deux grilles : 4 à 10 m (512²) et 6 à 20 m (256²). Tout ramener à
20 m donne un tenseur 256×256×10, soit **exactement une tuile Clay** — le montage le moins
cher coïncide avec l'unité annoncée depuis le début. Tout monter à 10 m donnerait 512×512,
soit **4 tuiles Clay** et 4× le calcul.
⚠ **Le vrai risque n'est pas la localisation, c'est la sensibilité** : un vecteur unique
couvre 26 km² ; une halle de 200 m, c'est 0,15 % de la scène. Si le signal se noie, on
mesurera de la dérive saisonnière et rien d'autre. **Ce doute est levé par la mesure, pas
par l'expertise** → fiche `l1-05.4`. Et `l1-04.3a` **chiffre le coût de la variante 4 tuiles**
(4 forwards 256² synthétiques contre 1 — jamais un forward 512², qui mesurerait ~16×,
revue K-11), sans la produire en masse.
⭐ **Couture architecturale** : la stratégie de découpage est un **champ de la spec**, pas
une hypothèse enfouie dans l'adapter, et le `spec_hash` entre dans la clé d'idempotence
**et dans le nom du fichier** — c'est cette seconde moitié qui rend la variante réversible :
une nouvelle spec écrit **à côté**, jamais par-dessus (`l1-01`, `l1-03.1`).
Produire l'autre variante plus tard **n'invalide rien** — ça ajoute des vecteurs à côté.
Changer d'avis coûte du CPU, pas une refonte.

**b. Masque SCL → PAS de masque. Seuil d'entrée à 10 %. Tout consigner.**
Mesuré sur les 9 873 manifestes (grandeur exacte : un manifeste par `item_id`, donc immunisée
au défaut `rep-01` qui touche les agrégats de compteurs) :

| `cloud_pct` des chips ingérés | valeur |
|---|---|
| médiane · p75 · p90 | **0,0 %** · 3,3 % · 14,8 % |
| ≤ 1 % | 3 788 chips (65 %) |
| ≤ 10 % | 4 959 chips (**86 %**) |
| entre 20 et 30 % | 356 chips (6 %) |

Le seuil d'ingestion à 30 % est une porte large que presque personne ne franchit :
**masquer des pixels serait un outil lourd pour un chip sur sept**, et remplacer des pixels
présente aux GFM une distribution qu'ils n'ont jamais vue. On serre donc le filtre à
l'entrée de l'embedding — `embed_cloud_pct_max: 10` **dans `settings.yaml`, pas une
constante** — et on écrit `cloud_pct` + le résumé SCL dans le compagnon de chaque vecteur,
pour que le Lot 2 puisse pondérer quand il aura le contexte.
⚠ Le coût n'est pas le nombre de chips mais la **couverture temporelle**, très inégale :
B08 et B07 tombent à ~25 mois couverts sur 48. À surveiller en `l1-05.3a`.

**c. TerraMind → variante `small`, entrée 256 ACTÉE.** La revue a tranché les deux pièges
à la source : **256×256 est accepté** (pos-emb interpolés → 256 tokens) — la question 224
n'existe plus, le verdict est consigné par `l1-00` ; et la sortie est **384-d en liste de
12 tenseurs** (la carte HF qui annonce `(B, 196, 768)` est fausse — copier-coller de la
variante base) : l'agrégation `out[-1].mean(dim=1)` est écrite dans `l1-02.2`, car
`merge_method='mean'` moyenne les modalités, pas les patchs.

**d. Déterminisme → exigé à CONFIGURATION FIXÉE, mesuré entre configurations.**
Formulation corrigée en cours de cadrage : `l1-04.3b` fait **varier** le nombre de threads
BLAS pour mesurer le passage à l'échelle — exiger le bit à bit sur tout le banc
contredirait ce levier. Donc : même modèle + mêmes threads + même entrée → **identité
exacte** (c'est ce dont l'idempotence a besoin) ; et **l'écart entre nombres de threads est
MESURÉ, pas exigé nul**. Ce chiffre est utile en soi : s'il n'est pas nul, le Lot 2 ne
devra pas comparer des vecteurs calculés à des moments différents sans le savoir.

### 2ter. Seuils décisionnels ACTÉS (arbitrage Philippe, revue C-17/K-15)

- **Séparabilité** : silhouette **> 0,2** sur au moins un modèle, lue **contre la baseline
  triviale** (moyenne + σ par bande — 20 nombres) publiée à côté : un GFM qui ne bat pas la
  baseline n'apporte rien, quel que soit son score absolu.
- **Trajectoire** : dérive = `1 − cosine` ; rapport A02/C08 = **médiane des 6 derniers
  mois** ; **> 2** viable · 1–2 douteux · ≤ 1 non viable.
- **Fidélité de quantification** : min de similarité **≥ 0,999** retenable ·
  0,99–0,999 douteux (remonté) · < 0,99 écarté.
- **Corrélation nuage** : |r| > 0,5 **sur la plage complète** (chips à 30 %, filtre
  d'embedding désactivé pour la mesure — revue K-14) → seuil de 10 % insuffisant, remonté.

Les fiches **publient et qualifient** contre ces seuils ; seule `l1-06.H` **prononce** —
un seuil raté est un résultat majeur, jamais un blocage de run.

## 3. ⭐ Politique de test du lot — proportionnée, c'est un POC

**Constat mesuré sur le Lot 0** : **8 413 lignes de tests pour 4 074 lignes de source,
ratio 2,07×** ; `test_contact_sheet.py` fait **5,8×** son module ; `test_logging.py` pèse
659 lignes pour du journal, qui n'est pas le produit. Le mot « mutation » apparaît dans
**26 fichiers**. **Décision Philippe du 23/08 : ne pas reproduire ce travers.**

⚠ **Ce que ce constat dit, et ce qu'il ne dit pas.** Le problème n'est pas le volume : c'est
**ce qui a été testé**. 659 lignes sur le journal, de la machinerie de mutation permanente
là où une vérification ponctuelle suffisait. Un module difficile mérite tous les tests qu'il
faut — le ratio n'est pas un objectif à atteindre par le bas.

Règles du Lot 1 :

1. **Le `core/` pur est là où les tests rendent le plus** — normalisation radiométrique,
   spec de bandes, métriques de séparabilité : c'est là que se cachent les vraies erreurs de
   calcul, et ça se teste à sec en millisecondes. Les adapters et les CLIs se testent aussi,
   mais sur leurs **invariants** (conservation, idempotence, codes de sortie), pas sur leurs
   détails.
2. **UN seul smoke** traversant la chaîne réelle sur 2-3 chips fixtures. Il remplace une
   dizaine de tests d'intégration.
3. **Aucun test sur les valeurs d'embedding.** On n'asserte pas 1024 flottants. Ce qui se
   teste : la **forme** (dimension, dtype, absence de NaN) et le **déterminisme**.
4. ⭐ **Vérification par mutation ≠ test de mutation.** Casser une garde une fois pour voir
   si elle mord est un **geste ponctuel, consigné en une ligne de prose** dans le Résumé de
   réalisation. En faire une machinerie permanente coûte plus cher que ce qu'elle protège.
   *Corollaire appliqué à la garde réseau : on ne la teste pas, on met le **smoke sous la
   garde** — elle est alors exercée à chaque `just check`, gratuitement.*
5. **Aucun test dont l'oracle est « ça ne plante pas ».** Un test doit pouvoir devenir
   rouge pour une raison qu'on sait nommer.

⚠ **Pas de quota, ni plancher ni plafond.** Ces règles disent *ce qui* mérite d'être testé,
jamais *combien* de tests ou de lignes écrire. Un module retors mérite dix tests, un module
trivial en mérite un — c'est le jugement de l'implémenteur, pas une cible chiffrée. Le
travers du Lot 0 n'était pas le volume en soi, c'était de tester ce qui ne le méritait pas.

## 4. Graphe (5 chapeaux · 24 fiches agent · 2 fiches humaines) — v4, corrigé

⭐ Règles inchangées (E-c du Lot 0) : seules les fiches dispatchables ordonnent le run ;
un chapeau a `depends_on: []` ; une fiche humaine bloque volontairement ; un `depends_on`
est satisfait quand la fiche visée est en `fait/`. ⚠ **Le dispatch est GLOUTON** : les
niveaux ne gouvernent rien, seuls les `depends_on` protègent — c'est pourquoi les revues
ont ajouté 12 arêtes que « les niveaux qui tombaient juste » masquaient.

### O1 — Socle · `l1-01` (+ les fiches à plat `l1-00` et `l1-07`)

| Fiche | Objet | Effort | `depends_on` |
|---|---|---|---|
| `l1-00` | Socle d'inférence : dépendances, cache `~/.cache`, fetch-models, check_cache | **M** | — |
| `l1-07` | ⭐ Gate avec poids — cache CI + défaut versionné pour les worktrees | S | `l1-00` |
| `l1-01.1` | Ordre normatif (celui de Clay), spec, `spec_hash`, `validate_spec` | S | — |
| `l1-01.2` | `ChipTensor` complet (DN, lat/lon, gsd=20, `scl_summary`) | M | `l1-01.1`, `l1-01.4` |
| `l1-01.3` | Port `embed(chip)` + registre table pré-posée, imports paresseux | S | `l1-01.1` |
| `l1-01.4` | 4 fixtures réelles gelées | S | — |

### O2 — Modèles & exécution · `l1-02`, `l1-03`

| Fiche | Objet | Effort | `depends_on` |
|---|---|---|---|
| `l1-02.1` | Adapter Clay (masque 0, datacube, z-score DN, CLS 1024) | M | `l1-00`, **`l1-07`**, `l1-01.2`, `l1-01.3` |
| `l1-02.2` | Adapter TerraMind (384-d, agrégation explicite, table de noms) | M | `l1-00`, **`l1-07`**, `l1-01.2`, `l1-01.3` |
| `l1-02.3` | Garde `HF_HUB_OFFLINE` posée par le code de production | S | `l1-02.1`, `l1-02.2` |
| `l1-02.4` | Substituabilité (1024/384/double), grep mécanisé | S | `l1-02.1`, `l1-02.2` |
| `l1-03.1` | Stockage `<model_id>.<spec_hash[:8]>.npy` + `VectorMeta` unique | S | — |
| `l1-03.2` | CLI `embed` — idempotence, filtre + précédence, `.error.json` rejoué | M | **`l1-00`**, `l1-01.2`, `l1-01.3`, `l1-01.4`, `l1-03.1` |
| `l1-03.3` | CLI `embed-backfill` — `embed_workers`, ThreadPool, SIGINT après jalon | M | `l1-03.2` |
| `l1-03.4` | Smoke sous la garde + `tests/test_smoke.py` au périmètre | S | `l1-03.2`, `l1-01.4`, `l1-02.3` *(l1-07 devenu transitif)* |

### O3 — Banc & qualité · `l1-04`, `l1-05`

| Fiche | Objet | Effort | `depends_on` |
|---|---|---|---|
| `l1-04.1` | Instrumentation 3 phases + ⭐ **protocole de stabilité et échantillon gelé** | M | `l1-03.2` |
| `l1-04.2` | ⛔ Levier I/O drvfs/ext4, alternances lisibles dans le JSON | S | `l1-04.1`, **`l1-02.4`** |
| `l1-04.3a` | ⛔ Levier résolution — **coût absolu**, pas le ratio tautologique — + batch | M | `l1-04.1`, `l1-02.4` |
| `l1-04.3b` | ⛔ Levier threads + contention, threads relevés **depuis un worker** | **M** | `l1-04.1`, `l1-02.4`, `l1-03.3` |
| `l1-04.4` | ⛔ Levier quantification, plancher figé, feature `bench` **pré-posée** | M | `l1-04.1`, `l1-02.4` |
| `l1-05.1` | Métriques pures — silhouette **sur distance 1−cos**, dérive=1−cos | S | — |
| `l1-05.2` | ⛔ Déterminisme — rouge **déclaré**, barème 3 états, `min_detectable` | S | `l1-03.2`, `l1-02.4` |
| `l1-05.3a` | CLI `similarity-report` **`.md`+`.json`**, baseline, invariants refaits | M | `l1-05.1`, **`l1-03.1`** |
| `l1-05.3.H` | ⛔ Campagne : sous-échantillon (`--out` distinct), complet, `campaign.json` | H | `l1-05.3a`, `l1-04.3b`, **`l1-03.3`** |
| `l1-05.4` | Trajectoires A02/C08, témoins nommés, corrélation plage complète | M | `l1-05.3.H` |
| `l1-04.5` | Rapport : comparatif, extrapolations ×2, **ratio discrimination/s** | M | `l1-04.2`, `l1-04.3a`, `l1-04.3b`, `l1-04.4`, `l1-05.3.H` |

### O4 — Décision · `l1-06.H`

| Fiche | Objet | Effort | `depends_on` |
|---|---|---|---|
| `l1-06.H` | ⛔ Arbitrage : modèle, périmètre, leviers, unité, nuages, déterminisme, tiny, **garde du smoke** | H | `l1-04.5`, `l1-05.4`, `l1-05.2` |

⚠ **`l1-05.2` peut arriver en rouge, et c'est voulu** : sa clause « pas terminable » créait
un interblocage (l'arbitre dépend d'elle). Elle se termine désormais en **rouge déclaré**,
et c'est le point 6 de `l1-06.H` qui devient bloquant **pour la recette**, pas pour le run.

### Niveaux topologiques (dérivés des `depends_on` ci-dessus)

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

**Profondeur 8, largeur moyenne 26/8 = 3,25** *(recalculé depuis les frontmatters après la
revue v3 — l'ancien « ~3,1 » était faux)*. Deux gates humains — la campagne (N5) et
l'arbitrage (N7) — comme au Lot 0 (`l0-03.H`, `l0-04.H`) : **22 fiches agent s'enchaînent
sans intervention jusqu'à la campagne**, puis deux fiches agent terminales (`l1-04.5`,
`l1-05.4` — elles sont **après**, pas avant), puis l'arbitrage.

⚠ **Il n'y a pas « un » chemin critique** (revue v3, S-13/D-12 — le chemin publié
jusqu'ici passait par une arête `l1-02.4 → l1-04.1` qui **n'existe pas**, et l'énumération
exhaustive donne **48** chaînes maximales de longueur 8, pas trois). Ce qui commande le
calendrier, ce sont les **goulots** :

1. **`l1-05.3.H`** (N5, humain) — la campagne : tout N6 l'attend, et elle-même attend que
   les modèles, le backfill et le réglage de `l1-04.3b` soient là ;
2. **`l1-04.5` et `l1-05.4`** (N6) — les deux rapports décisionnels ;
3. **`l1-06.H`** (N7) — l'arbitrage, feuille du graphe.

⛔ **Règle de dispatch — les cinq fiches de banc de N4 ne se parallélisent pas** (revue v3,
E-8). `l1-04.2`, `l1-04.3a`, `l1-04.3b`, `l1-04.4` et `l1-05.2` mesurent toutes du **temps
CPU** : les lancer ensemble, c'est mesurer la contention qu'on a créée soi-même. Le critère
habituel de `/run` (« zones de code disjointes ») ne protège **pas** ici — leurs fichiers
*sont* disjoints, et il les déclarerait donc sûres. Trois garde-fous, sans nouvel outillage :

- la règle générale de `_tools/CLAUDE.md` — **un seul agent d'implémentation à la fois** —
  suffit si elle est tenue ; ces cinq fiches sont le cas où elle n'est pas négociable ;
- chacune porte un **bandeau ⛔** en tête de fiche ;
- chaque JSON de banc porte un champ **`concurrent_load`** : si la règle a été enfreinte,
  la mesure reste **lisible comme suspecte** au lieu d'être silencieusement fausse.

### 4bis. Ce que le port doit absorber

Clay rend **un CLS 1024-d** ; TerraMind rend **une liste de 12 tenseurs `(B, 256, 384)`**,
agrégée par l'adapter (`out[-1].mean(dim=1)`). Le port promet « un vecteur par chip » via
`embed(chip: ChipTensor)` — l'appelant ne voit pas la différence. ⚠ Écrit dans les fiches :
comparer un CLS à une moyenne de patchs n'est pas parfaitement équitable au sens
scientifique — c'est en revanche ce qu'on utiliserait en production, donc la bonne
comparaison pour nous ; et TerraMind, multimodal utilisé en mono-modalité S2, part
handicapé — un score inférieur ne prouverait pas qu'il est moins bon.

## 5. Pièges identifiés (v2 — mesurés ou vérifiés à la source)

1. **Le chargement peut dominer le forward** — d'où `l1-04.1` avant tous les leviers.
2. **drvfs** : ~16 Gio à lire à travers un montage Windows (`l1-04.2`).
3. ⚠ **Les documentations publiques des deux modèles sont fausses ou non exécutables**
   (revue K-01/K-02) : carte HF TerraMind fausse sur la forme de sortie, quickstart Clay
   non exécutable, masque à 75 % par défaut en inférence. **Les fiches d'adapter portent la
   recette vérifiée au code source — la suivre, ne pas « corriger » depuis la doc.**
4. **Un oracle de déterminisme ou de fidélité fixé après la mesure ne prouve rien** — tous
   les seuils sont actés en §2ter.
5. **Aucun poids ne se télécharge au run** — trois artefacts, une seule garde (`l1-00`,
   `l1-02.3`), le smoke dessous.
6. **Zones partagées (v3 — table de propriété exclusive)** :

   | Fichier / répertoire | Propriétaire unique | Note |
   |---|---|---|
   | `pyproject.toml` · `pixi.lock` · `.gitignore` | **`l1-00`** | y compris la feature `bench` (onnxruntime) que `l1-04.4` consomme sans l'écrire, et l'extension de `test_packaging.py` aux extras |
   | `config/settings.yaml` · `config_io._INT_FIELDS` **et `_PATH_FIELDS`** | **`l1-00`** | ⭐ **les 3 clés sont PRÉ-POSÉES** (`hf_home`, `embed_cloud_pct_max`, `embed_workers`) ; `l1-03.2` et `l1-03.3` **consomment**. Plus d'écriture séquentielle à trois — le patron « table pré-posée », comme pour le registre. `_PATH_FIELDS` est neuf (revue v4, M1) : le Lot 0 n'avait aucun champ-chemin à expanser |
   | `justfile` | **`l1-00`** | recette `fetch-models`, hors gate |
   | `.github/workflows/` · `.env.example` | **`l1-07`** | zone **actée équipe** le 25/08 (précédent : codeql, Dependabot) |
   | `adapters/model_registry.py` | **`l1-01.3`** | table pré-posée à 3 entrées ; les adapters n'écrivent que leur fichier |
   | `scripts/smoke.py` **et `tests/test_smoke.py`** | **`l1-03.4`** | ⭐ le test était absent de cette table — il rejoue `smoke.main()` sous pytest (revue v3, A-4) |
   | `scripts/check_cache.py` | **`l1-00`** | versionné ; consommateur des oracles de `l1-07` |
   | `tests/fixtures/embed/` | `l1-01.4` | |
   | `tests/fixtures/vectors/` | **`l1-05.3a`** | vecteurs **fabriqués** — le répertoire n'avait aucun propriétaire (revue v3, S-15) |
   | `tests/fixtures/reports/` | `l1-04.5` | JSON de fixture des rapports, disjoint du précédent |
   | `docs/lots/lot-1/` | **création par `l1-05.3a`**, dépôts par `l1-04.5` et `l1-05.4` | zone **ouverte à l'équipe en création** le 25/08 ; le reste de `docs/lots/` demeure zone PO |
   | `README.md` · `CLAUDE.md` | ⛔ **fermés** | `l1-02.3` et `l1-07` **rédigent** leur ligne au Résumé ; Philippe la reporte |
7. **La contention workers × threads** se mesure (`l1-04.3b`), ne se devine pas — le 6 du
   Lot 0 était calibré pour un goulot réseau.
8. ⭐ **Le harnais est le dernier endroit où les fiches cassent** (revue v4). Trois pièges
   qui ne se voient qu'en exécutant : `assert` dans `scripts/` déclenche **S101** (cinq
   oracles l'exigent — `l1-00` pré-pose l'exemption) · **`mypy --strict` couvre
   `scripts/`**, « script de mesure » ne dispense de rien · `tests/test_smoke.py` charge
   `scripts/smoke.py` **à la collecte pytest**, donc l'import d'un adapter en tête de
   fichier se paie à chaque `just test` (`l1-03.4` : import paresseux).

## 5bis. ⛔ Prérequis de dispatch — à faire AVANT le premier agent

Quatre gestes, **dans cet ordre**. Aucun n'est optionnel.

1. ✅ **Zones d'écriture portées dans `CLAUDE.md`** — *fait le 26/08* (revue v4, M4).
   `CLAUDE.md` disait encore « l'équipe d'implémentation écrit dans `src/`, `tests/`,
   `scripts/` », et il précise de lui-même que **ses instructions priment** : un agent
   consciencieux — celui qu'on veut — aurait lu la contradiction avec `docs/lots/lot-1/` et
   fait ce que la méthode prescrit alors, **signaler plutôt qu'écrire**. Or `l1-05.3a` est
   en **N1**. Les quatre exceptions actées : `.github/`, `config/`, `.env.example`, et la
   **création** sous `docs/lots/<lot>/` ; `README.md` et `CLAUDE.md` restent **fermés**.
2. ⛔ **COMMITER les fiches — avant la sonde, et c'est le geste qu'on oublie.**
   Un worktree se crée depuis une **référence git** : il ne contient **jamais** l'arbre de
   travail. Avec `worktree.baseRef: "head"` (réglage en place), la base est le **dernier
   commit local** — pas les fichiers modifiés. Mesuré le 26/08 : `HEAD` = `cfd09cb`, le
   commit d'**ouverture** du chantier, avec **52 fiches modifiées non commitées**. Un agent
   dispatché dans cet état lirait le Lot 1 sans `l1-00`, sans `l1-07`, sans les corrections
   des revues v3 et v4 — c'est-à-dire l'inverse de ce qu'on vient de faire.
   ⚠ **Et la sonde ne l'attraperait pas** : elle vérifie que le worktree est sur le HEAD
   **attendu**, pas que ce HEAD **contient** ce qu'on croit. Les deux contrôles sont
   complémentaires, dans cet ordre.
   *(Le `push` n'est nécessaire que si `baseRef` vaut `fresh` — la base est alors le ref
   distant. Avec `"head"`, commiter suffit.)*
3. ⛔ **La sonde de worktree** (`CLAUDE.md` § « Worktrees d'agents » ; checklist opérationnelle
   dans `.claude/commands/run.md`) : un agent trivial en `isolation: "worktree"` qui rapporte
   `pwd` et `git rev-parse --short HEAD`, comparé au HEAD attendu. 30 secondes en lecture
   seule ; on ne dispatche pas sans.
   ⭐ **Pourquoi elle est un prérequis et pas une précaution** : la défaillance qu'elle
   prévient est **silencieuse et passe le gate**. Un agent sur une base périmée lit une
   version antérieure de **sa propre fiche**, code contre elle, et livre quelque chose de
   cohérent — donc `just check` est **vert**. C'est arrivé au run N0 : code livré amputé
   d'un champ, gate au vert. Lint, types, tests et smoke vérifient tous que le code est
   conforme à *une* spec ; **aucun** ne vérifie que c'est la **bonne**. Et les deux réglages
   (`git remote set-head`, `worktree.baseRef`) sont **invérifiables par lecture** — le
   second n'est lu qu'au **démarrage de session**, ce qui a déjà fait conclure à tort qu'il
   était inopérant.
4. ⭐ **`l1-00` avant tout le reste, seule.** Elle porte le bloquant de la revue v4
   (exemption `S101`), son majeur le plus vicieux (expansion de `~`), la feature `models`,
   la feature `bench` et `allow-direct-references` : cinq choses dont dépend le vert des
   autres. ⚠ **Son O4 mesure le coût d'installation de la feature `models` par worktree** —
   le Lot 0 payait déjà 1 min 5 s et 696 Mo par worktree (drvfs sans liens durs, recopie
   intégrale). **Attendre ce chiffre avant de fixer la largeur des vagues suivantes**, pas
   l'inverse.

## 6. Ce qui n'est PAS dans ce lot

pgvector et l'indexation (Lot 2) · la détection de changement (Lot 2) · l'entraînement ou le
fine-tuning (hors POC) · le GPU (pas de matériel) · Sentinel-1, la fusion multimodale, le
recalage sub-pixel.
