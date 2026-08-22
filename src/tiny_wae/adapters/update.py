"""adapters/update.py — boucle par site du run quotidien "quoi de neuf ?" (l0-05.2).

Porte TOUTE l'orchestration (décision de couche du dépôt, cf. `adapters/ingestion.py`) :
`cli/update.py` ne fait QUE parser les options, appeler ce module, imprimer les résultats
et mapper les codes de sortie — ce qui rend la boucle testable sans sous-processus.

Pour chaque site : la dernière date connue vient de `adapters.manifests.last_datetime`,
la fenêtre incrémentale de `core.windows.update_window_for_site` (jamais recalculée à la
main, décision d'ancrage n°2 de la fiche). Un site sans aucun manifeste (`NoManifests`)
est un statut à part entière (« vierge »), pas une exception : c'est ce qui produit
l'exit 1 « backfill » du CLI, sans jamais interrompre le traitement des autres sites.

Une exception levée par `ingest_from_source` pour UN site (`StacUnreachable`, ou toute
autre erreur remontée après épuisement des tentatives de `adapters.ingestion`) est
capturée ICI, classée via `adapters.ingestion._is_network_error` (jamais redéfinie) et
transformée en résultat « failed » pour ce site — les autres sites du parc sont traités
normalement (oracle O5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from tiny_wae.adapters.ingestion import _is_network_error, ingest_from_source
from tiny_wae.adapters.manifests import last_datetime
from tiny_wae.adapters.stac import StacSource
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Site
from tiny_wae.core.windows import NoManifests, update_window_for_site

# Statuts possibles d'un `SiteUpdateResult` — fermé, consommé par `cli/update.py` pour
# le résumé final ("N avec du nouveau, M à jour, K échecs") et le calcul du code de sortie.
UPDATED = "updated"
UP_TO_DATE = "up_to_date"
VIERGE = "vierge"
FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SiteUpdateResult:
    """Résultat de l'update d'UN site — un par site du parc, quel que soit son sort.

    `assets_read` vaut 0 pour un site vierge ou une exception levée avant qu'aucun asset
    n'ait été lu (oracle O2 : un run "rien de nouveau" doit rendre `assets_read == 0`,
    pas seulement `ingested == 0` — un pipeline qui relirait les assets sans rien ingérer
    passerait un oracle qui ne regarderait que `ingested`).
    """

    site_id: str
    status: str
    ingested: int
    assets_read: int
    is_network_failure: bool
    message: str | None


def update_site(
    *,
    site: Site,
    settings: Settings,
    source: StacSource,
    data_root: Path,
    now: datetime,
    margin_days: int | None = None,
) -> SiteUpdateResult:
    """Met à jour UN site : fenêtre incrémentale depuis son dernier manifeste, puis
    `ingest_from_source`. Ne lève JAMAIS — toute exception d'ingestion est capturée et
    classée réseau/non-réseau (décision d'ancrage n°5 de la fiche), afin que la boucle du
    parc (`update_all`) ne s'arrête jamais sur l'échec d'un seul site.
    """
    margin = settings.incremental_margin_days if margin_days is None else margin_days
    window = update_window_for_site(last_datetime(data_root, site.id), margin, now)

    if isinstance(window, NoManifests):
        return SiteUpdateResult(
            site_id=site.id,
            status=VIERGE,
            ingested=0,
            assets_read=0,
            is_network_failure=False,
            message=f"site {site.id} : aucun manifeste — lancer `backfill` avant `update`",
        )

    try:
        outcome = ingest_from_source(
            site=site, window=window, source=source, settings=settings, data_root=data_root
        )
    except Exception as exc:  # noqa: BLE001 — reclassée, jamais avalée silencieusement.
        return SiteUpdateResult(
            site_id=site.id,
            status=FAILED,
            ingested=0,
            assets_read=0,
            is_network_failure=_is_network_error(exc),
            message=str(exc),
        )

    counters = outcome.run.counters
    if counters["failed"] > 0:
        return SiteUpdateResult(
            site_id=site.id,
            status=FAILED,
            ingested=counters["ingested"],
            assets_read=outcome.run.assets_read,
            is_network_failure=outcome.all_failures_network,
            message=None,
        )

    status = UPDATED if counters["ingested"] > 0 else UP_TO_DATE
    return SiteUpdateResult(
        site_id=site.id,
        status=status,
        ingested=counters["ingested"],
        assets_read=outcome.run.assets_read,
        is_network_failure=False,
        message=None,
    )


def update_all(
    *,
    sites: list[Site],
    settings: Settings,
    source: StacSource,
    data_root: Path,
    now: datetime,
    margin_days: int | None = None,
) -> list[SiteUpdateResult]:
    """Boucle le run quotidien sur tout le parc (ou le sous-ensemble filtré par le CLI) —
    ordre stable (celui de `sites`), un `SiteUpdateResult` par site, jamais moins."""
    return [
        update_site(
            site=site,
            settings=settings,
            source=source,
            data_root=data_root,
            now=now,
            margin_days=margin_days,
        )
        for site in sites
    ]
