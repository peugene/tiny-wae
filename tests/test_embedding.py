"""tests/test_embedding.py — oracle figé de la fiche l1-01.1 (six critères, pas plus)."""

import pytest

from tiny_wae.core.bands import BAND_ORDER_10M, BAND_ORDER_20M
from tiny_wae.core.embedding import (
    BAND_ORDER_EMBED,
    EmbeddingSpec,
    MissingBandError,
    spec_hash,
    to_reflectance,
    validate_spec,
)


def test_band_order_embed_matches_clay_order_ordered() -> None:
    """O1a : égalité ORDONNÉE avec le tuple Clay gelé dans le test (rougit sur permutation)."""
    clay_order = (
        "blue",
        "green",
        "red",
        "rededge1",
        "rededge2",
        "rededge3",
        "nir",
        "nir08",
        "swir16",
        "swir22",
    )
    assert clay_order == BAND_ORDER_EMBED


def test_band_order_embed_is_union_of_lot0_orders() -> None:
    """O1b : même ensemble que Lot 0 (attrape l'oubli et le doublon), ordre différent."""
    assert set(BAND_ORDER_EMBED) == set(BAND_ORDER_10M) | set(BAND_ORDER_20M)


def test_spec_hash_insensitive_to_numeric_type() -> None:
    """O2 (sens 1) : size_px=256 (int) et 256.0 (float) donnent le même hash."""
    spec_int = EmbeddingSpec(
        bands=("blue", "green"),
        size_px=256,
        resolution_m=10.0,
        tiling="whole_chip",
        normalization="clay_v1",
    )
    spec_float = EmbeddingSpec(
        bands=("blue", "green"),
        size_px=256.0,  # type: ignore[arg-type]  # O2 : injecté volontairement en float
        resolution_m=10.0,
        tiling="whole_chip",
        normalization="clay_v1",
    )
    assert spec_hash(spec_int) == spec_hash(spec_float)


def test_spec_hash_differs_on_tiling_or_normalization() -> None:
    """O2 (sens 2) : un tiling ou une normalization différents changent le hash."""
    base = EmbeddingSpec(
        bands=("blue", "green"),
        size_px=256,
        resolution_m=10.0,
        tiling="whole_chip",
        normalization="clay_v1",
    )
    diff_normalization = EmbeddingSpec(
        bands=("blue", "green"),
        size_px=256,
        resolution_m=10.0,
        tiling="whole_chip",
        normalization="clay_v2",
    )
    assert spec_hash(base) != spec_hash(diff_normalization)


def test_to_reflectance_boa_offset_not_reapplied() -> None:
    """O3 : mêmes scale/offset, boa_offset_applied change le résultat (au 1e-6)."""
    value = 1234.0
    scale = 0.0001
    offset = -0.1
    with_offset = to_reflectance(value, scale, offset, boa_offset_applied=False)
    without_offset = to_reflectance(value, scale, offset, boa_offset_applied=True)
    assert with_offset == pytest.approx(0.0234, abs=1e-6)
    assert without_offset == pytest.approx(0.1234, abs=1e-6)
    assert with_offset != without_offset


def test_validate_spec_names_missing_band() -> None:
    """O4 : bande absente -> erreur nommant littéralement la bande manquante."""
    spec = EmbeddingSpec(
        bands=("blue", "not_a_band"),
        size_px=256,
        resolution_m=10.0,
        tiling="whole_chip",
        normalization="clay_v1",
    )
    with pytest.raises(MissingBandError, match="not_a_band"):
        validate_spec(spec, available_bands=("blue", "green"))


def test_validate_spec_rejects_tiles() -> None:
    """O5 : tiling='tiles' lève NotImplementedError (variante non implémentée du lot)."""
    spec = EmbeddingSpec(
        bands=("blue",),
        size_px=256,
        resolution_m=10.0,
        tiling="tiles",
        normalization="clay_v1",
    )
    with pytest.raises(NotImplementedError):
        validate_spec(spec, available_bands=("blue",))
