---
description: Revue adversariale (cohérence d'un chantier, ou d'un diff)
---
Mène une **revue adversariale** de : $ARGUMENTS (un chantier de maturation, un diff, ou un lot de
fiches).

## Mécanique (éprouvée : 23 findings bruts → 14 confirmés → 3 bloquants réels sur un chantier auth)

1. **Angles indépendants en parallèle** (un agent par angle, aveugles les uns aux autres) :
   découpage/granularité, dépendances/séquençage, pièges & sécurité, couverture/angles morts,
   effort/réalisme. Chaque angle est vérifié **contre le code réel** (« LIS les fichiers réels du
   dépôt avant de juger — n'invente rien, ne suppose rien ») et chaque finding porte une **preuve
   obligatoire** (citation exacte ou référence fichier:ligne) + sévérité + action recommandée.
2. ⭐ **L'angle « couverture » reçoit la liste EXHAUSTIVE des règles/décisions actées** en
   discussion (numérotées, une ligne chacune) et vérifie que CHACUNE est couverte par au moins une
   fiche, sans contradiction entre fiches, et sans scope creep. C'est l'angle au meilleur
   rendement observé — mais il ne vaut que ce que vaut la liste : la constituer au fil de la
   maturation, pas la reconstituer de mémoire à la fin.
3. **Réfutation indépendante** : chaque finding brut passe devant un agent réfuteur qui **revérifie
   à la source** (« ne fais pas confiance à l'énoncé ») et tranche : confirmé ou réfuté (faux
   positif, hors périmètre, déjà correct). Seuls les confirmés entrent en synthèse — sans cette
   passe, ~40 % de bruit.
4. **Synthèse** actionnable : verdict global, issues consolidées par sévérité décroissante
   (ne PAS marquer « corrigé » — la correction s'applique après), fiches à
   créer/scinder/fusionner/requalifier, questions ouvertes nécessitant un GO humain (souvent vide
   si la maturation a bien tranché — le dire explicitement), deltas de roadmap, prochaines actions.

Pour un **chantier** : produis `_revue.md` → `revue.html` (cf. `docs/backlog/_modele-chantier.md`
et les templates roadmap/revue). Sois **sévère** : cherche les vrais problèmes, pas des broutilles.

⚠ **Traçabilité des décisions** : ce que la revue recommande n'est pas ce que l'humain décide.
Après le GO, requalifier les mentions « précisé en revue » en « décision <prénom>, GO du
<date> » dans les fiches.
