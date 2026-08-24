# Fiche Lot 1 — Banc d'embeddings GFM sur CPU

**Projet** : tiny-wae — POC Earth Intelligence perso
**Statut** : maturation — ouvert le 23/08/2026 après la recette du Lot 0 (GO Philippe)
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
- deux **adapters** derrière un port unique : **Clay v1.5** et **TerraMind** ;
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
| Modèles au banc | **Clay v1.5 + TerraMind** | Deux points suffisent à comparer, et ils sont complémentaires : les 10 bandes du Lot 0 ont été choisies à la spec de Clay (décision D-b) ; TerraMind est le modèle IBM/ESA, directement dans l'esprit du CCTP. Un banc à un seul modèle ne compare rien |
| Ce que le banc mesure | **Débit + RAM + séparabilité** | Sans signal de qualité, on optimiserait le débit d'un modèle dont les embeddings ne discriminent peut-être rien |
| Matériel | **CPU seul** | Pas de GPU sur la machine, et **pas d'achat prévu** |
| Décision de fin de lot | **Périmètre embeddable**, pas achat | Conséquence directe de la décision ci-dessus |
| Stockage des vecteurs | **Fichiers**, pas de base | pgvector est l'index du Lot 2 ; l'y mettre ici gonflerait le lot sans rien mesurer de plus |
| Corpus de mesure | `D:\datas\tiny-wae` — **local, pas le NAS** | Le confondant réseau disparaît. Reste celui du montage Windows, mesuré en O2 |

## Faits relevés (à vérifier par les fiches, pas à croire sur parole)

- **Le corpus** : 5 793 chips, 9 873 manifestes, ~2,9 Mo par acquisition.
- **Deux rasters par acquisition, à deux résolutions** : `chip.tif` (512×512, **4 bandes**
  10 m, uint16, **non compressé**) et `chip_20m.tif` (256×256, **6 bandes** 20 m). Les 10
  bandes de la spec Clay sont donc réparties sur deux fichiers, à deux grilles différentes :
  **assembler le tenseur d'entrée coûte une double lecture plus un rééchantillonnage.**
- **Clay v1.5** : embeddings **1024 dimensions**, spec à **10 bandes** Sentinel-2, tuiles
  256×256, patch d'attention 8×8. ⚠ Le chiffre de ~20 embeddings/s publié par Clay a été
  obtenu **sur AWS**, pas sur un CPU de poste — il ne vaut que comme ordre de grandeur d'un
  plafond, jamais comme référence de comparaison.
- **TerraMind** : modèle multimodal IBM / ESA / Jülich, intégré à **TerraTorch**, décliné en
  variantes ; les variantes **tiny/small** sont celles que les auteurs recommandent pour
  l'exécution locale et l'inférence rapide. **La licence est à relever et à consigner par la
  fiche d'adapter** — elle conditionne l'usage.
- **Le montage `/mnt/d` de WSL2 passe par drvfs.** Le Lot 0 a déjà mesuré ce que cette couche
  coûte (`just install` y recopiait 696 Mo faute de liens durs). Une passe complète, c'est
  **~16 Gio à lire à travers elle** : à chiffrer avant d'accuser le CPU.

## Livrables

- `core/embedding.py` — spec de bandes et normalisation, pur, testable à sec.
- `adapters/chip_loader.py` — le tenseur d'entrée, depuis les deux rasters.
- `adapters/embed_clay.py`, `adapters/embed_terramind.py` — derrière un port unique.
- `cli/embed.py`, `cli/embed_backfill.py` — orchestrables, I/O explicites.
- Un **rapport de banc** comparatif, avec extrapolation chiffrée au corpus et au run quotidien.
- Un **rapport de séparabilité** par modèle.
- Un corpus de fixtures d'embedding, et un smoke `embed` dans le gate.

## Critères de sortie

Le lot est fini quand ces cinq points sont vrais, chiffres à l'appui :

1. **Substituabilité prouvée** : le même code produit un vecteur avec Clay et avec TerraMind,
   sans branche conditionnelle chez l'appelant — vérifié par un test, pas par relecture.
2. **Idempotence** : deux passes d'`embed` sur le même chip et le même modèle ne recalculent
   rien la seconde fois, et le vecteur est identique (déterminisme mesuré, tolérance déclarée
   si elle n'est pas nulle).
3. **Aucun accès réseau au run** : les poids sont résolus depuis un cache local ; la garde
   est vérifiée par mutation, comme celle du Lot 0.
4. **Le banc publie une extrapolation chiffrée** : chips par heure et par modèle, RAM crête,
   et ce que ça donne sur 5 793 chips **et** sur une journée d'incrémental — avec le
   dénominateur et le cas défavorable.
5. **Le banc publie un pouvoir discriminant** par modèle, mesuré sur le corpus réel, et le
   rapport discrimination / seconde qui permet de trancher.

⚠ Un critère de sortie qu'on ne peut pas rendre **rouge** n'en est pas un : chaque oracle du
chantier doit être exercé dans les deux sens.

## Questions ouvertes (à trancher avant descente en fiches)

1. **Quelle unité embedder ?** Le chip entier (5 120 m) donne un vecteur par acquisition —
   c'est la colonne vertébrale annoncée. Mais Clay travaille sur des tuiles de 256×256 : à 10 m
   le chip en fait quatre, à 20 m une seule. Un vecteur par chip, ou un par tuile agrégé
   ensuite ? **Ça change le nombre de vecteurs, le coût, et la finesse de détection du Lot 2.**
2. **Que fait-on du masque SCL à l'entrée du modèle ?** Neutraliser les pixels nuageux, ou
   laisser le modèle les voir ? La seconde option est plus simple et plus fidèle à
   l'entraînement des GFM ; la première réduit le bruit. À trancher, pas à découvrir.
3. **Quelle variante de TerraMind ?** Les auteurs recommandent tiny/small en local. À fixer
   avant la fiche d'adapter, sinon l'oracle n'a pas de référence.
4. **Quelle tolérance de déterminisme ?** Bit à bit est l'idéal, mais le multi-threading BLAS
   peut introduire des écarts. Fixer un seuil **avant** de mesurer, sinon on le fixera après
   coup à la valeur observée — ce qui ne prouve rien.

## Déclinaison en backlog

Chantier `docs/backlog/maturation/lot-1-embeddings/` — **5 chapeaux · 20 sous-tâches ·
1 fiche humaine**, en quatre phases :

| Phase | Objet | Chapeaux |
|---|---|---|
| **O1** | Socle : contrat d'entrée, chargement, port, fixtures | `l1-01` |
| **O2** | Modèles et exécution : adapters, CLI, stockage | `l1-02`, `l1-03` |
| **O3** | Mesure : banc instrumenté, leviers, séparabilité | `l1-04`, `l1-05` |
| **O4** | Décision : arbitrage humain du périmètre | `l1-06.H` |

La roadmap détaillée et le graphe de dépendances vivent dans `_roadmap.md` du chantier. Ce
document reste la **source de vérité du lotissement** ; les fiches en sont la déclinaison
opérationnelle.
