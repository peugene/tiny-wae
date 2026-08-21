---
description: Run autonome producteur/consommateur sur les fiches a-faire/
---
Tu es l'**agent principal** (orchestrateur). Lance un **run autonome producteur/consommateur**
sur les fiches prêtes (`docs/backlog/a-faire/`), selon `docs/backlog/_methode-backlog.md`.

## 0. Pré-requis
Les fiches `a-faire/` sont **rédigées pour être exécutées par un agent (effort medium)** sans
question ni décision (critères « Prêt à faire », **oracle figé** compris). Si une fiche ne
l'est pas → la mûrir d'abord, pas la lancer.

⛔ **Ne JAMAIS dispatcher** : une fiche `categorie: humain` (bandeau « NE PAS DISPATCHER » —
elle est réalisée par l'humain ; ses dépendants restent bloqués, c'est voulu) ni une fiche
`categorie: chapeau` (elle ne porte que le contexte de ses `subtasks:`). Un chapeau passe
en `fait/` quand toutes ses sous-tâches y sont.

## 1. Cadrage (AVANT de lancer)
- Lis les fiches `a-faire/` et calcule leur **ordre topologique** (via `depends_on`)
  ⭐ **sur les seules fiches DISPATCHABLES** (ni `chapeau`, ni `humain`) : un chapeau a
  `depends_on: []` et n'ordonne rien ; une fiche humaine bloque volontairement ses
  dépendants. Un `depends_on` est **satisfait quand la fiche visée est en `fait/`**.
- ⭐ **Fournis la FICHE et le CHAPEAU dans le prompt de l'agent** quand la fiche a un `parent:` : il
  porte le contexte et les décisions actées que la sous-tâche ne répète pas.
- Lance `just dashboard` avant de commencer : il **contrôle le graphe** (ids inexistants,
  cycles, parent/subtasks non appariés, fiche isolée). Toute anomalie se corrige en
  maturation AVANT le run.
- Repère celles **parallélisables de façon SÛRE** (zones de code **disjointes**). **Au
  moindre doute → séquentiel.**
- Crée la **liste de tâches** (outil Task) pour le suivi.
- Présente le plan, **puis lance — en autonomie, sans attendre de validation.**

## 2. Pour CHAQUE fiche
1. ⭐ **Valider la fiche AVANT de lancer l'agent**, en t'**ancrant dans le CODE RÉEL** (lis
   les modules/CLIs/fichiers cités) — **jamais sur des suppositions.** Grave ce que tu as
   vérifié dans une section **« ⚠ Ancrage dans le code réel »** ajoutée **dans la fiche
   elle-même**, commitée avant le dispatch. Fiche fausse ou périmée → corriger, ou différer.
2. `a-faire/ → en-cours/` ; TaskUpdate → in_progress.
3. Agent d'implémentation isolé en **worktree git** (`wt/<id>`) ; commit sur sa branche,
   **sans push, sans toucher `docs/backlog/`**.
   ⭐ **Contraintes de dispatch (décision Philippe, 21/08) — non négociables** :
   - **`subagent_type: implementeur-fiche`** (`.claude/agents/`) : **Sonnet, effort medium**,
     et sa liste d'outils **exclut toute délégation** (ni Agent, ni Workflow) — la
     contrainte est structurelle, pas déclarative.
   - ⛔ **L'agent n'exécute RIEN en tâche de fond** (pas de `run_in_background`, pas de `&`) :
     il implémente lui-même, au premier plan, et attend chaque résultat.
   - ⛔ **Il ne rend la main qu'avec `just check` au vert.** Un compte rendu sans gate vert
     = fiche non terminée : on ne merge pas, on relance ou on diffère.
   - Toi, orchestrateur, tu **revérifies** le gate toi-même (étape 4) : la parole de l'agent
     ne remplace jamais la mesure.
   - ⚠ Ne pas confondre : **toi** tu lances l'agent et tu travailles pendant qu'il tourne —
     c'est l'interdiction faite à **l'agent**, dans sa propre exécution, de détacher quoi
     que ce soit.

   Pendant que l'agent travaille : ancrer la fiche **SUIVANTE — et seulement elle** (les
   faits dépendant de la fiche en cours se notent « à reconfirmer post-merge », jamais
   comme acquis).
4. ⭐ **AVANT le merge** : valider la conformité contre la fiche — diff relu, `just check`,
   `/review` adversariale si code sensible (auth, écriture, suppression de données).
5. **Merge** `git merge --no-ff wt/<id>` → ⭐ **REVALIDER sur la branche principale**
   (`just check` au vert).
6. « Résumé de réalisation » (avec le **verdict d'oracle chiffré**) → `fait/` → **UN commit
   par fiche** → TaskUpdate → completed → `git worktree remove`.

## 3. Clôture
Toutes les fiches faites : **régénérer le dashboard** (`just dashboard`), branche propre,
**débrief final** (réalisations + décisions prises en cours + fiches différées créées).

## 4. Autonomie — la règle d'or
**Un run ne s'interrompt PAS**, sauf gros blocage insoluble — ou fiche humaine non faite
(alors : traiter tout ce qui est dispatchable, puis s'arrêter en le signalant au débrief,
avec la liste des fiches en attente de l'humain). Sur blocage/question : (1)
**trancher et documenter** dans la fiche, signalé au débrief ; ou (2) **différer** via une
nouvelle fiche en `maturation/`, et continuer. Cette règle **prime** sur toute convention
« demander un GO » héritée d'ailleurs.

## 5. Hygiène de commit — garde-fous durs (non négociables)
- **Gate = `just check` AVANT tout commit. Jamais de commit sur du rouge.**
- **1 fiche = 1 commit logique.** Message : `feat|fix|refactor|test|chore(<domaine>):
  <titre> (<id-fiche>)`.
- **JAMAIS `--no-verify`. JAMAIS `amend`** d'un commit refusé → nouveau commit.
- **Pas de `git add .` aveugle** — stager explicitement.
- **Aucun push** — le push est une décision humaine.
- **Borne anti-boucle** : `just check` encore rouge après ~3 corrections → **différer** la
  fiche et continuer le run.
