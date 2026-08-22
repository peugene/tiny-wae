---
id: <NN-slug>.R          # suffixe .R = rétroactive, sur le modèle du .H des fiches humaines
titre: "[RÉTROACTIVE] Objet du travail déjà réalisé"
effort: "—"              # rien à faire : le code existe déjà
categorie: documentaire  # ⭐ exempte la fiche des contrôles de graphe (isolée / feuille)
phase: <O1|O2|O3>
depends_on: []           # une fiche documentaire n'ordonne rien et n'est ordonnée par rien
parent:
subtasks: []
---

# [<NN-slug>.R] — RÉTROACTIVE : titre

> 📘 **Fiche documentaire, écrite APRÈS coup.** Elle ne demande aucun travail : elle
> enregistre un travail déjà livré, réalisé hors du cycle `maturation → a-faire →
> en-cours → fait`. Rien à dispatcher.
> **Constat d'origine** : <revue / incident / demande qui a rendu ce trou visible>.

## Pourquoi cette fiche existe

<Quel travail a échappé au cycle, et pourquoi c'est un problème : le backlog « fait foi »,
or il ne portait pas trace de ce travail. Dire concrètement ce qu'un lecteur futur aurait
ignoré.>

⚠ **Cette fiche est un précédent, pas une pratique.** Écrire une fiche après le code
inverse la règle du projet. Elle se justifie quand le travail porte des décisions
structurantes qui seront relues plus tard. Le réflexe correct reste : une contrainte
externe arrive en cours de lot → **elle produit une fiche AVANT d'être implémentée**,
même courte.

## Ce qui a été livré (déjà en place)

| Commit | Objet |
|---|---|
| `<sha>` | … |

**Bilan mesuré** : <fichiers touchés, lignes, évolution du nombre de tests>.

### <Décision ou changement 1>

<Le QUOI en deux lignes, puis le POURQUOI — c'est le pourquoi qu'on re-découvre à ses
dépens. Reprendre le corps du commit plutôt que le résumer : il a été écrit au moment où
l'auteur savait.>

## Ce qui garde tout ça

<Les garde-fous automatiques posés par ce travail. Une fiche rétroactive qui ne liste que
des décisions laisse croire qu'elles tiennent toutes seules.>

| Garde-fou | Ce qu'il attrape |
|---|---|
| `<test>` | … |

## Vérifications effectuées à l'époque

<Mesures réelles, avec les chiffres. Distinguer « exécuté » de « déclaré ».>

## ⚠ Ce qui N'A PAS été revérifié

<Le point le plus important d'une fiche rétroactive : quels oracles de fiches déjà closes
ce travail a-t-il potentiellement invalidés ? Un refactor qui touche ce qu'un oracle
vérifie périme cet oracle, même si tout reste vert par ailleurs.>

| Oracle | Attendu | Mesuré | Verdict |
|---|---|---|---|
| `<fiche> / <O_n>` | … | *à remplir* | ⬜ |

## À reporter dans les fiches closes

<Les fiches en `fait/` que ce travail a rendues fausses. Règle : **ajouter un
post-scriptum daté**, ne pas réécrire l'historique d'une fiche close.>

## Définition de « terminé » pour cette fiche

Purement documentaire : terminée quand **(a)** les oracles ci-dessus ont été rejoués et
consignés, **(b)** les post-scriptums ont été ajoutés aux fiches closes concernées, et
**(c)** la fiche a été déplacée en `fait/`. Aucun code à écrire.
