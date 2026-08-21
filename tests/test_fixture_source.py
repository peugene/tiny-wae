"""Tests adapters/fixture_source.py (l0-03.5) — sur le corpus enregistré hors pytest.

Aucun test ici ne fait de réseau (pytest tourne sous ``--disable-socket``, cf.
pyproject.toml) : tout part du corpus déjà enregistré dans ``tests/fixtures/stac/cog_*.json``
et ``tests/fixtures/cog/`` par ``scripts/record_cog_fixtures.py``.

Couvre l'oracle de la fiche :
- O1 : substituabilité au port ``StacSource`` — statiquement (``_consume`` annoté, appelé
  avec ``FixtureSource`` ET (sans exécution) avec ``EarthSearchSource``) et à l'exécution
  (``FixtureSource.search`` rend une ``Envelope`` d'``Acquisition`` aux mêmes champs).
- O2 : corpus >= 14 items sur 2 sites, les 3 items gelés du chapeau l0-02 présents par id
  (+ l'item ``sequence=1``).
- O3 : tous les hrefs SERVIS (les 11 clés mappées, pour TOUS les items des 2 sites)
  commencent par ``file://`` — aucun ``https://`` résiduel.
- O5 (indirect) : ces tests tournent dans ``just check``, donc hors ligne.
"""

from __future__ import annotations

from datetime import datetime

from tiny_wae.adapters.config_io import DEFAULT_SITES_PATH, load_settings, load_sites
from tiny_wae.adapters.fixture_source import (
    DEFAULT_COG_DIR,
    DEFAULT_STAC_DIR,
    FixtureNotFoundError,
    FixtureSource,
)
from tiny_wae.adapters.stac import EarthSearchSource, StacSource, StacSourceError
from tiny_wae.core.acquisition import Acquisition
from tiny_wae.core.envelope import Envelope
from tiny_wae.core.settings import EXPECTED_ASSET_KEYS
from tiny_wae.core.sites import Site
from tiny_wae.core.windows import Window

# Fenêtre arbitraire — FixtureSource ne (re-)filtre pas le corpus par date, elle se
# contente de la reporter dans l'enveloppe (cf. docstring de FixtureSource.search).
_ANY_WINDOW = Window(start=datetime(2020, 1, 1), end=datetime(2027, 1, 1))

# Les 3 items GELÉS du chapeau l0-02 (site A01) + l'item sequence=1 (cf. décision
# d'ancrage n°5 de la fiche l0-03.5).
_A01_FROZEN_IDS = {
    "S2A_31TGJ_20240801_0_L2A",
    "S2B_31TGJ_20230315_0_L2A",
    "S2C_31TGJ_20260513_0_L2A",
}
_A01_SEQUENCE_1_ID = "S2A_31TGJ_20260813_1_L2A"

_MIN_TOTAL_ITEMS = 14
_MIN_B09_ITEMS = 3


def _sites() -> dict[str, Site]:
    """Charge les sites RÉELS de ``config/sites.yaml`` (mêmes objets que le script
    d'enregistrement) — pas de site fabriqué : le corpus est indexé sur ces ids."""
    return {site.id: site for site in load_sites(DEFAULT_SITES_PATH)}


def _consume(source: StacSource) -> Envelope:
    """Fonction annotée sur le PORT ``StacSource`` (oracle O1) — appelée avec
    ``FixtureSource`` (exécutée) et référencée avec ``EarthSearchSource`` (non exécutée,
    cf. ``test_fixture_source_typed_as_earthsearch_too`` ci-dessous) : la même fonction
    consomme les deux implémentations sans distinction, ce qui rend la substituabilité
    réellement vérifiée plutôt que seulement déclarée."""
    site = _sites()["A01"]
    return source.search(site, _ANY_WINDOW)


def test_fixture_source_typed_as_earthsearch_too() -> None:
    """O1 (volet statique) : ``EarthSearchSource`` est assignable à ``StacSource`` au même
    titre que ``FixtureSource`` — construite mais jamais appelée (aucun réseau). La vraie
    preuve statique est que ``mypy --strict`` accepte cette ligne (elle échouerait à la
    compilation si ``EarthSearchSource`` ne respectait plus le protocole ``StacSource``)."""
    settings = load_settings()
    earth_search_source: StacSource = EarthSearchSource(settings=settings)
    assert isinstance(earth_search_source, EarthSearchSource)  # construite, jamais .search()


def test_fixture_source_substitutable_o1() -> None:
    """O1 (volet exécution) : ``_consume`` (typé sur le port) accepte une ``FixtureSource``
    et rend une ``Envelope`` dont les items sont des ``Acquisition`` aux mêmes champs
    qu'``EarthSearchSource`` (cf. ``tests/test_stac.py``)."""
    settings = load_settings()
    envelope = _consume(FixtureSource(settings=settings))
    assert isinstance(envelope, Envelope)
    assert envelope.items, "corpus A01 vide — le script d'enregistrement a-t-il tourné ?"
    for acquisition in envelope.items:
        assert isinstance(acquisition, Acquisition)


def test_fixture_source_a01_contains_frozen_items() -> None:
    """O2 : les 3 items gelés du chapeau l0-02 + l'item sequence=1 sont présents par id
    dans l'enveloppe A01."""
    settings = load_settings()
    site = _sites()["A01"]
    envelope = FixtureSource(settings=settings).search(site, _ANY_WINDOW)

    served_ids = {acq.item_id for acq in envelope.items}
    missing_frozen = _A01_FROZEN_IDS - served_ids
    assert not missing_frozen, f"item(s) gelé(s) absent(s) du corpus A01 : {missing_frozen}"
    assert _A01_SEQUENCE_1_ID in served_ids


def test_fixture_source_corpus_size_o2() -> None:
    """O2 : corpus >= 14 items sur 2 sites (A01 mono-tuile + B09 mono-tuile) — publié dans
    le Résumé de la fiche, pas seulement borné ici."""
    settings = load_settings()
    source = FixtureSource(settings=settings)
    sites = _sites()

    a01_envelope = source.search(sites["A01"], _ANY_WINDOW)
    b09_envelope = source.search(sites["B09"], _ANY_WINDOW)

    assert len(b09_envelope.items) >= _MIN_B09_ITEMS
    total = len(a01_envelope.items) + len(b09_envelope.items)
    assert total >= _MIN_TOTAL_ITEMS, f"corpus total={total}, attendu >= {_MIN_TOTAL_ITEMS}"


def test_fixture_source_hrefs_are_all_file_scheme_o3() -> None:
    """O3 : TOUS les hrefs servis (les clés mappées, sur TOUS les items des 2 sites)
    commencent par ``file://`` — un seul ``https://`` résiduel rendrait la garde de
    l0-03.7 (``TINY_WAE_OFFLINE``) inopérante sans que rien ne le signale. Porte sur le
    corpus ENTIER, pas un échantillon."""
    settings = load_settings()
    source = FixtureSource(settings=settings)
    sites = _sites()

    checked = 0
    for site_id in ("A01", "B09"):
        envelope = source.search(sites[site_id], _ANY_WINDOW)
        assert envelope.items, f"site {site_id} : enveloppe vide"
        for acquisition in envelope.items:
            assert acquisition.assets, f"item {acquisition.item_id} : aucun asset servi"
            for key, href in acquisition.assets.items():
                assert href.startswith("file://"), (
                    f"item {acquisition.item_id} asset {key!r} : href={href!r} "
                    "ne commence pas par file://"
                )
                checked += 1
    # Corpus complet attendu : 11 clés d'assets mappées par item (chapeau l0-03).
    assert checked >= _MIN_TOTAL_ITEMS * len(EXPECTED_ASSET_KEYS)


def test_fixture_source_missing_site_raises() -> None:
    """Un site sans fixture enregistrée (ex. C01, hors périmètre du corpus l0-03.5) lève
    ``FixtureNotFoundError`` plutôt que de rendre silencieusement une enveloppe vide."""
    settings = load_settings()
    site = _sites()["C01"]
    try:
        FixtureSource(settings=settings).search(site, _ANY_WINDOW)
    except FixtureNotFoundError:
        pass
    else:
        raise AssertionError("FixtureNotFoundError attendue pour un site sans corpus enregistré")


def test_fixture_source_reference_tile_none_raises() -> None:
    """Même garde qu'``EarthSearchSource`` : ``site.reference_tile`` non posée -> refus,
    AVANT toute lecture de fixture."""
    settings = load_settings()
    site = Site(
        id="ZZZ",
        name="site sans tuile",
        lat=0.0,
        lon=0.0,
        category="stable-watch",
        note="",
        reference_tile=None,
    )
    try:
        FixtureSource(settings=settings).search(site, _ANY_WINDOW)
    except StacSourceError:
        pass
    else:
        raise AssertionError("StacSourceError attendue quand reference_tile est None")


def test_fixture_source_default_dirs_point_at_recorded_corpus() -> None:
    """Les répertoires par défaut de ``FixtureSource`` sont bien ceux écrits par
    ``scripts/record_cog_fixtures.py`` (pas un chemin de test isolé) — garde-fou contre un
    renommage silencieux d'un des deux côtés."""
    assert DEFAULT_STAC_DIR.exists()
    assert DEFAULT_COG_DIR.exists()
    assert (DEFAULT_STAC_DIR / "cog_a01.json").exists()
    assert (DEFAULT_STAC_DIR / "cog_b09.json").exists()
