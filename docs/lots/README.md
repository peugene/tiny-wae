# Lots — feuille de route du POC tiny-wae

**Statut** : document de pilotage (architecte/PO) — source de vérité du lotissement.
**Date** : 21/08/2026 (transféré depuis un dossier de travail hors dépôt, désormais versionné ICI)

---

## Vision

Système de surveillance de sites par imagerie Sentinel-2 : des opérateurs surveillent des
centaines de sites ; l'IA pré-traite, trie, catalogue et alerte ; les sites très actifs
restent en analyse manuelle. Colonne vertébrale technique : **l'embedding par site et par
acquisition** (GFM → pgvector) — catalogage, détection de changement, recherche par
similarité et interrogation NL en découlent. Projet perso.

## Le lotissement

| Lot | Objet | Statut | Où |
|---|---|---|---|
| **Lot 0** | Ingestion Sentinel-2 — 25 sites, 48 mois, puis incrémental quotidien, CLIs orchestrables CWL | **Chantier en maturation** | `docs/backlog/maturation/lot-0-ingestion/` + [lot-0-sites.md](lot-0-sites.md) |
| **Lot 1** | Banc d'embeddings GFM sur CPU (TerraMind/Clay…) — le banc décide de l'achat matériel, pas l'inverse | À ouvrir après recette Lot 0 | — |
| **Lot 2** | Détection de changement : dérive d'embeddings + seuils, vérité terrain = chronologies publiques des sites | À ouvrir | — |
| **Lot 3** | Agent d'interrogation en langage naturel (API Claude actée ; LLM local à terme) | À ouvrir | — |
| **Lot 4** | (optionnel) UI opérateur minimale | À ouvrir | — |

Chaque lot devient un **chantier** du backlog (`docs/backlog/`, méthode
`_methode-backlog.md`) : roadmap → revue adversariale → fiches mûries → `/run`. Les oracles
sont figés avant implémentation.

## Décisions structurantes actées (rappel)

- POC 100 % Python · stack pixi/ruff/mypy/pytest/typer (cf. `_tools_python/reco-stack-python.md`)
- Budget zéro : PC dev + NAS ; achat matériel éventuel décidé par les mesures du Lot 1
- Hors périmètre POC : entraînement de modèles, Sentinel-1 (V2), multi-utilisateurs, temps réel
- Données : politique Copernicus « free, full and open » — mention « Contains modified
  Copernicus Sentinel data » en cas de publication

## Convention documentaire

Les `.md` de ce dossier sont la source (canal agents) ; les `.html` sont générés
(`just md2html <src> <dest> "Titre"`) pour lecture humaine. Ne pas éditer les `.html`.
