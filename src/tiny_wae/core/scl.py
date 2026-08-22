"""core/scl.py — verdict d'ingestion à partir des comptes de classes SCL, pur (zéro I/O).

Le verdict décide si un item est ingéré ou rejeté, en fonction de la proportion de pixels
« invalides » (classes {0, 1} — no-data, saturé/défectueux) et « nuageux » (classes
{3, 8, 9, 10} — ombre de nuage, probabilité moyenne/haute, cirrus). Les classes 2 (ombre de
terrain sombre) et 11 (neige/glace) sont comptées dans le résultat mais ne pèsent pas dans
la décision — décision différée, documentée par le chapeau l0-03.

Ordre imposé par le chapeau : ``invalid_pct`` d'abord, puis ``cloud_pct``, seuils
**stricts** (``>``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from tiny_wae.core.settings import Settings

# Classes SCL (Sentinel-2 Scene Classification Layer) impliquées dans le verdict.
_INVALID_CLASSES = (0, 1)
_CLOUD_CLASSES = (3, 8, 9, 10)

VerdictStatus = Literal["ingested", "rejected_invalid", "rejected_clouds"]


@dataclass(frozen=True, slots=True)
class Verdict:
    """Résultat du calcul de verdict : statut + les deux pourcentages qui l'ont produit."""

    status: VerdictStatus
    invalid_pct: float
    cloud_pct: float


def verdict(scl_class_counts: dict[int, int], settings: Settings) -> Verdict:
    """Calcule le verdict d'ingestion à partir des comptes de classes SCL.

    ``scl_class_counts`` : mapping classe SCL (int) -> nombre de pixels. Le total (dénominateur
    des pourcentages) est la somme de toutes les classes présentes, y compris 2 et 11 — un chip
    est un rectangle plein, chaque pixel appartient forcément à une classe.
    Seuils lus sur ``settings`` (``invalid_pct_max``, ``cloud_pct_max``) — jamais en dur.
    """
    total = sum(scl_class_counts.values())
    if total == 0:
        raise ValueError("scl_class_counts : somme nulle, impossible de calculer un pourcentage")

    invalid_count = sum(scl_class_counts.get(cls, 0) for cls in _INVALID_CLASSES)
    cloud_count = sum(scl_class_counts.get(cls, 0) for cls in _CLOUD_CLASSES)
    invalid_pct = 100.0 * invalid_count / total
    cloud_pct = 100.0 * cloud_count / total

    # Ordre imposé par le chapeau : invalid_pct d'abord, puis cloud_pct, seuils stricts.
    if invalid_pct > settings.invalid_pct_max:
        status: VerdictStatus = "rejected_invalid"
    elif cloud_pct > settings.cloud_pct_max:
        status = "rejected_clouds"
    else:
        status = "ingested"

    return Verdict(status=status, invalid_pct=invalid_pct, cloud_pct=cloud_pct)
