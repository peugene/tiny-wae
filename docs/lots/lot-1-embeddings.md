# Fiche Lot 1 — Banc d'embeddings GFM sur CPU

**Projet** : tiny-wae — POC Earth Intelligence perso
**Statut** : maturation — ouvert le 23/08/2026 ; **quatre revues passées, corrections appliquées** — v1 adversariale du 24/08 (116 findings, 24 clusters, `_revue.md`), v2 externe du 24/08 (5/5 confirmés dont le gate avec poids, `_revue-v2.md`), v3 du 25/08 à 6 angles dont l'ancrage dans le code (117 findings, 32 clusters, réfutation indépendante, `_revue-v3.md`), **v4 du 26/08 par l'équipe d'implémentation** — la première à ouvrir le code, lancer le linter et recompter le corpus : 12 issues dont 1 bloquante, et **1 chiffre faux** (`_revue-v4.md`). Prêt pour la descente en `a-faire/`, sous réserve des **prérequis de dispatch** (roadmap §5bis)
**Date** : 23/08/2026. Déclinaison opérationnelle : chantier `docs/backlog/maturation/lot-1-embeddings/`

Poser la colonne vertébrale technique du POC — **un embedding par site et par acquisition** —
et mesurer ce que la machine actuelle permet d'en faire. Le lot livre deux adapters de modèles
de fondation géospatiaux, un CLI d'embedding idempotent, un banc de mesure instrumenté, et un
premier signal de qualité. Il se conclut par un arbitrage humain de périmètre.

## Objectif

Le Lot 0 a produit **5 793 chips** sur 25 sites et 48 mois (15,95 Gio). Ces chips ne sont
pour l'instant que des images. Le Lot 1 les transforme en **vecteurs** : c'est ce qui rend
possible, aux lots suivants, la détection de changement (dérive d'embeddings), la recherche
par similarité et l'interrogation en langage naturel.

⭐ **Ce que ce lot doit trancher a changé de nature.** La feuille de route disait « le banc
décide de l'achat matériel ». **Décision Philippe du 23/08 : il n'y aura pas d'achat, on fait
avec la machine existante.** Le banc ne décide donc plus d'une dépense, il décide d'un
**périmètre** : combien de chips, de sites et de mois sont embeddables dans le temps
disponible, et quels leviers permettent d'en embedder plus avant de renoncer à quoi que ce
soit.

**Corollaire, qui oriente tout le lot** : le critère de choix d'un modèle n'est plus « le
meilleur » mais **le plus de pouvoir discriminant par seconde de CPU**. Un banc qui ne
mesurerait que le débit n'aurait pas de numérateur — c'est pourquoi la séparabilité entre en
O3, et non au Lot 2.

## Périmètre

**Dans le lot** :

- un **contrat d'entrée** commun aux modèles : ordre des bandes, normalisation radiométrique
  (les `scale`/`offset` par asset sont au manifeste depuis l'arbitrage n°1 du Lot 0),
  assemblage du tenseur depuis les **deux** rasters ;
- deux **adapters** derrière un port unique : **Clay v1.5** et **TerraMind small** ;
- un **CLI `embed`** idempotent et son backfill, sur le modèle des CLIs du Lot 0 ;
- un **stockage fichier** des vecteurs (pas de base) ;
- un **banc instrumenté** : chargement / forward / écriture chronométrés séparément, RAM
  crête, et quatre leviers chiffrés ;
- un **signal de qualité** : séparabilité inter-sites, stabilité et déterminisme.

**Hors lot** (explicite — c'est ce qui protège du glissement) :

- **pgvector** et toute indexation : c'est l'index de recherche, il ouvre le Lot 2. Le banc
  écrit dans des fichiers, ce qui suffit à mesurer et à alimenter la suite ;
- **toute détection de changement** — Lot 2 ;
- **tout entraînement ou fine-tuning** — hors périmètre du POC entier ;
- **le GPU** : la machine n'en a pas, le banc mesure ce qui existe ;
- **Sentinel-1**, la fusion multimodale, le recalage sub-pixel.

## Décisions structurantes actées

| Décision | Choix | Motif |
|---|---|---|
| Modèles au banc | **Clay v1.5 (de facto large) + TerraMind small** | Complémentaires (spec de bandes Clay / modèle IBM-ESA, esprit du CCTP). ⚠ Asymétrie subie et déclarée (revue v1) : ~302 M contre ~21 M de paramètres — seul `large` existe en Clay v1.5 ; rapport de coût attendu ~50×, compteurs publiés côte à côte |
| Ce que le banc mesure | **Débit + RAM + séparabilité** | Sans signal de qualité, on optimiserait le débit d'un modèle dont les embeddings ne discriminent peut-être rien |
| Matériel | **CPU seul** | Pas de GPU sur la machine, et **pas d'achat prévu** |
| Décision de fin de lot | **Périmètre embeddable**, pas achat | Conséquence directe de la décision ci-dessus |
| Stockage des vecteurs | **Fichiers**, pas de base | pgvector est l'index du Lot 2 ; l'y mettre ici gonflerait le lot sans rien mesurer de plus |
| Corpus de mesure | `D:\datas\tiny-wae` — **local, pas le NAS** | Le confondant réseau disparaît. Reste celui du montage Windows, mesuré en O2 |

## Faits relevés (à vérifier par les fiches, pas à croire sur parole)

- **Le corpus** : 5 793 chips, 9 873 manifestes, ~2,9 Mo par acquisition. ⭐ **Recompté le
  26/08** (revue v4) : **63 (B08) à 579 (B01) chips par site**, médiane 219 — soit un
  déséquilibre de **9,2×** entre sites, et non 7× comme annoncé jusque-là. Après le filtre à
  10 % : **4 959 chips**, de 49 à 563 par site.
- **Deux rasters par acquisition, à deux résolutions** : `chip.tif` (512×512, **4 bandes**
  10 m, uint16, **non compressé**) et `chip_20m.tif` (256×256, **6 bandes** 20 m). Les 10
  bandes de la spec Clay sont donc réparties sur deux fichiers, à deux grilles différentes :
  **assembler le tenseur d'entrée coûte une double lecture plus un rééchantillonnage.**
- **Clay v1.5** : CLS **1024-d**, 10 bandes (⚠ `nir` en 7ᵉ position — PAS la concaténation
  des constantes du Lot 0), 256×256, patch 8×8 → 1024 tokens. ⚠ **Masque à 75 % par défaut,
  y compris en inférence** — `mask_ratio=0.0` obligatoire (revue). Attend un **z-score sur
  DN** et un datacube `{pixels, time, latlon, gsd, waves}`. Le ~20 embeddings/s publié
  vient d'**AWS GPU (g4/g6), en configuration masquée** — jamais une référence pour nous.
- **TerraMind small** : sortie **384-d** (⚠ la carte HF annonçant 768 est fausse — vérifié
  au code source), liste de 12 tenseurs à agréger soi-même, **256×256 accepté** (256
  tokens). **Licence Apache 2.0, vérifiée** — comme Clay. Une bande mal nommée dans
  `bands=` produit des poids aléatoires silencieux : assertion obligatoire.
- **Le montage `/mnt/d` de WSL2 passe par drvfs.** Le Lot 0 a déjà mesuré ce que cette couche
  coûte (`just install` y recopiait 696 Mo faute de liens durs). Une passe complète, c'est
  **~16 Gio à lire à travers elle** : à chiffrer avant d'accuser le CPU.

## Livrables

- `core/embedding.py` — spec de bandes et normalisation, pur, testable à sec.
- `core/similarity.py` — métriques pures : cosinus, intra/inter, silhouette, dérive.
- `adapters/chip_loader.py` — le tenseur d'entrée, depuis les deux rasters.
- `adapters/embed_clay.py`, `adapters/embed_terramind.py` — derrière un port unique.
- `adapters/vectors.py` — stockage, clé d'idempotence, `VectorMeta`, `list_vectors`.
- `adapters/bench_probe.py` — instrumentation, protocole de stabilité, échantillon gelé.
- `cli/embed.py`, `cli/embed_backfill.py` — orchestrables, I/O explicites.
- `cli/bench.py`, `cli/bench_report.py`, `cli/similarity_report.py`,
  `cli/trajectory_report.py` — mesure et rapports.
- `scripts/fetch_models.py` et `scripts/check_cache.py` — les poids, hors gate.
- Un **rapport de banc** comparatif, avec extrapolation chiffrée au corpus et au run
  quotidien, et le **ratio discrimination / seconde**.
- Un **rapport de séparabilité** par modèle (`.md` **et** `.json`).
- Un **rapport de trajectoires** témoins (A02 / C08) — le verdict sur l'unité d'embedding.
- Un corpus de fixtures d'embedding, et un smoke `embed` dans le gate.

## Critères de sortie

Le lot est fini quand ces cinq points sont vrais, chiffres à l'appui :

1. **Substituabilité prouvée** : le même code produit un vecteur avec Clay et avec TerraMind,
   sans branche conditionnelle chez l'appelant — vérifié par un test, pas par relecture.
2. **Idempotence** : deux passes d'`embed` sur le même chip et le même modèle ne recalculent
   rien la seconde fois, et le vecteur est identique (déterminisme mesuré, tolérance déclarée
   si elle n'est pas nulle).
3. **Aucun accès réseau au run** : les trois artefacts de poids sont résolus depuis un
   cache local unique ; la garde est posée par le code de production et **le smoke tourne
   dessous** — elle est exercée à chaque `just check`, pas testée à part.
4. **Le banc publie une extrapolation chiffrée** : chips par heure et par modèle, RAM crête,
   et ce que ça donne sur 5 793 chips **et** sur une journée d'incrémental — avec le
   dénominateur et le cas défavorable.
5. **Le banc publie un pouvoir discriminant** par modèle — lu contre une **baseline
   triviale** — et le **ratio discrimination / seconde** (porté par `l1-04.5`, après la
   campagne) qui permet de trancher.

⚠ Un critère de sortie qu'on ne peut pas rendre **rouge** n'en est pas un : chaque oracle du
chantier doit être exercé dans les deux sens.

## Questions de cadrage — TRANCHÉES

Les quatre questions ouvertes à l'ouverture du lot ont été tranchées le 23/08 (Philippe),
puis précisées par la revue v1 du 24/08 : unité = un vecteur par chip en 20 m ·
pas de masque SCL, seuil 10 % paramétré, tout consigné · TerraMind small en 256 ·
déterminisme exigé à configuration fixée, mesuré entre threads. Les seuils décisionnels
(silhouette 0,2 + baseline, dérive > 2, fidélité ≥ 0,999, corrélation nuage 0,5) sont
actés. **Détail : roadmap du chantier, §2bis et §2ter** — qui fait foi pour la déclinaison.

## Déclinaison en backlog

Chantier `docs/backlog/maturation/lot-1-embeddings/` — **5 chapeaux · 24 fiches agent
(dont le socle `l1-00` et le gate avec poids `l1-07`) · 2 fiches humaines** (la campagne
`l1-05.3.H` et l'arbitrage `l1-06.H`) — soit **26 fiches dispatchables**, profondeur 8,
largeur moyenne 3,25 — en quatre phases :

| Phase | Objet | Chapeaux et fiches à plat |
|---|---|---|
| **O1** | Socle : dépendances et cache des poids, gate avec poids, contrat d'entrée, chargement, port, fixtures | `l1-01` + **`l1-00`** et **`l1-07`** (à plat) |
| **O2** | Modèles et exécution : adapters, CLI, stockage, smoke | `l1-02`, `l1-03` |
| **O3** | Mesure : banc instrumenté, leviers, séparabilité, trajectoires | `l1-04`, `l1-05` |
| **O4** | Décision : arbitrage humain du périmètre | `l1-06.H` |

Les livrables décisionnels (bench-report, similarity-report, trajectory-report,
campaign.json) sont versionnés sous **[`docs/lots/lot-1/`](lot-1/)** — jamais dans `data/`,
qui est gitignoré. Ce répertoire est **ouvert à l'équipe en création** (décision Philippe du
25/08) ; il est créé par `l1-05.3a`.

La roadmap détaillée et le graphe de dépendances vivent dans `_roadmap.md` du chantier. Ce
document reste la **source de vérité du lotissement** ; les fiches en sont la déclinaison
opérationnelle.
