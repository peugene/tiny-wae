"""Tests cli/report.py (l0-04.2) — wiring `report` (agrégats + --check-completeness).

Aucun test ici ne fait de réseau (pytest tourne sous ``--disable-socket``) : le mode par
défaut lit ``tests/fixtures/manifests/`` (via ``TINY_WAE_DATA_ROOT``, comme un vrai
``data_root``) ; ``--check-completeness`` monkeypatche ``build_source`` (même convention
que ``cli/search.py`` / ``tests/test_cli_search.py``) pour rejouer une fixture enregistrée
au lieu d'ouvrir une socket.

Couvre :
- O1/O4 (volet CLI) : `report` sur le corpus fixtures, le site C07 apparaît avec les
  comptes mesurés, exit OK, fichier Markdown écrit.
- O2ter (volet wiring CLI, complémentaire du test core sur OVERLAP dans
  test_report.py::test_o2ter_*) : `--check-completeness --sites C07` sur une fixture
  ``/search`` qui porte elle aussi les 2 pièges (hors-tuile, pré-filtre scène) en plus des
  12 ids réels du corpus C07 -> écart 0 -> OK ; fixture mutée (1 id retiré) -> ROUGE,
  l'id manquant nommé, exit FAILURE.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import tiny_wae.cli.report as report_module
from tiny_wae.__main__ import app
from tiny_wae.adapters.stac import StacSource, build_envelope
from tiny_wae.cli import exit_codes
from tiny_wae.core.envelope import Envelope
from tiny_wae.core.settings import EXPECTED_ASSET_KEYS
from tiny_wae.core.sites import Site
from tiny_wae.core.windows import Window

runner = CliRunner()

SITES_PATH = Path("config/sites.yaml")
SETTINGS_PATH = Path("config/settings.yaml")
MANIFESTS_ROOT = Path("tests/fixtures/manifests")
STAC_FIXTURES_ROOT = Path("tests/fixtures/stac")


class _FixtureSource:
    """Double de test de ``StacSource`` — rejoue une fixture ``/search`` enregistrée
    (même convention que ``tests/test_cli_search.py::_FixtureSource``)."""

    def __init__(self, fixture_name: str, *, reference_tile: str) -> None:
        data = json.loads((STAC_FIXTURES_ROOT / fixture_name).read_text(encoding="utf-8"))
        self._raw_items = list(data["items"])
        self._reference_tile = reference_tile

    def search(self, site: Site, window: Window) -> Envelope:
        return build_envelope(
            site_id=site.id,
            window=window,
            raw_items=self._raw_items,
            reference_tile=self._reference_tile,
            scene_cloud_max=95,
            asset_keys=EXPECTED_ASSET_KEYS,
        )


def _patch_source(monkeypatch: pytest.MonkeyPatch, source: StacSource) -> None:
    monkeypatch.setattr(report_module, "build_source", lambda settings: source)


# ── O1/O4 : mode rapport par défaut ──────────────────────────────────────────────────────


def test_o1_report_defaut_ecrit_le_site_c07_avec_les_comptes_mesures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``report`` (sans ``--check-completeness``) sur ``TINY_WAE_DATA_ROOT`` pointé vers le
    corpus fixtures : le site C07 apparaît dans le Markdown avec les comptes mesurés,
    exit OK, fichier écrit."""
    monkeypatch.setenv("TINY_WAE_DATA_ROOT", str(MANIFESTS_ROOT))
    out_path = tmp_path / "report.md"

    result = runner.invoke(
        app,
        [
            "report",
            "--out",
            str(out_path),
            "--sites-path",
            str(SITES_PATH),
            "--settings-path",
            str(SETTINGS_PATH),
        ],
    )

    assert result.exit_code == exit_codes.OK, result.output
    assert out_path.exists()
    markdown = out_path.read_text(encoding="utf-8")
    assert "| C07 | 15 | 1 | 2 | 12 | 6 | 3 | 1 | 1 | 1 | 0 |" in markdown


# ── O2ter (wiring CLI) : --check-completeness sur C07 ────────────────────────────────────


def test_o2ter_check_completeness_ok_sur_fixture_c07(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Fixture ``c07_completeness.json`` : les 12 ids réels (found_tile de C07) + 1 item
    écarté par le pré-filtre scène + 2 items hors-tuile -> écart 0 malgré les 2 pièges,
    exit OK, STDERR nomme le site en 'complétude=OK'."""
    monkeypatch.setenv("TINY_WAE_DATA_ROOT", str(MANIFESTS_ROOT))
    _patch_source(monkeypatch, _FixtureSource("c07_completeness.json", reference_tile="52TEL"))

    result = runner.invoke(
        app,
        [
            "report",
            "--check-completeness",
            "--sites",
            "C07",
            "--from",
            "2026-01-01",
            "--to",
            "2026-02-01",
            "--sites-path",
            str(SITES_PATH),
            "--settings-path",
            str(SETTINGS_PATH),
        ],
    )

    assert result.exit_code == exit_codes.OK, result.output
    assert "site=C07" in result.output
    assert "complétude=OK" in result.output


def test_o2ter_check_completeness_rouge_id_manquant_nomme(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Fixture MUTÉE (retire ``S2A_C07_ING01``) : ROUGE, exit FAILURE, l'id manquant est
    nommé littéralement sur STDERR."""
    monkeypatch.setenv("TINY_WAE_DATA_ROOT", str(MANIFESTS_ROOT))
    raw = json.loads((STAC_FIXTURES_ROOT / "c07_completeness.json").read_text(encoding="utf-8"))
    raw["items"] = [it for it in raw["items"] if it["id"] != "S2A_C07_ING01"]
    mutated_path = tmp_path / "c07_completeness_mutated.json"
    mutated_path.write_text(json.dumps(raw), encoding="utf-8")

    class _MutatedSource:
        def search(self, site: Site, window: Window) -> Envelope:
            raw_items = json.loads(mutated_path.read_text(encoding="utf-8"))["items"]
            return build_envelope(
                site_id=site.id,
                window=window,
                raw_items=raw_items,
                reference_tile="52TEL",
                scene_cloud_max=95,
                asset_keys=EXPECTED_ASSET_KEYS,
            )

    _patch_source(monkeypatch, _MutatedSource())

    result = runner.invoke(
        app,
        [
            "report",
            "--check-completeness",
            "--sites",
            "C07",
            "--from",
            "2026-01-01",
            "--to",
            "2026-02-01",
            "--sites-path",
            str(SITES_PATH),
            "--settings-path",
            str(SETTINGS_PATH),
        ],
    )

    assert result.exit_code == exit_codes.FAILURE, result.output
    assert "complétude=ROUGE" in result.output
    assert "S2A_C07_ING01" in result.output


def test_usage_check_completeness_sans_sites_est_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--check-completeness`` sans ``--sites``/``--from``/``--to`` -> exit USAGE (2)."""
    monkeypatch.setenv("TINY_WAE_DATA_ROOT", str(MANIFESTS_ROOT))
    result = runner.invoke(
        app,
        [
            "report",
            "--check-completeness",
            "--sites-path",
            str(SITES_PATH),
            "--settings-path",
            str(SETTINGS_PATH),
        ],
    )
    assert result.exit_code == exit_codes.USAGE
