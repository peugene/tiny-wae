"""Tests cwl/ (l0-06.1) — cohérence entre les .cwl et les CLI réels.

`cwltool --validate` (recette `just cwl`) ne connaît RIEN de nos CLI : un fichier CWL
syntaxiquement valide qui référence une option renommée passera la validation sans
broncher, et le workflow cassera silencieusement à l'exécution. C'est le seul angle mort
de `just cwl`, et c'est ce que ce module comble (décision d'ancrage n°3 de la fiche) :
chaque fichier `.cwl` est chargé en YAML brut (`yaml.safe_load` — un `.cwl` EST un YAML),
et chaque `inputBinding.prefix` qu'il déclare est confronté aux options réellement
exposées par le CLI `typer`/`click` correspondant (via `typer.main.get_command`, jamais
via un parsing de `--help`). Renommer une option d'un CLI sans toucher au `.cwl` fait
échouer ce test — c'est l'oracle O3 de la fiche (qui REMPLACE l'O3 initial de la fiche,
déjà couvert ailleurs par les tests de l0-02.2 sur l'invariant STDOUT-JSON).

Couvre aussi, plus superficiellement :
- que `baseCommand` pointe bien vers le module `tiny_wae` et la sous-commande attendue ;
- que le workflow chaîne bien `search_step/acquisitions` -> `ingest_step/acquisitions`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer.main
import yaml

from tiny_wae.__main__ import app

CWL_DIR = Path(__file__).resolve().parent.parent / "cwl"

# Commande click racine (group) exposant les sous-commandes typer du projet.
_click_root = typer.main.get_command(app)


def _cli_option_prefixes(command_name: str) -> set[str]:
    """Renvoie l'ensemble des chaînes d'option (ex. ``--site``) réellement exposées par
    la sous-commande `command_name` du CLI (`python -m tiny_wae <command_name>`)."""
    command = _click_root.commands[command_name]  # type: ignore[attr-defined]
    prefixes: set[str] = set()
    for param in command.params:
        prefixes.update(param.opts)
    return prefixes


def _load_cwl(name: str) -> dict[str, Any]:
    """Charge un fichier `.cwl` comme le YAML qu'il est (aucun parseur CWL dédié ici :
    on veut lire les champs bruts, pas les faire valider par cwltool)."""
    text = (CWL_DIR / name).read_text(encoding="utf-8")
    loaded = yaml.safe_load(text)
    assert isinstance(loaded, dict)
    return loaded


def _declared_prefixes(cwl_doc: dict[str, Any]) -> dict[str, str]:
    """Extrait {nom d'input CWL: prefix déclaré} pour tous les inputs qui portent un
    `inputBinding.prefix` (les autres, ex. `data_root` d'ingest.cwl, ne passent par
    aucune option CLI — normal, ne rien exiger dessus)."""
    inputs = cwl_doc["inputs"]
    declared: dict[str, str] = {}
    for name, spec in inputs.items():
        if isinstance(spec, dict):
            binding = spec.get("inputBinding")
            if isinstance(binding, dict) and "prefix" in binding:
                declared[name] = binding["prefix"]
    return declared


def test_search_cwl_base_command() -> None:
    """`search.cwl` appelle bien `python -m tiny_wae search` (décision d'ancrage n°1)."""
    doc = _load_cwl("search.cwl")
    assert doc["baseCommand"] == ["python", "-m", "tiny_wae", "search"]


def test_ingest_cwl_base_command() -> None:
    """`ingest.cwl` appelle bien `python -m tiny_wae ingest`."""
    doc = _load_cwl("ingest.cwl")
    assert doc["baseCommand"] == ["python", "-m", "tiny_wae", "ingest"]


def test_search_cwl_prefixes_match_real_cli_options() -> None:
    """Oracle O3 (remplacé) : chaque prefix de search.cwl est une option réelle de
    `python -m tiny_wae search`. Casse si une option de cli/search.py est renommée
    sans mettre à jour cwl/search.cwl."""
    doc = _load_cwl("search.cwl")
    declared = _declared_prefixes(doc)
    assert declared, "search.cwl doit déclarer au moins un inputBinding.prefix"
    real_options = _cli_option_prefixes("search")
    for cwl_input_name, prefix in declared.items():
        assert prefix in real_options, (
            f"search.cwl: input {cwl_input_name!r} déclare le prefix {prefix!r}, "
            f"absent des options réelles de `search` ({sorted(real_options)})"
        )


def test_ingest_cwl_prefixes_match_real_cli_options() -> None:
    """Même oracle pour ingest.cwl — inclut `--acquisitions`, le point de chaînage."""
    doc = _load_cwl("ingest.cwl")
    declared = _declared_prefixes(doc)
    assert declared, "ingest.cwl doit déclarer au moins un inputBinding.prefix"
    real_options = _cli_option_prefixes("ingest")
    for cwl_input_name, prefix in declared.items():
        assert prefix in real_options, (
            f"ingest.cwl: input {cwl_input_name!r} déclare le prefix {prefix!r}, "
            f"absent des options réelles de `ingest` ({sorted(real_options)})"
        )
    assert "--acquisitions" in real_options, (
        "le CLI ingest doit toujours exposer --acquisitions : c'est le point de "
        "chaînage du workflow CWL (cf. cwl/workflow.cwl)"
    )


def test_ingest_cwl_declares_data_root_env_var_requirement() -> None:
    """L'oracle O2 repose sur TINY_WAE_DATA_ROOT posé via EnvVarRequirement (ingest n'a
    aucune option --data-root — cf. cwl/README.md)."""
    doc = _load_cwl("ingest.cwl")
    requirements = doc.get("requirements", {})
    env_req = requirements.get("EnvVarRequirement")
    assert env_req is not None, "ingest.cwl doit déclarer un EnvVarRequirement"
    assert "TINY_WAE_DATA_ROOT" in env_req.get("envDef", {})


def test_workflow_cwl_chains_search_output_into_ingest_input() -> None:
    """Le workflow chaîne bien la sortie `acquisitions` du step search vers l'entrée
    `acquisitions` du step ingest (le fil du chaînage, décision d'ancrage n°4)."""
    doc = _load_cwl("workflow.cwl")
    steps = doc["steps"]
    ingest_step = steps["ingest_step"]
    assert ingest_step["in"]["acquisitions"] == "search_step/acquisitions"
    assert ingest_step["run"] == "ingest.cwl"
    assert steps["search_step"]["run"] == "search.cwl"


def test_workflow_cwl_output_sources_point_to_declared_steps() -> None:
    """Les outputSource du workflow référencent des steps/sorties qui existent
    réellement (pas un copier-coller périmé après renommage d'un step)."""
    doc = _load_cwl("workflow.cwl")
    steps = doc["steps"]
    for _out_name, out_spec in doc["outputs"].items():
        source = out_spec["outputSource"]
        step_name, step_output = source.split("/", 1)
        assert step_name in steps, f"step {step_name!r} inconnu (outputSource {source!r})"
        assert step_output in steps[step_name]["out"], (
            f"{source!r} référence une sortie absente de steps[{step_name!r}]['out']"
        )
