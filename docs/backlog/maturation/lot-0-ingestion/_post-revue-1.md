# Post-revue 1 — Lot 0 Ingestion, après implémentation

**Date** : 22/08/2026 · **Revueur** : architecte/PO (instance Cowork, Opus) — **revue solo,
non adversariale**, à la demande de Philippe. Aucun agent délégué : tous les constats
ci-dessous ont été établis par lecture directe du code livré.
**Objet** : ce que l'équipe a réellement produit en 8 runs, confronté aux fiches et à leurs
oracles figés.
**Base** : `cf2b5ca` (branche `develop`).

---

## Ce qui a été mesuré

| Grandeur | Valeur |
|---|---|
| Fiches en `fait/` | 23 (dont 4 chapeaux) — 1 fiche humaine en `a-faire/` (`l0-03.H`) |
| Code | 34 modules, **4 669 lignes** sous `src/` |
| Tests | 27 fichiers, **238 tests**, **6 656 lignes** — ratio tests/code **1,42** |
| Fixtures versionnées | 187 fichiers, **31 Mo** |
| Runs d'implémentation | 8 (N0 → N8), plus 4 commits de refactor CWL postérieurs |

**Verdict global : conformité élevée.** Sur les oracles que j'ai pu confronter au code, la
correspondance est bonne, y compris sur les critères les plus retors — ceux qui avaient
justement été ajoutés par les revues v1/v2/v3. Les constats ci-dessous portent sur des
**écarts périphériques** : le harnais de CI, la duplication de trois constantes, et une
zone de traçabilité où le backlog ne dit plus la vérité. Aucun défaut fonctionnel trouvé.

### Oracles vérifiés au code, conformes

- **l0-01.3 / O2** — le test `test_o2_c07_choisit_52tel_marge_geometrique`
  (`tests/test_tiles.py:78`) est bien **pur et littéral** : origines ULX/ULY mesurées en
  constantes du module, marges calculées, choix de tuile. Le défaut de la v3 (« un décompte
  ne contient aucune marge ») ne s'est **pas** reproduit — le test le dit même dans sa
  docstring, et O2bis prouve que le décompte ne sert qu'au départage.
- **l0-03.3 / O1bis** — le hash de contenu porte sur `array.tobytes() + EPSG + transform +
  dtype` (`adapters/chips.py:167-179`), **jamais** sur les octets du GeoTIFF. La dérive
  plateforme redoutée est évitée à la racine.
- **l0-03.4 / O5ter** — la règle de repli tuile, ajoutée tardivement en correction PO et
  jamais écrite avant, est implémentée (`adapters/ingestion.py:429`, `cli/ingest.py:101`),
  portée au `run.json` (`adapters/manifests.py:135`) et testée
  (`tests/test_ingestion.py:541`). Elle **signale** sans auto-corriger, comme spécifié.
- **l0-03.2 / O3bis et O4bis** — les deux pièges les plus subtils du chapeau (stabilité du
  `grid_hash` entre `699960` et `699960.0`, et `item_ids_for_site` qui diffère de
  `aggregate_counters` sur des runs recouvrants) ont chacun leur test dédié.
- **l0-02.2 / O3** — l'assertion littérale sur l'URL **et** le mot « injoignable » en STDERR
  est bien présente (`tests/test_cli_search.py:151-160`).
- **Sources uniques déjà tenues** : `cli/exit_codes.py` pour les 4 codes de sortie,
  `core/bands.py` pour l'ordre des bandes, importé par les trois adapters qui en ont besoin.

### À saluer explicitement

Trois pratiques dépassent ce que la méthode exigeait :

1. **La distinction « ✅ exécuté » vs « déclaré »** dans les résumés de réalisation. Les
   oracles live hors gate portent la mention « exécuté, pas déclaré » avec les valeurs
   relevées (l0-06.1, l0-06.2). C'est la différence entre un verdict et une affirmation.
2. **La vérification par mutation.** Plusieurs commits prouvent qu'un test sait rendre
   rouge : « entrée renommée → rouge ; retour à `python -m tiny_wae` → rouge » (`208f79b`).
   Un test qui n'a jamais échoué n'a rien prouvé — l'équipe l'a intégré.
3. **Les commentaires portent le POURQUOI.** Le bloc `[tool.pytest.ini_options]` du
   `pyproject.toml` explique que `--disable-socket` ne couvre pas le chemin GDAL, et
   renvoie à la garde de contrat qui, elle, le couvre. C'est de la connaissance capitalisée
   à l'endroit où elle sera relue.

---

## A. Défauts à corriger

### A1 — ⚠ La définition de « fini » existe à TROIS endroits, et les trois divergent

| Où | Contenu |
|---|---|
| `justfile:99` | `lint && types && test && smoke && cwl` |
| `.github/workflows/ci.yml` | `lint`, `types`, `test` — **ni `smoke`, ni `cwl`** |
| `README.md:16` | « lint + types + tests + smoke » — **oublie `cwl`** |

**Conséquence concrète** : une pull request peut être **verte en CI** avec un smoke rouge
ou un CWL invalide. Le seul garde-fou contre un `.cwl` cassé — `cwltool --validate` sur les
4 artefacts — ne tourne que sur le poste de qui pense à lancer `just check`.

Et rien ne s'y oppose techniquement, j'ai vérifié les deux objections possibles :

- **le smoke ne fait pas de réseau** : `--replay` est le mode par défaut, il pose lui-même
  `TINY_WAE_OFFLINE=1`, lit le corpus de fixtures versionné et écrit dans un
  `TemporaryDirectory` (`scripts/smoke.py`, en-tête et §mode) ;
- **`cwltool` est déjà dans l'environnement** : déclaré en `[tool.pixi.feature.dev…]`
  (`pyproject.toml:80`), donc disponible en CI sans installation supplémentaire.

**Recommandation** : remplacer les trois `- run: just <étape>` de la CI par un unique
**`- run: just check`**. Le harnais cesse alors d'exister en double : la CI rejoue le gate
local, elle ne le redéfinit pas. Corriger au passage la ligne du README. *C'est la règle
« une énumération normative n'existe qu'à UN endroit » appliquée au gate lui-même.*

### A2 — `RUN_STATUSES` est déclaré deux fois, à l'identique

`adapters/manifests.py:52` et `core/report.py:23` portent la même énumération des 6 statuts.
Le commentaire de `report.py` l'assume — « recopiés en ANCRAGE, jamais redéfinis
différemment » — et la raison est légitime : `core/` ne doit pas importer `adapters/`.

Mais **c'est une énumération de domaine, pas d'I/O** : sa place est dans `core/`. Le projet
possède déjà le bon patron, à deux fichiers de là : `BAND_ORDER_10M/20M` vit dans
`core/bands.py` et est importé par `chips.py`, `manifests.py` et `contact_sheet.py`. Les
statuts n'ont pas eu droit au même traitement.

**Recommandation** : déplacer `RUN_STATUSES` et `MANIFEST_STATUSES` dans `core/` (un
`core/statuses.py`, ou à côté du modèle de manifeste), `adapters/manifests.py` les importe.
Le respect des couches est préservé **et** l'énumération n'existe plus qu'une fois. Coût
estimé : une dizaine de lignes. C'est exactement l'incident qui a produit la règle du kit —
il est ici en germe, pas encore réalisé.

### A3 — Le seuil de tuile suspecte est dupliqué en dur dans le message utilisateur

`adapters/ingestion.py:60` définit `_TILE_SUSPECT_RATIO = 0.20`. `cli/ingest.py:103` écrit :

```python
f"⚠ site={site_id} : > {int(100 * 0.20)}% des items de la tuile de référence "
```

Régler le seuil à 0,25 ferait **mentir le message** sans qu'aucun test ne s'en aperçoive :
le message dirait « > 20 % » pendant que le code déclencherait à 25 %. Importer la
constante suffit.

### A4 — Même classe, moindre portée : noms de fichiers et liste de fichiers attendus

`adapters/chips.py:40-41` définit `CHIP_10M_FILENAME` / `CHIP_20M_FILENAME`, mais
`adapters/contact_sheet.py` écrit `"chip.tif"` en dur trois fois (lignes 124, 273, 274), et
`core/report.py:33` re-liste `EXPECTED_FILES`. Renommer un artefact de sortie demanderait
aujourd'hui de le savoir.

---

## B. Traçabilité : le backlog ne dit plus la vérité sur le CWL

### B1 — ⚠ Quatre commits de refactor CWL, hors du cycle de fiches

`e355121`, `13de5f0`, `24b564c`, `208f79b` : le dossier `cwl/` devient
`assets/cwl/{tools,workflows}/<nom>/1.0/`, **toute** expression CWL est supprimée,
`baseCommand` passe de `[python, -m, tiny_wae, …]` à `[tiny-wae, …]`, et `tests/test_cwl.py`
est réécrit (8 → 15 tests). C'est un travail substantiel et, à la lecture des messages de
commit, remarquablement raisonné.

**Mais aucune fiche ne le couvre.** Le dossier `fait/` — qui « fait foi » — ne l'enregistre
pas. Un lecteur du backlog dans six mois ne saura pas que ce refactor a eu lieu, ni
pourquoi le glob du tool `search` est un littéral (la raison, elle, n'existe que dans le
corps du commit `24b564c` : un `$(inputs.…)` perd la sortie **sans erreur** côté PID-FLOW).

### B2 — Les fiches l0-06.1 et l0-06.2 décrivent une arborescence qui n'existe plus

Elles nomment à leur périmètre `cwl/search.cwl`, `cwl/ingest.cwl`, `cwl/workflow.cwl`,
`cwl/update.cwl`, `cwl/README.md` — **aucun de ces chemins n'existe** (vérifié : `find`
ne renvoie que les quatre fichiers sous `assets/cwl/`). Elles annoncent aussi
`baseCommand: [python, -m, tiny_wae, <cmd>]`, remplacé depuis. Le dernier commit touchant
ces deux fiches (`284f540`) **précède** les quatre commits de refactor.

### B3 — Les oracles live de l0-06 n'ont pas été rejoués après le refactor

- **l0-06.1 / O2** : équivalence des ensembles `(item_id, statut)` entre run CWL et run CLI
  direct sur deux `data_root` vierges.
- **l0-06.2 / O2** : après amorçage, le 2ᵉ `cwltool update.cwl` rend `ingested == 0` **et**
  `assets_read == 0`.

Les deux ont été exécutés — les résumés publient les valeurs — mais **sur les CWL d'avant le
refactor**. Après refactor, le commit `208f79b` rapporte un run nominal (`found_stac=3`,
`found_tile=3`, 3 manifestes écrits) : c'est une preuve que « ça tourne », ce n'est ni
l'équivalence, ni l'idempotence. Or le refactor a touché précisément ce qui pourrait les
casser : le chemin d'exécution (`baseCommand`) et la récupération des sorties (le `glob`
littéral).

**Recommandation** (par ordre de coût croissant, l'une des trois suffit) :

1. **Minimum** : rejouer les deux O2 (~30 min, réseau réel) et ajouter un post-scriptum daté
   au résumé des deux fiches, avec les chemins `assets/cwl/…` corrigés au périmètre.
2. **Mieux** : ouvrir une fiche rétroactive `l0-06.3` en `fait/` — « Passage des CWL aux
   conventions PID-FLOW » — avec son propre oracle (les 15 tests de `test_cwl.py`, plus les
   deux O2 rejoués). Le corps des 4 commits fournit déjà 90 % du texte.
3. Traiter le sujet dans la recette du lot (`l0-04.H`), qui rejouera de toute façon la
   chaîne complète.

### B4 — Mineur : un script renommé sans que la fiche le dise

`scripts/record_fixtures.py`, nommé au périmètre de l0-03.5, a été scindé en
`record_cog_fixtures.py` et `record_stac_fixtures.py`. La scission est judicieuse ; la fiche
n'en porte pas trace.

---

## C. Observations de méthode

### C1 — Deux chapeaux affichent « Maturation » pour un travail quasi terminé

`l0-03` (**7 sous-tâches sur 8** en `fait/`) et `l0-04` (2 sur 3) sont toujours dans
`maturation/lot-0-ingestion/`. Le dossier faisant foi, le tableau de bord annonce
« Maturation » pour des chantiers presque clos. Leur place est `en-cours/`.

*Note d'outillage* : le générateur signale désormais mécaniquement le cas symétrique — un
chapeau non clos dont **toutes** les sous-tâches sont en `fait/` apparaît en « ℹ à relire ».
Il ne se déclenche pas encore ici, `l0-03.H` et `l0-04.H` étant ouvertes.

### C2 — Un oracle « figé » a été re-gelé par l'implémentation

La table d'oracle de l0-01.3 annonce des marges « ≈ **495** m vs 4 155 m ». Le test livré
assert `pytest.approx(500.4, abs=5.0)` et `pytest.approx(4159.6, abs=5.0)` : la valeur de la
fiche (495) tombe **hors** de la tolérance du test livré (plancher 495,4).

Rien n'est caché — le résumé de réalisation publie les valeurs mesurées et l'écart est
visible. Mais la table d'oracle, elle, n'a pas été corrigée. Sur un dispositif dont toute la
valeur tient à ce que l'oracle soit **figé avant** l'implémentation, ce genre de détail
décrédibilise s'il se répète. **Recommandation** : quand la mesure infirme un chiffre gelé,
corriger la table d'oracle **et** dire en une ligne pourquoi — plutôt que de laisser le
résumé et l'oracle diverger silencieusement.

### C3 — Le déséquilibre de charge entre chapeaux, à garder pour le lotissement suivant

`l0-03` a porté 8 sous-tâches et `l0-01` en a porté 3. Le calibrage « une fiche = un agent
Sonnet medium » a bien tenu au niveau des sous-tâches, mais le chapeau `l0-03` est devenu un
XL qui a concentré l'essentiel du risque du lot. Au Lot 1, scinder au niveau du chapeau
autant qu'au niveau des fiches.

---

## D. Ce que je n'ai PAS pu vérifier

Par honnêteté sur la portée de cette revue :

- **Je n'ai pas exécuté la suite complète.** Mon environnement ne dispose que de Python
  3.10, or `adapters/ingestion.py:112` utilise la syntaxe générique PEP 695 (`def
  _retry_call[T](…)`), réservée à 3.12+. J'ai exécuté les 13 fichiers de tests
  collectables : **111 tests passés, 0 échec, en 1,56 s**. Les 14 autres n'ont pas pu être
  collectés (import transitif du module 3.12). Le projet en déclare 238 : **je n'en ai donc
  validé que 47 %**, et les 53 % non exécutés couvrent précisément l'ingestion, le backfill,
  l'update, le report et le CWL.
- **Je n'ai rejoué aucun oracle live** (réseau earth-search) ni `just cwl` — `cwltool` n'est
  pas installé chez moi. Les verdicts B3 reposent sur la lecture des messages de commit et
  des résumés, pas sur une ré-exécution.
- **Je n'ai pas audité la justesse géodésique des 25 `reference_tile`** : c'est précisément
  l'objet de la fiche humaine `l0-03.H`, en attente de Philippe.
- **Je n'ai pas évalué les performances ni les volumes réels** : hors périmètre des fiches
  livrées, mesurés par `l0-04.H`.

---

## Plan d'action proposé

| # | Action | Constat | Coût | Qui |
|---|---|---|---|---|
| 1 | CI = `just check` (une seule source), README corrigé | A1 | 10 min | équipe |
| 2 | Rejouer les deux O2 de l0-06 · post-scriptum daté aux fiches | B3, B2 | 30 min | équipe |
| 3 | `RUN_STATUSES` en `core/` · seuil importé · noms de fichiers | A2, A3, A4 | 30 min | équipe |
| 4 | Chapeaux `l0-03`/`l0-04` déplacés en `en-cours/` | C1 | 2 min | équipe |
| 5 | ✅ **Fait le 22/08** — fiche rétroactive **`l0-R1`** (`maturation/l0-R1.md`) | B1 | — | PO |
| 6 | Corriger la table d'oracle de l0-01.3 | C2 | 5 min | PO |
| 7 | **Puis** : `l0-03.H` (revue de centrage), qui débloque `l0-04.H` et la recette du lot | — | — | Philippe |

Les points 1 à 4 sont des corrections mécaniques sans arbitrage.

Le point 5 demandait un arbitrage — **écrire une fiche après coup est un précédent**. Il a
été tranché par Philippe le 22/08 : la fiche `l0-R1` existe, en `maturation/`, purement
documentaire (`categorie: documentaire`, `depends_on: []`) ; l'équipe la déplacera en
`fait/` après avoir rejoué les deux O2 de B3 et posté les post-scriptums de B2. Elle couvre
aussi le 5ᵉ commit hors cycle découvert en la rédigeant — `24680d1`, la wheel incomplète —
qui relève du même sujet : rendre le Lot 0 exécutable par un worker PID-FLOW. La règle,
elle, ne change pas : **la fiche précède le code.**

---

## Conclusion

Le Lot 0 est **livré et solide**. Sur les critères où l'échec aurait coûté le plus cher —
géométrie des chips, idempotence, conservation des compteurs, garde réseau du chemin GDAL —
le code fait ce que les fiches demandaient, et les tests savent rendre rouge.

Le seul risque réel identifié n'est pas dans le code mais dans le **harnais** : le gate qui
tourne en CI n'est pas celui que le projet appelle « fini » (A1). Tant que ce n'est pas
corrigé, la CI donne une assurance qu'elle ne fournit pas.

Le second sujet est la **traçabilité du refactor CWL** (B1-B3) : un travail de qualité mais
invisible du backlog, dont les oracles n'ont pas été rejoués après avoir changé exactement
ce qu'ils vérifiaient.
