---
id: l0-01-sites-config
titre: Config YAML des 25 sites + modèle typé + CLI de validation
effort: S
categorie: pipeline
phase: O1
depends_on: []
---

# [l0-01] — Config des sites de surveillance

> Fiche de backlog : brief pour l'IA. En `a-faire/`, ce brief doit être autonome.

## Objectif

Poser la source de vérité des sites surveillés : un fichier `config/sites.yaml` (25 sites de
l'annexe A de `_roadmap.md`), son modèle typé, et un CLI de validation. Tout le pipeline
aval lit CETTE config — jamais de coordonnées en dur ailleurs.

## Contexte et périmètre

- `config/sites.yaml` : par site — `id` (ex. `A01`), `name`, `lat`, `lon`, `category`
  (`nuclear-construction` | `megaproject` | `stable-watch`), `note` optionnelle.
- `src/tiny_wae/core/sites.py` : dataclass `Site` + validation pure (lat/lon bornés,
  ids uniques, catégorie connue).
- `src/tiny_wae/adapters/sites_io.py` : chargement YAML → `list[Site]` (parse aux
  frontières, cf. principes du kit).
- `src/tiny_wae/cli/` : sous-commande `sites validate` (+ `sites list`) branchée dans
  `__main__.py`.
- Dépendance à ajouter : `pyyaml` (conda-forge, via pixi — arbitrage trivial, acté).

## Définition de « terminé »

- [ ] `config/sites.yaml` avec les 25 sites de l'annexe A (C08 : choisir une zone rurale
      stable ~30 km SO de Toulouse, la documenter dans `note`).
- [ ] `just run sites validate` : OK sur la config livrée, erreur claire sur config cassée.
- [ ] Tests unitaires de la validation (cas passants + 3 cas d'erreur).

## Oracle / recette (figé AVANT implémentation)

| # | Critère mesuré | Seuil de succès |
|---|---|---|
| O1 | `sites validate` sur la config livrée | exit 0, 25 sites comptés |
| O2 | Mutations de test (id dupliqué, lat=95, catégorie inconnue) | exit ≠ 0 + message nommant le site fautif |
| O3 | `just check` | vert (le smoke placeholder reste OK à ce stade) |

**Non testé par cette fiche** : l'exactitude des coordonnées (planche visuelle d'O2, l0-04).

## Notes / pistes

Verrou à lever avant `a-faire/` : choix définitif de la zone C08 (proposer 1 candidat avec
coordonnées, Philippe tranche en revue).

---

## Résumé de réalisation

*(à remplir avant de déplacer la fiche dans `fait/`)*
