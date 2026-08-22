"""Tests scripts/smoke.py (l0-03.7) — le gate permanent : smoke replay/live + garde de
contrat.

``scripts/`` n'est pas un package importable normalement (``mypy`` ne le couvre pas non
plus, ``pyproject.toml`` : ``files = ["src"]``) : ce test le charge par chemin
(``importlib.util.spec_from_file_location``, comme posé par l0-03.4).

Couvre les oracles de la fiche (hors O5, ``--live``, hors gate — non exercé sous pytest,
zéro réseau) :

- O1/O4 : ``check_o1_o4_ingest_ok`` réussit deux fois de suite sur un ``data_root`` vierge
  à chaque fois (répétabilité), ``content_hashes`` identiques aux deux runs.
- O2 : un asset dont le href ``file://`` pointe vers un chemin absent fait échouer l'item
  (``status == "failed"``), et le chemin manquant est nommé littéralement dans
  ``manifest.cause``.
- O3/O3bis : la garde de contrat (``chips._guard_href``) lève ``RemoteAccessForbidden``
  sous ``TINY_WAE_OFFLINE=1`` pour un href ``https://``, et NE lève rien quand la
  variable est absente.
- ``main()`` (mode ``--replay``, celui câblé dans ``just smoke``) sort en 0.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import Iterator
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


@pytest.fixture(autouse=True)
def _restore_offline_env() -> Iterator[None]:
    """Garde-fou de test : quel que soit ce que le module fait, l'environnement du process
    pytest ne doit jamais garder ``TINY_WAE_OFFLINE`` en sortie d'un test (décision
    d'ancrage n°5 de la fiche : la variable ne doit jamais fuir)."""
    previous = os.environ.get(smoke.OFFLINE_ENV_VAR)
    yield
    if previous is None:
        os.environ.pop(smoke.OFFLINE_ENV_VAR, None)
    else:
        os.environ[smoke.OFFLINE_ENV_VAR] = previous


def test_o1_o4_ingest_ok_est_repetable(tmp_path: Path) -> None:
    """O1 + O4 : deux runs sur deux `data_root` vierges rendent le MÊME `content_hashes`,
    tous deux avec `assets_read > 0` — témoin positif ET répétabilité."""
    previous = smoke._set_offline(True)
    try:
        smoke.check_o1_o4_ingest_ok(tmp_path / "run1", run_label="test run 1")
        smoke.check_o1_o4_ingest_ok(tmp_path / "run2", run_label="test run 2")

        manifest1 = smoke.read_manifest(tmp_path / "run1" / "data", smoke.SITE_ID, smoke.ITEM_ID)
        manifest2 = smoke.read_manifest(tmp_path / "run2" / "data", smoke.SITE_ID, smoke.ITEM_ID)
        assert manifest1.content_hashes == manifest2.content_hashes
        assert manifest1.assets_read > 0
        assert manifest2.assets_read > 0
    finally:
        smoke._restore_offline(previous)


def test_o2_fixture_locale_manquante_nomme_le_chemin(tmp_path: Path) -> None:
    """O2 : le chemin du fichier manquant est nommé littéralement dans `manifest.cause` —
    ni un mot vague, ni une classe d'exception : le chemin exact."""
    previous = smoke._set_offline(True)
    try:
        smoke.check_o2_missing_local_fixture(tmp_path)  # ne lève rien -> le mécanisme marche
    finally:
        smoke._restore_offline(previous)


def test_o3_garde_de_contrat_sur_le_pipeline_complet(tmp_path: Path) -> None:
    """O3 : sous `TINY_WAE_OFFLINE=1`, un href `https://` fait échouer l'INGESTION RÉELLE.

    Le contrôle passe par `ingest_from_source`, pas par un appel direct à la garde : ce que
    l'oracle protège, c'est que le pipeline la DÉCLENCHE. Un test qui appellerait
    `chips._guard_href` isolément resterait vert si l'appel disparaissait de `read_scl` —
    exactement le faux-vert que cette fiche existe pour empêcher.
    """
    previous = smoke._set_offline(True)
    try:
        smoke.check_o3_contract_guard_end_to_end(tmp_path)  # ne lève rien -> le mécanisme marche
    finally:
        smoke._restore_offline(previous)


def test_o3bis_garde_non_permanente() -> None:
    """O3bis : sans `TINY_WAE_OFFLINE`, la garde ne bloque pas — seul cas où l'on appelle la
    garde directement, vérifier « l'ouverture est tentée » exigerait un vrai réseau."""
    smoke.check_o3bis_guard_not_permanent()


def test_main_replay_exit_code_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """`main()` (mode `--replay`, celui câblé dans `just smoke`) sort en 0 sur le chemin
    heureux, et n'a PAS laissé fuir `TINY_WAE_OFFLINE` dans l'environnement du process."""
    with pytest.raises(SystemExit) as exc_info:
        smoke.main()
    assert exc_info.value.code == 0
    assert "vert" in capsys.readouterr().out
    assert smoke.OFFLINE_ENV_VAR not in os.environ
