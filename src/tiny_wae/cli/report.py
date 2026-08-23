"""cli/report.py — wiring pur : commande `report` (agrégats + critère de complétude, l0-04.2).

⛔ Aucune logique métier ici (règle de couche) : l'agrégation, les invariants, le rendu
Markdown vivent dans ``core/report.py`` (PUR). Ce module charge la config, lit les
manifestes/runs via l'API ``adapters.manifests`` (le SEUL point d'accès aux JSON du
domaine, cf. sa docstring), appelle ``core/report.py``, écrit le fichier ou STDERR.

Deux modes, mutuellement exclusifs :
- par défaut : rapport Markdown sur tous les sites de ``sites.yaml``, écrit à ``--out``.
- ``--check-completeness --sites A01,C07,…`` : contrôle réseau (arbitrage n°2 de la
  fiche) — comparaison d'ENSEMBLES d'ids, tolérance 0, hors ``just check`` (fait un vrai
  ``/search``). ``build_source`` est le point de couture monkeypatché par les tests
  (même convention que ``cli/search.py``, décision n°1 de son ancrage) : aucun réseau
  n'est jamais ouvert par un test.
"""

from __future__ import annotations

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
from tiny_wae.adapters.manifests import (
    aggregate_counters,
    grid_hash,
    item_ids_for_site,
    list_for_site,
)
from tiny_wae.adapters.stac import EarthSearchSource, StacSource, StacSourceError, StacUnreachable
from tiny_wae.cli import exit_codes
from tiny_wae.core.report import (
    CompletenessResult,
    SiteReport,
    build_site_report,
    check_completeness,
    render_report,
)
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Site, SiteValidationError
from tiny_wae.core.windows import Window

DEFAULT_OUT_PATH = Path("report.md")


def register(app: typer.Typer) -> None:
    """Enregistre la commande `report` sur `app` (convention d'auto-découverte)."""
    app.command(name="report")(report)


def build_source(settings: Settings) -> StacSource:
    """Construit la source STAC réelle — point de couture monkeypatché par les tests
    (même convention que ``cli/search.py``)."""
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


def _run_completeness_check(
    site_ids: list[str],
    *,
    sites: list[Site],
    data_root: Path,
    window: Window,
    source: StacSource,
) -> list[CompletenessResult]:
    """Pour chaque site demandé : interroge la source (qui applique déjà les TROIS filtres
    du pipeline — bbox, tuile, ``eo:cloud_cover`` — cf. ``adapters.stac.build_envelope``)
    et compare l'ensemble d'ids obtenu à ``item_ids_for_site`` (arbitrage n°2, tolérance 0).
    """
    results: list[CompletenessResult] = []
    for site_id in site_ids:
        site = _find_site(sites, site_id)
        envelope = source.search(site, window)
        source_ids = {acquisition.item_id for acquisition in envelope.items}
        manifest_ids = item_ids_for_site(data_root, site_id)
        results.append(check_completeness(site_id, manifest_ids, source_ids))
    return results


def _build_site_reports(sites: list[Site], settings: Settings, data_root: Path) -> list[SiteReport]:
    """Construit un ``SiteReport`` (cf. ``core/report.py``) par site de ``sites.yaml``, à
    partir des manifestes/compteurs lus via l'API ``adapters.manifests``."""
    reports: list[SiteReport] = []
    for site in sites:
        manifests = list_for_site(data_root, site.id)
        counters = aggregate_counters(data_root, site.id)
        try:
            current_hash = grid_hash(site.grid, settings)
        except ValueError:
            # Grille pas encore posée (l0-01.3) : aucun manifeste ne peut alors être
            # 'ingested' pour ce site (write_manifest exigerait un grid_hash calculable)
            # — l'intégrité n'a rien à vérifier, valeur qui ne matchera jamais rien.
            current_hash = ""
        reports.append(
            build_site_report(
                site.id,
                counters,
                manifests,
                current_grid_hash=current_hash,
                chip_nodata_pct_max=settings.chip_nodata_pct_max,
            )
        )
    return reports


def report(
    out: Path = typer.Option(  # noqa: B008
        DEFAULT_OUT_PATH, "--out", help="Chemin du rapport Markdown produit."
    ),
    check_completeness_flag: bool = typer.Option(
        False,
        "--check-completeness",
        help="Contrôle de complétude réseau (arbitrage n°2) au lieu du rapport agrégé.",
    ),
    sites_arg: str | None = typer.Option(
        None,
        "--sites",
        help="Ids de sites séparés par des virgules (requis avec --check-completeness).",
    ),
    date_from: str | None = typer.Option(
        None, "--from", help="Début de fenêtre YYYY-MM-DD (requis avec --check-completeness)."
    ),
    date_to: str | None = typer.Option(
        None, "--to", help="Fin de fenêtre YYYY-MM-DD (requis avec --check-completeness)."
    ),
    sites_path: Path = typer.Option(  # noqa: B008
        DEFAULT_SITES_PATH, "--sites-path", help="Chemin vers sites.yaml."
    ),
    settings_path: Path = typer.Option(  # noqa: B008
        DEFAULT_SETTINGS_PATH, "--settings-path", help="Chemin vers settings.yaml."
    ),
) -> None:
    """Sans ``--check-completeness`` : rapport Markdown agrégé (tous les sites de
    ``sites.yaml``) à ``--out``. Avec ``--check-completeness --sites A01,C07,…`` : contrôle
    de complétude réseau, ids manquants/en trop nommés sur STDERR, tolérance 0."""
    try:
        settings = load_settings(settings_path)
        sites = load_sites(sites_path)
    except (ConfigError, SiteValidationError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=exit_codes.USAGE) from exc

    data_root = Path(settings.data_root)

    if check_completeness_flag:
        if not sites_arg or not date_from or not date_to:
            typer.echo("usage : --check-completeness requiert --sites, --from et --to", err=True)
            raise typer.Exit(code=exit_codes.USAGE)
        try:
            site_ids = [s.strip() for s in sites_arg.split(",") if s.strip()]
            window = Window(start=_parse_date("from", date_from), end=_parse_date("to", date_to))
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=exit_codes.USAGE) from exc

        source = build_source(settings)
        try:
            results = _run_completeness_check(
                site_ids, sites=sites, data_root=data_root, window=window, source=source
            )
        except StacUnreachable as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=exit_codes.INCONCLUSIVE) from exc
        except (StacSourceError, ValueError) as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=exit_codes.FAILURE) from exc

        all_ok = True
        for result in results:
            if result.ok:
                typer.echo(f"site={result.site_id}  complétude=OK (0 écart)", err=True)
            else:
                all_ok = False
                typer.echo(
                    f"site={result.site_id}  complétude=ROUGE  "
                    f"manquants={sorted(result.missing)}  en_trop={sorted(result.extra)}",
                    err=True,
                )
        raise typer.Exit(code=exit_codes.OK if all_ok else exit_codes.FAILURE)

    site_reports = _build_site_reports(sites, settings, data_root)
    markdown = render_report(site_reports)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
    typer.echo(f"rapport écrit : {out} ({len(site_reports)} sites)", err=True)
    raise typer.Exit(code=exit_codes.OK)
