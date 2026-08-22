#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: Workflow

label: "tiny-wae"
doc: |
  Chaîne les deux CommandLineTools tiny-wae : `search` écrit son enveloppe JSON dans un
  fichier (invariant STDOUT-JSON de l0-02.2, ici redirigé vers un fichier via `--json`
  pour rester robuste en exécution CWL), `ingest` la consomme via `--acquisitions`.

  Les deux tools sont des tools PARTAGÉS (`tools/<nom>/1.0/tool.cwl`), pas des tools
  internes embarqués : `update` les rejoint sous la même racine et le lot suivant pourra
  les recomposer. Cf. assets/cwl/README.md pour le périmètre (validation locale
  uniquement — PAS d'enregistrement server, PAS de `pid:Milestone`).

inputs:
  site:
    type: string
    label: "Site"
    doc: "Id du site (config/sites.yaml)."
  from_date:
    type: string
    label: "Début de fenêtre"
    doc: "Début de fenêtre, YYYY-MM-DD."
  to_date:
    type: string
    label: "Fin de fenêtre"
    doc: "Fin de fenêtre, YYYY-MM-DD."
  sites_path:
    type: File?
    label: "Fichier sites.yaml"
    doc: "Chemin vers sites.yaml (défaut CLI : config/sites.yaml)."
  settings_path:
    type: File?
    label: "Fichier settings.yaml"
    doc: "Chemin vers settings.yaml (défaut CLI : config/settings.yaml)."

outputs:
  acquisitions:
    type: File
    label: "Acquisitions (enveloppe JSON)"
    doc: "Enveloppe JSON des items STAC trouvés (sortie intermédiaire, exposée pour audit)."
    outputSource: search_step/acquisitions
  # Pas de sortie pour ingest_step : `ingest` écrit en dehors du sandbox CWL (racine
  # posée par TINY_WAE_DATA_ROOT dans l'environnement du worker, potentiellement un
  # chemin absolu — cf. tools/ingest/1.0/tool.cwl et assets/cwl/README.md). Le succès du
  # step est signalé par son code de sortie.

steps:
  search_step:
    label: "Recherche STAC"
    run: ../../../tools/search/1.0/tool.cwl
    in:
      site: site
      from_date: from_date
      to_date: to_date
      sites_path: sites_path
      settings_path: settings_path
    out: [acquisitions]

  ingest_step:
    label: "Ingestion des chips"
    run: ../../../tools/ingest/1.0/tool.cwl
    in:
      acquisitions: search_step/acquisitions
      sites_path: sites_path
      settings_path: settings_path
    out: []
