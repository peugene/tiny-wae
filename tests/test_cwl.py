"""Tests assets/cwl/ (l0-06.1, l0-06.2) — conformité PID-FLOW et cohérence avec les CLI.

Deux angles morts, deux familles de tests.

**1. `cwltool --validate` (recette `just cwl`) ne connaît RIEN de nos CLI** : un fichier
CWL syntaxiquement valide qui référence une option renommée passera la validation sans
broncher, et le workflow cassera silencieusement à l'exécution (décision d'ancrage n°3 de
l0-06.1). Chaque `.cwl` est donc chargé en YAML brut (`yaml.safe_load` — un `.cwl` EST un
YAML) et chaque `inputBinding.prefix` est confronté aux options réellement exposées par le
CLI `typer`/`click` correspondant (via `typer.main.get_command`, jamais via un parsing de
`--help`).

**2. `cwltool` est plus permissif que PID-FLOW** : la structure de dépôt, les exigences
CWL admises et l'évaluation des expressions diffèrent, et `just cwl` reste VERT sur un
fichier que PID-FLOW refusera au register ou exécutera de travers. Les tests
`..._pid_flow` codifient les conventions relevées dans `cwl-assets` (cf.
assets/cwl/README.md), que rien d'autre ne vérifie ici.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer.main
import yaml

from tiny_wae.__main__ import app

CWL_ROOT = Path(__file__).resolve().parent.parent / "assets" / "cwl"

# Version unique de tous les artefacts (répertoire `<nom>/<version>/`).
CWL_VERSION = "1.0"

# {nom d'artefact PID-FLOW: chemin du .cwl}. Le nom est celui du RÉPERTOIRE, c'est-à-dire
# l'identité de l'artefact côté cwl-store — pas le nom de fichier, qui vaut toujours
# `tool.cwl` ou `workflow.cwl`.
_TOOLS = {
    name: CWL_ROOT / "tools" / name / CWL_VERSION / "tool.cwl"
    for name in ("search", "ingest", "update")
}
_WORKFLOWS = {"tiny-wae": CWL_ROOT / "workflows" / "tiny-wae" / CWL_VERSION / "workflow.cwl"}
_ALL_CWL = {**_TOOLS, **_WORKFLOWS}

# Exigences CWL que PID-FLOW ne supporte pas aujourd'hui (cf. assets/cwl/README.md). La
# liste est ici, pas dans les .cwl : un fichier ne peut pas documenter ce qu'il ne
# contient pas.
_FORBIDDEN_REQUIREMENTS = ("InlineJavascriptRequirement", "EnvVarRequirement")

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
    """Charge l'artefact `name` comme le YAML qu'il est (aucun parseur CWL dédié ici :
    on veut lire les champs bruts, pas les faire valider par cwltool)."""
    loaded = yaml.safe_load(_ALL_CWL[name].read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _declared_prefixes(cwl_doc: dict[str, Any]) -> dict[str, str]:
    """Extrait {nom d'input CWL: prefix déclaré} pour tous les inputs qui portent un
    `inputBinding.prefix` — un input qui n'en porte pas ne passe par aucune option CLI
    et n'a donc rien à confronter."""
    inputs = cwl_doc["inputs"]
    declared: dict[str, str] = {}
    for name, spec in inputs.items():
        if isinstance(spec, dict):
            binding = spec.get("inputBinding")
            if isinstance(binding, dict) and "prefix" in binding:
                declared[name] = binding["prefix"]
    return declared


# --------------------------------------------------------------------------------------
# Conformité PID-FLOW (structure de dépôt et conventions cwl-assets)
# --------------------------------------------------------------------------------------


def test_arborescence_pid_flow() -> None:
    """Chaque artefact est à `<workflows|tools>/<nom>/1.0/<workflow|tool>.cwl`, et il n'y
    a AUCUN autre `.cwl` sous `assets/cwl/`.

    PID-FLOW déduit la classe d'un artefact du préfixe de son chemin au scan : un fichier
    hors convention est silencieusement ignoré (log ERROR + skip), pas signalé."""
    for name, path in _ALL_CWL.items():
        assert path.is_file(), f"artefact {name!r} attendu à {path}"
    trouves = sorted(p.resolve() for p in CWL_ROOT.rglob("*.cwl"))
    attendus = sorted(p.resolve() for p in _ALL_CWL.values())
    assert trouves == attendus, (
        "des .cwl hors convention traînent sous assets/cwl/ — PID-FLOW les ignore au scan"
    )


def test_class_coherente_avec_le_repertoire() -> None:
    """`class: Workflow` sous `workflows/`, `class: CommandLineTool` sous `tools/`.

    Une discordance est REJETÉE au scan par PID-FLOW (garde-fou de cohérence côté
    server) : `cwltool --validate`, lui, ne voit rien à redire."""
    for name in _TOOLS:
        assert _load_cwl(name)["class"] == "CommandLineTool"
    for name in _WORKFLOWS:
        assert _load_cwl(name)["class"] == "Workflow"


def test_cwl_version_v1_2() -> None:
    """`cwlVersion: v1.2` — exigé par PID-FLOW sur tous les artefacts."""
    for name in _ALL_CWL:
        assert _load_cwl(name)["cwlVersion"] == "v1.2", f"{name}: cwlVersion doit être v1.2"


def test_label_egale_le_nom_de_l_artefact() -> None:
    """Le `label` porte le NOM de l'artefact, pas une phrase descriptive (convention
    cwl-assets) : c'est lui qui identifie la brique dans l'IHM PID-FLOW. La description
    va dans `doc`."""
    for name in _ALL_CWL:
        doc = _load_cwl(name)
        assert doc["label"] == name, f"{name}: label={doc['label']!r}, attendu {name!r}"
        assert doc.get("doc"), f"{name}: doc manquant (le label ne décrit plus rien)"


def test_chaque_tool_exige_la_capability_python() -> None:
    """Chaque tool déclare `SoftwareRequirement: python` en `hints`.

    C'est ce qui fait qu'un worker PID-FLOW prend la tâche : sans `python` dans ses
    WORKER_CAPABILITIES il ne la prend pas, et la tâche reste en attente sans erreur —
    panne muette, pas échec."""
    for name in _TOOLS:
        hints = _load_cwl(name).get("hints", [])
        packages = [
            package.get("package")
            for hint in hints
            if isinstance(hint, dict) and hint.get("class") == "SoftwareRequirement"
            for package in hint.get("packages", [])
        ]
        assert "python" in packages, f"{name}: capability `python` non déclarée en hints"


def test_aucune_expression_cwl_dans_les_fichiers() -> None:
    """⛔ Aucune expression `$(...)`, nulle part.

    PID-FLOW ne les évalue pas : un glob `$(inputs.x)` « ne matche rien » (constat porté
    par cwl-assets, tool AppendToFile), et la sortie est perdue SANS erreur. `cwltool`,
    lui, les résout parfaitement — d'où ce test, qui est le seul filet."""
    for name, path in _ALL_CWL.items():
        text = path.read_text(encoding="utf-8")
        for numero, ligne in enumerate(text.splitlines(), start=1):
            nu = ligne.strip()
            if nu.startswith("#"):  # les commentaires en PARLENT, ils n'en contiennent pas
                continue
            assert "$(" not in ligne, (
                f"{name}:{numero} contient une expression CWL — PID-FLOW ne l'évalue pas "
                f"(cf. assets/cwl/README.md) : {nu}"
            )


def test_search_glob_litteral_colle_au_default() -> None:
    """Le glob littéral de la sortie `acquisitions` est EXACTEMENT le défaut de l'input
    `json_out`. Les deux ne peuvent pas être liés par une expression (cf. test
    précédent) : ce test est ce qui les tient synchronisés."""
    doc = _load_cwl("search")
    defaut = doc["inputs"]["json_out"]["default"]
    glob = doc["outputs"]["acquisitions"]["outputBinding"]["glob"]
    assert glob == defaut, (
        f"glob={glob!r} et json_out.default={defaut!r} ont divergé — la sortie du tool "
        "`search` ne serait plus capturée, et le chaînage vers `ingest` casserait"
    )


def test_workflow_reference_des_tools_partages_existants() -> None:
    """Chaque `run:` du workflow pointe un tool PARTAGÉ (`../../../tools/<nom>/<version>/
    tool.cwl`) qui EXISTE réellement.

    Référencer le tool interne d'un AUTRE workflow est refusé au register PID-FLOW ; un
    chemin relatif faux, lui, casse à la résolution."""
    workflow_path = _ALL_CWL["tiny-wae"]
    for nom_step, step in _load_cwl("tiny-wae")["steps"].items():
        cible = step["run"]
        assert cible.startswith("../../../tools/"), (
            f"step {nom_step!r}: `run: {cible}` n'est pas une référence de tool partagé"
        )
        assert cible.endswith(f"/{CWL_VERSION}/tool.cwl"), (
            f"step {nom_step!r}: `run: {cible}` — version attendue {CWL_VERSION}"
        )
        assert (workflow_path.parent / cible).resolve().is_file(), (
            f"step {nom_step!r}: `run: {cible}` ne résout vers aucun fichier"
        )


def _declares_requirement(node: Any, requirement_class: str) -> bool:
    """Vrai si `node` déclare `requirement_class`, sous l'une OU l'autre des deux formes
    admises par CWL : clé d'une map de `requirements`/`hints`, ou entrée
    `{class: <requirement_class>}` d'une liste. Récursif : un `requirements` niché dans
    un step de workflow compte aussi."""
    if isinstance(node, dict):
        if requirement_class in node:
            return True
        if node.get("class") == requirement_class:
            return True
        return any(_declares_requirement(value, requirement_class) for value in node.values())
    if isinstance(node, list):
        return any(_declares_requirement(item, requirement_class) for item in node)
    return False


def test_aucun_cwl_ne_declare_d_exigence_non_supportee_par_pid_flow() -> None:
    """⛔ Ni `InlineJavascriptRequirement` ni `EnvVarRequirement` — PID-FLOW ne les
    supporte pas aujourd'hui.

    `cwltool --validate` (`just cwl`) reste VERT si on les rajoute : l'exécuteur de
    développement est plus permissif que celui de production, et c'est exactement
    l'angle mort que ce test comble. Aucune des deux ne nous manque — nous n'utilisons
    aucune expression CWL, et `TINY_WAE_DATA_ROOT` est posée dans l'environnement du
    worker (cf. assets/cwl/README.md).
    """
    for name in _ALL_CWL:
        doc = _load_cwl(name)
        for requirement_class in _FORBIDDEN_REQUIREMENTS:
            assert not _declares_requirement(doc, requirement_class), (
                f"{name} déclare {requirement_class} — non supporté par PID-FLOW "
                "(cf. assets/cwl/README.md)"
            )


def test_aucun_cwl_ne_declare_d_input_data_root() -> None:
    """`data_root` n'est plus un input CWL : la racine de stockage vient de
    TINY_WAE_DATA_ROOT, posée dans l'environnement du worker (cf. assets/cwl/README.md).
    Le ré-exposer en input impliquerait de la reposer via EnvVarRequirement, que
    PID-FLOW ne supporte pas."""
    for name in _ALL_CWL:
        inputs = _load_cwl(name).get("inputs", {})
        assert "data_root" not in inputs, (
            f"{name} déclare un input `data_root` — la racine vient de "
            "TINY_WAE_DATA_ROOT posée par le worker (cf. assets/cwl/README.md)"
        )


# --------------------------------------------------------------------------------------
# Cohérence avec les CLI réels (angle mort de `cwltool --validate`)
# --------------------------------------------------------------------------------------


def test_base_commands() -> None:
    """Chaque tool appelle bien `python -m tiny_wae <sous-commande>`, où la sous-commande
    est le NOM de l'artefact (décision d'ancrage n°1 de l0-06.1)."""
    for name in _TOOLS:
        assert _load_cwl(name)["baseCommand"] == ["python", "-m", "tiny_wae", name]


def test_prefixes_match_real_cli_options() -> None:
    """Oracle O3 (remplacé) : chaque prefix déclaré par un tool est une option RÉELLE de
    la sous-commande correspondante. Casse si une option de `cli/<cmd>.py` est renommée
    sans mettre à jour le tool."""
    for name in _TOOLS:
        declared = _declared_prefixes(_load_cwl(name))
        assert declared, f"{name}: aucun inputBinding.prefix déclaré"
        real_options = _cli_option_prefixes(name)
        for cwl_input_name, prefix in declared.items():
            assert prefix in real_options, (
                f"{name}: input {cwl_input_name!r} déclare le prefix {prefix!r}, absent "
                f"des options réelles de `{name}` ({sorted(real_options)})"
            )


def test_ingest_expose_toujours_acquisitions() -> None:
    """`--acquisitions` est le point de chaînage du workflow : le CLI `ingest` doit
    toujours l'exposer, sinon `search_step -> ingest_step` n'a plus de fil."""
    assert "--acquisitions" in _cli_option_prefixes("ingest")


def test_workflow_chaine_la_sortie_de_search_dans_ingest() -> None:
    """Le workflow chaîne bien la sortie `acquisitions` du step search vers l'entrée
    `acquisitions` du step ingest (le fil du chaînage, décision d'ancrage n°4)."""
    steps = _load_cwl("tiny-wae")["steps"]
    assert steps["ingest_step"]["in"]["acquisitions"] == "search_step/acquisitions"


def test_workflow_output_sources_pointent_vers_des_steps_declares() -> None:
    """Les outputSource du workflow référencent des steps/sorties qui existent
    réellement (pas un copier-coller périmé après renommage d'un step)."""
    doc = _load_cwl("tiny-wae")
    steps = doc["steps"]
    for _out_name, out_spec in doc["outputs"].items():
        source = out_spec["outputSource"]
        step_name, step_output = source.split("/", 1)
        assert step_name in steps, f"step {step_name!r} inconnu (outputSource {source!r})"
        assert step_output in steps[step_name]["out"], (
            f"{source!r} référence une sortie absente de steps[{step_name!r}]['out']"
        )
