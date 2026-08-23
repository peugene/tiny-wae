"""adapters/manifests.py — module-interface du lot d'ingestion (l0-03).

LE seul endroit du projet qui lit ou écrit un manifeste ou un journal de run : l0-04, l0-05
et l0-06 n'accèdent JAMAIS aux JSON directement, ils passent par cette API.

Porte deux schémas versionnés (``schema_version: 1``) :

- **manifeste** (``<data_root>/{site_id}/{item_id}/manifest.json``) : le compte-rendu d'un
  item traité (ingéré ou rejeté), avec son ``grid_hash`` d'idempotence, son
  ``chip_nodata_pct`` (garde nodata mesurée sur le chip — arbitrage n°3), sa
  ``radiometry`` par asset (arbitrage n°1) et ses ``content_hashes`` (contenu décodé, pas
  les octets du GeoTIFF — cf. chapeau l0-03).
- **run.json** (``<data_root>/{site_id}/runs/{run_id}.json``) : le journal d'un run, avec
  ses compteurs et **deux invariants de conservation** vérifiés à l'écriture
  (``ConservationError`` sinon, décision E-a) :
  ``found_stac == skipped_scene_cloud + off_tile + found_tile + skipped_asset_scheme``
  (``skipped_asset_scheme`` : D2 de la fiche data-01) et
  ``found_tile == somme des 6 statuts``. ⭐ D6 (data-01) : ``skipped_asset_scheme`` est
  TOLÉRÉ ABSENT à la LECTURE (``aggregate_counters``, il vaut alors 0) — jamais à
  l'écriture, qui reste stricte.

⭐ Arbitrage n°2 (21/08) : ``aggregate_counters`` **somme** les compteurs de runs et ne
prétend PAS dédupliquer (impossible : ``run.json`` ne porte que des scalaires) — en régime
permanent les runs se recouvrent, donc les compteurs agrégés **sur-comptent** ; c'est
volontaire, ils servent au volume, jamais à la complétude. Le contrôle de complétude
utilise ``item_ids_for_site`` — un **ensemble d'item_id** reconstruit par lecture directe
des manifestes présents sur disque (un manifeste par item, quel que soit le nombre de runs
qui l'ont traversé), donc exact par construction.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from tiny_wae.core.bands import BAND_ORDER_10M, BAND_ORDER_20M
from tiny_wae.core.envelope import ENVELOPE_COUNTERS
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Grid
from tiny_wae.core.statuses import MANIFEST_STATUSES, RUN_STATUSES

SCHEMA_VERSION = 1

# Les 5 compteurs d'enveloppe + les 6 statuts — COMPOSÉS depuis core/, jamais recopiés
# (post-revue 1, constat A2 : le vocabulaire de domaine appartient à ``core/``).
_COUNTER_KEYS: tuple[str, ...] = (*ENVELOPE_COUNTERS, *RUN_STATUSES)

# D6 (fiche data-01) : compteurs d'enveloppe tolérés ABSENTS à la LECTURE d'un run.json
# déjà écrit (valent alors 0) — jamais à l'écriture (``write_run`` reste strict, O8). Liste
# EXPLICITE plutôt qu'un "toute clé manquante vaut 0" générique : un statut manquant sur un
# journal existant resterait une vraie corruption, jamais masquée silencieusement. Seul
# ``skipped_asset_scheme`` (D2, absent des 1404 run.json de la campagne du 2026-08-23) y
# figure ; un futur compteur neuf s'ajouterait ici explicitement, au même titre.
_READ_TOLERANT_COUNTER_KEYS: frozenset[str] = frozenset({"skipped_asset_scheme"})


class ManifestError(ValueError):
    """Erreur de base du module manifests."""


class EmptyGridError(ManifestError):
    """La grille du site n'est pas encore posée (epsg/origin_x/origin_y à None)."""


class ConservationError(ManifestError):
    """Un invariant de conservation des compteurs de run est violé (décision E-a)."""


class ManifestStatusError(ManifestError):
    """``manifest.status`` n'est pas un statut légitime (fiche l0-07, garde symétrique de
    ``ConservationError`` : à l'ÉCRITURE d'un manifeste, jamais à sa lecture)."""


@dataclass(frozen=True, slots=True)
class Manifest:
    """Compte-rendu d'un item traité — un fichier ``manifest.json`` par item.

    ``radiometry`` est PAR ASSET (clé d'asset -> {"scale":..., "offset":...} ou ``None``),
    jamais deux scalaires d'item (arbitrage n°1). ``content_hashes`` porte, par fichier
    produit, le hash du CONTENU DÉCODÉ (array + CRS + transform + dtype), jamais les
    octets du GeoTIFF (le WKT PROJ embarqué dérive entre versions/plateformes).
    """

    schema_version: int
    site_id: str
    item_id: str
    datetime: str
    tile: str
    sequence: str
    platform: str
    status: str
    cause: str | None
    invalid_pct: float
    cloud_pct: float
    chip_nodata_pct: float
    scl_class_counts: dict[str, int]
    processing_baseline: str
    boa_offset_applied: bool
    radiometry: dict[str, dict[str, float] | None]
    grid_hash: str
    assets_read: int
    content_hashes: dict[str, str]
    bytes_downloaded: int
    bytes_written: int
    duration_s: float
    files: list[str]
    versions: dict[str, str]


@dataclass(frozen=True, slots=True)
class Run:
    """Journal d'un run d'ingestion — un fichier ``run.json`` par run.

    ``window`` est un mapping ``{"start": ..., "end": ...}`` (chaînes ISO). ``counters``
    porte les 5 compteurs d'enveloppe (l0-02, ``skipped_asset_scheme`` ajouté par data-01)
    + les 6 statuts (cf. ``RUN_STATUSES``) ; ``write_run`` vérifie les deux invariants de
    conservation avant d'écrire.
    """

    schema_version: int
    site_id: str
    run_id: str
    window: dict[str, str]
    counters: dict[str, int]
    assets_read: int
    bytes_downloaded: int
    tile_suspect: bool
    duration_s: float


def grid_hash(
    grid: Grid,
    settings: Settings,
    *,
    band_order_10m: tuple[str, ...] = BAND_ORDER_10M,
    band_order_20m: tuple[str, ...] = BAND_ORDER_20M,
) -> str:
    """Signature d'idempotence de la grille (sha256 d'une chaîne canonique, chapeau l0-03).

    Chaîne canonique : ``epsg|origin_x|origin_y|chip_px_10m|chip_px_20m|bandes_10m|bandes_20m``,
    origines normalisées par ``int()`` (O3bis : ``699960`` et ``699960.0`` donnent le MÊME
    hash — sinon une relecture YAML déclenche une ré-ingestion fantôme de tout le parc).
    La signature inclut les ordres de bandes et les tailles : un changement (ex. D-b, 3 →
    6 bandes à 20 m) DOIT invalider les chips existants (les paramètres ``band_order_*``
    permettent de le tester sans dépendre de l'état du module ``core.bands``).

    Lève ``EmptyGridError`` si la grille n'est pas encore posée : hacher la chaîne
    ``"None|None|None|…"`` produirait un hash stable mais faux.
    """
    if grid.epsg is None or grid.origin_x is None or grid.origin_y is None:
        raise EmptyGridError(
            "grid_hash : grille vide (epsg/origin_x/origin_y à None) — la grille du site "
            "doit être posée avant toute ingestion"
        )
    canonical = "|".join(
        [
            str(grid.epsg),
            str(int(grid.origin_x)),
            str(int(grid.origin_y)),
            str(settings.chip_px_10m),
            str(settings.chip_px_20m),
            ",".join(band_order_10m),
            ",".join(band_order_20m),
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _manifest_path(data_root: Path, site_id: str, item_id: str) -> Path:
    """Chemin du manifeste d'un item : ``<data_root>/{site_id}/{item_id}/manifest.json``."""
    return Path(data_root) / site_id / item_id / "manifest.json"


def _run_path(data_root: Path, site_id: str, run_id: str) -> Path:
    """Chemin d'un journal de run : ``<data_root>/{site_id}/runs/{run_id}.json``."""
    return Path(data_root) / site_id / "runs" / f"{run_id}.json"


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> Path:
    """Écrit ``payload`` en JSON de façon atomique : fichier tmp puis ``rename``.

    Le fichier final n'apparaît jamais partiellement écrit (interruption = tmp orphelin,
    jamais de manifeste fantôme — O3). Le nom du tmp ne matche jamais ``manifest.json`` ni
    ``<run_id>.json`` : un ``glob`` ciblé ne le voit donc jamais.

    ⭐ Le nom du tmp porte le PID **ET l'identifiant de thread** : le PID seul ne
    discrimine pas deux threads du MÊME process, et ``adapters/backfill.py`` (l0-04.1) en
    lance un par site. Deux écritures concurrentes de la même cible se disputaient alors le
    même tmp — la première à faire ``replace`` le faisait disparaître sous la seconde, qui
    échouait en ``FileNotFoundError``. Défaut réel, reproduit par l0-04.1 sous
    ``--workers 4``, corrigé ici plutôt que contourné en amont.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )
    tmp_path.replace(path)
    return path


def write_manifest(data_root: Path, manifest: Manifest) -> Path:
    """Écrit le manifeste d'un item, de façon atomique (tmp + rename).

    Lève ``ManifestStatusError`` (et n'écrit rien — ni ``manifest.json``, ni tmp résiduel)
    si ``manifest.status`` n'est pas l'un des statuts légitimes de ``MANIFEST_STATUSES``
    (fiche l0-07) : la garde porte sur l'ÉCRITURE, sur le patron de ``write_run`` /
    ``_validate_counters`` ; ``read_manifest`` reste délibérément permissif (cf. sa
    docstring).

    Doit être appelé EN DERNIER par l'appelant (``adapters/chips.py``), après que tous les
    fichiers de sortie de l'item ont été écrits sur disque — c'est ce qui garantit qu'un
    manifeste présent atteste de fichiers complets.
    """
    if manifest.status not in MANIFEST_STATUSES:
        raise ManifestStatusError(
            f"manifest.status={manifest.status!r} refusé — statuts admis : "
            f"{sorted(MANIFEST_STATUSES)}"
        )
    path = _manifest_path(data_root, manifest.site_id, manifest.item_id)
    return _write_json_atomic(path, asdict(manifest))


def read_manifest(data_root: Path, site_id: str, item_id: str) -> Manifest:
    """Lit le manifeste d'un item. Lève ``FileNotFoundError`` s'il n'existe pas.

    Ne valide PAS ``status`` (délibéré, fiche l0-07) : durcir la lecture rendrait illisible
    un manifeste écrit par une version antérieure, éventuellement moins stricte. La garde
    protège ce qu'on écrit (``write_manifest``), pas ce qu'on a déjà écrit.
    """
    path = _manifest_path(data_root, site_id, item_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    return Manifest(**data)


def list_for_site(data_root: Path, site_id: str) -> list[Manifest]:
    """Liste tous les manifestes d'un site (tri par ``item_id``).

    Ne glob QUE les fichiers nommés exactement ``manifest.json`` : un tmp orphelin
    (nommé différemment, cf. ``_write_json_atomic``) ou un fichier sous ``runs/`` ne sont
    jamais vus.
    """
    site_dir = Path(data_root) / site_id
    if not site_dir.exists():
        return []
    manifests = [
        Manifest(**json.loads(p.read_text(encoding="utf-8")))
        for p in sorted(site_dir.rglob("manifest.json"))
    ]
    return sorted(manifests, key=lambda m: m.item_id)


def last_datetime(data_root: Path, site_id: str) -> str | None:
    """Date/heure (ISO, str) du manifeste le plus récent d'un site, statuts rejetés inclus.

    ``None`` si le site n'a aucun manifeste. Les dates ISO 8601 se comparent lexicalement
    à l'identique de leur ordre chronologique.
    """
    manifests = list_for_site(data_root, site_id)
    if not manifests:
        return None
    return max(m.datetime for m in manifests)


def item_ids_for_site(data_root: Path, site_id: str) -> set[str]:
    """Ensemble EXACT des ``item_id`` déjà manifestés pour un site (arbitrage n°2).

    Reconstruit par lecture directe des manifestes sur disque (un par item, quel que soit
    le nombre de runs qui l'ont traversé) : contrairement à ``aggregate_counters``, cet
    ensemble ne sur-compte jamais les items traités par plusieurs runs qui se recouvrent.
    """
    return {m.item_id for m in list_for_site(data_root, site_id)}


def _validate_counters(counters: dict[str, int]) -> None:
    """Vérifie les deux invariants de conservation d'un ``counters`` de run.json.

    Lève ``ConservationError`` (nommant les valeurs en cause) si l'un des deux invariants
    est violé, ou si une clé attendue manque (décision E-a : l'invariant sait rendre
    rouge plutôt que de laisser un compteur incohérent partir en base).
    """
    missing = [key for key in _COUNTER_KEYS if key not in counters]
    if missing:
        raise ConservationError(f"run.counters : clé(s) manquante(s) {missing}")

    envelope_sum = (
        counters["skipped_scene_cloud"]
        + counters["off_tile"]
        + counters["found_tile"]
        + counters["skipped_asset_scheme"]
    )
    if counters["found_stac"] != envelope_sum:
        raise ConservationError(
            "invariant violé : found_stac="
            f"{counters['found_stac']} != skipped_scene_cloud+off_tile+found_tile"
            f"+skipped_asset_scheme={envelope_sum}"
        )

    status_sum = sum(counters[status] for status in RUN_STATUSES)
    if counters["found_tile"] != status_sum:
        raise ConservationError(
            f"invariant violé : found_tile={counters['found_tile']} != somme des 6 statuts="
            f"{status_sum}"
        )


def write_run(data_root: Path, run: Run) -> Path:
    """Écrit le journal d'un run, de façon atomique, après vérification des invariants.

    Lève ``ConservationError`` (et n'écrit rien) si l'un des deux invariants de
    conservation des compteurs est violé.
    """
    _validate_counters(run.counters)
    path = _run_path(data_root, run.site_id, run.run_id)
    return _write_json_atomic(path, asdict(run))


def read_run(data_root: Path, site_id: str, run_id: str) -> Run:
    """Lit le journal d'un run. Lève ``FileNotFoundError`` s'il n'existe pas."""
    path = _run_path(data_root, site_id, run_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    return Run(**data)


def list_runs(data_root: Path, site_id: str) -> list[Run]:
    """Liste tous les runs d'un site (tri par ``run_id``)."""
    runs_dir = Path(data_root) / site_id / "runs"
    if not runs_dir.exists():
        return []
    runs = [
        Run(**json.loads(p.read_text(encoding="utf-8"))) for p in sorted(runs_dir.glob("*.json"))
    ]
    return sorted(runs, key=lambda r: r.run_id)


def _with_read_tolerant_defaults(counters: dict[str, int]) -> dict[str, int]:
    """D6 (fiche data-01) : complète ``counters`` relu d'un run.json existant avec ``0``
    pour chaque clé de ``_READ_TOLERANT_COUNTER_KEYS`` absente — jamais pour les autres,
    qui restent exigées par ``_validate_counters`` (une clé ANCIENNE manquante est une
    vraie corruption, pas un cas de rétrocompatibilité)."""
    filled = dict(counters)
    for key in _READ_TOLERANT_COUNTER_KEYS:
        filled.setdefault(key, 0)
    return filled


def aggregate_counters(data_root: Path, site_id: str) -> dict[str, int]:
    """Somme les compteurs de tous les runs d'un site — donnée de VOLUME, pas de complétude.

    ⚠ Sur-compte dès que des runs se recouvrent (fenêtres qui se chevauchent en régime
    permanent) : ``run.json`` ne porte que des scalaires, cette fonction ne prétend PAS
    dédupliquer. Pour la complétude (l'ensemble exact des items déjà traités), utiliser
    ``item_ids_for_site``. Chaque run relu est revalidé (``ConservationError`` si un
    invariant y est violé, au même titre qu'à l'écriture) — après complétion D6 des
    compteurs neufs tolérés absents (``_with_read_tolerant_defaults``), pour rester
    lisible sur les 1404 run.json de la campagne du 2026-08-23, écrits avant
    ``skipped_asset_scheme``.
    """
    totals: dict[str, int] = dict.fromkeys(_COUNTER_KEYS, 0)
    for run in list_runs(data_root, site_id):
        counters = _with_read_tolerant_defaults(run.counters)
        _validate_counters(counters)
        for key in _COUNTER_KEYS:
            totals[key] += counters[key]
    return totals
