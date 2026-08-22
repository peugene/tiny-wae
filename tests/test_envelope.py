"""Tests core/envelope.py (l0-02.1).

Couvre :
- le critère LOCAL de round-trip JSON (Envelope + Acquisitions imbriquées) ;
- O5 (via ce module ISOLÉMENT, la version « corpus 5 fixtures » est dans test_stac.py) :
  l'invariant de conservation lève ``ConservationError`` — DISCRIMINANT : un code qui ne
  vérifierait rien laisserait passer une Envelope incohérente sans lever.
"""

from __future__ import annotations

import pytest

from tiny_wae.core.acquisition import Acquisition
from tiny_wae.core.envelope import ConservationError, Envelope


def _acquisition(item_id: str) -> Acquisition:
    """Acquisition minimale littérale, un seul asset, pour peupler des items d'Envelope."""
    return Acquisition(
        item_id=item_id,
        datetime="2024-08-01T10:00:00Z",
        platform="sentinel-2a",
        tile="52TEL",
        sequence="0",
        scene_cloud_cover=1.0,
        nodata_pixel_pct=0.0,
        processing_baseline="05.09",
        boa_offset_applied=True,
        proj_epsg=32652,
        assets={"blue": "https://example.test/B02.tif"},
        radiometry={"blue": (0.0001, -0.1)},
    )


def test_construction_valide_ne_leve_pas() -> None:
    """Compteurs cohérents (found_stac = skipped+off_tile+found_tile, found_tile = len(items))."""
    envelope = Envelope(
        schema_version=1,
        site_id="C07",
        window={"start": "2024-08-01T00:00:00", "end": "2024-08-31T00:00:00"},
        counters={"found_stac": 5, "skipped_scene_cloud": 2, "off_tile": 1, "found_tile": 2},
        items=[_acquisition("a"), _acquisition("b")],
    )
    assert envelope.counters["found_tile"] == 2


def test_conservation_violee_found_stac() -> None:
    """found_stac != skipped+off_tile+found_tile -> ConservationError (jamais silencieux)."""
    with pytest.raises(ConservationError):
        Envelope(
            schema_version=1,
            site_id="C07",
            window={"start": "x", "end": "y"},
            counters={"found_stac": 99, "skipped_scene_cloud": 2, "off_tile": 1, "found_tile": 2},
            items=[_acquisition("a"), _acquisition("b")],
        )


def test_conservation_violee_found_tile_vs_items() -> None:
    """found_tile != len(items) -> ConservationError, même si le premier invariant tient."""
    with pytest.raises(ConservationError):
        Envelope(
            schema_version=1,
            site_id="C07",
            window={"start": "x", "end": "y"},
            counters={"found_stac": 3, "skipped_scene_cloud": 1, "off_tile": 1, "found_tile": 1},
            items=[_acquisition("a"), _acquisition("b")],  # 2 items, found_tile dit 1
        )


def test_compteurs_incomplets() -> None:
    """Une clé de compteur manquante -> ConservationError nommant la clé, pas un KeyError brut."""
    with pytest.raises(ConservationError):
        Envelope(
            schema_version=1,
            site_id="C07",
            window={"start": "x", "end": "y"},
            counters={"found_stac": 0, "off_tile": 0, "found_tile": 0},
            items=[],
        )


def test_round_trip_to_dict_from_dict() -> None:
    """to_dict -> from_dict reproduit l'Envelope champ à champ, items imbriqués inclus."""
    envelope = Envelope(
        schema_version=1,
        site_id="C07",
        window={"start": "2024-08-01T00:00:00", "end": "2024-08-31T00:00:00"},
        counters={"found_stac": 3, "skipped_scene_cloud": 1, "off_tile": 0, "found_tile": 2},
        items=[_acquisition("a"), _acquisition("b")],
    )
    restored = Envelope.from_dict(envelope.to_dict())
    assert restored == envelope


def test_round_trip_via_json_serialisation() -> None:
    """Round-trip complet en passant PAR un vrai json.dumps/loads."""
    import json

    envelope = Envelope(
        schema_version=1,
        site_id="C07",
        window={"start": "2024-08-01T00:00:00", "end": "2024-08-31T00:00:00"},
        counters={"found_stac": 1, "skipped_scene_cloud": 0, "off_tile": 0, "found_tile": 1},
        items=[_acquisition("a")],
    )
    reloaded = Envelope.from_dict(json.loads(json.dumps(envelope.to_dict())))
    assert reloaded == envelope
