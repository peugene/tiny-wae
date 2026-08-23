---
id: rep-01
titre: "Trois défauts d'affichage de report : ratio faussé par les relances, O1 non vérifiable, mauvaise classe SCL mise en avant"
effort: S
categorie: rapport
phase:
depends_on: [data-01]
parent:
subtasks: []
---

# [rep-01] — Le ratio publié par `report` est faussé par les relances

> Fiche de backlog : sert de **brief (prompt)** pour l'IA.
> Avancement = dossier : `maturation/` → `a-faire/` → `en-cours/` → `fait/`.

## Objectif

Deux défauts d'**affichage** de `report`, relevés le 2026-08-23 pendant la lecture de
jugement de la recette du Lot 0 (`l0-04.H`). **La donnée est saine dans les deux cas** —
c'est sa présentation qui est fausse, d'où l'effort S et l'absence de caractère bloquant.

1. **Le ratio `ingested / found_tile` est faussé dès qu'un site a été relancé.** Il mélange
   un numérateur stable (les items ingérés une fois pour toutes, par idempotence) et un
   dénominateur qui grossit à chaque run. La section « Pires cas en tête », qui trie sur ce
   ratio, publie donc un **classement faux**.
2. **La colonne `skipped_asset_scheme` n'est pas affichée** alors qu'elle est entrée dans
   l'identité de conservation avec `data-01`. Conséquence : l'oracle **O1 n'est plus
   re-vérifiable à la main** depuis le tableau publié.
3. **La section « Classes SCL agrégées » met en avant la MAUVAISE classe** (trouvé par
   Philippe le 2026-08-23). `SCL_HIGHLIGHT_CLASSES = ("2", "11")` est commenté
   « 2 = ombre de nuage » — c'est faux : dans la table de classification de scène
   Sentinel-2 L2A, **2 = ombres portées du relief** (*topographic casted shadows*) et
   **3 = ombres de nuage** (*cloud shadows*). Le rapport publie donc l'ombre de terrain,
   statique et prévisible, et **tait l'ombre de nuage** — précisément celle qui fabriquera
   de faux changements au Lot 2. Mesuré sur le corpus : **classe 3 à 0,74 %** des pixels
   contre **classe 2 à 0,24 %**. On met en avant la plus petite ET la moins pertinente.

## Contexte et périmètre

### Constat mesuré (compte-rendu, PAS un oracle)

Sur le rapport de la campagne 25×48 régénéré le 2026-08-23 :

| Site | Ratio publié | Ratio réel (corpus distinct) | Rang publié | Rang réel |
|---|---|---|---|---|
| A03 Sizewell | 14,5 % (169/1162) | **38,0 %** (169/445) | **1er (pire)** | 5e |
| B01 NEOM | 45,8 % (570/1245) | **92,2 %** (579/628) | 12e | **25e (meilleur)** |
| A01 ITER | 24,8 % (191/770) | **65,3 %** (194/297) | 6e | 15e |

Le site présenté comme le pire du parc ne l'est pas, et le meilleur site du parc est publié
au milieu du classement. Les sites intacts sont ceux qui n'ont jamais été relancés — le
défaut est donc **invisible tant qu'on ne relance rien**, ce qui explique qu'il ait passé
les fiches `l0-04.x`.

Sur le second point : recalculée depuis le tableau publié, l'identité O1 montre un écart de
5 (un par site touché par `data-01`). L'identité vraie, avec le 4e terme, boucle :
`21426 = 3993 (ssc) + 3935 (off_tile) + 13493 (found_tile) + 5 (skipped_asset_scheme)`.

### ⚠ Ancrage dans le code réel (vérifié le 2026-08-23, HEAD `189b0cb` ; **revérifié au
dispatch à HEAD `5b2beff` — `git diff 189b0cb..HEAD -- src/ tests/` vide, l'ancrage tient**)

- **La cause est nommée dans le code lui-même.** `adapters/manifests.py::aggregate_counters`
  porte en docstring : *« Somme les compteurs de tous les runs d'un site — donnée de VOLUME,
  pas de complétude. ⚠ Sur-compte dès que des runs se recouvrent […] cette fonction ne
  prétend PAS dédupliquer. »* C'est l'**arbitrage n°2 du 21/08**, rappelé en tête du module.
  Le défaut n'est pas ce sur-comptage — il est **voulu et correct** pour le tableau de
  volume : il est qu'une donnée de volume est réutilisée comme **taux**.
- `core/report.py:91` — `SiteReport.ingested_ratio` calcule
  `counters["ingested"] / counters["found_tile"]`, donc **sur le `counters` sur-comptant**.
- `core/report.py:332` — `render_report` trie la section « pires cas » sur `r.ingested_ratio`.
- `core/report.py:245` — `_worst_case_line` réaffiche `ingested/found_tile` et les causes,
  toutes prises dans `counters`.
- ⭐ **Le correctif ne demande AUCUNE I/O nouvelle.** `build_site_report`
  (`core/report.py:187`) reçoit déjà `manifests: Sequence[ManifestLike]` — la liste
  complète des manifestes du site, un par item **distinct** — et en extrait déjà
  `ingested = [m for m in manifests if m.status == "ingested"]` (ligne 205) pour le contrôle
  d'intégrité. Le numérateur et le dénominateur distincts sont donc **déjà en main**.
- `adapters/manifests.py::item_ids_for_site` documente la même distinction et sert déjà de
  référence exacte pour la complétude (O2) : c'est la doctrine du projet, on l'applique ici.
- `core/report.py:113` — `check_conservation` compte bien les **4** termes
  (`skipped_scene_cloud + off_tile + found_tile + skipped_asset_scheme`) : le verdict `OK`
  du tableau est juste. Seul l'**affichage** omet la colonne.
- `core/report.py:278` — la ligne d'en-tête du tableau markdown est écrite en dur ; c'est là
  que la colonne manque.
- `core/report.py:25` — `SCL_HIGHLIGHT_CLASSES: tuple[str, ...] = ("2", "11")`, précédé du
  commentaire faux en `report.py:24`.
- `core/report.py:336` — le titre de section réécrit le même libellé faux **en dur** :
  `"## Classes SCL agrégées (2 = ombre de nuage, 11 = neige — instrument V3)"`. Il ne dérive
  PAS de la constante : c'est la cause structurelle de la dérive, deux sources de vérité pour
  un même fait.
- ⭐ **Aucune donnée n'est perdue, et aucune ré-ingestion n'est nécessaire.**
  `core/report.py:341` agrège `scl_totals` sur **toutes** les classes présentes dans les
  manifestes ; seul l'**affichage** est filtré par `SCL_HIGHLIGHT_CLASSES` (`report.py:344`).
  La classe 3 est donc déjà dans le corpus du 23/08 et ressortira au premier `report` qui
  suivra le correctif.
- Les deux seuls usages de la constante sont sa déclaration et cette boucle d'affichage
  (`grep SCL_HIGHLIGHT_CLASSES` sur `src/ tests/ scripts/` : 2 occurrences, aucune en test).
  Le filtre nuages du pipeline n'en dépend pas — il vit dans `core/`/`adapters/` d'ingestion
  et travaille sur ses propres classes ({0,1} invalides, {3,8,9,10} nuages). **Cette fiche ne
  touche donc PAS au filtrage, seulement au rapport.**

⚠ **Fait mesuré à ne pas chercher à réconcilier** : sur A01, le nombre de manifestes sur
disque (297) diffère de `found_tile − skipped` (770 − 478 = 292), et `rejected_clouds`
agrégé (101) est inférieur au compte disque (103). Des journaux de runs interrompus
manquent. **C'est précisément pourquoi le compte de manifestes fait foi** (même arbitrage
n°2 que pour la complétude) : il est exact par construction, la somme des journaux non.

### ⭐ Décisions actées

- **D1** — Le ratio et le classement se calculent sur le **corpus distinct**, jamais sur
  `counters`. Numérateur : nombre de manifestes de statut `ingested`. Dénominateur :
  `len(manifests)`, soit le nombre d'items **distincts** instruits ayant atteint l'écriture.
- **D2** — `SiteReport` gagne deux champs explicites **nommés `distinct_ingested` et
  `distinct_instructed`** (noms ARRÊTÉS, ne pas en inventer d'autres), remplis par
  `build_site_report`.
  `ingested_ratio` est recalculé sur eux. **Ne pas** dériver le dénominateur de
  `found_tile − skipped` : cette soustraction est fausse dès qu'un journal manque (cf.
  ancrage).
- **D3** — Le **tableau de volume reste inchangé** : ses colonnes sont des compteurs de
  volume, correctes comme telles, et O1 en dépend. On ne « corrige » pas `aggregate_counters`.
- **D4** — La colonne **`skipped_asset_scheme`** est ajoutée au tableau, entre `off_tile` et
  `found_tile` (ordre de l'identité O1), pour rendre celle-ci re-vérifiable à l'œil.
- **D5** — `_worst_case_line` affiche désormais le ratio distinct et **libelle ses
  dénominateurs sans ambiguïté** : `ingested/instruits (distincts)` pour le ratio,
  `off_tile=N/found_stac` (volume) pour les causes. Les pourcentages de causes restent
  calculés sur `counters` — ils sont **robustes aux relances**, tout y grossit ensemble.
- **D6** — Le titre de la section devient explicite sur ce qu'il classe :
  « Pires cas en tête (ratio sur corpus distinct — caractéristique de site) ».
- **D8** — `SCL_HIGHLIGHT_CLASSES` devient **`("3", "11")`** : l'ombre de NUAGE remplace
  l'ombre de relief. La classe 2 n'est pas ajoutée en troisième — elle est statique à site et
  saison donnés, elle ne produit pas le faux changement que cette section sert à anticiper.
  Elle reste comptée dans les manifestes, récupérable à tout moment.
- **D9** — Le titre de section **cesse d'être écrit en dur** : les libellés vivent dans un
  seul mapping **nommé `SCL_CLASS_LABELS`** (nom ARRÊTÉ), de contenu exact
  `{"3": "ombre de nuage", "11": "neige"}`, dont dérivent ET `SCL_HIGHLIGHT_CLASSES`
  (= `tuple(SCL_CLASS_LABELS)`) ET le titre de section. C'est ce qui empêche la dérive de recommencer :
  aujourd'hui le libellé faux existe à deux endroits qui s'ignorent (`report.py:24` et
  `report.py:336`).
- **D10** — Aucun emoji dans le code ni dans la sortie console (règle permanente du projet).
  *(ancien D7, renuméroté)*

### Fichiers touchés

- `src/tiny_wae/core/report.py` — `SiteReport` (champs + `ingested_ratio`),
  `build_site_report`, `_worst_case_line`, `render_report` (en-tête et ligne du tableau).
- `tests/test_report.py` — tests des oracles ci-dessous.
- ⛔ **Ne pas toucher** `adapters/manifests.py` : son sur-comptage est volontaire et documenté.

## Définition de « terminé »

- Le ratio et le classement publiés sont ceux du corpus distinct, insensibles au nombre de
  relances d'un site.
- Le tableau affiche `skipped_asset_scheme` et l'identité O1 se revérifie par addition des
  colonnes affichées.
- Les libellés de dénominateurs ne laissent aucune ambiguïté sur ce qui est distinct et ce
  qui est du volume.
- `just check` vert au commit de la fiche.

## Oracle / recette (figé AVANT implémentation)

Tous sur **fixtures**, en mémoire ou en `tmp_path` : le corpus réel de la campagne n'est pas
reproductible en test, et un oracle porte sur une propriété du code **à l'instant présent**.

- **O1 — insensibilité aux relances (l'oracle central).** Fixture : un site à **3 items
  distincts** (2 `ingested`, 1 `rejected_clouds`) et **2 journaux de runs** dont le second
  ne fait que re-voir les items déjà traités (`skipped = 3`). Attendu : ratio publié
  **2/3 = 66,7 %**, et NON `2/6 = 33,3 %`. **Discriminant** : le test échoue si le ratio est
  calculé sur `counters`.
- **O2 — classement.** Fixture à 2 sites : le site X a un meilleur ratio distinct mais plus
  de relances que le site Y. Attendu : X apparaît **après** Y dans « pires cas en tête ».
  **Discriminant** : l'ordre s'inverse si le tri porte sur `counters`.
- **O3 — colonne présente.** L'en-tête du tableau contient `skipped_asset_scheme`, et sur une
  fixture où ce compteur vaut 2, la cellule affiche `2`.
- **O4 — identité re-vérifiable.** Sur une fixture, la somme des colonnes
  `skipped_scene_cloud + off_tile + found_tile + skipped_asset_scheme` **lues dans la ligne
  markdown rendue** égale la colonne `found_stac` de cette même ligne.
- **O6 — la bonne classe SCL est mise en avant.** Fixture : un site dont les manifestes
  portent `scl_class_counts` non nuls sur les classes **2, 3 et 11**, avec trois valeurs
  distinctes. Attendu dans le markdown rendu : une ligne pour la classe **3** et une pour la
  classe **11**, **aucune pour la classe 2**, et le titre de section qui nomme la classe 3
  « ombre de nuage ». **Discriminant** : le test échoue avec la constante actuelle `("2","11")`,
  et échoue aussi si le titre reste écrit en dur (le libellé et la constante doivent provenir
  du même mapping — vérifier en assertant que le titre contient bien les classes de
  `SCL_HIGHLIGHT_CLASSES`, pas une chaîne figée).
- **O5 — non-régression du volume.** Les colonnes de compteurs existantes et le verdict
  `conservation` sont inchangés à fixture identique (les tests actuels de `test_report.py`
  restent verts sans modification de leurs attendus).

**Non testé, explicite** : le corpus réel de la campagne (non reproductible) ; la
distribution mensuelle des observations (hors périmètre) ; l'exactitude de
`aggregate_counters` elle-même (inchangée par cette fiche, et volontairement sur-comptante) ;
la **table de classification SCL** elle-même (fait externe, documenté par l'ESA — la fiche
l'applique, elle ne le teste pas) ; le **filtre nuages du pipeline**, hors périmètre et non
modifié.

---
## Résumé de réalisation

**Faite le 2026-08-23** — agent Sonnet medium en worktree isolé (HEAD vérifié `7496d14`),
commit `88c0733`, mergé en `c78cd8b`. **305 tests** (+5 neufs, +1 assertion corrigée).

### Verdict d'oracle chiffré

| Oracle | Verdict | Mesure |
|---|---|---|
| O1 ratio insensible aux relances | **VERT** | fixture 3 items distincts relancée une fois : ratio = 2/3, pas 2/6 |
| O2 classement sur ratio distinct | **VERT** | site à ratio distinct 0,8 / volume 0,2 passe bien APRÈS un site à 0,3 |
| O3 colonne affichée | **VERT** | `skipped_asset_scheme` dans l'en-tête, cellule à 2 sur fixture |
| O4 identité re-vérifiable | **VERT** | somme des 4 colonnes LUES dans la ligne markdown = `found_stac` |
| O5 non-régression du volume | **VERT** | compteurs, `conservation` et `failed_pct` inchangés à fixture identique |
| O6 bonne classe SCL | **VERT** | classes 3 et 11 rendues, classe 2 absente, titre dérivé du mapping |

### ⭐ Vérification sur le CORPUS RÉEL (au-delà de l'oracle, avant merge)

Le code corrigé a été exécuté sur les 9 873 manifestes de la campagne du 23/08 (sortie hors
`data_root`, corpus non modifié). Trois faits :

1. **Le classement est corrigé** : B08 → A07 → A02 → A04 → A03 en tête, B01 en queue.
   Avant : A03 en tête et B01 au 12e rang.
2. **Les comptes distincts du code coïncident au chiffre près avec un comptage indépendant**
   fait à la main sur le disque (`find <site> -name chip.tif | wc -l`) : B08 63/322,
   A07 112/443, A02 141/448, A04 83/242, A03 169/445, B01 579/628. Deux chemins de calcul
   sans rapport donnent le même résultat.
3. **O1 se revérifie à la main** sur les 25 sites : écart nul en additionnant les colonnes
   affichées. **SCL** : classe 3 = 2 816 348 px (0,742 %) contre 903 143 px (0,238 %) pour
   la classe 2 qui était mise en avant à tort — le rapport publie désormais l'ombre de
   nuage, celle qui produira de faux changements au Lot 2.

### Décisions prises en cours de route

- **Débordement de périmètre assumé et déclaré** : `tests/test_cli_report.py` (1 assertion +
  son commentaire) a dû être corrigé en plus des 2 fichiers prévus. Il portait la **même
  assertion littérale** sur la ligne markdown que `tests/test_report.py`, que D4 change par
  construction ; sans ça le gate restait rouge (mesuré : 1 failed, 304 passed). Mécanique,
  aucune logique nouvelle.
  ⚠ **Ce que ça révèle** : le format d'une ligne de rapport est asserté littéralement à deux
  endroits qui s'ignorent — le même défaut de duplication que D9 corrige côté source. Non
  traité ici (gel des tests du Lot 0, décision Philippe du 23/08), mais consigné.
- **Tension O5 / D4-D8 tranchée par l'agent, correctement** : la lettre d'O5 disait « sans
  modification de leurs attendus », or D4 et D8 changent le format affiché par construction.
  L'agent a tranché en faveur des décisions actées et l'a signalé. C'est un défaut de
  rédaction de mon oracle, pas de son exécution : O5 visait la non-régression des **valeurs
  mesurées** (compteurs, `failed_pct`, `bytes_written` — strictement inchangés), pas
  l'immuabilité du texte des tests.

### Gate

`ruff` (72 fichiers), `mypy` (72 fichiers), `deptry`, **305 tests**, `smoke` vert, `cwltool`
valide. ⚠ `just check` complet ressort **rouge** en local sur `ruff format` — à cause d'un
bloc de code Python dans une fiche **non versionnée** du chantier Lot 1 écrite en parallèle
(`docs/backlog/maturation/lot-1-embeddings/l1-02.2.md`), hors de ce périmètre et non touchée.
Le fichier n'étant dans aucun commit, la CI ne le voit pas.

### Non fait

Le `report.md` du `data_root` n'a **pas** été régénéré — la vérification a écrit ailleurs
pour ne pas toucher au corpus. Il porte donc encore l'ancien classement jusqu'à la prochaine
exécution de `report`.
