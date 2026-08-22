# CLAUDE.md — tiny-wae

Guide pour Claude Code sur ce dépôt. **Ces instructions priment.** Le `~/.claude/CLAUDE.md` global
(porteur cross-projet du style de travail) le complète ; ici = **le projet**. Scaffoldé le 2026-08-21
avec le kit `_tools_python/`.

## ⚠ Multi-instances : zones d'écriture (accord Philippe, 2026-08-21)

Deux types d'instances Claude travaillent sur ce dépôt **en parallèle** :

- **L'architecte/PO** (instance Cowork) écrit UNIQUEMENT dans `docs/backlog/` (rédaction de
  fiches en `maturation/`, régénération du dashboard) et `docs/lots/` (feuille de route des
  lots, source de vérité du lotissement). Il ne touche jamais à `src/`, `tests/`,
  `scripts/`, et ne fait **ni commit ni push**.
- **L'équipe d'implémentation** (instances Claude Code) écrit dans `src/`, `tests/`,
  `scripts/`, et gère les **déplacements** de fiches (`a-faire/ → en-cours/ → fait/`) ainsi
  que git. L'éauipe peut :  modidier ou  rédiger des nouvelles fiches en maturation après une revue. Elle rédige aussi des fiches **différées**
  pendant un `/run` (règle d'autonomie de la méthode).

**Une troisième source alimente le dépôt** : le **tooling** (`scripts/`, en particulier
`backlog.py`) est mis au point **hors de ce dépôt**, puis déposé ici. Y trouver des
modifications qu'aucune instance n'a écrites est **normal** — on les commite comme le
reste, sans les traiter comme un écart de zone.

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

## Backlog (pilotage par fiches)
- Méthode : `docs/backlog/_methode-backlog.md`. **Statut = dossier** :
  `maturation/ → a-faire/ → en-cours/ → fait/`. Le Markdown est la spec ; le dossier fait foi.
- Tableau de bord : `just dashboard` (ne pas éditer `etat.html`).
- Une fiche en `a-faire/` = **brief autonome** (critères « Prêt à faire »), avec son
  **oracle figé** (mesures + seuils + non-testé explicite).

## Harnais d'auto-validation (autonomie)
- **`just check`** = lint (ruff) + types (mypy) + **deptry** (hygiène des dépendances) +
  tests (pytest) + **smoke** (le pipeline réel sur un périmètre minuscule) + **cwl**
  (validation des artefacts). **À lancer AVANT de dire « fini ». Jamais de commit sur du
  rouge.** La CI lance `just check`, à l'identique — une seule définition de « fini ». Détail : `_tools_python/harnais-agent-autovalidation-python.md`.
- **Chiffres honnêtes** : tout verdict donne le dénominateur, le cas défavorable, et ce qui
  n'a PAS été testé.
- `just psql "<sql>"` pour asserter l'état réel en base après une mutation.

## ⚠ Worktrees d'agents (`/run`) — isolation native, sous conditions

L'isolation `isolation: "worktree"` (dynamic workflow) **fonctionne** et donne un worktree par
agent sous `.claude/worktrees/` (gitignoré, nettoyé automatiquement). **Mais sa base doit être
choisie**, sinon l'agent code sur un arbre périmé : au run N0, un agent a lu une version
**antérieure de sa propre fiche** et livré du code amputé d'un champ.

**Deux réglages, à tenir tous les deux :**

1. `git remote set-head origin <branche-de-chantier>` — réglage **local** du clone, lu **à
   chaud**. Sans lui, la base par défaut (`fresh`) est `origin/main`, figée depuis le scaffold.
   ⚠ **Corollaire : pousser la branche de chantier AVANT chaque run** — cette base est le ref
   *distant*, pas ton HEAD local.
2. `.claude/settings.json` → `worktree.baseRef: "head"` — base = **HEAD local**, ce qui lève
   l'obligation de pousser. ⚠ **Les settings ne sont lus qu'au DÉMARRAGE de session** : un
   fichier créé en cours de session reste sans effet — c'est ce qui a fait conclure à tort que
   le réglage était inopérant.

⭐ **Sonde de contrôle avant tout dispatch réel** (~30 s, lecture seule) : un agent trivial en
`isolation: 'worktree'` qui rapporte `pwd` et `git rev-parse --short HEAD`, comparé au HEAD
attendu. Mesuré le 21/08 : 2 agents en parallèle, worktrees distincts, tous deux sur `13b483f`.
**On ne dispatche pas sans cette vérification** — elle coûte 30 s, l'erreur a coûté un dispatch
entier.

⛔ **`.pixi/` ne se partage JAMAIS entre worktrees** (le réflexe « symlink du `node_modules` »
ne transpose PAS ici) : le projet est installé **en éditable**, et
`.pixi/envs/default/lib/.../_editable_impl_tiny_wae.pth` contient un chemin **absolu**. Un
`.pixi` partagé ferait tourner `just check` du worktree **sur le code d'un autre arbre** — gate
au vert sur le mauvais code, le pire des faux positifs. Chaque worktree fait son `just install`.

**Coût mesuré** : le worktree est gratuit (~1 Mo), mais `just install` y coûte **1 min 5 s et
696 Mo réels** — `/mnt/d` est un montage Windows (drvfs) sans liens durs, pixi recopie donc
l'environnement entier au lieu de le lier. 3 agents en parallèle ≈ 2,1 Go et 3 min d'install.

**Repli si la sonde est rouge** : worktree à la main
(`git worktree add -b wt/<id> /mnt/d/git/_wt-<id> <branche>`, copier `.env`, `just install`),
agent lancé **sans** `isolation:` avec le chemin absolu dans son prompt — l'isolation n'est
alors garantie que par la consigne, donc relire le diff avant merge.

## Commandes (.claude/commands/)
`/new-fiche` · `/dashboard` · `/md2html` · `/run` (producteur/consommateur) · `/review`
(adversariale).

## Démarrage (référence : `_tools_python/kickoff-nouveau-projet.md`)
1. `cp .env.example .env` · `just install` · `just db` (Postgres + pgvector up).
2. **Poser le harnais** (`just check` vert) **AVANT** la 1re feature.
3. Backlog : idées → `docs/backlog/maturation/INDEX.md` → fiches → mûrir → `/run`.
