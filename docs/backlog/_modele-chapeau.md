---
id: NN-slug
titre: "[CHAPEAU] Thème de la fiche chapeau"
effort: L            # somme indicative des sous-tâches — le chapeau ne se dispatche PAS
categorie: chapeau
phase:
depends_on: []       # dépendances du GROUPE (souvent : le chapeau précédent)
parent:
subtasks: [NN-slug.1, NN-slug.2]
---

# [NN] — CHAPEAU : Thème

> **Fiche chapeau : elle ne se dispatche pas.** Elle porte le contexte et les décisions
> communes une seule fois, pour que chaque sous-tâche reste courte et implémentable par un
> agent d'effort medium. Le chapeau passe en `fait/` quand toutes ses sous-tâches y sont.
> (Pattern repris du backlog `pid-flow` : frontmatter `parent:` / `subtasks:`.)

## Contexte

[Le pourquoi commun aux sous-tâches, les faits vérifiés à ne pas re-déduire, les pièges.]

## Décisions portées par ce chapeau (ne pas rouvrir)

- [Décision 1 — avec sa source : GO humain daté, revue, mesure.]
- [Décision 2 …]

## Sous-tâches

| Fiche | Effort | Objet |
|---|---|---|
| NN-slug.1 | S | … |
| NN-slug.2 | M | … |

## Hors périmètre du chapeau

[Ce qui appartient à d'autres chapeaux / lots, et ce qui est explicitement « non testé ».]
