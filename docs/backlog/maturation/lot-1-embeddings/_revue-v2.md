# Revue v2 — Chantier Lot 1 (externe, INTERROMPUE)

**Date** : 24/08/2026 · **Origine** : revue externe fournie par Philippe (le modèle a
crashé avant la fin — le finding m2 est tronqué, la suite éventuelle est perdue).
**Contre-vérification** : chaque citation revérifiée par l'orchestrateur contre les fiches
et le dépôt réels avant prise en compte. **Verdict : 5/5 findings confirmés, zéro faux
positif** — un taux que ni la v1 ni son réfuteur n'avaient atteint.

Sa force : elle a regardé là où la v1 ne pouvait pas — **l'intersection des fiches et de
l'infrastructure du dépôt** (CI, worktrees, carte des zones, code du Lot 0 cité
fichier:ligne).

## Findings retenus et corrections appliquées

**B1 [BLOQUANT] — Le gate serait rouge en CI et dans tout worktree neuf dès `l1-03.4`.**
Chaîne vérifiée : CI = `just install` + `just check` → `check` inclut `smoke` → le smoke
charge un vrai modèle sous la garde offline → cache gitignoré, `fetch-models` hors gate →
**rouge à chaque commit, partout où le cache n'existe pas**. Le commentaire de `ci.yml`
(« le smoke est déterministe et hors ligne ») était vrai du Lot 0, faux dès `l1-03.4`.
Ironie assumée : ce commentaire corrige le constat A1 de la post-revue du Lot 0 — la
correction de « la CI diverge du gate » a créé « le gate exige un état que la CI n'a pas ».
→ **Fiche neuve `l1-07` « Gate avec poids »** (CI : fetch + cache d'actions ; worktrees :
`hf_home` partagé absolu via `.env`) ; `l1-03.4` en dépend désormais. ⚠ Le point « qui
possède `.github/` » est remonté à Philippe dans la fiche — précédent existant : c'est
l'équipe qui a livré `codeql.yml` et Dependabot.

**M1 [MAJEUR] — `l1-00` ne nommait pas le mécanisme réconciliant deptry / wheel légère /
env de dev.** → Tranché dans `l1-00` : **extra PEP 621 `[project.optional-dependencies]
models`**, la feature pixi s'y adosse ; « deptry compte les extras comme déclarées » mis en
oracle (à confirmer à l'implémentation), pas affirmé.

**M2 [MAJEUR] — `read_vector(dir, model_id)` incohérent avec le nom
`<model_id>.<spec_hash[:8]>.npy`** : impossible de désambiguïser deux variantes de spec, et
le glob « un seul match » casserait le scénario O5 de `l1-03.2`. Défaut né de MA passe de
correction (K-20 appliqué sans propager à la signature — la règle « qui consomme ce que je
viens de changer ? » prise en défaut chez celui qui l'a écrite). → Signature corrigée :
`read_vector(dir, model_id, spec_hash)`.

**m1 [MINEUR] — `--cloud-max` utilisé par la checklist de `l1-05.3.H` mais défini par
aucune fiche CLI.** → Option ajoutée aux interfaces de `l1-03.2` et `l1-03.3` (une commande
copiable pour un humain vaut mieux qu'une variable d'environnement).

**m2 [MINEUR, tronqué] — `FakeEmbeddingModel` sous-spécifié** : `l1-03.2`/O6 exige un
double qui « lève sur un id », `l1-03.3`/O4 un signal de progression pour le jalon SIGINT —
capacités absentes de la spec du double en `l1-01.3`. → Spec complétée : `fail_on`,
`delay_s`, notification de progression.

## Limite

La revue est **incomplète** : elle s'est arrêtée au milieu de m2, dans la section des
mineurs. Ce qui précédait (graphe, décisions, critères de sortie, faits du Lot 0) avait été
balayé avec verdict « sain » ; la perte probable se limite donc à d'éventuels mineurs
supplémentaires. À garder en tête si un défaut de cette famille ressort à l'implémentation.
