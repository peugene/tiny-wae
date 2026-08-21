---
id: l0-06-cwl-steps
titre: Définitions CWL des steps d'ingestion + chaîne (exemple - cwl-assets)
effort: M
categorie: outillage
phase: O3
depends_on: [l0-05-incremental]
---

# [l0-06] — Emballage CWL du pipeline

> Fiche de backlog : brief pour l'IA. En `a-faire/`, ce brief doit être autonome.

## Objectif

Rendre le pipeline orchestrable par le moteur CWL de Philippe (PID-FLOW) : un
CommandLineTool CWL par CLI (search, ingest, update, report), une chaîne Workflow, sur le
modèle du dépôt `cwl-assets` (motivation : anticiper l'intégration pour de futurs clients).

## Contexte et périmètre

- Répertoire `cwl/` dans tiny-wae : tools + workflow, spec **CWL v1.2** en 1re ligne
  (convention cwl-assets).
- S'inspirer de `cwl-assets` (dépôt voisin) : templates `tool-python.cwl`,
  `workflow-with-milestones.cwl`, conventions `baseCommand` en chemin relatif au scripts
  root, hints `SoftwareRequirement`. **S'inspirer ≠ copier** : tiny-wae garde ses CLIs
  installés (package), pas des scripts déployés par rsync — le `baseCommand` sera
  `python -m tiny_wae …` ; noter l'écart et sa raison dans un README du dossier `cwl/`.
- Milestones IHM (`pid:Milestone`) sur les steps de 1er niveau du workflow.
- Validation : `cwltool --validate` sur chaque fichier + **un run local `cwltool`** du
  workflow sur 1 site / petite fenêtre (équivalent `bin/run-local.sh` de cwl-assets).

## Définition de « terminé »

- [ ] `cwl/` : ≥ 3 tools (search, ingest, update) + 1 workflow, tous validés.
- [ ] Run local cwltool du workflow OK sur 1 site (mêmes sorties que le CLI direct).
- [ ] README `cwl/` : conventions, écarts avec cwl-assets, commande de validation.

## Oracle / recette (figé AVANT implémentation)

| # | Critère mesuré | Seuil de succès |
|---|---|---|
| O1 | `cwltool --validate` sur tous les .cwl | 0 erreur |
| O2 | Run local du workflow (1 site, 10 jours) vs CLI direct | manifestes équivalents (mêmes statuts/comptes) |
| O3 | Enregistrement PID-FLOW réel | **selon Q-D** (revue) : hors périmètre par défaut — le dire explicitement dans le README |

**Non testé par cette fiche** : exécution par un worker PID-FLOW réel (dépend de Q-D et de
l'environnement de Philippe — geste d'infra).

## Notes / pistes

Verrou avant `a-faire/` : trancher **Q-D** (validation locale seule vs enregistrement
server). Dépendance externe à nommer si Q-D = enregistrement : version PID-FLOW cible
(règle cwl-assets : l'ordre de livraison inter-dépôts n'est jamais un détail).

---

## Résumé de réalisation

*(à remplir avant de déplacer la fiche dans `fait/`)*
