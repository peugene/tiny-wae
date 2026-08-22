# backlog-kit (Python) — piloter un projet par fiches + dashboard

> Kit **clone-ready** pour piloter un projet (surtout **piloté par IA**) avec des **fiches de
> tâche** en Markdown, un **tableau de bord HTML** auto-généré, des **chantiers** (sous-dossiers
> autonomes) découpés en **phases**, et la méthode **roadmap → revue**. Port **Python**
> (2026-08-21) du backlog-kit de `_tools`/`_tools_js` — méthode identique, scripts réécrits.
>
> ⚠ **Divergences du port Python à reporter dans `_tools`/`_tools_js`** (règle : le plus
> récent fait foi) : 1) les deux scripts Node sont fusionnés en UN CLI Python
> (`scripts/backlog.py dashboard|lots|md2html`, dépendance unique `markdown`) ; 2) le modèle de
> fiche gagne une section **« Oracle / recette »** (mesures + seuils figés avant
> implémentation, distincte de « Définition de terminé ») ; 3) **`dashboard` génère aussi
> le `.html` de CHAQUE fiche** (ids cliquables — le backlog se parcourt entièrement en
> HTML) ; 4) **fiches CHAPEAU + sous-tâches** (`parent:` / `subtasks:`, pattern `pid-flow`) ;
> 5) **fiches HUMAINES** (`categorie: humain`) et interdiction des gates humains dans les
> fiches d'implémentation ; 6) **barème S/M/L/XL** explicite.

## Ce que c'est (et pourquoi)

Un projet piloté par IA a besoin d'un **backlog qui sert aussi de brief** : chaque fiche est à
la fois une tâche *et* le prompt qui la fait réaliser. Le kit fournit :

- une **méthode** (cycle de vie en dossiers, critères de maturité) ;
- un **script sans magie** : `scripts/backlog.py` (dashboard HTML + feuille de route + md→html) ;
- des **templates** (fiche, chantier, roadmap, revue).

Principe fondateur : **le Markdown est la spec / le canal IA ; le HTML est la vue humaine,
dérivée** (il ne peut donc pas mentir sur l'avancement). **Le dossier fait foi.**

## Le modèle : statut = dossier

```
maturation/  →  a-faire/  →  en-cours/  →  fait/
```

On fait avancer une tâche en **déplaçant sa fiche** de dossier. **Règle d'or : toute décision
se prend en amont (maturation), jamais pendant l'implémentation.**

- **`maturation/`** — l'idée a sa fiche mais le brief est **incomplet** : on y **lève tous les
  verrous** (choix techniques, questions ouvertes, schéma + migration si la BD bouge).
- **`a-faire/`** — fiche **mûre** = brief **autonome**, implémentable **sans question ni
  décision**.
- **`en-cours/`** — en réalisation (une à la fois de préférence).
- **`fait/`** — terminée, avec son **« Résumé de réalisation »** (fait, verdict d'oracle,
  commit(s), date).

### ⭐ Taille d'une fiche : le barème (invariant)

**Une fiche en `a-faire/` doit être implémentable par un agent d'effort MEDIUM** (type
Sonnet), en autonomie, sans poser de question. Barème : **S** ≤ 1 session d'agent · **M**
≤ 2-3 · **L** = plusieurs (à scinder si possible) · **XL** = interdit en `a-faire/`.
Une fiche qui cumule plusieurs préoccupations (un contrat + un CLI + un harnais + une
campagne) est **hors gabarit** : la scinder en **CHAPEAU + sous-tâches**.

### Fiche CHAPEAU + sous-tâches (pattern `pid-flow`)

Un thème trop gros pour une fiche devient un **chapeau** (`categorie: chapeau`,
`subtasks: [...]`) qui **ne se dispatche pas** : il porte le contexte, les faits vérifiés
et les décisions communes **une seule fois**, pour que chaque sous-tâche (`parent: <id>`)
reste courte. Le chapeau passe en `fait/` quand toutes ses sous-tâches y sont. Modèle :
`_modele-chapeau.md`.

### ⭐ Grain du graphe : seules les fiches dispatchables ordonnent le run

Un **chapeau** a `depends_on: []` — **il n'ordonne rien** ; sa place dans la chaîne s'écrit
en prose dans son corps. Toutes les vraies arêtes vivent dans les **sous-tâches**. Une
fiche **humaine**, elle, porte un `depends_on` et **bloque volontairement** ses dépendants.
Un `depends_on` est **satisfait quand la fiche visée est en `fait/`** — un seul critère,
le dossier fait foi (pas de « levée au merge »).

*Motif : mélanger les deux grains produit deux graphes contradictoires — au grain chapeau,
tout l'aval se retrouve bloqué derrière un gate humain, y compris des fiches sans rapport.*

Le filet de sécurité n'est plus le `depends_on` de groupe mais un **contrôle mécanique** :
`dashboard` vérifie le graphe à chaque génération et affiche, en tête du tableau de bord
**et** en console, deux niveaux :

- **⚠ anomalies** (à corriger) : `depends_on`/`subtasks` pointant vers un id inexistant,
  cycles, `parent`/`subtasks` non appariés, chapeau portant un `depends_on`, fiche isolée.
- **ℹ à relire** : un **chapeau non clos** dont toutes les sous-tâches sont en `fait/`
  (déplacer une fiche est un geste d'équipe, pas une erreur de graphe : on le rappelle,
  on ne l'impose pas) ; et les **feuilles** du graphe (aucune fiche n'en dépend). Certaines sont
  légitimes — recette finale, dernier maillon d'outillage — d'autres révèlent une **arête
  oubliée**. Le contrôle ne peut pas trancher : il liste, le PO juge. *Cas vécu : une
  fiche produisant la configuration de tout le lot s'est retrouvée sans aucun dépendant
  après un desserrage de dépendances ; elle serait apparue ici.*

### ⭐ Règle de rédaction : une énumération normative n'existe qu'à UN endroit

Statuts, codes de sortie, ordre de bandes, liste de clés : dès qu'une **énumération** est
normative, elle est **définie dans le chapeau** et les sous-tâches y **renvoient** (« les
6 statuts du chapeau X ») au lieu de la recopier. *Motif : une même liste recopiée dans
cinq fiches a produit quatre incohérences le jour où un statut y a été ajouté — corrigé au
point de définition, jamais chez les consommateurs.* Aucun contrôle mécanique ne rattrape
cela de façon fiable ; la seule parade robuste est de **ne pas dupliquer**.

### ⭐ Après toute correction : la question de propagation

Une correction n'est finie que lorsqu'on a répondu à **« qui consomme ce que je viens de
changer ? »** — schéma, oracle d'une autre fiche, document de lot, checklist humaine. Une
passe de correction qui ne se pose pas cette question crée autant de défauts qu'elle en
répare, et les nouveaux sont plus difficiles à voir car ils sont *cohérents localement*.

### ⛔ Fiches HUMAINES — un gate humain n'est JAMAIS dans une fiche d'implémentation

Une validation humaine (revue visuelle, lancement d'infra, recette) ne doit apparaître ni
dans une définition de terminé, ni dans une table d'oracle : la fiche agent produit un
**artefact** avec des critères mécaniques, et la validation devient une **fiche séparée**
`categorie: humain`, titre préfixé `[HUMAIN]`, avec un bandeau ⛔ « ne pas dispatcher ».
Les fiches aval en dépendent par `depends_on` : **le run se met en pause** tant qu'elle
n'est pas en `fait/` — comportement voulu. Modèle : `_modele-fiche-humaine.md`.
⚠ La commande `/run` doit refuser de dispatcher toute fiche `categorie: humain`.

### 📘 Fiches DOCUMENTAIRES — enregistrer un travail qui a échappé au cycle

Il arrive qu'un travail soit livré **hors du cycle** : une contrainte externe tombe en
cours de lot, quelqu'un l'implémente dans la foulée, et le backlog — qui « fait foi » — n'en
porte aucune trace. Les fiches closes se mettent alors à décrire un état du code qui
n'existe plus.

La parade est une **fiche documentaire** (`categorie: documentaire`, id suffixé `.R` pour
rétroactive, sur le modèle du `.H` des fiches humaines). Elle **n'ordonne rien et n'est
ordonnée par rien** : `depends_on: []`, pas de parent. Le contrôle de graphe la traite en
conséquence — elle est **exemptée** de l'anomalie « fiche isolée » et de l'info
« feuille », qui seraient toutes deux des faux positifs par construction. Modèle :
`_modele-fiche-documentaire.md`.

⭐ **La section qui compte n'est pas la liste des changements, c'est « ce qui n'a PAS été
revérifié ».** Un travail hors cycle a souvent modifié précisément ce qu'un oracle déjà
validé vérifiait : le refactor reste vert partout, et l'oracle est périmé sans que rien ne
le signale. *Cas vécu : un refactor d'artefacts d'orchestration a changé le chemin
d'exécution et la récupération des sorties — soit exactement les deux choses que l'oracle
d'équivalence de la fiche close mesurait ; les runs post-refactor prouvaient que « ça
tourne », pas que l'équivalence tenait encore.*

⚠ **C'est un précédent, pas une pratique** : écrire une fiche après le code inverse la
règle « les décisions se prennent en amont ». Le réflexe correct reste de produire une
fiche — même courte — **avant** d'implémenter la contrainte qui vient d'arriver.

### Critère « Prêt à faire » (passage `maturation/` → `a-faire/`)

Objectif : **une fiche en `a-faire/` doit être implémentable par un agent (effort medium) sans
poser une seule question.** Avant de déplacer, vérifier : objectif clair · périmètre
(modules/CLIs/fichiers **nommés**) · **toutes les décisions tranchées** · migration BD
spécifiée (le cas échéant) · définition de « terminé » **vérifiable** · **oracle figé**
(mesures, seuils, non-testé explicite) · `depends_on` identifiées · auto-suffisante ·
**pas de doublon inter-module** · ⭐ **gate vert à son propre commit** (une fiche ne doit
JAMAIS différer à une fiche ultérieure la correction d'un `just check` qu'elle casse
elle-même — le protocole de run interdit tout commit sur du rouge, sans exception ; le
nécessaire au gate s'absorbe dans la fiche qui le casse). Un point manquant → **reste en
maturation**.

## Anatomie d'un backlog

```
docs/backlog/
  _methode-backlog.md       (cette méthode, adaptée au projet)
  _modele-fiche.md  _modele-chantier.md  _modele-roadmap.md  _modele-revue.md
  maturation/
    INDEX.md                (réservoir d'idées priorisées P1/P2/P3)
    etat.html               (← GÉNÉRÉ : le tableau de bord. Ne pas éditer.)
    nn-fiche-a-plat.md
    <chantier>/             (un SOUS-DOSSIER = un chantier autonome)
      _chantier.md          (manifeste : label, desc, phases)
      _roadmap.md → roadmap.html   (phase 1, indicative)
      _revue.md   → revue.html     (phase 2, revue adversariale)
      sv-1-…md  (phase: O1)
  a-faire/  en-cours/  fait/
```

## Conventions

### Fiche (frontmatter YAML)

```yaml
---
id: 02-ingestion       # = nom du fichier sans .md ; sert de clé partout
titre: Ingestion STAC
effort: L              # S | M | L | XL
categorie: pipeline    # taxonomie libre
phase: O2              # optionnel : rattache la fiche à une phase d'un chantier
depends_on: [00-socle] # fiches à finir avant celle-ci
---
```

> C'est le **seul** frontmatter qu'on s'autorise : pas de reporting, pas de sprint, pas de
> statut dupliqué (le dossier fait foi). Une fiche sans `id:` (INDEX, analyse…) est ignorée
> par le dashboard.

### Chantier = sous-dossier autonome

Manifeste `_chantier.md` :

```yaml
---
id: lot-0
label: Lot 0 — Ingestion
desc: Acquisition et stockage du jeu de données de référence.
phases: O1=Plomberie | O2=Reprise d'historique | O3=Incrémental
---
```

Le statut d'un chantier = le dossier où il vit. Terminé (rangé sous `fait/<chantier>/`), le
dashboard génère une **page d'archive** `chantier-<id>.html`.

### roadmap / revue (méthode deux phases)

Pour un chantier conséquent : **`_roadmap.md`** (indicative, posée avant le code) puis
**`_revue.md`** (revue de cohérence **adversariale** : valider découpage / dépendances /
effort, trancher les questions, **figer la roadmap**), et enfin mûrir les fiches. Le dashboard
lie automatiquement les `*.html` trouvés dans le dossier du chantier.

## Le script

```bash
python scripts/backlog.py dashboard --project "Mon projet" [--backlog docs/backlog]
python scripts/backlog.py lots      --project "Mon projet" [--lots docs/lots]
python scripts/backlog.py md2html _roadmap.md roadmap.html "Titre" ["Bandeau"]
```

Dépendance : `markdown` (déclarée par le scaffolder dans l'environnement du projet).
`dashboard` écrit `maturation/etat.html`, une archive par chantier terminé, **et le `.html`
de chaque fiche** — le backlog entier se parcourt en HTML, sans jamais ouvrir un `.md` :

- **dashboard** : compteurs cliquables (ancres par état), ids en liens, sous-tâches
  **imbriquées sous leur chapeau** (`↳`), chapeaux marqués `▣`, fiches humaines `⛔`,
  `depends_on` cliquables.
- **page de fiche** : **breadcrumb** (`🏠 Backlog › chantier › ▣ chapeau › fiche`),
  **pastille d'état** dans le titre, **bandeau détaillé** (une ligne par attribut : effort,
  priorité, catégorie, phase, chantier), **sommaire** replié, **précédent / suivant** dans
  l'ordre de lecture (la fratrie du chapeau, sinon les ids du chantier), bandeau
  d'avertissement pour les fiches chapeau/humaines, et des blocs de navigation où **chaque
  fiche liée porte son état** : « Dépend de » · « Débloque » · sous-tâches (si chapeau) ·
  chapeau + fratrie (si sous-tâche).

  ⭐ **Répartition assumée : le bandeau porte les ATTRIBUTS, la navigation porte le GRAPHE.**
  Lister les dépendances aux deux endroits produisait deux fois la même liste à deux
  centimètres d'écart. Le `<h1>` du corps est retiré au rendu (le bandeau porte déjà
  « [id] titre », et le frontmatter fait foi) — mesuré sur un backlog réel : les 31 fiches
  avaient un H1 différent de leur `titre:`, en faire une anomalie n'aurait produit que du
  bruit.

⭐ **Écriture conditionnelle** : un `.html` n'est réécrit que si son contenu diffère
**ailleurs que sur son horodatage de génération**. Sans ce filtre, chaque `just dashboard`
réécrivait *tous* les fichiers avec une date fraîche : le diff git se remplissait de
fichiers au contenu identique et le churn masquait les vraies évolutions du backlog. La
sortie console affiche `Fiches .html N/M réécrite(s)` — un `N` non nul signale exactement
ce qui a bougé (la fiche modifiée **et** celles dont la navigation la référence).

**Ne rien éditer à la main** (écrasé). Régénérer après **toute** évolution du backlog.
Via la façade : `just dashboard`.

## Les lots — la couche AU-DESSUS du backlog (`just lots`)

Un **lot** est une tranche de la feuille de route, tenue par l'architecte/PO dans
`docs/lots/` : le *quoi et dans quel ordre*, quand le backlog porte le *comment*. C'est un
objet **différent d'une fiche** — pas de dossier-état, pas de graphe de dépendances : un
statut lisible **dans** la fiche, et un ordre de lecture.

- Une fiche par lot : `lot-<N>-<slug>.md`. Le `<N>` donne l'ordre (**tri numérique** : le
  lot 10 passe après le lot 1, pas après le 0) ; les fichiers sans numéro finissent à la fin.
- **Statut** : soit un frontmatter (`titre` / `statut` / `date`), soit — c'est le cas
  courant, ces fiches sont d'abord de la prose — l'en-tête `**Statut** : …` / `**Date** : …`.
  Le texte libre est normalisé par mot-clé vers un badge coloré (Maturation · En cours ·
  Validé · Livré · Abandonné · Obsolète) ; un statut non reconnu reste **affiché tel quel**
  en gris plutôt que d'être perdu.
- `README.md` n'est pas un lot : c'est la feuille de route elle-même, rendue **dans le corps
  de l'index** — une seule page à ouvrir pour avoir la vue d'ensemble ET les cartes.
- Produit `index.html` (compteurs par état, cartes avec badge/extrait/date) et une page par
  lot : **breadcrumb**, badge d'état, **sommaire** replié, **précédent/suivant**.
- **Navigation croisée** : l'index des lots pointe vers le dashboard du backlog, et le
  dashboard pointe vers la feuille de route dès qu'elle est générée.

⚠ Sans cette commande, un dossier de lots rendu fiche par fiche (`md2html`) redevient un tas
de pages orphelines : pas d'entrée, pas d'état visible, aucune navigation. C'est exactement
ce qui s'est produit sur un projet du kit avant l'ajout de `lots`.

## ⚠ `maturation/` est une zone PARTAGÉE

Quand un PO (ou une instance pilote) et une équipe d'implémentation travaillent en
parallèle, les zones d'écriture se séparent naturellement — `src/` et git à l'équipe,
`docs/lots/` au PO — **sauf `maturation/`, qui appartient aux deux** :

- le **PO** y rédige et y mûrit les fiches ;
- l'**équipe** y écrit les fiches **différées** pendant un `/run` (règle d'autonomie) et y
  **corrige ou complète** une fiche après une revue — c'est elle qui découvre, en
  implémentant, ce qu'un brief a d'inexact.

Conséquence pratique : sur ce dossier, **une fiche à la fois par instance**, et on annonce
ce qu'on touche. Les autres dossiers d'état (`a-faire/`, `en-cours/`, `fait/`) restent
gérés par l'équipe seule — le **déplacement** d'une fiche est un geste d'implémentation.

*(La section « Multi-instances » du `CLAUDE.md` scaffoldé porte la version détaillée, à
adapter ou supprimer selon le projet.)*

## Le pattern producteur / consommateur (run autonome)

Le backlog **alimente** un **run autonome** : l'**agent principal** (orchestrateur) pilote,
des **agents d'implémentation** réalisent les fiches en tâche de fond. Le brief opérationnel
est la commande `/run` (`.claude/commands/run.md`). Règles clés : **ne jamais dispatcher
une fiche `categorie: humain` ni une fiche `categorie: chapeau`** ; fiches validées
**ancrées dans le code réel** avant dispatch (section « ⚠ Ancrage » gravée dans la fiche) ;
agents isolés en **worktree git**, commit sans push ; conformité validée **avant** merge
(`--no-ff`) ; revalidation `just check` **après** merge ; un run **ne s'interrompt pas** —
sur blocage : trancher-et-documenter, ou différer via une fiche en `maturation/`. Seule
exception à la non-interruption : une fiche humaine non faite bloque légitimement ses
dépendants (le run traite les autres, puis s'arrête en le signalant au débrief).

> La **validation autonome** (`just check` : lint + types + tests + smoke) est **la
> condition** de ce mode — cf. la fiche *harnais* du kit.
