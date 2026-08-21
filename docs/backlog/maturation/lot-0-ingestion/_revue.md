# Revue de cohérence adversariale — Chantier Lot 0 Ingestion

**Date** : 21/08/2026 · **Orchestrateur** : architecte/PO (Cowork, Fable) · **Protocole** : 5 angles
Opus indépendants et aveugles (découpage, séquençage, faits externes avec vérification API réelle,
couverture des 28 décisions actées, effort/oracles) + réfutation Opus indépendante.

**Chiffres de la revue** : 81 findings bruts → 68 après dédoublonnage → **52 confirmés,
16 partiels (sous-énoncés corrigés), 0 réfuté en bloc** → 11 clusters de fond → 5 critiques.
L'angle « faits externes » a interrogé l'API earth-search réelle (48 requêtes cumulées,
reproductibles) ; la réfutation a re-mesuré indépendamment les bloquants.

## Verdict global

**Le chantier n'est PAS prêt à passer en `a-faire/`.** La structure (chantier, phases, oracles
présents partout, « Non testé » systématique) est saine — mais les fiches n'avaient jamais été
confrontées à l'API réelle, et la revue révèle 5 défauts critiques dont un **irréversible**
(choix des bandes) et deux qui rendraient la recette du lot **auto-validante** (oracle
inéchouable, rapport non testé). C'est exactement ce que la revue devait attraper : aucun de
ces défauts n'aurait été détecté par les oracles tels qu'écrits.

## Les 5 critiques (consolidés, classement du réfuteur)

**C1 — Clé de stockage non unique (EXT-3/EXT-4, bloquant).** Le layout `{site}/{YYYY-MM-DD}/`
entre en collision de façon *déterministe* : deux tuiles MGRS le même jour (prouvé sur C07
Punggye-ri : items 52TDL **et** 52TEL du 2026-06-30 ; 636 items sur 48 mois, 319+317) et les
retraitements `_1_L2A` (452 310 items `s2:sequence=1` mesurés sur 8 mois de 2026). Perte de
données silencieuse que l'oracle d'idempotence validerait au vert.
→ **Clé = item id STAC** (`{site_id}/{item_id}/`), une entrée de manifeste par item.

**C2 — Noms d'assets faux (EXT-1, bloquant).** earth-search nomme les assets
`blue/green/red/nir/scl` — les clés `B02/B03/B04/B08/SCL` écrites dans l0-02 (périmètre ET
oracle O1) n'existent pas ; piège aggravant : `eo:bands[].name` vaut bien « B02 ».
→ Table de correspondance en config, oracle reformulé.

**C3 — Contrat manifeste non gravé (SEQ-4/SEQ-5, bloquant).** `manifest.json` est consommé
par l0-04/05/06 mais décrit en prose dans l0-03 seul, avec 2 statuts (`ingested|rejected_clouds`)
alors que le rapport de recette exige « trouvées/échecs » : **l'oracle du lot est insatisfiable
tel quel**. → `adapters/manifests.py` (write/read/list/last_date), schéma versionné, statuts
`ingested|rejected_clouds|failed` + journal `found` par (site, fenêtre).

**C4 — Recette auto-validante (EFF-3 + EXT-10 + EFF-23 + EFF-15, bloquant).** L'oracle-phare
« ≥ 60 acquisitions/site » ne peut pas échouer (clause d'exemption), ne discrimine rien
(324 à **1383** items disponibles par site mesurés — un pipeline perdant 80 % passe), son
exemption « sites récents » repose sur un fait faux (Sizewell = 1383 items, le mieux fourni du
parc — S2 image depuis 2015, chantier ou pas), et le CLI `report` qui produit ces chiffres n'a
lui-même aucun test. → Oracle en **ratio exploitables/trouvés avec dénominateur publié par
site** ; `report` testé sur manifestes fixtures aux comptes connus ; exemption supprimée.

**C5 — l0-04 incompatible avec le run autonome (SEQ-1/DEC-1/EFF-2, bloquant).** Une seule
fiche cumule 3 CLIs, une campagne réelle de **15-30 h** (séquentiel, ~16 000 items mesurés
pour 25 sites — pas ~11 000) et un gate humain, sous un effort « M », en tête de chaîne de
l0-05/06 : le `/run` s'y arrête ou s'auto-valide. → Scission 04a/04b + graphe rebranché (§graphe).

**Hors podium mais IRRÉVERSIBLE (EXT-11)** : 4 bandes 10 m sans SWIR condamnent le Lot 1 —
TerraMind attend 12 canaux S2 dont SWIR (224×224), Clay ~10 bandes. Corriger après backfill =
**re-télécharger l'intégralité** (~100-200 Go transférés mesurés en ordre de grandeur, 15-30 h).
La justification « multiples de 224/256 » de la fiche source est fausse pour 224 (512/224=2,29).
→ Décision AVANT l0-03 : ajouter `nir08/swir16/swir22` en fichier 20 m séparé (`chip_20m.tif`,
+50 % stockage) — recommandé — ou assumer par écrit la ré-ingestion au Lot 1.

## Autres confirmés majeurs (par cluster)

- **Config applicative sans propriétaire** (DEC-4/SEQ-7/COV-9) : URL STAC, collection, seuil
  nuages, data_root invoqués par 3 fiches, possédés par aucune ; `.env.example` réel = 1 ligne
  DATABASE_URL. → l0-01 étendue : `config/settings` + `.env.example` enrichi + liste de clés figée.
- **« Harmonized » n'existe pas** (EXT-2 partiel) : vocabulaire Google Earth Engine, pas
  earth-search. L'offset baseline (scale 0.0001/offset −0.1, `boa_offset_applied`) est à LIRE
  des métadonnées et journaliser. Nuance réfuteur : pas de mélange de conventions dans la fenêtre
  actuelle (démarre 2022-08 > bascule 2022-01) — mais la fenêtre est glissante : à instrumenter.
- **SCL incomplet et 20 m** (EXT-5/DEC-8/EXT-6) : classes 0 (NO_DATA — chip vide classé
  « clair » !), 1, 2, 11 (neige : Escondida, Punggye-ri) absentes ; grille 20 m jamais traitée.
  → deux compteurs (`invalid_pct` {0,1} rejet dur ; `cloud_pct` {3,8,9,10} seuil 30 %), origine
  chip calée sur multiple de 20 m, % calculé à 20 m (256×256), `nearest` obligatoire.
- **Grille cible par site non figée** (EXT-7 partiel) : figer CRS+origine par site dans
  `sites.yaml` ; oracle « transform/CRS identiques au bit près pour tous les chips d'un site ».
  Nuance : sur les 6 sites testés, même zone UTM — risque latent, pas systématique.
- **`just check` devient réseau-dépendant** (DEC-7/SEQ-6/EFF-5) : smoke **replay sur cassette
  par défaut** dans `check`, `--live` à la demande ; cache data partagé hors worktree ;
  ⚠ découverte réfuteur : `data/` n'est **pas** dans `.gitignore`.
- **Ordre des opérations** (EXT-8 partiel) : SCL d'abord, court-circuit avant lecture 10 m —
  gain fort sur sites nuageux (Hinkley : 526/688 scènes ≥ 40 %), faible sur désertiques.
- **Volumétrie transférée ≠ stockée** (EXT-9) : ~16 000 items, transfert ~100-200 Go (blocs
  COG 1024² → sur-lecture ×2-15, non mesuré finement), 15-30 h séquentiel. O4/O5 doivent
  distinguer octets transférés / stockés / requêtes. Éclaire Q-C.
- **Contrat search→ingest implicite** (COV-3) : `ingest --acquisitions <json>` à ajouter
  (sinon le workflow CWL refait la recherche → O2 de l0-06 compromis) ; O2 exige aussi deux
  `data_root` distincts (EFF-4 : l'idempotence rend « mêmes comptes » impossible sinon).
- **Planche de centrage trop tardive** (EXT-13) : planche précoce (1 chip récent/site,
  ~15 min) validée AVANT le backfill 48 mois ; coordonnées ±1-2 km corrigées à ce moment-là.
- **Requester-pays** (EXT-14) : sélectionner les assets COG `https://`, refuser `s3://` (les
  variantes `-jp2` sont sur bucket payant).
- **Incrémental** (EXT-15/EFF-17) : revisite réelle 2,1-4,6 j selon site (pas ~5 j) — la
  prémisse « runs souvent vides » est fausse (~8-12 acquisitions/jour sur le parc) ; marge
  3 j OK pour la latence (~3-5 h mesurée) mais **aucune détection des publications tardives** →
  rescan périodique (`backfill --months 2`) + le dire en « Non testé ».
- **Gates humains dans les tables d'oracle** (EFF-2) : section « Gate humain (hors run) »
  distincte, règle de flux : la fiche reste en `en-cours/`, le run continue.
- **Oracles sur acquisitions « connues » jamais identifiées** (EFF-6) : geler des item ids
  littéraux dans les fiches avant `a-faire/`.
- **Hygiène** : `just check` dans chaque oracle (DEC-10) ; modules core/adapters nommés dans
  l0-04/05/06 (COV-14) ; invariant logs-STDERR décliné (COV-7) ; deps Pillow + cwltool à
  arbitrer (COV-5/EFF-18) ; références `LOT0-fiche-sites.md` → `docs/lots/lot-0-sites.md`
  (COV-10) ; contradiction « un an minimum » dans lot-0-sites §1 (COV-11) ; oracle l0-01
  durci ids/8-9-8 (COV-12/EFF-11) ; contradiction C08 DoD vs Notes (EFF-12) ; barème S/M/L à
  définir dans la méthode (EFF-20 — amélioration kit, à reporter) ; CDSE = acter hors Lot 0
  avec abstraction `StacSource` en DoD de l0-02 (COV-6) ; pré-filtre scène 80 % : décision à
  tracer + comptage des écartés (COV-2/EXT-16 partiel).

## Graphe de dépendances cible (post-scission)

```
l0-01-sites-config    []           + config applicative + grilles cibles + taxonomie CLI
l0-02-stac-search     [l0-01]      + assets réels + StacSource + item ids gelés
l0-03-chip-ingest     [l0-02]      + manifests.py + clé item_id + SCL 2 compteurs + smoke replay + planche précoce
l0-04a-outillage      [l0-03]      backfill/report/contact-sheet + tests fixtures  ─┐
l0-05-incremental     [l0-03]      ‖ parallélisable                                 ├─ après correctifs C3 + SEQ-8
l0-06-cwl-steps       [l0-03, l0-05 si tool update conservé]  ‖                    ─┘
l0-04b-recette        [l0-04a]     campagne réelle 25×48 + gate humain Philippe (hors run)
```
⚠ Parallélisation conditionnée à : contrat manifeste gravé (C3), auto-découverte des
sous-commandes dans `__main__.py`, `pixi.lock` régénéré au merge (jamais mergé).

## Questions nécessitant un GO Philippe

| # | Question | Recommandation |
|---|---|---|
| G1 ⚠ irréversible | Bandes : ajouter `nir08/swir16/swir22` (20 m, fichier séparé) pour le Lot 1 ? | **OUI** (+50 % stockage, évite ré-ingestion 100-200 Go) |
| G2 | SCL conservé en sortie (fichier 20 m à côté du chip) ? | **OUI** (exigé par lot-0-sites O3, nécessaire au Lot 2) |
| G3 | Scission l0-04a/04b + graphe ci-dessus | **OUI** |
| G4 = Q-A | pystac-client | **OUI** (défaut confirmé par l'usage réel de l'API) |
| G5 = Q-B | GeoTIFF simple (pas COG) | **OUI** |
| G6 = Q-C | Backfill : pool 4-8 workers d'emblée (15-30 h → ~3-5 h) | **OUI** (mesuré, ~15 lignes) |
| G7 = Q-D | CWL : validation locale cwltool seule, enregistrement PID-FLOW hors lot | **OUI** |
| G8 | Multi-tuiles : tuile de référence par site + garde nodata (pas de mosaïque) | **OUI** (KISS ; à vérifier sur C07 au 1er chip) |
| G9 | Clé de stockage = item id STAC | **OUI** |
| G10 | C08 zone témoin : candidat à proposer en maturation de l0-01 | à trancher avec la fiche |

## Sous-énoncés corrigés par la réfutation (ne pas propager)

Pas de mélange de baselines dans la fenêtre actuelle (mesuré) ; le pré-filtre 80 % économise
réellement sur sites nuageux ; marge nette incrémentale ≈ 3 j (latence ~3 h, pas 2 j) ;
volumes revus À LA HAUSSE (16 000 items, 324-1383/site) ; rien n'est en `fait/` (preuve de
SEQ-12 fausse, fond valide). Non vérifié par la revue : facteur de sur-lecture COG exact,
liste de bandes Clay précise, délai réel des retraitements tardifs.

## Prochaines actions

1. GO Philippe sur G1-G10 (G1 en premier — il conditionne l0-03).
2. PO : réécriture des fiches (scission 04a/04b, correctifs C1-C5 + majeurs), roadmap figée v2,
   corrections lot-0-sites.md, report des améliorations kit (barème S/M/L, gate humain).
3. Re-passage « Prêt à faire » fiche par fiche → `a-faire/` → l'équipe enchaîne en `/run`.
