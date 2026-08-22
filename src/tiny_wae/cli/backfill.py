"""cli/backfill.py — wiring pur : historique 48 mois sites × fenêtres (l0-04.1).

⛔ Aucune logique métier ici (règle de couche) : la boucle sites × fenêtres, le pool de
workers et l'isolation par site vivent dans ``adapters/backfill.py`` (décision d'ancrage
n°1 de la fiche) — ce module parse les options, charge la config, appelle l'orchestrateur,
écrit les compteurs sur STDERR et mappe le résultat sur un code de sortie.

``build_source`` est SON PROPRE point de couture (même règle que ``cli/ingest.py``,
décision d'ancrage n°4 de l0-03.4) : ne pas le partager avec un autre CLI.

Accusé de réception et interruption immédiate (obs-02) : la POLITIQUE du Ctrl+C vit ici,
pas dans ``adapters/`` (D1) — ``_on_stop_requested`` est le callback câblé sur
``run_backfill(on_stop_requested=...)``, appelé SYNCHRONEMENT par le gestionnaire de
signal pur. Premier appel (``already_requested`` faux) : accusé de réception immédiat
(D2). Second appel (déjà demandé) : message D4 puis ``os._exit(130)`` IMMÉDIAT (D3) — une
exception ne suffirait pas ici, le thread principal est bloqué dans ``as_completed``, à
l'intérieur d'un ``with ThreadPoolExecutor(...)`` dont ``__exit__`` appelle
``shutdown(wait=True)`` et attendrait la fin de tous les workers (ancrage de la fiche).
Les deux messages s'écrivent par ``os.write(2, ...)``, PAS par ``logging`` ni
``typer.echo`` (D5) : un gestionnaire de signal s'exécute entre deux bytecodes du thread
principal, et passer par le verrou de handler de ``logging`` exposerait à un interblocage
si le signal frappe pendant que ce même thread le détient déjà.
"""

from __future__ import annotations

import contextlib
import os
import sys
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

# Messages du gestionnaire de Ctrl+C (obs-02, D2/D4/D7) — AUCUN emoji, le mot porte
# l'information mieux qu'un pictogramme pour un opérateur qui lit dans l'urgence. Le saut
# de ligne initial sépare visuellement le message d'une ligne de progression en cours
# d'écriture par un AUTRE thread au même instant (`logging` sérialise ses propres lignes,
# mais pas contre cette écriture directe sur le descripteur).
_FIRST_INTERRUPT_MESSAGE = (
    "\nbackfill : interruption demandée (Ctrl+C) : les fenêtres en cours vont à leur "
    "terme, aucune nouvelle n'est lancée ; un second Ctrl+C interrompt immédiatement.\n"
)
_SECOND_INTERRUPT_MESSAGE = (
    "\nbackfill : arrêt immédiat (2e Ctrl+C) : des fichiers partiels sans manifeste "
    "peuvent subsister, ils seront réingérés au prochain run.\n"
)


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


def _emit_signal_message(message: str) -> None:
    """Écrit ``message`` DIRECTEMENT sur le descripteur STDERR (fd 2), en contournant le
    buffer Python de ``sys.stderr`` et le logger (D5). Sûr en contexte de gestionnaire de
    signal : ``os.write`` ne prend aucun verrou Python. ``sys.stderr.flush()`` d'abord,
    pour que tout ce qui a DÉJÀ été écrit via `logging`/`typer.echo` (canal figé par
    obs-01, lui aussi STDERR) apparaisse AVANT ce message plutôt que de rester coincé dans
    un buffer d'écriture Python encore en attente."""
    with contextlib.suppress(OSError):  # flux déjà fermé : best-effort, pas fatal ici.
        sys.stderr.flush()
    os.write(2, message.encode("utf-8"))


def _on_stop_requested(already_requested: bool) -> None:
    """Politique du Ctrl+C (obs-02, D2/D3/D4) — callback câblé sur
    ``run_backfill(on_stop_requested=...)``, appelé SYNCHRONEMENT par le gestionnaire de
    signal pur d'``adapters/backfill.py``. Premier Ctrl+C (``already_requested`` faux) :
    accusé de réception, puis retour normal (l'arrêt propre existant, l0-04.1, continue de
    jouer). Second Ctrl+C (``already_requested`` vrai) : message D4 puis sortie IMMÉDIATE
    ``os._exit(130)`` — ``130 = 128 + SIGINT``, convention shell. ``os._exit`` et non une
    exception : le thread principal est bloqué dans ``as_completed``, à l'intérieur d'un
    ``with ThreadPoolExecutor(...)`` dont ``__exit__`` fait ``shutdown(wait=True)`` ;
    lever depuis le handler attendrait la fin de tous les workers, exactement ce que
    l'opérateur cherche à éviter en tapant un second Ctrl+C."""
    if not already_requested:
        _emit_signal_message(_FIRST_INTERRUPT_MESSAGE)
        return
    _emit_signal_message(_SECOND_INTERRUPT_MESSAGE)
    os._exit(130)


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
        on_stop_requested=_on_stop_requested,
    )

    _report_counters(outcome)

    if outcome.interrupted or outcome.failed_site_ids:
        if outcome.all_failures_network:
            raise typer.Exit(code=exit_codes.INCONCLUSIVE)
        raise typer.Exit(code=exit_codes.FAILURE)
    raise typer.Exit(code=exit_codes.OK)
