"""Tests scripts/smoke.py (l0-03.4) — oracle O7 : le smoke minimal du gate `just check`.

``scripts/`` n'est pas un package importable normalement (``mypy`` ne le couvre pas non
plus, ``pyproject.toml`` : ``files = ["src"]``) : ce test le charge par chemin
(``importlib.util.spec_from_file_location``, décision d'ancrage n°2 de la fiche).

Couvre :
- témoin POSITIF : ``run_smoke`` avec la source par défaut (1 item synthétique) réussit
  silencieusement (aucune ``AssertionError``), et les 3 fichiers + le manifeste existent.
- témoin NÉGATIF : un double du port qui ne rend RIEN (``with_item=False``) fait échouer
  ``run_smoke`` (``AssertionError``, ``assets_read`` resté à 0) — un smoke qui passerait
  vert sur une source vide serait un gate creux.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SMOKE_PATH = Path("scripts/smoke.py")


def _load_smoke_module() -> ModuleType:
    """Charge ``scripts/smoke.py`` comme un module, sans dépendre d'un package `scripts`."""
    spec = importlib.util.spec_from_file_location("smoke", SMOKE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["smoke"] = module
    spec.loader.exec_module(module)
    return module


smoke = _load_smoke_module()


def test_o7_temoin_positif_run_smoke_reussit(tmp_path: Path) -> None:
    """La source par défaut (1 item synthétique) fait passer `run_smoke` : 3 fichiers,
    manifeste `status == "ingested"`, `assets_read > 0`."""
    source = smoke.build_fake_source(tmp_path / "raw", with_item=True)
    smoke.run_smoke(tmp_path, source)  # ne lève rien -> vert

    item_dir = tmp_path / "data" / smoke.SITE_ID / smoke.ITEM_ID
    assert (item_dir / "chip.tif").exists()
    assert (item_dir / "chip_20m.tif").exists()
    assert (item_dir / "scl.tif").exists()


def test_o7_temoin_negatif_double_qui_ne_rend_rien_fait_echouer_le_smoke(tmp_path: Path) -> None:
    """Un double du port qui ne rend RIEN (0 item) fait échouer `run_smoke` : le gate
    doit être ROUGE, pas passer en silence sur une source vide."""
    empty_source = smoke.build_fake_source(tmp_path / "raw", with_item=False)
    with pytest.raises(AssertionError):
        smoke.run_smoke(tmp_path, empty_source)


def test_o7_main_exit_code_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """`main()` (le point d'entrée `just smoke`) sort en 0 sur le chemin heureux."""
    with pytest.raises(SystemExit) as exc_info:
        smoke.main()
    assert exc_info.value.code == 0
    assert "vert" in capsys.readouterr().out
