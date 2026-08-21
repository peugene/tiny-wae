#!/usr/bin/env python3
"""record_stac_fixtures.py — enregistrement RÉSEAU des 5 fixtures STAC (l0-02.1).

Les tests tournent sous ``--disable-socket`` (aucun accès réseau) : ce script s'exécute
HORS pytest, via ``just script record_stac_fixtures``, et écrit les items bruts (JSON
``FeatureCollection`` exact, non retouché) dans ``tests/fixtures/stac/``.

⭐ **Adressage par ID ET par fenêtre ABSOLUE (verrou V1 de la roadmap)** : les fenêtres
``datetime`` ci-dessous sont des dates calendaires fixes, jamais dérivées de ``now()`` —
deux des items gelés (le nuageux du 15/03/2023, le S2C du 13/05/2026) sortiraient d'une
fenêtre relative « 48 derniers mois » une fois cette date passée, rendant le script non
rejouable. earth-search exige un RFC3339 complet AVEC heure (plage date seule -> 400,
découverte de terrain de l0-01.3) : toutes les bornes ci-dessous en portent une.

Les 5 fixtures :
    1. ``s2b_cloudy.json``   — item gelé S2B_31TGJ_20230315_0_L2A (cc 88,3 % — filtre cloud).
    2. ``s2c_new_schema.json`` — item S2C_31TGJ_20260513_0_L2A (schéma d'assets S2C, s3://
       sur les assets non mappés ``cloud``/``snow``).
    3. ``sequence_1.json``   — item S2A_31TGJ_20260813_1_L2A (``s2:sequence == "1"``).
    4. ``empty.json``        — réponse earth-search vide (bbox océanique, aucun résultat).
    5. ``bi_tile.json``      — réponse bi-tuile sur C07 (bbox à cheval sur 52TDL/52TEL,
       seule fixture qui exerce ``off_tile`` — O4 de la fiche).

Codes de sortie (``cli.exit_codes``, réutilisés) : 0 OK · 3 réseau injoignable ou item
introuvable (aucune fixture écrite côté fautif — les autres si déjà enregistrées).
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from pystac_client import Client

from tiny_wae.adapters.config_io import DEFAULT_SETTINGS_PATH, load_settings
from tiny_wae.cli import exit_codes

FIXTURES_DIR = Path("tests/fixtures/stac")

# Bbox océanique (Pacifique sud) garantie sans couverture Sentinel-2 (aucune terre émergée).
_EMPTY_BBOX = (-140.0, -30.0, -139.9, -29.9)

# Bbox C07 à cheval sur 52TDL/52TEL (mesurée — cf. périmètre de la fiche l0-02.1).
_C07_BI_TILE_BBOX = (129.0494, 41.257, 129.1106, 41.303)


class RecordNetworkError(RuntimeError):
    """Amont réseau injoignable ou item introuvable — mappé sur ``exit_codes.INCONCLUSIVE``."""


def _search_by_ids(client: Client, collection: str, item_ids: list[str]) -> list[dict[str, Any]]:
    """Recherche par ID(s), doublée d'une fenêtre ABSOLUE large (2020-2027, couvre toute la
    fenêtre de vie connue des items gelés) : la requête reste rejouable après l'expiration
    d'une fenêtre glissante, et la fenêtre absolue garde le filtre significatif même si
    earth-search venait à ignorer ``ids`` seul."""
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
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Recherche par bbox + fenêtre ABSOLUE (bornes RFC3339 littérales, jamais ``now()``)."""
    search = client.search(collections=[collection], bbox=bbox, datetime=(start, end), limit=limit)
    return [item.to_dict() for item in search.items()]


def _write_fixture(name: str, items: list[dict[str, Any]]) -> Path:
    """Écrit ``{"items": [...]}`` dans ``FIXTURES_DIR/name`` (indenté, déterministe)."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIXTURES_DIR / name
    payload = {"items": items}
    fd, tmp_name = tempfile.mkstemp(dir=FIXTURES_DIR, prefix=f".{name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        tmp_path.replace(path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return path


def run() -> int:
    """Enregistre les 5 fixtures. Renvoie le code de sortie du processus."""
    settings = load_settings(DEFAULT_SETTINGS_PATH)

    try:
        client = Client.open(settings.stac_url)

        cloudy = _search_by_ids(client, settings.stac_collection, ["S2B_31TGJ_20230315_0_L2A"])
        if not cloudy:
            raise RecordNetworkError("S2B_31TGJ_20230315_0_L2A introuvable")
        _write_fixture("s2b_cloudy.json", cloudy)
        print("record-stac-fixtures : s2b_cloudy.json (1 item)", file=sys.stderr)

        s2c = _search_by_ids(client, settings.stac_collection, ["S2C_31TGJ_20260513_0_L2A"])
        if not s2c:
            raise RecordNetworkError("S2C_31TGJ_20260513_0_L2A introuvable")
        _write_fixture("s2c_new_schema.json", s2c)
        print("record-stac-fixtures : s2c_new_schema.json (1 item)", file=sys.stderr)

        seq1 = _search_by_ids(client, settings.stac_collection, ["S2A_31TGJ_20260813_1_L2A"])
        if not seq1:
            raise RecordNetworkError("S2A_31TGJ_20260813_1_L2A introuvable")
        _write_fixture("sequence_1.json", seq1)
        print("record-stac-fixtures : sequence_1.json (1 item)", file=sys.stderr)

        empty = _search_by_bbox(
            client,
            settings.stac_collection,
            _EMPTY_BBOX,
            "2024-01-01T00:00:00Z",
            "2024-02-01T00:00:00Z",
        )
        _write_fixture("empty.json", empty)
        print(f"record-stac-fixtures : empty.json ({len(empty)} item)", file=sys.stderr)

        bi_tile = _search_by_bbox(
            client,
            settings.stac_collection,
            _C07_BI_TILE_BBOX,
            "2024-08-01T00:00:00Z",
            "2024-08-31T23:59:59Z",
        )
        if not bi_tile:
            raise RecordNetworkError("bi_tile (C07) : réponse vide, attendu >= 2 items")
        _write_fixture("bi_tile.json", bi_tile)
        print(f"record-stac-fixtures : bi_tile.json ({len(bi_tile)} items)", file=sys.stderr)

    except RecordNetworkError as exc:
        print(f"record-stac-fixtures : {exc}", file=sys.stderr)
        return exit_codes.INCONCLUSIVE
    except Exception as exc:  # amont injoignable, timeout, etc. — non concluant, pas un bug.
        print(f"record-stac-fixtures : réseau injoignable : {exc}", file=sys.stderr)
        return exit_codes.INCONCLUSIVE

    print(f"record-stac-fixtures : 5 fixtures écrites dans {FIXTURES_DIR}", file=sys.stderr)
    return exit_codes.OK


def main() -> None:
    """Point d'entrée : aucun argument (les 5 fixtures sont fixes, cf. décision de fiche)."""
    sys.exit(run())


if __name__ == "__main__":
    main()
