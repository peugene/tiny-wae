"""Tests cli/update.py (l0-05.2) — wiring : `--sites`, `--now`, codes de sortie.

Config isolée (sites.yaml/settings.yaml sous `tmp_path`), `build_source` (point de
couture PROPRE à ce module, même convention que `cli/ingest.py`/`cli/search.py`)
monkeypatché — aucun test ici ne fait de réseau, aucun ne dort (`ingestion_module._sleep`
neutralisé). Le volet business (O1/O2/O3, classification réseau vs applicatif) est
couvert en profondeur par `tests/test_update.py` (fixtures réelles) : ici on vérifie que
le CLI mappe correctement des `SiteUpdateResult` déjà produits sur les bons codes de
sortie et messages, avec une boucle réduite à 2 sites synthétiques.

Couvre l'oracle de la fiche, volet CLI :
- O4 : site vierge -> exit FAILURE (1), message nommant `backfill`.
- O5 : échec injecté sur 1 site (2e OK) -> exit FAILURE (1), compteurs des 2 sites visibles.
- O5bis : amont injoignable sur TOUS les sites (déjà manifestés) -> exit INCONCLUSIVE (3),
  distinct de O5 et du site vierge (O4).
- `--sites` : filtre CSV, `all` par défaut, id inconnu -> USAGE (2).
- `--now` : mal formé -> USAGE (2) ; rappel du rattrapage mensuel affiché le 1er du mois.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import tiny_wae.adapters.ingestion as ingestion_module
import tiny_wae.cli.update as update_module
from tiny_wae.__main__ import app
from tiny_wae.adapters.manifests import Manifest, write_manifest
from tiny_wae.adapters.stac import StacSource, StacUnreachable
from tiny_wae.cli import exit_codes
from tiny_wae.core.envelope import Envelope
from tiny_wae.core.sites import Site
from tiny_wae.core.windows import Window

runner = CliRunner()

_SITE_1 = "T01"
_SITE_2 = "T02"


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise l'attente de backoff (règle du dépôt : aucun test ne doit dormir)."""
    monkeypatch.setattr(ingestion_module, "_sleep", lambda seconds: None)


def _write_config(tmp_path: Path) -> tuple[Path, Path, Path]:
    """sites.yaml (2 sites, grilles posées) + settings.yaml isolés. Rend (sites,
    settings, data_root)."""
    data_root = tmp_path / "data"
    sites_path = tmp_path / "sites.yaml"
    settings_path = tmp_path / "settings.yaml"
    sites_path.write_text(
        f"""
sites:
  - id: {_SITE_1}
    name: "Site 1"
    lat: 43.0
    lon: 5.0
    category: stable-watch
    note: ""
    reference_tile: "31TCJ"
    grid:
      epsg: 32631
      origin_x: 699960.0
      origin_y: 4900020.0
  - id: {_SITE_2}
    name: "Site 2"
    lat: 44.0
    lon: 6.0
    category: stable-watch
    note: ""
    reference_tile: "31TCJ"
    grid:
      epsg: 32631
      origin_x: 699960.0
      origin_y: 4900020.0
""",
        encoding="utf-8",
    )
    settings_path.write_text(
        f"""
stac_url: "https://example.invalid/stac"
stac_collection: "sentinel-2-l2a"
data_root: "{data_root.as_posix()}"
http_retries: 1
http_backoff_s: 1
""",
        encoding="utf-8",
    )
    return sites_path, settings_path, data_root


def _seed_manifest(data_root: Path, site_id: str, item_id: str, dt: str) -> None:
    """Écrit un manifeste minimal valide — établit `last_datetime` sans passer par une
    ingestion réelle (aucune raster nécessaire pour les tests de mapping du CLI)."""
    write_manifest(
        data_root,
        Manifest(
            schema_version=1,
            site_id=site_id,
            item_id=item_id,
            datetime=dt,
            tile="31TCJ",
            sequence="0",
            platform="sentinel-2a",
            status="ingested",
            cause=None,
            invalid_pct=0.0,
            cloud_pct=0.0,
            chip_nodata_pct=0.0,
            scl_class_counts={},
            processing_baseline="99.9",
            boa_offset_applied=True,
            radiometry={},
            grid_hash="deadbeef",
            assets_read=1,
            content_hashes={},
            bytes_downloaded=0,
            bytes_written=1,
            duration_s=0.01,
            files=[],
            versions={"tiny_wae": "0.0.0"},
        ),
    )


def _empty_envelope(site_id: str) -> Envelope:
    """Enveloppe "rien de nouveau" — prouve qu'un site a été traité (compteurs à zéro,
    `run.json` écrit) sans nécessiter de raster synthétique."""
    return Envelope(
        schema_version=1,
        site_id=site_id,
        window={"start": "2026-01-01T00:00:00", "end": "2026-02-01T00:00:00"},
        counters={"found_stac": 0, "skipped_scene_cloud": 0, "off_tile": 0, "found_tile": 0},
        items=[],
    )


class _MultiSiteSource:
    """Double `StacSource` : rend une enveloppe vide OU lève l'exception mappée par id de
    site — aucun réseau, aucun raster nécessaire."""

    def __init__(self, per_site: dict[str, Exception | None]) -> None:
        self._per_site = per_site

    def search(self, site: Site, window: Window) -> Envelope:
        exc = self._per_site.get(site.id)
        if exc is not None:
            raise exc
        return _empty_envelope(site.id)


def _patch_source(monkeypatch: pytest.MonkeyPatch, source: StacSource) -> None:
    monkeypatch.setattr(update_module, "build_source", lambda settings: source)


# ── O4 : site vierge -> exit FAILURE (1), message backfill ──────────────────────────


def test_o4_site_vierge_exit_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sites_path, settings_path, data_root = _write_config(tmp_path)
    _patch_source(monkeypatch, _MultiSiteSource({}))
    data_root.mkdir(parents=True)  # data_root existe, mais AUCUN manifeste pour T01/T02.

    result = runner.invoke(
        app,
        [
            "update",
            "--sites",
            _SITE_1,
            "--now",
            "2026-01-15",
            "--sites-path",
            str(sites_path),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.FAILURE
    assert result.exit_code == 1
    assert "status=vierge" in result.stderr
    assert "backfill" in result.stderr


# ── O5 : échec injecté sur 1 site, l'autre OK -> exit FAILURE (1) ───────────────────


def test_o5_un_site_echoue_lautre_ok_exit_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sites_path, settings_path, data_root = _write_config(tmp_path)
    _seed_manifest(data_root, _SITE_1, "ITEM_1", "2026-01-01T00:00:00Z")
    _seed_manifest(data_root, _SITE_2, "ITEM_2", "2026-01-01T00:00:00Z")
    _patch_source(
        monkeypatch,
        _MultiSiteSource({_SITE_1: ValueError("bug applicatif simulé")}),
    )

    result = runner.invoke(
        app,
        [
            "update",
            "--now",
            "2026-01-15",
            "--sites-path",
            str(sites_path),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.FAILURE
    assert result.exit_code == 1
    assert f"site={_SITE_1}  status=failed" in result.stderr
    assert f"site={_SITE_2}  status=up_to_date" in result.stderr
    assert "2 sites, 0 avec du nouveau, 1 à jour, 1 échecs" in result.stderr


# ── O5bis : amont injoignable sur TOUS les sites -> exit INCONCLUSIVE (3) ───────────


def test_o5bis_tous_injoignables_exit_inconclusive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Distinct de O5 (exit 1, ci-dessus) ET du site vierge (O4, exit 1) : ici les DEUX
    sites ont déjà des manifestes (pas vierges) et échouent tous deux pour une raison
    réseau -> exit 3, pas 1."""
    sites_path, settings_path, data_root = _write_config(tmp_path)
    _seed_manifest(data_root, _SITE_1, "ITEM_1", "2026-01-01T00:00:00Z")
    _seed_manifest(data_root, _SITE_2, "ITEM_2", "2026-01-01T00:00:00Z")
    unreachable = StacUnreachable("https://example.invalid/stac injoignable (simulé)")
    _patch_source(monkeypatch, _MultiSiteSource({_SITE_1: unreachable, _SITE_2: unreachable}))

    result = runner.invoke(
        app,
        [
            "update",
            "--now",
            "2026-01-15",
            "--sites-path",
            str(sites_path),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.INCONCLUSIVE
    assert result.exit_code == 3
    assert result.exit_code != exit_codes.FAILURE


def test_exit_ok_sans_echec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Aucun site vierge, aucun échec -> exit OK (0), même si rien de nouveau."""
    sites_path, settings_path, data_root = _write_config(tmp_path)
    _seed_manifest(data_root, _SITE_1, "ITEM_1", "2026-01-01T00:00:00Z")
    _seed_manifest(data_root, _SITE_2, "ITEM_2", "2026-01-01T00:00:00Z")
    _patch_source(monkeypatch, _MultiSiteSource({}))

    result = runner.invoke(
        app,
        [
            "update",
            "--now",
            "2026-01-15",
            "--sites-path",
            str(sites_path),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.OK
    assert "2 sites, 0 avec du nouveau, 2 à jour, 0 échecs" in result.stderr


# ── --sites : filtre CSV / all / id inconnu ──────────────────────────────────────────


def test_sites_all_par_defaut_traite_les_deux_sites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sites_path, settings_path, data_root = _write_config(tmp_path)
    _patch_source(monkeypatch, _MultiSiteSource({}))

    result = runner.invoke(
        app,
        [
            "update",
            "--now",
            "2026-01-15",
            "--sites-path",
            str(sites_path),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert f"site={_SITE_1}" in result.stderr
    assert f"site={_SITE_2}" in result.stderr


def test_sites_csv_filtre_un_seul_site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sites_path, settings_path, data_root = _write_config(tmp_path)
    _patch_source(monkeypatch, _MultiSiteSource({}))

    result = runner.invoke(
        app,
        [
            "update",
            "--sites",
            _SITE_2,
            "--now",
            "2026-01-15",
            "--sites-path",
            str(sites_path),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert f"site={_SITE_2}" in result.stderr
    assert f"site={_SITE_1}" not in result.stderr
    assert "1 sites" in result.stderr


def test_sites_id_inconnu_usage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sites_path, settings_path, data_root = _write_config(tmp_path)
    _patch_source(monkeypatch, _MultiSiteSource({}))

    result = runner.invoke(
        app,
        [
            "update",
            "--sites",
            "INCONNU",
            "--now",
            "2026-01-15",
            "--sites-path",
            str(sites_path),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.USAGE


# ── --now : mal formé -> USAGE ; rappel mensuel le 1er du mois ──────────────────────


def test_now_mal_forme_usage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sites_path, settings_path, data_root = _write_config(tmp_path)
    _patch_source(monkeypatch, _MultiSiteSource({}))

    result = runner.invoke(
        app,
        [
            "update",
            "--now",
            "pas-une-date",
            "--sites-path",
            str(sites_path),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.USAGE


def test_rappel_rattrapage_mensuel_le_premier_du_mois(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sites_path, settings_path, data_root = _write_config(tmp_path)
    _patch_source(monkeypatch, _MultiSiteSource({}))

    result = runner.invoke(
        app,
        [
            "update",
            "--now",
            "2026-02-01",
            "--sites-path",
            str(sites_path),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert "rattrapage mensuel" in result.stderr

    result_autre_jour = runner.invoke(
        app,
        [
            "update",
            "--now",
            "2026-02-02",
            "--sites-path",
            str(sites_path),
            "--settings-path",
            str(settings_path),
        ],
    )
    assert "rattrapage mensuel" not in result_autre_jour.stderr
