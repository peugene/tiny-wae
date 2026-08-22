"""Tests cli/backfill.py (l0-04.1) — wiring : options, codes de sortie, `build_source`
monkeypatché vers ``FixtureSource`` (aucun réseau). ``config/sites.yaml`` réel (A01/B09,
grilles déjà posées) ; ``config/settings.yaml`` recopié avec un ``data_root`` isolé sous
``tmp_path``.

Couvre :
- O1 : `backfill --sites A01 --months 1 --workers 4 --now <fenêtre du corpus>` -> exit OK,
  compteurs gelés sur STDERR (found_stac=6 ...).
- O2 : échec injecté sur B09 -> exit FAILURE, site fautif nommé sur STDERR, A01 complet.
- O2bis : amont injoignable sur les 2 sites demandés -> exit INCONCLUSIVE.
- usage : `--sites` avec un id inconnu -> exit USAGE, AVANT toute soumission au pool.
- `--workers` par défaut = `settings.backfill_workers` quand l'option est omise.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from typer.testing import CliRunner

import tiny_wae.cli.backfill as backfill_module
from tiny_wae.__main__ import app
from tiny_wae.adapters.config_io import DEFAULT_SITES_PATH
from tiny_wae.adapters.fixture_source import FixtureSource
from tiny_wae.adapters.manifests import list_for_site
from tiny_wae.adapters.stac import StacSource, StacUnreachable
from tiny_wae.cli import exit_codes
from tiny_wae.core.envelope import Envelope
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Site
from tiny_wae.core.windows import Window

runner = CliRunner()

# Date qui, via `backfill_windows(1, now)`, rend la fenêtre [2022-09-01, 2022-09-30[ —
# couvre exactement les 6 items de septembre 2022 du corpus A01 (ancrage de la fiche).
_NOW_SEPT_2022 = "2022-09-30"


def _write_settings(tmp_path: Path, *, data_root: Path) -> Path:
    """Recopie ``config/settings.yaml`` réel avec un ``data_root`` isolé sous tmp_path —
    mêmes chip_px_10m/20m que le corpus enregistré (l0-03.5), sans quoi les chips ne
    matcheraient pas la taille des fixtures COG."""
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        f"""
stac_url: "https://earth-search.aws.element84.com/v1"
stac_collection: "sentinel-2-l2a"
cloud_pct_max: 30
scene_cloud_max: 95
invalid_pct_max: 1
chip_nodata_pct_max: 1
data_root: "{data_root.as_posix()}"
incremental_margin_days: 3
http_retries: 1
http_backoff_s: 1
backfill_workers: 6
chip_px_10m: 512
chip_px_20m: 256
""",
        encoding="utf-8",
    )
    return settings_path


@dataclass(frozen=True, slots=True)
class _FailingSiteSource:
    """Double ``StacSource`` qui échoue TOUJOURS pour un site donné, délègue à une source
    réelle pour les autres — même double que ``tests/test_backfill.py``, dupliqué ici
    plutôt que partagé via un module utilitaire (fiche : 2 fichiers de test autorisés,
    aucun troisième)."""

    delegate: StacSource
    failing_site_id: str

    def search(self, site: Site, window: Window) -> Envelope:
        if site.id == self.failing_site_id:
            raise ValueError(f"panne injectée pour {site.id}")
        return self.delegate.search(site, window)


@dataclass(frozen=True, slots=True)
class _AlwaysUnreachableSource:
    """Double ``StacSource`` qui lève ``StacUnreachable`` pour TOUT site (O2bis)."""

    def search(self, site: Site, window: Window) -> Envelope:
        raise StacUnreachable(f"amont injoignable pour {site.id}")


def _patch_source(monkeypatch: pytest.MonkeyPatch, source: StacSource) -> None:
    monkeypatch.setattr(backfill_module, "build_source", lambda settings: source)


def test_backfill_a01_septembre_2022_exit_ok_compteurs_geles_o1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O1 : `--sites A01 --months 1 --workers 4 --now 2022-09-30` -> exit OK, compteurs
    GELÉS EN LITTÉRAL sur STDERR (found_stac=6, skipped_scene_cloud=0, off_tile=0,
    found_tile=6)."""
    data_root = tmp_path / "data"
    settings_path = _write_settings(tmp_path, data_root=data_root)
    settings = Settings(
        stac_url="https://earth-search.aws.element84.com/v1",
        stac_collection="sentinel-2-l2a",
        data_root=str(data_root),
    )
    _patch_source(monkeypatch, FixtureSource(settings=settings))

    result = runner.invoke(
        app,
        [
            "backfill",
            "--sites",
            "A01",
            "--months",
            "1",
            "--workers",
            "4",
            "--now",
            _NOW_SEPT_2022,
            "--sites-path",
            str(DEFAULT_SITES_PATH),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.OK, result.output
    assert "'found_stac': 6" in result.output
    assert "'skipped_scene_cloud': 0" in result.output
    assert "'off_tile': 0" in result.output
    assert "'found_tile': 6" in result.output
    assert len(list_for_site(data_root, "A01")) == 6


def test_backfill_echec_sur_1_site_exit_failure_site_nomme_o2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O2 : échec injecté sur B09 -> exit FAILURE (1), B09 nommé sur STDERR, A01 complet
    malgré l'échec."""
    data_root = tmp_path / "data"
    settings_path = _write_settings(tmp_path, data_root=data_root)
    settings = Settings(
        stac_url="https://earth-search.aws.element84.com/v1",
        stac_collection="sentinel-2-l2a",
        data_root=str(data_root),
    )
    source = _FailingSiteSource(delegate=FixtureSource(settings=settings), failing_site_id="B09")
    _patch_source(monkeypatch, source)

    result = runner.invoke(
        app,
        [
            "backfill",
            "--sites",
            "A01,B09",
            "--months",
            "1",
            "--workers",
            "4",
            "--now",
            _NOW_SEPT_2022,
            "--sites-path",
            str(DEFAULT_SITES_PATH),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.FAILURE, result.output
    assert "['B09']" in result.output
    assert len(list_for_site(data_root, "A01")) == 6


def test_backfill_amont_injoignable_partout_exit_inconclusive_o2bis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O2bis : amont injoignable sur les 2 sites demandés -> exit INCONCLUSIVE (3),
    distinct de O2."""
    data_root = tmp_path / "data"
    settings_path = _write_settings(tmp_path, data_root=data_root)
    _patch_source(monkeypatch, _AlwaysUnreachableSource())

    result = runner.invoke(
        app,
        [
            "backfill",
            "--sites",
            "A01,B09",
            "--months",
            "1",
            "--now",
            _NOW_SEPT_2022,
            "--sites-path",
            str(DEFAULT_SITES_PATH),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.INCONCLUSIVE, result.output


def test_backfill_site_inconnu_exit_usage_avant_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--sites` avec un id inconnu -> exit USAGE (2), AVANT toute soumission au pool
    (aucun manifeste écrit)."""
    data_root = tmp_path / "data"
    settings_path = _write_settings(tmp_path, data_root=data_root)

    called = {"count": 0}

    class _CountingSource:
        def search(self, site: Site, window: Window) -> Envelope:
            called["count"] += 1
            raise AssertionError("ne doit jamais être appelé : usage invalide en amont")

    _patch_source(monkeypatch, _CountingSource())

    result = runner.invoke(
        app,
        [
            "backfill",
            "--sites",
            "ZZZ99",
            "--months",
            "1",
            "--now",
            _NOW_SEPT_2022,
            "--sites-path",
            str(DEFAULT_SITES_PATH),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.USAGE, result.output
    assert called["count"] == 0
    assert not data_root.exists()


def test_backfill_workers_defaut_vient_des_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sans `--workers`, le CLI passe `settings.backfill_workers` (ici forcé à 2 dans le
    fichier écrit) à l'orchestrateur — vérifié en interceptant `run_backfill`."""
    data_root = tmp_path / "data"
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        f"""
stac_url: "https://earth-search.aws.element84.com/v1"
stac_collection: "sentinel-2-l2a"
data_root: "{data_root.as_posix()}"
backfill_workers: 2
""",
        encoding="utf-8",
    )
    settings = Settings(
        stac_url="https://earth-search.aws.element84.com/v1",
        stac_collection="sentinel-2-l2a",
        data_root=str(data_root),
    )
    _patch_source(monkeypatch, FixtureSource(settings=settings))

    seen_workers: dict[str, int] = {}
    real_run_backfill = backfill_module.run_backfill

    def _spy_run_backfill(**kwargs: object) -> object:
        seen_workers["workers"] = kwargs["workers"]  # type: ignore[assignment]
        return real_run_backfill(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(backfill_module, "run_backfill", _spy_run_backfill)

    result = runner.invoke(
        app,
        [
            "backfill",
            "--sites",
            "A01",
            "--months",
            "1",
            "--now",
            _NOW_SEPT_2022,
            "--sites-path",
            str(DEFAULT_SITES_PATH),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.OK, result.output
    assert seen_workers["workers"] == 2
