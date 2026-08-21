# tiny-wae

**POC Earth Intelligence** — surveillance de sites par imagerie Sentinel-2, embeddings de
modèles de fondation géospatiaux (GFM), détection de changement et interrogation en langage
naturel. Projet personnel.

Projet Python piloté par IA — scaffoldé le 2026-08-21 avec le kit `_tools_python`.

## Démarrage

```bash
cp .env.example .env
just install       # environnement pixi (lockfile)
just db            # PostgreSQL + pgvector (inutile avant le Lot 1)
just check         # lint + types + tests + smoke — le gate
```

## Organisation

- `src/tiny_wae/` — `core/` (métier pur) · `adapters/` (I/O : STAC, stockage, BD) · `cli/`
  (entrées typer — chaque étape de pipeline = un CLI à I/O explicites, orchestrable CWL)
- `docs/backlog/` — pilotage par fiches (statut = dossier) ; `just dashboard` pour la vue
- `justfile` — **la** façade de commandes (`just` pour la liste)
- `.claude/commands/` — `/new-fiche`, `/dashboard`, `/md2html`, `/run`, `/review`

## Conventions

Code en anglais (identifiants et valeurs), commentaires/commits/fiches en français.
`just check` vert avant tout commit. Voir `CLAUDE.md`.

## Feuille de route

Lots à venir (fiches dans `docs/backlog/`) : **Lot 0** ingestion Sentinel-2 (25 sites,
48 mois) · **Lot 1** banc d'embeddings GFM · **Lot 2** détection de changement ·
**Lot 3** agent d'interrogation NL · Lot 4 (optionnel) UI opérateur.
