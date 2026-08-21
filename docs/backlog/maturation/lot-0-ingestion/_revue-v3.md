# Revue adversariale v3 — Chantier Lot 0 Ingestion (structure chapeaux + sous-tâches)

**Date** : 21/08/2026 · **Protocole** : identique aux v1/v2 (5 angles Opus aveugles + réfuteur
Opus indépendant, vérifications API/mesures refaites).
**Objet** : absorption des 72 confirmés de la v2 + passe fraîche sur la restructuration
(6 chapeaux · 17 sous-tâches · 2 fiches humaines).

**Chiffres (réfuteur)** : 45 items examinés → **39 confirmés (87 %), 5 partiels, 0 réfuté en
bloc**, 1 non vérifiable · **~28 défauts DISTINCTS** après dédoublonnage · **6 findings que
les 5 angles ont manqués** · 9 mesures refaites par le réfuteur.
(v1 : 52/16/0 — v2 : 72/12/0.)

## Verdict global

**Pas prêt pour `a-faire/`, mais pour une raison plus étroite que le volume ne le suggère.**
La restructuration a réussi sur le fond : le cluster « l0-03 regonflée » est entièrement
absorbé, les gates humains sont sortis des fiches agent, `just check` est dans 17/17 oracles,
les comptes sont gelés dans les fiches, deux oracles négatifs exemplaires existent, la
hiérarchie `parent`/`subtasks` est rigoureusement cohérente (19/19 appariées, zéro orpheline).
Ce qui reste : **4 décisions** pour toi, et une **passe PO mécanique** dominée par deux
gestes — re-dériver le graphe depuis les corps de fiches, et republier `lot-0-sites.md` en v3.

⚠ **Deux findings ★ ont mesuré juste et conclu faux** (voir §Sous-assertions) : ne pas
reprendre les actions proposées par l'angle « faits externes » sur C2 et C3.

## Décisions demandées (4)

| # | Question | Recommandation |
|---|---|---|
| **E-a** | **Définition unique de `found`** (pré- ou post-filtre tuile) et objet réel de l'oracle de recette. Mesuré : C07 `found`=636 / tuile=319 → `off_tile` = **49,8 %** contre un seuil de 1 % ; A01 = 0 %. Le seuil mesure la géométrie du site, pas le pipeline. Et `cloud_pct` (taux chip, SCL) n'existe pas pour les items `off_tile`/`skipped_scene_cloud` : la « distribution cloud_pct sur found » n'a pas de dénominateur. La fixture canonique du lot elle-même (found=14, off_tile=2) donne 21,4 %. | `found` **post-filtre tuile** partout (enveloppe, run.json, report, contrôle l0-04.H) ; recette = ratio `ingested/found` publié par site **avec dénominateur** + `failed ≤ 1 %` seul ; `off_tile` **publié mais non oraclé** (donnée de site) |
| **E-b** | **Garde réseau du gate — amendement à D-a.** Mesuré par le réfuteur : sous `pytest_socket.disable_socket()`, `rasterio.open("https://…")` atteint le réseau (`CURL error` du proxy, pas `SocketBlockedError`). ⚠ Le mode de défaillance est **l'inverse** de ce qu'annonçait l'angle EXT : sur ta machine connectée, le smoke passerait **VERT en téléchargeant**. | Garde **sur le contrat** : `assert href.startswith("file://")` dans `FixtureSource` + refus explicite dans `chips.read_*` ; O3 réécrit dessus. Monkeypatch socket conservé en ceinture pour le chemin STAC/httpx uniquement |
| **E-c** | **Grain du graphe : chapeau ou sous-tâche ?** `l0-03.subtasks` contient `l0-03.H` et l0-04/05/06 portent `depends_on: [l0-03]` → au grain chapeau, tout l'aval est bloqué par le gate humain ; au grain sous-tâche, presque rien. Deux graphes contradictoires. ⚠ Lié : **D-d n'a jamais été formellement close** (la v2 recommandait « depends_on levé au merge » ; la v3 a adopté l'inverse sans consigner le refus). | **Seuls les `depends_on` de sous-tâche ordonnent le run** ; celui d'un chapeau est documentaire. À graver dans la méthode **et** dans `/run` (le kit ne le dit pas non plus — cf. M5) |
| **E-d** | **Que doit prouver le gate d'idempotence ?** Sous fixtures `file://`, `bytes_downloaded == 0` **dès le 1er run** : les 3 oracles « 2e run : bytes == 0 » sont vrais par construction, sans témoin positif nulle part. Et `--now` de `ingest` est une **option sans effet** (ses 2 formes d'appel ont une fenêtre explicite) — or l0-03.5/O4 teste le déterminisme dessus. | Compteur `assets_read` + `skipped == N` + hash du **tableau décodé** (pas des octets) ; `--now` remonté à `backfill`/`update` seulement ; `bytes_downloaded` = octets HTTP du **seul chemin instrumentable** (STAC), le reste déclaré estimation ou non mesuré |

## Corrections PO (mécaniques, sans nouveau GO)

**Geste 1 — re-dériver le graphe** (clusters C1+C8+C13, une seule cause : les frontmatters
n'ont pas été relus après le redécoupage) : `l0-01.3` n'est déclarée par **personne** alors
qu'elle seule remplit `reference_tile`/`grid` ; 5 arêtes manquantes (l0-05.2→l0-03.5 ·
l0-03.6→l0-03.5 · l0-04.2→l0-03.5 · l0-01.3→l0-01.2 · l0-06.1→l0-02.2) ; 1 arête inversée
(l0-02.1/O5 exige `--disable-socket` livré par son dépendant → remonter `pytest-socket` dans
l0-02.1 ou l0-01.2) ; graphe de la roadmap à régénérer depuis les frontmatters (4 arêtes
fausses, profondeur réelle **8 niveaux**).

**Geste 2 — republier `docs/lots/lot-0-sites.md` en v3** (7 divergences confirmées) : 3 bandes
au lieu de 6 (contredit D-b) · « +50 % » et « ×1,5 » au lieu de ×1,41 · « ~16 000 items » et
« 100-200 Go » au lieu de ~11 000 et 50-100 Go · O2 « aucun site < 15 % » alors que le seuil
n'est plus décisionnel · O1 garde le gate humain **dans la table d'oracle** (correction PO v2
n°38 jamais faite) · pré-filtre 95 % absent (n°39 jamais faite) · en-tête « roadmap v2 ».
C'est le document que l0-01.1 désigne comme unique copie de la liste des sites et où l0-04.H
consigne la recette.

**Geste 3 — remettre le projet au niveau du kit** : le kit `_tools_python` **est à jour** ;
c'est le projet qui est en retard. Recopier `backlog-kit/README.md` →
`docs/backlog/_methode-backlog.md` et `scaffold/templates/commands/{run,new-fiche}.md` →
`.claude/commands/`. ⚠ **Insuffisant seul** (M5) : ni le kit ni le projet ne disent (a)
d'ignorer le `depends_on` d'un chapeau au tri topologique, (b) de fournir le chapeau à l'agent
dans son prompt. Ces deux règles sont à écrire ici **et** dans le kit.

**Autres corrections confirmées** : garde nodata de **G8** sans aucun instrument (pas de
`nodata_pct_max`, pas de champ manifeste, l0-03.3/O3 calcule une fraction qui ne va nulle part
— un critère GO'd est tombé) · `report` doit publier « octets stockés » et « requêtes » : aucun
champ ne les porte et la lecture disque est interdite · doublon
`core/windows.py`/`core/update_bounds.py` avec oracle **littéralement identique**, décision
laissée à l'agent · `aggregate_counters` promet un dédoublonnage par `item_id` alors que
`run.json` ne porte que des scalaires (recouvrement quotidien de 3 j → double comptage de
`found`) · `grid_hash` : sérialisation non spécifiée, signature n'incluant ni bandes ni
tailles (D-b vient pourtant d'en changer 3→6), aucun filtre en lecture, pas de purge ·
`pyproject.toml` zone partagée par 7 fiches, jamais déclarée (recommandation : **pré-poser les
8 dépendances en l0-01.1**) · artefact du gate humain déposé dans un `data_root` gitignoré
d'un worktree supprimé (prescrire un `TINY_WAE_DATA_ROOT` absolu) · règle de repli tuile
(correction PO v2 n°31) : zéro occurrence dans les 25 fiches · `smoke` compté comme 9ᵉ
commande auto-découverte alors que c'est un script (+ `version` = 10ᵉ point d'entrée hors
liste) · code `3 INCONCLUSIVE` jamais décliné dans ingest/backfill/update · oracles
auto-référentiels (l0-02.2/O1 « N de la fixture » sans N gelé ; l0-03.4/O1 teste une copie) ·
seuils non chiffrés (« variance > seuil », « message clair ») · clause non bornée « rejouer »
(l0-06.1/O2) · l0-06.2/O2 faux (`update` va jusqu'à `now`, et `update.cwl` n'expose pas
`--now`) · SIGINT dans le gate sans traiter win-64 · `chip_px_10m/20m` en settings que
personne ne lit · l0-05 chapeau sans section « Décisions portées » · 10/17 sous-tâches ne
mentionnent jamais leur chapeau (l0-03.5 renvoie aux « items gelés (chapeau l0-02) » sans
recopier les 3 ids) · l0-03.5 surchargée (script réseau + corpus + FixtureSource + réécriture
du smoke + mesures live, sur le point de passage unique du graphe) · `skipped_scene_cloud`
produit mais jamais publié, aucune équation de bouclage `found = Σ` · renvois morts
(« l0-03.5/O-mesure », « l0-02.2/O-live ») · DoD « 5 mutations » vs O2 qui en liste 4 · « les
9 clés » suivi de 11 · l0-03.H invoque `survey_tiles.py --sites` inexistant, hors façade
`just` (les deps ne seront pas là) · fixtures annoncées ~2-5 Mo, réel ~25 MiB brut /
12-15 MiB compressés · ids `sequence=1` et C07 bi-tuile toujours non gelés malgré « aucun
verrou restant » — 🎁 **candidat mesuré par le réfuteur : `S2A_31TGJ_20260813_1_L2A`** (réel,
dans la fenêtre, tuile de A01).

## Les 6 défauts que les 5 angles ont MANQUÉS (réfuteur)

1. **`raster_scale`/`raster_offset` sont par ASSET, pas par item** — mesuré : les 10 bandes de
   réflectance ont `0.0001/-0.1`, mais `aot`/`wvp` ont `0.001/0` et `scl` n'en a aucun. Or ces
   champs sont gravés **scalaires** dans `Acquisition` et au manifeste, et c'est la traçabilité
   radiométrique promise au Lot 1. Contrat lossy à requalifier.
2. **Les clés STAC réelles ne sont écrites nulle part** — `s2:processing_baseline`,
   `s2:nodata_pixel_percentage`, **`earthsearch:boa_offset_applied`** (préfixe **vendeur**, qui
   disparaîtra à la bascule CDSE que `StacSource` doit rendre bon marché), `s2:sequence` dont
   la valeur est la **chaîne** `"0"`. L'agent devra deviner.
3. **`--now` de `ingest` est une option morte** et un oracle du gate repose dessus (M3/E-d).
4. **D-d n'a jamais été formellement close** — la v3 a renversé la recommandation v2 sans
   consigner le refus ; c'est la racine de E-c, et la v4 rouvrirait le sujet.
5. **Le geste 3 donnera un faux sentiment de résolution** — le kit lui-même ne couvre ni le
   grain du graphe ni la transmission du chapeau à l'agent.
6. **l0-02.1 exige à l'oracle O4 une fixture bi-tuile (C07) absente de son propre périmètre** —
   et c'est la seule qui teste `off_tile`, au cœur de E-a. Invisible à une analyse de graphe.

## Sous-assertions RÉFUTÉES (ne pas propager)

- **D-c est implémentable** : les origines de tuiles se dérivent bien (coin MGRS 100 km calé
  sur le réseau 60 m — vérifié sur 4 tuiles) et le réfuteur a **reproduit les marges** au mètre
  près (52TDL 509 m / 52TEL 4 151 m). La lacune est **documentaire** (la fiche ne dit pas la
  règle ni la source ; `/aggregate` ne la donne pas, `/search` si) — pas une refonte. L'oracle
  O2 reste néanmoins incohérent (des comptes d'items ne portent aucune marge).
- **Garde socket** : le danger est le **faux-vert** (smoke qui télécharge), pas le faux-rouge.
- **Hash GeoTIFF** : rasterio n'écrit **aucune** chaîne de version GDAL ; le risque réel est le
  WKT PROJ embarqué. Un hash d'octets reste fragile → hasher le tableau décodé.
- « Profondeur 4-5 annoncée » : la roadmap v3 n'annonce aucun chiffre (c'était la v2).
- « l0-05.x parallèle en interne » : sur-lecture du §2.

## Non vérifié par cette revue

Spec de bandes Clay v1.5 (l'ordre `nir` en 4ᵉ vs 7ᵉ — de toute façon déclaré « contrat du
Lot 1 ») · existence réelle de la fixture `S2C_31TGJ_20260513_0_L2A` · comptes des 23 sites non
sondés (~11 000 reste une extrapolation sur 6 points) · SIGINT sur win-64 · quotas earth-search
en charge · facteur de sur-lecture COG · reproductibilité des hashes entre plateformes ·
taux de nuages au grain **chip** (toutes les mesures restent au niveau scène).

## Prochaine étape

GO Philippe sur E-a → E-d, puis passe PO v4 (les 3 gestes + les corrections listées), puis
re-passage « Prêt à faire » fiche par fiche.
