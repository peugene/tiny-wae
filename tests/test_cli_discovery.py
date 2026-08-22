"""Test discovery : auto-découverte des commandes CLI (l0-01.2).

Couvre O1 de la fiche : un module factice déposé dans un package `cli/` temporaire (jamais
dans `src/` installé) apparaît dans `--help` sans que `discover_commands` ait besoin de
connaître son existence à l'avance — donc sans toucher `__main__.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from typer.testing import CliRunner

from tiny_wae.cli.discovery import discover_commands

runner = CliRunner()

_FAKE_MODULE_SOURCE = '''
"""Module factice de test — expose register() comme la convention l'exige."""

import typer


def register(app: typer.Typer) -> None:
    """Enregistre la commande factice `fake-command` sur `app`."""

    @app.command(name="fake-command")
    def fake_command() -> None:
        """Commande factice, sans effet."""
        typer.echo("fake ok")
'''

_NOT_A_COMMAND_SOURCE = '''
"""Module factice SANS register() — doit être ignoré silencieusement par la découverte."""

VALUE = 42
'''


def test_discover_commands_finds_module_without_touching_main(tmp_path: Path) -> None:
    """O1 : un module `cli/` temporaire exposant `register` apparaît dans `--help`."""
    package_root = tmp_path / "fake_project"
    cli_dir = package_root / "fake_cli"
    cli_dir.mkdir(parents=True)
    (package_root / "__init__.py").write_text("", encoding="utf-8")
    (cli_dir / "__init__.py").write_text('"""Package cli factice de test."""\n', encoding="utf-8")
    (cli_dir / "fake_command_module.py").write_text(_FAKE_MODULE_SOURCE, encoding="utf-8")
    (cli_dir / "not_a_command_module.py").write_text(_NOT_A_COMMAND_SOURCE, encoding="utf-8")

    sys.path.insert(0, str(tmp_path))
    try:
        app = typer.Typer()

        @app.callback()
        def _fake_main() -> None:
            """Force le mode multi-commandes (même contrainte que l'app réelle)."""

        discover_commands(app, package_name="fake_project.fake_cli")

        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "fake-command" in result.output

        result_run = runner.invoke(app, ["fake-command"])
        assert result_run.exit_code == 0
        assert "fake ok" in result_run.output
    finally:
        sys.path.remove(str(tmp_path))
        for mod_name in list(sys.modules):
            if mod_name.startswith("fake_project"):
                del sys.modules[mod_name]


def test_main_module_has_no_per_command_wiring() -> None:
    """Non-régression (Définition de « terminé ») : `__main__.py` n'importe/ne référence
    aucun module de commande par son nom — l'ajout d'un module dans `cli/` ne doit jamais
    nécessiter de le modifier. Seul `discover_commands` y figure."""
    main_source = Path("src/tiny_wae/__main__.py").read_text(encoding="utf-8")
    assert "discover_commands" in main_source
    for forbidden in ("sites_validate", "sites_list", "cli.sites"):
        assert forbidden not in main_source


def test_discover_commands_ignores_module_without_register(tmp_path: Path) -> None:
    """Un module de `cli/` sans `register` est ignoré (pas d'erreur, pas de commande)."""
    package_root = tmp_path / "fake_project_2"
    cli_dir = package_root / "fake_cli"
    cli_dir.mkdir(parents=True)
    (package_root / "__init__.py").write_text("", encoding="utf-8")
    (cli_dir / "__init__.py").write_text("", encoding="utf-8")
    (cli_dir / "not_a_command_module.py").write_text(_NOT_A_COMMAND_SOURCE, encoding="utf-8")

    sys.path.insert(0, str(tmp_path))
    try:
        app = typer.Typer(no_args_is_help=True)

        @app.callback()
        def _fake_main() -> None:
            """Force le mode multi-commandes (même contrainte que l'app réelle)."""

        discover_commands(app, package_name="fake_project_2.fake_cli")
        # Aucune commande enregistrée : `--help` doit réussir sans planter.
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
    finally:
        sys.path.remove(str(tmp_path))
        for mod_name in list(sys.modules):
            if mod_name.startswith("fake_project_2"):
                del sys.modules[mod_name]
