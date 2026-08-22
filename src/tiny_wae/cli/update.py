"""cli/update.py — wiring pur : run quotidien "quoi de neuf ?" sur le parc (l0-05.2).

⛔ Aucune logique métier ici (règle de couche) : la boucle par site vit dans
``adapters/update.py`` (décision d'ancrage n°1 de la fiche) — ce module parse les
options, charge la config, filtre les sites, appelle l'orchestrateur, imprime les
résultats et mappe les codes de sortie.

⚠ ``--now`` est OBLIGATOIREMENT injectable (décision d'ancrage n°4, contrairement à
``ingest`` qui n'en a pas) : ``update`` calcule une fenêtre relative à "maintenant". Sans
option, un cron réel utilise l'horloge système ; les tests passent toujours ``--now``
pour rester déterministes.

Codes de sortie (décision d'ancrage n°5) : ``OK`` (0) si aucun échec ; ``FAILURE`` (1) si
au moins un échec accompagné d'au moins un succès, OU si au moins un site est vierge ;
``INCONCLUSIVE`` (3) UNIQUEMENT si tous les échecs sont d'origine réseau ET qu'aucun site
n'a abouti — c'est le CLI du cron, celui que personne ne regarde tourner.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import typer

from tiny_wae.adapters.config_io import (
    DEFAULT_SETTINGS_PATH,
    DEFAULT_SITES_PATH,
    ConfigError,
    load_settings,
    load_sites,
)
from tiny_wae.adapters.stac import EarthSearchSource, StacSource
from tiny_wae.adapters.update import (
    FAILED,
    UP_TO_DATE,
    UPDATED,
    VIERGE,
    SiteUpdateResult,
    update_all,
)
from tiny_wae.cli import exit_codes
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Site, SiteValidationError


def register(app: typer.Typer) -> None:
    """Enregistre la commande `update` sur `app` (convention d'auto-découverte)."""
    app.command(name="update")(update)


def build_source(settings: Settings) -> StacSource:
    """Construit la source STAC réelle — point de couture monkeypatché par les tests
    (son propre point, distinct de `cli/ingest.py` et `cli/search.py`, même convention)."""
    return EarthSearchSource(settings)


def _parse_sites_filter(raw: str, sites: list[Site]) -> list[Site]:
    """`--sites all` (défaut) -> le parc entier, dans l'ordre de `sites.yaml`. Sinon une
    liste CSV d'ids -> lève `ValueError` (mappé sur USAGE) si un id est inconnu."""
    if raw.strip().lower() == "all":
        return sites
    wanted = [item.strip() for item in raw.split(",") if item.strip()]
    by_id = {site.id: site for site in sites}
    missing = [site_id for site_id in wanted if site_id not in by_id]
    if missing:
        raise ValueError(f"--sites : id(s) inconnu(s) {missing} (cf. sites.yaml)")
    return [by_id[site_id] for site_id in wanted]


def _parse_now(raw: str) -> datetime:
    """Parse `--now` (``YYYY-MM-DD`` ou ISO complet) en `datetime` naïf ; lève
    `ValueError` sinon."""
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(
            f"--now {raw!r} : datetime attendu (YYYY-MM-DD ou YYYY-MM-DDTHH:MM:SS)"
        ) from exc
    return parsed.replace(tzinfo=None)


def _report_site(result: SiteUpdateResult) -> None:
    """Une ligne par site sur STDERR (discipline des flux du dépôt)."""
    line = (
        f"site={result.site_id}  status={result.status}  ingested={result.ingested}  "
        f"assets_read={result.assets_read}"
    )
    if result.message is not None:
        line += f"  message={result.message}"
    typer.echo(line, err=True)


def _report_summary(results: list[SiteUpdateResult], now: datetime) -> None:
    """Résumé final honnête + rappel du rattrapage mensuel le 1er du mois (décision
    d'ancrage n°6 : documenté, non automatisé — cf. README)."""
    new_count = sum(1 for r in results if r.status == UPDATED)
    up_to_date_count = sum(1 for r in results if r.status == UP_TO_DATE)
    failure_count = sum(1 for r in results if r.status in (VIERGE, FAILED))
    typer.echo(
        f"{len(results)} sites, {new_count} avec du nouveau, {up_to_date_count} à jour, "
        f"{failure_count} échecs",
        err=True,
    )
    if now.day == 1:
        typer.echo(
            "⭐ 1er du mois : penser au rattrapage mensuel des retraitements tardifs "
            "(`just run backfill --site <id> --months 2`) — non automatisé, cf. README",
            err=True,
        )


def _exit_code_for(results: list[SiteUpdateResult]) -> int:
    """Décision d'ancrage n°5 : 0 sans échec ; 3 ssi TOUS les échecs sont d'origine
    réseau ET qu'aucun site n'a abouti (site vierge exclu, jamais réseau) ; 1 sinon."""
    failures = [r for r in results if r.status in (VIERGE, FAILED)]
    if not failures:
        return exit_codes.OK
    any_success = any(r.status in (UPDATED, UP_TO_DATE) for r in results)
    all_network = all(r.is_network_failure for r in failures)
    if all_network and not any_success:
        return exit_codes.INCONCLUSIVE
    return exit_codes.FAILURE


def update(
    sites: str = typer.Option(
        "all", "--sites", help="Ids CSV à traiter, ou `all` (défaut) pour tout le parc."
    ),
    now: str | None = typer.Option(
        None,
        "--now",
        help="Horodatage injecté (YYYY-MM-DD[THH:MM:SS]) — sans option, horloge système.",
    ),
    sites_path: Path = typer.Option(  # noqa: B008
        DEFAULT_SITES_PATH, "--sites-path", help="Chemin vers sites.yaml."
    ),
    settings_path: Path = typer.Option(  # noqa: B008
        DEFAULT_SETTINGS_PATH, "--settings-path", help="Chemin vers settings.yaml."
    ),
) -> None:
    """Run quotidien : pour chaque site, fenêtre depuis le dernier manifeste connu
    (marge `incremental_margin_days`), `ingest`, résumé honnête sur STDERR. Un site sans
    aucun manifeste est signalé « vierge » (pointant `backfill`), jamais traité comme un
    bug. Rejouable à l'infini (idempotence héritée d'`ingest`)."""
    try:
        settings = load_settings(settings_path)
        all_sites = load_sites(sites_path)
        selected = _parse_sites_filter(sites, all_sites)
        effective_now = datetime.now(UTC).replace(tzinfo=None) if now is None else _parse_now(now)
    except (ConfigError, SiteValidationError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=exit_codes.USAGE) from exc

    source = build_source(settings)
    results = update_all(
        sites=selected,
        settings=settings,
        source=source,
        data_root=Path(settings.data_root),
        now=effective_now,
    )

    for result in results:
        _report_site(result)
    _report_summary(results, effective_now)

    raise typer.Exit(code=_exit_code_for(results))
