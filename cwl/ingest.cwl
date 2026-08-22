#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: CommandLineTool
label: "tiny-wae ingest — ingestion des chips d'un site"
doc: |
  Emballe `python -m tiny_wae ingest` (cf. cwl/README.md pour l'écart assumé vs
  cwl-assets : `tiny_wae` est un package installé, pas un script rsyncé).
  Prend en entrée soit `acquisitions` (enveloppe JSON produite par search.cwl —
  c'est le chaînage du workflow), soit le triplet `site`/`from_date`/`to_date` en
  recherche directe (les deux formes sont mutuellement exclusives côté CLI).

baseCommand: [python, -m, tiny_wae, ingest]

# OK=0 et FAILURE=1 (>=1 item en échec mais au moins un succès) sont tous deux acceptés :
# un échec partiel est un résultat métier légitime, pas un incident d'exécution — le
# forcer en erreur CWL casserait le workflow sur des runs par ailleurs sains.
# USAGE=2 (config/usage invalide) et INCONCLUSIVE=3 (aucun item n'a abouti, échecs
# réseau uniquement) restent des échecs CWL. Détail : cwl/README.md.
successCodes: [0, 1]

# ⛔ PAS d'`InlineJavascriptRequirement` ici — non supporté par PID-FLOW aujourd'hui, et
# inutile : `$(inputs.x)` est une référence de paramètre, toujours disponible sans lui.
# Cf. cwl/README.md. Ne pas le (ré)ajouter par réflexe.
requirements:
  EnvVarRequirement:
    envDef:
      # Surcharge de settings.data_root (mécanisme TINY_WAE_* d'adapters/config_io.py) —
      # c'est le levier utilisé par l'oracle O2 pour pointer deux data_root vierges
      # distincts entre le run CWL et le run CLI direct.
      TINY_WAE_DATA_ROOT: $(inputs.data_root)

inputs:
  data_root:
    type: string
    default: "./data"
    doc: "Surcharge TINY_WAE_DATA_ROOT — racine de stockage des chips ingérées."
  acquisitions:
    type: File?
    inputBinding:
      prefix: --acquisitions
    doc: "Enveloppe JSON déjà produite (chaînage CWL, cf. search.cwl)."
  site:
    type: string?
    inputBinding:
      prefix: --site
    doc: "Id du site (sites.yaml) — forme recherche directe."
  from_date:
    type: string?
    inputBinding:
      prefix: --from
    doc: "Début de fenêtre, YYYY-MM-DD (requis avec site)."
  to_date:
    type: string?
    inputBinding:
      prefix: --to
    doc: "Fin de fenêtre, YYYY-MM-DD (requis avec site)."
  force:
    type: boolean?
    default: false
    inputBinding:
      prefix: --force
    doc: "Ré-ingestion inconditionnelle (ignore l'idempotence grid_hash)."
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

# Pas de sortie capturée : `ingest` écrit ses chips/manifestes en dehors du répertoire de
# travail du tool (racine pilotée par `data_root`, potentiellement un chemin absolu externe
# au sandbox CWL — cf. cwl/README.md). Un `outputBinding.glob` ne peut PAS pointer un chemin
# absolu (interdit par la spec CWL) : tenté puis retiré, cf. note dans le README. Le succès
# de l'ingestion est signalé par le code de sortie (`successCodes` ci-dessus), pas par une
# sortie CWL.
outputs: []
