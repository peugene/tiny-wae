"""Tests core/scl.py (l0-03.1).

Couvre l'oracle de la fiche :
- O2 : comptes SCL fabriqués (100 % classe 0 · 40 % classe 8 · 29 % classes {3,8} ·
  50 % classe 11) -> rejected_invalid / rejected_clouds / ingested / ingested (classe 11
  non décisionnelle), avec compteurs exacts.
"""

from __future__ import annotations

import pytest

from tiny_wae.core.scl import verdict
from tiny_wae.core.settings import Settings

_SETTINGS = Settings(
    stac_url="https://example.test/stac",
    stac_collection="sentinel-2-l2a",
    invalid_pct_max=1,
    cloud_pct_max=30,
)


def test_verdict_o2_100pct_classe0_rejected_invalid() -> None:
    """100 % classe 0 (no-data) -> rejected_invalid, invalid_pct=100.0 exact."""
    result = verdict({0: 1000}, _SETTINGS)
    assert result.status == "rejected_invalid"
    assert result.invalid_pct == 100.0
    assert result.cloud_pct == 0.0


def test_verdict_o2_40pct_classe8_rejected_clouds() -> None:
    """40 % classe 8 (nuage probabilité moyenne) -> rejected_clouds, cloud_pct=40.0 exact
    (40 > cloud_pct_max=30)."""
    counts = {8: 40, 6: 60}  # 6 = water, non décisionnelle
    result = verdict(counts, _SETTINGS)
    assert result.status == "rejected_clouds"
    assert result.invalid_pct == 0.0
    assert result.cloud_pct == 40.0


def test_verdict_o2_29pct_classes_3_8_ingested() -> None:
    """29 % classes {3,8} -> ingested (29 <= cloud_pct_max=30), cloud_pct=29.0 exact."""
    counts = {3: 15, 8: 14, 4: 71}  # 4 = vegetation, non décisionnelle
    result = verdict(counts, _SETTINGS)
    assert result.status == "ingested"
    assert result.invalid_pct == 0.0
    assert result.cloud_pct == 29.0


def test_verdict_o2_50pct_classe11_ingested_non_decisionnelle() -> None:
    """50 % classe 11 (neige/glace, non décisionnelle) -> ingested malgré la proportion,
    invalid_pct=0.0 et cloud_pct=0.0 exacts (11 n'entre dans aucun des deux comptes)."""
    counts = {11: 50, 4: 50}
    result = verdict(counts, _SETTINGS)
    assert result.status == "ingested"
    assert result.invalid_pct == 0.0
    assert result.cloud_pct == 0.0


def test_verdict_ordre_invalid_avant_cloud() -> None:
    """Un chip à la fois invalide ET nuageux est rejeté pour invalid_pct (ordre imposé par
    le chapeau : invalid_pct d'abord, puis cloud_pct)."""
    counts = {0: 50, 8: 50}  # 50 % invalide, 50 % nuageux
    result = verdict(counts, _SETTINGS)
    assert result.status == "rejected_invalid"


def test_verdict_seuils_stricts() -> None:
    """Seuils stricts (>) : exactement au seuil -> ingested, pas rejeté."""
    counts = {8: 30, 4: 70}  # cloud_pct == cloud_pct_max == 30, pas > 30
    result = verdict(counts, _SETTINGS)
    assert result.status == "ingested"
    assert result.cloud_pct == 30.0


def test_verdict_total_nul_leve_erreur() -> None:
    """Comptes vides (total nul) -> ValueError explicite, pas une division par zéro silencieuse."""
    with pytest.raises(ValueError):
        verdict({}, _SETTINGS)
