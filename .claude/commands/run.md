---
description: Run autonome producteur/consommateur sur les fiches a-faire/
---
Tu es l'**agent principal** (orchestrateur, typiquement Opus xHigh). Lance un **run autonome
producteur/consommateur** sur les fiches prêtes (`docs/backlog/a-faire/`), selon
`docs/backlog/_methode-backlog.md`.

## 0. Pré-requis
Les fiches `a-faire/` sont **rédigées pour être exécutées par un agent Sonnet (effort medium)** sans
question ni décision (critères « Prêt à faire », **oracle figé** compris). Si une fiche ne l'est pas
→ la mûrir d'abord, pas la lancer.

⛔ **Ne JAMAIS dispatcher** : une fiche `categorie: humain` (bandeau « NE PAS DISPATCHER » — elle est
réalisée par l'humain ; ses dépendants restent bloqués, c'est voulu) ni une fiche
`categorie: chapeau` (elle ne porte que le contexte de ses `subtasks:`). Un chapeau passe en `fait/`
quand toutes ses sous-tâches y sont.

## 1. Cadrage (AVANT de lancer)
- Lis les fiches `a-faire/` et calcule leur **ordre topologique** (via `depends_on`) ⭐ **sur les
  seules fiches DISPATCHABLES** (ni `chapeau`, ni `humain`) : un chapeau a `depends_on: []` et
  n'ordonne rien ; une fiche humaine bloque volontairement ses dépendants. Un `depends_on` est
  **satisfait quand la fiche visée est en `fait/`**.
- Repère celles **parallélisables de façon SÛRE** (zones de code / fichiers **disjoints**, aucun
  couplage). **En cas de doute → séquentiel.**
- Lance `just dashboard` : il **contrôle le graphe** (ids inexistants, cycles, `parent`/`subtasks`
  non appariés, chapeau qui ordonne, fiche isolée) et **liste les feuilles à relire**. Toute
  anomalie se corrige en maturation AVANT le run.
- Crée la **liste de tâches via l'outil Task** (une tâche par fiche + une de clôture) pour le suivi.
- Présente-moi le plan (ordre topologique + ce qui part en parallèle), **puis lance — en autonomie,
  sans attendre ma validation.**

## 2. Pour CHAQUE fiche
1. ⭐ **Valider la fiche AVANT de lancer l'agent**, en t'**ancrant dans le CODE RÉEL** du projet
   (lis les fichiers/modules/CLIs cités) — **jamais sur des suppositions.** Si la fiche est
   fausse, périmée ou infaisable : la **corriger**, ou la **différer** (cf. §4).
   ⭐ **Systématique, quelle que soit la taille de la fiche** : grave ce que tu as vérifié dans une
   section **« ⚠ Ancrage dans le code réel »** ajoutée **dans la fiche elle-même** (pas seulement
   dans le prompt de dispatch) — commitée avant le dispatch, pas après. Ce n'est pas une formalité :
   sur le projet d'origine, c'est cet ancrage qui a débusqué une **faille d'autorisation réelle**
   (mutations par id enfant sans vérification de l'entité parente) avant qu'elle parte en dispatch.
   Un ancrage qui ne vit que dans le prompt d'un agent ne laisse aucune trace pour la fiche
   suivante ni pour une relecture a posteriori.
2. `a-faire/ → en-cours/` ; `TaskUpdate` → in_progress.
3. Lancer un **agent Sonnet medium en TÂCHE DE FOND**, isolé dans un **worktree git** (`wt/<id>`) ;
   il code et **commit sur sa branche, sans push, sans toucher `docs/backlog/`**. (Plusieurs agents en
   parallèle seulement pour les fiches jugées sûres au §1.)
   ⭐ **Si la fiche a un `parent:`, fournis-lui le CHAPEAU dans son prompt** : il porte le contexte,
   les faits vérifiés et les décisions actées que la sous-tâche ne répète pas.
   ⭐ **Ancrage anticipé pendant l'attente** : le temps d'attente de cet agent se met à profit pour
   ancrer la fiche **SUIVANTE — et seulement elle**, jamais plus loin dans la file (pas de
   pré-ancrage en rafale). **Exception** : si cette fiche suivante dépend de la fiche en cours de
   dispatch — explicitement (`depends_on`) ou implicitement (elle consomme un type/port/schéma que
   la fiche en cours est en train de créer/modifier) — l'ancrage anticipé ne peut porter que sur les
   faits **indépendants** de cette dépendance ; les faits qui en dépendent (forme exacte d'un port
   encore en cours d'écriture, schéma de manifeste qui suppose un merge pas encore fait…) se notent
   comme **« à reconfirmer post-merge »**, jamais comme acquis — et la fiche suivante n'est ni
   déplacée en `en-cours/` ni dispatchée avant cette reconfirmation.
4. ⭐ **AVANT le merge** : **valider la conformité des modifs** de l'agent contre la fiche — relire le
   diff, `just check`, `/review` adversariale si code sensible (auth, écriture, suppression de
   données, accès réseau).
5. **Merge** `git merge --no-ff wt/<id>` → ⭐ **APRÈS le merge, REVALIDER sur la branche principale**
   que tout est au vert (`just check` — les recettes `just` valident et doivent passer au vert).
   ⚠ `pixi.lock` : versionné mais **jamais mergé** — en cas de conflit, le régénérer sur la branche
   cible (`just install`) plutôt que de résoudre à la main.
6. « Résumé de réalisation » — avec le **verdict d'oracle chiffré** — → `fait/` → **UN commit pour
   cette fiche** → `TaskUpdate` → completed → `git worktree remove`.

## 3. Clôture
- Quand **TOUTES** les fiches sont terminées : **régénérer le dashboard** (`/dashboard`).
- Branche propre (tout commité). **Débrief final** : tout ce qui a été fait pendant la phase,
  + les **décisions prises en cours de route**, + les **fiches différées** créées, + les fiches
  restées **en attente d'une fiche humaine**.

## 4. Autonomie — la règle d'or
**Un run ne s'interrompt PAS** — sauf **GROS blocage insoluble**, ou **fiche humaine non faite**
(alors : traiter tout ce qui est dispatchable, puis s'arrêter en le signalant au débrief). Sur un
blocage ou une question, tu **ne me sollicites pas** : tu choisis l'une des deux voies, et tu
continues le run. **Cette règle prime sur toute convention « proposer / demander un GO avant »
héritée du CLAUDE.md** : un point ouvert rencontré en cours de run se tranche-et-documente (ou se
diffère), il ne justifie jamais une interruption. Le run existe précisément pour ne pas être
interrompu.
1. **Prends une décision, documente-la** (dans la fiche concernée) et **signale-la au débrief final.**
2. Si c'est **trop compliqué** pour être tranché là : **diffère** — rédige une **nouvelle fiche en
   `maturation/`** qui capture le problème, et passe à la suite.

## 5. Hygiène de commit — garde-fous durs (non négociables)
- **Gate = `just check` AVANT tout commit** (lint → types → tests → smoke). **Jamais de commit sur
  du rouge.**
- **1 fiche = 1 commit logique**, jamais groupé. Message :
  `feat|fix|refactor|test|chore(<domaine>): <titre> (<id-fiche>)` + corps citant l'ID de la fiche.
- **JAMAIS `--no-verify`. JAMAIS `amend`** un commit refusé par un hook → **nouveau commit**.
- **Pas de `git add .` aveugle** — stager explicitement les fichiers de la fiche.
- **Aucun push** — les agents de fond commitent sur leur branche ; le merge reste local. Le **push
  est une décision humaine**.
- **Borne anti-boucle** : si `just check` reste rouge après ~3 tentatives de correction sur une
  fiche, **ne pas s'acharner** → **différer** la fiche (§4.2) et continuer le run.
