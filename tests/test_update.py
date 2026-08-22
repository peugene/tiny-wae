"""Tests adapters/update.py (l0-05.2) — boucle par site du run quotidien.

Aucun test ici ne fait de réseau (``FixtureSource`` sert le corpus enregistré, pystac_client
n'est jamais construit ; les cas d'échec injectent des exceptions directement). Aucun test
ne dort (``ingestion_module._sleep`` neutralisé).

Couvre l'oracle de la fiche, volet adapter (le volet CLI — codes de sortie, ``--sites``,
``--now`` — vit dans ``tests/test_cli_update.py``) :

- O1 : fixture réelle A01 — 2 items nouveaux (21 et 26 sept. 2022) après ingestion d'une
  sous-fenêtre (01-16 sept.) — ``ingested == 2`` EXACTEMENT (témoin positif).
- O2 : ``update`` x2 d'affilée (même ``now``) — 1er `assets_read > 0`, 2e `ingested == 0`
  ET `assets_read == 0`.
- O3 : trou simulé sur A01 (manifestes du dernier mois retirés), restauré à l'identique ;
  hashes des manifestes B09 inchangés.
- O4 : site sans aucun manifeste -> statut `vierge`, message nommant `backfill`.
- O5 (volet adapter) : échec injecté sur 1 site (B09), l'autre (A01, fixture réelle)
  traité normalement -> ses compteurs le prouvent.
- O5bis (volet adapter) : amont injoignable sur TOUS les sites -> tous `failed`,
  `is_network_failure=True`.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

import pytest

import tiny_wae.adapters.ingestion as ingestion_module
from tiny_wae.adapters.config_io import DEFAULT_SITES_PATH, load_settings, load_sites
from tiny_wae.adapters.fixture_source import FixtureSource
from tiny_wae.adapters.ingestion import ingest_from_source
from tiny_wae.adapters.manifests import list_for_site
from tiny_wae.adapters.stac import StacSource, StacUnreachable
from tiny_wae.adapters.update import (
    FAILED,
    UP_TO_DATE,
    UPDATED,
    VIERGE,
    SiteUpdateResult,
    update_all,
    update_site,
)
from tiny_wae.core.envelope import Envelope
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Site
from tiny_wae.core.windows import Window


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise l'attente de backoff (règle du dépôt : aucun test ne doit dormir)."""
    monkeypatch.setattr(ingestion_module, "_sleep", lambda seconds: None)


def _sites() -> dict[str, Site]:
    """Sites RÉELS de ``config/sites.yaml`` — le corpus de fixtures est indexé dessus."""
    return {site.id: site for site in load_sites(DEFAULT_SITES_PATH)}


def _settings() -> Settings:
    return load_settings()


class _RaisingSource:
    """Double levant systématiquement `exc` — simule un site injoignable ou en échec
    applicatif, sans jamais toucher au réseau."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def search(self, site: Site, window: Window) -> Envelope:
        raise self._exc


class _PartialFailureSource:
    """Délègue à `delegate` (ex. `FixtureSource` réelle) sauf pour `failing_site_id`, où
    `exc` est levée — c'est ce qui permet de tester l'isolement par site (O5) SANS
    fabriquer de rasters synthétiques : le site "témoin" est traité par le vrai pipeline."""

    def __init__(self, delegate: StacSource, *, failing_site_id: str, exc: Exception) -> None:
        self._delegate = delegate
        self._failing_site_id = failing_site_id
        self._exc = exc

    def search(self, site: Site, window: Window) -> Envelope:
        if site.id == self._failing_site_id:
            raise self._exc
        return self._delegate.search(site, window)


# ── O1 / O2 : sous-fenêtre A01 puis update (recette de l'ancrage n°3) ────────────────


def _seed_a01_sub_window(data_root: Path) -> None:
    """Ingère A01 sur [01-17 sept. 2022] (4 items : 2 rejected_clouds, 2 ingested) —
    l'état initial d'où O1/O2 mesurent les items "nouveaux"."""
    settings = _settings()
    source = FixtureSource(settings=settings)
    window = Window(start=datetime(2022, 9, 1), end=datetime(2022, 9, 17))
    ingest_from_source(
        site=_sites()["A01"], window=window, source=source, settings=settings, data_root=data_root
    )


def test_o1_deux_items_nouveaux_exactement(tmp_path: Path) -> None:
    """O1, témoin positif : après la sous-fenêtre, `update` au 26 sept. découvre EXACTEMENT
    2 items nouveaux (21 et 26 sept., les seuls ingérés de la fin de fenêtre) — un `update`
    inopérant (qui ne rechercherait rien, ou toute la fenêtre déjà vue) échoue ici."""
    data_root = tmp_path / "data"
    _seed_a01_sub_window(data_root)
    settings = _settings()
    source = FixtureSource(settings=settings)

    result = update_site(
        site=_sites()["A01"],
        settings=settings,
        source=source,
        data_root=data_root,
        now=datetime(2022, 9, 26, 12, 0, 0),
    )

    assert result.status == UPDATED
    assert result.ingested == 2
    ids = {m.item_id for m in list_for_site(data_root, "A01") if m.status == "ingested"}
    assert "S2A_31TGJ_20220921_0_L2A" in ids
    assert "S2B_31TGJ_20220926_0_L2A" in ids


def test_o2_update_deux_fois_daffilee(tmp_path: Path) -> None:
    """O2 : 1er `update` (sur l'état d'O1) -> `assets_read > 0` ; 2e `update`, MÊME `now`
    -> `ingested == 0` ET `assets_read == 0` (rien de nouveau, rien relu)."""
    data_root = tmp_path / "data"
    _seed_a01_sub_window(data_root)
    settings = _settings()
    source = FixtureSource(settings=settings)
    now = datetime(2022, 9, 26, 12, 0, 0)

    first = update_site(
        site=_sites()["A01"], settings=settings, source=source, data_root=data_root, now=now
    )
    assert first.assets_read > 0

    second = update_site(
        site=_sites()["A01"], settings=settings, source=source, data_root=data_root, now=now
    )
    assert second.status == UP_TO_DATE
    assert second.ingested == 0
    assert second.assets_read == 0


# ── O3 : trou simulé sur A01, restauré à l'identique — B09 inchangé ──────────────────


def _b09_manifest_hashes(data_root: Path) -> dict[str, str]:
    """sha256 du contenu brut de chaque `manifest.json` de B09 (ordre par item_id)."""
    site_dir = data_root / "B09"
    return {
        str(p.relative_to(data_root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(site_dir.rglob("manifest.json"))
    }


def test_o3_trou_simule_restaure_a_lidentique(tmp_path: Path) -> None:
    """Ingestion complète de sept. 2022 sur A01 (6 items) + un run B09 témoin. On retire
    les manifestes des 2 derniers items (21, 26 sept. — "le dernier mois"), on relance
    `update` : l'ensemble (item_id, statut) de A01 est restauré À L'IDENTIQUE, et les
    hashes des manifestes de B09 n'ont pas bougé (aucune écriture croisée entre sites)."""
    data_root = tmp_path / "data"
    settings = _settings()
    source = FixtureSource(settings=settings)
    sites = _sites()

    full_window = Window(start=datetime(2022, 9, 1), end=datetime(2022, 10, 1))
    ingest_from_source(
        site=sites["A01"], window=full_window, source=source, settings=settings, data_root=data_root
    )
    b09_window = Window(start=datetime(2023, 8, 1), end=datetime(2023, 9, 1))
    ingest_from_source(
        site=sites["B09"], window=b09_window, source=source, settings=settings, data_root=data_root
    )

    baseline = {m.item_id: m.status for m in list_for_site(data_root, "A01")}
    assert len(baseline) == 6  # les 6 items de sept. 2022 (cf. ancrage de la fiche).
    b09_hashes_before = _b09_manifest_hashes(data_root)
    assert b09_hashes_before  # B09 a bien des manifestes à comparer.

    # Le "trou" : on retire les 2 items du dernier mois (21 et 26 sept.).
    for item_id in ("S2A_31TGJ_20220921_0_L2A", "S2B_31TGJ_20220926_0_L2A"):
        item_dir = data_root / "A01" / item_id
        for f in item_dir.iterdir():
            f.unlink()
        item_dir.rmdir()
    assert len(list_for_site(data_root, "A01")) == 4

    result = update_site(
        site=sites["A01"],
        settings=settings,
        source=source,
        data_root=data_root,
        now=datetime(2022, 9, 26, 12, 0, 0),
    )

    assert result.status == UPDATED
    restored = {m.item_id: m.status for m in list_for_site(data_root, "A01")}
    assert restored == baseline

    assert _b09_manifest_hashes(data_root) == b09_hashes_before


# ── O4 : site vierge ──────────────────────────────────────────────────────────────────


def test_o4_site_vierge_statut_et_message_backfill(tmp_path: Path) -> None:
    """Aucun manifeste pour le site -> statut `vierge`, message nommant `backfill` — pas
    une exception, pas un `failed`."""
    data_root = tmp_path / "data"
    settings = _settings()
    source = FixtureSource(settings=settings)

    result = update_site(
        site=_sites()["A01"],
        settings=settings,
        source=source,
        data_root=data_root,
        now=datetime(2022, 9, 26),
    )

    assert result.status == VIERGE
    assert result.ingested == 0
    assert result.assets_read == 0
    assert result.message is not None
    assert "backfill" in result.message


# ── O5 (volet adapter) : échec injecté sur 1 site, l'autre traité réellement ─────────


def test_o5_echec_un_site_lautre_traite_reellement(tmp_path: Path) -> None:
    """B09 échoue (exception applicative, PAS réseau) ; A01 est traité par le VRAI
    pipeline (fixtures réelles) sur la même boucle -> ses compteurs le prouvent
    (`ingested == 2`, identique à O1)."""
    data_root = tmp_path / "data"
    settings = _settings()
    sites = _sites()
    delegate = FixtureSource(settings=settings)

    _seed_a01_sub_window(data_root)
    # B09 a besoin d'un manifeste préalable pour ne pas être "vierge" (ce n'est pas ce
    # que ce test vérifie) : un run réel minimal suffit.
    ingest_from_source(
        site=sites["B09"],
        window=Window(start=datetime(2023, 8, 1), end=datetime(2023, 8, 24)),
        source=delegate,
        settings=settings,
        data_root=data_root,
    )

    source = _PartialFailureSource(
        delegate, failing_site_id="B09", exc=ValueError("bug applicatif simulé")
    )

    results = update_all(
        sites=[sites["A01"], sites["B09"]],
        settings=settings,
        source=source,
        data_root=data_root,
        now=datetime(2022, 9, 26, 12, 0, 0),
    )

    by_id = {r.site_id: r for r in results}
    assert by_id["A01"].status == UPDATED
    assert by_id["A01"].ingested == 2
    assert by_id["B09"].status == FAILED
    assert by_id["B09"].is_network_failure is False


# ── O5bis (volet adapter) : amont injoignable sur TOUS les sites ────────────────────


def test_o5bis_tous_les_sites_injoignables(tmp_path: Path) -> None:
    """`StacUnreachable` sur les 2 sites (déjà manifestés, donc pas `vierge`) -> tous
    `failed`, `is_network_failure=True` pour les deux — c'est le CLI qui en fera
    l'INCONCLUSIVE (3), testé séparément dans `test_cli_update.py`."""
    data_root = tmp_path / "data"
    settings = _settings()
    sites = _sites()
    delegate = FixtureSource(settings=settings)

    _seed_a01_sub_window(data_root)
    ingest_from_source(
        site=sites["B09"],
        window=Window(start=datetime(2023, 8, 1), end=datetime(2023, 8, 24)),
        source=delegate,
        settings=settings,
        data_root=data_root,
    )

    source = _RaisingSource(StacUnreachable("endpoint injoignable (simulé)"))

    results = update_all(
        sites=[sites["A01"], sites["B09"]],
        settings=settings,
        source=source,
        data_root=data_root,
        now=datetime(2022, 9, 26, 12, 0, 0),
    )

    assert all(r.status == FAILED for r in results)
    assert all(r.is_network_failure for r in results)


# ── Structure : update_all rend un résultat par site, dans l'ordre ──────────────────


def test_update_all_un_resultat_par_site_dans_lordre(tmp_path: Path) -> None:
    """`update_all` rend exactement `len(sites)` résultats, dans l'ordre d'entrée."""
    data_root = tmp_path / "data"
    settings = _settings()
    sites = _sites()
    source = FixtureSource(settings=settings)

    results: list[SiteUpdateResult] = update_all(
        sites=[sites["B09"], sites["A01"]],
        settings=settings,
        source=source,
        data_root=data_root,
        now=datetime(2022, 9, 26),
    )

    assert [r.site_id for r in results] == ["B09", "A01"]
    assert all(r.status == VIERGE for r in results)  # aucun manifeste pré-existant ici.
