"""Tests core/tiles.py (l0-01.3).

Couvre l'oracle de la fiche — tests PURS, entrées littérales, aucun réseau (pytest tourne
avec --disable-socket, cf. pyproject.toml) :
- O2 : cas C07 (chip + emprises des deux tuiles 52TDL/52TEL) -> choix = 52TEL, marges
  ≈ 495 m vs ≈ 4 155 m (géométrie, pas un décompte d'items).
- O2bis : deux tuiles de marges ÉGALES, comptes 319 vs 317 -> choix = la plus fournie.
"""

from __future__ import annotations

import pytest

from tiny_wae.core.tiles import (
    TILE_SIDE_M,
    TileCandidate,
    TileGeometryError,
    candidate_margin_m,
    chip_bounds_utm,
    chip_origin,
    choose_reference_tile,
    geometric_margin_m,
    mgrs_zone_epsg,
    natural_utm_epsg,
    round_down_to_step,
    tile_bounds,
    wgs84_survey_bbox,
)

# Punggye-ri (C07) — coordonnées littérales de config/sites.yaml.
_C07_LAT, _C07_LON = 41.28, 129.08
_C07_EPSG = 32652  # zone 52, bande T (nord) — mesuré via /search proj:epsg.
_SPAN_M = 5120.0  # 512 px @ 10 m (chip_px_10m du settings par défaut).

# Origines mesurées (proj:transform de l'asset blue, cf. ancrage réseau du run) — ULX/ULY.
_TDL_ORIGIN = (399960.0, 4600020.0)
_TEL_ORIGIN = (499980.0, 4600020.0)


def test_mgrs_zone_epsg_bande_nord() -> None:
    """52TEL (bande T, nord) -> EPSG 326xx."""
    assert mgrs_zone_epsg("MGRS-52TEL") == 32652
    assert mgrs_zone_epsg("52TEL") == 32652


def test_mgrs_zone_epsg_bande_sud() -> None:
    """Bande C-M -> EPSG 327xx (sud) ; cas Escondida (B06), zone 19, bande K."""
    assert mgrs_zone_epsg("19KFV") == 32719


def test_mgrs_zone_epsg_code_malforme() -> None:
    """Code sans zone numérique ou sans bande -> TileGeometryError typée."""
    with pytest.raises(TileGeometryError):
        mgrs_zone_epsg("TEL")
    with pytest.raises(TileGeometryError):
        mgrs_zone_epsg("52")


def test_natural_utm_epsg_c07() -> None:
    """C07 (lon 129.08, nord) retombe en zone 52 nord (326xx) — cohérent avec la tuile choisie."""
    assert natural_utm_epsg(_C07_LAT, _C07_LON) == 32652


def test_geometric_margin_m_valeurs_connues() -> None:
    """Chip et tuile littéraux -> marge = min des 4 distances aux bords."""
    chip = (100.0, 100.0, 200.0, 200.0)
    tile = (0.0, 0.0, 1000.0, 1000.0)
    assert geometric_margin_m(chip, tile) == 100.0


def test_round_down_to_step() -> None:
    """Arrondi au multiple de 20 m inférieur — cas pile et cas à arrondir."""
    assert round_down_to_step(504140.0) == 504140.0
    assert round_down_to_step(504139.57) == 504120.0
    assert round_down_to_step(19.9) == 0.0


def test_o2_c07_choisit_52tel_marge_geometrique() -> None:
    """O2 : C07, deux tuiles candidates -> 52TEL l'emporte (marge ≈ 4155 m vs ≈ 500 m).

    ⚠ L'oracle porte sur des GÉOMÉTRIES (bbox chip + emprise de tuile mesurée via
    proj:transform), pas sur un décompte d'items — un décompte seul aurait fait gagner
    52TDL (319 vs 317), ce qui est le défaut corrigé par la règle D-c.
    """
    margin_dl = candidate_margin_m(
        _C07_LAT, _C07_LON, _SPAN_M, _C07_EPSG, *_TDL_ORIGIN, TILE_SIDE_M
    )
    margin_el = candidate_margin_m(
        _C07_LAT, _C07_LON, _SPAN_M, _C07_EPSG, *_TEL_ORIGIN, TILE_SIDE_M
    )
    assert margin_dl == pytest.approx(500.4, abs=5.0)
    assert margin_el == pytest.approx(4159.6, abs=5.0)

    candidates = [
        TileCandidate("52TDL", _C07_EPSG, *_TDL_ORIGIN, margin_dl, item_count=319),
        TileCandidate("52TEL", _C07_EPSG, *_TEL_ORIGIN, margin_el, item_count=317),
    ]
    chosen = choose_reference_tile(candidates)
    assert chosen.code == "52TEL"


def test_o2bis_egalite_de_marge_depart_par_le_compte_ditems() -> None:
    """O2bis : deux candidates de marge ÉGALE, comptes 319 vs 317 -> la plus fournie l'emporte."""
    candidates = [
        TileCandidate("52TXX", 32652, 0.0, 0.0, margin_m=1000.0, item_count=317),
        TileCandidate("52TYY", 32652, 0.0, 0.0, margin_m=1000.0, item_count=319),
    ]
    chosen = choose_reference_tile(candidates)
    assert chosen.code == "52TYY"
    assert chosen.item_count == 319


def test_choose_reference_tile_liste_vide() -> None:
    """Aucune candidate -> TileGeometryError typée (pas d'IndexError silencieux)."""
    with pytest.raises(TileGeometryError):
        choose_reference_tile([])


def test_tile_bounds_depuis_origine_mesuree() -> None:
    """tile_bounds(ULX, ULY) -> emprise cohérente avec le côté nominal 109 800 m."""
    minx, miny, maxx, maxy = tile_bounds(*_TEL_ORIGIN)
    assert (minx, maxy) == _TEL_ORIGIN
    assert maxx - minx == TILE_SIDE_M
    assert maxy - miny == TILE_SIDE_M


def test_chip_bounds_utm_carre_centre() -> None:
    """chip_bounds_utm centré sur (x, y), côté span_m — carré exact."""
    minx, miny, maxx, maxy = chip_bounds_utm(1000.0, 2000.0, 5120.0)
    assert (maxx - minx, maxy - miny) == (5120.0, 5120.0)
    assert (minx + maxx) / 2 == 1000.0
    assert (miny + maxy) / 2 == 2000.0


def test_chip_origin_multiple_de_20m() -> None:
    """chip_origin renvoie une origine dont les deux coordonnées sont multiples de 20 m."""
    origin_x, origin_y = chip_origin(_C07_LAT, _C07_LON, _C07_EPSG, _SPAN_M)
    assert origin_x % 20 == 0
    assert origin_y % 20 == 0


def test_wgs84_survey_bbox_encadre_le_point() -> None:
    """La bbox WGS84 du relevé contient bien le point d'origine (lat, lon)."""
    minlon, minlat, maxlon, maxlat = wgs84_survey_bbox(_C07_LAT, _C07_LON, _SPAN_M)
    assert minlon < _C07_LON < maxlon
    assert minlat < _C07_LAT < maxlat
