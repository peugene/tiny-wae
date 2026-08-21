---
description: Créer une nouvelle fiche de backlog en maturation
---
Crée une nouvelle fiche de tâche à partir de `docs/backlog/_modele-fiche.md` pour : $ARGUMENTS.

- Place-la dans `docs/backlog/maturation/`, nommée `NN-slug.md`.
- Renseigne le frontmatter (`id` = nom de fichier sans `.md`, `titre`, `effort`, `categorie`,
  `depends_on`) et le corps comme un **brief**.
- Rédige l'**oracle** (mesures + seuils + « non testé ») dès la maturation — il se fige AVANT
  l'implémentation, jamais après.
- **Taille** : la fiche doit être implémentable par un agent d'effort medium (barème du
  `_methode-backlog.md`). Trop grosse → **CHAPEAU + sous-tâches**
  (`docs/backlog/_modele-chapeau.md`).
- **Gate humain** : jamais dans une fiche d'implémentation ni dans ses oracles → fiche
  séparée `categorie: humain` (`docs/backlog/_modele-fiche-humaine.md`).
- **Lève les verrous** que tu peux ; laisse la fiche **en maturation** tant qu'une décision
  reste ouverte. Ne la passe pas en `a-faire/` tant que TOUS les critères « Prêt à faire »
  de `docs/backlog/_methode-backlog.md` ne sont pas cochés.
- Ajoute une ligne dans `docs/backlog/maturation/INDEX.md` si l'idée n'y est pas.
