# Revue de cohérence — <Chantier> (phase 2)

> Passage **adversarial** sur la roadmap indicative : valider découpage / dépendances /
> effort, trancher les questions ouvertes, **figer la roadmap finale**, puis faire mûrir
> les fiches vers `a-faire/`. Générer la vue : `md-to-html _revue.md revue.html`.

## Les angles d'analyse (chacun en aveugle si la revue est multi-agents)

1. **Découpage** — grain des fiches (implémentables par un agent d'effort medium, sans
   question), chapeaux/sous-tâches, périmètres disjoints, briefs autonomes.
2. **Séquençage / graphe** — recalculer les `depends_on` depuis les frontmatters (jamais
   depuis la prose), arêtes manquantes ET inutiles, zones partagées, chemin critique.
   ⚠ Le dispatch est glouton : les « niveaux qui tombent juste » ne protègent rien.
3. **Faits externes** — chaque affirmation factuelle vérifiée À LA SOURCE (API réelle,
   code source des dépôts amont — pas leurs docs ni leurs cartes, qui mentent).
4. **Couverture des décisions actées** — chaque décision portée par une fiche, sans
   contradiction, définie à UN endroit ; décisions implicites prises sans cadrage.
5. **Effort / oracles** — cheatabilité (comment passer au vert sans faire le travail),
   rougissabilité, témoins positifs ET négatifs, seuils justifiés ou arbitraires cachés.
6. ⭐ **Fiches × infrastructure du dépôt** — confronter les fiches à la CI, aux worktrees
   d'agents, à la carte des zones d'écriture, au gate réel (`justfile`), au `.gitignore`
   et au code EXISTANT (citations `fichier:ligne`). *Angle ajouté après qu'une revue
   externe a trouvé un bloquant invisible des 5 premiers : un smoke exigeant un cache de
   poids que ni la CI ni les worktrees n'auraient jamais eu — chaque commit serait passé
   au rouge. Les fiches étaient cohérentes entre elles ET avec les sources amont ; c'est
   leur rencontre avec l'infrastructure qui cassait.*

Puis un **réfuteur indépendant** re-vérifie chaque finding avec preuve — y compris les
décisions actées, qui ne sont pas hors de portée — et traque les « mesure juste,
conclusion fausse ».

## ⭐ Lire ne suffit pas : les deux niveaux de l'ancrage

L'angle 6 se pratique à deux niveaux, et **seul le second attrape les bloquants coûteux**.

- **Niveau 1 — LIRE.** Ouvrir le fichier, citer `fichier:ligne`. Nécessaire, jamais
  suffisant : on vérifie que le code **dit** ce que la fiche prétend, pas ce qu'il **fait**
  quand on l'exécute.
- **Niveau 2 — SONDER.** ⭐ Tout mécanisme dont le chantier **dépend** se sonde : une
  commande jetable, un **témoin dans les deux sens**, le résultat consigné dans la revue.
  Exemples : le linter sur un fichier d'essai contenant la construction litigieuse ·
  l'outil de dépendances sur un projet jouet · le type-checker sur un cas isolé · le
  build sur une branche jouet. **Une sonde coûte une minute et vaut mieux qu'un paragraphe
  d'argumentation.**

⛔ **Aucun chiffre publié sans mesure quand la source est accessible.** Un ordre de grandeur
écrit de mémoire dans une fiche ou une roadmap est une **dette silencieuse** : personne ne
le recompte, et il finit cité comme un fait établi. Si le corpus, la base ou le dépôt est
monté, **on compte** — et on garde la commande à côté du chiffre.

*Les deux règles ont un prix connu. Une revue avait bien cité le code, `fichier:ligne`, sans
jamais lancer une seule commande ; la passe suivante en a lancé trois — le linter sur un
fichier d'essai, l'outil de dépendances sur un projet jouet, un comptage du corpus — et a
sorti **un bloquant et un chiffre faux** que les passes de lecture avaient laissés intacts.
Le chiffre faux traînait depuis trois revues, sur un corpus monté et disponible.*

## 1. Verdict global

[La roadmap est-elle solide ? ce qui change vs l'indicative.]

## 2. Synthèse par objectif / phase

[Verdict court + points saillants par phase.]

## 3. Issues consolidées

| Sévérité | Fiche(s) | Problème | Action recommandée |
|---|---|---|---|
| bloquant | … | … | … |

## 4. Fiches à créer / scinder / fusionner / requalifier

## 5. Questions ouvertes — décisions recommandées

## 6. Roadmap finale — deltas vs indicative

## 7. Prochaines actions (1er lot mûrissable vers `a-faire/`)
