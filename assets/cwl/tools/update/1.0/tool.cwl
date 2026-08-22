#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: CommandLineTool

label: "update"
doc: |
  Run quotidien tiny-wae : fenêtre depuis le dernier manifeste connu.

  Emballe la sous-commande `update` de l'exécutable `tiny-wae` (cf. assets/cwl/README.md
  pour l'écart assumé vs cwl-assets : `tiny_wae` est un package Python installé qui
  expose un point d'entrée console, pas un script rsyncé sous
  WORKER_PYTHON_SCRIPTS_ROOT).
  Pour chaque site du parc (ou le sous-ensemble filtré par `sites`), calcule la
  fenêtre depuis le dernier manifeste connu (marge `incremental_margin_days`) et
  appelle `ingest` dessus. C'est le tool destiné à un ordonnancement quotidien
  (cron/PID-FLOW, hors lot — cf. chapeau l0-06).

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
baseCommand: [tiny-wae, update]

# OK=0 (aucun échec) et FAILURE=1 (>=1 échec avec au moins un succès, OU au moins un
# site vierge sans aucun manifeste connu — cf. cli/update.py) sont tous deux acceptés :
# un site vierge n'est pas un incident d'exécution, c'est un résultat métier légitime
# qui pointe vers `backfill` (hors périmètre d'`update`, cf. l0-05.2). Le forcer en
# erreur CWL casserait le run quotidien sur un parc par ailleurs sain, dès qu'un site
# vient d'être ajouté à sites.yaml sans backfill préalable.
# USAGE=2 (config/usage invalide) et INCONCLUSIVE=3 (tous les échecs sont d'origine
# réseau, aucun site n'a abouti) restent des échecs CWL — un run quotidien qui ne fait
# QUE des erreurs réseau doit remonter en échec, pas se fondre dans le succès silencieux.
successCodes: [0, 1]

inputs:
  sites:
    type: string?
    label: "Sites à traiter"
    doc: "Ids CSV à traiter, ou `all` (défaut CLI) pour tout le parc."
    inputBinding:
      prefix: --sites
  now:
    type: string?
    label: "Horodatage injecté"
    doc: |
      Horodatage injecté (YYYY-MM-DD[THH:MM:SS]) — sans option, horloge système.
      Laisser vide pour un run réel planifié ; à fixer pour un run reproductible
      (c'est ce que fait l'oracle O2 pour comparer deux runs successifs).
    inputBinding:
      prefix: --now
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

# Pas de sortie CWL déclarée, même raison que le tool `ingest` (cf. assets/cwl/README.md) :
# `update` délègue l'ingestion effective à `ingest`, qui écrit hors du répertoire de
# travail du tool (racine posée par TINY_WAE_DATA_ROOT dans l'environnement du worker,
# potentiellement un chemin absolu externe au sandbox CWL — un outputBinding.glob absolu
# est interdit par la spec CWL). Le succès du run se lit au code de sortie (successCodes
# ci-dessus) et au résumé STDERR ; ce qui a été effectivement écrit se vérifie sur disque
# (manifestes `run.json`, cf. adapters/manifests.py), pas via une sortie CWL.
outputs: []
