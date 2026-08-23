---
id: rep-01
titre: "Le ratio publié par report est faussé par les relances, et O1 n'est plus vérifiable à la main"
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

### ⚠ Ancrage dans le code réel (vérifié le 2026-08-23, HEAD `189b0cb`)

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

⚠ **Fait mesuré à ne pas chercher à réconcilier** : sur A01, le nombre de manifestes sur
disque (297) diffère de `found_tile − skipped` (770 − 478 = 292), et `rejected_clouds`
agrégé (101) est inférieur au compte disque (103). Des journaux de runs interrompus
manquent. **C'est précisément pourquoi le compte de manifestes fait foi** (même arbitrage
n°2 que pour la complétude) : il est exact par construction, la somme des journaux non.

### ⭐ Décisions actées

- **D1** — Le ratio et le classement se calculent sur le **corpus distinct**, jamais sur
  `counters`. Numérateur : nombre de manifestes de statut `ingested`. Dénominateur :
  `len(manifests)`, soit le nombre d'items **distincts** instruits ayant atteint l'écriture.
- **D2** — `SiteReport` gagne les deux comptes distincts comme champs explicites (p. ex.
  `distinct_ingested` / `distinct_instructed`), remplis par `build_site_report`.
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
- **D7** — Aucun emoji dans le code ni dans la sortie console (règle permanente du projet).

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
- **O5 — non-régression du volume.** Les colonnes de compteurs existantes et le verdict
  `conservation` sont inchangés à fixture identique (les tests actuels de `test_report.py`
  restent verts sans modification de leurs attendus).

**Non testé, explicite** : le corpus réel de la campagne (non reproductible) ; la
distribution mensuelle des observations (hors périmètre) ; l'exactitude de
`aggregate_counters` elle-même (inchangée par cette fiche, et volontairement sur-comptante).
