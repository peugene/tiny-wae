# Roadmap — Lot 0 : Ingestion Sentinel-2 (v4, FIGÉE post-revue v3 + relectures équipe)

> **v4 du 21/08/2026** — absorbe les arbitrages n°1/n°2/n°3 (radiométrie par asset,
> complétude par ensembles, garde nodata instrumentée) et les relectures d'équipe.
> **v3** — restructuration en **chapeaux + sous-tâches** (pattern pid-flow,
> décision Philippe : chaque fiche doit être implémentable par un agent Sonnet effort
> medium en autonomie) et **fiches humaines séparées** (décision Philippe : les gates
> humains existent, comme fiches dédiées `catégorie: humain`, jamais dispatchées — le
> `depends_on` met le run en pause). Intègre D-a (rejeu = GeoTIFF locaux + FixtureSource),
> D-b (chip 20 m à 6 bandes : rededge1/2/3 + nir08 + swir16 + swir22), D-c (tuile de
> référence par marge géométrique) et les corrections PO de `_revue-v2.md`.
> Historique : v1 → `_revue.md` ; v2 → `_revue-v2.md`. Source du lotissement :
> `docs/lots/lot-0-sites.md`.

## 1. Décisions actées (ne pas rouvrir)

Les décisions détaillées vivent dans les CHAPEAUX (l0-01 à l0-06, section « Décisions
portées ») — la roadmap ne les duplique plus, elle les indexe :

- **l0-01** : C08 Bouconne · règle D-c (marge géométrique) · grilles 20 m · codes de
  sortie 0/1/2/3 · auto-découverte CLI, taxonomie fermée de 9 sous-commandes
  (`version` comprise ; `smoke` EXCLU — c'est un script, cf. chapeau l0-01).
- **l0-02** : assets réels (clés stables ; `eo:bands[].name` hétérogène — jamais s'y
  fier) · S2C (schéma différent, garde s3 limitée aux assets mappés, lire `platform`) ·
  collection `sentinel-2-l2a` · filtre tuile dans search (compté `off_tile`) · bbox
  toujours dans la requête · enveloppe JSON versionnée · ⭐ **`found_stac` / `found_tile`
  (décision E-a, 21/08 : deux dénominateurs nommés, le mot `found` seul est banni ;
  invariants de conservation)** · item ids GELÉS (clair 2024 / nuageux 2023 / S2C 2026 —
  mesurés en revue v2).
- **l0-03** : layout `{site}/{item_id}` (G9) · 3 fichiers dont chip 20 m à 6 bandes (D-b,
  ×1,41) et GeoTIFF simple (G5) · SCL-first, 3 statuts de rejet
  (`rejected_clouds`/`rejected_invalid`/`rejected_nodata`), classes 2/11 journalisées
  (décision différée, instrument = report) · idempotence **+ grid_hash** (correction de
  coordonnées → ré-ingestion automatique) + `--force` · retry paramétré au niveau
  requête · ⭐ **instrumentation E-d : `assets_read` = critère d'idempotence (témoins
  positif ET négatif), `content_hashes` = hash du tableau DÉCODÉ (jamais les octets du
  GeoTIFF), `bytes_downloaded` = STAC seul et hors gate, `bytes_written` = seule mesure
  de volume exacte, `--now` retiré d'`ingest`** · rejeu D-a · ⭐ **garde réseau de CONTRAT
  (décision E-b, 21/08) : `TINY_WAE_OFFLINE=1` + refus des hrefs non-`file://` dans
  `chips.py` → `RemoteAccessForbidden` ; `pytest-socket` en ceinture pour le seul chemin
  STAC (il ne couvre pas GDAL — mesuré)** · manifeste + run.json complets avec API.
- **l0-04** : pool workers (G6) · ~11 000 items instruits (`found_tile`) · ⭐ **oracle de
  recette refondu par E-a : 3 critères mécaniques — conservation (identité comptable),
  complétude par **ENSEMBLES d'item_id** (requête témoin reproduisant les 3 filtres :
  bbox + fenêtre + tuile + pré-filtre scène), `failed ≤ 1 % de found_tile`, **intégrité**
  (fichiers/hashes/grid_hash courant/nodata, depuis les manifestes) ;
  `off_tile`/`skipped_scene_cloud`/ratio d'ingestion PUBLIÉS SANS SEUIL (caractéristiques
  de site). La « cohérence statistique » de la v3 est supprimée : non calculable et
  circulaire** · report = seul instrument, testé sur comptes connus, porte aussi
  `--check-completeness`.
- **l0-05** : marge 3 j (config) · rattrapage mensuel documenté non automatisé · cron =
  infra Philippe.
- **l0-06** : Q-D = validation locale seule (G7) · 3 tools + 1 workflow, liste fermée ·
  `pid:Milestone` retiré (hors lot) · `just cwl` dans le gate, impact cwltool assumé.
- Transverses : logs STDERR / données STDOUT-JSON ou fichiers · aucune IA · hors lot :
  S1, recalage sub-pixel, radiométrie fine, mosaïque, enregistrement PID-FLOW, CDSE ·
  fiches HUMAINES : `categorie: humain`, préfixe titre `[HUMAIN]`, bandeau ⛔, jamais
  dispatchées (règle également à reporter dans la commande `/run` du kit).

## 2. Graphe (6 chapeaux · 18 sous-tâches agent · 2 fiches humaines)

⭐ **Grain du graphe — décision Philippe E-c (21/08)** : **seules les fiches dispatchables
ordonnent le run**. Un **chapeau** a `depends_on: []` et n'ordonne rien (sa place dans la
chaîne est écrite en prose dans son corps, et ci-dessous à titre indicatif) ; une fiche
**humaine** porte un `depends_on` et **bloque volontairement** ses dépendants. Un
`depends_on` est **satisfait quand la fiche visée est en `fait/`** — pas d'autre critère.
**Clôture de D-d** (restée ouverte depuis la revue v2, d'où sa réouverture en v3) : sa
première moitié (« une fiche à gate humain reste en `en-cours/` sans bloquer le graphe »)
est **REJETÉE** — remplacée par les fiches humaines séparées et bloquantes ; sa seconde
moitié (« levée au merge ») est **REJETÉE** — le dossier fait foi, un seul critère.

**Graphe RÉEL, dérivé des frontmatters** (généré, pas dessiné — geste PO de la revue v3 ;
`just dashboard` contrôle désormais sa cohérence à chaque génération). Niveaux
topologiques, `⛔` = fiche humaine :

```
N0  l0-01.1
N1  l0-01.2 · l0-03.1 · l0-03.2
N2  l0-01.3 · l0-02.1 · l0-05.1
N3  l0-02.2 · l0-03.3
N4  l0-03.4
N5  l0-03.5 · l0-06.1
N6  l0-03.6 · l0-03.7 · l0-04.1 · l0-05.2
N7  ⛔ l0-03.H · l0-04.2 · l0-06.2
N8  ⛔ l0-04.H
```

**Profondeur : 9 niveaux, largeur moyenne 2,2** (les fiches d'un même niveau sont
parallélisables une fois leurs dépendances satisfaites). Feuilles : `l0-04.H` (recette),
`l0-06.2`, `l0-03.7`. ⭐ **18 fiches sur 20 s'enchaînent sans aucune intervention
humaine** : `l0-03.H` n'a qu'un dépendant (`l0-04.H`, une feuille), donc les deux gates
sont groupés à la toute fin — c'est le comportement voulu, pas une contrainte subie.

Corrections successives apportées à ce graphe (revue v3 + passe PO du 21/08) :
`l0-01.3` n'était déclarée par personne (les grilles seraient restées vides) ·
`l0-03.6`/`l0-04.2`/`l0-05.2` consomment le corpus de `l0-03.5` · `l0-06.1` emballe aussi
le CLI `search` (`l0-02.2`) · l'arête inversée `l0-02.1 → l0-02.2` (pytest-socket) est
supprimée par la **pré-pose de toutes les dépendances en l0-01.1** · `l0-03.1` et
`l0-02.1` sont **desserrées** (grille synthétique et tuile littérale dans leurs tests
plutôt que `sites.yaml` réel) : deux niveaux gagnés sur le chemin critique.

**Zones partagées** (une seule fiche propriétaire chacune, plus de conflit possible) :
`pyproject.toml` → **l0-01.1 seule** (les 8 dépendances y sont pré-posées) ·
`__main__.py` → l0-01.2 seule (auto-découverte ensuite) · `scripts/smoke.py` → l0-03.4
(minimal) puis l0-03.7 (complet) · `justfile` → l0-01.3 (survey-tiles) · l0-03.7 (smoke) ·
l0-06.1 (cwl) — tous séquentiels au graphe · `cli/contact_sheet.py` → l0-03.6 puis
l0-04.2 (extension actée) · `tests/fixtures/` → l0-02.1 (stac) · l0-03.2 (manifests) ·
l0-03.5 (cog) — sous-dossiers disjoints · `pixi.lock` versionné mais **jamais mergé**
(régénérer sur la branche cible).

## 3. Pièges transverses (mesurés — cf. revues)

Multi-tuiles fréquent (A03, A04, C07 sur 7 sondés) · ~50 % des granules d'une tuile ne
touchent pas le chip (bbox obligatoire) · baselines multiples DANS la fenêtre (04.00 →
05.12) mais convention d'offset homogène (journalisée) · S2C en production (nouveau
schéma) · l'item de référence 2022 sortait de la fenêtre glissante fin sept. 2026 → ids
gelés en 2023/2024/2026 · Hinkley ~16 % de scènes < 30 % de nuages (niveau scène ; le
taux chip sera mesuré par la campagne) · volumétrie : ~11 000 items (par tuile), transfert
50-100 Go ≠ stocké ~×1,41 · revisite 2,1-4,6 j → l'incrémental n'est pas « souvent vide ».

## 4. Verrous

**Aucun verrou bloquant restant.**

- **V1 — item ids gelés** : les 3 du chapeau l0-02 (clair `S2A_31TGJ_20240801_0_L2A`,
  nuageux `S2B_31TGJ_20230315_0_L2A`, S2C `S2C_31TGJ_20260513_0_L2A`), **plus** le
  `sequence=1` (`S2A_31TGJ_20260813_1_L2A`, mesuré en revue v3) et **la fixture bi-tuile
  C07**, tous deux entrés au périmètre de l0-02.1 / l0-03.5 lors de la passe PO du 21/08
  (ils manquaient : la roadmap annonçait « aucun verrou » alors que 2 oracles en
  dépendaient). ⚠ **Adressage par id et par fenêtre absolue** dans `record_fixtures.py` :
  deux de ces items sortiront de la fenêtre 48 mois glissante (le nuageux le 15/03/2027).
- **V2** — donnée d'implémentation (l0-01.3, fiche à réseau assumée, avec sa source
  d'emprise de tuile désormais spécifiée).
- **V3** — décision différée documentée (instrument : agrégat `scl_class_counts` du
  report, l0-04.2) ; une fiche de décision sera créée en maturation après la campagne.

## Annexe A — Les 25 sites

Inchangée depuis la v2 (GO 20/08 + C08 Bouconne 43.628, 1.217 GO 21/08) — voir
`docs/lots/lot-0-sites.md` §3, désormais l'unique copie de la liste (la duplication
roadmap/lot est supprimée : le lot fait foi).
