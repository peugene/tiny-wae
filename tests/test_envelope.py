"""Tests core/envelope.py (l0-02.1 + fiche data-01).

Couvre :
- le critère LOCAL de round-trip JSON (Envelope + Acquisitions imbriquées) ;
- O5 (via ce module ISOLÉMENT, la version « corpus 5 fixtures » est dans test_stac.py) :
  l'invariant de conservation lève ``ConservationError`` — DISCRIMINANT : un code qui ne
  vérifierait rien laisserait passer une Envelope incohérente sans lever.
- data-01/O2 : l'identité comptable ÉTENDUE (``found_stac == skipped_scene_cloud +
  off_tile + found_tile + skipped_asset_scheme``) — au point de définition, ``core/envelope.py``.
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
    """Compteurs cohérents (found_stac = skipped+off_tile+found_tile+skipped_asset_scheme,
    found_tile = len(items))."""
    envelope = Envelope(
        schema_version=1,
        site_id="C07",
        window={"start": "2024-08-01T00:00:00", "end": "2024-08-31T00:00:00"},
        counters={
            "found_stac": 5,
            "skipped_scene_cloud": 2,
            "off_tile": 1,
            "found_tile": 2,
            "skipped_asset_scheme": 0,
        },
        items=[_acquisition("a"), _acquisition("b")],
    )
    assert envelope.counters["found_tile"] == 2


def test_conservation_violee_found_stac() -> None:
    """found_stac != skipped+off_tile+found_tile+skipped_asset_scheme -> ConservationError
    (jamais silencieux)."""
    with pytest.raises(ConservationError):
        Envelope(
            schema_version=1,
            site_id="C07",
            window={"start": "x", "end": "y"},
            counters={
                "found_stac": 99,
                "skipped_scene_cloud": 2,
                "off_tile": 1,
                "found_tile": 2,
                "skipped_asset_scheme": 0,
            },
            items=[_acquisition("a"), _acquisition("b")],
        )


def test_conservation_violee_found_tile_vs_items() -> None:
    """found_tile != len(items) -> ConservationError, même si le premier invariant tient."""
    with pytest.raises(ConservationError):
        Envelope(
            schema_version=1,
            site_id="C07",
            window={"start": "x", "end": "y"},
            counters={
                "found_stac": 3,
                "skipped_scene_cloud": 1,
                "off_tile": 1,
                "found_tile": 1,
                "skipped_asset_scheme": 0,
            },
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


def test_compteur_skipped_asset_scheme_manquant_leve() -> None:
    """data-01 : ``skipped_asset_scheme`` absent est traité comme n'importe quelle clé
    manquante à la CONSTRUCTION d'une Envelope — la tolérance D6 ne vaut qu'à la lecture de
    ``run.json`` (``adapters/manifests.py``), jamais ici (Envelope n'a pas de corpus
    historique à préserver : ``envelope.json`` est un artefact éphémère de chaînage CWL)."""
    with pytest.raises(ConservationError):
        Envelope(
            schema_version=1,
            site_id="C07",
            window={"start": "x", "end": "y"},
            counters={"found_stac": 2, "skipped_scene_cloud": 0, "off_tile": 0, "found_tile": 2},
            items=[_acquisition("a"), _acquisition("b")],
        )


# ── data-01/O2 : identité comptable ÉTENDUE (D3) ─────────────────────────────────────


def test_o2_identite_etendue_avec_skipped_asset_scheme() -> None:
    """found_stac == skipped_scene_cloud + off_tile + found_tile + skipped_asset_scheme,
    avec skipped_asset_scheme > 0 : c'est l'extension D3 de la fiche data-01, au point de
    définition (jamais contournée)."""
    envelope = Envelope(
        schema_version=1,
        site_id="C07",
        window={"start": "2024-08-01T00:00:00", "end": "2024-08-31T00:00:00"},
        counters={
            "found_stac": 5,
            "skipped_scene_cloud": 1,
            "off_tile": 1,
            "found_tile": 2,
            "skipped_asset_scheme": 1,
        },
        items=[_acquisition("a"), _acquisition("b")],
    )
    assert envelope.counters["skipped_asset_scheme"] == 1
    assert envelope.counters["found_stac"] == (
        envelope.counters["skipped_scene_cloud"]
        + envelope.counters["off_tile"]
        + envelope.counters["found_tile"]
        + envelope.counters["skipped_asset_scheme"]
    )


def test_o2_conservation_violee_si_skipped_asset_scheme_omis_de_la_somme() -> None:
    """Un found_stac qui n'inclut PAS skipped_asset_scheme dans son décompte casse
    l'invariant -> ConservationError (discriminant : prouve que le terme est bien exigé,
    pas juste toléré présent)."""
    with pytest.raises(ConservationError):
        Envelope(
            schema_version=1,
            site_id="C07",
            window={"start": "x", "end": "y"},
            counters={
                "found_stac": 4,  # devrait être 5 (1+1+2+1) pour boucler
                "skipped_scene_cloud": 1,
                "off_tile": 1,
                "found_tile": 2,
                "skipped_asset_scheme": 1,
            },
            items=[_acquisition("a"), _acquisition("b")],
        )


def test_round_trip_to_dict_from_dict() -> None:
    """to_dict -> from_dict reproduit l'Envelope champ à champ, items imbriqués inclus."""
    envelope = Envelope(
        schema_version=1,
        site_id="C07",
        window={"start": "2024-08-01T00:00:00", "end": "2024-08-31T00:00:00"},
        counters={
            "found_stac": 3,
            "skipped_scene_cloud": 1,
            "off_tile": 0,
            "found_tile": 2,
            "skipped_asset_scheme": 0,
        },
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
        counters={
            "found_stac": 1,
            "skipped_scene_cloud": 0,
            "off_tile": 0,
            "found_tile": 1,
            "skipped_asset_scheme": 0,
        },
        items=[_acquisition("a")],
    )
    reloaded = Envelope.from_dict(json.loads(json.dumps(envelope.to_dict())))
    assert reloaded == envelope
