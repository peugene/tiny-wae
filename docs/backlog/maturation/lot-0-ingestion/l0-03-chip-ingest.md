---
id: l0-03-chip-ingest
titre: Ingestion d'un chip — lecture COG fenêtrée, masque SCL, GeoTIFF + manifeste, idempotent
effort: L
categorie: pipeline
phase: O1
depends_on: [l0-02-stac-search]
---

# [l0-03] — Ingestion d'un chip

> Fiche de backlog : brief pour l'IA. En `a-faire/`, ce brief doit être autonome.
> **C'est la fiche cœur du lot** — et celle qui câble le smoke réel (règle : le gate
> appartient à la fiche qui le change).

## Objectif

Pour (site, acquisition) : produire le chip 512×512 @ 10 m (B02/B03/B04/B08) + le verdict
nuages SCL + le manifeste — ou décider proprement de rejeter (trop nuageux). Relançable à
l'infini sans effet.

## Contexte et périmètre

- `src/tiny_wae/adapters/chips.py` + logique pure dans `core/` (calcul de la fenêtre depuis
  lat/lon, décision de rejet depuis les comptes SCL — testable à sec).
- **Lecture fenêtrée** des COG via rasterio (`rasterio.windows`) : ~512×512 px par bande,
  JAMAIS la scène entière. Dépendances pixi : `rasterio` (conda-forge).
- Masque : classes SCL {3 ombre, 8/9/10 nuages} → % du chip ; **> 30 % → rejet** (seuil
  dans la config). Un rejet EST une sortie : consigné dans le manifeste (pas de chip.tif).
- Sorties : `<data_root>/{site_id}/{YYYY-MM-DD}/chip.tif` (GeoTIFF 4 bandes + tags) et
  `manifest.json` (site, acquisition id, datetime, cloud_pct_chip, statut `ingested` |
  `rejected_clouds`, versions, durée). `data_root` en env (`TINY_WAE_DATA_ROOT`), défaut
  `./data` en dev — le NAS n'est qu'un chemin.
- **Idempotence** : manifeste présent avec même acquisition id → skip silencieux compté.
- CLI : `ingest --site A01 --from … --to …` (enchaîne search → chips, compteurs en sortie :
  ingested/rejected/skipped/failed + dénominateur).
- **Smoke réel** : remplacer `scripts/smoke.py` — `ingest` sur A01, fenêtre de 10 jours
  connue pour contenir ≥ 1 acquisition claire, puis assertions (chip lisible, 4 bandes,
  512×512, manifeste cohérent). ⚠ le smoke fait du réseau réel : il reste hors CI (la CI
  garde lint+types+tests — déjà le cas dans `ci.yml`).

## Définition de « terminé »

- [ ] `just run ingest --site A01 --from … --to …` produit chips + manifestes.
- [ ] Tests : fenêtre/rejet SCL en pur (`core/`), écriture/skip sur fixtures locales.
- [ ] `scripts/smoke.py` remplacé ; `just check` vert de bout en bout.

## Oracle / recette (figé AVANT implémentation)

| # | Critère mesuré | Seuil de succès |
|---|---|---|
| O1 | Chip A01 sur acquisition claire connue | 512×512×4 @ 10 m, géoréférencé UTM, ITER visuellement identifiable (contrôle Philippe sur 1 image) |
| O2 | Acquisition très nuageuse connue | statut `rejected_clouds`, pas de chip.tif, manifeste présent |
| O3 | **Run double** (même commande 2×) | 2e run : 100 % skipped, 0 octet re-téléchargé, sorties identiques |
| O4 | Volume/durée par chip (mesure, pas seuil) | publiés dans le résumé de réalisation (baseline pour l0-04) |

**Non testé par cette fiche** : montée en volume (l0-04), exactitude radiométrique.

## Notes / pistes

Verrous à lever avant `a-faire/` : Q-B (GeoTIFF vs COG — défaut GeoTIFF) ; choisir la
fenêtre de référence du smoke (une date claire sur ITER à repérer via l0-02).

---

## Résumé de réalisation

*(à remplir avant de déplacer la fiche dans `fait/`)*
