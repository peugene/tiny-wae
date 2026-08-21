---
id: NN-slug.H
titre: "[HUMAIN] Objet de la validation / du geste humain"
effort: H            # H = humain, hors barème agent
categorie: humain
phase:
depends_on: [NN-slug.n]   # la ou les fiches qui produisent l'artefact à valider
parent: NN-slug
---

# [NN.H] — ⛔ FICHE HUMAINE — NE PAS DISPATCHER À UN AGENT

> **Cette fiche est réalisée par un humain.** Aucun agent IA ne doit la prendre,
> l'implémenter, ni la déplacer en son nom. Les fiches aval en dépendent via `depends_on` :
> **le run se met en pause ici** — c'est le comportement voulu (gate humain).
>
> Règle de méthode : un gate humain ne vit JAMAIS dans une fiche d'implémentation (ni dans
> ses oracles). Il devient une fiche séparée `categorie: humain`, dont l'artefact d'entrée
> est produit par une fiche agent avec des critères mécaniques.

## Objet

[Ce qui est à valider ou à faire, et pourquoi une machine ne peut pas le faire.]

## Checklist

- [ ] [geste 1 — commande exacte si applicable]
- [ ] [geste 2 …]
- [ ] Déplacer cette fiche en `fait/` avec deux lignes de résumé.

## Critère de sortie

[Ce qui doit être vrai pour que le run reprenne. Décisions éventuelles à consigner ici.]

---
## Résumé de réalisation
*(rempli par l'humain : ce qui a été validé/corrigé, date, verdict)*
