"""cli/ingest.py — wiring pur : ingestion des chips pour un site (l0-03.4).

⛔ Aucune logique métier ici (règle de couche) : toute la boucle d'ingestion vit dans
``adapters/ingestion.py`` (décision d'ancrage n°1) — ce module parse les options, charge
la config, appelle l'orchestrateur, écrit les compteurs sur STDERR et mappe les
exceptions sur les codes de sortie.

Deux formes d'appel, mutuellement exclusives :

- ``ingest --acquisitions <envelope.json>`` : chaînage CWL, l'enveloppe est déjà là.
- ``ingest --site A01 --from 2024-01-01 --to 2024-12-31`` : interroge la source STAC.

⚠ PAS d'option ``--now`` (décision E-d du chapeau l0-03) : les deux formes portent une
fenêtre explicite, l'option serait morte — ``--now`` vit sur ``backfill`` et ``update``.

``build_source`` est SON PROPRE point de couture (décision d'ancrage n°4) : ne pas
réutiliser celui de ``cli/search.py``, deux CLIs qui partagent un point de monkeypatch se
contaminent en test.
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
from tiny_wae.adapters.ingestion import IngestOutcome, ingest_from_envelope, ingest_from_source
from tiny_wae.adapters.manifests import RUN_STATUSES, Run
from tiny_wae.adapters.stac import EarthSearchSource, StacSource, StacUnreachable
from tiny_wae.cli import exit_codes
from tiny_wae.core.envelope import ConservationError, Envelope
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Site, SiteValidationError
from tiny_wae.core.windows import Window


def register(app: typer.Typer) -> None:
    """Enregistre la commande `ingest` sur `app` (convention d'auto-découverte)."""
    app.command(name="ingest")(ingest)


def build_source(settings: Settings) -> StacSource:
    """Construit la source STAC réelle — point de couture monkeypatché par les tests
    (décision d'ancrage n°4 : propre à ce module, jamais partagé avec `cli/search.py`)."""
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


def _require_grid_computed(site: Site) -> None:
    """Garde de config (décision d'ancrage n°5) : une grille non calculée n'est PAS un
    item en échec, c'est une erreur d'usage — exit USAGE (2) avant même d'entrer dans la
    boucle d'ingestion."""
    if site.grid.epsg is None:
        raise ValueError(
            f"site {site.id} : grille non calculée (grid.epsg absent de sites.yaml) — "
            "lancer `just survey-tiles` avant d'ingérer ce site"
        )


def _report_counters(site_id: str, run: Run) -> None:
    """Écrit les compteurs finaux sur STDERR — les 4 compteurs d'enveloppe puis les 6
    statuts, plus bytes et durée (cf. fiche : discipline des flux, rien d'autre sur
    STDOUT que ce que le CLI y écrit explicitement — ici tout part sur STDERR)."""
    c = run.counters
    typer.echo(
        f"site={site_id}  found_stac={c['found_stac']}  "
        f"skipped_scene_cloud={c['skipped_scene_cloud']}  off_tile={c['off_tile']}  "
        f"found_tile={c['found_tile']}",
        err=True,
    )
    statuses = "  ".join(f"{status}={c[status]}" for status in RUN_STATUSES)
    typer.echo(
        f"{statuses}  bytes_downloaded={run.bytes_downloaded}  "
        f"duration_s={run.duration_s:.2f}  run_id={run.run_id}",
        err=True,
    )
    if run.tile_suspect:
        typer.echo(
            f"⚠ site={site_id} : > {int(100 * 0.20)}% des items de la tuile de référence "
            "sont rejected_nodata (dénominateur found_tile) — tuile suspecte, à corriger "
            "en config (édition de sites.yaml + `just survey-tiles`), PAS d'auto-bascule",
            err=True,
        )


def _exit_code_for(run: Run, outcome: IngestOutcome) -> int:
    """Décision d'ancrage n°10 : 0 sans échec, 3 si TOUS les échecs sont d'origine réseau
    ET qu'aucun item n'a abouti, 1 sinon (au moins un échec, mais pas les deux conditions
    de l'exit 3 réunies)."""
    failed = run.counters["failed"]
    if failed == 0:
        return exit_codes.OK
    succeeded = run.counters["found_tile"] - failed
    if outcome.all_failures_network and succeeded == 0:
        return exit_codes.INCONCLUSIVE
    return exit_codes.FAILURE


def ingest(
    acquisitions: Path | None = typer.Option(  # noqa: B008 — idiome typer standard.
        None, "--acquisitions", help="Enveloppe JSON déjà produite (chaînage CWL, cf. `search`)."
    ),
    site_id: str | None = typer.Option(  # noqa: B008
        None, "--site", help="Id du site (sites.yaml) — forme recherche directe."
    ),
    date_from: str | None = typer.Option(  # noqa: B008
        None, "--from", help="Début de fenêtre, YYYY-MM-DD (requis avec --site)."
    ),
    date_to: str | None = typer.Option(  # noqa: B008
        None, "--to", help="Fin de fenêtre, YYYY-MM-DD (requis avec --site)."
    ),
    force: bool = typer.Option(  # noqa: B008
        False, "--force", help="Ré-ingestion inconditionnelle (ignore l'idempotence grid_hash)."
    ),
    sites_path: Path = typer.Option(  # noqa: B008
        DEFAULT_SITES_PATH, "--sites-path", help="Chemin vers sites.yaml."
    ),
    settings_path: Path = typer.Option(  # noqa: B008
        DEFAULT_SETTINGS_PATH, "--settings-path", help="Chemin vers settings.yaml."
    ),
) -> None:
    """Ingère les chips d'un site : garde epsg -> SCL -> verdict -> chips -> manifeste,
    par item. Relançable à l'infini (idempotence au grain item + `grid_hash`). Compteurs
    finaux sur STDERR, `run.json` écrit via `adapters/manifests.py`. Codes de sortie :
    OK=0, FAILURE=1 (>=1 failed avec au moins un succès), USAGE=2 (config/usage invalide,
    dont grille non calculée), INCONCLUSIVE=3 (tous les échecs sont d'origine réseau et
    aucun item n'a abouti)."""
    if (acquisitions is None) == (site_id is None):
        typer.echo(
            "usage : fournir SOIT --acquisitions <envelope.json> SOIT --site (avec --from/--to), "
            "jamais les deux ni aucun",
            err=True,
        )
        raise typer.Exit(code=exit_codes.USAGE)
    if site_id is not None and (date_from is None or date_to is None):
        typer.echo("usage : --site requiert --from ET --to", err=True)
        raise typer.Exit(code=exit_codes.USAGE)

    try:
        settings = load_settings(settings_path)
        sites = load_sites(sites_path)

        if acquisitions is not None:
            data = json.loads(acquisitions.read_text(encoding="utf-8"))
            envelope = Envelope.from_dict(data)
            site = _find_site(sites, envelope.site_id)
            _require_grid_computed(site)
            outcome = ingest_from_envelope(
                envelope=envelope,
                grid=site.grid,
                settings=settings,
                data_root=Path(settings.data_root),
                force=force,
            )
            reported_site_id = site.id
        else:
            assert site_id is not None and date_from is not None and date_to is not None
            site = _find_site(sites, site_id)
            _require_grid_computed(site)
            window = Window(start=_parse_date("from", date_from), end=_parse_date("to", date_to))
            source = build_source(settings)
            outcome = ingest_from_source(
                site=site,
                window=window,
                source=source,
                settings=settings,
                data_root=Path(settings.data_root),
                force=force,
            )
            reported_site_id = site.id
    except (ConfigError, SiteValidationError, ConservationError, ValueError, KeyError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=exit_codes.USAGE) from exc
    except StacUnreachable as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=exit_codes.INCONCLUSIVE) from exc

    _report_counters(reported_site_id, outcome.run)
    raise typer.Exit(code=_exit_code_for(outcome.run, outcome))
