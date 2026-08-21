#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: Workflow
label: "tiny-wae — search puis ingest, chaînés par l'enveloppe JSON"
doc: |
  Chaîne les deux CommandLineTools : `search` écrit son enveloppe JSON dans un
  fichier (invariant STDOUT-JSON de l0-02.2, ici redirigé vers un fichier via
  `--json` pour rester robuste en exécution CWL), `ingest` la consomme via
  `--acquisitions`. Cf. cwl/README.md pour le périmètre (validation locale
  uniquement — PAS d'enregistrement server, PAS de `pid:Milestone`).

inputs:
  site:
    type: string
    doc: "Id du site (config/sites.yaml)."
  from_date:
    type: string
    doc: "Début de fenêtre, YYYY-MM-DD."
  to_date:
    type: string
    doc: "Fin de fenêtre, YYYY-MM-DD."
  data_root:
    type: string
    default: "./data"
    doc: "Surcharge TINY_WAE_DATA_ROOT — racine de stockage des chips ingérées."
  sites_path:
    type: File?
    doc: "Chemin vers sites.yaml (défaut CLI : config/sites.yaml)."
  settings_path:
    type: File?
    doc: "Chemin vers settings.yaml (défaut CLI : config/settings.yaml)."

outputs:
  acquisitions:
    type: File
    outputSource: search_step/acquisitions
    doc: "Enveloppe JSON des items STAC trouvés (sortie intermédiaire, exposée pour audit)."
  # Pas de sortie pour ingest_step : `ingest` écrit en dehors du sandbox CWL (racine
  # pilotée par `data_root`, potentiellement un chemin absolu — cf. cwl/ingest.cwl et
  # cwl/README.md). Le succès du step est signalé par son code de sortie.

steps:
  search_step:
    run: search.cwl
    in:
      site: site
      from_date: from_date
      to_date: to_date
      sites_path: sites_path
      settings_path: settings_path
    out: [acquisitions]

  ingest_step:
    run: ingest.cwl
    in:
      acquisitions: search_step/acquisitions
      data_root: data_root
      sites_path: sites_path
      settings_path: settings_path
    out: []
