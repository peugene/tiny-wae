"""Tests core/windows.py (l0-03.1).

Couvre l'oracle de la fiche :
- O3 : update_window(now=2026-08-21, last=2026-08-15, margin=3) -> fenêtre
  [2026-08-12 -> 2026-08-21] (test déterministe, horloge injectée).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from tiny_wae.adapters.manifests import last_datetime as manifests_last_datetime
from tiny_wae.core.windows import (
    NoManifests,
    Window,
    backfill_windows,
    update_window,
    update_window_for_site,
)

FIXTURES_ROOT = Path("tests/fixtures/manifests")


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


# --- l0-05.1 : update_window_for_site ------------------------------------------------------


def test_update_window_for_site_o1_lit_le_corpus_fixtures() -> None:
    """O1 : la fenêtre est obtenue en lisant réellement les manifestes du corpus C07.

    Le manifeste le plus récent de C07 est ``S2A_C07_FAIL01`` (statut ``failed``,
    2026-01-25T10:15:00Z) — c'est cette date qui doit border la fenêtre, marge soustraite.
    """
    last = manifests_last_datetime(FIXTURES_ROOT, "C07")
    now = datetime(2026, 1, 28)
    window = update_window_for_site(last, margin_days=3, now=now)
    assert window == Window(start=datetime(2026, 1, 22, 10, 15), end=now)


def test_update_window_for_site_o2_site_sans_manifeste_rend_nomanifests() -> None:
    """O2 : site sans manifeste -> `NoManifests`, pas d'exception, pas de fenêtre par défaut."""
    last = manifests_last_datetime(FIXTURES_ROOT, "INCONNU")
    result = update_window_for_site(last, margin_days=3, now=datetime(2026, 8, 21))
    assert result == NoManifests()


def test_update_window_for_site_o3_rejected_clouds_plus_recent_que_ingested() -> None:
    """O3 : un manifeste `rejected_clouds` plus récent qu'un `ingested` est bien pris en
    compte dans `last_datetime` (C07 : les CLD0x, rejetés, dominent tous les ING0x)."""
    last = manifests_last_datetime(FIXTURES_ROOT, "C07")
    assert last == "2026-01-25T10:15:00Z"  # domine aussi les CLD0x (rejected_clouds)


def test_update_window_for_site_parse_le_suffixe_z() -> None:
    """Le suffixe `Z` (UTC) des dates ISO rendues par `manifests.last_datetime` est bien
    géré par `datetime.fromisoformat` (converti/retiré avant de rejoindre `update_window`)."""
    window = update_window_for_site(
        "2026-08-15T00:00:00Z", margin_days=3, now=datetime(2026, 8, 21)
    )
    assert window == Window(start=datetime(2026, 8, 12), end=datetime(2026, 8, 21))
