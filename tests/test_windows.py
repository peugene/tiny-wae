"""Tests core/windows.py (l0-03.1).

Couvre l'oracle de la fiche :
- O3 : update_window(now=2026-08-21, last=2026-08-15, margin=3) -> fenêtre
  [2026-08-12 -> 2026-08-21] (test déterministe, horloge injectée).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from tiny_wae.core.windows import Window, backfill_windows, update_window


def test_update_window_o3_deterministe() -> None:
    """O3 : now/last/margin littéraux -> fenêtre [2026-08-12, 2026-08-21] exacte."""
    now = datetime(2026, 8, 21)
    last = datetime(2026, 8, 15)
    window = update_window(last, margin_days=3, now=now)
    assert window == Window(start=datetime(2026, 8, 12), end=datetime(2026, 8, 21))


def test_backfill_windows_ordre_plus_ancienne_dabord() -> None:
    """La fenêtre du mois le plus ancien vient en premier dans la liste (contrat l0-04.1)."""
    now = datetime(2026, 8, 21)
    windows = backfill_windows(3, now)
    assert len(windows) == 3
    assert windows[0].start < windows[1].start < windows[2].start
    assert windows[0].start == datetime(2026, 6, 1)
    assert windows[1].start == datetime(2026, 7, 1)
    assert windows[2].start == datetime(2026, 8, 1)


def test_backfill_windows_derniere_fenetre_bornee_par_now() -> None:
    """La fenêtre du mois courant s'arrête à `now`, pas à la fin du mois calendaire (pas
    de recherche dans le futur)."""
    now = datetime(2026, 8, 21)
    windows = backfill_windows(1, now)
    assert windows == [Window(start=datetime(2026, 8, 1), end=now)]


def test_backfill_windows_traverse_annee() -> None:
    """Le découpage mensuel gère correctement le report d'année (décembre -> janvier)."""
    now = datetime(2026, 1, 15)
    windows = backfill_windows(2, now)
    assert windows[0].start == datetime(2025, 12, 1)
    assert windows[0].end == datetime(2026, 1, 1)
    assert windows[1].start == datetime(2026, 1, 1)
    assert windows[1].end == now


def test_backfill_windows_months_invalide() -> None:
    """months <= 0 -> ValueError explicite."""
    with pytest.raises(ValueError):
        backfill_windows(0, datetime(2026, 8, 21))
