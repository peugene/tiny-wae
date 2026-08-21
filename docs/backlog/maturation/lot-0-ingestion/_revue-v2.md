# Revue adversariale v2 — Chantier Lot 0 Ingestion (fiches réécrites du 21/08)

**Date** : 21/08/2026 · **Protocole** : identique à la v1 (5 angles Opus aveugles + réfuteur
Opus indépendant, vérifications API earth-search + docs TerraMind/Clay refaites).
**Mission double** : vérifier l'ABSORPTION des findings v1, puis passe adversariale fraîche.

**Chiffres** : ~89 findings bruts → 84 examinés en réfutation → **72 confirmés (86 %),
12 partiels, 0 réfuté en bloc** ; 5 sous-assertions réfutées ; **4 findings nouveaux
découverts par le réfuteur**. (v1 pour mémoire : 52/16/0.)

## Verdict global

**Le chantier n'est toujours pas prêt pour `a-faire/`** — mais le diagnostic a changé de
nature. La v2 a réellement absorbé l'essentiel de la v1 (scission 04a/04b, clé item_id,
assets réels, gates humains sectionnés, `just check` 7/7, ratio au lieu du seuil absolu,
C08, Q-D…). Les défauts restants sont de trois ordres : (1) **deux récidives structurelles**
— l0-03 a regonflé jusqu'à devenir ce qu'on reprochait à l0-04, et le contrat manifeste
reste troué (`off_tile`/`skipped`/`run.json` sans API) ; (2) **une impasse technique non
tranchée** — la « cassette » de rejeu des fenêtres COG n'est pas réalisable telle qu'écrite
(GDAL/vsicurl échappe aux mocks Python) ; (3) une **rafale d'incohérences de rédaction**
(roadmap vs frontmatters, verrous, conventions bbox/tuile mélangées) — nombreuses mais
locales. Les corrections tiennent en une passe de maturation v3.

## Les 7 critiques (classement du réfuteur)

1. **SEQ2-6 — idempotence vs correction de grille** *(nouveau, le plus grave)* : corriger
   les coordonnées d'un site change sa grille mais pas les `item_id` → les chips
   pré-correction sont skippés à JAMAIS ; l'oracle d'intégrité de la recette (l0-04b/O3)
   échoue par construction sur tout site corrigé, et la taxonomie figée n'a ni `--force` ni
   purge. → Signature de grille dans le manifeste + `ingest --force` + planche précoce sur
   data_root jetable. *(Correction PO)*
2. **EFF2-3 + EFF2-9 — le smoke `--replay` est techniquement impossible tel qu'écrit** :
   rasterio lit via GDAL/libcurl en C — vcrpy/pytest-socket ne l'interceptent pas. Et O7
   exempte le smoke du `--disable-socket` : la propriété « hors ligne » n'est instrumentée
   par rien. → **Décision D-a** ci-dessous.
3. **Cluster B — contrat manifeste troué (récidive C3)** : `off_tile` sans statut, `skipped`
   impossible en lecture de manifestes (fixture 7/14 incohérente), `run.json` sans schéma ni
   API, `found` bivalent selon la forme d'appel. *(Correction PO)*
4. **EXT2-5/8/13 — conventions bbox vs tuile mélangées** : ~16 000 items (bbox) et revisite
   2,1-4,6 j (tuile) dans la même page ; l0-04b/O2 « ±2 % » faux par construction sur C07
   (319 vs 636 = 50 %) ; 50,3 % des granules d'une tuile ne touchent pas le chip (bbox
   obligatoire dans la requête) ; et la règle « tuile majoritaire » choisirait la MAUVAISE
   tuile sur C07 (52TDL, marge 500 m, vs 52TEL, marge 4 160 m). → **Décision D-c**.
5. **EXT2-2 — bandes red-edge manquantes** : Clay v1.5 liste `rededge1/2/3` dans ses 10
   bandes ; TerraMind en attend 12. Les capter maintenant : ×1,41 total (< budget ×1,5
   déjà accordé — le « +50 % » annoncé était faux : la v2 actuelle coûte ×1,22). ⚠ Réfuté
   au passage : ce n'est PAS irréversible (layout item_id → passe ciblée possible plus
   tard) et TerraMind accepte des sous-ensembles — c'est une **optimisation de coût**, pas
   un blocage. → **Décision D-b**.
6. **Cluster A — l0-03 regonflée, gate humain déplacé au goulot** : la planche précoce +
   gate Philippe vivent dans la fiche dont dépendent l0-04a/05/06 ; « le run continue sur
   les fiches parallèles » — qui sont un ensemble vide ; « débloqué au merge » n'existe pas
   dans la méthode. → Scission l0-03a (code) / l0-03b-planche (feuille, gate) + **Décision
   D-d** (règle de flux à graver dans la méthode).
7. **Cluster F — verrous** : V1 nomme 1 item, les oracles en exigent 4 (clair, nuageux,
   sequence=1, C07) ; V2 contradiction roadmap/fiche ; V3 déclaré bloquant à tort
   (deadlock). *(Correction PO — items candidats mesurés par la revue : clair
   `S2A_31TGJ_20240801_0_L2A` (cc<2 %, milieu de fenêtre — l'ancien candidat 2022 sort de
   la fenêtre glissante le 26/09/2026 et son cc réel est 1,5 %, pas 18) ; nuageux
   `S2B_31TGJ_20230315_0_L2A` (cc 88,3 %, cirrus 82,7) ; robustesse S2C
   `S2C_31TGJ_20260513_0_L2A`.)*

## Les 4 findings NOUVEAUX du réfuteur

- **S2C change le schéma d'assets DANS la fenêtre** : `eo:bands[].name` vaut `blue` sur les
  items anciens et `B02` sur les S2C ≥ 2025 (le champ est hétérogène — ne jamais s'y fier) ;
  les S2C portent des assets `cloud`/`snow` en `s3://` → la règle « tout s3:// refusé »
  rejetterait des items VALIDES si elle n'est pas restreinte aux 8 assets mappés.
- **Règle d'épinglage « majoritaire » = mauvaise tuile sur C07** (cf. critique 4).
- **`smoke` est un 9ᵉ point d'entrée** hors de la taxonomie CLI « figée » à 8.
- **`proj:epsg` absent du contrat `Acquisition`** → la garde EPSG est inimplémentable
  depuis le contrat gravé.

## Sous-assertions réfutées (ne pas propager)

« Ni TiM ni génération TerraMind » (faux : sous-ensembles documentés, l'exemple 6 bandes est
couvert) ; « Clay non consommable » (faux en absolu : nb de bandes variable, la spec fixe
vaut pour la comparabilité des embeddings) ; « irréversible » (faux : passe ciblée possible) ;
« eo:bands[].name = blue » comme absolu (hétérogène S2A/B vs S2C) ; l0-04b/O5 « sans seuil »
(il est binaire). Pour mémoire v1 : la fenêtre contient bien PLUSIEURS baselines
(04.00/05.09/05.12) — c'est la *convention d'offset* qui est homogène, la roadmap avait
perdu ce mot.

## Décisions demandées à Philippe

| # | Question | Recommandation |
|---|---|---|
| **D-a** | Mécanisme de rejeu du smoke (l'écrit actuel est infaisable) | **GeoTIFF locaux clippés versionnés (`tests/fixtures/cog/`, ~2-5 Mo) + injection de source via le port `StacSource`** — pas de mock HTTP ; le smoke replay devient un test pur, couvert par `--disable-socket` ; `--live` reste le chemin réel hors gate |
| **D-b** | Rouvrir G1 : ajouter `rededge1/2/3` (20 m) au `chip_20m.tif` (6 bandes) | **OUI** — ×1,41 total, sous le budget ×1,5 accordé ; rend Clay v1.5 nominal ; `coastal`/`nir09` (60 m, fenêtre non entière) restent EXCLUS et documentés |
| **D-c** | Règle d'épinglage de tuile : majoritaire vs marge géométrique | **Marge géométrique maximale** (le chip le plus loin du bord de tuile) — la majorité choisit la mauvaise tuile sur C07 ; départage par majorité en cas d'égalité |
| **D-d** | Règle de flux méthode : « un `depends_on` est levé au MERGE de la dépendance ; une fiche à gate humain reste en `en-cours/` sans bloquer le graphe » — à graver dans `_methode-backlog.md` (amélioration kit, à reporter dans _tools*) | **OUI** + scission l0-03a/l0-03b-planche qui rend le cas rare |

## Corrections PO actées (sans nouveau GO — exécution en v3 des fiches)

Signature de grille au manifeste + `--force`/purge + planche sur data_root jetable (SEQ2-6) ·
contrat complet : statut `off_tile`, schéma+API `run.json` (`read_run`/`aggregate_found`),
`found` défini par forme d'appel, fixture l0-04a refaite (cluster B) · `core/windows.py` et
le runner par site remontés dans l0-03a ; `contact-sheet` regroupé dans l0-03b avec oracle
mécanique (cluster C) · cassette : périmètre A01×1 mois, horloge injectable, `backfill`
testé sur fixtures d'items (cluster D) · roadmap corrigée : graphe 5 niveaux, l0-06 après
l0-05, conventions volumétrie par tuile (~11 000 items), prévisionnel stockage ×1,41
recalculé partout (cluster E + EXT2-3/5) · verrous reclassés : V1 = 3 ids gelés (mesurés) +
corpus fixtures, V2 = donnée d'implémentation, V3 = décision différée documentée (cluster F)
· G5 « GeoTIFF pas COG » + `rasterio` actés dans l0-03, `pyproj` + client HTTP dans l0-01 ·
codes de sortie figés dans l0-01 (0/1/2/3 dont « non concluant ») · `asset_map` redéfini
(logique → clé provider ; libellés B0x documentaires) · garde s3:// restreinte aux 8 assets
mappés + fixture S2C · `proj:epsg` ajouté à `Acquisition` + garde epsg==grille · oracles
réécrits : l0-04b/O1 mécanique (cohérence ratio vs distribution cloud_pct mesurée, sans
clause rédactionnelle), l0-04b/O2 requête témoin littérale ±0, l0-03/O5 règle de repli
pré-décidée (bascule de tuile puis ROUGE), l0-05/O1 témoin positif obligatoire,
`bytes_downloaded` défini (octets HTTP du corps, STAC+assets, par item + agrégé run) ·
`scl_class_counts` agrégé par `report` (instrument de V3) · `StacSource` en DoD l0-02 ·
scale/offset capturés au manifeste · atomicité manifeste (tmp+rename, écrit en dernier) ·
gate humain sorti de la table de lot-0-sites §5 · pré-filtre 95 % documenté dans
lot-0-sites · règle façade : « pixi » purgé des fiches · `.env.example` complet · clés
settings ajoutées (marge, retry, workers, tailles, seuils nodata/invalid) · `pid:Milestone`
et `report.html` : retirés (scope creep) ou actés explicitement · zones partagées complétées
(justfile, tests/fixtures/, settings, pixi.lock jamais mergé — recopié dans les fiches à
dépendances) · Ctrl-C : déclassé en Non testé ou oraclisé · effort l0-05 → M.

## Non vérifié par cette revue

Multi-tuiles des 20 sites non mesurés (extrapolation ~11 000 items) ; exigence réelle de la
génération TerraMind (12 canaux non documenté) ; facteur de sur-lecture COG ; taux de nuages
au grain CHIP (toutes les mesures sont niveau scène — le seuil 15 % de l0-04b/O1 reste une
hypothèse, mesurable via la planche précoce) ; l'assertion GDAL/vsicurl (raisonnement
d'implémentation, non testée empiriquement).
