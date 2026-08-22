#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: CommandLineTool
label: "tiny-wae search — recherche STAC d'un site sur une fenêtre"
doc: |
  Emballe `python -m tiny_wae search` (cf. cwl/README.md pour l'écart assumé vs
  cwl-assets : `tiny_wae` est un package installé, pas un script rsyncé).
  Écrit l'enveloppe JSON dans un fichier (`--json`) plutôt que sur STDOUT — c'est
  le point de chaînage du workflow (cf. workflow.cwl).

baseCommand: [python, -m, tiny_wae, search]

# Seul le succès plein (OK=0) est accepté ici : un endpoint injoignable (INCONCLUSIVE=3),
# une config invalide (USAGE=2) ou un échec métier (FAILURE=1) doivent arrêter le workflow —
# cf. cwl/README.md pour la justification complète des successCodes de chaque tool.
successCodes: [0]

inputs:
  site:
    type: string
    inputBinding:
      prefix: --site
    doc: "Id du site (config/sites.yaml)."
  from_date:
    type: string
    inputBinding:
      prefix: --from
    doc: "Début de fenêtre, YYYY-MM-DD."
  to_date:
    type: string
    inputBinding:
      prefix: --to
    doc: "Fin de fenêtre, YYYY-MM-DD."
  json_out:
    type: string
    default: acquisitions.json
    inputBinding:
      prefix: --json
    doc: "Nom du fichier où écrire l'enveloppe JSON (point de chaînage vers ingest)."
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

outputs:
  acquisitions:
    type: File
    outputBinding:
      glob: $(inputs.json_out)
    doc: "Enveloppe JSON des items STAC trouvés — consommée par ingest.cwl."
