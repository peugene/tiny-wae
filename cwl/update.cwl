#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: CommandLineTool
label: "tiny-wae update — run quotidien, fenêtre depuis le dernier manifeste connu"
doc: |
  Emballe `python -m tiny_wae update` (cf. cwl/README.md pour l'écart assumé vs
  cwl-assets : `tiny_wae` est un package installé, pas un script rsyncé).
  Pour chaque site du parc (ou le sous-ensemble filtré par `sites`), calcule la
  fenêtre depuis le dernier manifeste connu (marge `incremental_margin_days`) et
  appelle `ingest` dessus. C'est le tool destiné à un ordonnancement quotidien
  (cron/PID-FLOW, hors lot — cf. chapeau l0-06).

baseCommand: [python, -m, tiny_wae, update]

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
    inputBinding:
      prefix: --sites
    doc: "Ids CSV à traiter, ou `all` (défaut CLI) pour tout le parc."
  now:
    type: string?
    inputBinding:
      prefix: --now
    doc: |
      Horodatage injecté (YYYY-MM-DD[THH:MM:SS]) — sans option, horloge système.
      Laisser vide pour un run réel planifié ; à fixer pour un run reproductible
      (c'est ce que fait l'oracle O2 pour comparer deux runs successifs).
  sites_path:
    type: File?
    inputBinding:
      prefix: --sites-path
    doc: "Chemin vers sites.yaml (défaut CLI : config/sites.yaml)."
  settings_path:
    type: File?
    inputBinding:
      prefix: --settings-path
    doc: "Chemin vers settings.yaml (défaut CLI : config/settings.yaml)."

# Pas de sortie CWL déclarée, même raison que ingest.cwl (cf. cwl/README.md) :
# `update` délègue l'ingestion effective à `ingest`, qui écrit hors du répertoire de
# travail du tool (racine posée par TINY_WAE_DATA_ROOT dans l'environnement du worker,
# potentiellement un chemin absolu
# externe au sandbox CWL — un outputBinding.glob absolu est interdit par la spec CWL).
# Le succès du run se lit au code de sortie (successCodes ci-dessus) et au résumé
# STDERR ; ce qui a été effectivement écrit se vérifie sur disque (manifestes
# `run.json`, cf. adapters/manifests.py), pas via une sortie CWL.
outputs: []
