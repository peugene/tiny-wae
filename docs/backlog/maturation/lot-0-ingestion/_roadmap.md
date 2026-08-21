# Roadmap — Lot 0 : Ingestion Sentinel-2 (phase 1, indicative)

> Roadmap **indicative** posée avant le code. Sera figée après la **revue de cohérence**
> (`_revue.md`, phase 2). Transposition au format chantier de la fiche `LOT0-fiche-sites.md`
> validée par Philippe le 20/08/2026 (GO sur les 25 sites, historique 48 mois, pipeline CWL).

## 1. Cible & décisions actées (ne pas rouvrir)

- **25 sites** en 3 catégories (annexe A), **48 mois** d'historique glissant, puis
  **ingestion incrémentale quotidienne** (même pipeline, fenêtre bornée).
- Produit : **Sentinel-2 L2A** (collection *harmonized* — offset baseline janv. 2022 corrigé),
  chips **512×512 px @ 10 m** (5,12 km), bandes **B02/B03/B04/B08 + SCL**, rejet si
  **> 30 % nuages/ombres** sur le chip (seuil ajustable).
- Source STAC : **earth-search (AWS)** en priorité, **CDSE** en secours — l'abstraction STAC
  rend le basculement peu coûteux.
- Stockage : NAS, layout `<racine>/{site_id}/{date}/chip.tif` + `manifest.json` par
  acquisition. **Idempotence obligatoire** (run double = zéro doublon, zéro re-téléchargement).
- **Chaque étape = un CLI typer à I/O explicites**, pensé pour devenir un step **CWL**
  (moteur PID-FLOW ; cwl-assets sert d'exemple pour le tooling).
- Aucune IA dans ce lot. Hors périmètre : Sentinel-1 (V2), recalage sub-pixel, qualité
  radiométrique fine.

## 2. Objectifs / phases

- **O1 — Plomberie STAC** : config des sites typée et validée ; recherche d'acquisitions ;
  téléchargement fenêtré + masque SCL + chip GeoTIFF + manifeste. Le smoke réel remplace le
  placeholder ici.
- **O2 — Historique 48 mois** : orchestration du backfill 25 sites × 48 mois ; rapport de
  recette chiffré (oracle O2 de la fiche d'origine : ≥ 60 acquisitions exploitables/site,
  chiffres par site publiés y compris les pires) ; planche de contrôle visuel (gate Philippe).
- **O3 — Incrémental & CWL** : mode quotidien (fenêtre depuis le dernier manifeste) ;
  définitions CWL des steps + chaîne enregistrable dans PID-FLOW.

## 3. Pièges critiques transverses

- **Coordonnées des sites de mémoire (±1-2 km)** : la planche visuelle (O2) est LE filet —
  toute correction de centrage se reporte dans la config, puis ré-ingestion ciblée.
- **Nuages** : sites UK/tropicaux peuvent perdre > 60 % des acquisitions — c'est une mesure
  attendue (argument S1 en V2), pas un échec d'ingestion.
- **Quotas/latence des sources STAC** : earth-search est sans auth mais sans SLA ; prévoir
  reprise sur erreur (backoff) et reprise de run (idempotence).
- **Téléchargement fenêtré** : lire les COG par fenêtres (rasterio) — jamais la scène
  entière (des Go pour 5 km²).
- **Mélange logs/données** : logs sur STDERR, données/manifestes en fichiers — invariant CWL.
- **Sites récents** (Sizewell, Chancay) : peu ou pas d'acquisitions utiles en début de
  fenêtre 48 mois — vérité terrain, à distinguer d'un bug.

## 4. Séquençage recommandé

O1 strictement séquentiel (config → recherche → ingestion, chaque fiche dépend de la
précédente). O2 après O1 complet. O3 après O2 (l'incrémental réutilise tout ; le CWL
emballe des CLIs stabilisés).

## 5. Questions ouvertes (à trancher en maturation / revue)

- **Q-A** (l0-02) : bibliothèque cliente STAC — `pystac-client` (mûr, standard) vs requêtes
  HTTP directes ? Défaut recommandé : pystac-client.
- **Q-B** (l0-03) : format de sortie — GeoTIFF simple vs COG ? Défaut : GeoTIFF (COG inutile
  pour des chips de 5 km lus localement).
- **Q-C** (l0-04) : parallélisme du backfill — séquentiel simple d'abord, paralléliser
  seulement si la mesure l'exige ?
- **Q-D** (l0-06) : niveau d'intégration PID-FLOW dans CE lot — définitions CWL validées
  (`cwltool --validate` + run local) suffisent-elles, ou enregistrement réel sur le server ?

## 6. Liste des fiches du chantier

| Phase | Fiche | Effort | Objet |
|---|---|---|---|
| O1 | `l0-01-sites-config` | S | Config YAML des 25 sites + modèle typé + CLI de validation |
| O1 | `l0-02-stac-search` | M | Adapter STAC : acquisitions par site/fenêtre/nuages + CLI |
| O1 | `l0-03-chip-ingest` | L | Chip : lecture fenêtrée, masque SCL, GeoTIFF + manifeste, idempotent ; câble le smoke réel |
| O2 | `l0-04-backfill` | M | Backfill 48 mois × 25 sites + rapport chiffré + planche visuelle |
| O3 | `l0-05-incremental` | S | Mode quotidien : fenêtre depuis dernier manifeste |
| O3 | `l0-06-cwl-steps` | M | Définitions CWL des steps + chaîne (exemple : cwl-assets) |

## Annexe A — Les 25 sites (GO Philippe 20/08/2026)

Coordonnées de mémoire (±1-2 km), **à valider/corriger via la planche visuelle d'O2**.

**A — Nucléaire en construction (8)** : A01 ITER Cadarache FR (43.708, 5.776) · A02 Hinkley
Point C UK (51.208, −3.130) *cas défavorable nuages* · A03 Sizewell C UK (52.215, 1.620) ·
A04 Flamanville FR (49.536, −1.882) · A05 Akkuyu TR (36.144, 33.541) · A06 El Dabaa EG
(31.043, 28.494) · A07 Zhangzhou CN (23.816, 117.578) · A08 Vogtle US (33.143, −81.762).

**B — Mégachantiers (9)** : B01 NEOM The Line SA (28.09, 35.23) · B02 Aéroport King Salman
SA (24.96, 46.70) · B03 Nouvelle capitale admin. EG (30.03, 31.73) · B04 Barrage GERD ET
(11.215, 35.093) · B05 Parc solaire MBR Dubaï AE (24.76, 55.36) · B06 Mine Escondida CL
(−24.27, −69.07) · B07 Salar d'Atacama CL (−23.50, −68.30) · B08 Port de Chancay PE
(−11.57, −77.27) · B09 A69 Toulouse-Castres FR (43.60, 2.00) *contrôle local*.

**C — Stables & veille OSINT (8)** : C01 Golfech FR (44.11, 0.85) · C02 Airbus
Toulouse-Blagnac FR (43.63, 1.36) · C03 Fos-sur-Mer FR (43.42, 4.85) · C04 Lacq FR (43.42,
−0.62) · C05 Natanz IR (33.72, 51.73) · C06 Engels RU (51.48, 46.21) · C07 Punggye-ri KP
(41.28, 129.08) · C08 zone témoin rurale SO Toulouse *à définir dans l0-01*.

Équilibre : 12 « changement attendu », 8 « stables » (mesure des faux positifs du futur
Lot 2), 5 intermédiaires.
