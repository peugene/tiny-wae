#!/usr/bin/env python3
"""smoke.py — le gate permanent : deux modes + garde réseau de contrat (l0-03.7).

Remplace le smoke minimal de l0-03.4 (double en mémoire) : ce module fait tourner le
pipeline `ingest` RÉEL sur le corpus de fixtures COG enregistré (`tests/fixtures/`,
l0-03.5) via `FixtureSource`, dans ses deux modes :

- ``--replay`` (défaut, câblé dans `just check`) : hors ligne, déterministe, RAPIDE — un
  seul item réel (le clair gelé du site A01, cf. chapeau l0-02), lu deux fois pour la
  répétabilité (O4), plus deux cas négatifs ciblés (O2, O3/O3bis).
- ``--live`` (hors gate) : le MÊME chemin via `EarthSearchSource`, réseau réel, publie
  durée + octets écrits par chip (baseline attendue par l0-04).

⭐ **Garde réseau de CONTRAT, pas de transport (décision E-b, mesurée en revue v3)** :
`pytest-socket` (utilisé par la suite `pytest`) patche le module `socket` de la stdlib
Python, mais rasterio lit les rasters via **GDAL/libcurl (C)** — un flux qui ne passe
JAMAIS par le `socket` Python. Une garde qui se contenterait de `pytest-socket` laisserait
donc ce smoke passer **VERT en téléchargeant réellement** (le faux-vert que ce module doit
justement empêcher). C'est pourquoi `adapters/chips.py` porte sa propre garde
(`RemoteAccessForbidden`, appliquée AVANT toute ouverture rasterio) sous
`TINY_WAE_OFFLINE=1` — posé par ce script lui-même en mode `--replay`, jamais par
l'appelant. `pytest-socket` reste une ceinture utile pour le seul chemin STAC
(httpx/pystac-client), mais ne couvre pas le chemin GDAL exercé ici.

Le mode `--replay` pose puis REPOSE `TINY_WAE_OFFLINE` (jamais de fuite dans le reste de
`just check`). Toutes les sorties de ce script partent dans un `tempfile.TemporaryDirectory()`
— jamais dans `./data`.
"""

from __future__ import annotations

import dataclasses
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from tiny_wae.adapters import chips as chips_module
from tiny_wae.adapters.chips import OFFLINE_ENV_VAR, RemoteAccessForbidden
from tiny_wae.adapters.config_io import (
    DEFAULT_SETTINGS_PATH,
    DEFAULT_SITES_PATH,
    load_settings,
    load_sites,
)
from tiny_wae.adapters.fixture_source import DEFAULT_COG_DIR, DEFAULT_STAC_DIR, FixtureSource
from tiny_wae.adapters.ingestion import ingest_from_source
from tiny_wae.adapters.manifests import read_manifest
from tiny_wae.adapters.stac import EarthSearchSource, StacSource
from tiny_wae.core.acquisition import Acquisition
from tiny_wae.core.envelope import Envelope
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Site
from tiny_wae.core.windows import Window

# Site + item réels du corpus l0-03.5 (site A01, tuile 31TGJ) — l'item clair gelé du
# chapeau l0-02 (cc 0,00217 %), fenêtre resserrée à son seul jour pour rester déterministe
# et rapide (un smoke qui interrogerait tout le corpus paierait le coût à CHAQUE fiche).
SITE_ID = "A01"
ITEM_ID = "S2A_31TGJ_20240801_0_L2A"
_WINDOW = Window(start=datetime(2024, 8, 1), end=datetime(2024, 8, 2))

# Hashes de contenu GRAVÉS (O1) — capturés sur un run réussi de référence, cf. Résumé de
# la fiche l0-03.7. Portent sur le contenu DÉCODÉ (tableau numpy + CRS + transform +
# dtype — décision d'ancrage n°7 du chapeau), jamais les octets du GeoTIFF.
EXPECTED_CONTENT_HASHES = {
    "chip.tif": "a889f09a5f34af071ba6768014865b46a9f50f4fb1a0fdcca18702f009f1837d",
    "chip_20m.tif": "1898963d3a40c6d3e35e752d044956d4319d5e88657805c4eea604d10d40e90d",
    "scl.tif": "a04cf6eb87cfaa6e1e90ab9f46b70c4d18dbe31f604141e456e184a29d67d96d",
}


def _settings() -> Settings:
    """Réglages RÉELS (`config/settings.yaml`) — le corpus a été clippé sur ces tailles
    par `scripts/record_cog_fixtures.py` ; des réglages différents désaligneraient les
    fenêtres lues avec l'emprise réellement enregistrée."""
    return load_settings(DEFAULT_SETTINGS_PATH)


def _site(site_id: str) -> Site:
    """Cherche `site_id` dans `config/sites.yaml` — le smoke n'invente aucun site."""
    for site in load_sites(DEFAULT_SITES_PATH):
        if site.id == site_id:
            return site
    raise AssertionError(f"site {site_id!r} absent de config/sites.yaml")


def _set_offline(value: bool) -> str | None:
    """Pose ou retire `TINY_WAE_OFFLINE`, rend la valeur PRÉCÉDENTE (pour restauration)."""
    previous = os.environ.get(OFFLINE_ENV_VAR)
    if value:
        os.environ[OFFLINE_ENV_VAR] = "1"
    else:
        os.environ.pop(OFFLINE_ENV_VAR, None)
    return previous


def _restore_offline(previous: str | None) -> None:
    """Repose l'environnement dans son état initial (décision d'ancrage n°5) — un
    `os.environ` qui fuit dans le reste de `just check` serait un effet de bord invisible."""
    if previous is None:
        os.environ.pop(OFFLINE_ENV_VAR, None)
    else:
        os.environ[OFFLINE_ENV_VAR] = previous


def check_o1_o4_ingest_ok(dest: Path, *, run_label: str) -> None:
    """O1 + un témoin de O4 : ingestion RÉELLE (FixtureSource, corpus enregistré) d'un
    `data_root` neuf — 3 fichiers, manifeste `ingested`, `content_hashes` == valeurs
    gravées, `assets_read > 0`. Appelée deux fois (O4, `data_root` vierge à chaque fois)
    par `run_replay` pour la répétabilité."""
    settings = _settings()
    site = _site(SITE_ID)
    source: StacSource = FixtureSource(settings, stac_dir=DEFAULT_STAC_DIR, cog_dir=DEFAULT_COG_DIR)
    data_root = dest / "data"

    outcome = ingest_from_source(
        site=site, window=_WINDOW, source=source, settings=settings, data_root=data_root
    )

    assert outcome.run.assets_read > 0, (
        f"[{run_label}] assets_read={outcome.run.assets_read} attendu > 0"
    )

    item_dir = data_root / SITE_ID / ITEM_ID
    for filename in ("chip.tif", "chip_20m.tif", "scl.tif"):
        assert (item_dir / filename).exists(), (
            f"[{run_label}] fichier manquant : {item_dir / filename}"
        )

    manifest = read_manifest(data_root, SITE_ID, ITEM_ID)
    assert manifest.status == "ingested", (
        f"[{run_label}] status={manifest.status!r} attendu 'ingested'"
    )
    assert manifest.assets_read > 0, f"[{run_label}] manifest.assets_read attendu > 0"
    for filename, expected_hash in EXPECTED_CONTENT_HASHES.items():
        actual_hash = manifest.content_hashes.get(filename)
        assert actual_hash == expected_hash, (
            f"[{run_label}] content_hashes[{filename!r}]={actual_hash!r} "
            f"attendu {expected_hash!r} (le contenu décodé a changé)"
        )


def check_o2_missing_local_fixture(dest: Path) -> None:
    """O2 : une fixture LOCALE retirée — un asset dont le href `file://` pointe vers un
    chemin qui n'existe pas sur disque (aucun mock : c'est un `file://` réel, absolu,
    construit à partir du corpus enregistré, juste inexistant). Sous
    `TINY_WAE_OFFLINE=1`, le schéma `file://` passe la garde de contrat (O3 ne s'applique
    pas ici — décision d'ancrage n°4) : l'échec vient de l'OUVERTURE rasterio elle-même,
    et son message nomme le chemin manquant, littéralement, dans `manifest.cause`."""
    settings = _settings()
    site = _site(SITE_ID)
    source = FixtureSource(settings, stac_dir=DEFAULT_STAC_DIR, cog_dir=DEFAULT_COG_DIR)
    envelope = source.search(site, _WINDOW)
    assert envelope.items, "corpus A01 vide sur la fenêtre du smoke — fixture absente ?"
    acquisition = envelope.items[0]

    missing_path = (DEFAULT_COG_DIR / ITEM_ID / "scl_MISSING.tif").resolve()
    assert not missing_path.exists(), f"garde-fou : {missing_path} ne devrait pas exister"
    broken_assets = dict(acquisition.assets)
    broken_assets["scl"] = missing_path.as_uri()
    broken_acquisition = dataclasses.replace(acquisition, assets=broken_assets)

    data_root = dest / "data_o2"
    outcome = ingest_from_source(
        site=site,
        window=_WINDOW,
        source=_SingleItemSource(envelope=envelope, item=broken_acquisition),
        settings=settings,
        data_root=data_root,
    )
    assert outcome.run.counters["failed"] == 1, (
        f"O2 : counters['failed']={outcome.run.counters['failed']} attendu 1"
    )
    manifest = read_manifest(data_root, SITE_ID, ITEM_ID)
    assert manifest.status == "failed", f"O2 : status={manifest.status!r} attendu 'failed'"
    cause = manifest.cause or ""
    assert str(missing_path) in cause, (
        f"O2 : chemin manquant {str(missing_path)!r} absent de manifest.cause={cause!r}"
    )


def _https_envelope() -> tuple[Envelope, str]:
    """Enveloppe A01 dont les hrefs sont restés en `https://`, et le href `scl` de son
    premier item.

    Fabriquée SANS rien inventer ni mocker (décision d'ancrage n°3) : une `FixtureSource`
    dont `cog_dir` est un répertoire VIDE ne trouve aucun fichier local à `_localize_hrefs`
    — les hrefs de l'enveloppe restent ceux enregistrés par `record_cog_fixtures.py`.
    """
    settings = _settings()
    site = _site(SITE_ID)
    with tempfile.TemporaryDirectory() as empty_cog_dir:
        source = FixtureSource(settings, stac_dir=DEFAULT_STAC_DIR, cog_dir=Path(empty_cog_dir))
        envelope = source.search(site, _WINDOW)
    assert envelope.items, "corpus A01 vide sur la fenêtre du smoke — fixture absente ?"
    href = envelope.items[0].assets["scl"]
    assert href.startswith("https://"), (
        f"href={href!r} attendu https:// (cog_dir vide, rien à localiser)"
    )
    return envelope, href


def check_o3_contract_guard_end_to_end(dest: Path) -> None:
    """O3 : sous `TINY_WAE_OFFLINE=1`, un href `https://` fait ÉCHOUER l'ingestion réelle,
    avec `RemoteAccessForbidden` nommée dans la cause — et sans qu'aucune requête ne parte.

    ⭐ Passe par le PIPELINE COMPLET (`ingest_from_source`), pas par un appel direct à la
    garde : ce que l'oracle protège, ce n'est pas que `chips._guard_href` sache lever, c'est
    que le chemin d'ingestion la déclenche. Un test qui appellerait la garde isolément
    resterait VERT si l'appel disparaissait de `read_scl` — précisément le faux-vert que
    cette fiche existe pour empêcher.

    Aucun réseau n'est émis : la garde lève AVANT toute ouverture rasterio, c'est le
    contrat de `adapters/chips` (décision E-b). C'est ce qui rend ce test possible dans un
    gate hors ligne.
    """
    settings = _settings()
    site = _site(SITE_ID)
    envelope, _ = _https_envelope()

    data_root = dest / "data_o3"
    outcome = ingest_from_source(
        site=site,
        window=_WINDOW,
        source=_SingleItemSource(envelope=envelope, item=envelope.items[0]),
        settings=settings,
        data_root=data_root,
    )
    assert outcome.run.counters["failed"] == 1, (
        f"O3 : counters['failed']={outcome.run.counters['failed']} attendu 1 "
        "(href https:// sous TINY_WAE_OFFLINE=1 doit faire échouer l'item)"
    )
    manifest = read_manifest(data_root, SITE_ID, envelope.items[0].item_id)
    assert manifest.status == "failed", f"O3 : status={manifest.status!r} attendu 'failed'"
    cause = manifest.cause or ""
    assert RemoteAccessForbidden.__name__ in cause or "TINY_WAE_OFFLINE" in cause, (
        f"O3 : cause={cause!r} ne nomme ni RemoteAccessForbidden ni TINY_WAE_OFFLINE"
    )
    assert manifest.files == [], f"O3 : files={manifest.files!r} — rien ne doit être écrit"


def check_o3bis_guard_not_permanent() -> None:
    """O3bis : sans `TINY_WAE_OFFLINE`, la garde ne bloque rien (elle n'est pas permanente).

    Seul cas où l'on appelle `chips._guard_href` directement plutôt que le pipeline :
    vérifier littéralement que « l'ouverture est tentée normalement » obligerait à émettre
    une vraie requête réseau DANS le gate, ce qui est exclu (`just check` reste hors ligne).
    On vérifie donc que rien ne s'y oppose, ce qui est exactement ce que l'oracle demande.
    """
    _, href = _https_envelope()
    previous = _set_offline(False)
    try:
        try:
            chips_module._guard_href(href)  # noqa: SLF001 — fonction interne, cf. docstring.
        except RemoteAccessForbidden as exc:
            raise AssertionError(
                "O3bis : la garde ne doit PAS bloquer quand TINY_WAE_OFFLINE est absent "
                f"(RemoteAccessForbidden levée : {exc})"
            ) from exc
    finally:
        _restore_offline(previous)


@dataclasses.dataclass(frozen=True, slots=True)
class _SingleItemSource:
    """Double EN MÉMOIRE rejouant une enveloppe RÉELLE (déjà servie par `FixtureSource`)
    avec un seul item substitué — utilisé par O2 pour injecter l'asset cassé sans passer
    par un `FixtureSource` qui re-localiserait le href (cf. `check_o2_missing_local_fixture`)."""

    envelope: Envelope
    item: Acquisition

    def search(self, site: Site, window: Window) -> Envelope:
        """Rend l'enveloppe d'origine, `items` réduits au seul item substitué."""
        return dataclasses.replace(self.envelope, items=[self.item])


def run_replay() -> None:
    """Mode `--replay` (défaut, câblé dans `just check`) : hors ligne, déterministe.

    Pose `TINY_WAE_OFFLINE=1` pour toute la durée (décision d'ancrage n°5), l'enlève en
    sortant même en cas d'échec. Exécute, dans l'ordre : O1 (ingestion réelle), O4 (même
    ingestion sur un `data_root` neuf, deuxième témoin de répétabilité), O2 (fixture
    locale manquante), O3 (garde de contrat sur le pipeline complet), puis O3bis hors
    variable (la garde n'est pas permanente).
    """
    previous = _set_offline(True)
    try:
        with tempfile.TemporaryDirectory() as tmp1:
            check_o1_o4_ingest_ok(Path(tmp1), run_label="O1/O4 run 1")
        with tempfile.TemporaryDirectory() as tmp2:
            check_o1_o4_ingest_ok(Path(tmp2), run_label="O1/O4 run 2")
        with tempfile.TemporaryDirectory() as tmp3:
            check_o2_missing_local_fixture(Path(tmp3))
        with tempfile.TemporaryDirectory() as tmp4:
            check_o3_contract_guard_end_to_end(Path(tmp4))
    finally:
        _restore_offline(previous)

    # O3bis se vérifie hors de la variable (elle la retire elle-même le temps du contrôle).
    check_o3bis_guard_not_permanent()


def run_live() -> None:
    """Mode `--live` (hors gate, O5) : MÊME chemin via `EarthSearchSource`, réseau réel.

    Publie durée + octets écrits par chip sur STDOUT — baseline attendue par l0-04. Si le
    réseau est indisponible, l'exception remonte : ce script ne prétend jamais avoir
    mesuré ce qu'il n'a pas mesuré (O5 doit être déclaré NON MESURÉ par l'appelant, pas
    inventé)."""
    settings = _settings()
    site = _site(SITE_ID)
    source: StacSource = EarthSearchSource(settings)

    with tempfile.TemporaryDirectory() as tmp:
        data_root = Path(tmp) / "data"
        start = time.monotonic()
        outcome = ingest_from_source(
            site=site, window=_WINDOW, source=source, settings=settings, data_root=data_root
        )
        duration_s = time.monotonic() - start

        manifest = read_manifest(data_root, SITE_ID, ITEM_ID)
        assert manifest.status == "ingested", (
            f"--live : status={manifest.status!r} attendu 'ingested'"
        )
        bytes_per_chip = manifest.bytes_written / len(manifest.files) if manifest.files else 0.0

        print(
            f"smoke --live : vert — durée={duration_s:.2f}s bytes_written={manifest.bytes_written} "
            f"({bytes_per_chip:.0f} octets/chip en moyenne, {len(manifest.files)} fichiers) "
            f"run_id={outcome.run.run_id}"
        )


def main() -> None:
    """Point d'entrée `just smoke` (`--replay`, défaut) et `--live` (hors gate, O5)."""
    live = "--live" in sys.argv[1:]
    try:
        if live:
            run_live()
        else:
            run_replay()
    except AssertionError as exc:
        print(f"smoke: ROUGE — {exc}", file=sys.stderr)
        sys.exit(1)

    if not live:
        print(
            "smoke: vert — replay hors ligne (O1/O4 ingestion réelle, O2 fixture manquante, "
            "O3/O3bis garde de contrat)"
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
