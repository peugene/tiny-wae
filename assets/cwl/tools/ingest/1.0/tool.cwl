#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: CommandLineTool

label: "ingest"
doc: |
  Ingestion des chips d'un site tiny-wae.

  Emballe la sous-commande `ingest` de l'exécutable `tiny-wae` (cf. assets/cwl/README.md
  pour l'écart assumé vs cwl-assets : `tiny_wae` est un package Python installé qui
  expose un point d'entrée console, pas un script rsyncé sous
  WORKER_PYTHON_SCRIPTS_ROOT).
  Prend en entrée soit `acquisitions` (enveloppe JSON produite par le tool `search` —
  c'est le chaînage du workflow), soit le triplet `site`/`from_date`/`to_date` en
  recherche directe (les deux formes sont mutuellement exclusives côté CLI).

  La racine de stockage vient de TINY_WAE_DATA_ROOT, posée dans l'environnement du
  worker (aucun input CWL — cf. assets/cwl/README.md).

# Dépendance Python → capability "python" exigée du worker PID-FLOW : un worker sans
# `python` dans WORKER_CAPABILITIES ne prendra pas la tâche.
hints:
  - class: SoftwareRequirement
    packages:
      - package: python

# `tiny-wae` = point d'entrée console généré à l'installation du paquet, résolu sur le
# PATH du job. PAS `python -m tiny_wae` : `python` est le nom le plus surchargé du système
# et se résout silencieusement sur un interpréteur sans le paquet. Détail : README.
baseCommand: [tiny-wae, ingest]

# OK=0 et FAILURE=1 (>=1 item en échec mais au moins un succès) sont tous deux acceptés :
# un échec partiel est un résultat métier légitime, pas un incident d'exécution — le
# forcer en erreur CWL casserait le workflow sur des runs par ailleurs sains.
# USAGE=2 (config/usage invalide) et INCONCLUSIVE=3 (aucun item n'a abouti, échecs
# réseau uniquement) restent des échecs CWL. Détail : assets/cwl/README.md.
successCodes: [0, 1]

inputs:
  acquisitions:
    type: File?
    label: "Acquisitions (enveloppe JSON)"
    doc: "Enveloppe JSON déjà produite (chaînage CWL, cf. le tool `search`)."
    inputBinding:
      prefix: --acquisitions
  site:
    type: string?
    label: "Site"
    doc: "Id du site (sites.yaml) — forme recherche directe."
    inputBinding:
      prefix: --site
  from_date:
    type: string?
    label: "Début de fenêtre"
    doc: "Début de fenêtre, YYYY-MM-DD (requis avec site)."
    inputBinding:
      prefix: --from
  to_date:
    type: string?
    label: "Fin de fenêtre"
    doc: "Fin de fenêtre, YYYY-MM-DD (requis avec site)."
    inputBinding:
      prefix: --to
  force:
    type: boolean?
    default: false
    label: "Ré-ingestion forcée"
    doc: "Ré-ingestion inconditionnelle (ignore l'idempotence grid_hash)."
    inputBinding:
      prefix: --force
  sites_path:
    type: File?
    label: "Fichier sites.yaml"
    doc: "Chemin vers sites.yaml (défaut CLI : config/sites.yaml)."
    inputBinding:
      prefix: --sites-path
  settings_path:
    type: File?
    label: "Fichier settings.yaml"
    doc: "Chemin vers settings.yaml (défaut CLI : config/settings.yaml)."
    inputBinding:
      prefix: --settings-path

# Pas de sortie capturée : `ingest` écrit ses chips/manifestes en dehors du répertoire de
# travail du tool (racine posée par TINY_WAE_DATA_ROOT dans l'environnement du worker,
# potentiellement un chemin absolu externe au sandbox CWL — cf. assets/cwl/README.md).
# Un `outputBinding.glob` ne peut PAS pointer un chemin absolu (interdit par la spec CWL) :
# tenté puis retiré, cf. note dans le README. Le succès de l'ingestion est signalé par le
# code de sortie (`successCodes` ci-dessus), pas par une sortie CWL.
outputs: []
