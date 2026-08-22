"""cli/sites_validate.py — wiring pur : valide `config/sites.yaml` (chargement de l0-01.1).

Zéro logique ici : `load_sites` fait le chargement YAML + validation (elle appelle déjà
`core.sites.validate_sites`). Ce module se contente de mapper les deux exceptions possibles
(`ConfigError` du chargement, `SiteValidationError` de la validation) sur le code de sortie
`USAGE` et d'écrire le message d'erreur sur STDERR.
"""

from __future__ import annotations

from pathlib import Path

import typer

from tiny_wae.adapters.config_io import DEFAULT_SITES_PATH, ConfigError, load_sites
from tiny_wae.cli import exit_codes
from tiny_wae.core.sites import SiteValidationError


def register(app: typer.Typer) -> None:
    """Enregistre la commande `sites-validate` sur `app` (convention d'auto-découverte)."""
    app.command(name="sites-validate")(sites_validate)


def sites_validate(
    path: Path = typer.Option(  # noqa: B008 — idiome typer standard (Option en défaut).
        DEFAULT_SITES_PATH, "--path", help="Chemin vers sites.yaml."
    ),
) -> None:
    """Charge et valide les sites ; exit OK si valides, USAGE (message sur STDERR) sinon."""
    try:
        sites = load_sites(path)
    except (ConfigError, SiteValidationError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=exit_codes.USAGE) from exc

    typer.echo(f"{len(sites)} site(s) valide(s)", err=True)
    raise typer.Exit(code=exit_codes.OK)
