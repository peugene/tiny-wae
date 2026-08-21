"""Tests cli/search.py (l0-02.2) — capture STDOUT/STDERR, garde anti-socket, INCONCLUSIVE.

Aucun test ici ne fait de réseau : ``build_source`` (point de couture de la fiche, décision
n°1 de l'ancrage) est monkeypatché pour renvoyer un double de test qui rejoue les fixtures
STAC déjà enregistrées (``tests/fixtures/stac/*.json``) — jamais un vrai ``EarthSearchSource``.
Tourne sous ``--disable-socket`` (cf. pyproject.toml) : toute fuite réseau ferait échouer le
test avec ``SocketBlockedError`` plutôt que de passer en silence.

Couvre l'oracle de la fiche :
- O1 : fixture bi-tuile C07 — compteurs GELÉS en littéral (found_stac=12,
  skipped_scene_cloud=2, off_tile=6, found_tile=4, relevés dans test_stac.py::test_o4_*),
  conservation vérifiée par Envelope.__post_init__, STDOUT = JSON parsable SEUL.
- O2 : fenêtre vide -> items == [], exit 0.
- O3 : endpoint injoignable (StacUnreachable simulée) -> exit 3, STDERR contient l'URL de
  l'endpoint ET le mot "injoignable" (assertion littérale).
- Discipline des flux : `--json <path>` écrit l'enveloppe dans le fichier, STDOUT reste vide.
- Erreurs d'usage (site inconnu, date malformée) -> exit USAGE (2).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import tiny_wae.cli.search as search_module
from tiny_wae.__main__ import app
from tiny_wae.adapters.stac import StacSource, StacUnreachable, build_envelope
from tiny_wae.cli import exit_codes
from tiny_wae.core.envelope import Envelope
from tiny_wae.core.settings import EXPECTED_ASSET_KEYS
from tiny_wae.core.sites import Site
from tiny_wae.core.windows import Window

runner = CliRunner()

SITES_PATH = Path("config/sites.yaml")
SETTINGS_PATH = Path("config/settings.yaml")
FIXTURES_ROOT = Path("tests/fixtures/stac")

# C07 est le site multi-tuile du chapeau l0-02 (52TDL/52TEL) — reference_tile="52TEL" dans
# config/sites.yaml, cohérent avec la fixture bi_tile.json et test_stac.py::test_o4_*.
SITE_ID = "C07"
REFERENCE_TILE = "52TEL"


def _load_raw_items(name: str) -> list[dict]:
    """Charge les items bruts d'une fixture enregistrée (``{"items": [...]}``)."""
    data = json.loads((FIXTURES_ROOT / name).read_text(encoding="utf-8"))
    return list(data["items"])


class _FixtureSource:
    """Double de test de ``StacSource`` — rejoue une fixture au lieu du réseau.

    Vit ICI (tests/), pas dans src/ : la vraie ``FixtureSource`` (offline pour de bon) est
    le périmètre de l0-03.5 (décision n°1 de l'ancrage de la fiche l0-02.2).
    """

    def __init__(self, fixture_name: str) -> None:
        self._raw_items = _load_raw_items(fixture_name)

    def search(self, site: Site, window: Window) -> Envelope:
        """Rejoue la fixture chargée, filtrée comme le ferait la vraie source."""
        return build_envelope(
            site_id=site.id,
            window=window,
            raw_items=self._raw_items,
            reference_tile=site.reference_tile or REFERENCE_TILE,
            scene_cloud_max=95,
            asset_keys=EXPECTED_ASSET_KEYS,
        )


class _UnreachableSource:
    """Double de test simulant un endpoint STAC injoignable (réseau coupé)."""

    def __init__(self, stac_url: str) -> None:
        self._stac_url = stac_url

    def search(self, site: Site, window: Window) -> Envelope:
        """Lève ``StacUnreachable`` — simule la coupure réseau (aucune socket ouverte)."""
        raise StacUnreachable(f"{self._stac_url} injoignable : connexion refusée (simulé)")


def _patch_source(monkeypatch: pytest.MonkeyPatch, source: StacSource) -> None:
    """Monkeypatche le point de couture ``build_source`` du module CLI."""
    monkeypatch.setattr(search_module, "build_source", lambda settings: source)


def _invoke(*extra_args: str) -> object:
    """Invoque `search` avec les options communes (site C07, fenêtre 2024)."""
    return runner.invoke(
        app,
        [
            "search",
            "--site",
            SITE_ID,
            "--from",
            "2024-01-01",
            "--to",
            "2024-12-31",
            "--sites-path",
            str(SITES_PATH),
            "--settings-path",
            str(SETTINGS_PATH),
            *extra_args,
        ],
    )


# ── O1 : fixture bi-tuile C07, compteurs gelés en littéral ──────────────────────────


def test_o1_bi_tile_compteurs_geles_et_stdout_json_seul(monkeypatch: pytest.MonkeyPatch) -> None:
    """Compteurs figés (relevés dans test_stac.py::test_o4_*) ; STDOUT = JSON parsable seul."""
    _patch_source(monkeypatch, _FixtureSource("bi_tile.json"))
    result = _invoke()

    assert result.exit_code == exit_codes.OK
    payload = json.loads(result.stdout)
    assert payload["counters"]["found_stac"] == 12
    assert payload["counters"]["skipped_scene_cloud"] == 2
    assert payload["counters"]["off_tile"] == 6
    assert payload["counters"]["found_tile"] == 4
    assert len(payload["items"]) == 4
    # STDOUT ne contient RIEN d'autre que le JSON (la table lisible part sur STDERR).
    assert result.stdout.strip().count("\n") == 0
    assert "found_stac" in result.stderr


# ── O2 : fenêtre vide ─────────────────────────────────────────────────────────────────


def test_o2_fenetre_vide(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixture vide -> items == [], exit 0."""
    _patch_source(monkeypatch, _FixtureSource("empty.json"))
    result = _invoke()

    assert result.exit_code == exit_codes.OK
    payload = json.loads(result.stdout)
    assert payload["items"] == []
    assert payload["counters"]["found_stac"] == 0


# ── O3 : endpoint injoignable -> INCONCLUSIVE (3) ────────────────────────────────────


def test_o3_endpoint_injoignable_inconclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    """StacUnreachable -> exit 3 ; STDERR contient l'URL de l'endpoint ET "injoignable"."""
    stac_url = "https://earth-search.aws.element84.com/v1"
    _patch_source(monkeypatch, _UnreachableSource(stac_url))
    result = _invoke()

    assert result.exit_code == exit_codes.INCONCLUSIVE
    assert result.exit_code == 3
    assert stac_url in result.stderr
    assert "injoignable" in result.stderr
    # Rien sur STDOUT quand la recherche échoue.
    assert result.stdout == ""


# ── Discipline des flux : --json <path> laisse STDOUT vide ──────────────────────────


def test_json_path_ecrit_fichier_stdout_vide(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`--json out.json` écrit l'enveloppe dans le fichier ; STDOUT reste vide."""
    _patch_source(monkeypatch, _FixtureSource("bi_tile.json"))
    out_path = tmp_path / "out.json"
    result = _invoke("--json", str(out_path))

    assert result.exit_code == exit_codes.OK
    assert result.stdout == ""
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["counters"]["found_stac"] == 12


# ── Erreurs d'usage ───────────────────────────────────────────────────────────────────


def test_site_inconnu_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Id de site absent de sites.yaml -> exit USAGE (2), rien sur STDOUT."""
    _patch_source(monkeypatch, _FixtureSource("empty.json"))
    result = runner.invoke(
        app,
        [
            "search",
            "--site",
            "ZZ99",
            "--from",
            "2024-01-01",
            "--to",
            "2024-12-31",
            "--sites-path",
            str(SITES_PATH),
            "--settings-path",
            str(SETTINGS_PATH),
        ],
    )
    assert result.exit_code == exit_codes.USAGE
    assert "ZZ99" in result.stderr
    assert result.stdout == ""


def test_date_malformee_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Date hors format YYYY-MM-DD -> exit USAGE (2)."""
    _patch_source(monkeypatch, _FixtureSource("empty.json"))
    result = runner.invoke(
        app,
        [
            "search",
            "--site",
            SITE_ID,
            "--from",
            "01/09/2022",
            "--to",
            "2024-12-31",
            "--sites-path",
            str(SITES_PATH),
            "--settings-path",
            str(SETTINGS_PATH),
        ],
    )
    assert result.exit_code == exit_codes.USAGE
    assert result.stdout == ""
