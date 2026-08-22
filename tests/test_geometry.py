"""Tests core/geometry.py (l0-03.1).

Couvre l'oracle de la fiche :
- O1 : grille SYNTHÉTIQUE littérale (epsg 32631, origine multiple de 60 m) + tailles lues
  des settings -> chip_bounds au mètre près, emprise 10 m et 20 m identiques, alignement
  ×2 exact. Volontairement découplé de sites.yaml : ce module est pur.
"""

from __future__ import annotations

import pytest
from affine import Affine

from tiny_wae.core.geometry import (
    GridNotComputedError,
    InconsistentChipSizesError,
    chip_bounds,
    transform_for,
)
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Grid

# Grille synthétique : origine multiple de 60 m (tuile S2 32631T réelle), littérale.
_GRID = Grid(epsg=32631, origin_x=699960.0, origin_y=4900020.0)

_SETTINGS = Settings(
    stac_url="https://example.test/stac",
    stac_collection="sentinel-2-l2a",
    chip_px_10m=512,
    chip_px_20m=256,
)


def test_chip_bounds_o1_valeurs_attendues_au_metre_pres() -> None:
    """O1 : chip_bounds == valeurs attendues au mètre près, dérivées de la grille synthétique."""
    minx, miny, maxx, maxy = chip_bounds(_GRID, _SETTINGS)
    span = 512 * 10  # == 256 * 20 == 5120 m
    assert (minx, maxy) == (699960.0, 4900020.0)
    assert maxx == 699960.0 + span
    assert miny == 4900020.0 - span


def test_chip_bounds_o1_emprise_10m_et_20m_identiques() -> None:
    """O1 : l'emprise couverte par 512 px @ 10 m == celle couverte par 256 px @ 20 m."""
    bounds = chip_bounds(_GRID, _SETTINGS)
    span_10m = _SETTINGS.chip_px_10m * 10
    span_20m = _SETTINGS.chip_px_20m * 20
    assert span_10m == span_20m
    assert bounds[2] - bounds[0] == span_10m
    assert bounds[3] - bounds[1] == span_20m


def test_chip_bounds_o1_alignement_x2_exact() -> None:
    """O1 : l'origine (multiple de 60 m) reste un multiple de 20 m après emprise -> pixel
    grid 20 m entière ; le pas 10 m divise exactement le pas 20 m (alignement ×2)."""
    minx, miny, maxx, maxy = chip_bounds(_GRID, _SETTINGS)
    for value in (minx, miny, maxx, maxy):
        assert value % 20 == 0, f"{value} n'est pas un multiple de 20 m"
    assert (maxx - minx) % 10 == 0
    assert (maxx - minx) / 10 == _SETTINGS.chip_px_10m
    assert (maxx - minx) / 20 == _SETTINGS.chip_px_20m


def test_chip_bounds_grille_non_calculee_leve_erreur_typee() -> None:
    """Grille vide (epsg/origin à None, état par défaut du parc) -> GridNotComputedError."""
    with pytest.raises(GridNotComputedError):
        chip_bounds(Grid(), _SETTINGS)


def test_chip_bounds_tailles_incoherentes_leve_erreur_typee() -> None:
    """chip_px_10m×10 != chip_px_20m×20 -> InconsistentChipSizesError, pas un résultat faux."""
    bad_settings = Settings(
        stac_url="https://example.test/stac",
        stac_collection="sentinel-2-l2a",
        chip_px_10m=512,
        chip_px_20m=100,
    )
    with pytest.raises(InconsistentChipSizesError):
        chip_bounds(_GRID, bad_settings)


def test_transform_for_10m() -> None:
    """transform_for renvoie un affine.Affine cohérent avec l'origine et la résolution."""
    transform = transform_for(_GRID, 10)
    assert transform == Affine(10.0, 0.0, 699960.0, 0.0, -10.0, 4900020.0)


def test_transform_for_20m() -> None:
    """transform_for à 20 m ne réutilise pas le transform 10 m (résolution correcte)."""
    transform = transform_for(_GRID, 20)
    assert transform == Affine(20.0, 0.0, 699960.0, 0.0, -20.0, 4900020.0)


def test_transform_for_grille_non_calculee_leve_erreur_typee() -> None:
    """Même garde que chip_bounds sur une grille vide."""
    with pytest.raises(GridNotComputedError):
        transform_for(Grid(), 10)
