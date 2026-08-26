"""adapters/vectors.py — format de stockage des vecteurs d'embedding et clé d'idempotence
(l1-03.1).

⭐ Module **N0** : aucune dépendance à un autre module du projet (ni ``core/``, ni
``adapters/manifests.py``) — seulement des chaînes, ``numpy`` et la bibliothèque standard.
C'est ce qui lui permet de s'écrire avant que ``torch`` soit installé (``l1-00``) et avant
les autres fiches du Lot 1.

Un vecteur, c'est **deux fichiers** à côté du chip :
``<dir>/<model_id>.<spec_hash[:8]>.npy`` (le tableau) et son compagnon
``<dir>/<model_id>.<spec_hash[:8]>.json`` (``VectorMeta``). L'atomicité de chaque fichier
pris isolément (tmp + ``Path.replace``, patron de ``adapters/manifests.py``) ne rend PAS la
**paire** atomique : c'est pourquoi l'ordre d'écriture est contractuel.

- Le ``.npy`` s'écrit D'ABORD, atomiquement.
- Le ``.json`` s'écrit EN DERNIER : c'est LUI le marqueur de complétude.
- ``list_vectors`` ne globe QUE les ``.json`` (patron littéral de
  ``adapters/manifests.py::list_for_site``, qui ne globe que ``manifest.json``) — un
  ``.npy`` orphelin (interruption entre les deux écritures) n'est donc jamais vu : un
  déchet invisible, jamais une erreur.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np


class VectorError(ValueError):
    """Erreur de base du module vectors."""


class CorruptedVectorError(VectorError):
    """Le ``.npy`` désigné par un compagnon présent est illisible ou tronqué."""


@dataclass(frozen=True, slots=True)
class VectorMeta:
    """LA définition unique du compagnon d'un vecteur (les autres fiches y renvoient).

    ``scl_summary`` : forme imbriquée ``{"classes": {...}, "valid_pct": ...}`` — jamais
    plate (revue v4, M5) : mettre ``valid_pct`` au même niveau que les fractions de
    ``classes`` fausserait ``sum(classes.values()) ≈ 1``. ``classes`` reprend les clés
    telles qu'écrites par le manifeste (chaînes de chiffres, ex. ``"3"``, ``"8"``), jamais
    traduites en libellés. ``valid_pct`` est un pourcentage 0-100 (convention du projet,
    comme ``cloud_pct``), dérivé de ``100 - invalid_pct`` (``core/scl.py``), jamais
    recalculé indépendamment.

    ``blas_threads`` et ``torch_version`` sont informatifs (comparaison de vecteurs
    calculés sous des réglages différents) : ils n'entrent PAS dans ``embedding_key``
    (les y mettre invaliderait les vecteurs à chaque changement de machine).
    """

    item_id: str
    site_id: str
    datetime: str
    cloud_pct: float
    scl_summary: dict[str, Any]
    model_id: str
    dim: int
    spec_hash: str
    grid_hash: str
    embedding_key: str
    blas_threads: int | None
    torch_version: str | None
    package_version: str
    written_at: str


def embedding_key(grid_hash: str, model_id: str, spec_hash: str) -> str:
    """Clé d'idempotence : les TROIS composantes, pas deux.

    Sans ``spec_hash``, un changement de résolution d'entrée resservirait des vecteurs
    périmés sans que rien ne le signale (cf. notes de la fiche l1-03.1). Simple
    concaténation stable ``"|"``-séparée : la clé n'a pas besoin d'être hachée, seule son
    égalité/inégalité compte pour ``l1-03.2``.
    """
    return "|".join([grid_hash, model_id, spec_hash])


def torch_version() -> str | None:
    """Version installée de torch, lue SANS l'importer (``importlib.metadata`` seulement).

    Cette fiche est N0 : elle s'écrit avant que torch soit installé, et un ``import torch``
    au niveau module rendrait rouge la garde d'import paresseux (O6). Repli ``None`` si le
    paquet est absent — le champ est informatif, pas structurant.
    """
    try:
        return importlib.metadata.version("torch")
    except importlib.metadata.PackageNotFoundError:
        return None


def blas_threads() -> int | None:
    """Nombre de threads BLAS configurés, lu depuis les variables d'environnement usuelles.

    Aucune dépendance native (pas de ``threadpoolctl``) : simple lecture d'environnement,
    dans l'ordre où les bibliothèques BLAS les consultent le plus couramment. ``None`` si
    aucune n'est positionnée — le champ est informatif, pas structurant.
    """
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        value = os.environ.get(var)
        if value is not None:
            try:
                return int(value)
            except ValueError:
                continue
    return None


def _package_version() -> str:
    """Version installée du paquet ``tiny_wae``."""
    return importlib.metadata.version("tiny_wae")


def build_meta(
    *,
    item_id: str,
    site_id: str,
    item_datetime: str,
    cloud_pct: float,
    scl_summary: dict[str, Any],
    model_id: str,
    dim: int,
    spec_hash: str,
    grid_hash: str,
) -> VectorMeta:
    """Construit un ``VectorMeta`` complet : calcule ``embedding_key`` et lit les champs de
    configuration (``blas_threads``, ``torch_version``, version du paquet, horodatage) —
    l'appelant (``l1-03.2``) n'a jamais à les composer à la main."""
    return VectorMeta(
        item_id=item_id,
        site_id=site_id,
        datetime=item_datetime,
        cloud_pct=cloud_pct,
        scl_summary=scl_summary,
        model_id=model_id,
        dim=dim,
        spec_hash=spec_hash,
        grid_hash=grid_hash,
        embedding_key=embedding_key(grid_hash, model_id, spec_hash),
        blas_threads=blas_threads(),
        torch_version=torch_version(),
        package_version=_package_version(),
        written_at=datetime_now_iso(),
    )


def datetime_now_iso() -> str:
    """Horodatage ISO courant (UTC) — isolé pour rester patchable en test."""
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class Vector:
    """Un vecteur relu : le tableau et son compagnon."""

    array: np.ndarray
    meta: VectorMeta


def _base_name(model_id: str, spec_hash: str) -> str:
    """Base commune du nom de fichier (sans extension) — dérivée UNIQUEMENT de
    ``model_id`` et ``spec_hash`` (revue v3, V-15) : un seul endroit fabrique ce nom."""
    return f"{model_id}.{spec_hash[:8]}"


def _npy_path(directory: Path, model_id: str, spec_hash: str) -> Path:
    return Path(directory) / f"{_base_name(model_id, spec_hash)}.npy"


def _json_path(directory: Path, model_id: str, spec_hash: str) -> Path:
    return Path(directory) / f"{_base_name(model_id, spec_hash)}.json"


def _atomic_write_bytes(path: Path, write: Callable[[Path], None]) -> None:
    """Écrit ``path`` de façon atomique (tmp + ``Path.replace``), ``write`` recevant le
    chemin temporaire à remplir. Le nom du tmp porte le PID ET l'identifiant de thread
    (patron ``adapters/manifests.py::_write_json_atomic`` — collision réelle rencontrée
    sous ``ThreadPoolExecutor`` avec le PID seul)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    write(tmp_path)
    tmp_path.replace(path)


def _write_npy(vector: np.ndarray) -> Callable[[Path], None]:
    """Fabrique la fonction d'écriture passée à ``_atomic_write_bytes`` : ouvre le tmp en
    binaire et y passe le FICHIER (pas le chemin) à ``np.save`` — c'est ce qui empêche
    numpy d'ajouter de lui-même une extension ``.npy`` au nom temporaire (qui se termine
    déjà par ``.tmp``)."""

    def _write(tmp: Path) -> None:
        with tmp.open("wb") as handle:
            np.save(handle, vector, allow_pickle=False)

    return _write


def write_vector(directory: Path, vector: np.ndarray, meta: VectorMeta) -> tuple[Path, Path]:
    """Écrit un vecteur et son compagnon, atomiquement CHACUN, dans cet ordre :

    1. le ``.npy`` (le tableau) ;
    2. le ``.json`` (le compagnon) — c'est lui qui marque la paire complète.

    ``model_id`` n'est pas un argument séparé : le nom de fichier se dérive de ``meta``
    uniquement (revue v3, V-15), pour ne jamais nommer un fichier d'après un modèle décrit
    par un autre.

    Retourne ``(chemin_npy, chemin_json)``.
    """
    directory = Path(directory)
    npy_path = _npy_path(directory, meta.model_id, meta.spec_hash)
    json_path = _json_path(directory, meta.model_id, meta.spec_hash)

    def _write_meta(tmp: Path) -> None:
        tmp.write_text(
            json.dumps(asdict(meta), indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

    _atomic_write_bytes(npy_path, _write_npy(vector))
    _atomic_write_bytes(json_path, _write_meta)
    return npy_path, json_path


def read_vector(directory: Path, model_id: str, spec_hash: str) -> Vector | None:
    """Relit un vecteur. ``spec_hash`` est dans la signature (deux variantes de spec
    peuvent coexister — un glob « un seul match » casserait ``l1-03.2``/O5).

    Rend ``None`` si le compagnon (``.json``) est absent — qu'il n'y ait rien du tout, ou
    qu'un ``.npy`` orphelin traîne seul (déchet, jamais une erreur). Lève
    ``CorruptedVectorError`` si le compagnon est présent mais que le ``.npy`` est absent ou
    illisible.
    """
    directory = Path(directory)
    json_path = _json_path(directory, model_id, spec_hash)
    if not json_path.exists():
        return None

    meta = VectorMeta(**json.loads(json_path.read_text(encoding="utf-8")))
    npy_path = _npy_path(directory, model_id, spec_hash)
    try:
        array = np.load(npy_path, allow_pickle=False)
    except (OSError, ValueError, EOFError) as exc:
        raise CorruptedVectorError(
            f"read_vector : {npy_path} illisible ou tronqué alors que son compagnon "
            f"{json_path} est présent"
        ) from exc
    return Vector(array=array, meta=meta)


def list_vectors(
    directory: Path, *, model_id: str | None = None, spec_hash: str | None = None
) -> list[VectorMeta]:
    """Liste les compagnons présents dans ``directory``, triés par ``model_id`` puis
    ``spec_hash``.

    Ne glob QUE les ``.json`` (patron littéral de
    ``adapters/manifests.py::list_for_site``) : un ``.npy`` orphelin (interruption entre
    les deux écritures, ou tmp résiduel) n'est jamais vu — c'est le ``.json`` qui fait foi.

    Filtres optionnels ``model_id`` / ``spec_hash`` : c'est aux lecteurs de choisir quelle
    spec ils veulent, jamais au hasard du glob (``l1-03.2``/O5 exige que deux specs
    puissent coexister sans se mélanger).
    """
    directory = Path(directory)
    if not directory.exists():
        return []
    metas = [
        VectorMeta(**json.loads(p.read_text(encoding="utf-8")))
        for p in sorted(directory.glob("*.json"))
    ]
    if model_id is not None:
        metas = [m for m in metas if m.model_id == model_id]
    if spec_hash is not None:
        metas = [m for m in metas if m.spec_hash == spec_hash]
    return sorted(metas, key=lambda m: (m.model_id, m.spec_hash))


def scl_summary(scl_class_counts: dict[str, int], invalid_pct: float) -> dict[str, Any]:
    """Construit ``scl_summary`` au format imbriqué ``{"classes": {...}, "valid_pct": ...}``
    (revue v4, M5).

    ``classes`` : les comptes du manifeste (clés = chaînes de chiffres, TELLES QUELLES,
    jamais traduites en libellés — ``core/report.py`` ne porte de libellé que pour 2
    classes sur 12, en fabriquer un second jeu ici recréerait le défaut corrigé par
    ``rep-01``) convertis en fractions du total.
    ``valid_pct`` : DÉRIVÉ de ``invalid_pct`` (``core/scl.py::verdict``, ou le champ déjà
    calculé du manifeste) — ``100 - invalid_pct``, jamais recalculé indépendamment, sur le
    même dénominateur.
    """
    total = sum(scl_class_counts.values())
    if total == 0:
        raise VectorError("scl_summary : somme des comptes SCL nulle")
    classes = {cls: count / total for cls, count in scl_class_counts.items()}
    return {"classes": classes, "valid_pct": 100.0 - invalid_pct}


__all__ = [
    "CorruptedVectorError",
    "Vector",
    "VectorError",
    "VectorMeta",
    "blas_threads",
    "build_meta",
    "embedding_key",
    "list_vectors",
    "read_vector",
    "scl_summary",
    "torch_version",
    "write_vector",
]
