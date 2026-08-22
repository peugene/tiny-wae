"""Tests adapters/backfill.py (l0-04.1) — boucle sites × fenêtres, pool, isolation par
site, interruption propre. Tout sur ``FixtureSource`` (corpus réel de l0-03.5) ou sur des
doubles ``StacSource`` en mémoire — aucun réseau, aucun ``time.sleep`` réel.

Couvre l'oracle de la fiche :
- O1 : déterminisme du pool (``--workers`` 4 vs 1 -> même ensemble (item_id, statut)) +
  compteurs GELÉS EN LITTÉRAL sur A01 × sept. 2022 (found_stac=6 ...).
- O2 : échec injecté sur 1 site / 2 -> l'autre site complet, ``failed_site_ids`` nomme le
  fautif, l'ensemble n'est PAS interrompu.
- O2bis : amont injoignable sur TOUS les sites -> ``all_failures_network`` vrai.
- O3 : le gestionnaire de signal (fonction pure, appelée directement, PAS un vrai signal)
  arrête les nouvelles soumissions, attend les tâches en cours, et 100 % des manifestes
  présents restent relisibles.
- O4 : run double — 1er run assets_read > 0, 2e run assets_read == 0, 100 % skipped,
  content_hashes identiques.

⚠ Ancrage de la fiche : les corpus A01 (sept. 2022) et B09 (août 2023) ne se recouvrent
PAS dans le temps — chaque test multi-sites construit ses fenêtres PAR SITE via
``windows_by_site`` (jamais une fenêtre unique partagée), et B09 est majoritairement
nuageux (un seul item clair sur 4) : aucun test n'attend 4 ``ingested`` sur B09.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest

from tiny_wae.adapters.backfill import (
    BackfillOutcome,
    _request_stop,
    build_tasks,
    run_backfill,
)
from tiny_wae.adapters.config_io import DEFAULT_SITES_PATH, load_settings, load_sites
from tiny_wae.adapters.fixture_source import FixtureSource
from tiny_wae.adapters.manifests import list_for_site, read_manifest
from tiny_wae.adapters.stac import StacSource, StacUnreachable
from tiny_wae.core.envelope import Envelope
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Site
from tiny_wae.core.windows import Window

# Fenêtre exacte du corpus A01 × septembre 2022 (6 items gelés, cf. test_fixture_source.py
# et l'ancrage de la fiche). Fenêtre demi-ouverte [start, end[.
_A01_SEPT_2022 = Window(start=datetime(2022, 9, 1), end=datetime(2022, 10, 1))
_A01_SEPT_2022_ITEM_IDS = {
    "S2A_31TGJ_20220901_0_L2A",
    "S2B_31TGJ_20220906_0_L2A",
    "S2A_31TGJ_20220911_0_L2A",
    "S2B_31TGJ_20220916_0_L2A",
    "S2A_31TGJ_20220921_0_L2A",
    "S2B_31TGJ_20220926_0_L2A",
}
# Fenêtre exacte du corpus B09 × août 2023 (4 items, cf. l'ancrage : cloud_pct 0.5/86.5/
# 84.6/63.8 % — plusieurs partiront en rejected_clouds au verdict SCL, ne PAS attendre
# 4 ingested).
_B09_AOUT_2023 = Window(start=datetime(2023, 8, 1), end=datetime(2023, 9, 1))


def _sites() -> dict[str, Site]:
    """Charge les sites RÉELS de ``config/sites.yaml`` (grilles déjà posées pour A01/B09)."""
    return {site.id: site for site in load_sites(DEFAULT_SITES_PATH)}


def _settings() -> Settings:
    return load_settings()


def _read_item_status_set(data_root: Path, site_id: str) -> set[tuple[str, str]]:
    """Ensemble (item_id, statut) des manifestes présents pour un site — l'invariant que
    le pool doit préserver quel que soit ``workers`` (O1)."""
    return {(m.item_id, m.status) for m in list_for_site(data_root, site_id)}


# ── O1 : compteurs gelés + déterminisme du pool ──────────────────────────────────────


def test_backfill_a01_septembre_2022_compteurs_geles_o1(tmp_path: Path) -> None:
    """O1 (volet compteurs) : A01 × sept. 2022, un seul (site, fenêtre) -> compteurs
    GELÉS EN LITTÉRAL (jamais recopiés depuis l'enveloppe à l'exécution)."""
    settings = _settings()
    sites = _sites()
    site = sites["A01"]
    source = FixtureSource(settings=settings)

    outcome = run_backfill(
        sites=[site],
        windows_by_site={"A01": [_A01_SEPT_2022]},
        source=source,
        settings=settings,
        data_root=tmp_path,
        workers=4,
        install_signal_handlers=False,
    )

    assert outcome.all_ok
    assert len(outcome.site_results) == 1
    result = outcome.site_results[0]
    assert len(result.outcomes) == 1
    counters = result.outcomes[0].run.counters
    assert counters["found_stac"] == 6
    assert counters["skipped_scene_cloud"] == 0
    assert counters["off_tile"] == 0
    assert counters["found_tile"] == 6
    # Les deux invariants de conservation (chapeau l0-02) bouclent déjà à l'écriture du
    # run.json (write_run lève ConservationError sinon) : on les revérifie ici en clair.
    assert counters["found_stac"] == (
        counters["skipped_scene_cloud"] + counters["off_tile"] + counters["found_tile"]
    )
    status_sum = (
        counters["ingested"]
        + counters["rejected_clouds"]
        + counters["rejected_invalid"]
        + counters["rejected_nodata"]
        + counters["failed"]
        + counters["skipped"]
    )
    assert counters["found_tile"] == status_sum


def test_backfill_pool_deterministe_workers_4_vs_1_o1(tmp_path: Path) -> None:
    """O1 (volet déterminisme) : plusieurs tâches réelles (6 fenêtres journalières
    couvrant chacune un item du corpus A01 × sept. 2022) -> ``--workers 4`` et
    ``--workers 1`` rendent le MÊME ensemble (item_id, statut). L'ORDRE peut varier,
    l'ENSEMBLE non — c'est le seul test qui prouve que le pool ne perd ni ne duplique
    rien."""
    settings = _settings()
    site = _sites()["A01"]
    source = FixtureSource(settings=settings)

    # Une fenêtre d'un jour par date connue du corpus -> 6 tâches réelles pour 1 site,
    # de quoi exercer un pool à 4 workers sans dépendre d'un timing.
    daily_windows = [
        Window(start=datetime(2022, 9, day), end=datetime(2022, 9, day + 1))
        for day in (1, 6, 11, 16, 21, 26)
    ]

    data_root_4 = tmp_path / "workers4"
    outcome_4 = run_backfill(
        sites=[site],
        windows_by_site={"A01": daily_windows},
        source=source,
        settings=settings,
        data_root=data_root_4,
        workers=4,
        install_signal_handlers=False,
    )
    data_root_1 = tmp_path / "workers1"
    outcome_1 = run_backfill(
        sites=[site],
        windows_by_site={"A01": daily_windows},
        source=source,
        settings=settings,
        data_root=data_root_1,
        workers=1,
        install_signal_handlers=False,
    )

    assert outcome_4.all_ok
    assert outcome_1.all_ok
    set_4 = _read_item_status_set(data_root_4, "A01")
    set_1 = _read_item_status_set(data_root_1, "A01")
    assert set_4 == set_1
    assert {item_id for item_id, _status in set_4} == _A01_SEPT_2022_ITEM_IDS


# ── O2 : isolation par site (corpus non recouvrants) ─────────────────────────────────


@dataclass(frozen=True, slots=True)
class _FailingSiteSource:
    """Double ``StacSource`` qui échoue TOUJOURS pour un site donné, délègue à une source
    réelle (``FixtureSource``) pour les autres — injection de l'échec par la source, voie
    acceptée par l'ancrage de la fiche (les corpus A01/B09 ne se recouvrant pas dans le
    temps, une fenêtre unique laisserait forcément un site vide)."""

    delegate: StacSource
    failing_site_id: str

    def search(self, site: Site, window: Window) -> Envelope:
        if site.id == self.failing_site_id:
            raise ValueError(f"panne injectée pour {site.id}")
        return self.delegate.search(site, window)


def test_backfill_echec_sur_1_site_isole_lautre_o2(tmp_path: Path) -> None:
    """O2 : échec injecté sur B09 -> A01 complet (found_stac=6, ingested présent), exit
    logique = site fautif nommé (B09), run PAS interrompu."""
    settings = _settings()
    sites = _sites()
    source = _FailingSiteSource(delegate=FixtureSource(settings=settings), failing_site_id="B09")

    outcome = run_backfill(
        sites=[sites["A01"], sites["B09"]],
        windows_by_site={"A01": [_A01_SEPT_2022], "B09": [_B09_AOUT_2023]},
        source=source,
        settings=settings,
        data_root=tmp_path,
        workers=4,
        install_signal_handlers=False,
    )

    assert not outcome.interrupted
    assert outcome.failed_site_ids == ["B09"]
    assert not outcome.all_ok

    a01_result = next(r for r in outcome.site_results if r.site_id == "A01")
    b09_result = next(r for r in outcome.site_results if r.site_id == "B09")
    assert a01_result.ok
    assert len(a01_result.outcomes) == 1
    assert a01_result.outcomes[0].run.counters["found_stac"] == 6
    assert not b09_result.ok
    assert len(b09_result.failures) == 1
    assert "panne injectée pour B09" in b09_result.failures[0].error
    assert not b09_result.failures[0].is_network  # ValueError : pas une erreur réseau

    # A01 a bien écrit ses manifestes malgré l'échec de B09 (isolation réelle, pas
    # seulement déclarée dans le résultat).
    assert len(list_for_site(tmp_path, "A01")) == 6
    assert list_for_site(tmp_path, "B09") == []


# ── O2bis : amont injoignable sur TOUS les sites -> distinct de O2 ───────────────────


@dataclass(frozen=True, slots=True)
class _AlwaysUnreachableSource:
    """Double ``StacSource`` qui lève ``StacUnreachable`` pour TOUT site — simule un
    amont totalement injoignable (O2bis)."""

    def search(self, site: Site, window: Window) -> Envelope:
        raise StacUnreachable(f"amont injoignable pour {site.id}")


def test_backfill_amont_injoignable_partout_o2bis(tmp_path: Path) -> None:
    """O2bis : les DEUX sites échouent, tous deux d'origine réseau, aucun succès nulle
    part -> ``all_failures_network`` vrai — distinct de O2 (échec partiel, non-réseau)."""
    settings = _settings()
    sites = _sites()

    outcome = run_backfill(
        sites=[sites["A01"], sites["B09"]],
        windows_by_site={"A01": [_A01_SEPT_2022], "B09": [_B09_AOUT_2023]},
        source=_AlwaysUnreachableSource(),
        settings=settings,
        data_root=tmp_path,
        workers=4,
        install_signal_handlers=False,
    )

    assert sorted(outcome.failed_site_ids) == ["A01", "B09"]
    assert outcome.all_failures_network
    for result in outcome.site_results:
        assert not result.outcomes
        assert all(f.is_network for f in result.failures)


def test_backfill_echec_o2_nest_pas_all_failures_network(tmp_path: Path) -> None:
    """Non-régression : un échec NON réseau (O2, ValueError injectée) ne doit JAMAIS
    déclencher ``all_failures_network`` même si c'est le seul site en échec — sinon le
    CLI confondrait un bug métier avec un amont injoignable (exit INCONCLUSIVE au lieu de
    FAILURE)."""
    settings = _settings()
    sites = _sites()
    source = _FailingSiteSource(delegate=FixtureSource(settings=settings), failing_site_id="B09")

    outcome = run_backfill(
        sites=[sites["A01"], sites["B09"]],
        windows_by_site={"A01": [_A01_SEPT_2022], "B09": [_B09_AOUT_2023]},
        source=source,
        settings=settings,
        data_root=tmp_path,
        workers=4,
        install_signal_handlers=False,
    )
    assert not outcome.all_failures_network


# ── O3 : interruption propre (gestionnaire appelé directement, PAS un vrai signal) ────


@dataclass(slots=True)
class _BlockingThenRealSource:
    """Double ``StacSource`` qui bloque la PREMIÈRE recherche jusqu'à ce que le test
    libère ``release_event`` (signale son entrée via ``started_event``), puis délègue à
    une source réelle pour toutes les recherches suivantes — permet de synchroniser
    précisément "le pool est en train de traiter une tâche" avec l'appel au gestionnaire
    de signal, SANS aucun ``time.sleep`` (règle du dépôt : aucun test ne dort)."""

    delegate: StacSource
    started_event: threading.Event
    release_event: threading.Event
    _blocked_once: bool = False
    # `field(default_factory=...)` et PAS `threading.Lock()` : un défaut de dataclass est
    # évalué UNE fois, à la définition de la classe — le verrou serait partagé par toutes
    # les instances (débusqué par ruff RUF009).
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def search(self, site: Site, window: Window) -> Envelope:
        with self._lock:
            block = not self._blocked_once
            self._blocked_once = True
        if block:
            self.started_event.set()
            self.release_event.wait(timeout=5)
        return self.delegate.search(site, window)


def test_backfill_sigint_arrete_soumissions_et_attend_en_cours_o3(tmp_path: Path) -> None:
    """O3 : le gestionnaire de signal (``_request_stop``, fonction PURE) est appelé
    DIRECTEMENT — pas un vrai signal (non portable linux-64/win-64, cf. l'ancrage). Ce
    qu'on prouve : la tâche en cours va à son terme (n'est pas tuée à mi-item), les
    tâches pas-encore-démarrées sont annulées, ``interrupted`` est vrai, et 100 % des
    manifestes déjà écrits restent relisibles par ``read_manifest``."""
    settings = _settings()
    site = _sites()["A01"]
    started = threading.Event()
    release = threading.Event()
    source = _BlockingThenRealSource(
        delegate=FixtureSource(settings=settings), started_event=started, release_event=release
    )
    stop_event = threading.Event()

    # 6 fenêtres journalières -> 6 tâches, workers=1 pour garantir qu'une seule tourne à
    # la fois : la 1re bloque, les 5 autres restent dans la file (annulables).
    daily_windows = [
        Window(start=datetime(2022, 9, day), end=datetime(2022, 9, day + 1))
        for day in (1, 6, 11, 16, 21, 26)
    ]

    result_holder: dict[str, BackfillOutcome] = {}

    def _run() -> None:
        result_holder["outcome"] = run_backfill(
            sites=[site],
            windows_by_site={"A01": daily_windows},
            source=source,
            settings=settings,
            data_root=tmp_path,
            workers=1,
            stop_event=stop_event,
            install_signal_handlers=False,
        )

    runner_thread = threading.Thread(target=_run)
    runner_thread.start()

    # Attend que la 1re tâche soit réellement engagée avant de "recevoir" le signal.
    assert started.wait(timeout=5), "la tâche bloquante n'a jamais démarré"
    _request_stop(stop_event, 0, None)  # appel DIRECT du gestionnaire — pas un vrai signal.
    release.set()  # laisse la tâche en cours aller à son terme.
    runner_thread.join(timeout=10)
    assert not runner_thread.is_alive(), "le backfill ne s'est pas arrêté à temps"

    outcome = result_holder["outcome"]
    assert outcome.interrupted

    # 100 % des manifestes présents restent relisibles (atomicité de l0-03.2, vérifiée ici).
    manifests = list_for_site(tmp_path, "A01")
    assert manifests, "la tâche en cours aurait dû aller à son terme et écrire ses manifestes"
    for manifest in manifests:
        reread = read_manifest(tmp_path, "A01", manifest.item_id)
        assert reread.item_id == manifest.item_id
    # L'interruption a bien empêché AU MOINS une des 6 fenêtres d'être traitée (sinon le
    # test ne prouverait rien sur l'annulation des tâches en file).
    assert len(manifests) < 6


# ── O4 : run double — témoins positif ET négatif ──────────────────────────────────────


def test_backfill_run_double_idempotent_o4(tmp_path: Path) -> None:
    """O4 : 1er run -> assets_read > 0 (témoin positif) ; 2e run (même site, même
    fenêtre) -> assets_read == 0, 100 % skipped, content_hashes identiques (témoin
    négatif). Un seul des deux témoins ne vaudrait rien (idempotence non prouvée)."""
    settings = _settings()
    site = _sites()["A01"]
    source = FixtureSource(settings=settings)

    outcome_1 = run_backfill(
        sites=[site],
        windows_by_site={"A01": [_A01_SEPT_2022]},
        source=source,
        settings=settings,
        data_root=tmp_path,
        workers=4,
        install_signal_handlers=False,
    )
    assert outcome_1.all_ok
    run_1 = outcome_1.site_results[0].outcomes[0].run
    assert run_1.assets_read > 0, "témoin positif : le 1er run doit avoir lu des assets"
    hashes_before = {m.item_id: m.content_hashes for m in list_for_site(tmp_path, "A01")}
    assert any(hashes_before.values()), "au moins un item ingéré devrait porter des hashes"

    outcome_2 = run_backfill(
        sites=[site],
        windows_by_site={"A01": [_A01_SEPT_2022]},
        source=source,
        settings=settings,
        data_root=tmp_path,
        workers=4,
        install_signal_handlers=False,
    )
    assert outcome_2.all_ok
    run_2 = outcome_2.site_results[0].outcomes[0].run
    assert run_2.assets_read == 0, "témoin négatif : le 2e run ne doit relire aucun asset"
    assert run_2.counters["skipped"] == run_2.counters["found_tile"] == 6
    hashes_after = {m.item_id: m.content_hashes for m in list_for_site(tmp_path, "A01")}
    assert hashes_after == hashes_before


# ── build_tasks : une seule et même liste de fenêtres par site ────────────────────────


def test_build_tasks_meme_fenetres_pour_tous_les_sites() -> None:
    """``build_tasks`` associe la MÊME liste de fenêtres à chaque site (usage CLI,
    ``--months`` global) — un appelant qui veut des fenêtres différentes par site
    construit ``windows_by_site`` à la main (voie utilisée par les tests O2/O2bis/O3
    ci-dessus)."""
    sites = [_sites()["A01"], _sites()["B09"]]
    windows = [_A01_SEPT_2022]
    tasks = build_tasks(sites, windows)
    assert tasks == {"A01": [_A01_SEPT_2022], "B09": [_A01_SEPT_2022]}


def test_backfill_site_sans_fenetre_reste_ok_et_vide(tmp_path: Path) -> None:
    """Un site absent de ``windows_by_site`` n'est PAS traité (aucune tâche) : son
    ``SiteResult`` est vide et ``ok`` (pas d'échec)."""
    settings = _settings()
    sites = [_sites()["A01"], _sites()["B09"]]

    outcome = run_backfill(
        sites=sites,
        windows_by_site={"A01": [_A01_SEPT_2022]},  # B09 absent volontairement.
        source=FixtureSource(settings=settings),
        settings=settings,
        data_root=tmp_path,
        workers=4,
        install_signal_handlers=False,
    )
    b09_result = next(r for r in outcome.site_results if r.site_id == "B09")
    assert b09_result.ok
    assert b09_result.outcomes == []
    assert b09_result.failures == []


@pytest.mark.parametrize("workers", [1, 2])
def test_backfill_isolation_meme_avec_peu_de_workers(tmp_path: Path, workers: int) -> None:
    """Isolation par site indépendante de la taille du pool : même avec ``workers=1``
    (aucune vraie concurrence), l'échec de B09 ne doit pas empêcher A01 d'aboutir."""
    settings = _settings()
    sites = _sites()
    source = _FailingSiteSource(delegate=FixtureSource(settings=settings), failing_site_id="B09")

    outcome = run_backfill(
        sites=[sites["A01"], sites["B09"]],
        windows_by_site={"A01": [_A01_SEPT_2022], "B09": [_B09_AOUT_2023]},
        source=source,
        settings=settings,
        data_root=tmp_path,
        workers=workers,
        install_signal_handlers=False,
    )
    assert outcome.failed_site_ids == ["B09"]
    a01_result = next(r for r in outcome.site_results if r.site_id == "A01")
    assert a01_result.ok
