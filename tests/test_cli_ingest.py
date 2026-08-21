"""Tests cli/ingest.py (l0-03.4) — 2 formes d'appel, --force, codes de sortie.

Config isolée (sites.yaml/settings.yaml écrits sous ``tmp_path``, `data_root` sous
``tmp_path`` également) : aucun test n'écrit dans ``./data`` ni ne dépend de
``config/sites.yaml`` du dépôt. ``build_source`` (point de couture PROPRE à ce module,
décision d'ancrage n°4) est monkeypatché pour la forme ``--site`` ; la forme
``--acquisitions`` ne l'utilise jamais (l'enveloppe est déjà sur disque).

Couvre :
- les 2 formes d'appel (``--acquisitions`` et ``--site --from --to``) ;
- ``--force`` : ré-ingestion inconditionnelle même à grid_hash identique ;
- grille non calculée -> exit USAGE (2), jamais un item `failed` (décision d'ancrage n°5) ;
- O5 : 1 item sur 3 échoue -> exit FAILURE (1) ;
- O6 : tous les items échouent (origine réseau) -> exit INCONCLUSIVE (3) ;
- endpoint STAC injoignable (StacUnreachable) -> exit INCONCLUSIVE (3), sans qu'aucun item
  ne soit tenté.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from typer.testing import CliRunner

import tiny_wae.adapters.ingestion as ingestion_module
import tiny_wae.cli.ingest as ingest_module
from tiny_wae.__main__ import app
from tiny_wae.adapters.stac import StacSource, StacUnreachable
from tiny_wae.cli import exit_codes
from tiny_wae.core.acquisition import Acquisition
from tiny_wae.core.envelope import Envelope
from tiny_wae.core.geometry import transform_for
from tiny_wae.core.sites import Grid, Site
from tiny_wae.core.windows import Window

runner = CliRunner()

_GRID = Grid(epsg=32631, origin_x=699960.0, origin_y=4900020.0)
_SITE_ID = "T01"
_VEGETATION = 4
_BAND_VALUE = 500
_CHIP_PX_10M = 4
_CHIP_PX_20M = 2


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise l'attente de backoff (règle du dépôt : aucun test ne doit dormir)."""
    monkeypatch.setattr(ingestion_module, "_sleep", lambda seconds: None)


def _write_config(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Écrit sites.yaml + settings.yaml isolés sous tmp_path. Rend (sites, settings, data_root)."""
    data_root = tmp_path / "data"
    sites_path = tmp_path / "sites.yaml"
    settings_path = tmp_path / "settings.yaml"
    sites_path.write_text(
        f"""
sites:
  - id: {_SITE_ID}
    name: "Site de test"
    lat: 43.0
    lon: 5.0
    category: stable-watch
    note: "site isolé de test"
    reference_tile: "31TCJ"
    grid:
      epsg: {_GRID.epsg}
      origin_x: {_GRID.origin_x}
      origin_y: {_GRID.origin_y}
""",
        encoding="utf-8",
    )
    settings_path.write_text(
        f"""
stac_url: "https://example.invalid/stac"
stac_collection: "sentinel-2-l2a"
chip_px_10m: {_CHIP_PX_10M}
chip_px_20m: {_CHIP_PX_20M}
data_root: "{data_root.as_posix()}"
http_retries: 1
http_backoff_s: 1
""",
        encoding="utf-8",
    )
    return sites_path, settings_path, data_root


def _write_config_no_grid(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Variante sans grille posée (epsg absent) — pour le cas d'usage n°5."""
    data_root = tmp_path / "data"
    sites_path = tmp_path / "sites.yaml"
    settings_path = tmp_path / "settings.yaml"
    sites_path.write_text(
        f"""
sites:
  - id: {_SITE_ID}
    name: "Site sans grille"
    lat: 43.0
    lon: 5.0
    category: stable-watch
    note: "grille non calculée"
""",
        encoding="utf-8",
    )
    settings_path.write_text(
        f"""
stac_url: "https://example.invalid/stac"
stac_collection: "sentinel-2-l2a"
data_root: "{data_root.as_posix()}"
""",
        encoding="utf-8",
    )
    return sites_path, settings_path, data_root


def _write_raster(path: Path, *, resolution: int, size: int, value: int, dtype: type) -> None:
    transform = transform_for(_GRID, resolution)
    array = np.full((size, size), value, dtype=dtype)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=size,
        width=size,
        count=1,
        dtype=array.dtype,
        crs=f"EPSG:{_GRID.epsg}",
        transform=transform,
    ) as dst:
        dst.write(array, 1)


def _make_clear_item(tmp_path: Path, item_id: str) -> Acquisition:
    assets: dict[str, str] = {}
    for key in ("blue", "green", "red", "nir"):
        p = tmp_path / f"{item_id}_{key}.tif"
        _write_raster(p, resolution=10, size=_CHIP_PX_10M, value=_BAND_VALUE, dtype=np.uint16)
        assets[key] = str(p)
    for key in ("rededge1", "rededge2", "rededge3", "nir08", "swir16", "swir22"):
        p = tmp_path / f"{item_id}_{key}.tif"
        _write_raster(p, resolution=20, size=_CHIP_PX_20M, value=_BAND_VALUE, dtype=np.uint16)
        assets[key] = str(p)
    p = tmp_path / f"{item_id}_scl.tif"
    _write_raster(p, resolution=20, size=_CHIP_PX_20M, value=_VEGETATION, dtype=np.uint8)
    assets["scl"] = str(p)
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


def _make_failing_item(item_id: str) -> Acquisition:
    """Item dont tous les hrefs sont introuvables -> échec réseau (OSError/RasterioIOError)."""
    keys = (
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
    missing = {key: f"/nonexistent/{item_id}_{key}.tif" for key in keys}
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


def _envelope_payload(items: list[Acquisition]) -> dict[str, object]:
    found_tile = len(items)
    envelope = Envelope(
        schema_version=1,
        site_id=_SITE_ID,
        window={"start": "2026-01-01T00:00:00", "end": "2026-02-01T00:00:00"},
        counters={
            "found_stac": found_tile,
            "skipped_scene_cloud": 0,
            "off_tile": 0,
            "found_tile": found_tile,
        },
        items=items,
    )
    return envelope.to_dict()


class _FakeSource:
    """Double en mémoire du port `StacSource` — rejoue une enveloppe déjà construite."""

    def __init__(self, envelope: Envelope) -> None:
        self._envelope = envelope

    def search(self, site: Site, window: Window) -> Envelope:
        return self._envelope


class _UnreachableSource:
    """Double simulant un endpoint STAC injoignable — jamais un item n'est tenté."""

    def search(self, site: Site, window: Window) -> Envelope:
        raise StacUnreachable(
            "https://example.invalid/stac injoignable : connexion refusée (simulé)"
        )


def _patch_source(monkeypatch: pytest.MonkeyPatch, source: StacSource) -> None:
    monkeypatch.setattr(ingest_module, "build_source", lambda settings: source)


# ── Forme --acquisitions ──────────────────────────────────────────────────────────────


def test_forme_acquisitions_ingere_et_exit_ok(tmp_path: Path) -> None:
    """`ingest --acquisitions <envelope.json>` ingère l'item, exit OK."""
    sites_path, settings_path, data_root = _write_config(tmp_path)
    item = _make_clear_item(tmp_path, "ITEM_A")
    envelope_path = tmp_path / "envelope.json"
    envelope_path.write_text(json.dumps(_envelope_payload([item])), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "ingest",
            "--acquisitions",
            str(envelope_path),
            "--sites-path",
            str(sites_path),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.OK
    assert "ingested=1" in result.stderr
    assert (data_root / _SITE_ID / "ITEM_A" / "chip.tif").exists()


# ── Forme --site --from --to ─────────────────────────────────────────────────────────


def test_forme_site_ingere_et_exit_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`ingest --site --from --to` interroge la source (monkeypatchée) puis ingère."""
    sites_path, settings_path, data_root = _write_config(tmp_path)
    item = _make_clear_item(tmp_path, "ITEM_B")
    envelope = Envelope.from_dict(_envelope_payload([item]))
    _patch_source(monkeypatch, _FakeSource(envelope))

    result = runner.invoke(
        app,
        [
            "ingest",
            "--site",
            _SITE_ID,
            "--from",
            "2026-01-01",
            "--to",
            "2026-02-01",
            "--sites-path",
            str(sites_path),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.OK
    assert "ingested=1" in result.stderr
    assert (data_root / _SITE_ID / "ITEM_B" / "chip.tif").exists()


def test_deux_formes_a_la_fois_usage(tmp_path: Path) -> None:
    """--acquisitions ET --site en même temps -> USAGE (2)."""
    sites_path, settings_path, _ = _write_config(tmp_path)
    result = runner.invoke(
        app,
        [
            "ingest",
            "--acquisitions",
            str(tmp_path / "whatever.json"),
            "--site",
            _SITE_ID,
            "--from",
            "2026-01-01",
            "--to",
            "2026-02-01",
            "--sites-path",
            str(sites_path),
            "--settings-path",
            str(settings_path),
        ],
    )
    assert result.exit_code == exit_codes.USAGE


def test_aucune_forme_usage(tmp_path: Path) -> None:
    """Ni --acquisitions ni --site -> USAGE (2)."""
    sites_path, settings_path, _ = _write_config(tmp_path)
    result = runner.invoke(
        app, ["ingest", "--sites-path", str(sites_path), "--settings-path", str(settings_path)]
    )
    assert result.exit_code == exit_codes.USAGE


# ── --force : ré-ingestion inconditionnelle ──────────────────────────────────────────


def test_force_reingere_meme_grid_hash_identique(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2e run SANS --force -> skipped=1 ; 2e run AVEC --force -> ingested=1 de nouveau."""
    sites_path, settings_path, data_root = _write_config(tmp_path)
    item = _make_clear_item(tmp_path, "ITEM_C")
    envelope = Envelope.from_dict(_envelope_payload([item]))
    _patch_source(monkeypatch, _FakeSource(envelope))

    common_args = [
        "ingest",
        "--site",
        _SITE_ID,
        "--from",
        "2026-01-01",
        "--to",
        "2026-02-01",
        "--sites-path",
        str(sites_path),
        "--settings-path",
        str(settings_path),
    ]

    result_1 = runner.invoke(app, common_args)
    assert result_1.exit_code == exit_codes.OK
    assert "ingested=1" in result_1.stderr

    result_2 = runner.invoke(app, common_args)
    assert result_2.exit_code == exit_codes.OK
    assert "skipped=1" in result_2.stderr
    assert "ingested=0" in result_2.stderr

    result_3 = runner.invoke(app, [*common_args, "--force"])
    assert result_3.exit_code == exit_codes.OK
    assert "ingested=1" in result_3.stderr
    assert "skipped=0" in result_3.stderr


# ── Grille non calculée -> USAGE (décision d'ancrage n°5) ────────────────────────────


def test_grille_non_calculee_usage_jamais_un_item_failed(tmp_path: Path) -> None:
    """site.grid.epsg absent -> exit USAGE (2), message pointant `just survey-tiles` —
    JAMAIS un item `failed` (aucun manifeste écrit)."""
    sites_path, settings_path, data_root = _write_config_no_grid(tmp_path)

    result = runner.invoke(
        app,
        [
            "ingest",
            "--site",
            _SITE_ID,
            "--from",
            "2026-01-01",
            "--to",
            "2026-02-01",
            "--sites-path",
            str(sites_path),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.USAGE
    assert "survey-tiles" in result.stderr
    assert not data_root.exists()


# ── O5 : échec injecté sur 1 item / N -> FAILURE (1) ─────────────────────────────────


def test_o5_un_item_echoue_exit_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """1 item sur 3 échoue (hrefs introuvables), les 2 autres traités -> exit FAILURE (1)."""
    sites_path, settings_path, data_root = _write_config(tmp_path)
    items = [
        _make_clear_item(tmp_path, "ITEM_OK1"),
        _make_failing_item("ITEM_KO"),
        _make_clear_item(tmp_path, "ITEM_OK2"),
    ]
    envelope = Envelope.from_dict(_envelope_payload(items))
    _patch_source(monkeypatch, _FakeSource(envelope))

    result = runner.invoke(
        app,
        [
            "ingest",
            "--site",
            _SITE_ID,
            "--from",
            "2026-01-01",
            "--to",
            "2026-02-01",
            "--sites-path",
            str(sites_path),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.FAILURE
    assert result.exit_code == 1
    assert "failed=1" in result.stderr
    assert "ingested=2" in result.stderr


# ── O6 : tous les items échouent (réseau) -> INCONCLUSIVE (3) ───────────────────────


def test_o6_tous_les_items_echouent_reseau_exit_inconclusive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Amont injoignable simulé : TOUS les items échouent (hrefs introuvables), aucun
    n'aboutit -> exit INCONCLUSIVE (3), distinct du cas O5 qui rend 1."""
    sites_path, settings_path, data_root = _write_config(tmp_path)
    items = [_make_failing_item("ITEM_KO1"), _make_failing_item("ITEM_KO2")]
    envelope = Envelope.from_dict(_envelope_payload(items))
    _patch_source(monkeypatch, _FakeSource(envelope))

    result = runner.invoke(
        app,
        [
            "ingest",
            "--site",
            _SITE_ID,
            "--from",
            "2026-01-01",
            "--to",
            "2026-02-01",
            "--sites-path",
            str(sites_path),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.INCONCLUSIVE
    assert result.exit_code == 3
    assert "failed=2" in result.stderr


def test_endpoint_stac_injoignable_exit_inconclusive_sans_item_tente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`StacUnreachable` levée par la recherche elle-même -> exit INCONCLUSIVE (3), le
    `run.json` n'est même pas écrit (aucun item n'a été tenté)."""
    sites_path, settings_path, data_root = _write_config(tmp_path)
    _patch_source(monkeypatch, _UnreachableSource())

    result = runner.invoke(
        app,
        [
            "ingest",
            "--site",
            _SITE_ID,
            "--from",
            "2026-01-01",
            "--to",
            "2026-02-01",
            "--sites-path",
            str(sites_path),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.INCONCLUSIVE
    assert "injoignable" in result.stderr
    assert not data_root.exists()
