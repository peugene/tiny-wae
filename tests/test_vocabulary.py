"""Tests du vocabulaire de domaine — il n'existe qu'à UN endroit (post-revue 1, A2/A3/A4).

Trois énumérations normatives vivaient dans ``adapters/`` et étaient RECOPIÉES ailleurs,
parce que ``core/`` ne doit jamais importer ``adapters/`` : les 6 statuts de run, les 3 noms
de fichiers d'un item, et le seuil de tuile suspecte (celui-là recopié en clair dans un
message utilisateur). Chaque recopie était assumée en commentaire — mais un commentaire
n'empêche pas de diverger, et rien dans le gate ne l'aurait vu.

Les constantes sont désormais dans ``core/`` et importées. Ces tests vérifient l'IDENTITÉ
(``is``), pas l'égalité : deux listes recopiées à l'identique sont égales, seule l'identité
prouve qu'il n'y en a qu'une.
"""

from __future__ import annotations

from types import ModuleType

import pytest

import tiny_wae.adapters.chips as chips_module
import tiny_wae.adapters.ingestion as ingestion_module
import tiny_wae.adapters.manifests as manifests_module
import tiny_wae.cli.ingest as ingest_module
import tiny_wae.core.report as report_module
from tiny_wae.adapters.manifests import Run
from tiny_wae.core import artifacts, statuses


def _attribut(module: ModuleType, nom: str) -> object:
    """Lit un attribut par son NOM dans l'espace de noms du module.

    `getattr` plutôt que l'accès pointé : mypy strict interdit de référencer un nom
    seulement ré-exporté (`no_implicit_reexport`) — or c'est exactement ce qu'on veut
    inspecter, le fait que le nom vu par le consommateur SOIT l'objet de `core/`."""
    return getattr(module, nom)


def test_les_statuts_sont_la_meme_objet_partout() -> None:
    """`RUN_STATUSES` n'est pas recopié : les consommateurs pointent l'objet de `core/`."""
    for module in (manifests_module, report_module, ingestion_module, ingest_module):
        assert module.RUN_STATUSES is statuses.RUN_STATUSES, (
            f"{module.__name__} porte sa PROPRE copie de RUN_STATUSES"
        )


def test_manifest_statuses_a_bien_disparu() -> None:
    """`MANIFEST_STATUSES` n'existe plus nulle part : elle n'a jamais eu de consommateur.

    Ce test dit à quoi s'attendre à qui la chercherait — et fait échouer sa réintroduction
    silencieuse. La règle qu'elle prétendait porter (« `skipped` n'est jamais écrit à un
    manifeste ») n'était appliquée par personne : `write_manifest` ne valide pas le statut."""
    assert not hasattr(statuses, "MANIFEST_STATUSES")
    assert not hasattr(manifests_module, "MANIFEST_STATUSES")


def test_les_noms_de_fichiers_sont_le_meme_objet_partout() -> None:
    """Les 3 noms d'artefacts viennent de `core/artifacts.py`, et `EXPECTED_FILES` en est
    DÉRIVÉ — renommer `chip.tif` se fait à un seul endroit."""
    assert _attribut(chips_module, "CHIP_10M_FILENAME") is artifacts.CHIP_10M_FILENAME
    assert _attribut(report_module, "EXPECTED_FILES") is artifacts.EXPECTED_FILES
    assert artifacts.EXPECTED_FILES == (
        artifacts.CHIP_10M_FILENAME,
        artifacts.CHIP_20M_FILENAME,
        artifacts.SCL_FILENAME,
    )


def test_les_compteurs_d_enveloppe_sont_composes_et_non_recopies() -> None:
    """Les 10 clés de `run.json` = les 4 compteurs d'enveloppe (core/envelope) + les 6
    statuts, composés. Avant, les 4 étaient re-listés à la main dans `adapters/`."""
    from tiny_wae.core.envelope import ENVELOPE_COUNTERS

    assert (*ENVELOPE_COUNTERS, *statuses.RUN_STATUSES) == manifests_module._COUNTER_KEYS


def _run_avec_tuile_suspecte() -> Run:
    """Un `Run` minimal cohérent, marqué `tile_suspect` — seul champ qui compte ici."""
    counters = dict.fromkeys(statuses.RUN_STATUSES, 0)
    counters.update(
        {"found_stac": 5, "skipped_scene_cloud": 0, "off_tile": 0, "found_tile": 5},
        rejected_nodata=5,
    )
    return Run(
        schema_version=1,
        site_id="A01",
        run_id="run-test",
        window={"start": "2026-01-01T00:00:00+00:00", "end": "2026-01-10T00:00:00+00:00"},
        counters=counters,
        assets_read=0,
        bytes_downloaded=0,
        tile_suspect=True,
        duration_s=0.0,
    )


def test_le_message_de_tuile_suspecte_cite_le_seuil_reel(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """⭐ Le pourcentage affiché est CALCULÉ depuis `TILE_SUSPECT_RATIO`, pas écrit en dur.

    Le test est discriminant parce qu'il déplace le seuil : avec l'ancien
    `int(100 * 0.20)` en dur, le message continuerait d'annoncer « 20 % » pendant que le
    code déclencherait à 25 % — il mentirait, et aucun test ne l'aurait vu."""
    monkeypatch.setattr(ingest_module, "TILE_SUSPECT_RATIO", 0.25)
    ingest_module._report_counters("A01", _run_avec_tuile_suspecte())
    err = capsys.readouterr().err
    assert "> 25% des items de la tuile de référence" in err
    assert "20%" not in err


def test_le_seuil_du_cli_est_celui_de_l_adapter() -> None:
    """Le CLI n'a pas son propre seuil : c'est l'objet de `adapters/ingestion.py`."""
    assert _attribut(ingest_module, "TILE_SUSPECT_RATIO") is ingestion_module.TILE_SUSPECT_RATIO


def test_le_message_nominal_annonce_le_seuil_configure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Sans monkeypatch : le message cite le seuil réellement en vigueur (20 %)."""
    ingest_module._report_counters("A01", _run_avec_tuile_suspecte())
    err = capsys.readouterr().err
    assert f"> {ingestion_module.TILE_SUSPECT_RATIO:.0%} des items" in err
