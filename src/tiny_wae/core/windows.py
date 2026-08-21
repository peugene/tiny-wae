"""core/windows.py — fenêtres temporelles d'ingestion, pur (zéro I/O).

Fournisseur unique des fenêtres consommées par l0-04 (backfill) et l0-05 (incrémental).
``now`` est toujours passé en paramètre (horloge injectable, décision D-a) : aucune
fonction de ce module n'appelle ``datetime.now()`` elle-même — c'est ce qui rend le smoke
déterministe.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class Window:
    """Fenêtre temporelle demi-ouverte [start, end[ utilisée pour une recherche STAC.

    Type réutilisé tel quel par l0-05.1 (``update_window`` en particulier, signature figée
    ici et consommée en aval — ne pas la changer).
    """

    start: datetime
    end: datetime


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    """Ajoute ``delta`` mois à (year, month), avec report d'année correct."""
    total = year * 12 + (month - 1) + delta
    return total // 12, total % 12 + 1


def backfill_windows(months: int, now: datetime) -> list[Window]:
    """Découpe les ``months`` derniers mois calendaires en fenêtres mensuelles.

    Renvoie une **liste** de fenêtres, la plus ancienne d'abord — l0-04.1 écrit un
    ``run.json`` par (site, fenêtre) et passe ``--months N`` : une fenêtre unique casserait
    ce contrat aval. La dernière fenêtre (mois courant) est bornée par ``now``, pas par la
    fin du mois calendaire (on ne cherche pas dans le futur).
    """
    if months <= 0:
        raise ValueError(f"months={months} doit être > 0")

    windows: list[Window] = []
    for offset in range(months - 1, -1, -1):
        year, month = _add_months(now.year, now.month, -offset)
        start = datetime(year, month, 1)
        next_year, next_month = _add_months(year, month, 1)
        month_end = datetime(next_year, next_month, 1)
        end = now if offset == 0 else month_end
        windows.append(Window(start=start, end=end))
    return windows


def update_window(last_datetime: datetime, margin_days: int, now: datetime) -> Window:
    """Fenêtre incrémentale : de ``last_datetime`` reculé de ``margin_days``, jusqu'à ``now``.

    La marge couvre les items apparus tardivement dans le catalogue STAC pour une date déjà
    couverte par un run précédent. Réutilisée telle quelle par l0-05.1 (``-> Window |
    NoManifests`` côté appelant) : signature figée, ne pas la changer.
    """
    start = last_datetime - timedelta(days=margin_days)
    return Window(start=start, end=now)
