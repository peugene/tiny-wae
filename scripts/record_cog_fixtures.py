#!/usr/bin/env python3
"""record_cog_fixtures.py — enregistrement RÉSEAU du corpus COG local (l0-03.5).

Script RÉSEAU, LENT (~14 items x 11 assets = ~154 lectures fenêtrées via GDAL, compte
plusieurs minutes) et JETABLE : il tourne HORS du gate (``just script
record_cog_fixtures``), jamais sous pytest. Il écrit deux choses INDISSOCIABLES (les
hrefs des rasters viennent des items) :

1. les enveloppes STAC brutes (``tests/fixtures/stac/cog_<site_id>.json``, format
   ``{"items": [<item brut>]}``, identique à ``record_stac_fixtures.py``) ;
2. les GeoTIFF clippés correspondants (``tests/fixtures/cog/<item_id>/<asset_key>.tif``,
   un par (item, clé d'asset mappée), fenêtrés sur l'emprise du chip du site, compressés
   DEFLATE).

⭐ **Collision de noms résolue (décision d'ancrage n°1 de la fiche l0-03.5)** : la fiche
demandait ``scripts/record_fixtures.py``, mais ce nom serait indistinguable de
``scripts/record_stac_fixtures.py`` (l0-02.1, 5 fixtures d'items bruts, tests déjà verts —
NE JAMAIS LE MODIFIER). D'où ``record_cog_fixtures.py``.

⚠ **Adressage par ID et par fenêtre ABSOLUE (verrou V1, repris de record_stac_fixtures.py)**
: aucune fenêtre n'est dérivée de ``now()`` — deux des items gelés (nuageux 15/03/2023,
S2C 13/05/2026) sortiraient d'une fenêtre glissante 48 mois, rendant le script non
rejouable après ces dates.

Corpus visé (décision d'ancrage n°5) : ≥ 14 items sur 2 sites —
    - **A01** (ITER Cadarache, tuile 31TGJ) : les 3 items GELÉS du chapeau l0-02 (clair,
      nuageux, schéma S2C) + l'item ``sequence=1`` + la fenêtre A01 x septembre 2022
      (mesurée à 6 items par l0-04.1) ;
    - **B09** (Autoroute A69, tuile 31TDJ, mono-tuile) : ≥ 3 items sur une fenêtre large.

Codes de sortie (``cli.exit_codes``, réutilisés) : 0 OK · 3 réseau injoignable ou item
gelé introuvable (aucune fixture inventée pour compenser — un corpus fabriqué rendrait
verts des tests qui ne prouvent rien).
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import rasterio
from affine import Affine
from pystac_client import Client
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.windows import from_bounds

from tiny_wae.adapters.config_io import (
    DEFAULT_SETTINGS_PATH,
    DEFAULT_SITES_PATH,
    load_settings,
    load_sites,
)
from tiny_wae.cli import exit_codes
from tiny_wae.core.bands import BAND_ORDER_10M, BAND_ORDER_20M
from tiny_wae.core.geometry import chip_bounds, transform_for
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Grid, Site
from tiny_wae.core.tiles import wgs84_survey_bbox

STAC_FIXTURES_DIR = Path("tests/fixtures/stac")
COG_FIXTURES_DIR = Path("tests/fixtures/cog")

# Les 3 items GELÉS du chapeau l0-02 (site A01, tuile 31TGJ) + l'item séquence 1.
_A01_FROZEN_IDS = [
    "S2A_31TGJ_20240801_0_L2A",  # clair (cc < 2 %, milieu de fenêtre)
    "S2B_31TGJ_20230315_0_L2A",  # très nuageux (cc 88,3 %, cirrus 82,7)
    "S2C_31TGJ_20260513_0_L2A",  # robustesse S2C (nouveau schéma d'assets)
    "S2A_31TGJ_20260813_1_L2A",  # sequence=1
]

# Fenêtre A01 mesurée par l0-04.1 (found_stac=6, mono-tuile, aucun rejet cloud/tuile).
_A01_WINDOW_START = "2022-09-01T00:00:00Z"
_A01_WINDOW_END = "2022-10-01T00:00:00Z"

# Fenêtre B09 (mono-tuile 31TDJ) — large pour ne pas dépendre d'une date précise mesurée
# à l'avance ; ``_B09_LIMIT`` borne le nombre d'items réellement enregistrés (le budget
# du corpus, décision d'ancrage n°6, ne tolère pas une revisite S2A/S2B à 5 jours sur
# 3 mois — mesuré : 38 items pour cette fenêtre avant plafonnement).
_B09_WINDOW_START = "2023-06-01T00:00:00Z"
_B09_WINDOW_END = "2023-09-01T00:00:00Z"
_B09_MIN_ITEMS = 3
_B09_LIMIT = 4

# Résolution (m) par clé d'asset — 4 bandes 10 m, 6 bandes 20 m + scl (D-b, chapeau l0-03).
_ASSET_RESOLUTION: dict[str, int] = dict.fromkeys(BAND_ORDER_10M, 10)
_ASSET_RESOLUTION.update(dict.fromkeys(BAND_ORDER_20M, 20))
_ASSET_RESOLUTION["scl"] = 20


class RecordNetworkError(RuntimeError):
    """Amont réseau injoignable, item gelé introuvable, ou corpus sous le seuil attendu."""


def _search_by_ids(client: Client, collection: str, item_ids: list[str]) -> list[dict[str, Any]]:
    """Recherche par ID(s), doublée d'une fenêtre ABSOLUE large (2020-2027) — repris tel
    quel de ``record_stac_fixtures.py`` (même verrou V1)."""
    search = client.search(
        collections=[collection],
        ids=item_ids,
        datetime=("2020-01-01T00:00:00Z", "2027-01-01T00:00:00Z"),
    )
    return [item.to_dict() for item in search.items()]


def _search_by_bbox(
    client: Client,
    collection: str,
    bbox: tuple[float, float, float, float],
    start: str,
    end: str,
    max_items: int = 50,
) -> list[dict[str, Any]]:
    """Recherche par bbox + fenêtre ABSOLUE (bornes RFC3339 littérales, jamais ``now()``).

    ⚠ ``max_items`` plafonne le nombre TOTAL d'items rendus par ``.items()`` — ``limit``
    de ``pystac-client`` ne fixe que la taille de PAGE, pas un plafond (mesuré : une
    première version de ce script, qui ne passait que ``limit``, a enregistré 38 items
    B09 sur une fenêtre censée n'en produire que quelques-uns)."""
    search = client.search(
        collections=[collection], bbox=bbox, datetime=(start, end), max_items=max_items
    )
    return [item.to_dict() for item in search.items()]


def _write_stac_fixture(name: str, items: list[dict[str, Any]]) -> Path:
    """Écrit ``{"items": [...]}`` dans ``STAC_FIXTURES_DIR/name`` (indenté, déterministe) —
    format IDENTIQUE à ``record_stac_fixtures.py`` (décision d'ancrage n°2 : aucun
    ``Envelope.to_dict()`` sérialisé sur disque)."""
    STAC_FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    path = STAC_FIXTURES_DIR / name
    payload = {"items": items}
    fd, tmp_name = tempfile.mkstemp(dir=STAC_FIXTURES_DIR, prefix=f".{name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        tmp_path.replace(path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return path


def _clip_asset(
    href: str,
    out_path: Path,
    *,
    bounds: tuple[float, float, float, float],
    transform: Affine,
    chip_px: int,
    dtype: str,
    crs: CRS,
) -> None:
    """Lit UNE fenêtre GDAL sur ``bounds`` (transform de la source) et écrit un GeoTIFF
    clippé DEFLATE (fixtures, pas une sortie de pipeline — G5 ne porte pas ici, cf.
    décision d'ancrage n°7). ``transform``/``crs`` viennent de la grille du SITE (pas de
    la source) — c'est la grille de sortie qui fait foi, exactement comme
    ``adapters/chips.py::write_chips``."""
    with rasterio.open(href) as src:
        window = from_bounds(*bounds, transform=src.transform)
        array = src.read(
            1, window=window, out_shape=(chip_px, chip_px), resampling=Resampling.nearest
        ).astype(dtype)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        out_path,
        "w",
        driver="GTiff",
        height=chip_px,
        width=chip_px,
        count=1,
        dtype=array.dtype,
        crs=crs,
        transform=transform,
        compress="deflate",
    ) as dst:
        dst.write(array, 1)


def _record_item_cog(item: dict[str, Any], *, grid: Grid, settings: Settings) -> int:
    """Clippe et écrit localement les assets mappés d'UN item — renvoie le nombre
    d'assets effectivement écrits (un item S2C peut ne pas porter toutes les clés)."""
    bounds = chip_bounds(grid, settings)
    crs = CRS.from_epsg(grid.epsg)
    item_id = item["id"]
    written = 0
    for key in settings.asset_keys:
        asset = item.get("assets", {}).get(key)
        if asset is None:
            continue
        href = asset["href"]
        resolution = _ASSET_RESOLUTION[key]
        chip_px = settings.chip_px_10m if resolution == 10 else settings.chip_px_20m
        dtype = "uint8" if key == "scl" else "uint16"
        transform = transform_for(grid, resolution)
        out_path = COG_FIXTURES_DIR / item_id / f"{key}.tif"
        _clip_asset(
            href,
            out_path,
            bounds=bounds,
            transform=transform,
            chip_px=chip_px,
            dtype=dtype,
            crs=crs,
        )
        written += 1
    return written


def _record_site(
    client: Client, settings: Settings, site: Site, raw_items: list[dict[str, Any]]
) -> None:
    """Écrit l'enveloppe STAC brute du site puis clippe le corpus raster de chaque item."""
    _write_stac_fixture(f"cog_{site.id.lower()}.json", raw_items)
    print(
        f"record-cog-fixtures : cog_{site.id.lower()}.json ({len(raw_items)} items)",
        file=sys.stderr,
    )
    for index, item in enumerate(raw_items, start=1):
        started = time.monotonic()
        written = _record_item_cog(item, grid=site.grid, settings=settings)
        elapsed = time.monotonic() - started
        print(
            f"record-cog-fixtures : [{site.id}] {index}/{len(raw_items)} {item['id']} "
            f"({written} assets, {elapsed:.1f}s)",
            file=sys.stderr,
        )


def run() -> int:
    """Enregistre le corpus des 2 sites (A01, B09). Renvoie le code de sortie du processus."""
    settings = load_settings(DEFAULT_SETTINGS_PATH)
    sites = {site.id: site for site in load_sites(DEFAULT_SITES_PATH)}
    a01 = sites["A01"]
    b09 = sites["B09"]

    try:
        client = Client.open(settings.stac_url)

        frozen = _search_by_ids(client, settings.stac_collection, _A01_FROZEN_IDS)
        found_ids = {item["id"] for item in frozen}
        missing = [item_id for item_id in _A01_FROZEN_IDS if item_id not in found_ids]
        if missing:
            raise RecordNetworkError(f"item(s) gelé(s) introuvable(s) sur earth-search : {missing}")

        span_10m = float(settings.chip_px_10m * 10)

        a01_bbox = wgs84_survey_bbox(a01.lat, a01.lon, span_10m)
        a01_window = _search_by_bbox(
            client,
            settings.stac_collection,
            a01_bbox,
            _A01_WINDOW_START,
            _A01_WINDOW_END,
            max_items=10,
        )

        # Déduplique par id (la fenêtre A01 x sept. 2022 ne recoupe pas les items gelés
        # 2023/2024/2026, mais on protège l'invariant "un item, un dossier" quoi qu'il
        # arrive si earth-search venait à re-servir un id).
        by_id: dict[str, dict[str, Any]] = {item["id"]: item for item in frozen}
        for item in a01_window:
            by_id.setdefault(item["id"], item)
        a01_items = list(by_id.values())

        b09_bbox = wgs84_survey_bbox(b09.lat, b09.lon, span_10m)
        b09_items = _search_by_bbox(
            client,
            settings.stac_collection,
            b09_bbox,
            _B09_WINDOW_START,
            _B09_WINDOW_END,
            max_items=_B09_LIMIT,
        )
        if len(b09_items) < _B09_MIN_ITEMS:
            raise RecordNetworkError(
                f"B09 : {len(b09_items)} item(s) trouvé(s), {_B09_MIN_ITEMS} attendus au minimum"
            )

        total = len(a01_items) + len(b09_items)
        print(
            f"record-cog-fixtures : corpus = {len(a01_items)} items (A01) + "
            f"{len(b09_items)} items (B09) = {total}",
            file=sys.stderr,
        )

        _record_site(client, settings, a01, a01_items)
        _record_site(client, settings, b09, b09_items)

    except RecordNetworkError as exc:
        print(f"record-cog-fixtures : {exc}", file=sys.stderr)
        return exit_codes.INCONCLUSIVE
    except Exception as exc:  # amont injoignable, timeout, etc. — non concluant, pas un bug.
        print(f"record-cog-fixtures : réseau injoignable : {exc}", file=sys.stderr)
        return exit_codes.INCONCLUSIVE

    print(f"record-cog-fixtures : corpus écrit sous {COG_FIXTURES_DIR}", file=sys.stderr)
    return exit_codes.OK


def main() -> None:
    """Point d'entrée : aucun argument (le corpus est fixe, cf. décision d'ancrage n°5)."""
    sys.exit(run())


if __name__ == "__main__":
    main()
