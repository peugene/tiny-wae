---
id: NN-slug
titre: Titre court de la tâche
effort: S            # S | M | L | XL — barème : S ≤ 1 session d'agent · M ≤ 2-3 ·
                     # L = plusieurs (scinder si possible) · XL = INTERDIT en a-faire/
categorie: pipeline  # taxonomie libre ; valeurs réservées : `chapeau`, `humain`
phase:               # optionnel : id de phase DANS un chantier (ex. O1) — sinon vide
depends_on: []       # ids de fiches à terminer avant celle-ci (ex. [00-socle])
parent:              # optionnel : id de la fiche CHAPEAU dont celle-ci est une sous-tâche
subtasks: []         # si CHAPEAU : ids des sous-tâches (le chapeau ne se dispatche pas)
---

# [NN] — Titre de la tâche

> Fiche de backlog : sert de **brief (prompt)** pour l'IA.
> Avancement = dossier : `maturation/` → `a-faire/` → `en-cours/` → `fait/`.
> En `a-faire/`, ce brief doit être **autonome** : implémentable sans question ni décision
> (cf. « Prêt à faire » du `README.md`).

## Objectif

[Le résultat attendu : QUOI et POURQUOI. 2-3 phrases.]

## Contexte et périmètre

[Où ça se passe : modules / CLIs / fichiers **nommés**. Contraintes.
Si le schéma BD bouge : livrer le schéma cible **et** le script de migration.]

## Définition de « terminé »

- [ ] [ce qui doit EXISTER, concret et vérifiable]
- [ ] …

## Oracle / recette (figé AVANT implémentation)

> Le « terminé » dit ce qui existe ; l'oracle dit ce qui est **mesuré**, avec quel **seuil**,
> et ce qui n'est **pas testé**. Il se fige à la rédaction de la fiche, jamais après coup.

| # | Critère mesuré | Seuil de succès |
|---|---|---|
| O1 | [métrique ou vérification] | [seuil chiffré ou verdict binaire] |

**Non testé par cette fiche** : [le dire explicitement — chiffres honnêtes.]

## Notes / pistes (optionnel)

[Approche envisagée, points de vigilance, décisions liées, liens utiles.]

---

## Résumé de réalisation

*(à remplir avant de déplacer la fiche dans `fait/`)*

- **Ce qui a été fait** : …
- **Verdict de l'oracle** : [chiffres obtenus, y compris défavorables]
- **Commit(s)** : …
- **Date** : AAAA-MM-JJ
