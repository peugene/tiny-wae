"""Tests adapters/ingestion.py (l0-03.4) — boucle d'ingestion complète, sur doubles en
mémoire du port ``StacSource`` et rasters synthétiques écrits par le test (les fixtures
COG réelles arrivent en l0-03.5).

Couvre l'oracle de la fiche (numérotation reprise de ``l0-03.4.md``) :
- O1 : run sur 5 items (clair/nuageux/invalide/nodata/échec) -> statuts conformes,
  invariants de conservation du run.json, compteurs GELÉS EN LITTÉRAL dans le test.
- O2 : run double — témoin positif (1er run : assets_read > 0) ET négatif (2e run :
  assets_read == 0, skipped == N, content_hashes identiques).
- O3 : grid_hash changé -> ré-ingestion, nouveau transform correct.
- O4 : item sequence=1 même date que le "_0" -> 2 répertoires distincts.
- O5 : échec injecté sur 1 item / N -> manifeste failed+cause, les N-1 autres traités.
- O5bis : garde nodata -> rejected_nodata, chip_nodata_pct au manifeste, fichiers supprimés.
- O5ter : règle de repli tuile -> tile_suspect=true si rejected_nodata/found_tile > 20 %.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio

import tiny_wae.adapters.ingestion as ingestion_module
from tiny_wae.adapters.ingestion import ingest_from_envelope
from tiny_wae.adapters.manifests import grid_hash, list_for_site, read_manifest
from tiny_wae.core.acquisition import Acquisition
from tiny_wae.core.envelope import Envelope
from tiny_wae.core.geometry import transform_for
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Grid

# Grille synthétique littérale : origine multiple de 60 m (mêmes valeurs que test_chips.py).
_GRID = Grid(epsg=32631, origin_x=699960.0, origin_y=4900020.0)

_SETTINGS = Settings(
    stac_url="https://example.test/stac",
    stac_collection="sentinel-2-l2a",
    chip_px_10m=4,
    chip_px_20m=2,
    http_retries=2,
    http_backoff_s=1,
)

_VEGETATION = 4  # classe SCL hors invalide {0,1} et nuageuse {3,8,9,10} -> "ingested".
_INVALID = 0
_CLOUD = 9
_BAND_VALUE = 500


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise l'attente de backoff pour TOUS les tests de ce module (règle n°10 du
    dépôt : aucun test ne doit dormir)."""
    monkeypatch.setattr(ingestion_module, "_sleep", lambda seconds: None)


def _write_raster(
    path: Path, *, grid: Grid, resolution: int, size: int, value: int, dtype: type
) -> None:
    """Écrit un GeoTIFF source 1 bande, constant, exactement sur l'emprise du chip."""
    transform = transform_for(grid, resolution)
    array = np.full((size, size), value, dtype=dtype)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=size,
        width=size,
        count=1,
        dtype=array.dtype,
        crs=f"EPSG:{grid.epsg}",
        transform=transform,
    ) as dst:
        dst.write(array, 1)


def _write_scl(tmp_path: Path, name: str, *, grid: Grid, settings: Settings, scl_value: int) -> str:
    path = tmp_path / f"{name}_scl.tif"
    _write_raster(
        path,
        grid=grid,
        resolution=20,
        size=settings.chip_px_20m,
        value=scl_value,
        dtype=np.uint8,
    )
    return str(path)


def _write_bands(
    tmp_path: Path,
    name: str,
    *,
    grid: Grid,
    settings: Settings,
    band_value: int,
    nodata_fraction: float = 0.0,
) -> dict[str, str]:
    """Écrit les 10 bandes (4 x 10 m + 6 x 20 m). ``nodata_fraction`` met à 0 (nodata) la
    fraction demandée des pixels des 4 bandes 10 m."""
    assets: dict[str, str] = {}
    for key in ("blue", "green", "red", "nir"):
        p = tmp_path / f"{name}_{key}.tif"
        _write_raster(
            p,
            grid=grid,
            resolution=10,
            size=settings.chip_px_10m,
            value=band_value,
            dtype=np.uint16,
        )
        assets[key] = str(p)
    for key in ("rededge1", "rededge2", "rededge3", "nir08", "swir16", "swir22"):
        p = tmp_path / f"{name}_{key}.tif"
        _write_raster(
            p,
            grid=grid,
            resolution=20,
            size=settings.chip_px_20m,
            value=band_value,
            dtype=np.uint16,
        )
        assets[key] = str(p)

    if nodata_fraction > 0:
        total_pixels = settings.chip_px_10m * settings.chip_px_10m
        n_nodata = int(total_pixels * nodata_fraction)
        for key in ("blue", "green", "red", "nir"):
            with rasterio.open(assets[key]) as src:
                arr = src.read(1)
                profile = src.profile
            flat = arr.reshape(-1)
            flat[:n_nodata] = 0
            arr = flat.reshape(arr.shape)
            with rasterio.open(assets[key], "w", **profile) as dst:
                dst.write(arr, 1)
    return assets


def _make_clear(tmp_path: Path, item_id: str) -> Acquisition:
    assets = _write_bands(tmp_path, item_id, grid=_GRID, settings=_SETTINGS, band_value=_BAND_VALUE)
    assets["scl"] = _write_scl(
        tmp_path, item_id, grid=_GRID, settings=_SETTINGS, scl_value=_VEGETATION
    )
    return Acquisition(
        item_id=item_id,
        datetime="2026-01-01T10:00:00Z",
        platform="sentinel-2a",
        tile="31TCJ",
        sequence="0",
        scene_cloud_cover=0.0,
        nodata_pixel_pct=0.0,
        processing_baseline="99.9",
        boa_offset_applied=True,
        proj_epsg=_GRID.epsg,
        assets=assets,
        radiometry=dict.fromkeys(assets),
    )


def _make_cloudy(tmp_path: Path, item_id: str) -> Acquisition:
    acq = _make_clear(tmp_path, item_id)
    # écrase le SCL en tout-nuageux (classe 9) -> cloud_pct = 100 %.
    scl_path = acq.assets["scl"]
    _write_raster(
        Path(scl_path),
        grid=_GRID,
        resolution=20,
        size=_SETTINGS.chip_px_20m,
        value=_CLOUD,
        dtype=np.uint8,
    )
    return acq


def _make_invalid(tmp_path: Path, item_id: str) -> Acquisition:
    acq = _make_clear(tmp_path, item_id)
    scl_path = acq.assets["scl"]
    _write_raster(
        Path(scl_path),
        grid=_GRID,
        resolution=20,
        size=_SETTINGS.chip_px_20m,
        value=_INVALID,
        dtype=np.uint8,
    )
    return acq


def _make_nodata_with_settings(
    tmp_path: Path, item_id: str, *, settings: Settings, nodata_fraction: float
) -> Acquisition:
    assets = _write_bands(
        tmp_path,
        item_id,
        grid=_GRID,
        settings=settings,
        band_value=_BAND_VALUE,
        nodata_fraction=nodata_fraction,
    )
    assets["scl"] = _write_scl(
        tmp_path, item_id, grid=_GRID, settings=settings, scl_value=_VEGETATION
    )
    return Acquisition(
        item_id=item_id,
        datetime="2026-01-01T10:00:00Z",
        platform="sentinel-2a",
        tile="31TCJ",
        sequence="0",
        scene_cloud_cover=0.0,
        nodata_pixel_pct=0.0,
        processing_baseline="99.9",
        boa_offset_applied=True,
        proj_epsg=_GRID.epsg,
        assets=assets,
        radiometry=dict.fromkeys(assets),
    )


def _make_nodata(tmp_path: Path, item_id: str, *, nodata_fraction: float = 0.5) -> Acquisition:
    return _make_nodata_with_settings(
        tmp_path, item_id, settings=_SETTINGS, nodata_fraction=nodata_fraction
    )


def _make_failing(item_id: str) -> Acquisition:
    """Item dont TOUS les hrefs pointent vers des fichiers inexistants -> échec réseau."""
    missing = {
        key: f"/nonexistent/{item_id}_{key}.tif"
        for key in (
            "blue",
            "green",
            "red",
            "nir",
            "rededge1",
            "rededge2",
            "rededge3",
            "nir08",
            "swir16",
            "swir22",
            "scl",
        )
    }
    return Acquisition(
        item_id=item_id,
        datetime="2026-01-01T10:00:00Z",
        platform="sentinel-2a",
        tile="31TCJ",
        sequence="0",
        scene_cloud_cover=0.0,
        nodata_pixel_pct=0.0,
        processing_baseline="99.9",
        boa_offset_applied=True,
        proj_epsg=_GRID.epsg,
        assets=missing,
        radiometry=dict.fromkeys(missing),
    )


def _envelope(
    site_id: str, items: list[Acquisition], *, off_tile: int = 1, skipped_scene_cloud: int = 1
) -> Envelope:
    found_tile = len(items)
    found_stac = found_tile + off_tile + skipped_scene_cloud
    return Envelope(
        schema_version=1,
        site_id=site_id,
        window={"start": "2026-01-01T00:00:00", "end": "2026-02-01T00:00:00"},
        counters={
            "found_stac": found_stac,
            "skipped_scene_cloud": skipped_scene_cloud,
            "off_tile": off_tile,
            "found_tile": found_tile,
        },
        items=items,
    )


# ── O1 : 5 items, statuts conformes, compteurs gelés en littéral ────────────────────


def test_o1_run_mix_statuts_conformes_et_compteurs_geles(tmp_path: Path) -> None:
    """5 items (clair/nuageux/invalide/nodata/échec) -> chaque statut attendu, invariants
    du run.json bouclés, compteurs GELÉS EN LITTÉRAL (jamais recopiés à l'exécution)."""
    items = [
        _make_clear(tmp_path, "ITEM_CLEAR"),
        _make_cloudy(tmp_path, "ITEM_CLOUDY"),
        _make_invalid(tmp_path, "ITEM_INVALID"),
        _make_nodata(tmp_path, "ITEM_NODATA", nodata_fraction=0.5),
        _make_failing("ITEM_FAIL"),
    ]
    envelope = _envelope("T01", items, off_tile=1, skipped_scene_cloud=1)
    data_root = tmp_path / "data"

    outcome = ingest_from_envelope(
        envelope=envelope, grid=_GRID, settings=_SETTINGS, data_root=data_root
    )
    run = outcome.run

    assert read_manifest(data_root, "T01", "ITEM_CLEAR").status == "ingested"
    assert read_manifest(data_root, "T01", "ITEM_CLOUDY").status == "rejected_clouds"
    assert read_manifest(data_root, "T01", "ITEM_INVALID").status == "rejected_invalid"
    assert read_manifest(data_root, "T01", "ITEM_NODATA").status == "rejected_nodata"
    failed_manifest = read_manifest(data_root, "T01", "ITEM_FAIL")
    assert failed_manifest.status == "failed"
    assert failed_manifest.cause  # non vide

    # Compteurs gelés en LITTÉRAL (règle du dépôt) — pas recopiés depuis `run.counters`.
    assert run.counters["found_stac"] == 7
    assert run.counters["skipped_scene_cloud"] == 1
    assert run.counters["off_tile"] == 1
    assert run.counters["found_tile"] == 5
    assert run.counters["ingested"] == 1
    assert run.counters["rejected_clouds"] == 1
    assert run.counters["rejected_invalid"] == 1
    assert run.counters["rejected_nodata"] == 1
    assert run.counters["failed"] == 1
    assert run.counters["skipped"] == 0

    # Les deux invariants de conservation bouclent (revérifiés par write_run/read_run).
    c = run.counters
    assert c["found_stac"] == c["skipped_scene_cloud"] + c["off_tile"] + c["found_tile"]
    assert c["found_tile"] == (
        c["ingested"]
        + c["rejected_clouds"]
        + c["rejected_invalid"]
        + c["rejected_nodata"]
        + c["failed"]
        + c["skipped"]
    )

    # exit code décision d'ancrage n°10 : échec non-réseau ? Ici l'échec EST réseau
    # (RasterioIOError, sous-classe d'OSError) mais 4 autres items ont abouti -> pas
    # d'exit 3 (couvert côté CLI par test_cli_ingest.py — ici on vérifie juste le flag).
    assert outcome.all_failures_network is True  # seul échec constaté est réseau


# ── O2 : run double, témoins positif ET négatif ──────────────────────────────────────


def test_o2_run_double_temoins_positif_et_negatif(tmp_path: Path) -> None:
    """1er run : assets_read > 0. 2e run (même grid_hash) : assets_read == 0, skipped ==
    N, content_hashes identiques (le hash porte le contenu décodé, jamais les octets)."""
    items = [_make_clear(tmp_path, "ITEM_A"), _make_clear(tmp_path, "ITEM_B")]
    envelope = _envelope("T01", items, off_tile=0, skipped_scene_cloud=0)
    data_root = tmp_path / "data"

    run_ids = iter(["run-1", "run-2"])
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(ingestion_module, "_new_run_id", lambda: next(run_ids))
    try:
        outcome_1 = ingest_from_envelope(
            envelope=envelope, grid=_GRID, settings=_SETTINGS, data_root=data_root
        )
        hashes_1 = {m.item_id: m.content_hashes for m in list_for_site(data_root, "T01")}

        outcome_2 = ingest_from_envelope(
            envelope=envelope, grid=_GRID, settings=_SETTINGS, data_root=data_root
        )
        hashes_2 = {m.item_id: m.content_hashes for m in list_for_site(data_root, "T01")}
    finally:
        monkeypatch.undo()

    assert outcome_1.run.assets_read > 0  # témoin positif
    assert outcome_2.run.assets_read == 0  # témoin négatif
    assert outcome_2.run.counters["skipped"] == 2
    assert outcome_2.run.counters["ingested"] == 0
    assert hashes_1 == hashes_2


# ── O3 : grid_hash changé -> ré-ingestion ────────────────────────────────────────────


def test_o3_grid_hash_change_reingere_avec_nouveau_transform(tmp_path: Path) -> None:
    """Grille mutée (nouvelle origine) entre deux runs -> le 2e run RÉ-ingère l'item
    (n'est PAS compté "skipped"), avec le transform correct de la NOUVELLE grille."""
    item_id = "ITEM_MOVED"
    items = [_make_clear(tmp_path, item_id)]
    envelope = _envelope("T01", items, off_tile=0, skipped_scene_cloud=0)
    data_root = tmp_path / "data"

    outcome_1 = ingest_from_envelope(
        envelope=envelope, grid=_GRID, settings=_SETTINGS, data_root=data_root
    )
    assert outcome_1.run.counters["ingested"] == 1

    moved_grid = Grid(epsg=_GRID.epsg, origin_x=_GRID.origin_x + 60, origin_y=_GRID.origin_y)
    # L'item doit rester superposable à la NOUVELLE grille : réécrit avec le nouveau transform.
    assets = _write_bands(
        tmp_path, item_id + "_v2", grid=moved_grid, settings=_SETTINGS, band_value=_BAND_VALUE
    )
    assets["scl"] = _write_scl(
        tmp_path, item_id + "_v2", grid=moved_grid, settings=_SETTINGS, scl_value=_VEGETATION
    )
    moved_acq = Acquisition(
        item_id=item_id,
        datetime="2026-01-01T10:00:00Z",
        platform="sentinel-2a",
        tile="31TCJ",
        sequence="0",
        scene_cloud_cover=0.0,
        nodata_pixel_pct=0.0,
        processing_baseline="99.9",
        boa_offset_applied=True,
        proj_epsg=moved_grid.epsg,
        assets=assets,
        radiometry=dict.fromkeys(assets),
    )
    envelope_2 = _envelope("T01", [moved_acq], off_tile=0, skipped_scene_cloud=0)

    outcome_2 = ingest_from_envelope(
        envelope=envelope_2, grid=moved_grid, settings=_SETTINGS, data_root=data_root
    )

    assert outcome_2.run.counters["skipped"] == 0
    assert outcome_2.run.counters["ingested"] == 1
    manifest = read_manifest(data_root, "T01", item_id)
    assert manifest.grid_hash == grid_hash(moved_grid, _SETTINGS)
    assert manifest.grid_hash != grid_hash(_GRID, _SETTINGS)
    with rasterio.open(data_root / "T01" / item_id / "chip.tif") as dst:
        assert tuple(dst.transform)[:6] == tuple(transform_for(moved_grid, 10))[:6]


# ── O4 : sequence=1 même date que le "_0" -> 2 répertoires distincts ────────────────


def test_o4_sequence_1_meme_date_repertoires_distincts(tmp_path: Path) -> None:
    """item_id différent par la séquence -> 2 répertoires, aucun écrasement."""
    acq_0 = _make_clear(tmp_path, "S2A_31TCJ_20260101_0_L2A")
    acq_1 = _make_clear(tmp_path, "S2A_31TCJ_20260101_1_L2A")
    envelope = _envelope("T01", [acq_0, acq_1], off_tile=0, skipped_scene_cloud=0)
    data_root = tmp_path / "data"

    outcome = ingest_from_envelope(
        envelope=envelope, grid=_GRID, settings=_SETTINGS, data_root=data_root
    )

    assert outcome.run.counters["ingested"] == 2
    dir_0 = data_root / "T01" / "S2A_31TCJ_20260101_0_L2A"
    dir_1 = data_root / "T01" / "S2A_31TCJ_20260101_1_L2A"
    assert dir_0.exists() and dir_1.exists()
    assert dir_0 != dir_1
    assert (dir_0 / "chip.tif").exists()
    assert (dir_1 / "chip.tif").exists()


# ── O5 : échec injecté sur 1 item / N ────────────────────────────────────────────────


def test_o5_echec_injecte_sur_un_item_les_autres_traites(tmp_path: Path) -> None:
    """1 item sur 3 échoue (hrefs inexistants) -> manifeste failed+cause, les 2 autres
    traités normalement."""
    items = [
        _make_clear(tmp_path, "ITEM_OK1"),
        _make_failing("ITEM_KO"),
        _make_clear(tmp_path, "ITEM_OK2"),
    ]
    envelope = _envelope("T01", items, off_tile=0, skipped_scene_cloud=0)
    data_root = tmp_path / "data"

    outcome = ingest_from_envelope(
        envelope=envelope, grid=_GRID, settings=_SETTINGS, data_root=data_root
    )

    assert outcome.run.counters["failed"] == 1
    assert outcome.run.counters["ingested"] == 2
    assert read_manifest(data_root, "T01", "ITEM_KO").status == "failed"
    assert read_manifest(data_root, "T01", "ITEM_KO").cause
    assert read_manifest(data_root, "T01", "ITEM_OK1").status == "ingested"
    assert read_manifest(data_root, "T01", "ITEM_OK2").status == "ingested"


# ── O5bis : garde nodata ──────────────────────────────────────────────────────────────


def test_o5bis_garde_nodata_trente_sept_virgule_cinq_pour_cent_rejette_et_supprime_fichiers(
    tmp_path: Path,
) -> None:
    """37,5 % de nodata sur le chip (6/16 pixels, chip 4×4) -> rejected_nodata,
    chip_nodata_pct au manifeste, AUCUN fichier laissé sur disque."""
    item = _make_nodata(tmp_path, "ITEM_NOD", nodata_fraction=0.375)
    envelope = _envelope("T01", [item], off_tile=0, skipped_scene_cloud=0)
    data_root = tmp_path / "data"

    outcome = ingest_from_envelope(
        envelope=envelope, grid=_GRID, settings=_SETTINGS, data_root=data_root
    )

    assert outcome.run.counters["rejected_nodata"] == 1
    manifest = read_manifest(data_root, "T01", "ITEM_NOD")
    assert manifest.status == "rejected_nodata"
    assert manifest.chip_nodata_pct == pytest.approx(37.5)
    item_dir = data_root / "T01" / "ITEM_NOD"
    assert not (item_dir / "chip.tif").exists()
    assert not (item_dir / "chip_20m.tif").exists()
    assert not (item_dir / "scl.tif").exists()


def test_o5bis_garde_nodata_zero_virgule_cinq_pour_cent_ingere(tmp_path: Path) -> None:
    """0,5 % de nodata -> reste sous le seuil par défaut (1 %) -> ingested.

    Grille 20×20 dédiée (au lieu de 4×4) : la granularité de ``_SETTINGS`` (16 pixels) ne
    permet pas d'exprimer 0,5 % (1 pixel = 6,25 %) — 400 pixels le permettent (2/400).
    """
    fine_settings = Settings(
        stac_url=_SETTINGS.stac_url,
        stac_collection=_SETTINGS.stac_collection,
        chip_px_10m=20,
        chip_px_20m=10,
        http_retries=_SETTINGS.http_retries,
        http_backoff_s=_SETTINGS.http_backoff_s,
    )
    item = _make_nodata_with_settings(
        tmp_path, "ITEM_OK_NOD", settings=fine_settings, nodata_fraction=0.005
    )
    envelope = _envelope("T01", [item], off_tile=0, skipped_scene_cloud=0)
    data_root = tmp_path / "data"

    outcome = ingest_from_envelope(
        envelope=envelope, grid=_GRID, settings=fine_settings, data_root=data_root
    )

    assert outcome.run.counters["ingested"] == 1
    manifest = read_manifest(data_root, "T01", "ITEM_OK_NOD")
    assert manifest.status == "ingested"
    assert manifest.chip_nodata_pct == pytest.approx(0.5)
    assert (data_root / "T01" / "ITEM_OK_NOD" / "chip.tif").exists()


# ── O5ter : règle de repli tuile ──────────────────────────────────────────────────────


def test_o5ter_tile_suspect_au_dela_de_vingt_pour_cent(tmp_path: Path) -> None:
    """2 items rejected_nodata sur 5 (40 % > 20 %, dénominateur found_tile) ->
    tile_suspect=true. Le CLI signale et s'arrête là — aucune bascule ici."""
    items = [
        _make_clear(tmp_path, "ITEM_C1"),
        _make_clear(tmp_path, "ITEM_C2"),
        _make_clear(tmp_path, "ITEM_C3"),
        _make_nodata(tmp_path, "ITEM_N1", nodata_fraction=0.4),
        _make_nodata(tmp_path, "ITEM_N2", nodata_fraction=0.4),
    ]
    envelope = _envelope("T01", items, off_tile=0, skipped_scene_cloud=0)
    data_root = tmp_path / "data"

    outcome = ingest_from_envelope(
        envelope=envelope, grid=_GRID, settings=_SETTINGS, data_root=data_root
    )

    assert outcome.run.counters["rejected_nodata"] == 2
    assert outcome.run.counters["found_tile"] == 5
    assert outcome.run.tile_suspect is True


def test_o5ter_tile_pas_suspecte_a_vingt_pour_cent_pile(tmp_path: Path) -> None:
    """1 item rejected_nodata sur 5 (20 % pile, seuil STRICT ">") -> tile_suspect=false."""
    items = [
        _make_clear(tmp_path, "ITEM_C1"),
        _make_clear(tmp_path, "ITEM_C2"),
        _make_clear(tmp_path, "ITEM_C3"),
        _make_clear(tmp_path, "ITEM_C4"),
        _make_nodata(tmp_path, "ITEM_N1", nodata_fraction=0.4),
    ]
    envelope = _envelope("T01", items, off_tile=0, skipped_scene_cloud=0)
    data_root = tmp_path / "data"

    outcome = ingest_from_envelope(
        envelope=envelope, grid=_GRID, settings=_SETTINGS, data_root=data_root
    )

    assert outcome.run.counters["rejected_nodata"] == 1
    assert outcome.run.tile_suspect is False
