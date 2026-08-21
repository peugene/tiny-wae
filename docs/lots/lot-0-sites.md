# Fiche Lot 0 — Sites de surveillance & ingestion Sentinel-2

**Projet** : tiny-wae — POC Earth Intelligence perso
**Statut** : validé — GO Philippe (liste des 25 sites arbitrée) ; **v3 du 21/08/2026** : aligné sur les trois revues adversariales et les GO Philippe **G1-G10** puis **D-a/D-b/D-c** et **E-a/E-b/E-c/E-d**. C08 = Bouconne.
**Date** : 20/08/2026 — transférée le 21/08/2026 depuis un dossier de travail hors dépôt ; **la source est désormais ce fichier**. Déclinaison opérationnelle : chantier `docs/backlog/maturation/lot-0-ingestion/` (roadmap v3 figée + revues v1/v2/v3)

---

## 1. Objet du lot

Mettre en place la plomberie données : sélection de 25 sites, récupération automatisée des
vignettes (chips) Sentinel-2 L2A sur **48 mois glissants**, masquage nuages, stockage NAS,
puis ingestion incrémentale quotidienne. Aucune IA dans ce lot — uniquement de l'ingestion
fiable et mesurée.

## 2. Paramètres techniques (v3 — post-revues, GO Philippe 21/08)

| Paramètre | Valeur actée | Justification |
|---|---|---|
| Source données | STAC `earth-search` v1, collection **`sentinel-2-l2a`** (la « c1 » a un trou avant déc. 2022, mesuré). CDSE : hors Lot 0, port `StacSource` prévu | Sans auth, COG directs. ⚠ Assets réels nommés `blue/green/red/nir/…/scl` (pas B02…) ; COG `https://` uniquement (variantes `-jp2` = bucket requester-pays) |
| Produit | Sentinel-2 L2A | L'offset baseline (janv. 2022) se lit dans les métadonnées de chaque asset et se journalise — la « collection harmonized » n'existe pas sur earth-search (vocable Earth Engine, corrigé en revue) |
| Chips | `chip.tif` 512×512 @ 10 m (blue/green/red/nir) + **`chip_20m.tif` 256×256 @ 20 m à SIX bandes : `rededge1/rededge2/rededge3/nir08/swir16/swir22`** (**décision D-b**) + **`scl.tif` 20 m** (**GO G2**) | Clay v1.5 attend 10 bandes S2 **dont les 3 red-edge** ; les capter maintenant coûte **×1,41** au total (sous le budget ×1,5 accordé — le « +50 % » de la v2 était faux : la variante à 3 bandes coûtait ×1,22). GeoTIFF simple, pas COG (**GO G5**) |
| Grille | CRS UTM + origine par site, calée multiple de 20 m, figée dans `sites.yaml` ; **tuile MGRS de référence épinglée par MARGE GÉOMÉTRIQUE maximale** (**GO G8 + décision D-c**) | Chips superposables au bit près entre dates (condition du Lot 2). Multi-tuiles = cas **fréquent** (A03, A04, C07 mesurés) ; la règle « tuile majoritaire » choisissait la MAUVAISE tuile sur C07 (marge 495 m vs 4 155 m) |
| Filtre nuages | SCL lu EN PREMIER à 20 m : `invalid_pct` {0,1} → rejet dur ; `cloud_pct` {3,8,9,10} → seuil 30 % configurable ; classes 2/11 comptées (décision différée sur chiffres). Pré-filtre **scène** `eo:cloud_cover < 95 %` en amont, les écartés étant comptés (`skipped_scene_cloud`) | Classe 0 absente = chip vide classé « clair » (bug attrapé en revue) ; SCL-first économise le transfert des rejets |
| Historique | **48 mois glissants** (arbitrage Philippe, 20/08/2026) puis incrémental quotidien (marge 3 j, rattrapage mensuel des retraitements tardifs) | Volumes mesurés **par tuile épinglée** (la convention du pipeline) : **~11 000 items instruits** pour 25 sites, transfert estimé 50-100 Go (**non mesuré** — cf. §5/O5), stocké ~×1,41 du 10 m seul ; backfill en pool 4-8 workers (**GO G6**) |
| Dénominateurs | **`found_stac`** (items STAC bruts, avant tout filtre) et **`found_tile`** (= `found_stac − skipped_scene_cloud − off_tile`, les items réellement instruits) — **décision E-a**, le mot `found` seul est banni | Un ratio bâti sur `found_stac` mesurerait la géométrie du site : `off_tile` vaut **49,8 %** sur C07 (chip à cheval sur 2 tuiles) contre **0 %** sur A01 |
| Stockage | NAS : `/{site_id}/{item_id}/` (**GO G9** — clé = item id STAC) + `manifest.json` par item (contrat gravé, versionné) | Le layout par date collisionne (tuiles multiples même jour, retraitements `s2:sequence`) — prouvé en revue |

⚠️ **Coordonnées ci-dessous : de mémoire, précision estimée ±1–2 km.** La validation visuelle
de centrage de chaque chip fait partie de l'oracle (§5). Certains mégachantiers dépassent la
taille d'un chip : un segment représentatif est désigné.

## 3. Liste des sites (25)

### Catégorie A — Nucléaire en construction (8) — vérité terrain riche, chronologies publiques

| ID | Site | Pays | Lat, Lon (approx.) | Signature attendue |
|---|---|---|---|---|
| A01 | ITER (Cadarache) | FR | 43.708, 5.776 | Assemblage, bâtiments annexes, parkings |
| A02 | Hinkley Point C | UK | 51.208, −3.130 | Chantier EPR massif — **cas défavorable nuages** |
| A03 | Sizewell C | UK | 52.215, 1.620 | Terrassements en démarrage |
| A04 | Flamanville | FR | 49.536, −1.882 | Post-chantier : activité décroissante |
| A05 | Akkuyu | TR | 36.144, 33.541 | 4 réacteurs en construction, très actif |
| A06 | El Dabaa | EG | 31.043, 28.494 | Chantier actif, ciel clair quasi permanent |
| A07 | Zhangzhou | CN | 23.816, 117.578 | Réacteurs Hualong One en série |
| A08 | Vogtle 3-4 | US | 33.143, −81.762 | Achevé 2023-24 : transition chantier → stable |

### Catégorie B — Mégachantiers mondiaux (9) — signatures énormes, idéal détection de changement

| ID | Site | Pays | Lat, Lon (approx.) | Signature attendue |
|---|---|---|---|---|
| B01 | NEOM "The Line" (segment Hidden Marina) | SA | 28.09, 35.23 | Terrassement massif, désert = ciel clair |
| B02 | Aéroport King Salman (Riyad) | SA | 24.96, 46.70 | Pistes et terminaux en construction |
| B03 | Nouvelle capitale administrative | EG | 30.03, 31.73 | Urbanisation massive |
| B04 | Barrage GERD | ET | 11.215, 35.093 | Niveau du réservoir (saisonnier + remplissage) |
| B05 | Parc solaire M. bin Rashid (Dubaï) | AE | 24.76, 55.36 | Extension par phases datées |
| B06 | Mine d'Escondida | CL | −24.27, −69.07 | Extension fosse/terrils, désert d'Atacama |
| B07 | Salar d'Atacama (bassins lithium) | CL | −23.50, −68.30 | Évolution des bassins d'évaporation |
| B08 | Port de Chancay | PE | −11.57, −77.27 | Mise en service 2024, extension |
| B09 | Autoroute A69 Toulouse-Castres (section) | FR | 43.60, 2.00 | Chantier linéaire — **contrôle local visitable** |

### Catégorie C — Sites stables & veille type OSINT (8) — mesure des faux positifs + thématique surveillance

| ID | Site | Pays | Lat, Lon (approx.) | Rôle |
|---|---|---|---|---|
| C01 | Centrale de Golfech | FR | 44.11, 0.85 | Contrôle négatif nucléaire, proche Toulouse |
| C02 | Airbus Toulouse-Blagnac | FR | 43.63, 1.36 | Contrôle négatif industriel, vérifiable de visu |
| C03 | Port de Fos-sur-Mer | FR | 43.42, 4.85 | Industriel stable, trafic variable |
| C04 | Raffinerie de Lacq | FR | 43.42, −0.62 | Industriel stable |
| C05 | Natanz | IR | 33.72, 51.73 | Veille OSINT documentée, changements épisodiques |
| C06 | Base aérienne d'Engels | RU | 51.48, 46.21 | Veille OSINT documentée |
| C07 | Punggye-ri | KP | 41.28, 129.08 | Site quasi statique, OSINT — ⚠ multi-tuiles avéré (52TDL/52TEL), tuile de référence à épingler |
| C08 | **Forêt de Bouconne** | FR | 43.628, 1.217 | Contrôle négatif pur — **décision Philippe, GO du 21/08/2026**. Massif ~2 000 ha à l'ouest de Toulouse, vérifiable sur place. Forêt gérée : coupes d'entretien possibles = « faux positifs explicables », notés |

**Équilibre** : 12 sites « changement attendu », 8 « stables » (dont 4 contrôles négatifs stricts),
5 intermédiaires. Les stables sont aussi importants que les actifs : c'est eux qui mesurent le
taux de faux positifs du futur Lot 2.

## 4. Livrables du lot

1. Pipeline d'ingestion Python (STAC → chips GeoTIFF sur NAS), idempotent, rejouable, configurable par fichier de sites (YAML). Chaque étape livrée comme **CLI autonome à I/O explicites, orchestrable par l'outil de workflow CWL de Philippe**.
2. Historique 48 mois ingéré pour les 25 sites.
3. Mode incrémental : le même pipeline, borné par fenêtre temporelle, pour l'ingestion quotidienne des nouvelles acquisitions.
4. Rapport de recette chiffré (`report`, voir §5) + `report --check-completeness`.
5. Planches de contrôle visuel : **précoce** (1 chip récent/site, AVANT le backfill) et **first/last** en fin de campagne.
6. Emballage **CWL local** : 3 CommandLineTools (`search`, `ingest`, `update`) + 1 Workflow, validés par `cwltool` (l'enregistrement PID-FLOW réel est **hors lot** — GO G7).

## 5. Oracle de recette (v3 — décision E-a : critères MÉCANIQUES uniquement)

**Les 4 critères ci-dessous sont prononcés par l'outil** (`report`), pas par un humain :

| # | Critère | Seuil de succès |
|---|---|---|
| O1 | **Conservation** (identité comptable, par site et sur l'agrégat) : `found_stac = skipped_scene_cloud + off_tile + found_tile` ET `found_tile = somme des 6 statuts` (`ingested | rejected_clouds | rejected_invalid | rejected_nodata | failed | skipped` — énumération normative du chapeau l0-02) | boucle exactement — 25/25 sites. C'est ce critère qui attrape la **perte silencieuse** que les oracles v1/v2 laissaient passer |
| O2 | **Complétude vs source** : **comparaison d'ENSEMBLES d'`item_id`** — manifestes du site vs ids d'un `/search` paginé reproduisant les **trois** filtres du pipeline (bbox + fenêtre + `grid:code` + `eo:cloud_cover < 95 %`) via `report --check-completeness` | écart **0**, ids manquants nommés. ⚠ Ni somme de compteurs (sur-comptage par recouvrement), ni filtre incomplet (l'oubli du pré-filtre scène rendrait l'écart = `skipped_scene_cloud`) |
| O3 | **Intégrité** — colonne `integrite: OK/ROUGE` de `report`, calculée **depuis les manifestes** (pas de relecture des rasters) : les 3 fichiers listés, `content_hashes` complets, `grid_hash` == grille **courante** du site, **`chip_nodata_pct` < 1 %** (garde nodata du GO G8, instrumentée : seuil en settings, champ au manifeste, statut `rejected_nodata`) | 100 % des items `ingested` ; items fautifs nommés |
| O4 | **`failed ≤ 1 % de found_tile`** — seul seuil légitime : un échec technique EST un défaut de pipeline | par site |

**Idempotence** (vérifiée dans le harnais, pas en recette — décision E-d) : run double →
1er run `assets_read > 0`, 2e run `assets_read == 0` et `content_hashes` (hash du tableau
**décodé**) inchangés. `bytes_downloaded` n'est PAS un critère : il ne couvre que le
chemin STAC (les lectures GDAL ne sont pas instrumentables depuis Python).

**Publiés SANS seuil, par site, pires en tête** — ce sont des caractéristiques de site, pas
des critères de qualité : `off_tile` (49,8 % sur C07 vs 0 % sur A01 — géométrie),
`skipped_scene_cloud`, **ratio `ingested / found_tile` avec son dénominateur**, agrégat
`scl_class_counts`, `bytes_written` (octets réellement écrits — seule mesure de volume
exacte), durée. Leur **lecture et le verdict qu'on en tire relèvent du jugement humain**
(fiche `l0-04.H`), pas d'un seuil automatique.

**Centrage** : validé par les **fiches humaines** `l0-03.H` (planche précoce, AVANT le
backfill — 25/25) puis `l0-04.H` (planche first/last, contrôle de non-régression). Ce ne
sont pas des oracles : ce sont des fiches de backlog à part entière, jamais dispatchées à
un agent.

**Non testé dans ce lot** : qualité radiométrique fine (l'offset baseline est *journalisé*,
pas appliqué), recalage sub-pixel entre dates, mosaïque multi-tuiles, Sentinel-1,
enregistrement PID-FLOW, bascule CDSE, tout ce qui touche aux GFMs. **Volume réellement
transféré** : hors instrument (relevé système ou déclaré non mesuré).

## 6. Risques identifiés

- Sites UK/tropicaux : forte perte nuages — mesuré au niveau **scène** sur Hinkley : 111 items sous 30 % de nuages sur 688 (16,1 %). Le taux au grain **chip** (le seul qui compte) n'est pas mesuré et sera vraisemblablement meilleur. Argument S1 pour la V2.
- Coordonnées de mémoire (±1-2 km) : corrigées à la **planche précoce** (`l0-03.H`), avant le backfill. Le `grid_hash` du manifeste garantit la ré-ingestion automatique des sites corrigés.
- earth-search : pérennité du service non garantie — l'abstraction STAC rend le basculement CDSE peu coûteux.
- The Line : ralentissements de chantier documentés en 2025 — signature possiblement plus faible qu'espéré.
- ~~Sites récents = peu d'acquisitions~~ — **corrigé en revue (21/08)** : faux. Sizewell est le site le MIEUX fourni du parc (1383 items/48 mois) ; S2 image depuis 2015, chantier ou pas. Ce qui manque en début de fenêtre d'un site récent, c'est le *signal de changement*, pas l'imagerie.
- Retraitements tardifs (`s2:sequence ≥ 1`, phénomène massif mesuré) : échappent à la fenêtre incrémentale — rattrapage mensuel documenté, non automatisé au POC.
