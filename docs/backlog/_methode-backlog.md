# backlog-kit (Python) — piloter un projet par fiches + dashboard

> Kit **clone-ready** pour piloter un projet (surtout **piloté par IA**) avec des **fiches de
> tâche** en Markdown, un **tableau de bord HTML** auto-généré, des **chantiers** (sous-dossiers
> autonomes) découpés en **phases**, et la méthode **roadmap → revue**. Port **Python**
> (2026-08-21) du backlog-kit de `_tools`/`_tools_js` — méthode identique, scripts réécrits.
>
> ⚠ **Divergences du port Python à reporter dans `_tools`/`_tools_js`** (règle : le plus
> récent fait foi) : 1) les deux scripts Node sont fusionnés en UN CLI Python
> (`scripts/backlog.py dashboard|md2html`, dépendance unique `markdown`) ; 2) le modèle de
> fiche gagne une section **« Oracle / recette »** (mesures + seuils figés avant
> implémentation, distincte de « Définition de terminé »).

## Ce que c'est (et pourquoi)

Un projet piloté par IA a besoin d'un **backlog qui sert aussi de brief** : chaque fiche est à
la fois une tâche *et* le prompt qui la fait réaliser. Le kit fournit :

- une **méthode** (cycle de vie en dossiers, critères de maturité) ;
- un **script sans magie** : `scripts/backlog.py` (dashboard HTML + md→html) ;
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
desc: Chips Sentinel-2 sur 48 mois pour 25 sites.
phases: O1=Plomberie STAC | O2=Historique | O3=Incrémental
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
python scripts/backlog.py md2html _roadmap.md roadmap.html "Titre" ["Bandeau"]
```

Dépendance : `markdown` (déclarée par le scaffolder dans l'environnement pixi du projet).
Écrit `maturation/etat.html` + une archive par chantier terminé. **Ne rien éditer à la main**
(écrasé). Régénérer après **toute** évolution du backlog. Via la façade : `just dashboard`.

## Le pattern producteur / consommateur (run autonome)

Le backlog **alimente** un **run autonome** : l'**agent principal** (orchestrateur) pilote,
des **agents d'implémentation** réalisent les fiches en tâche de fond. Le brief opérationnel
est la commande `/run` (`.claude/commands/run.md`). Règles clés : fiches validées **ancrées
dans le code réel** avant dispatch (section « ⚠ Ancrage » gravée dans la fiche) ; agents
isolés en **worktree git**, commit sans push ; conformité validée **avant** merge
(`--no-ff`) ; revalidation `just check` **après** merge ; un run **ne s'interrompt pas** —
sur blocage : trancher-et-documenter, ou différer via une fiche en `maturation/`.

> La **validation autonome** (`just check` : lint + types + tests + smoke) est **la
> condition** de ce mode — cf. la fiche *harnais* du kit.
