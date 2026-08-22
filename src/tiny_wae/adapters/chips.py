"""adapters/chips.py — lecture COG fenêtrée + écriture chip.tif/chip_20m.tif/scl.tif (l0-03.3).

Seul point du projet qui ouvre un raster (STAC ou fixture) : c'est ici, et nulle part
ailleurs, que vit la garde réseau de contrat (décision E-b) — la placer dans
``FixtureSource`` seul serait contournable, et ``pytest-socket`` ne couvre pas les
lectures GDAL (C/libcurl).

Pas de CLI ici (l0-03.4), pas de manifeste ni de verdict SCL (l0-03.4 assemble) : ce
module expose des fonctions pures côté résultat (aucun état de module mutable — décision
d'ancrage n°2, l0-04.1 fera tourner plusieurs ingestions dans un pool de workers).
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.windows import from_bounds

from tiny_wae.core.acquisition import Acquisition
from tiny_wae.core.artifacts import CHIP_10M_FILENAME, CHIP_20M_FILENAME, SCL_FILENAME
from tiny_wae.core.bands import BAND_ORDER_10M, BAND_ORDER_20M
from tiny_wae.core.geometry import chip_bounds, transform_for
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Grid

# Valeur nodata conventionnelle des assets S2 L2A (cf. chapeau l0-03).
NODATA_VALUE = 0

# Nom EXACT de la variable d'environnement (décision d'ancrage n°5) — aucune variante.
OFFLINE_ENV_VAR = "TINY_WAE_OFFLINE"


class EpsgMismatchError(ValueError):
    """``Acquisition.proj_epsg`` != ``Grid.epsg`` — chip non superposable à la grille du site."""


class RemoteAccessForbidden(ValueError):
    """Sous ``TINY_WAE_OFFLINE=1``, href refusé (schéma ni ``file://`` ni chemin nu).

    Levée AVANT toute ouverture de raster — aucune requête n'est jamais émise, pas même
    une sonde.
    """


@dataclass(frozen=True, slots=True)
class ChipResult:
    """Résultat de ``write_chips`` — contrat repris tel quel par ``Manifest`` (l0-03.4).

    Noms alignés sur ``adapters.manifests.Manifest`` pour que l0-03.4 recopie sans
    traduire.
    """

    files: list[str]
    assets_read: int
    content_hashes: dict[str, str]
    bytes_written: int
    chip_nodata_pct: float


def _is_offline() -> bool:
    """Vrai si la garde réseau de contrat est active (``TINY_WAE_OFFLINE`` vaut ``"1"``)."""
    return os.environ.get(OFFLINE_ENV_VAR) == "1"


def _guard_href(href: str) -> None:
    """Sous ``TINY_WAE_OFFLINE=1``, refuse tout href dont le schéma n'est pas accepté.

    Schémas acceptés (décision d'ancrage n°5) : ``file://`` et un chemin nu sans schéma
    (forme des fixtures locales de l0-03.5, que rasterio ouvre telles quelles). Refusés :
    ``http://``, ``https://``, ``s3://`` et tout autre schéma. Hors ``TINY_WAE_OFFLINE=1``,
    ne fait rien (l'ouverture réseau est tentée normalement).
    """
    if not _is_offline():
        return
    if href.startswith("file://"):
        return
    if "://" not in href:
        return
    raise RemoteAccessForbidden(
        f"TINY_WAE_OFFLINE=1 : href {href!r} refusé (schéma ni file:// ni chemin nu)"
    )


def check_epsg(acq: Acquisition, grid: Grid) -> None:
    """Garde epsg (ordre invariant du chapeau, en tête de toute ingestion d'item).

    Lève ``EpsgMismatchError`` si ``acq.proj_epsg`` != ``grid.epsg`` (y compris si
    ``grid.epsg`` est ``None`` — grille non calculée) : un chip lu sous cette
    projection ne serait pas superposable à la grille du site.
    """
    if grid.epsg is None or acq.proj_epsg != grid.epsg:
        raise EpsgMismatchError(
            f"acq.proj_epsg={acq.proj_epsg} != grid.epsg={grid.epsg} — item non "
            "superposable à la grille du site"
        )


def _read_window(
    href: str, bounds: tuple[float, float, float, float], out_shape: tuple[int, int]
) -> np.ndarray:
    """Lit UNE fenêtre rasterio dérivée de ``bounds`` sur le transform de la source.

    La garde réseau (``_guard_href``) est appliquée avant toute ouverture. Le
    rééchantillonnage (``Resampling.nearest``) n'intervient que si la fenêtre calculée ne
    correspond pas exactement à ``out_shape`` (cas normal : fenêtre entière, pas de
    rééchantillonnage réel).
    """
    _guard_href(href)
    with rasterio.open(href) as src:
        window = from_bounds(*bounds, transform=src.transform)
        array: np.ndarray = src.read(
            1, window=window, out_shape=out_shape, resampling=Resampling.nearest
        )
        return array


def read_scl(acq: Acquisition, grid: Grid, settings: Settings) -> tuple[np.ndarray, int]:
    """Lit la fenêtre SCL (256×256 par défaut) dans la projection de la grille du site.

    Retourne ``(array, assets_read)`` — le compteur d'ouvertures remonte PAR VALEUR
    (décision d'ancrage n°2), jamais par un état de module. Le comptage des classes SCL
    et le verdict restent hors périmètre (décision d'ancrage n°3, l0-03.4).
    """
    bounds = chip_bounds(grid, settings)
    out_shape = (settings.chip_px_20m, settings.chip_px_20m)
    array = _read_window(acq.assets["scl"], bounds, out_shape)
    return array, 1


def read_bands_10m(acq: Acquisition, grid: Grid, settings: Settings) -> tuple[np.ndarray, int]:
    """Lit les 4 bandes 10 m, empilées dans l'ordre gravé ``BAND_ORDER_10M``.

    Retourne ``(array, assets_read)`` avec ``array`` de forme
    ``(4, chip_px_10m, chip_px_10m)`` — une ouverture par bande.
    """
    bounds = chip_bounds(grid, settings)
    out_shape = (settings.chip_px_10m, settings.chip_px_10m)
    bands = [_read_window(acq.assets[key], bounds, out_shape) for key in BAND_ORDER_10M]
    return np.stack(bands, axis=0), len(BAND_ORDER_10M)


def read_bands_20m(acq: Acquisition, grid: Grid, settings: Settings) -> tuple[np.ndarray, int]:
    """Lit les 6 bandes 20 m, empilées dans l'ordre gravé ``BAND_ORDER_20M`` (D-b).

    Retourne ``(array, assets_read)`` avec ``array`` de forme
    ``(6, chip_px_20m, chip_px_20m)`` — une ouverture par bande.
    """
    bounds = chip_bounds(grid, settings)
    out_shape = (settings.chip_px_20m, settings.chip_px_20m)
    bands = [_read_window(acq.assets[key], bounds, out_shape) for key in BAND_ORDER_20M]
    return np.stack(bands, axis=0), len(BAND_ORDER_20M)


def _content_hash(array: np.ndarray, grid: Grid, resolution: int) -> str:
    """Hash de contenu décodé (O1bis) : ``sha256(bytes(array) + EPSG + transform + dtype)``.

    JAMAIS les octets du fichier GeoTIFF (le WKT PROJ embarqué dérive entre versions et
    plateformes — décision d'ancrage n°7) : le hash porte sur le tableau numpy et les
    métadonnées géographiques attendues (indépendantes de GDAL/PROJ).
    """
    transform = transform_for(grid, resolution)
    coeffs = ",".join(
        f"{c:.10f}"
        for c in (transform.a, transform.b, transform.c, transform.d, transform.e, transform.f)
    )
    header = f"EPSG:{grid.epsg}|{coeffs}|{array.dtype.str}".encode()
    return hashlib.sha256(array.tobytes() + header).hexdigest()


def _write_geotiff(
    path: Path, array: np.ndarray, *, transform: Affine, crs: CRS, item_id: str, band_order: str
) -> None:
    """Écrit un GeoTIFF simple (PAS COG — G5) : ``array`` de forme ``(bands, H, W)``."""
    count, height, width = array.shape
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=count,
        dtype=array.dtype,
        crs=crs,
        transform=transform,
    ) as dst:
        dst.write(array)
        dst.update_tags(item_id=item_id, band_order=band_order)


def write_chips(
    dest_dir: Path,
    *,
    bands_10m: np.ndarray,
    bands_20m: np.ndarray,
    scl: np.ndarray,
    grid: Grid,
    item_id: str,
    assets_read: int,
) -> ChipResult:
    """Écrit les 3 GeoTIFF de sortie sur la grille du site et calcule le résultat (O1/O1bis/O3).

    ``bands_10m``/``bands_20m`` sont castés en ``uint16`` (convention S2 L2A), ``scl`` en
    ``uint8``. ``assets_read`` est repris tel quel (décision d'ancrage n°2 : cette fonction
    ne compte AUCUNE ouverture, elle assemble le résultat des ``read_*``).

    ``chip_nodata_pct`` (0–100, décision d'ancrage n°4) : fraction de pixels du chip 10 m
    où les 4 bandes valent toutes ``NODATA_VALUE`` (0) — un pixel n'est nodata que si
    aucune bande n'y porte de signal, décision prise ici faute de spécification plus fine
    dans la fiche.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    bands_10m_u16 = bands_10m.astype(np.uint16)
    bands_20m_u16 = bands_20m.astype(np.uint16)
    scl_u8 = scl.astype(np.uint8)

    crs = CRS.from_epsg(grid.epsg)
    transform_10m = transform_for(grid, 10)
    transform_20m = transform_for(grid, 20)

    path_10m = dest_dir / CHIP_10M_FILENAME
    path_20m = dest_dir / CHIP_20M_FILENAME
    path_scl = dest_dir / SCL_FILENAME

    _write_geotiff(
        path_10m,
        bands_10m_u16,
        transform=transform_10m,
        crs=crs,
        item_id=item_id,
        band_order=",".join(BAND_ORDER_10M),
    )
    _write_geotiff(
        path_20m,
        bands_20m_u16,
        transform=transform_20m,
        crs=crs,
        item_id=item_id,
        band_order=",".join(BAND_ORDER_20M),
    )
    _write_geotiff(
        path_scl,
        scl_u8[np.newaxis, :, :],
        transform=transform_20m,
        crs=crs,
        item_id=item_id,
        band_order="scl",
    )

    nodata_mask = np.all(bands_10m_u16 == NODATA_VALUE, axis=0)
    chip_nodata_pct = 100.0 * float(nodata_mask.sum()) / float(nodata_mask.size)

    content_hashes = {
        CHIP_10M_FILENAME: _content_hash(bands_10m_u16, grid, 10),
        CHIP_20M_FILENAME: _content_hash(bands_20m_u16, grid, 20),
        SCL_FILENAME: _content_hash(scl_u8, grid, 20),
    }
    bytes_written = sum(p.stat().st_size for p in (path_10m, path_20m, path_scl))

    return ChipResult(
        files=[CHIP_10M_FILENAME, CHIP_20M_FILENAME, SCL_FILENAME],
        assets_read=assets_read,
        content_hashes=content_hashes,
        bytes_written=bytes_written,
        chip_nodata_pct=chip_nodata_pct,
    )
