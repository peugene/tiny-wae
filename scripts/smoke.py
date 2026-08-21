#!/usr/bin/env python3
"""smoke.py — le pipeline RÉEL sur un périmètre minuscule (gate `just smoke`, l0-03.4).

⭐ Smoke MINIMAL (ajout PO du 21/08 — le gate était creux) : exécute `ingest` de bout en
bout via `adapters/ingestion.ingest_from_source`, sur un double EN MÉMOIRE du port
`StacSource` + un raster synthétique écrit par CE script (aucun réseau, aucune fixture
externe) — le smoke complet (corpus réel, 2 modes, garde de contrat) vient en l0-03.7 et
remplacera celui-ci.

Structuré en fonctions (décision d'ancrage n°2 de la fiche) pour que
`tests/test_smoke.py` importe ce fichier par chemin
(`importlib.util.spec_from_file_location`, `mypy` ne couvre PAS `scripts/` —
`pyproject.toml` : `files = ["src"]`) et exerce le témoin négatif de l'oracle O7 (un
double du port qui ne rend rien -> smoke ROUGE) sans dupliquer la logique.

Écrit ses sorties dans un `tempfile.TemporaryDirectory()` — JAMAIS dans `./data`.
"""

from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import rasterio

from tiny_wae.adapters.ingestion import ingest_from_source
from tiny_wae.adapters.manifests import read_manifest
from tiny_wae.adapters.stac import StacSource
from tiny_wae.core.acquisition import Acquisition
from tiny_wae.core.envelope import Envelope
from tiny_wae.core.geometry import transform_for
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Grid, Site
from tiny_wae.core.windows import Window

# Identité et grille synthétiques (aucun rapport avec un vrai site de config/sites.yaml —
# le smoke minimal n'ouvre jamais sites.yaml/settings.yaml, il construit ses réglages).
SITE_ID = "SMOKE"
ITEM_ID = "S2A_SMOKE_20260101_0_L2A"
_GRID = Grid(epsg=32631, origin_x=699960.0, origin_y=4900020.0)

# Valeur de pixel non nulle sur les 4 bandes 10 m -> chip_nodata_pct == 0 (largement sous
# le seuil par défaut) ; classe SCL 4 (végétation) -> hors classes invalides {0,1} et
# nuageuses {3,8,9,10} -> verdict "ingested".
_BAND_VALUE = 500
_SCL_VEGETATION = 4


def _settings() -> Settings:
    """Réglages du smoke — chips minuscules (20×20 / 10×10) pour rester rapide."""
    return Settings(
        stac_url="https://example.invalid/stac",  # jamais résolu : source en mémoire.
        stac_collection="sentinel-2-l2a",
        chip_px_10m=20,
        chip_px_20m=10,
    )


def _site() -> Site:
    """Site synthétique, grille déjà posée (le smoke ne dépend d'aucun `survey-tiles`)."""
    return Site(
        id=SITE_ID,
        name="Smoke synthétique",
        lat=0.0,
        lon=0.0,
        category="stable-watch",
        note="site fabriqué par scripts/smoke.py — jamais dans sites.yaml",
        reference_tile="31TCJ",
        grid=_GRID,
    )


def _write_synthetic_raster(
    path: Path, *, settings: Settings, resolution: int, value: int, dtype: type
) -> None:
    """Écrit un GeoTIFF 1 bande, constant, exactement sur l'emprise du chip synthétique."""
    size = settings.chip_px_10m if resolution == 10 else settings.chip_px_20m
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


def _write_synthetic_assets(raw_dir: Path, settings: Settings) -> dict[str, str]:
    """Écrit les 11 rasters source (4 bandes 10 m + 6 bandes 20 m + SCL) sous `raw_dir` et
    rend le mapping clé d'asset -> chemin (forme "chemin nu", acceptée par la garde réseau
    de `adapters/chips.py` même sous `TINY_WAE_OFFLINE=1`)."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    assets: dict[str, str] = {}
    for key in ("blue", "green", "red", "nir"):
        path = raw_dir / f"{key}.tif"
        _write_synthetic_raster(
            path, settings=settings, resolution=10, value=_BAND_VALUE, dtype=np.uint16
        )
        assets[key] = str(path)
    for key in ("rededge1", "rededge2", "rededge3", "nir08", "swir16", "swir22"):
        path = raw_dir / f"{key}.tif"
        _write_synthetic_raster(
            path, settings=settings, resolution=20, value=_BAND_VALUE, dtype=np.uint16
        )
        assets[key] = str(path)
    path = raw_dir / "scl.tif"
    _write_synthetic_raster(
        path, settings=settings, resolution=20, value=_SCL_VEGETATION, dtype=np.uint8
    )
    assets["scl"] = str(path)
    return assets


def _make_acquisition(assets: dict[str, str]) -> Acquisition:
    """Item synthétique unique — un seul item S2 L2A "clair" à ingérer."""
    return Acquisition(
        item_id=ITEM_ID,
        datetime="2026-01-01T10:00:00Z",
        platform="sentinel-2a",
        tile="31TCJ",
        sequence="0",
        scene_cloud_cover=0.0,
        nodata_pixel_pct=0.0,
        processing_baseline="99.9",
        boa_offset_applied=True,
        proj_epsg=_GRID.epsg,  # type: ignore[arg-type] — _GRID.epsg toujours posé ici.
        assets=assets,
        radiometry=dict.fromkeys(assets),
    )


@dataclass(frozen=True, slots=True)
class _InMemorySource:
    """Double EN MÉMOIRE du port ``StacSource`` — rejoue une enveloppe déjà construite,
    sans jamais toucher au réseau ni à `pystac-client`."""

    envelope: Envelope

    def search(self, site: Site, window: Window) -> Envelope:
        """Rend l'enveloppe fabriquée par ``build_fake_source``, quels que soient
        ``site``/``window`` (le smoke n'exerce pas le filtrage STAC lui-même — l0-02.1/2
        le couvrent déjà)."""
        return self.envelope


def build_fake_source(raw_dir: Path, *, with_item: bool = True) -> StacSource:
    """Fabrique le double en mémoire du port ``StacSource``.

    ``with_item=False`` construit une enveloppe VIDE (0 item) — c'est le témoin négatif de
    l'oracle O7 : un double du port qui ne rend rien doit faire échouer ``run_smoke``
    (``assets_read`` reste à 0). ``with_item=True`` (défaut) écrit le raster synthétique
    sous ``raw_dir`` et construit l'enveloppe à un seul item, prête à être ingérée.
    """
    settings = _settings()
    if not with_item:
        envelope = Envelope(
            schema_version=1,
            site_id=SITE_ID,
            window={"start": "2026-01-01T00:00:00", "end": "2026-01-02T00:00:00"},
            counters={
                "found_stac": 0,
                "skipped_scene_cloud": 0,
                "off_tile": 0,
                "found_tile": 0,
            },
            items=[],
        )
        return _InMemorySource(envelope=envelope)

    assets = _write_synthetic_assets(raw_dir, settings)
    acquisition = _make_acquisition(assets)
    envelope = Envelope(
        schema_version=1,
        site_id=SITE_ID,
        window={"start": "2026-01-01T00:00:00", "end": "2026-01-02T00:00:00"},
        counters={"found_stac": 1, "skipped_scene_cloud": 0, "off_tile": 0, "found_tile": 1},
        items=[acquisition],
    )
    return _InMemorySource(envelope=envelope)


def run_smoke(dest: Path, source: StacSource) -> None:
    """Exécute `ingest` de bout en bout sur `source` (le pipeline réel, `data_root` sous
    `dest`) et asserte le résultat minimal de l'oracle O7 : 3 fichiers produits, manifeste
    conforme (`status == "ingested"`), `assets_read > 0`.

    Lève ``AssertionError`` (message explicite) si l'un des trois ne tient pas — c'est ce
    qui fait passer le smoke ROUGE, y compris pour le témoin négatif (`with_item=False`).
    """
    settings = _settings()
    site = _site()
    data_root = dest / "data"
    window = Window(start=datetime(2026, 1, 1), end=datetime(2026, 1, 2))  # ignoré par le double.

    outcome = ingest_from_source(
        site=site, window=window, source=source, settings=settings, data_root=data_root
    )

    assert outcome.run.assets_read > 0, (
        f"assets_read={outcome.run.assets_read} attendu > 0 (le pipeline n'a rien lu)"
    )

    item_dir = data_root / SITE_ID / ITEM_ID
    for filename in ("chip.tif", "chip_20m.tif", "scl.tif"):
        assert (item_dir / filename).exists(), f"fichier manquant : {item_dir / filename}"

    manifest = read_manifest(data_root, SITE_ID, ITEM_ID)
    assert manifest.status == "ingested", f"status={manifest.status!r} attendu 'ingested'"


def main() -> None:
    """Point d'entrée `just smoke` : source à un item, dans un répertoire jetable."""
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)
        source = build_fake_source(dest / "raw")
        try:
            run_smoke(dest, source)
        except AssertionError as exc:
            print(f"smoke: ROUGE — {exc}", file=sys.stderr)
            sys.exit(1)
    print(
        "smoke: vert — ingest bout en bout (double en mémoire, 1 item, 3 fichiers, assets_read > 0)"
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
