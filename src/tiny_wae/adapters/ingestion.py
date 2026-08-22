"""adapters/ingestion.py — boucle d'ingestion complète (garde epsg → SCL → verdict →
bandes → garde nodata finale → manifeste), assemblée pour la fiche l0-03.4.

Porte TOUTE l'orchestration (décision d'ancrage n°1 de la fiche) : ``cli/ingest.py`` ne
fait QUE parser les options, appeler ce module et mapper les exceptions sur les codes de
sortie — c'est ce qui rend le pipeline importable et testable directement (le smoke de
``scripts/smoke.py`` l'appelle sans passer par un sous-processus).

Deux points d'entrée publics, un par forme d'appel de ``ingest`` :

- ``ingest_from_envelope`` : l'enveloppe JSON a déjà été produite ailleurs (chaînage CWL,
  forme ``--acquisitions``).
- ``ingest_from_source`` : interroge un port ``StacSource`` (avec retry) pour obtenir
  l'enveloppe (forme ``--site --from --to``).

Les deux convergent vers ``_run_ingestion``, qui porte la boucle par item et écrit
``run.json`` en dernier, via l'API ``adapters/manifests.py`` (jamais de JSON réécrit ici).
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

import tiny_wae
from tiny_wae.adapters.chips import (
    ChipResult,
    EpsgMismatchError,
    check_epsg,
    read_bands_10m,
    read_bands_20m,
    read_scl,
    write_chips,
)
from tiny_wae.adapters.manifests import (
    RUN_STATUSES,
    Manifest,
    Run,
    grid_hash,
    read_manifest,
    write_manifest,
    write_run,
)
from tiny_wae.adapters.stac import StacSource, StacUnreachable
from tiny_wae.core.acquisition import Acquisition
from tiny_wae.core.envelope import Envelope
from tiny_wae.core.scl import verdict as scl_verdict
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Grid, Site
from tiny_wae.core.windows import Window

# Seuil du signalement de tuile suspecte (O5ter, chapeau l0-03) — dénominateur found_tile,
# jamais found_stac (décision E-a du chapeau l0-02 : "found" seul est banni).
_TILE_SUSPECT_RATIO = 0.20


@dataclass(frozen=True, slots=True)
class IngestOutcome:
    """Résultat d'un run d'ingestion : le ``Run`` déjà écrit + de quoi calculer l'exit code.

    ``all_failures_network`` n'entre PAS dans le schéma ``run.json`` (il n'a pas de sens
    hors de ce process) : c'est le CLI qui en a besoin pour la décision d'ancrage n°10
    (exit ``INCONCLUSIVE`` ssi tous les échecs sont d'origine réseau ET aucun item n'a
    abouti). Vaut ``True`` par convention quand il n'y a aucun échec.
    """

    run: Run
    all_failures_network: bool


def _new_run_id() -> str:
    """Identifiant de run : ``run-YYYYMMDDTHHMMSS-ffffffZ`` (UTC, à la MICROSECONDE).

    Fonction interne monkeypatchée par les tests (décision d'ancrage n°3 de l0-03.4).

    ⭐ La résolution à la seconde ne suffisait pas : ``adapters/backfill.py`` (l0-04.1)
    traite plusieurs fenêtres d'un même site à la suite, et deux d'entre elles terminant
    dans la même seconde produisaient le MÊME ``run_id`` — donc le même chemin de
    ``run.json``, donc un journal écrasé en silence. La microseconde les sépare, et le tri
    lexicographique des identifiants reste chronologique.
    """
    return datetime.now(UTC).strftime("run-%Y%m%dT%H%M%S-%fZ")


def _sleep(seconds: float) -> None:
    """Attente de backoff isolée (décision d'ancrage n°6) — neutralisée par les tests, qui
    monkeypatchent cette fonction pour qu'aucun test ne dorme réellement."""
    time.sleep(seconds)


def _is_network_error(exc: BaseException) -> bool:
    """Classe une exception comme "d'origine réseau" (décision d'ancrage n°10).

    ``OSError`` couvre à la fois les erreurs de transport HTTP et les échecs d'ouverture
    GDAL/rasterio (``RasterioIOError`` en hérite) : c'est la même famille d'erreur que
    l'amont soit injoignable ou qu'un asset soit illisible. ``StacUnreachable`` (l0-02.2)
    en fait partie explicitement : elle N'hérite PAS d'``OSError`` (c'est voulu — elle ne
    doit pas être confondue avec un ``StacSourceError`` de parsing), et l'omettre ici
    classerait l'erreur réseau la PLUS explicite du projet comme « pas réseau ».
    Toute autre exception (garde epsg, clé d'asset manquante, bug de logique) n'est pas
    d'origine réseau.
    """
    return isinstance(exc, OSError | StacUnreachable)


def _retry_call[T](fn: Callable[[], T], settings: Settings) -> T:
    """Exécute ``fn`` avec retry/backoff (``settings.http_retries`` tentatives EN PLUS de
    la première), appliqué aux appels STAC et aux lectures COG (décision d'ancrage n°6).
    N'avale RIEN : la dernière exception est relancée telle quelle après épuisement des
    tentatives, pour que l'appelant la classe et lui donne une cause.

    ⭐ Seules les erreurs D'ORIGINE RÉSEAU (``_is_network_error``) sont retentées : une
    erreur déterministe (clé d'asset absente de l'item, bug de logique) ne se résoudra
    jamais d'elle-même, et la retenter ferait perdre ``http_retries × http_backoff_s``
    secondes PAR ITEM — 6 s ici, multipliées par les 25 sites × 48 mois de la campagne
    l0-04.H. Elle est donc relancée immédiatement, sans attente."""
    attempts = settings.http_retries + 1
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — reclassifiée par l'appelant, jamais avalée
            last_exc = exc
            if not _is_network_error(exc):
                raise
            if attempt < attempts - 1:
                _sleep(settings.http_backoff_s)
    assert (
        last_exc is not None
    )  # attempts >= 1 (settings.validate() garantit http_retries > 0... >=0)
    raise last_exc


def _radiometry_to_manifest(
    radiometry: dict[str, tuple[float, float] | None],
) -> dict[str, dict[str, float] | None]:
    """Convertit ``Acquisition.radiometry`` (tuples) vers la forme manifeste (dicts).

    Conversion à charge de cette fiche (cf. ancrage) : ``Acquisition.radiometry`` porte
    ``dict[str, tuple[float,float] | None]``, ``Manifest.radiometry`` porte
    ``dict[str, dict[str,float] | None]`` (``{"scale":…, "offset":…}``).
    """
    return {
        key: (None if value is None else {"scale": value[0], "offset": value[1]})
        for key, value in radiometry.items()
    }


def _scl_class_counts(scl_array: np.ndarray) -> dict[int, int]:
    """Compte les classes SCL d'un tableau 2D — mapping ``dict[int, int]`` attendu par
    ``core.scl.verdict``. Le tableau est déjà décodé (uint8) par ``read_scl``."""
    counter = Counter(int(v) for v in scl_array.flatten().tolist())
    return dict(counter)


def _empty_manifest(
    *,
    site_id: str,
    acq: Acquisition,
    status: str,
    cause: str | None,
    invalid_pct: float,
    cloud_pct: float,
    chip_nodata_pct: float,
    scl_class_counts: dict[int, int],
    grid_hash_value: str,
    assets_read: int,
    content_hashes: dict[str, str],
    bytes_written: int,
    files: list[str],
    duration_s: float,
) -> Manifest:
    """Assemble un ``Manifest`` complet — factorise les 24 champs communs à tous les
    statuts (ingested, rejected_*, failed) : seuls les champs qui varient par statut sont
    passés en paramètre, le reste vient de l'``Acquisition`` telle que le port l'a rendue.
    """
    return Manifest(
        schema_version=1,
        site_id=site_id,
        item_id=acq.item_id,
        datetime=acq.datetime,
        tile=acq.tile,
        sequence=acq.sequence,
        platform=acq.platform,
        status=status,
        cause=cause,
        invalid_pct=invalid_pct,
        cloud_pct=cloud_pct,
        chip_nodata_pct=chip_nodata_pct,
        scl_class_counts={str(k): v for k, v in scl_class_counts.items()},
        processing_baseline=acq.processing_baseline,
        boa_offset_applied=acq.boa_offset_applied,
        radiometry=_radiometry_to_manifest(acq.radiometry),
        grid_hash=grid_hash_value,
        assets_read=assets_read,
        content_hashes=content_hashes,
        bytes_downloaded=0,  # décision d'ancrage n°7 : jamais mesuré côté lecture raster.
        bytes_written=bytes_written,
        duration_s=duration_s,
        files=files,
        versions={"tiny_wae": tiny_wae.__version__},
    )


def _process_item(
    *,
    site_id: str,
    grid: Grid,
    acq: Acquisition,
    settings: Settings,
    data_root: Path,
    grid_hash_value: str,
) -> tuple[str, bool]:
    """Traite UN item selon l'ordre invariant du chapeau — écrit son manifeste, renvoie
    ``(status, is_network_failure)``. ``is_network_failure`` n'a de sens que pour
    ``status == "failed"`` (décision d'ancrage n°10, cf. ``IngestOutcome``)."""
    start = time.monotonic()
    dest_dir = Path(data_root) / site_id / acq.item_id

    # 1. Garde epsg — PAS de retry (pure, zéro I/O) : failed immédiat sans consommer de
    #    tentative réseau.
    try:
        check_epsg(acq, grid)
    except EpsgMismatchError as exc:
        manifest = _empty_manifest(
            site_id=site_id,
            acq=acq,
            status="failed",
            cause=str(exc),
            invalid_pct=0.0,
            cloud_pct=0.0,
            chip_nodata_pct=0.0,
            scl_class_counts={},
            grid_hash_value=grid_hash_value,
            assets_read=0,
            content_hashes={},
            bytes_written=0,
            files=[],
            duration_s=time.monotonic() - start,
        )
        write_manifest(data_root, manifest)
        return "failed", _is_network_error(exc)

    # 2. SCL seul (fenêtré), avec retry.
    try:
        scl_array, scl_reads = _retry_call(lambda: read_scl(acq, grid, settings), settings)
    except Exception as exc:  # noqa: BLE001 — jamais avalée, classée puis manifestée.
        manifest = _empty_manifest(
            site_id=site_id,
            acq=acq,
            status="failed",
            cause=str(exc),
            invalid_pct=0.0,
            cloud_pct=0.0,
            chip_nodata_pct=0.0,
            scl_class_counts={},
            grid_hash_value=grid_hash_value,
            assets_read=0,
            content_hashes={},
            bytes_written=0,
            files=[],
            duration_s=time.monotonic() - start,
        )
        write_manifest(data_root, manifest)
        return "failed", _is_network_error(exc)

    # 3. Verdict.
    class_counts = _scl_class_counts(scl_array)
    verdict_result = scl_verdict(class_counts, settings)

    if verdict_result.status != "ingested":
        # Un rejet SCL écrit un manifeste SANS chips (chapeau l0-03) : les bandes ne
        # sont même pas lues.
        manifest = _empty_manifest(
            site_id=site_id,
            acq=acq,
            status=verdict_result.status,
            cause=None,
            invalid_pct=verdict_result.invalid_pct,
            cloud_pct=verdict_result.cloud_pct,
            chip_nodata_pct=0.0,
            scl_class_counts=class_counts,
            grid_hash_value=grid_hash_value,
            assets_read=scl_reads,
            content_hashes={},
            bytes_written=0,
            files=[],
            duration_s=time.monotonic() - start,
        )
        write_manifest(data_root, manifest)
        return verdict_result.status, False

    # 4. Bandes 10 m puis 20 m, avec retry chacune.
    try:
        bands_10m, reads_10m = _retry_call(lambda: read_bands_10m(acq, grid, settings), settings)
        bands_20m, reads_20m = _retry_call(lambda: read_bands_20m(acq, grid, settings), settings)
    except Exception as exc:  # noqa: BLE001
        manifest = _empty_manifest(
            site_id=site_id,
            acq=acq,
            status="failed",
            cause=str(exc),
            invalid_pct=verdict_result.invalid_pct,
            cloud_pct=verdict_result.cloud_pct,
            chip_nodata_pct=0.0,
            scl_class_counts=class_counts,
            grid_hash_value=grid_hash_value,
            assets_read=scl_reads,
            content_hashes={},
            bytes_written=0,
            files=[],
            duration_s=time.monotonic() - start,
        )
        write_manifest(data_root, manifest)
        return "failed", _is_network_error(exc)

    chip_result: ChipResult = write_chips(
        dest_dir,
        bands_10m=bands_10m,
        bands_20m=bands_20m,
        scl=scl_array,
        grid=grid,
        item_id=acq.item_id,
        assets_read=scl_reads + reads_10m + reads_20m,
    )

    # 5. Garde nodata FINALE (arbitrage n°3) — postérieure au verdict SCL.
    if chip_result.chip_nodata_pct > settings.chip_nodata_pct_max:
        for filename in chip_result.files:
            (dest_dir / filename).unlink(missing_ok=True)
        manifest = _empty_manifest(
            site_id=site_id,
            acq=acq,
            status="rejected_nodata",
            cause=None,
            invalid_pct=verdict_result.invalid_pct,
            cloud_pct=verdict_result.cloud_pct,
            chip_nodata_pct=chip_result.chip_nodata_pct,
            scl_class_counts=class_counts,
            grid_hash_value=grid_hash_value,
            assets_read=chip_result.assets_read,
            content_hashes={},  # fichiers supprimés : pas de contenu à attester.
            bytes_written=0,
            files=[],
            duration_s=time.monotonic() - start,
        )
        write_manifest(data_root, manifest)
        return "rejected_nodata", False

    # 6. Ingéré — manifeste EN DERNIER (atomique), après que les 3 fichiers sont sur disque.
    manifest = _empty_manifest(
        site_id=site_id,
        acq=acq,
        status="ingested",
        cause=None,
        invalid_pct=verdict_result.invalid_pct,
        cloud_pct=verdict_result.cloud_pct,
        chip_nodata_pct=chip_result.chip_nodata_pct,
        scl_class_counts=class_counts,
        grid_hash_value=grid_hash_value,
        assets_read=chip_result.assets_read,
        content_hashes=chip_result.content_hashes,
        bytes_written=chip_result.bytes_written,
        files=chip_result.files,
        duration_s=time.monotonic() - start,
    )
    write_manifest(data_root, manifest)
    return "ingested", False


def _run_ingestion(
    *,
    site_id: str,
    grid: Grid,
    window: dict[str, str],
    envelope_counters: dict[str, int],
    items: list[Acquisition],
    settings: Settings,
    data_root: Path,
    force: bool,
) -> IngestOutcome:
    """Boucle d'ingestion sur des items déjà obtenus (enveloppe en main) — cœur commun aux
    deux formes d'appel du CLI. Idempotence au grain item + ``grid_hash`` (décision du
    chapeau l0-03) : un manifeste existant au ``grid_hash`` courant est compté ``skipped``
    sans aucune lecture ; ``force=True`` ignore cette vérification."""
    run_start = time.monotonic()
    current_hash = grid_hash(grid, settings)

    status_counts: dict[str, int] = dict.fromkeys(RUN_STATUSES, 0)
    assets_read_total = 0
    any_non_network_failure = False

    for acq in items:
        if not force:
            try:
                existing = read_manifest(data_root, site_id, acq.item_id)
            except FileNotFoundError:
                existing = None
            if existing is not None and existing.grid_hash == current_hash:
                status_counts["skipped"] += 1
                continue

        status, is_network = _process_item(
            site_id=site_id,
            grid=grid,
            acq=acq,
            settings=settings,
            data_root=data_root,
            grid_hash_value=current_hash,
        )
        status_counts[status] += 1
        if status == "ingested":
            manifest = read_manifest(data_root, site_id, acq.item_id)
            assets_read_total += manifest.assets_read
        elif status in ("rejected_clouds", "rejected_invalid", "rejected_nodata"):
            manifest = read_manifest(data_root, site_id, acq.item_id)
            assets_read_total += manifest.assets_read
        elif status == "failed" and not is_network:
            any_non_network_failure = True

    found_tile = envelope_counters["found_tile"]
    nodata_ratio = status_counts["rejected_nodata"] / found_tile if found_tile > 0 else 0.0
    tile_suspect = nodata_ratio > _TILE_SUSPECT_RATIO

    counters = {
        "found_stac": envelope_counters["found_stac"],
        "skipped_scene_cloud": envelope_counters["skipped_scene_cloud"],
        "off_tile": envelope_counters["off_tile"],
        "found_tile": found_tile,
        **status_counts,
    }

    run = Run(
        schema_version=1,
        site_id=site_id,
        run_id=_new_run_id(),
        window=dict(window),
        counters=counters,
        assets_read=assets_read_total,
        bytes_downloaded=0,  # ancrage n°7 : donnée de rapport, jamais un critère de gate.
        tile_suspect=tile_suspect,
        duration_s=time.monotonic() - run_start,
    )
    write_run(data_root, run)

    # Vrai si aucun échec (convention, cf. docstring d'IngestOutcome) OU si tous les
    # échecs constatés sont d'origine réseau (aucun échec non-réseau relevé).
    all_failures_network = status_counts["failed"] == 0 or not any_non_network_failure
    return IngestOutcome(run=run, all_failures_network=all_failures_network)


def ingest_from_envelope(
    *,
    envelope: Envelope,
    grid: Grid,
    settings: Settings,
    data_root: Path,
    force: bool = False,
) -> IngestOutcome:
    """Forme ``--acquisitions`` : l'enveloppe a déjà été produite (chaînage CWL, l0-02.2).

    ``grid`` est celle du site (``envelope.site_id``), à charge de l'appelant (CLI) de la
    résoudre via ``sites.yaml`` — ce module ne charge aucune config.
    """
    return _run_ingestion(
        site_id=envelope.site_id,
        grid=grid,
        window=envelope.window,
        envelope_counters=envelope.counters,
        items=envelope.items,
        settings=settings,
        data_root=data_root,
        force=force,
    )


def ingest_from_source(
    *,
    site: Site,
    window: Window,
    source: StacSource,
    settings: Settings,
    data_root: Path,
    force: bool = False,
) -> IngestOutcome:
    """Forme ``--site --from --to`` : interroge ``source`` (avec retry/backoff) puis
    ingeste. ``StacUnreachable`` (ou toute autre exception de transport), si elle survit
    aux tentatives, n'est PAS avalée : elle remonte telle quelle jusqu'au CLI, qui la
    mappe sur l'exit ``INCONCLUSIVE``."""
    envelope = _retry_call(lambda: source.search(site, window), settings)
    return _run_ingestion(
        site_id=site.id,
        grid=site.grid,
        window=envelope.window,
        envelope_counters=envelope.counters,
        items=envelope.items,
        settings=settings,
        data_root=data_root,
        force=force,
    )
