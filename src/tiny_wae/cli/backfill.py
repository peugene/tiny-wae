"""cli/backfill.py — wiring pur : historique 48 mois sites × fenêtres (l0-04.1).

⛔ Aucune logique métier ici (règle de couche) : la boucle sites × fenêtres, le pool de
workers et l'isolation par site vivent dans ``adapters/backfill.py`` (décision d'ancrage
n°1 de la fiche) — ce module parse les options, charge la config, appelle l'orchestrateur,
écrit les compteurs sur STDERR et mappe le résultat sur un code de sortie.

``build_source`` est SON PROPRE point de couture (même règle que ``cli/ingest.py``,
décision d'ancrage n°4 de l0-03.4) : ne pas le partager avec un autre CLI.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import typer

from tiny_wae.adapters.backfill import BackfillOutcome, build_tasks, run_backfill
from tiny_wae.adapters.config_io import (
    DEFAULT_SETTINGS_PATH,
    DEFAULT_SITES_PATH,
    ConfigError,
    load_settings,
    load_sites,
)
from tiny_wae.adapters.stac import EarthSearchSource, StacSource
from tiny_wae.cli import exit_codes
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Site, SiteValidationError
from tiny_wae.core.statuses import RUN_STATUSES
from tiny_wae.core.windows import Window, backfill_windows


def register(app: typer.Typer) -> None:
    """Enregistre la commande `backfill` sur `app` (convention d'auto-découverte)."""
    app.command(name="backfill")(backfill)


def build_source(settings: Settings) -> StacSource:
    """Construit la source STAC réelle — point de couture monkeypatché par les tests
    (propre à ce module, jamais partagé avec un autre CLI)."""
    return EarthSearchSource(settings)


def _parse_date(label: str, raw: str) -> datetime:
    """Parse une date ``YYYY-MM-DD`` en ``datetime`` naïf ; lève ``ValueError`` sinon."""
    try:
        return datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"--{label} {raw!r} : date attendue au format YYYY-MM-DD") from exc


def _select_sites(sites: list[Site], raw: str) -> list[Site]:
    """Résout ``--sites all|A01,B02`` en liste de ``Site`` — lève ``ValueError`` si un id
    demandé est inconnu (usage invalide, AVANT toute soumission au pool)."""
    if raw == "all":
        return list(sites)
    by_id = {site.id: site for site in sites}
    requested = [chunk.strip() for chunk in raw.split(",") if chunk.strip()]
    if not requested:
        raise ValueError("--sites : liste vide")
    unknown = [site_id for site_id in requested if site_id not in by_id]
    if unknown:
        raise ValueError(f"--sites : id(s) inconnu(s) {unknown} (cf. sites.yaml)")
    return [by_id[site_id] for site_id in requested]


def _report_counters(outcome: BackfillOutcome) -> None:
    """Écrit sur STDERR un résumé par site : compteurs agrégés (somme des fenêtres
    traitées) puis, pour un site en échec, ses fenêtres fautives nommées."""
    for result in outcome.site_results:
        totals: dict[str, int] = dict.fromkeys(RUN_STATUSES, 0)
        for status in ("found_stac", "skipped_scene_cloud", "off_tile", "found_tile"):
            totals[status] = 0
        for run_outcome in result.outcomes:
            for key, value in run_outcome.run.counters.items():
                totals[key] = totals.get(key, 0) + value
        typer.echo(
            f"site={result.site_id}  fenêtres_ok={len(result.outcomes)}  "
            f"fenêtres_échouées={len(result.failures)}  compteurs={totals}",
            err=True,
        )
        for failure in result.failures:
            typer.echo(
                f"site={result.site_id} fenêtre=[{failure.window.start}, "
                f"{failure.window.end}[ : {failure.error}",
                err=True,
            )
    if outcome.interrupted:
        typer.echo("backfill interrompu (SIGINT) : soumissions arrêtées", err=True)
    if outcome.failed_site_ids:
        typer.echo(f"site(s) en échec : {outcome.failed_site_ids}", err=True)


def backfill(
    sites_arg: str = typer.Option(
        "all", "--sites", help="'all' ou liste d'ids séparés par des virgules (ex. A01,B02)."
    ),
    months: int = typer.Option(48, "--months", help="Nombre de mois à couvrir, du plus récent."),
    workers: int | None = typer.Option(
        None, "--workers", help="Taille du pool (défaut : settings.backfill_workers)."
    ),
    now: str | None = typer.Option(
        None,
        "--now",
        help="Date de référence YYYY-MM-DD (défaut : date du jour). Passée LITTÉRALEMENT "
        "aux fenêtres — jamais recalculée en aval.",
    ),
    force: bool = typer.Option(
        False, "--force", help="Ré-ingestion inconditionnelle (ignore l'idempotence grid_hash)."
    ),
    sites_path: Path = typer.Option(  # noqa: B008
        DEFAULT_SITES_PATH, "--sites-path", help="Chemin vers sites.yaml."
    ),
    settings_path: Path = typer.Option(  # noqa: B008
        DEFAULT_SETTINGS_PATH, "--settings-path", help="Chemin vers settings.yaml."
    ),
) -> None:
    """Backfill : ingère les sites demandés sur ``--months`` mois glissants avant ``--now``,
    en pool de ``--workers`` (défaut ``settings.backfill_workers``). Un site = une unité
    d'isolation (l'échec d'un site n'arrête pas les autres). Codes de sortie : OK=0,
    FAILURE=1 (au moins un site en échec, ou run interrompu par SIGINT), USAGE=2
    (config/usage invalide), INCONCLUSIVE=3 (amont injoignable sur TOUS les sites)."""
    try:
        settings = load_settings(settings_path)
        sites = load_sites(sites_path)
        selected_sites = _select_sites(sites, sites_arg)
        reference_now = (
            _parse_date("now", now) if now is not None else datetime.now(UTC).replace(tzinfo=None)
        )
        windows: list[Window] = backfill_windows(months, reference_now)
    except (ConfigError, SiteValidationError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=exit_codes.USAGE) from exc

    source = build_source(settings)
    outcome = run_backfill(
        sites=selected_sites,
        windows_by_site=build_tasks(selected_sites, windows),
        source=source,
        settings=settings,
        data_root=Path(settings.data_root),
        workers=workers if workers is not None else settings.backfill_workers,
        force=force,
    )

    _report_counters(outcome)

    if outcome.interrupted or outcome.failed_site_ids:
        if outcome.all_failures_network:
            raise typer.Exit(code=exit_codes.INCONCLUSIVE)
        raise typer.Exit(code=exit_codes.FAILURE)
    raise typer.Exit(code=exit_codes.OK)
