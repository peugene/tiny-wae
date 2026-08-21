"""cli/sites_list.py — wiring pur : liste les sites chargés (l0-01.1), texte ou `--json`.

Même mapping d'erreurs que `sites_validate` (les deux CLIs partagent le même chargement).
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from tiny_wae.adapters.config_io import DEFAULT_SITES_PATH, ConfigError, load_sites
from tiny_wae.cli import exit_codes
from tiny_wae.core.sites import Site, SiteValidationError


def register(app: typer.Typer) -> None:
    """Enregistre la commande `sites-list` sur `app` (convention d'auto-découverte)."""
    app.command(name="sites-list")(sites_list)


def _site_to_dict(site: Site) -> dict[str, object]:
    """Représentation JSON-sérialisable d'un site, pour la sortie `--json`."""
    return {
        "id": site.id,
        "name": site.name,
        "lat": site.lat,
        "lon": site.lon,
        "category": site.category,
    }


def sites_list(
    path: Path = typer.Option(  # noqa: B008 — idiome typer standard (Option en défaut).
        DEFAULT_SITES_PATH, "--path", help="Chemin vers sites.yaml."
    ),
    as_json: bool = typer.Option(False, "--json", help="Sortie JSON plutôt que texte."),  # noqa: B008
) -> None:
    """Liste les sites (STDOUT, texte ou JSON) ; erreurs sur STDERR, exit USAGE."""
    try:
        sites = load_sites(path)
    except (ConfigError, SiteValidationError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=exit_codes.USAGE) from exc

    if as_json:
        typer.echo(json.dumps([_site_to_dict(s) for s in sites], ensure_ascii=False))
    else:
        for site in sites:
            typer.echo(f"{site.id}\t{site.category}\t{site.name}")

    raise typer.Exit(code=exit_codes.OK)
