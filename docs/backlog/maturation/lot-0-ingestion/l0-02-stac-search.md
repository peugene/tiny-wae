---
id: l0-02-stac-search
titre: Adapter STAC — acquisitions Sentinel-2 par site / fenêtre / nuages
effort: M
categorie: pipeline
phase: O1
depends_on: [l0-01-sites-config]
---

# [l0-02] — Recherche STAC des acquisitions

> Fiche de backlog : brief pour l'IA. En `a-faire/`, ce brief doit être autonome.

## Objectif

Savoir répondre à : « quelles acquisitions S2 L2A couvrent ce site sur cette fenêtre, avec
quelle couverture nuageuse scène ? » — via STAC, sans télécharger un seul pixel.

## Contexte et périmètre

- Source : **earth-search v1 (AWS)**, collection `sentinel-2-l2a` (harmonized). L'URL et le
  nom de collection vivent dans la config/env, PAS en dur (bascule CDSE prévue).
- `src/tiny_wae/adapters/stac.py` : recherche par bbox (dérivée du site : 5,12 km centrés)
  + fenêtre temporelle + filtre `eo:cloud_cover` scène (< 80 % — le filtre fin par chip via
  SCL vient en l0-03). Retourne un type interne `Acquisition` (id, datetime, cloud_cover,
  hrefs des assets B02/B03/B04/B08/SCL) — parse aux frontières, pas de dict brut.
- Bibliothèque : **pystac-client** (Q-A de la roadmap, défaut recommandé — à confirmer en
  revue). Dépendance via pixi.
- CLI : `search --site A01 --from 2022-09-01 --to 2022-10-01 [--json out.json]`.
- **Tests sur fixtures enregistrées** (réponses STAC réelles capturées une fois dans
  `tests/fixtures/stac/`) — aucun test n'ouvre de socket (règle harnais L2).

## Définition de « terminé »

- [ ] `just run search --site A01 --from … --to …` liste les acquisitions (table lisible +
      option JSON pour le chaînage).
- [ ] Type `Acquisition` consommé tel quel par l0-03 (contrat gravé dans le module).
- [ ] Tests fixtures : nominal, fenêtre vide, site inconnu.

## Oracle / recette (figé AVANT implémentation)

| # | Critère mesuré | Seuil de succès |
|---|---|---|
| O1 | Recherche réelle A01 (ITER), sept. 2022 (1 mois) | ≥ 3 acquisitions retournées, hrefs des 5 assets présents |
| O2 | Fenêtre vide (site A01, 1 jour sans passage) | liste vide, exit 0 — pas d'erreur |
| O3 | Tests fixtures | verts, zéro socket ouvert (vérifiable : exécution hors ligne) |

**Non testé par cette fiche** : CDSE en secours (différé — fiche à créer si earth-search
déçoit), contenu des pixels.

## Notes / pistes

Verrous à lever avant `a-faire/` : confirmer Q-A (pystac-client) ; figer le contrat
`Acquisition` exact (relire ce que l0-03 consommera).

---

## Résumé de réalisation

*(à remplir avant de déplacer la fiche dans `fait/`)*
