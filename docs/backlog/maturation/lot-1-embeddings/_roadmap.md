# Roadmap — Lot 1 : Banc d'embeddings GFM (v1, INDICATIVE — avant revue)

**Date** : 23/08/2026 · **Auteur** : architecte/PO · **Statut** : v1 posée avant revue
adversariale. **Rien n'est figé ici** : les efforts, le découpage et les arêtes du graphe
sont des propositions. La roadmap ne devient figée qu'après revue, et les fiches ne
descendent en `a-faire/` qu'après.

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

- **Modèles** : Clay v1.5 et **TerraMind small** (repli `tiny` si le CPU ne suit pas ;
  pas `base` — on cherche si l'approche tient, pas deux points de benchmark).
  **Licence TerraMind : Apache 2.0**, vérifiée sur la carte du modèle le 23/08/2026.
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
par l'expertise** → fiche `l1-05.4`. Et `l1-04.3` **chiffre le coût de la variante 4 tuiles
sur un échantillon**, sans la produire en masse.
⭐ **Couture architecturale** : la stratégie de découpage est un **champ de la spec**, pas
une hypothèse enfouie dans l'adapter, et le `spec_hash` entre dans la clé d'idempotence.
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
B08 et B07 tombent à ~25 mois couverts sur 48. À surveiller en `l1-05.3`.

**c. TerraMind → variante `small`.** Cf. §2. Deux pièges relevés sur la carte du modèle,
à lever par `l1-02.2` **avant** d'écrire du code : (1) l'exemple de référence est en
**224×224** quand notre chip fait 256 — nourrir Clay en 256 et TerraMind en 224 comparerait
des embeddings d'**emprises différentes** (5 120 m contre 4 480 m), ce qui invaliderait la
séparabilité ; vérifier si TerraMind accepte 256, sinon recadrer les deux et le documenter ;
(2) TerraMind rend **196 embeddings de patch (768-d)**, pas un vecteur — l'agrégation est à
la charge de l'adapter (cf. §4bis).

**d. Déterminisme → exigé à CONFIGURATION FIXÉE, mesuré entre configurations.**
Formulation corrigée en cours de cadrage : `l1-04.3` fait **varier** le nombre de threads
BLAS pour mesurer le passage à l'échelle — exiger le bit à bit sur tout le banc
contredirait ce levier. Donc : même modèle + mêmes threads + même entrée → **identité
exacte** (c'est ce dont l'idempotence a besoin) ; et **l'écart entre nombres de threads est
MESURÉ, pas exigé nul**. Ce chiffre est utile en soi : s'il n'est pas nul, le Lot 2 ne
devra pas comparer des vecteurs calculés à des moments différents sans le savoir.

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

## 4. Graphe (5 chapeaux · 20 sous-tâches agent · 1 fiche humaine)

⭐ **Grain du graphe (règle E-c du Lot 0, inchangée)** : seules les fiches **dispatchables**
ordonnent le run. Un chapeau a `depends_on: []` et n'ordonne rien. Une fiche **humaine**
porte un `depends_on` et bloque volontairement ses dépendants. Un `depends_on` est satisfait
**quand la fiche visée est en `fait/`**.

⭐ **Calibre** : une fiche = **une session d'agent Sonnet, effort medium**, sans question à
poser. Barème S ≤ 1 session · M ≤ 2-3 · L à scinder · XL interdit en `a-faire/`.

### O1 — Socle d'embedding · chapeau `l1-01`

| Fiche | Objet | Effort | `depends_on` |
|---|---|---|---|
| `l1-01.1` | `core/embedding.py` — spec de bandes, ordre, **normalisation radiométrique** depuis les `scale`/`offset` du manifeste. Pur, zéro I/O | S | — |
| `l1-01.2` | `adapters/chip_loader.py` — assemble le tenseur 10 bandes depuis `chip.tif` (4×512²) **et** `chip_20m.tif` (6×256²), rééchantillonnage explicite | M | `l1-01.1` |
| `l1-01.3` | Port `EmbeddingModel` (Protocol) + double de test substituable + registre `model_id → adapter` | S | — |
| `l1-01.4` | Corpus de **fixtures d'embedding** : N chips réels gelés, hors réseau — le pendant de `l0-03.5` | S | `l1-01.2` |

### O2 — Modèles & exécution · chapeaux `l1-02`, `l1-03`

| Fiche | Objet | Effort | `depends_on` |
|---|---|---|---|
| `l1-02.1` | Adapter **Clay v1.5** — poids, spec 10 bandes, sortie 1024-d | M | `l1-01.2`, `l1-01.3` |
| `l1-02.2` | Adapter **TerraMind** (via TerraTorch, variante à fixer) — **relever et consigner la licence** | M | `l1-01.2`, `l1-01.3` |
| `l1-02.3` | **Garde de contrat** : poids résolus depuis un cache local, JAMAIS de téléchargement au run ; recette de pré-chargement séparée | S | `l1-02.1` |
| `l1-02.4` | **Substituabilité prouvée** : le même code consomme les deux adapters, sans branche chez l'appelant | S | `l1-02.1`, `l1-02.2` |
| `l1-03.1` | Format de stockage des vecteurs + **clé d'idempotence** (`grid_hash` + `model_id` + `spec_hash`) | S | `l1-01.3` |
| `l1-03.2` | CLI **`embed`** — un site, une fenêtre. Idempotence, compteurs, codes de sortie du chapeau `l0-01` | M | `l1-03.1`, `l1-02.1` |
| `l1-03.3` | CLI **`embed-backfill`** — pool, reprise, interruption propre (patron de `l0-04.1`) | M | `l1-03.2` |
| `l1-03.4` | **Smoke `embed`** dans le gate — replay sur fixtures, hors ligne | S | `l1-03.2`, `l1-01.4` |

### O3 — Banc & qualité · chapeaux `l1-04`, `l1-05`

| Fiche | Objet | Effort | `depends_on` |
|---|---|---|---|
| `l1-04.1` | **Instrumentation** : chargement / forward / écriture chronométrés SÉPARÉMENT, RAM crête, sortie JSON | M | `l1-03.2` |
| `l1-04.2` | **Levier I/O** : drvfs (`/mnt/d`) vs ext4 local, même échantillon, écart chiffré | S | `l1-04.1` |
| `l1-04.3` | **Leviers modèle** : entrée 20 m seule vs 10+20 m · taille de batch · threads BLAS | M | `l1-04.1` |
| `l1-04.4` | **Levier quantification** : int8 / ONNX — mesuré, **ou déclaré non concluant avec sa raison** | M | `l1-04.1`, `l1-02.2` |
| `l1-04.5` | **Rapport de banc** : tableau comparatif + extrapolation chiffrée sur 5 793 chips ET sur une journée d'incrémental | M | `l1-04.2`, `l1-04.3`, `l1-04.4`, `l1-02.4` |
| `l1-05.1` | **Métriques pures** (cosinus, silhouette intra/inter) sur vecteurs synthétiques — testables à sec | S | — |
| `l1-05.2` | **Déterminisme** : identité exacte à configuration fixée · écart entre nombres de threads **mesuré** | S | `l1-03.2` |
| `l1-05.3` | **Campagne séparabilité** sur le corpus réel, rapport par modèle | M | `l1-05.1`, `l1-03.3` |
| `l1-05.4` | ⭐ **Trajectoire témoin** : A02 Hinkley Point C (chantier lourd, 48 mois) contre C08 Bouconne (zone témoin) — l'unité « un vecteur par chip » porte-t-elle le signal ? Et la corrélation embedding ↔ `cloud_pct` sur le site stable | M | `l1-05.3` |

### O4 — Décision · `l1-06.H`

| Fiche | Objet | Effort | `depends_on` |
|---|---|---|---|
| `l1-06.H` | ⛔ **HUMAIN** — arbitrage du périmètre embeddable au vu du banc, de la séparabilité et de la trajectoire témoin | H | `l1-04.5`, `l1-05.4` |

### Niveaux topologiques (dérivés des `depends_on` ci-dessus)

```
N0  l1-01.1 · l1-01.3 · l1-05.1
N1  l1-01.2 · l1-03.1
N2  l1-01.4 · l1-02.1 · l1-02.2
N3  l1-02.3 · l1-02.4 · l1-03.2
N4  l1-03.3 · l1-03.4 · l1-04.1 · l1-05.2
N5  l1-04.2 · l1-04.3 · l1-04.4 · l1-05.3
N6  l1-04.5 · l1-05.4
N7  ⛔ l1-06.H
```

**Profondeur 8, largeur moyenne 2,6.** Un seul gate humain, en feuille — **les 21 fiches
agent s'enchaînent sans intervention**. Feuilles : `l1-02.3`, `l1-03.4`, `l1-06.H` — les deux
premières sont des garde-fous terminaux, c'est légitime, mais à relire en revue.

### 4bis. Ce que le port doit absorber

Les deux modèles n'ont **pas le même contrat de sortie** : Clay rend **un vecteur** (son
embedding de classe), TerraMind rend **196 embeddings de patch** à agréger soi-même. Le port
`EmbeddingModel` promet « **un vecteur par chip** » ; chaque adapter est responsable de le
produire — Clay prend son CLS, TerraMind moyenne ses patchs. **L'appelant ne voit pas la
différence.**

⚠ À écrire dans la fiche plutôt qu'à laisser découvrir en revue : comparer un embedding CLS
à une moyenne de patchs **n'est pas une comparaison parfaitement équitable** au sens
scientifique. C'est en revanche ce qu'on utiliserait en production, donc la bonne comparaison
**pour nous**. De même, TerraMind est **multimodal** et sera utilisé en mono-modalité S2 :
s'il discrimine moins bien que Clay, cela ne prouvera pas qu'il est moins bon — seulement
qu'on l'utilise à moitié.

## 5. Pièges identifiés (à mesurer, pas à supposer)

1. **Le chargement peut dominer le forward.** Deux rasters, deux résolutions, un
   rééchantillonnage : si les trois temps ne sont pas séparés, on attribuera au GFM un coût
   qui est celui de l'I/O. C'est la raison d'être de `l1-04.1`, et elle précède tous les
   leviers.
2. **drvfs.** ~16 Gio à lire à travers un montage Windows. Le Lot 0 a déjà payé cette taxe.
3. **Le chiffre publié par Clay (~20 embeddings/s) vient d'AWS**, pas d'un CPU de poste. Il
   ne doit apparaître nulle part comme référence de comparaison.
4. **Un oracle de déterminisme fixé après la mesure ne prouve rien.** La tolérance se fixe en
   amont (question ouverte n°4).
5. **Le poids des modèles ne doit jamais se télécharger au run** — sinon le gate devient
   dépendant du réseau et le banc mesure la bande passante. Garde vérifiée par mutation.
6. **Zones partagées** : `pyproject.toml` → `l1-01.1` seule (dépendances pré-posées, patron
   du Lot 0) · `justfile` → `l1-02.3` (pré-chargement) puis `l1-03.4` (smoke) ·
   `tests/fixtures/` → `l1-01.4` seule.

## 6. Ce qui n'est PAS dans ce lot

pgvector et l'indexation (Lot 2) · la détection de changement (Lot 2) · l'entraînement ou le
fine-tuning (hors POC) · le GPU (pas de matériel) · Sentinel-1, la fusion multimodale, le
recalage sub-pixel.
