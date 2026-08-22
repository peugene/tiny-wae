"""cli/contact_sheet.py — wiring pur : planche de contrôle RGB (l0-03.6 ; --first-last l0-04.2).

⛔ Aucune logique métier ici (règle de couche) : le rendu et la composition vivent dans
``adapters/contact_sheet.py`` (décision d'ancrage n°2) — ce module ne fait que parser les
options, charger la config, appeler l'adaptateur et mapper les exceptions sur les codes de
sortie.

Deux modes, mutuellement exclusifs et l'un des deux requis : ``--latest`` (un chip récent
par site) et ``--first-last`` (premier et dernier chip ``ingested`` par site, 2 imagettes
par case — l0-04.2, extension actée en l0-03.6).
"""

from __future__ import annotations

from pathlib import Path

import typer

from tiny_wae.adapters.config_io import (
    DEFAULT_SETTINGS_PATH,
    DEFAULT_SITES_PATH,
    ConfigError,
    load_settings,
    load_sites,
)
from tiny_wae.adapters.contact_sheet import write_contact_sheet, write_first_last_contact_sheet
from tiny_wae.cli import exit_codes
from tiny_wae.core.sites import SiteValidationError

DEFAULT_OUT_PATH = Path("contact-sheet.png")


def register(app: typer.Typer) -> None:
    """Enregistre la commande `contact-sheet` sur `app` (convention d'auto-découverte)."""
    app.command(name="contact-sheet")(contact_sheet)


def contact_sheet(
    latest: bool = typer.Option(  # noqa: B008 — idiome typer standard.
        False, "--latest", help="Un chip récent par site."
    ),
    first_last: bool = typer.Option(  # noqa: B008
        False, "--first-last", help="Premier ET dernier chip ingested par site (l0-04.2)."
    ),
    out: Path = typer.Option(  # noqa: B008
        DEFAULT_OUT_PATH, "--out", help="Chemin du PNG produit."
    ),
    sites_path: Path = typer.Option(  # noqa: B008
        DEFAULT_SITES_PATH, "--sites-path", help="Chemin vers sites.yaml."
    ),
    settings_path: Path = typer.Option(  # noqa: B008
        DEFAULT_SETTINGS_PATH, "--settings-path", help="Chemin vers settings.yaml."
    ),
) -> None:
    """Compose la planche de contrôle sous ``settings.data_root`` (via les manifestes) :
    ``--latest`` (une imagette/site, le dernier chip ``ingested``) ou ``--first-last``
    (deux imagettes/site, premier et dernier chip ``ingested``) — exactement l'un des deux
    requis. Site sans chip -> case(s) grise(s) « aucun chip »."""
    if latest == first_last:  # les deux faux (aucun choix) OU les deux vrais (ambigu)
        typer.echo("usage : exactement un de --latest ou --first-last requis", err=True)
        raise typer.Exit(code=exit_codes.USAGE)

    try:
        settings = load_settings(settings_path)
        sites = load_sites(sites_path)
    except (ConfigError, SiteValidationError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=exit_codes.USAGE) from exc

    data_root = Path(settings.data_root)
    if first_last:
        write_first_last_contact_sheet(sites, data_root, out)
    else:
        write_contact_sheet(sites, data_root, out)
    typer.echo(f"planche écrite : {out} ({len(sites)} sites)", err=True)
    raise typer.Exit(code=exit_codes.OK)
