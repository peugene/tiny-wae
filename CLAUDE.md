# CLAUDE.md — tiny-wae

Guide pour Claude Code sur ce dépôt. **Ces instructions priment.** Le `~/.claude/CLAUDE.md` global
(porteur cross-projet du style de travail) le complète ; ici = **le projet**. Scaffoldé le 2026-08-21
avec le kit `_tools_python/`.

## ⚠ Multi-instances : zones d'écriture (accord Philippe, 2026-08-21)

Deux types d'instances Claude travaillent sur ce dépôt **en parallèle** :

- **L'architecte/PO** (instance Cowork) écrit UNIQUEMENT dans `docs/backlog/` (rédaction de
  fiches en `maturation/`, régénération du dashboard). Il ne touche jamais à `src/`, `tests/`,
  `scripts/`, et ne fait **ni commit ni push**.
- **L'équipe d'implémentation** (instances Claude Code) écrit dans `src/`, `tests/`,
  `scripts/`, et gère les **déplacements** de fiches (`a-faire/ → en-cours/ → fait/`) ainsi
  que git. Elle ne rédige pas de nouvelles fiches en `maturation/` — sauf fiches **différées**
  pendant un `/run` (règle d'autonomie de la méthode).

Règles : créer un fichier neuf ne conflicte jamais ; ne pas modifier un fichier hors de sa
zone (le signaler plutôt) ; `etat.html` est dérivé et régénérable (dernier écrit gagne, sans
enjeu) ; les caches d'outils (`.pixi/`, `.mypy_cache/`…) restent locaux à chaque instance.

## Vue d'ensemble
tiny-wae — projet **Python** (pipeline / traitement de données / outillage).
Objectif : **simple, rapide à livrer, maintenable**.

## Stack
- **Python 3.12 + pixi** (conda-forge + PyPI ; lockfile) · **ruff** (lint + format) ·
  **mypy strict sur `src/`** · **pytest** · **typer** (CLIs) · **`just`** (lanceur).
- **PostgreSQL + pgvector** (compose) pour l'état durable et les recherches vectorielles.
- Référence de décision : `_tools_python/reco-stack-python.md` (pixi vs uv, mypy pragmatique).

## ⭐ Règle façade
**`pixi` ne s'écrit jamais en dehors du `justfile`** (ni dans les fiches, ni dans la doc, ni
dans les prompts d'agents) : toujours `just lint`, `just test`, `just run <cli> …`. C'est ce
qui rend le gestionnaire d'environnement remplaçable à coût quasi nul.

## Conventions
- **Code en ANGLAIS — identifiants ET valeurs** (littéraux d'état, clés, slugs techniques).
  **Commentaires, commits, fiches, docstrings : en FRANÇAIS.** Package : `tiny_wae`.
- **Décisions en amont, KISS, proportionné** (cf. `~/.claude/CLAUDE.md`).
- **Couches** (cf. `_tools_python/principes-archi-garde-fous-python.md`) :

  ```
  src/tiny_wae/core/      → métier pur (zéro I/O, zéro framework) — testable à sec
  src/tiny_wae/adapters/  → I/O : APIs externes, fichiers, BD
  src/tiny_wae/cli/       → entrées typer = WIRING uniquement (fines, sans logique)
  ```

- **Chaque étape de pipeline = un CLI autonome** à entrées/sorties explicites (fichiers ou
  arguments — jamais d'état implicite partagé) : c'est ce qui les rend orchestrables (CWL,
  cron, tests) et testables isolément.
- **Toujours commenter les fonctions non triviales** (docstring courte : rôle, entrées,
  sorties) — le relecteur n'est pas forcément l'auteur.
- **Secrets** en variables d'environnement (`.env`, jamais commité), jamais dans le code.
- **Pas de montée de version** de lib/runtime sans accord explicite.

## Backlog (pilotage par fiches)
- Méthode : `docs/backlog/_methode-backlog.md`. **Statut = dossier** :
  `maturation/ → a-faire/ → en-cours/ → fait/`. Le Markdown est la spec ; le dossier fait foi.
- Tableau de bord : `just dashboard` (ne pas éditer `etat.html`).
- Une fiche en `a-faire/` = **brief autonome** (critères « Prêt à faire »), avec son
  **oracle figé** (mesures + seuils + non-testé explicite).

## Harnais d'auto-validation (autonomie)
- **`just check`** = lint (ruff) + types (mypy) + tests (pytest) + **smoke** (le pipeline réel
  sur un périmètre minuscule). **À lancer AVANT de dire « fini ». Jamais de commit sur du
  rouge.** Détail : `_tools_python/harnais-agent-autovalidation-python.md`.
- **Chiffres honnêtes** : tout verdict donne le dénominateur, le cas défavorable, et ce qui
  n'a PAS été testé.
- `just psql "<sql>"` pour asserter l'état réel en base après une mutation.

## Commandes (.claude/commands/)
`/new-fiche` · `/dashboard` · `/md2html` · `/run` (producteur/consommateur) · `/review`
(adversariale).

## Démarrage (référence : `_tools_python/kickoff-nouveau-projet.md`)
1. `cp .env.example .env` · `just install` · `just db` (Postgres + pgvector up).
2. **Poser le harnais** (`just check` vert) **AVANT** la 1re feature.
3. Backlog : idées → `docs/backlog/maturation/INDEX.md` → fiches → mûrir → `/run`.
