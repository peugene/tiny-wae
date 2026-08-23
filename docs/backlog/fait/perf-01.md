---
id: perf-01
titre: "Réglages GDAL pour la lecture des COG distants"
effort: S
categorie: performance
phase:
depends_on: [l0-03.3]
parent:
subtasks: []
---

# [perf-01] — Réglages GDAL pour la lecture des COG distants

> Fiche de backlog : sert de **brief (prompt)** pour l'IA.
> Avancement = dossier : `maturation/` → `a-faire/` → `en-cours/` → `fait/`.

## Objectif

La campagne d'historique du 2026-08-23 a mesuré que la lecture des COG distants passait
l'essentiel de son temps en **requêtes HTTP inutiles**, faute de configurer GDAL. Cinq
variables d'environnement, posées à la main sur la ligne de commande, ont fait passer le run
complet de **~21 h à 6 h 13**.

Ces réglages n'existent aujourd'hui **nulle part dans le dépôt** : ils ont été tapés dans un
shell et sont perdus. Il faut les poser dans le code, pour qu'ils s'appliquent quel que soit
l'appelant — et en particulier **sous PID-FLOW, où l'invocation est produite par le moteur et
où l'environnement du worker n'est pas maîtrisé**.

## Contexte et périmètre

### ⚠ Ancrage dans le code réel (vérifié le 2026-08-23, HEAD `690e899`)

- **Aucun réglage GDAL n'existe** : `grep -rn "GDAL_\|CPL_\|VSI_\|rasterio.Env\|AWS_"` sur
  `src/`, `config/`, `.env.example` et `justfile` ne rend **rien**.
- **Il n'existe qu'UN point d'ouverture de raster distant** : `adapters/chips.py::_read_window`
  (l. 105-121), qui fait `_guard_href(href)` puis `with rasterio.open(href) as src:`.
  `_write_geotiff` (l. 178) ouvre en écriture, en local — hors sujet.
- **Mesures de la campagne** (journaux `run.json`, `duration_s` et `assets_read` réels,
  mêmes sites A01-A06 avant/après, donc comparables) :

  | régime | n | s/asset | assets/min | s/fenêtre |
  |---|---|---|---|---|
  | 6 workers, défauts GDAL | 77 | 10,5 | 31,6 | 303 |
  | 13 workers, défauts GDAL | 13 | 17,1 | 17,9 | 665 |
  | 25 workers, défauts GDAL | 2 | 36,4 | 7,7 | 458 |
  | **6 workers + réglages** | 27 | **1,3** | **228** | **36** |

- **Ce que les réglages ont AUSSI supprimé** : les coupures de connexion. 3 retries urllib3
  (`SSLEOFError`, `RemoteDisconnected`) en 55 s à 25 workers ; **0 retry sur les 6 h 13** du
  run complet. Les retries étaient un symptôme du volume de requêtes parasites, pas une
  limite d'AWS.
- **Ce qui n'était PAS le goulot**, mesuré et écarté : la bande passante (8,9 Mbit/s
  consommés sur ~74 disponibles, soit 12 %), le CPU (**3,7 %** d'un cœur sur 16 — donc pas
  le GIL), le disque (drvfs mesuré à 35,6 ms/item contre 1,7 ms en ext4, mais 0,03 % du
  temps d'une fenêtre).
- **Le parallélisme ne compensait pas** : ajouter des workers faisait **baisser** le débit
  agrégé (31,6 → 17,9 → 7,7 assets/min). C'est la signature d'une ressource saturée par des
  requêtes inutiles, pas d'un manque de concurrence.

### ⭐ Décisions actées

- **D1 — Les cinq réglages retenus**, exactement ceux qui ont été mesurés :

  | option | rôle |
  |---|---|
  | `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR` | empêche GDAL de lister le « répertoire » S3 à chaque ouverture |
  | `CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.tif` | empêche la recherche de fichiers annexes inexistants (`.aux.xml`, `.ovr`, `.msk`), chacun payé en 404 |
  | `GDAL_HTTP_MULTIPLEX=YES` | multiplexage des requêtes |
  | `GDAL_HTTP_VERSION=2` | HTTP/2 |
  | `VSI_CACHE=TRUE` | cache des blocs déjà lus |

- **D2 — ⚠ L'Env s'ouvre DANS LE THREAD QUI LIT.** `rasterio.Env` pose ses options en
  **thread-local** : un Env ouvert dans le thread principal du CLI ne s'appliquerait **pas**
  aux workers du pool (`adapters/backfill.py` en lance un par site). C'est le piège central
  de cette fiche. Le contexte est donc ouvert **dans `_read_window`**, qui s'exécute
  toujours dans le thread qui fait la lecture.
- **D3 — Les options sont nommées UNE fois**, dans une constante de `adapters/chips.py`,
  jamais recopiées ailleurs (ni dans le justfile, ni dans la doc, ni dans un `.env`).
- **D4 — Aucune variable d'environnement à poser par l'opérateur.** Le but est précisément
  que le réglage survive à une invocation qu'on ne contrôle pas. ⛔ Ne pas se contenter de
  documenter les variables dans le README.
- **D5 — Ne PAS toucher `_guard_href`** : la garde `TINY_WAE_OFFLINE` reste appliquée avant
  toute ouverture, dans le même ordre qu'aujourd'hui.

### Fichiers touchés

- `src/tiny_wae/adapters/chips.py` — constante des options + `rasterio.Env` dans
  `_read_window`.
- `tests/test_chips.py` ou `tests/test_gdal_env.py` — les oracles ci-dessous.

## Définition de « terminé »

- [ ] Les 5 options de D1 sont actives pendant `rasterio.open` dans `_read_window`.
- [ ] Elles le sont **aussi depuis un thread worker**, pas seulement dans le thread principal.
- [ ] Aucune variable d'environnement n'est requise de l'appelant.
- [ ] La garde `_guard_href` s'applique toujours avant l'ouverture.
- [ ] `just check` vert au commit de la fiche.

## Oracle / recette (figé AVANT implémentation)

> ⛔ Aucun oracle de performance : le gate n'a pas de réseau. Le gain est établi par la
> mesure de campagne ci-dessus, pas par un test.

| # | Critère mesuré | Seuil de succès |
|---|---|---|
| O1 | `rasterio.open` monkeypatché pour capturer `rasterio.env.getenv()` au moment de l'appel, depuis le thread principal | les **5** options de D1 sont présentes avec leur valeur exacte |
| O2 | **le même test, mais l'appel lancé dans un `ThreadPoolExecutor`** | les **5** options y sont **aussi** — c'est l'oracle qui garde D2, le seul qui distingue un Env correctement placé d'un Env inopérant |
| O3 | ordre des opérations dans `_read_window` | `_guard_href` est appelé **avant** l'ouverture ; sous `TINY_WAE_OFFLINE=1`, un href `https://` est toujours refusé |
| O4 | les options ne sont écrites qu'à un seul endroit | `grep` des 5 noms dans `src/`, `justfile`, `docs/` : chacun n'apparaît **qu'une fois**, dans `adapters/chips.py` |
| O5 | non-régression | `just check` vert — **276 tests** au départ ; le smoke (fixtures locales en `file://`) passe à l'identique |

**Non testé par cette fiche** (chiffres honnêtes) :

- **Le gain de performance n'est pas testé**, il est *mesuré ailleurs* (campagne du
  2026-08-23). Aucun test du gate ne le rejoue, et aucun ne le protégerait d'une régression.
- **`CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.tif` est un pari** : il rendrait invisible tout asset
  distant dont l'extension n'est pas `.tif`. Tous les assets mappés du projet sont des COG
  `.tif` (les `s3://.jp2` sont déjà refusés en amont par `parse_item`), mais un changement
  de catalogue le casserait silencieusement. Non couvert.
- **Aucune mesure sous cwltool / PID-FLOW** : c'est pourtant le cas d'usage qui motive la
  fiche. À constater lors du premier passage réel.
- **Les autres pistes ne sont pas explorées** : `GDAL_CACHEMAX`, `GDAL_NUM_THREADS`,
  `CPL_VSIL_CURL_CHUNK_SIZE` pourraient encore aider, aucune n'a été mesurée.

## Notes / pistes

Le nombre optimal de workers est à **reposer** une fois cette fiche livrée : les mesures qui
montraient une dégradation au-delà de 6 workers ont toutes été prises avec les défauts GDAL.
Le goulot levé, le point d'équilibre a probablement changé. Ne pas reprendre les chiffres du
tableau d'ancrage comme s'ils valaient encore.

---

## Résumé de réalisation

- **Ce qui a été fait** : constante `GDAL_REMOTE_READ_OPTIONS` dans `adapters/chips.py`
  (les 5 options de D1, valeurs exactes), et `_read_window` ouvre
  `with rasterio.Env(**GDAL_REMOTE_READ_OPTIONS), rasterio.open(href) as src:`.
  `_guard_href` reste appelée avant, dans le même ordre (D5). Aucune variable
  d'environnement n'est requise de l'appelant.

- **Placement du contexte** : dans `_read_window` elle-même (D2), vérifié empiriquement
  avant écriture — `rasterio.env.getenv()` appelé depuis un worker de `ThreadPoolExecutor`
  lève `EnvError` si l'`Env` n'a été ouvert que dans le thread principal. C'est exactement
  le piège que D2 décrivait, et il est réel.

- **Verdict de l'oracle** (5 tests dans `tests/test_chips.py`) :
  - O1 : les **5** options présentes avec leur valeur exacte au moment de l'appel réel à
    `rasterio.open` (espion qui délègue à l'implémentation, pas un mock).
  - O2 : **les 5 aussi depuis un worker de `ThreadPoolExecutor`**. L'agent a vérifié que ce
    test discrimine en déplaçant l'`Env` au niveau module : O1 restait vert (le faux négatif
    classique), **O2 tombait** (`GDAL_DISABLE_READDIR_ON_OPEN : attendu 'EMPTY_DIR', vu
    None`). C'est cet oracle-là qui garde la fiche.
  - O3 : ordre réel `guard` -> `Env` -> `open` ; sous `TINY_WAE_OFFLINE=1` un href
    `https://` est refusé avant toute ouverture.
  - O4 : chacun des 5 noms d'option n'apparaît **qu'une fois** dans `src/`, `justfile`,
    `docs/` hors `docs/backlog/`.
  - O5 : `just check` **vert sur `develop` après merge** — **281 tests** (276 au départ, +5).

- **Écarts par rapport à la fiche** :
  1. **Périmètre du grep O4** : `docs/backlog/` est exclu. La fiche `perf-01.md` cite
     elle-même les 5 valeurs dans son tableau D1 ; sans cette exclusion le critère serait
     structurellement infaisable dès que la fiche existe, et une fiche livrée n'est jamais
     supprimée. Documenté dans le test.
  2. **O3 n'asserte pas une séquence stricte** : `rasterio.open` est décoré en interne
     (`ensure_env_with_credentials`) et pousse un second `Env` imbriqué. L'assertion porte
     sur les premières occurrences, pour ne pas dépendre d'un détail d'implémentation de
     rasterio.

- **Constat annexe utile** : en sabotant `_guard_href`, l'agent a provoqué une vraie
  résolution DNS — ce qui confirme que `--disable-socket` de pytest **ne couvre pas GDAL**.
  La garde `TINY_WAE_OFFLINE` n'est donc pas redondante avec le harnais de test.

- **Non testé** (inchangé) : le gain de performance n'est protégé par aucun test — il est
  mesuré en campagne, et rien ne signalerait une régression. Aucune mesure sous
  cwltool/PID-FLOW, qui est pourtant le cas d'usage motivant la fiche.
  `CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.tif` reste un pari si le catalogue change d'extension.

- **Commit(s)** : `7e9f61d` (implémentation), merge `--no-ff` sur `develop`.
- **Date** : 2026-08-23
