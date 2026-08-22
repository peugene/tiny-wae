#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: CommandLineTool

label: "search"
doc: |
  Recherche STAC d'un site tiny-wae sur une fenêtre temporelle.

  Emballe `python -m tiny_wae search` (cf. assets/cwl/README.md pour l'écart assumé
  vs cwl-assets : `tiny_wae` est un package Python installé, pas un script rsyncé
  sous WORKER_PYTHON_SCRIPTS_ROOT).
  Écrit l'enveloppe JSON dans un FICHIER (`--json`) plutôt que sur STDOUT — c'est le
  point de chaînage vers le tool `ingest` (cf. workflows/tiny-wae/1.0/workflow.cwl).

# Dépendance Python → capability "python" exigée du worker PID-FLOW : un worker sans
# `python` dans WORKER_CAPABILITIES ne prendra pas la tâche.
hints:
  - class: SoftwareRequirement
    packages:
      - package: python

baseCommand: [python, -m, tiny_wae, search]

# Seul le succès plein (OK=0) est accepté ici : un endpoint injoignable (INCONCLUSIVE=3),
# une config invalide (USAGE=2) ou un échec métier (FAILURE=1) doivent arrêter le workflow —
# cf. assets/cwl/README.md pour la justification complète des successCodes de chaque tool.
successCodes: [0]

inputs:
  site:
    type: string
    label: "Site"
    doc: "Id du site (config/sites.yaml)."
    inputBinding:
      prefix: --site
  from_date:
    type: string
    label: "Début de fenêtre"
    doc: "Début de fenêtre, YYYY-MM-DD."
    inputBinding:
      prefix: --from
  to_date:
    type: string
    label: "Fin de fenêtre"
    doc: "Fin de fenêtre, YYYY-MM-DD."
    inputBinding:
      prefix: --to
  json_out:
    type: string
    default: "acquisitions.json"
    label: "Nom du fichier d'enveloppe JSON"
    doc: |
      Nom du fichier où écrire l'enveloppe JSON (point de chaînage vers `ingest`).
      ⚠ Le glob de la sortie `acquisitions` est LITTÉRAL et doit rester identique à ce
      défaut : PID-FLOW n'évalue pas les expressions CWL, un glob calculé depuis cet
      input ne matcherait rien. Surcharger `json_out` casse donc la capture de la
      sortie — garde-fou : tests/test_cwl.py, test_search_glob_litteral_colle_au_default.
    inputBinding:
      prefix: --json
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

outputs:
  acquisitions:
    type: File
    label: "Acquisitions (enveloppe JSON)"
    doc: "Enveloppe JSON des items STAC trouvés — consommée par le tool `ingest`."
    outputBinding:
      glob: "acquisitions.json"
