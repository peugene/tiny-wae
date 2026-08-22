"""Tests adapters/stac.py (l0-02.1) — sur les 5 fixtures enregistrées hors pytest.

Aucun test ici ne fait de réseau (pytest tourne sous ``--disable-socket``, cf.
pyproject.toml) : tout part de JSON déjà enregistré dans ``tests/fixtures/stac/`` par
``scripts/record_stac_fixtures.py``.

Couvre l'oracle de la fiche :
- O1 : parsing S2B — 11 hrefs https://, proj_epsg=32631, sequence=="0" (chaîne),
  radiometry["blue"]==(0.0001,-0.1) ET radiometry["scl"] is None.
- O2 : parsing S2C sans erreur (assets s3:// non mappés ignorés), platform="sentinel-2c".
- O3 : sequence=1 portée, item distinct du "_0".
- O4 : fixture bi-tuile C07, reference_tile="52TEL" en LITTÉRAL -> off_tile compte les
  items 52TDL, absents de items.
- O5 : conservation exacte sur les 5 fixtures.

Plus le verrou de la décision n°1 (obligatoire, cf. fiche) : normalisation MGRS-xxx -> xxx.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pystac_client.exceptions
import pytest

from tiny_wae.adapters.stac import (
    EarthSearchSource,
    StacSourceError,
    StacUnreachable,
    build_envelope,
    parse_item,
)
from tiny_wae.core.settings import EXPECTED_ASSET_KEYS, Settings
from tiny_wae.core.sites import Site
from tiny_wae.core.windows import Window

FIXTURES_ROOT = Path("tests/fixtures/stac")


def _load_items(name: str) -> list[dict[str, Any]]:
    """Charge les items bruts (``{"items": [...]}``) d'une fixture enregistrée."""
    data = json.loads((FIXTURES_ROOT / name).read_text(encoding="utf-8"))
    return list(data["items"])


def _window() -> Window:
    """Fenêtre littérale, sans portée sur le contenu des fixtures (déjà figées au disque)."""
    return Window(start=datetime(2024, 1, 1), end=datetime(2024, 12, 31))


# ── O1 : parsing S2B (item nuageux gelé) ─────────────────────────────────────────────


def test_o1_parsing_s2b_cloudy() -> None:
    """11 hrefs https://, proj_epsg=32631, sequence=="0" (chaîne), radiometry par asset."""
    items = _load_items("s2b_cloudy.json")
    assert len(items) == 1
    acquisition = parse_item(items[0], EXPECTED_ASSET_KEYS)

    assert acquisition.item_id == "S2B_31TGJ_20230315_0_L2A"
    assert len(acquisition.assets) == 11
    assert all(href.startswith("https://") for href in acquisition.assets.values())
    assert acquisition.proj_epsg == 32631
    assert acquisition.sequence == "0"
    assert isinstance(acquisition.sequence, str)
    assert acquisition.radiometry["blue"] == (0.0001, -0.1)
    assert acquisition.radiometry["scl"] is None


# ── O2 : parsing S2C (nouveau schéma d'assets) ───────────────────────────────────────


def test_o2_parsing_s2c_sans_erreur() -> None:
    """Item S2C parsé sans lever — assets s3:// non mappés (cloud, snow) simplement absents."""
    items = _load_items("s2c_new_schema.json")
    acquisition = parse_item(items[0], EXPECTED_ASSET_KEYS)

    assert acquisition.platform == "sentinel-2c"
    assert "cloud" not in acquisition.assets
    assert "snow" not in acquisition.assets
    assert all(href.startswith("https://") for href in acquisition.assets.values())


# ── O3 : sequence=1 ───────────────────────────────────────────────────────────────────


def test_o3_sequence_portee_et_item_distinct() -> None:
    """sequence=="1", et item_id distinct de celui de la fixture S2B (_0)."""
    items = _load_items("sequence_1.json")
    acquisition = parse_item(items[0], EXPECTED_ASSET_KEYS)

    assert acquisition.sequence == "1"
    assert acquisition.item_id != "S2B_31TGJ_20230315_0_L2A"
    assert acquisition.item_id.endswith("_1_L2A")


# ── O4 : bi-tuile C07, reference_tile en LITTÉRAL ────────────────────────────────────


def test_o4_bi_tile_off_tile_compte_et_exclut() -> None:
    """reference_tile="52TEL" passé en LITTÉRAL (découplé de sites.yaml, desserrage PO)."""
    raw_items = _load_items("bi_tile.json")
    envelope = build_envelope(
        site_id="C07",
        window=_window(),
        raw_items=raw_items,
        reference_tile="52TEL",
        scene_cloud_max=95,
        asset_keys=EXPECTED_ASSET_KEYS,
    )

    # Mesuré sur la fixture (cf. record_stac_fixtures.py, fenêtre 2024-08) : 12 items bruts,
    # 6 sur 52TDL (tous hors tuile), 2 items TEL au-dessus du seuil cloud (skip AVANT tuile),
    # 4 items TEL retenus.
    assert envelope.counters["found_stac"] == 12
    assert envelope.counters["skipped_scene_cloud"] == 2
    assert envelope.counters["off_tile"] == 6
    assert envelope.counters["found_tile"] == 4
    assert len(envelope.items) == 4
    assert all(acq.tile == "52TEL" for acq in envelope.items)
    assert not any(acq.tile == "52TDL" for acq in envelope.items)


# ── O5 : conservation exacte sur les 5 fixtures ──────────────────────────────────────


@pytest.mark.parametrize(
    "fixture_name",
    ["s2b_cloudy.json", "s2c_new_schema.json", "sequence_1.json", "empty.json", "bi_tile.json"],
)
def test_o5_conservation_exacte(fixture_name: str) -> None:
    """found_stac == skipped_scene_cloud + off_tile + found_tile ET found_tile == len(items),
    vérifié INDÉPENDAMMENT de la garantie déjà portée par Envelope.__post_init__ (DISCRIMINANT :
    contrôle que found_stac colle bien au nombre RÉEL d'items bruts de la fixture, pas
    seulement à une arithmétique interne cohérente mais fausse)."""
    raw_items = _load_items(fixture_name)
    envelope = build_envelope(
        site_id="C07",
        window=_window(),
        raw_items=raw_items,
        reference_tile="52TEL",
        scene_cloud_max=95,
        asset_keys=EXPECTED_ASSET_KEYS,
    )
    counters = envelope.counters
    assert counters["found_stac"] == len(raw_items)
    assert counters["found_stac"] == (
        counters["skipped_scene_cloud"] + counters["off_tile"] + counters["found_tile"]
    )
    assert counters["found_tile"] == len(envelope.items)


# ── Verrou décision n°1 (obligatoire) : normalisation MGRS-xxx -> xxx ────────────────


def test_verrou_normalisation_tile_mgrs_prefix() -> None:
    """grid:code="MGRS-52TEL" -> tile=="52TEL" (SANS préfixe), et le filtre le retient face
    à reference_tile="52TEL" (code nu). Sans ce test, le défaut revient à la première
    régression (une comparaison "MGRS-52TEL" == "52TEL" échouerait silencieusement)."""
    raw_items = _load_items("bi_tile.json")
    tel_raw = next(item for item in raw_items if item["properties"]["grid:code"] == "MGRS-52TEL")
    acquisition = parse_item(tel_raw, EXPECTED_ASSET_KEYS)
    assert acquisition.tile == "52TEL"

    envelope = build_envelope(
        site_id="C07",
        window=_window(),
        raw_items=[tel_raw],
        reference_tile="52TEL",
        scene_cloud_max=100,  # neutralise le filtre cloud pour isoler le filtre tuile
        asset_keys=EXPECTED_ASSET_KEYS,
    )
    assert envelope.counters["off_tile"] == 0
    assert envelope.counters["found_tile"] == 1
    assert envelope.items[0].item_id == tel_raw["id"]


# ── Garde href s3:// sur asset mappé ──────────────────────────────────────────────────


def test_garde_href_s3_sur_asset_mappe_leve() -> None:
    """Un asset MAPPÉ (ex. 'blue') en s3:// fait lever StacSourceError — jamais silencieux."""
    item = {
        "id": "FAKE_ITEM",
        "properties": {
            "datetime": "2024-01-01T00:00:00Z",
            "platform": "sentinel-2a",
            "grid:code": "MGRS-52TEL",
            "s2:sequence": "0",
            "eo:cloud_cover": 1.0,
            "s2:nodata_pixel_percentage": 0.0,
            "s2:processing_baseline": "05.09",
            "earthsearch:boa_offset_applied": True,
            "proj:code": "EPSG:32652",
        },
        "assets": {"blue": {"href": "s3://bucket/blue.tif"}},
    }
    with pytest.raises(StacSourceError):
        parse_item(item, EXPECTED_ASSET_KEYS)


def test_garde_href_s3_asset_non_mappe_ignore() -> None:
    """Un asset NON mappé (absent de asset_keys) en s3:// est ignoré, jamais une erreur."""
    item = {
        "id": "FAKE_ITEM",
        "properties": {
            "datetime": "2024-01-01T00:00:00Z",
            "platform": "sentinel-2a",
            "grid:code": "MGRS-52TEL",
            "s2:sequence": "0",
            "eo:cloud_cover": 1.0,
            "s2:nodata_pixel_percentage": 0.0,
            "s2:processing_baseline": "05.09",
            "earthsearch:boa_offset_applied": True,
            "proj:code": "EPSG:32652",
        },
        "assets": {
            "blue": {"href": "https://example.test/blue.tif"},
            "cloud": {"href": "s3://bucket/cloud.jp2"},
        },
    }
    acquisition = parse_item(item, EXPECTED_ASSET_KEYS)
    assert "cloud" not in acquisition.assets
    assert acquisition.assets["blue"] == "https://example.test/blue.tif"


# ── proj:epsg / proj:code — écart mesuré vs la fiche ─────────────────────────────────


def test_proj_epsg_depuis_proj_code() -> None:
    """Les items live earth-search ne portent QUE proj:code ('EPSG:xxxxx') — pas proj:epsg
    (écart mesuré à l'enregistrement des fixtures du 21/08/2026, cf. adapters/stac.py)."""
    items = _load_items("s2b_cloudy.json")
    assert "proj:epsg" not in items[0]["properties"]
    assert items[0]["properties"]["proj:code"] == "EPSG:32631"
    acquisition = parse_item(items[0], EXPECTED_ASSET_KEYS)
    assert acquisition.proj_epsg == 32631


# ── Réponse vide ──────────────────────────────────────────────────────────────────────


def test_fixture_empty_zero_item() -> None:
    """La fixture 'réponse vide' contient bien 0 item — sinon O5 la testerait pour rien."""
    assert _load_items("empty.json") == []


# ── StacUnreachable — décision n°2 de l'ancrage de la fiche l0-02.2 ──────────────────


def _settings(stac_url: str) -> Settings:
    """Settings minimaux valides pour construire un EarthSearchSource dans ces tests."""
    return Settings(stac_url=stac_url, stac_collection="sentinel-2-l2a")


def _site_with_tile() -> Site:
    """Site minimal valide, reference_tile posée (condition d'entrée de EarthSearchSource)."""
    return Site(
        id="C07",
        name="Punggye-ri",
        lat=41.28,
        lon=129.08,
        category="stable-watch",
        note="",
        reference_tile="52TEL",
    )


def test_earthsearch_source_wraps_api_error_as_stac_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`pystac_client.exceptions.APIError` -> `StacUnreachable`, message avec l'URL."""
    stac_url = "https://earth-search.test/v1"

    def _raise_api_error(_url: str) -> None:
        raise pystac_client.exceptions.APIError("serveur en 502")

    monkeypatch.setattr("tiny_wae.adapters.stac.Client.open", _raise_api_error)

    source = EarthSearchSource(_settings(stac_url))
    with pytest.raises(StacUnreachable, match="injoignable"):
        source.search(
            _site_with_tile(), Window(start=datetime(2024, 1, 1), end=datetime(2024, 2, 1))
        )


def test_earthsearch_source_wraps_os_error_as_stac_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`OSError` (DNS, timeout bas niveau…) -> `StacUnreachable` également."""
    stac_url = "https://earth-search.test/v1"

    def _raise_os_error(_url: str) -> None:
        raise OSError("Name or service not known")

    monkeypatch.setattr("tiny_wae.adapters.stac.Client.open", _raise_os_error)

    source = EarthSearchSource(_settings(stac_url))
    with pytest.raises(StacUnreachable, match=stac_url):
        source.search(
            _site_with_tile(), Window(start=datetime(2024, 1, 1), end=datetime(2024, 2, 1))
        )


def test_stac_unreachable_ne_derive_pas_de_stac_source_error() -> None:
    """Garde de la décision n°2 : StacUnreachable hérite d'Exception, PAS de StacSourceError
    (sémantique opposée — un héritage ferait remonter un endpoint mort en « échec métier »,
    et un `except StacSourceError` amont attraperait à tort une simple coupure réseau)."""
    assert not issubclass(StacUnreachable, StacSourceError)
    assert issubclass(StacUnreachable, Exception)
