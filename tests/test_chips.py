"""Tests adapters/chips.py (l0-03.3).

Couvre l'oracle de la fiche, sur des rasters SYNTHÉTIQUES écrits par le test (l0-03.5
n'existe pas encore — décision d'ancrage n°8) :
- O1 : chip.tif 512×512×4 uint16, chip_20m.tif 256×256×6 uint16, scl.tif 256×256 uint8 ;
  CRS/transform == grille au bit près ; valeurs pixel == attendues au pixel près (pas
  seulement la forme) ; assets_read == nombre d'ouvertures.
- O1bis : hash de contenu (array + CRS + transform + dtype) stable entre deux exécutions.
- O2 : epsg acquisition != grille -> EpsgMismatchError.
- O2bis : href https:// sous TINY_WAE_OFFLINE=1 -> RemoteAccessForbidden avant ouverture ;
  file:// et chemin nu restent acceptés sous la même variable.
- O3 : fraction nodata du chip 10 m calculée == fraction injectée dans le raster
  synthétique, testée dans les deux sens (0,5 % et 40 %).

Couvre aussi l'oracle de perf-01 (réglages GDAL pour la lecture des COG distants) :
- O1 : les 5 options de D1 sont actives, valeur exacte, au moment de ``rasterio.open``
  dans ``_read_window``, depuis le thread principal.
- O2 : LE MÊME test, mais l'appel est lancé dans un ``ThreadPoolExecutor`` — c'est
  l'oracle qui garde D2 (``rasterio.Env`` thread-local, contexte ouvert DANS
  ``_read_window``, jamais plus haut).
- O3 : ``_guard_href`` s'exécute avant toute ouverture (contexte GDAL inclus) ; sous
  ``TINY_WAE_OFFLINE=1``, un href ``https://`` est refusé avant que le contexte GDAL ou
  ``rasterio.open`` ne soient jamais atteints.
- O4 : chaque option de D1 n'apparaît qu'une fois dans le dépôt, dans
  ``adapters/chips.py``.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS

from tiny_wae.adapters import chips as chips_module
from tiny_wae.adapters.chips import (
    OFFLINE_ENV_VAR,
    EpsgMismatchError,
    RemoteAccessForbidden,
    check_epsg,
    read_bands_10m,
    read_bands_20m,
    read_scl,
    write_chips,
)
from tiny_wae.core.acquisition import Acquisition
from tiny_wae.core.bands import BAND_ORDER_10M, BAND_ORDER_20M
from tiny_wae.core.geometry import transform_for
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Grid

# Grille synthétique littérale : origine multiple de 60 m (tuile S2 32631 réelle) — même
# grille que tests/test_geometry.py.
_GRID = Grid(epsg=32631, origin_x=699960.0, origin_y=4900020.0)

_SETTINGS = Settings(
    stac_url="https://example.test/stac",
    stac_collection="sentinel-2-l2a",
    chip_px_10m=512,
    chip_px_20m=256,
)

# Valeurs de pixel CHOISIES et distinctes par bande — c'est ce qui rend O1 discriminant
# (valeur attendue au pixel près, pas seulement une forme de tableau).
_VALUES_10M = {"blue": 111, "green": 222, "red": 333, "nir": 444}
_VALUES_20M = {
    "rededge1": 1001,
    "rededge2": 1002,
    "rededge3": 1003,
    "nir08": 1004,
    "swir16": 1005,
    "swir22": 1006,
}
_SCL_VALUE = 4


def _write_source(path: Path, *, grid: Grid, resolution: int, size: int, value: int) -> None:
    """Écrit un GeoTIFF source 1 bande, constant, exactement sur l'emprise du chip."""
    transform = transform_for(grid, resolution)
    array = np.full((size, size), value, dtype=np.uint16)
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


def _make_acq(assets: dict[str, str], *, proj_epsg: int = 32631) -> Acquisition:
    """Acquisition synthétique minimale — seuls ``proj_epsg`` et ``assets`` comptent ici."""
    return Acquisition(
        item_id="S2A_TEST_ITEM",
        datetime="2026-01-01T00:00:00Z",
        platform="sentinel-2a",
        tile="31TCJ",
        sequence="0",
        scene_cloud_cover=0.0,
        nodata_pixel_pct=0.0,
        processing_baseline="99.9",
        boa_offset_applied=False,
        proj_epsg=proj_epsg,
        assets=assets,
        radiometry=dict.fromkeys(assets),
    )


@pytest.fixture
def _sources(tmp_path: Path) -> dict[str, str]:
    """Écrit les 11 rasters source (4 bandes 10 m + 6 bandes 20 m + SCL) et rend les hrefs."""
    assets: dict[str, str] = {}
    for key, value in _VALUES_10M.items():
        p = tmp_path / f"{key}.tif"
        _write_source(p, grid=_GRID, resolution=10, size=_SETTINGS.chip_px_10m, value=value)
        assets[key] = str(p)
    for key, value in _VALUES_20M.items():
        p = tmp_path / f"{key}.tif"
        _write_source(p, grid=_GRID, resolution=20, size=_SETTINGS.chip_px_20m, value=value)
        assets[key] = str(p)
    p = tmp_path / "scl.tif"
    _write_source(p, grid=_GRID, resolution=20, size=_SETTINGS.chip_px_20m, value=_SCL_VALUE)
    assets["scl"] = str(p)
    return assets


def test_o1_read_puis_write_valeurs_formes_crs_transform_au_bit_pres(
    tmp_path: Path, _sources: dict[str, str]
) -> None:
    """O1 : lecture + écriture -> formes, dtypes, CRS/transform, valeurs pixel, assets_read."""
    acq = _make_acq(_sources)
    check_epsg(acq, _GRID)  # garde epsg : ne lève pas (32631 == 32631)

    bands_10m, read_10m = read_bands_10m(acq, _GRID, _SETTINGS)
    bands_20m, read_20m = read_bands_20m(acq, _GRID, _SETTINGS)
    scl, read_scl_count = read_scl(acq, _GRID, _SETTINGS)

    assert read_10m == 4
    assert read_20m == 6
    assert read_scl_count == 1
    assert bands_10m.shape == (4, 512, 512)
    assert bands_20m.shape == (6, 256, 256)
    assert scl.shape == (256, 256)

    # valeurs pixel au pixel près, dans l'ordre BAND_ORDER_10M/20M gravé
    for i, key in enumerate(BAND_ORDER_10M):
        assert np.all(bands_10m[i] == _VALUES_10M[key])
    for i, key in enumerate(BAND_ORDER_20M):
        assert np.all(bands_20m[i] == _VALUES_20M[key])
    assert np.all(scl == _SCL_VALUE)

    dest_dir = tmp_path / "out"
    result = write_chips(
        dest_dir,
        bands_10m=bands_10m,
        bands_20m=bands_20m,
        scl=scl,
        grid=_GRID,
        item_id=acq.item_id,
        assets_read=read_10m + read_20m + read_scl_count,
    )

    assert result.assets_read == 11
    assert result.files == ["chip.tif", "chip_20m.tif", "scl.tif"]
    assert result.bytes_written > 0

    with rasterio.open(dest_dir / "chip.tif") as dst:
        assert dst.count == 4
        assert (dst.height, dst.width) == (512, 512)
        assert dst.dtypes == ("uint16",) * 4
        assert dst.crs == CRS.from_epsg(32631)
        assert tuple(dst.transform)[:6] == tuple(transform_for(_GRID, 10))[:6]
        for i, key in enumerate(BAND_ORDER_10M, start=1):
            assert np.all(dst.read(i) == _VALUES_10M[key])
        assert dst.tags()["item_id"] == acq.item_id
        assert dst.tags()["band_order"] == ",".join(BAND_ORDER_10M)

    with rasterio.open(dest_dir / "chip_20m.tif") as dst:
        assert dst.count == 6
        assert (dst.height, dst.width) == (256, 256)
        assert dst.dtypes == ("uint16",) * 6
        assert dst.crs == CRS.from_epsg(32631)
        assert tuple(dst.transform)[:6] == tuple(transform_for(_GRID, 20))[:6]
        for i, key in enumerate(BAND_ORDER_20M, start=1):
            assert np.all(dst.read(i) == _VALUES_20M[key])

    with rasterio.open(dest_dir / "scl.tif") as dst:
        assert dst.count == 1
        assert (dst.height, dst.width) == (256, 256)
        assert dst.dtypes == ("uint8",)
        assert tuple(dst.transform)[:6] == tuple(transform_for(_GRID, 20))[:6]
        assert np.all(dst.read(1) == _SCL_VALUE)


def test_o1bis_hash_de_contenu_stable_entre_deux_executions(
    tmp_path: Path, _sources: dict[str, str]
) -> None:
    """O1bis : le hash de contenu est stable entre deux exécutions consécutives."""
    acq = _make_acq(_sources)
    bands_10m, n10 = read_bands_10m(acq, _GRID, _SETTINGS)
    bands_20m, n20 = read_bands_20m(acq, _GRID, _SETTINGS)
    scl, nscl = read_scl(acq, _GRID, _SETTINGS)
    total = n10 + n20 + nscl

    result_1 = write_chips(
        tmp_path / "run1",
        bands_10m=bands_10m,
        bands_20m=bands_20m,
        scl=scl,
        grid=_GRID,
        item_id=acq.item_id,
        assets_read=total,
    )
    result_2 = write_chips(
        tmp_path / "run2",
        bands_10m=bands_10m,
        bands_20m=bands_20m,
        scl=scl,
        grid=_GRID,
        item_id=acq.item_id,
        assets_read=total,
    )

    assert result_1.content_hashes == result_2.content_hashes
    for digest in result_1.content_hashes.values():
        assert len(digest) == 64  # sha256 hex


def test_o2_epsg_acquisition_different_de_la_grille_leve_erreur_typee() -> None:
    """O2 : acq.proj_epsg != grid.epsg -> EpsgMismatchError, rien n'est ouvert ni écrit."""
    acq = _make_acq({}, proj_epsg=32632)
    with pytest.raises(EpsgMismatchError):
        check_epsg(acq, _GRID)


def test_o2bis_href_https_sous_offline_leve_avant_ouverture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O2bis : href https:// sous TINY_WAE_OFFLINE=1 -> RemoteAccessForbidden, sans ouverture."""
    monkeypatch.setenv(OFFLINE_ENV_VAR, "1")
    acq = _make_acq({"scl": "https://example.test/assets/scl.tif"})
    with pytest.raises(RemoteAccessForbidden):
        read_scl(acq, _GRID, _SETTINGS)


def test_o2bis_href_file_scheme_sous_offline_reste_accepte(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """O2bis : href file:// sous TINY_WAE_OFFLINE=1 est accepté (schéma autorisé)."""
    monkeypatch.setenv(OFFLINE_ENV_VAR, "1")
    p = tmp_path / "scl.tif"
    _write_source(p, grid=_GRID, resolution=20, size=_SETTINGS.chip_px_20m, value=_SCL_VALUE)
    acq = _make_acq({"scl": f"file://{p}"})
    array, count = read_scl(acq, _GRID, _SETTINGS)
    assert count == 1
    assert np.all(array == _SCL_VALUE)


def test_o2bis_chemin_nu_sous_offline_reste_accepte(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """O2bis : chemin nu (sans schéma) sous TINY_WAE_OFFLINE=1 est accepté — forme des
    fixtures locales de l0-03.5."""
    monkeypatch.setenv(OFFLINE_ENV_VAR, "1")
    p = tmp_path / "scl.tif"
    _write_source(p, grid=_GRID, resolution=20, size=_SETTINGS.chip_px_20m, value=_SCL_VALUE)
    acq = _make_acq({"scl": str(p)})
    array, count = read_scl(acq, _GRID, _SETTINGS)
    assert count == 1
    assert np.all(array == _SCL_VALUE)


def _write_chips_with_nodata_fraction(
    tmp_path: Path, *, nodata_pixel_count: int, total_pixels_side: int
) -> float:
    """Construit un chip 10 m synthétique avec une fraction de pixels nodata CHOISIE
    (0 sur les 4 bandes) et retourne le ``chip_nodata_pct`` mesuré par ``write_chips``."""
    settings = Settings(
        stac_url="https://example.test/stac",
        stac_collection="sentinel-2-l2a",
        chip_px_10m=total_pixels_side,
        chip_px_20m=total_pixels_side // 2,
    )
    bands_10m = np.full((4, total_pixels_side, total_pixels_side), 500, dtype=np.uint16)
    # met à nodata (0 sur les 4 bandes) les N premiers pixels (ordre ligne-major aplati).
    flat = bands_10m.reshape(4, -1)
    flat[:, :nodata_pixel_count] = 0
    bands_10m = flat.reshape(4, total_pixels_side, total_pixels_side)
    bands_20m = np.full((6, settings.chip_px_20m, settings.chip_px_20m), 500, dtype=np.uint16)
    scl = np.full((settings.chip_px_20m, settings.chip_px_20m), _SCL_VALUE, dtype=np.uint8)

    result = write_chips(
        tmp_path,
        bands_10m=bands_10m,
        bands_20m=bands_20m,
        scl=scl,
        grid=_GRID,
        item_id="S2A_NODATA_TEST",
        assets_read=11,
    )
    return result.chip_nodata_pct


def test_o3_fraction_nodata_zero_virgule_cinq_pour_cent(tmp_path: Path) -> None:
    """O3 (sens 1) : 2 pixels nodata sur 400 -> chip_nodata_pct == 0.5 (côté ingested)."""
    pct = _write_chips_with_nodata_fraction(tmp_path, nodata_pixel_count=2, total_pixels_side=20)
    assert pct == pytest.approx(0.5)
    assert (
        pct <= Settings(stac_url="x", stac_collection="y").chip_nodata_pct_max
    )  # settings par défaut : 1 % -> resterait "ingested"


def test_o3_fraction_nodata_quarante_pour_cent(tmp_path: Path) -> None:
    """O3 (sens 2) : 160 pixels nodata sur 400 -> chip_nodata_pct == 40.0 (côté rejected_nodata)."""
    pct = _write_chips_with_nodata_fraction(tmp_path, nodata_pixel_count=160, total_pixels_side=20)
    assert pct == pytest.approx(40.0)
    assert (
        pct > Settings(stac_url="x", stac_collection="y").chip_nodata_pct_max
    )  # dépasse le seuil par défaut -> déclencherait rejected_nodata en l0-03.4


# --- perf-01 : réglages GDAL pour la lecture des COG distants ---------------------------

# Valeurs de D1, recopiées ICI littéralement (pas importées de chips.py) : c'est ce qui
# rend O1/O2 discriminants — importer la constante de production comparerait la constante
# à elle-même et resterait au vert même si sa valeur dérivait de D1.
_EXPECTED_GDAL_OPTIONS = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_MULTIPLEX": "YES",
    "GDAL_HTTP_VERSION": "2",
    "VSI_CACHE": "TRUE",
}


def _capture_gdal_env_at_open(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    """Remplace ``rasterio.open`` par un espion qui capture ``rasterio.env.getenv()`` au
    moment de l'appel puis délègue à l'implémentation réelle (perf-01, O1/O2) : le raster
    est réellement lu, seul l'environnement GDAL actif au moment de l'ouverture est observé
    en plus. ``EnvError`` (aucun contexte GDAL actif) est capturée en dict vide plutôt que
    laissée remonter, pour que l'assertion sur les valeurs produise un écart lisible plutôt
    qu'une exception opaque levée dans un thread du pool.
    """
    captured: list[dict[str, str]] = []
    real_open = rasterio.open

    def spy_open(href: object, *args: object, **kwargs: object) -> object:
        try:
            env_state = dict(rasterio.env.getenv())
        except rasterio.errors.EnvError:
            env_state = {}
        captured.append(env_state)
        return real_open(href, *args, **kwargs)

    monkeypatch.setattr(rasterio, "open", spy_open)
    return captured


def _write_offline_scl_source(tmp_path: Path) -> str:
    """Écrit une source SCL locale minimale et rend son chemin (chemin nu, hors garde)."""
    p = tmp_path / "scl.tif"
    _write_source(p, grid=_GRID, resolution=20, size=_SETTINGS.chip_px_20m, value=_SCL_VALUE)
    return str(p)


def test_o1_options_gdal_actives_pendant_ouverture_thread_principal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """O1 (perf-01) : les 5 options de D1 sont actives, valeur exacte, au moment de
    ``rasterio.open`` dans ``_read_window`` — depuis le thread principal."""
    # Source écrite AVANT l'espion : sinon l'ouverture en écriture de la fixture serait
    # elle-même capturée (elle n'a pas de contexte GDAL, ce n'est pas ce que O1 mesure).
    acq = _make_acq({"scl": _write_offline_scl_source(tmp_path)})
    captured = _capture_gdal_env_at_open(monkeypatch)

    read_scl(acq, _GRID, _SETTINGS)

    assert len(captured) == 1
    env = captured[0]
    for name, value in _EXPECTED_GDAL_OPTIONS.items():
        assert env.get(name) == value, f"{name} : attendu {value!r}, vu {env.get(name)!r}"


def test_o2_options_gdal_actives_depuis_un_thread_du_pool(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """O2 (perf-01) : LE MÊME test, mais l'appel est lancé dans un ``ThreadPoolExecutor``
    — l'oracle qui garde D2. ``rasterio.Env`` pose ses options en THREAD-LOCAL : un Env
    ouvert par erreur dans le thread principal (au lieu de DANS ``_read_window``) laisserait
    ``rasterio.env.getenv()`` lever ``EnvError`` depuis le thread du pool, et
    ``_capture_gdal_env_at_open`` capturerait un dict vide — cette assertion échouerait
    alors sur chacune des 5 options."""
    # Source écrite AVANT l'espion (même raison que O1).
    acq = _make_acq({"scl": _write_offline_scl_source(tmp_path)})
    captured = _capture_gdal_env_at_open(monkeypatch)

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(read_scl, acq, _GRID, _SETTINGS).result()

    assert len(captured) == 1
    env = captured[0]
    for name, value in _EXPECTED_GDAL_OPTIONS.items():
        assert env.get(name) == value, f"{name} : attendu {value!r}, vu {env.get(name)!r}"


def test_o3_ordre_guard_puis_contexte_gdal_puis_ouverture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """O3 (perf-01) : ordre RÉEL des opérations dans ``_read_window`` — ``_guard_href``
    s'exécute avant tout le reste (contexte GDAL inclus), jamais après.

    L'assertion porte sur la PREMIÈRE occurrence de chaque étape, pas sur une égalité
    stricte de séquence : ``rasterio.open`` est lui-même décoré
    (``ensure_env_with_credentials``) et pousse SYSTÉMATIQUEMENT un ``Env`` imbriqué
    supplémentaire en interne (vérifié en lisant sa source) — un second "env" après "open"
    est donc attendu et n'a rien à voir avec le contexte que POSE notre code."""
    # Source écrite AVANT les espions (même raison que O1) : sinon l'écriture de la
    # fixture apparaîtrait comme un "open" avant même le premier "guard" observé.
    acq = _make_acq({"scl": _write_offline_scl_source(tmp_path)})
    order: list[str] = []

    real_guard = chips_module._guard_href

    def spy_guard(href: str) -> None:
        order.append("guard")
        real_guard(href)

    real_env_enter = rasterio.Env.__enter__

    def spy_env_enter(self: rasterio.Env) -> object:
        order.append("env")
        return real_env_enter(self)

    real_open = rasterio.open

    def spy_open(href: object, *args: object, **kwargs: object) -> object:
        order.append("open")
        return real_open(href, *args, **kwargs)

    monkeypatch.setattr(chips_module, "_guard_href", spy_guard)
    monkeypatch.setattr(rasterio.Env, "__enter__", spy_env_enter)
    monkeypatch.setattr(rasterio, "open", spy_open)

    read_scl(acq, _GRID, _SETTINGS)

    assert order[0] == "guard", order
    assert order.index("env") < order.index("open"), order


def test_o3_offline_https_refuse_avant_toute_ouverture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O3 (perf-01) : sous ``TINY_WAE_OFFLINE=1``, un href ``https://`` est refusé AVANT
    toute ouverture — ni le contexte GDAL ni ``rasterio.open`` ne sont jamais atteints."""
    reached: list[str] = []

    real_env_enter = rasterio.Env.__enter__

    def spy_env_enter(self: rasterio.Env) -> object:
        reached.append("env")
        return real_env_enter(self)

    real_open = rasterio.open

    def spy_open(href: object, *args: object, **kwargs: object) -> object:
        reached.append("open")
        return real_open(href, *args, **kwargs)

    monkeypatch.setattr(rasterio.Env, "__enter__", spy_env_enter)
    monkeypatch.setattr(rasterio, "open", spy_open)
    monkeypatch.setenv(OFFLINE_ENV_VAR, "1")

    acq = _make_acq({"scl": "https://example.test/assets/scl.tif"})
    with pytest.raises(RemoteAccessForbidden):
        read_scl(acq, _GRID, _SETTINGS)

    assert reached == []


def test_o4_options_gdal_ecrites_une_seule_fois_dans_le_depot() -> None:
    """O4 (perf-01) : chaque option de D1 n'apparaît qu'UNE fois dans le dépôt (D3/D4),
    dans ``adapters/chips.py`` — jamais recopiée ailleurs.

    Périmètre : ``src/``, ``justfile``, ``docs/`` HORS ``docs/backlog/``. Les fiches de
    backlog narrent la décision en prose (D1 cite les 5 valeurs dans son propre tableau,
    ce qu'on attend d'une fiche) : ce n'est pas une seconde source de configuration au sens
    de D4 (l'inquiétude porte sur une doc opérationnelle qu'un opérateur recopierait), et
    les fiches livrées restent dans le dépôt (déplacées vers ``fait/``, jamais supprimées).
    Sans cette exclusion, le critère serait structurellement infaisable dès l'instant où
    cette fiche existe — point que la fiche perf-01 n'avait pas anticipé, tranché ici."""
    repo_root = Path(__file__).resolve().parent.parent
    chips_path = repo_root / "src" / "tiny_wae" / "adapters" / "chips.py"
    scan_roots = [repo_root / "src", repo_root / "justfile", repo_root / "docs"]
    excluded_dir = repo_root / "docs" / "backlog"

    files: list[Path] = []
    for root in scan_roots:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(
                f for f in root.rglob("*") if f.is_file() and excluded_dir not in f.parents
            )

    for name in _EXPECTED_GDAL_OPTIONS:
        total = 0
        locations: list[tuple[Path, int]] = []
        for f in files:
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            count = text.count(name)
            if count:
                locations.append((f, count))
                total += count
        assert total == 1, f"{name} : {total} occurrence(s) au lieu de 1 — {locations}"
        assert locations == [(chips_path, 1)], f"{name} : {locations}"
