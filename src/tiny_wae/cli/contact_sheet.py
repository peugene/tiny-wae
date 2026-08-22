"""cli/contact_sheet.py — wiring pur : planche de contrôle RGB (l0-03.6).

⛔ Aucune logique métier ici (règle de couche) : le rendu et la composition vivent dans
``adapters/contact_sheet.py`` (décision d'ancrage n°2) — ce module ne fait que parser les
options, charger la config, appeler l'adaptateur et mapper les exceptions sur les codes de
sortie.

``--latest`` est actuellement le SEUL mode supporté (booléen requis, cf. fiche) : le mode
``--first-last`` viendra en l0-04.2, sur le même module.
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
from tiny_wae.adapters.contact_sheet import write_contact_sheet
from tiny_wae.cli import exit_codes
from tiny_wae.core.sites import SiteValidationError

DEFAULT_OUT_PATH = Path("contact-sheet.png")


def register(app: typer.Typer) -> None:
    """Enregistre la commande `contact-sheet` sur `app` (convention d'auto-découverte)."""
    app.command(name="contact-sheet")(contact_sheet)


def contact_sheet(
    latest: bool = typer.Option(  # noqa: B008 — idiome typer standard.
        False, "--latest", help="Un chip récent par site (seul mode supporté à ce jour)."
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
    """Compose la planche de contrôle : pour chaque site de ``sites.yaml``, le dernier chip
    ``ingested`` disponible sous ``settings.data_root`` (via les manifestes), rendu RGB,
    grille labellisée (id + nom + date). Site sans chip -> case grise « aucun chip ».
    ``--latest`` requis (seul mode à ce jour ; ``--first-last`` viendra en l0-04.2)."""
    if not latest:
        typer.echo("usage : --latest requis (seul mode supporté à ce jour)", err=True)
        raise typer.Exit(code=exit_codes.USAGE)

    try:
        settings = load_settings(settings_path)
        sites = load_sites(sites_path)
    except (ConfigError, SiteValidationError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=exit_codes.USAGE) from exc

    write_contact_sheet(sites, Path(settings.data_root), out)
    typer.echo(f"planche écrite : {out} ({len(sites)} sites)", err=True)
    raise typer.Exit(code=exit_codes.OK)
