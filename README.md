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

## Run quotidien (`update`)

`update` interroge, pour chaque site, la fenêtre depuis son dernier manifeste connu
(marge `incremental_margin_days`, 3 jours par défaut) et ingère ce qui est nouveau —
rejouable à l'infini (idempotence héritée d'`ingest`). Commande cron type (une fois par
jour, horloge système — pas de `--now` en production, réservé aux tests déterministes) :

```bash
just run update --sites all
```

Codes de sortie : `0` aucun échec · `1` au moins un échec (ou un site vierge, pointant
`backfill`) avec au moins un succès ailleurs · `3` amont injoignable sur TOUS les sites
(panne réseau, distincte d'un bug — c'est le CLI que personne ne regarde tourner).

⚠ **Rattrapage mensuel, non automatisé** : les retraitements tardifs (`sequence >= 1`)
échappent structurellement à la fenêtre incrémentale. `update` le rappelle sur STDERR
chaque 1er du mois (selon la date injectée) ; le geste reste manuel :

```bash
just run backfill --site <id> --months 2
```

## Conventions

Code en anglais (identifiants et valeurs), commentaires/commits/fiches en français.
`just check` vert avant tout commit. Voir `CLAUDE.md`.

## Feuille de route

Lots à venir (fiches dans `docs/backlog/`) : **Lot 0** ingestion Sentinel-2 (25 sites,
48 mois) · **Lot 1** banc d'embeddings GFM · **Lot 2** détection de changement ·
**Lot 3** agent d'interrogation NL · Lot 4 (optionnel) UI opérateur.
