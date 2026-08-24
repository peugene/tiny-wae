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
| **Lot 0** | Ingestion Sentinel-2 — 25 sites, 48 mois, puis incrémental quotidien, CLIs orchestrables CWL | **Recette prononcée le 23/08/2026** — 5 793 chips, 15,95 Gio | `docs/backlog/maturation/lot-0-ingestion/` + [lot-0-sites.md](lot-0-sites.md) |
| **Lot 1** | Banc d'embeddings GFM sur CPU (Clay v1.5 + TerraMind) — le banc décide du **périmètre embeddable** | **Chantier en maturation** | `docs/backlog/maturation/lot-1-embeddings/` + [lot-1-embeddings.md](lot-1-embeddings.md) |
| **Lot 2** | Détection de changement : dérive d'embeddings + seuils, vérité terrain = chronologies publiques des sites | À ouvrir | — |
| **Lot 3** | Agent d'interrogation en langage naturel (API Claude actée ; LLM local à terme) | À ouvrir | — |
| **Lot 4** | (optionnel) UI opérateur minimale | À ouvrir | — |

Chaque lot devient un **chantier** du backlog (`docs/backlog/`, méthode
`_methode-backlog.md`) : roadmap → revue adversariale → fiches mûries → `/run`. Les oracles
sont figés avant implémentation.

## Décisions structurantes actées (rappel)

- POC 100 % Python · stack pixi/ruff/mypy/pytest/typer (cf. `_tools_python/reco-stack-python.md`)
- Budget zéro : PC dev + NAS. ⭐ **Décision du 23/08/2026 : pas d'achat matériel** — on fait
  avec la machine existante. Le Lot 1 ne décide donc pas d'une dépense mais du **périmètre
  embeddable**, et mesure les leviers qui permettent de l'élargir
- Hors périmètre POC : entraînement de modèles, Sentinel-1 (V2), multi-utilisateurs, temps réel
- Données : politique Copernicus « free, full and open » — mention « Contains modified
  Copernicus Sentinel data » en cas de publication

## Convention documentaire

Les `.md` de ce dossier sont la source (canal agents) ; les `.html` sont générés pour lecture
humaine. Ne pas éditer les `.html`.

⚠ **Une fiche de lot se régénère par `just lots`, JAMAIS par `just md2html`.** La page
produite par `md2html` s'ouvre normalement — elle a juste perdu sa pastille d'état, son fil
d'Ariane et son précédent/suivant, ce qui ne se voit qu'en comparant. C'est arrivé deux fois.
`just lots` régénère l'index **et** toutes les fiches d'un coup ; seul ce `README.md` passe
légitimement par `md2html`, puisqu'il est rendu dans le corps de l'index.
