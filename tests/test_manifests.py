"""Tests adapters/manifests.py — le module-interface du lot d'ingestion (l0-03.2).

Couvre l'oracle de la fiche :
- O1  : round-trip manifeste et run.json (identité champ à champ).
- O2  : corpus fixtures (site C07) — aggregate_counters colle aux comptes CONNUS, les
        deux invariants de conservation bouclent.
- O2bis : conservation violée (off_tile muté) — write_run et aggregate_counters lèvent
        ConservationError.
- O3  : interruption simulée (tmp orphelin) — read_manifest/list_for_site n'en voient rien.
- O3bis : grid_hash — 699960 (int) et 699960.0 (float) donnent le même hash ; un
        changement de BAND_ORDER_20M (3 -> 6 bandes) donne un hash différent.
- O4  : last_datetime sur le corpus C07, statuts rejetés inclus.
- O4bis : item_ids_for_site (site OVERLAP, 2 runs partageant 3 items) a la bonne
        cardinalité (union) alors qu'aggregate_counters sur-compte de 3.

Couvre aussi l'oracle de la fiche data-01 (asset s3:// n'emporte plus la fenêtre) côté
``manifests.py`` — le piège confirmé de son ancrage (``_validate_counters`` s'applique aussi
à la lecture) :
- O7  : aggregate_counters sur un run.json SANS ``skipped_asset_scheme`` (le corpus C07 lui-
        même, écrit avant la fiche) -- aucune exception, la clé absente compte pour 0.
- O8  : write_run reste STRICT si SEULE ``skipped_asset_scheme`` manque -- la tolérance ne
        vaut qu'à la lecture.

Couvre aussi l'oracle de la fiche l0-07 (``write_manifest`` refuse un statut illégitime) :
- O1 (l0-07) : status="skipped" -- ManifestStatusError, rien n'est écrit.
- O2 (l0-07) : status="Ingested" (casse) puis "ingere" (faute) -- lève dans les deux cas.
- O3 (l0-07) : les 5 statuts légitimes, un par un -- écrivent et se relisent identiques.
- O4 (l0-07) : le message de ManifestStatusError cite le statut refusé et les 5 admis.
"""

from __future__ import annotations

import json
import shutil
import threading
from dataclasses import replace
from pathlib import Path

import pytest

import tiny_wae.adapters.ingestion as ingestion_module
from tiny_wae.adapters.manifests import (
    ConservationError,
    EmptyGridError,
    Manifest,
    ManifestStatusError,
    Run,
    aggregate_counters,
    grid_hash,
    item_ids_for_site,
    last_datetime,
    list_for_site,
    list_runs,
    read_manifest,
    read_run,
    write_manifest,
    write_run,
)
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Grid
from tiny_wae.core.statuses import MANIFEST_STATUSES

FIXTURES_ROOT = Path("tests/fixtures/manifests")


def _settings() -> Settings:
    """Settings minimal valide pour les tests de grid_hash."""
    return Settings(stac_url="https://example.test/stac", stac_collection="sentinel-2-l2a")


def _sample_manifest(**overrides: object) -> Manifest:
    """Construit un Manifest complet, avec surcharges ponctuelles pour les tests."""
    base: dict[str, object] = {
        "schema_version": 1,
        "site_id": "A01",
        "item_id": "S2A_A01_20260105",
        "datetime": "2026-01-05T10:15:00Z",
        "tile": "31TGM",
        "sequence": "0",
        "platform": "sentinel-2a",
        "status": "ingested",
        "cause": None,
        "invalid_pct": 0.0,
        "cloud_pct": 2.5,
        "chip_nodata_pct": 0.0,
        "scl_class_counts": {str(i): 0 for i in range(12)},
        "processing_baseline": "05.00",
        "boa_offset_applied": True,
        "radiometry": {"blue": {"scale": 0.0001, "offset": -0.1}, "scl": None},
        "grid_hash": "d" * 64,
        "assets_read": 5,
        "content_hashes": {"chip.tif": "a" * 64},
        "bytes_downloaded": 12_000_000,
        "bytes_written": 9_000_000,
        "duration_s": 3.5,
        "files": ["chip.tif", "chip_20m.tif", "scl.tif"],
        "versions": {"tiny_wae": "0.1.0"},
    }
    base.update(overrides)
    return Manifest(**base)  # type: ignore[arg-type]


def _sample_run(**overrides: object) -> Run:
    """Construit un Run complet, avec surcharges ponctuelles pour les tests."""
    base: dict[str, object] = {
        "schema_version": 1,
        "site_id": "A01",
        "run_id": "run-test",
        "window": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-08T00:00:00Z"},
        "counters": {
            "found_stac": 3,
            "skipped_scene_cloud": 0,
            "off_tile": 0,
            "found_tile": 3,
            "skipped_asset_scheme": 0,
            "ingested": 3,
            "rejected_clouds": 0,
            "rejected_invalid": 0,
            "rejected_nodata": 0,
            "failed": 0,
            "skipped": 0,
        },
        "assets_read": 15,
        "bytes_downloaded": 36_000_000,
        "tile_suspect": False,
        "duration_s": 12.0,
    }
    base.update(overrides)
    return Run(**base)  # type: ignore[arg-type]


# --- O1 : round-trip -----------------------------------------------------------------


def test_manifest_round_trip_o1(tmp_path: Path) -> None:
    """O1 : write_manifest puis read_manifest rendent un objet identique champ à champ."""
    manifest = _sample_manifest()
    write_manifest(tmp_path, manifest)
    reread = read_manifest(tmp_path, manifest.site_id, manifest.item_id)
    assert reread == manifest


def test_run_round_trip_o1(tmp_path: Path) -> None:
    """O1 : write_run puis read_run rendent un objet identique champ à champ."""
    run = _sample_run()
    write_run(tmp_path, run)
    reread = read_run(tmp_path, run.site_id, run.run_id)
    assert reread == run


# --- O2 : corpus fixtures, aggregate_counters -----------------------------------------


def test_aggregate_counters_corpus_o2() -> None:
    """O2 : aggregate_counters sur le corpus C07 rend les comptes CONNUS documentés.

    ⭐ data-01/O7 : le corpus fixture ``tests/fixtures/manifests/C07/runs/*.json`` a été
    écrit AVANT cette fiche — il ne porte PAS ``skipped_asset_scheme`` (mêmes conditions
    que les 1404 ``run.json`` réels de la campagne du 2026-08-23). ``aggregate_counters``
    l'ajoute quand même au résultat, valant 0 (D6) : ``totals`` porte bien la clé alors que
    AUCUN fichier du corpus ne la porte — la preuve directe de la rétrocompatibilité de
    lecture, sans toucher au corpus."""
    totals = aggregate_counters(FIXTURES_ROOT, "C07")
    assert totals == {
        "found_stac": 15,
        "skipped_scene_cloud": 1,
        "off_tile": 2,
        "found_tile": 12,
        "skipped_asset_scheme": 0,
        "ingested": 6,
        "rejected_clouds": 3,
        "rejected_invalid": 1,
        "rejected_nodata": 1,
        "failed": 1,
        "skipped": 0,
    }
    # Les deux invariants bouclent : 15 = 1+2+12+0 ; 12 = 6+3+1+1+1+0.
    assert totals["found_stac"] == (
        totals["skipped_scene_cloud"]
        + totals["off_tile"]
        + totals["found_tile"]
        + totals["skipped_asset_scheme"]
    )
    assert totals["found_tile"] == (
        totals["ingested"]
        + totals["rejected_clouds"]
        + totals["rejected_invalid"]
        + totals["rejected_nodata"]
        + totals["failed"]
        + totals["skipped"]
    )


def test_o7_run_json_reel_sans_la_cle_neuve_reste_lisible() -> None:
    """data-01/O7 : confirme, en lisant le FICHIER brut, que le corpus C07 ne porte PAS
    ``skipped_asset_scheme`` -- condition d'entrée exacte de l'oracle, pas une hypothèse."""
    run_path = FIXTURES_ROOT / "C07" / "runs" / "run-2026-01-31.json"
    data = json.loads(run_path.read_text(encoding="utf-8"))
    assert "skipped_asset_scheme" not in data["counters"]

    # aggregate_counters relit ce fichier (parmi d'autres du site) sans lever, et le
    # compteur neuf absent vaut bien 0 dans le résultat.
    totals = aggregate_counters(FIXTURES_ROOT, "C07")
    assert totals["skipped_asset_scheme"] == 0


def test_corpus_c07_a_douze_manifestes() -> None:
    """Le corpus C07 porte exactement les 12 manifestes de found_tile (comptes CONNUS)."""
    manifests = list_for_site(FIXTURES_ROOT, "C07")
    assert len(manifests) == 12


# --- O2bis : conservation violée -------------------------------------------------------


def test_write_run_conservation_violee_o2bis(tmp_path: Path) -> None:
    """O2bis : off_tile muté (2 -> 3) casse found_stac == somme d'enveloppe -> lève."""
    run = _sample_run(
        counters={
            "found_stac": 15,
            "skipped_scene_cloud": 1,
            "off_tile": 3,  # muté : 1+3+12+0 = 16 != 15
            "found_tile": 12,
            "skipped_asset_scheme": 0,
            "ingested": 6,
            "rejected_clouds": 3,
            "rejected_invalid": 1,
            "rejected_nodata": 1,
            "failed": 1,
            "skipped": 0,
        }
    )
    with pytest.raises(ConservationError):
        write_run(tmp_path, run)
    # Rien n'a été écrit (write_run vérifie AVANT d'écrire).
    assert list_runs(tmp_path, run.site_id) == []


def test_aggregate_counters_conservation_violee_o2bis(tmp_path: Path) -> None:
    """O2bis : un run.json corrompu sur disque fait lever aggregate_counters à la relecture."""
    site_dir = shutil.copytree(FIXTURES_ROOT / "C07", tmp_path / "C07")
    run_path = site_dir / "runs" / "run-2026-01-31.json"
    data = json.loads(run_path.read_text(encoding="utf-8"))
    data["counters"]["off_tile"] = 3  # casse l'invariant d'enveloppe
    run_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ConservationError):
        aggregate_counters(tmp_path, "C07")


def test_write_run_cle_manquante_leve() -> None:
    """Un counters incomplet (clé manquante) lève ConservationError, pas un KeyError brut."""
    run = _sample_run(counters={"found_stac": 1})
    with pytest.raises(ConservationError):
        write_run(Path("unused"), run)


def test_o8_write_run_stricte_meme_avec_seul_skipped_asset_scheme_absent(tmp_path: Path) -> None:
    """data-01/O8 : counters par ailleurs COMPLET et cohérent, seule ``skipped_asset_scheme``
    manque -- ``write_run`` lève quand même ``ConservationError`` (la tolérance D6 vaut
    UNIQUEMENT à la lecture d'un run.json déjà écrit, jamais à l'écriture d'un run neuf) et
    n'écrit rien."""
    run = _sample_run(
        counters={
            "found_stac": 3,
            "skipped_scene_cloud": 0,
            "off_tile": 0,
            "found_tile": 3,
            # "skipped_asset_scheme" volontairement absent.
            "ingested": 3,
            "rejected_clouds": 0,
            "rejected_invalid": 0,
            "rejected_nodata": 0,
            "failed": 0,
            "skipped": 0,
        }
    )
    with pytest.raises(ConservationError):
        write_run(tmp_path, run)
    assert list_runs(tmp_path, run.site_id) == []


# --- O3 : interruption simulée, tmp orphelin --------------------------------------------


def test_tmp_orphelin_invisible_o3(tmp_path: Path) -> None:
    """O3 : un fichier tmp orphelin (écriture interrompue) n'est vu ni par read ni par list."""
    manifest = _sample_manifest()
    item_dir = tmp_path / manifest.site_id / manifest.item_id
    item_dir.mkdir(parents=True)
    # Simule une interruption : le tmp existe, jamais renommé en manifest.json.
    (item_dir / ".manifest.json.12345.tmp").write_text('{"broken": true', encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        read_manifest(tmp_path, manifest.site_id, manifest.item_id)
    assert list_for_site(tmp_path, manifest.site_id) == []


def test_write_manifest_est_atomique_pas_de_tmp_residuel(tmp_path: Path) -> None:
    """Après write_manifest, seul manifest.json existe : pas de tmp résiduel dans le dossier."""
    manifest = _sample_manifest()
    write_manifest(tmp_path, manifest)
    item_dir = tmp_path / manifest.site_id / manifest.item_id
    assert [p.name for p in item_dir.iterdir()] == ["manifest.json"]


# --- O3bis : sérialisation du grid_hash --------------------------------------------------


def test_grid_hash_leve_sur_grille_vide() -> None:
    """Grille non posée (défauts None) : grid_hash lève EmptyGridError, pas un hash bidon."""
    with pytest.raises(EmptyGridError):
        grid_hash(Grid(), _settings())


def test_grid_hash_int_et_float_identiques_o3bis() -> None:
    """699960 (int) et 699960.0 (float, relecture YAML) donnent le MÊME grid_hash."""
    settings = _settings()
    grid_int = Grid(epsg=32631, origin_x=699960, origin_y=5500020)
    grid_float = Grid(epsg=32631, origin_x=699960.0, origin_y=5500020.0)
    assert grid_hash(grid_int, settings) == grid_hash(grid_float, settings)


def test_grid_hash_change_avec_bandes_20m_o3bis() -> None:
    """Un changement de BAND_ORDER_20M (3 -> 6 bandes) donne un hash DIFFÉRENT."""
    settings = _settings()
    grid = Grid(epsg=32631, origin_x=699960, origin_y=5500020)
    hash_6_bandes = grid_hash(grid, settings)
    hash_3_bandes = grid_hash(grid, settings, band_order_20m=("rededge1", "rededge2", "rededge3"))
    assert hash_6_bandes != hash_3_bandes


# --- O4 : last_datetime, statuts rejetés inclus -------------------------------------------


def test_last_datetime_inclut_rejetes_o4() -> None:
    """O4 : last_datetime sur C07 rend la bonne date — celle du manifeste FAILED, le + récent."""
    assert last_datetime(FIXTURES_ROOT, "C07") == "2026-01-25T10:15:00Z"


def test_last_datetime_site_vide_rend_none(tmp_path: Path) -> None:
    """Un site sans aucun manifeste rend None plutôt qu'une erreur."""
    assert last_datetime(tmp_path, "INCONNU") is None


# --- O4bis : item_ids_for_site vs aggregate_counters sur runs recouvrants -----------------


def test_item_ids_for_site_vs_aggregate_o4bis() -> None:
    """O4bis : union exacte (7 items) alors qu'aggregate_counters sur-compte de 3 (10 vs 7)."""
    ids = item_ids_for_site(FIXTURES_ROOT, "OVERLAP")
    assert ids == {f"S2A_OVERLAP_{i:03d}" for i in range(1, 8)}
    assert len(ids) == 7

    totals = aggregate_counters(FIXTURES_ROOT, "OVERLAP")
    assert totals["ingested"] == 10  # 5 (run A) + 5 (run B), 3 items comptés deux fois
    assert totals["ingested"] - len(ids) == 3  # la preuve du sur-comptage


# --- l0-07 : write_manifest refuse un statut illégitime -------------------------------


def test_write_manifest_refuse_skipped_o1_l0_07(tmp_path: Path) -> None:
    """O1 (l0-07) : status="skipped" lève ManifestStatusError, rien n'est écrit -- ni
    manifest.json, ni tmp résiduel (le dossier cible n'existe même pas : la garde est
    vérifiée AVANT toute création de répertoire)."""
    manifest = _sample_manifest(status="skipped")
    with pytest.raises(ManifestStatusError):
        write_manifest(tmp_path, manifest)
    item_dir = tmp_path / manifest.site_id / manifest.item_id
    assert not item_dir.exists()


def test_write_manifest_refuse_casse_et_faute_o2_l0_07(tmp_path: Path) -> None:
    """O2 (l0-07) : la garde n'est pas une simple exclusion de "skipped" -- une casse
    différente ("Ingested") et une faute de frappe ("ingere") lèvent aussi, toutes les
    deux, et rien n'est écrit dans les deux cas."""
    for statut_invalide in ("Ingested", "ingere"):
        manifest = _sample_manifest(status=statut_invalide, item_id=f"item-{statut_invalide}")
        with pytest.raises(ManifestStatusError):
            write_manifest(tmp_path, manifest)
        item_dir = tmp_path / manifest.site_id / manifest.item_id
        assert not item_dir.exists()


@pytest.mark.parametrize("statut", sorted(MANIFEST_STATUSES))
def test_write_manifest_accepte_les_5_statuts_legitimes_o3_l0_07(
    tmp_path: Path, statut: str
) -> None:
    """O3 (l0-07) : les 5 statuts légitimes, un par un, écrivent normalement et se relisent
    identiques par read_manifest -- 5/5."""
    manifest = _sample_manifest(status=statut, item_id=f"item-{statut}")
    write_manifest(tmp_path, manifest)
    reread = read_manifest(tmp_path, manifest.site_id, manifest.item_id)
    assert reread == manifest


def test_message_manifest_status_error_o4_l0_07(tmp_path: Path) -> None:
    """O4 (l0-07) : le message de ManifestStatusError cite littéralement le statut refusé
    et les 5 statuts admis."""
    manifest = _sample_manifest(status="skipped")
    with pytest.raises(ManifestStatusError) as exc_info:
        write_manifest(tmp_path, manifest)
    message = str(exc_info.value)
    assert "skipped" in message
    for statut_admis in MANIFEST_STATUSES:
        assert statut_admis in message


# --- Divers : comportements auxiliaires -----------------------------------------------


def test_list_runs_corpus_overlap_deux_runs() -> None:
    """list_runs rend bien les 2 runs du corpus OVERLAP, triés par run_id."""
    runs = list_runs(FIXTURES_ROOT, "OVERLAP")
    assert [r.run_id for r in runs] == ["run-A", "run-B"]


def test_manifest_status_rejected_nodata_present_dans_corpus() -> None:
    """Le statut rejected_nodata (arbitrage n°3) est bien représenté dans le corpus C07."""
    manifests = list_for_site(FIXTURES_ROOT, "C07")
    nodata = [m for m in manifests if m.status == "rejected_nodata"]
    assert len(nodata) == 1
    assert nodata[0].chip_nodata_pct > 0


def test_manifest_est_immutable() -> None:
    """Manifest est frozen : replace() permet de dériver une variante sans le muter."""
    manifest = _sample_manifest()
    with pytest.raises(AttributeError):
        manifest.status = "failed"  # type: ignore[misc]
    variant = replace(manifest, status="failed")
    assert variant.status == "failed"
    assert manifest.status == "ingested"


# ── Concurrence : le défaut réel remonté par l0-04.1 (run N6) ────────────────────────


def test_ecriture_atomique_concurrente_sur_la_meme_cible(tmp_path: Path) -> None:
    """8 threads écrivant LE MÊME `run.json` en parallèle : aucune exception, fichier valide.

    ⚠ La cible doit être IDENTIQUE pour que le test morde : le nom du fichier temporaire
    dérive du nom de la cible, donc 8 run_id distincts donnent 8 tmp distincts et ne
    collisionnent jamais. Une première version de ce test utilisait des run_id différents —
    elle restait VERTE après avoir retiré `threading.get_ident()`, donc ne prouvait rien
    (vérifié par mutation avant de l'écrire ainsi).

    Défaut réel reproduit par l0-04.1 sous `--workers 4` : deux fenêtres du même site
    terminant dans la même seconde produisaient le même run_id, donc la même cible, donc le
    même tmp — la première à faire `replace` le faisait disparaître sous la seconde, qui
    échouait en `FileNotFoundError`.
    """
    erreurs: list[BaseException] = []
    depart = threading.Barrier(8)

    def _ecrire() -> None:
        depart.wait()  # maximise le recouvrement réel des écritures
        try:
            write_run(tmp_path, _sample_run(run_id="run-meme-cible"))
        except BaseException as exc:  # noqa: BLE001 — collecté pour être ré-assertée
            erreurs.append(exc)

    fils = [threading.Thread(target=_ecrire) for _ in range(8)]
    for f in fils:
        f.start()
    for f in fils:
        f.join()

    assert erreurs == [], f"écritures concurrentes en échec : {erreurs}"
    # Le dernier écrivain gagne — mais le fichier final doit être COMPLET et relisible :
    # c'est toute la promesse d'atomicité de l0-03.2, que la concurrence ne doit pas casser.
    relu = read_run(tmp_path, "A01", "run-meme-cible")
    assert relu.counters["found_stac"] == 3


def test_run_id_distinct_dans_la_meme_seconde() -> None:
    """Deux `_new_run_id()` consécutifs diffèrent, même appelés dans la même seconde.

    Sans résolution sous-seconde, deux fenêtres d'un même site traitées coup sur coup par
    `backfill` produisaient le même `run.json`, écrasé en silence — un journal perdu ne se
    voit nulle part, c'est le pire mode de défaillance pour une donnée de traçabilité.
    """
    identifiants = {ingestion_module._new_run_id() for _ in range(50)}
    assert len(identifiants) == 50, f"collisions : {50 - len(identifiants)} sur 50"
