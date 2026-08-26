"""Tests adapters/vectors.py — format de stockage des vecteurs + clé d'idempotence (l1-03.1).

Couvre l'oracle de la fiche :
- O1  : aller-retour écriture/lecture d'un vecteur + son compagnon, identité champ à champ.
- O2  : embedding_key -- les trois mutations séparées donnent une clé différente, les
        trois composantes inchangées donnent la même clé.
- O3  : tmp orphelin déposé dans le répertoire -- invisible, pas de vecteur fantôme.
- O3b : paire incomplète (.npy sans .json) -- déchet ignoré ; témoin inverse, la paire
        complète est bien vue.
- O4  : .npy tronqué -- erreur typée, pas un tableau silencieusement faux.
- O5  : list_vectors avec deux specs du même modèle + un autre modèle -- filtre exact.
- O6  : import du module dans un sous-processus frais -- torch n'entre jamais dans
        sys.modules.

Couvre aussi le format de scl_summary (imbriqué, valid_pct en pourcentage), exigé par la
définition de "terminé" bien qu'il ne porte pas de ligne d'oracle dédiée.

Non testé (assumé par la fiche) : concurrence réelle multi-thread (l1-03.3), volumes
(l1-04), toute valeur sémantique d'embedding.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from tiny_wae.adapters.vectors import (
    CorruptedVectorError,
    VectorMeta,
    build_meta,
    embedding_key,
    list_vectors,
    read_vector,
    scl_summary,
    write_vector,
)


def _meta(**overrides: object) -> VectorMeta:
    """Fabrique un VectorMeta minimal, valeurs par défaut surchargeables."""
    base = build_meta(
        item_id="item-1",
        site_id="C07",
        item_datetime="2026-08-26T00:00:00Z",
        cloud_pct=1.5,
        scl_summary={"classes": {"4": 1.0}, "valid_pct": 100.0},
        model_id="clay-v1",
        dim=768,
        spec_hash="a1b2c3d4e5f6",
        grid_hash="g1g2g3g4",
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


def test_o1_roundtrip_identity(tmp_path: Path) -> None:
    directory = tmp_path / "embeddings"
    vector = np.arange(8, dtype=np.float32).reshape(2, 4)
    meta = _meta()

    write_vector(directory, vector, meta)
    result = read_vector(directory, meta.model_id, meta.spec_hash)

    assert result is not None
    assert result.meta == meta
    assert np.array_equal(result.array, vector)
    assert result.array.dtype == vector.dtype
    assert result.array.shape == vector.shape


def test_o2_embedding_key_discriminates_each_component() -> None:
    base = embedding_key("grid-a", "model-a", "spec-a")

    assert embedding_key("grid-b", "model-a", "spec-a") != base
    assert embedding_key("grid-a", "model-b", "spec-a") != base
    assert embedding_key("grid-a", "model-a", "spec-b") != base
    assert embedding_key("grid-a", "model-a", "spec-a") == base


def test_o3_orphan_tmp_is_invisible(tmp_path: Path) -> None:
    directory = tmp_path / "embeddings"
    directory.mkdir()
    # Nom de tmp du patron _atomic_write_bytes -- ne se termine jamais par ".json".
    (directory / ".clay-v1.a1b2c3d4.json.4242.99.tmp").write_text("{}", encoding="utf-8")

    assert list_vectors(directory) == []
    assert read_vector(directory, "clay-v1", "a1b2c3d4e5f6") is None


def test_o3b_incomplete_pair_is_waste_until_completed(tmp_path: Path) -> None:
    directory = tmp_path / "embeddings"
    directory.mkdir()
    meta = _meta()
    npy_path = directory / f"{meta.model_id}.{meta.spec_hash[:8]}.npy"
    np.save(npy_path, np.zeros(3, dtype=np.float32))

    # .npy seul : déchet, jamais vu.
    assert list_vectors(directory) == []
    assert read_vector(directory, meta.model_id, meta.spec_hash) is None

    # Témoin inverse : la paire complète est bien vue.
    write_vector(directory, np.ones(3, dtype=np.float32), meta)
    assert len(list_vectors(directory)) == 1
    assert read_vector(directory, meta.model_id, meta.spec_hash) is not None


def test_o4_truncated_npy_raises_typed_error(tmp_path: Path) -> None:
    directory = tmp_path / "embeddings"
    meta = _meta()
    npy_path, _ = write_vector(directory, np.arange(16, dtype=np.float32), meta)
    npy_path.write_bytes(npy_path.read_bytes()[:10])  # tronque en plein header

    with pytest.raises(CorruptedVectorError):
        read_vector(directory, meta.model_id, meta.spec_hash)


def test_o5_list_vectors_filters_by_spec_hash(tmp_path: Path) -> None:
    directory = tmp_path / "embeddings"
    meta_spec1 = _meta(model_id="clay-v1", spec_hash="spec00001111")
    meta_spec2 = _meta(model_id="clay-v1", spec_hash="spec99998888")
    meta_other_model = _meta(model_id="terramind", spec_hash="spec55556666")

    for meta in (meta_spec1, meta_spec2, meta_other_model):
        write_vector(directory, np.zeros(4, dtype=np.float32), meta)

    assert len(list_vectors(directory)) == 3

    filtered = list_vectors(directory, spec_hash="spec00001111")
    assert len(filtered) == 1
    assert filtered[0].spec_hash == "spec00001111"

    filtered_both = list_vectors(directory, model_id="clay-v1", spec_hash="spec99998888")
    assert len(filtered_both) == 1
    assert filtered_both[0].model_id == "clay-v1"
    assert filtered_both[0].spec_hash == "spec99998888"


def test_o6_no_torch_import_in_fresh_subprocess() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import tiny_wae.adapters.vectors; print('torch' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "False"


def test_scl_summary_nested_format_and_valid_pct() -> None:
    summary = scl_summary({"3": 100, "8": 200, "9": 700}, invalid_pct=0.0)

    assert summary["valid_pct"] == 100.0
    assert set(summary["classes"]) == {"3", "8", "9"}
    assert summary["classes"]["8"] == pytest.approx(0.2)
    assert sum(summary["classes"].values()) == pytest.approx(1.0)
