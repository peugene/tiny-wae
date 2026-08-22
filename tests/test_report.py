"""Tests core/report.py (l0-04.2) — agrégats, conservation, intégrité, complétude, rendu.

C'est l'instrument de la recette (chapeau l0-04) : un rapport qui ne saurait pas rendre
ROUGE ne vaudrait rien — chaque oracle mutant est vérifié DANS LES DEUX SENS.

Ancrage (22/08/2026, cf. fiche) :
- ``tests/fixtures/manifests/C07/`` : 12 manifestes, un seul run (``run-2026-01-31``),
  compteurs MESURÉS : found_stac=15, skipped_scene_cloud=1, off_tile=2, found_tile=12,
  ingested=6, rejected_clouds=3, rejected_invalid=1, rejected_nodata=1, failed=1, skipped=0.
- ⚠ Piège du corpus (décision d'ancrage n°2) : tous les ``grid_hash`` valent
  ``"f" * 64`` et ``tile`` vaut ``"31TGM"`` (alors que ``config/sites.yaml`` donne
  ``52TEL`` à C07) — un corpus TEL QUEL rendrait le critère d'intégrité ROUGE par
  construction. O1/O2/O2bis (qui ne testent PAS l'intégrité) passent ``current_grid_hash``
  ÉGAL au littéral factice du corpus (neutralise le critère sans le tester — délibéré,
  documenté). O2quater (qui teste PRÉCISÉMENT l'intégrité) copie le corpus en ``tmp_path``
  et réécrit les ``grid_hash`` avec la vraie valeur calculée par
  ``manifests.grid_hash(grid, settings)`` pour la grille RÉELLE de C07 (``config/sites.yaml``)
  — c'est le cas nominal « → OK » ; les 3 mutations partent de ce corpus assaini.
- ``tests/fixtures/manifests/OVERLAP/`` : 2 runs recouvrants, 7 ``item_id`` réels
  (``item_ids_for_site`` == {S2A_OVERLAP_001..007}), alors que la SOMME des compteurs de
  run annonce ``found_tile=10`` (5+5) — la démonstration vivante de l'arbitrage n°2.
  ``tests/fixtures/stac/overlap_completeness.json`` est une fixture ``/search`` CRÉÉE pour
  cette fiche : les 7 ids réels (tuile ``31TCJ``, cc=10) + 2 items écartés par le
  pré-filtre scène (cc>=95) + 2 items ``off_tile`` (tuile ``31TCK``) — les TROIS pièges de
  la fiche dans le MÊME corpus (décision n°3 de l'ancrage).

Aucun test ici ne fait de réseau (pytest tourne sous ``--disable-socket``) : les manifestes
viennent des fixtures locales, la « source » de ``--check-completeness`` est rejouée via
``adapters.stac.build_envelope`` sur un JSON déjà enregistré.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from tiny_wae.adapters.config_io import (
    DEFAULT_SETTINGS_PATH,
    DEFAULT_SITES_PATH,
    load_settings,
    load_sites,
)
from tiny_wae.adapters.manifests import (
    Manifest,
    aggregate_counters,
    grid_hash,
    item_ids_for_site,
    list_for_site,
)
from tiny_wae.adapters.stac import build_envelope
from tiny_wae.core.report import build_site_report, check_completeness, render_report
from tiny_wae.core.settings import EXPECTED_ASSET_KEYS
from tiny_wae.core.windows import Window

MANIFESTS_ROOT = Path("tests/fixtures/manifests")
STAC_FIXTURES_ROOT = Path("tests/fixtures/stac")
SITE_ID = "C07"

# Littéral factice du corpus C07 tel quel (cf. ancrage) — 64 caractères 'f'.
_FIXTURE_FAKE_GRID_HASH = "f" * 64
# Fichiers attendus au manifeste d'un item ingéré (repris de core/report.EXPECTED_FILES,
# en LITTÉRAL ici pour ne pas coupler le test à l'implémentation qu'il vérifie).
_EXPECTED_FILES = ("chip.tif", "chip_20m.tif", "scl.tif")


def _c07_manifests() -> list[Manifest]:
    return list_for_site(MANIFESTS_ROOT, SITE_ID)


def _c07_counters() -> dict[str, int]:
    return dict(aggregate_counters(MANIFESTS_ROOT, SITE_ID))


# ── O1 : rapport EXACT chiffre à chiffre sur le corpus C07 ──────────────────────────────


def test_o1_c07_comptes_geles_mesures_par_aggregate_counters() -> None:
    """Les comptes de l'oracle sont ceux mesurés le 22/08 dans la fiche — comparés ici à
    ce que ``aggregate_counters`` produit RÉELLEMENT sur le corpus (pas recopiés en dur
    sans vérification, décision n°5 de l'ancrage)."""
    counters = _c07_counters()
    assert counters["found_stac"] == 15
    assert counters["skipped_scene_cloud"] == 1
    assert counters["off_tile"] == 2
    assert counters["found_tile"] == 12
    assert counters["ingested"] == 6
    assert counters["rejected_clouds"] == 3
    assert counters["rejected_invalid"] == 1
    assert counters["rejected_nodata"] == 1
    assert counters["failed"] == 1
    assert counters["skipped"] == 0


def test_o1_site_report_et_rendu_markdown() -> None:
    """``conservation: OK`` ; ratio 6/12 avec dénominateur affiché ; failed_pct = 1/12 =
    8,3 % signalé > 1 % ; classes SCL agrégées (mesurées : classe 4 = 393216, classes 2/11
    = 0 sur ce corpus, aucune n'est absente du rendu)."""
    counters = _c07_counters()
    report = build_site_report(
        SITE_ID,
        counters,
        _c07_manifests(),
        current_grid_hash=_FIXTURE_FAKE_GRID_HASH,
        chip_nodata_pct_max=1.0,
    )

    assert report.conservation_ok is True
    assert report.ingested_ratio == pytest.approx(6 / 12)
    assert report.failed_pct == pytest.approx(100 * 1 / 12)
    assert report.failed_pct > 1.0  # > seuil légitime (chapeau l0-04, critère 4)
    assert report.bytes_written == 54_000_000  # somme mesurée des bytes_written 'ingested'
    assert report.scl_class_counts["2"] == 0
    assert report.scl_class_counts["11"] == 0
    assert report.scl_class_counts["4"] == 393216

    markdown = render_report([report])
    assert "| C07 | 15 | 1 | 2 | 12 | 6 | 3 | 1 | 1 | 1 | 0 | 8.3 % | OK | OK |" in markdown
    assert "6/12" in markdown  # ratio + dénominateur affiché (pires cas en tête)
    assert "classe **2**" in markdown
    assert "classe **11**" in markdown


# ── O2 : conservation cassée -> ROUGE, mis en tête ───────────────────────────────────────


def test_o2_off_tile_mute_casse_conservation_et_rougeoie() -> None:
    """``off_tile`` porté à 3 (au lieu de 2, mesuré) : ``found_stac`` ne boucle plus ->
    ``conservation: ROUGE``, section « en tête » dédiée dans le rendu."""
    counters = _c07_counters()
    counters["off_tile"] = 3

    report = build_site_report(
        SITE_ID,
        counters,
        _c07_manifests(),
        current_grid_hash=_FIXTURE_FAKE_GRID_HASH,
        chip_nodata_pct_max=1.0,
    )

    assert report.conservation_ok is False
    markdown = render_report([report])
    assert "| C07 |" in markdown
    assert "ROUGE" in markdown
    assert "Conservation ROUGE — en tête" in markdown
    assert "C07" in markdown.split("Conservation ROUGE — en tête")[1]


# ── O2bis : failed -> 0, discriminant dans l'autre sens ─────────────────────────────────


def test_o2bis_failed_mute_a_zero_discrimine_sans_casser_conservation() -> None:
    """``failed`` porté à 0 (1 item déplacé vers ``skipped`` pour NE PAS casser
    l'invariant de conservation — ce test isole ``failed_pct``, pas la conservation, cf.
    docstring du fichier) : ``failed_pct = 0 %``, aucun ROUGE."""
    counters = _c07_counters()
    counters["failed"] = 0
    counters["skipped"] = 1  # found_tile inchangé : conservation reste vraie

    report = build_site_report(
        SITE_ID,
        counters,
        _c07_manifests(),
        current_grid_hash=_FIXTURE_FAKE_GRID_HASH,
        chip_nodata_pct_max=1.0,
    )

    assert report.conservation_ok is True  # preuve que ce mutant isole bien failed_pct
    assert report.failed_pct == 0.0
    markdown = render_report([report])
    assert "Conservation ROUGE" not in markdown


# ── O2quater : intégrité — corpus assaini, nominal OK, 3 mutations séparées -> ROUGE ────


def _real_c07_grid_hash() -> str:
    """Grid_hash RÉEL du site C07 (``config/sites.yaml`` + ``config/settings.yaml``) —
    la valeur que le critère d'intégrité doit trouver au manifeste pour dire OK."""
    settings = load_settings(DEFAULT_SETTINGS_PATH)
    sites = {site.id: site for site in load_sites(DEFAULT_SITES_PATH)}
    return grid_hash(sites[SITE_ID].grid, settings)


def _sanitized_c07_corpus(tmp_path: Path, *, subdir: str) -> Path:
    """Copie le corpus C07 dans ``tmp_path/<subdir>`` puis réécrit le ``grid_hash`` de
    TOUS les manifestes avec la vraie valeur (décision d'ancrage n°2) — jamais les
    fixtures versionnées elles-mêmes (elles servent des tests verts de l0-03.2)."""
    dest_root = tmp_path / subdir
    shutil.copytree(MANIFESTS_ROOT / SITE_ID, dest_root / SITE_ID)
    real_hash = _real_c07_grid_hash()
    for manifest_path in (dest_root / SITE_ID).rglob("manifest.json"):
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["grid_hash"] = real_hash
        manifest_path.write_text(json.dumps(data), encoding="utf-8")
    return dest_root


def test_o2quater_corpus_assaini_nominal_integrite_ok(tmp_path: Path) -> None:
    """Corpus copié + grid_hash réécrit à la valeur réelle -> ``integrite: OK`` (le cas
    « nominal » de l'oracle, impossible à obtenir sur le corpus versionné tel quel)."""
    data_root = _sanitized_c07_corpus(tmp_path, subdir="nominal")
    manifests = list_for_site(data_root, SITE_ID)
    counters = aggregate_counters(data_root, SITE_ID)
    real_hash = _real_c07_grid_hash()

    report = build_site_report(
        SITE_ID, counters, manifests, current_grid_hash=real_hash, chip_nodata_pct_max=1.0
    )

    assert report.integrity_ok is True
    assert report.integrity_issues == ()
    markdown = render_report([report])
    assert "## Intégrité — items fautifs" not in markdown


def test_o2quater_mutation_fichier_manquant_rougeoie_item_nomme(tmp_path: Path) -> None:
    """Un ``ingested`` (``S2A_C07_ING01``) réduit à 2 fichiers (``scl.tif`` retiré de
    ``files``) -> ROUGE, l'item et la cause nommés."""
    data_root = _sanitized_c07_corpus(tmp_path, subdir="missing_file")
    manifest_path = data_root / SITE_ID / "S2A_C07_ING01" / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["files"] = [f for f in data["files"] if f != "scl.tif"]
    manifest_path.write_text(json.dumps(data), encoding="utf-8")

    manifests = list_for_site(data_root, SITE_ID)
    counters = aggregate_counters(data_root, SITE_ID)
    real_hash = _real_c07_grid_hash()

    report = build_site_report(
        SITE_ID, counters, manifests, current_grid_hash=real_hash, chip_nodata_pct_max=1.0
    )

    assert report.integrity_ok is False
    assert any(issue.item_id == "S2A_C07_ING01" for issue in report.integrity_issues)
    assert any("fichiers manquants" in issue.cause for issue in report.integrity_issues)
    markdown = render_report([report])
    assert "S2A_C07_ING01" in markdown
    assert "fichiers manquants" in markdown


def test_o2quater_mutation_grid_hash_perime_rougeoie_item_nomme(tmp_path: Path) -> None:
    """Un ``ingested`` (``S2A_C07_ING02``) dont le ``grid_hash`` reste l'ANCIEN (périmé,
    orphelin d'une correction de coordonnées) -> ROUGE, l'item et la cause nommés."""
    data_root = _sanitized_c07_corpus(tmp_path, subdir="stale_grid_hash")
    manifest_path = data_root / SITE_ID / "S2A_C07_ING02" / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["grid_hash"] = _FIXTURE_FAKE_GRID_HASH  # périmé (jamais la vraie grille)
    manifest_path.write_text(json.dumps(data), encoding="utf-8")

    manifests = list_for_site(data_root, SITE_ID)
    counters = aggregate_counters(data_root, SITE_ID)
    real_hash = _real_c07_grid_hash()

    report = build_site_report(
        SITE_ID, counters, manifests, current_grid_hash=real_hash, chip_nodata_pct_max=1.0
    )

    assert report.integrity_ok is False
    assert any(issue.item_id == "S2A_C07_ING02" for issue in report.integrity_issues)
    assert any("grid_hash périmé" in issue.cause for issue in report.integrity_issues)
    markdown = render_report([report])
    assert "S2A_C07_ING02" in markdown
    assert "grid_hash périmé" in markdown


def test_o2quater_mutation_chip_nodata_pct_au_dessus_du_seuil_rougeoie_item_nomme(
    tmp_path: Path,
) -> None:
    """Un ``ingested`` (``S2A_C07_ING03``) dont ``chip_nodata_pct`` est remonté à 5 %
    (seuil 1 %) -> ROUGE, l'item et la cause nommés."""
    data_root = _sanitized_c07_corpus(tmp_path, subdir="nodata_over_threshold")
    manifest_path = data_root / SITE_ID / "S2A_C07_ING03" / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["chip_nodata_pct"] = 5.0
    manifest_path.write_text(json.dumps(data), encoding="utf-8")

    manifests = list_for_site(data_root, SITE_ID)
    counters = aggregate_counters(data_root, SITE_ID)
    real_hash = _real_c07_grid_hash()

    report = build_site_report(
        SITE_ID, counters, manifests, current_grid_hash=real_hash, chip_nodata_pct_max=1.0
    )

    assert report.integrity_ok is False
    assert any(issue.item_id == "S2A_C07_ING03" for issue in report.integrity_issues)
    assert any("chip_nodata_pct" in issue.cause for issue in report.integrity_issues)
    markdown = render_report([report])
    assert "S2A_C07_ING03" in markdown


# ── O2ter (core) : complétude — OVERLAP, arbitrage n°2, 3 pièges dans le même corpus ────


def _overlap_source_ids(fixture_name: str) -> set[str]:
    """Ids retenus par ``build_envelope`` (les 3 filtres du pipeline) sur une fixture
    ``/search`` enregistrée — reproduit exactement ce que ferait ``StacSource.search``."""
    raw_items = json.loads((STAC_FIXTURES_ROOT / fixture_name).read_text(encoding="utf-8"))["items"]
    envelope = build_envelope(
        site_id="OVERLAP",
        window=Window(start=datetime(2026, 2, 1), end=datetime(2026, 3, 1)),
        raw_items=raw_items,
        reference_tile="31TCJ",
        scene_cloud_max=95,
        asset_keys=EXPECTED_ASSET_KEYS,
    )
    return {a.item_id for a in envelope.items}


def test_o2ter_overlap_completude_ok_malgre_recouvrement_nuage_et_hors_tuile() -> None:
    """``item_ids_for_site`` (7 ids réels, ARBITRAGE N°2 : jamais une somme — la somme des
    2 runs recouvrants de OVERLAP annonce ``found_tile=10``, cf. ``test_manifests.py``)
    comparé aux ids retenus par ``build_envelope`` sur une fixture portant les TROIS
    pièges (recouvrement côté manifestes, pré-filtre scène ET hors-tuile côté source) ->
    écart 0, malgré les trois pièges réunis dans le même corpus (décision n°3)."""
    manifest_ids = item_ids_for_site(MANIFESTS_ROOT, "OVERLAP")
    assert manifest_ids == {f"S2A_OVERLAP_{i:03d}" for i in range(1, 8)}  # mesuré, 7 ids

    # Preuve que la somme sur-compte (arbitrage n°2, à ne JAMAIS comparer) :
    summed_found_tile = aggregate_counters(MANIFESTS_ROOT, "OVERLAP")["found_tile"]
    assert summed_found_tile == 10  # 3 items fantômes si on comparait la somme

    source_ids = _overlap_source_ids("overlap_completeness.json")
    assert source_ids == manifest_ids  # les 4 items pièges (scène+hors-tuile) sont EXCLUS

    result = check_completeness("OVERLAP", manifest_ids, source_ids)
    assert result.ok is True
    assert result.missing == frozenset()
    assert result.extra == frozenset()


def test_o2ter_overlap_completude_rouge_item_manquant_nomme(tmp_path: Path) -> None:
    """Corpus de MANIFESTES muté (le manifeste de ``S2A_OVERLAP_004`` est retiré — copie en
    ``tmp_path``, jamais la fixture versionnée) alors que la source continue de le
    retourner : ``item_ids_for_site`` ne rend plus que 6 ids -> ROUGE, l'id manquant nommé
    (celui que la source a mais que le pipeline n'a manifestement PAS ingéré), tolérance 0.
    """
    dest_root = tmp_path / "manifests"
    shutil.copytree(MANIFESTS_ROOT / "OVERLAP", dest_root / "OVERLAP")
    shutil.rmtree(dest_root / "OVERLAP" / "S2A_OVERLAP_004")

    manifest_ids = item_ids_for_site(dest_root, "OVERLAP")
    assert manifest_ids == {f"S2A_OVERLAP_{i:03d}" for i in (1, 2, 3, 5, 6, 7)}  # 004 absent

    source_ids = _overlap_source_ids("overlap_completeness.json")  # les 7 ids réels, intacts

    result = check_completeness("OVERLAP", manifest_ids, source_ids)
    assert result.ok is False
    assert result.missing == frozenset({"S2A_OVERLAP_004"})
    assert result.extra == frozenset()
