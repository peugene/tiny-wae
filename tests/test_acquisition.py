"""Tests core/acquisition.py (l0-02.1).

Couvre le critère LOCAL de la fiche : round-trip JSON de ``Acquisition``, y compris la
forme PAR ASSET de ``radiometry`` (arbitrage n°1 — un dict, pas deux scalaires) et le cas
``None`` (asset sans ``raster:bands``, ex. ``scl``).
"""

from __future__ import annotations

from tiny_wae.core.acquisition import Acquisition


def _sample() -> Acquisition:
    """Une Acquisition littérale, radiometry mixte (valeur + None) — cas représentatif."""
    return Acquisition(
        item_id="S2B_31TGJ_20230315_0_L2A",
        datetime="2023-03-15T10:38:55.261000Z",
        platform="sentinel-2b",
        tile="31TGJ",
        sequence="0",
        scene_cloud_cover=88.346541,
        nodata_pixel_pct=0.0,
        processing_baseline="05.09",
        boa_offset_applied=True,
        proj_epsg=32631,
        assets={"blue": "https://example.test/B02.tif", "scl": "https://example.test/SCL.tif"},
        radiometry={"blue": (0.0001, -0.1), "scl": None},
    )


def test_round_trip_to_dict_from_dict() -> None:
    """to_dict -> from_dict reproduit l'objet champ à champ, radiometry incluse (arbitrage n°1)."""
    acquisition = _sample()
    restored = Acquisition.from_dict(acquisition.to_dict())
    assert restored == acquisition


def test_to_dict_radiometry_json_compatible() -> None:
    """to_dict rend les tuples radiométriques en LISTES (JSON n'a pas de tuple), None reste None."""
    payload = _sample().to_dict()
    assert payload["radiometry"]["blue"] == [0.0001, -0.1]
    assert payload["radiometry"]["scl"] is None


def test_round_trip_via_json_serialisation() -> None:
    """Round-trip complet en passant PAR un vrai json.dumps/loads (pas juste le dict Python)."""
    import json

    acquisition = _sample()
    reloaded = Acquisition.from_dict(json.loads(json.dumps(acquisition.to_dict())))
    assert reloaded == acquisition
