"""cli/search.py — wiring pur : recherche STAC pour un site sur une fenêtre (l0-02.2).

Discipline des flux (décision n°3 de l'ancrage de la fiche) : l'enveloppe JSON part sur
STDOUT (``json.dumps(envelope.to_dict())``) OU dans le fichier ``--json <path>`` — dans ce
second cas STDOUT reste vide. La table lisible et toute erreur partent sur STDERR. Rien
d'autre ne s'écrit jamais sur STDOUT.

``build_source`` est le point de couture pour l'injection de fixtures en test (décision
n°1 de l'ancrage) : les tests monkeypatchent ``tiny_wae.cli.search.build_source`` — aucun
``FixtureSource`` ne vit dans ``src/`` (le double de test vit dans ``tests/``).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import typer

from tiny_wae.adapters.config_io import (
    DEFAULT_SETTINGS_PATH,
    DEFAULT_SITES_PATH,
    ConfigError,
    load_settings,
    load_sites,
)
from tiny_wae.adapters.stac import EarthSearchSource, StacSource, StacSourceError, StacUnreachable
from tiny_wae.cli import exit_codes
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Site, SiteValidationError
from tiny_wae.core.windows import Window


def register(app: typer.Typer) -> None:
    """Enregistre la commande `search` sur `app` (convention d'auto-découverte)."""
    app.command(name="search")(search)


def build_source(settings: Settings) -> StacSource:
    """Construit la source STAC réelle — point de couture monkeypatché par les tests."""
    return EarthSearchSource(settings)


def _find_site(sites: list[Site], site_id: str) -> Site:
    """Cherche un site par id dans la liste chargée — lève ``ValueError`` si absent."""
    for site in sites:
        if site.id == site_id:
            return site
    raise ValueError(f"site {site_id!r} inconnu (cf. sites.yaml)")


def _parse_date(label: str, raw: str) -> datetime:
    """Parse une date ``YYYY-MM-DD`` en ``datetime`` naïf ; lève ``ValueError`` sinon."""
    try:
        return datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"--{label} {raw!r} : date attendue au format YYYY-MM-DD") from exc


def search(
    site_id: str = typer.Option(..., "--site", help="Id du site (sites.yaml)."),
    date_from: str = typer.Option(..., "--from", help="Début de fenêtre, YYYY-MM-DD."),
    date_to: str = typer.Option(..., "--to", help="Fin de fenêtre, YYYY-MM-DD."),
    json_path: Path | None = typer.Option(  # noqa: B008 — idiome typer standard.
        None, "--json", help="Écrit l'enveloppe JSON dans ce fichier plutôt que sur STDOUT."
    ),
    sites_path: Path = typer.Option(  # noqa: B008
        DEFAULT_SITES_PATH, "--sites-path", help="Chemin vers sites.yaml."
    ),
    settings_path: Path = typer.Option(  # noqa: B008
        DEFAULT_SETTINGS_PATH, "--settings-path", help="Chemin vers settings.yaml."
    ),
) -> None:
    """Recherche les items S2 L2A d'un site sur une fenêtre — table sur STDERR, enveloppe
    JSON sur STDOUT ou dans ``--json``. Endpoint injoignable -> exit INCONCLUSIVE (3),
    jamais confondu avec un échec métier (exit FAILURE, 1) ou un usage invalide (exit
    USAGE, 2)."""
    try:
        settings = load_settings(settings_path)
        sites = load_sites(sites_path)
        site = _find_site(sites, site_id)
        window = Window(start=_parse_date("from", date_from), end=_parse_date("to", date_to))
    except (ConfigError, SiteValidationError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=exit_codes.USAGE) from exc

    source = build_source(settings)
    try:
        envelope = source.search(site, window)
    except StacUnreachable as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=exit_codes.INCONCLUSIVE) from exc
    except StacSourceError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=exit_codes.FAILURE) from exc

    counters = envelope.counters
    typer.echo(
        f"site={site.id}  found_stac={counters['found_stac']}  "
        f"skipped_scene_cloud={counters['skipped_scene_cloud']}  "
        f"off_tile={counters['off_tile']}  found_tile={counters['found_tile']}",
        err=True,
    )

    payload = json.dumps(envelope.to_dict(), ensure_ascii=False)
    if json_path is not None:
        json_path.write_text(payload, encoding="utf-8")
    else:
        typer.echo(payload)

    raise typer.Exit(code=exit_codes.OK)
