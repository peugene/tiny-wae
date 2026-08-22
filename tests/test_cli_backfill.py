"""Tests cli/backfill.py (l0-04.1) — wiring : options, codes de sortie, `build_source`
monkeypatché vers ``FixtureSource`` (aucun réseau). ``config/sites.yaml`` réel (A01/B09,
grilles déjà posées) ; ``config/settings.yaml`` recopié avec un ``data_root`` isolé sous
``tmp_path``.

Couvre :
- O1 : `backfill --sites A01 --months 1 --workers 4 --now <fenêtre du corpus>` -> exit OK,
  compteurs gelés sur STDERR (found_stac=6 ...).
- O2 : échec injecté sur B09 -> exit FAILURE, site fautif nommé sur STDERR, A01 complet.
- O2bis : amont injoignable sur les 2 sites demandés -> exit INCONCLUSIVE.
- usage : `--sites` avec un id inconnu -> exit USAGE, AVANT toute soumission au pool.
- `--workers` par défaut = `settings.backfill_workers` quand l'option est omise.

Couvre aussi obs-02 (accusé de réception + interruption immédiate au Ctrl+C) :
- O4 : `_on_stop_requested(False)` -> message des 3 informations de D2 sur STDERR
  uniquement, capturé au niveau DESCRIPTEUR (`capfd`, PAS `capsys` : le message passe
  par `os.write(2, ...)`, D5, hors du `sys.stderr` Python que `capsys` intercepte).
- D3/D4 (en process, `os._exit` monkeypatché — l'appeler pour de vrai tuerait le process
  de test) : `_on_stop_requested(True)` -> message des résidus possibles PUIS
  `os._exit(130)`.
- O5/O6/O7 : sous-processus RÉEL avec de VRAIS signaux (`skipif` win32, cf. la fiche —
  même raison que l'oracle O3 de l0-04.1 : l'envoi d'un signal n'est pas portable
  linux-64/win-64). Synchronisation par FIFO POSIX (rendez-vous `open()`, PAS de
  `time.sleep` — même principe que `_BlockingThenRealSource` de `tests/test_backfill.py`,
  transposé au sous-processus).
"""

from __future__ import annotations

import os
import queue
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
from typer.testing import CliRunner

import tiny_wae.cli.backfill as backfill_module
from tiny_wae.__main__ import app
from tiny_wae.adapters.backfill import _request_stop
from tiny_wae.adapters.config_io import DEFAULT_SITES_PATH
from tiny_wae.adapters.fixture_source import FixtureSource
from tiny_wae.adapters.manifests import list_for_site, read_manifest
from tiny_wae.adapters.stac import StacSource, StacUnreachable
from tiny_wae.cli import exit_codes
from tiny_wae.core.envelope import Envelope
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Site
from tiny_wae.core.windows import Window

runner = CliRunner()

# Date qui, via `backfill_windows(1, now)`, rend la fenêtre [2022-09-01, 2022-09-30[ —
# couvre exactement les 6 items de septembre 2022 du corpus A01 (ancrage de la fiche).
_NOW_SEPT_2022 = "2022-09-30"


def _write_settings(tmp_path: Path, *, data_root: Path) -> Path:
    """Recopie ``config/settings.yaml`` réel avec un ``data_root`` isolé sous tmp_path —
    mêmes chip_px_10m/20m que le corpus enregistré (l0-03.5), sans quoi les chips ne
    matcheraient pas la taille des fixtures COG."""
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        f"""
stac_url: "https://earth-search.aws.element84.com/v1"
stac_collection: "sentinel-2-l2a"
cloud_pct_max: 30
scene_cloud_max: 95
invalid_pct_max: 1
chip_nodata_pct_max: 1
data_root: "{data_root.as_posix()}"
incremental_margin_days: 3
http_retries: 1
http_backoff_s: 1
backfill_workers: 6
chip_px_10m: 512
chip_px_20m: 256
""",
        encoding="utf-8",
    )
    return settings_path


@dataclass(frozen=True, slots=True)
class _FailingSiteSource:
    """Double ``StacSource`` qui échoue TOUJOURS pour un site donné, délègue à une source
    réelle pour les autres — même double que ``tests/test_backfill.py``, dupliqué ici
    plutôt que partagé via un module utilitaire (fiche : 2 fichiers de test autorisés,
    aucun troisième)."""

    delegate: StacSource
    failing_site_id: str

    def search(self, site: Site, window: Window) -> Envelope:
        if site.id == self.failing_site_id:
            raise ValueError(f"panne injectée pour {site.id}")
        return self.delegate.search(site, window)


@dataclass(frozen=True, slots=True)
class _AlwaysUnreachableSource:
    """Double ``StacSource`` qui lève ``StacUnreachable`` pour TOUT site (O2bis)."""

    def search(self, site: Site, window: Window) -> Envelope:
        raise StacUnreachable(f"amont injoignable pour {site.id}")


def _patch_source(monkeypatch: pytest.MonkeyPatch, source: StacSource) -> None:
    monkeypatch.setattr(backfill_module, "build_source", lambda settings: source)


def test_backfill_a01_septembre_2022_exit_ok_compteurs_geles_o1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O1 : `--sites A01 --months 1 --workers 4 --now 2022-09-30` -> exit OK, compteurs
    GELÉS EN LITTÉRAL sur STDERR (found_stac=6, skipped_scene_cloud=0, off_tile=0,
    found_tile=6)."""
    data_root = tmp_path / "data"
    settings_path = _write_settings(tmp_path, data_root=data_root)
    settings = Settings(
        stac_url="https://earth-search.aws.element84.com/v1",
        stac_collection="sentinel-2-l2a",
        data_root=str(data_root),
    )
    _patch_source(monkeypatch, FixtureSource(settings=settings))

    result = runner.invoke(
        app,
        [
            "backfill",
            "--sites",
            "A01",
            "--months",
            "1",
            "--workers",
            "4",
            "--now",
            _NOW_SEPT_2022,
            "--sites-path",
            str(DEFAULT_SITES_PATH),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.OK, result.output
    assert "'found_stac': 6" in result.output
    assert "'skipped_scene_cloud': 0" in result.output
    assert "'off_tile': 0" in result.output
    assert "'found_tile': 6" in result.output
    assert len(list_for_site(data_root, "A01")) == 6


def test_backfill_echec_sur_1_site_exit_failure_site_nomme_o2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O2 : échec injecté sur B09 -> exit FAILURE (1), B09 nommé sur STDERR, A01 complet
    malgré l'échec."""
    data_root = tmp_path / "data"
    settings_path = _write_settings(tmp_path, data_root=data_root)
    settings = Settings(
        stac_url="https://earth-search.aws.element84.com/v1",
        stac_collection="sentinel-2-l2a",
        data_root=str(data_root),
    )
    source = _FailingSiteSource(delegate=FixtureSource(settings=settings), failing_site_id="B09")
    _patch_source(monkeypatch, source)

    result = runner.invoke(
        app,
        [
            "backfill",
            "--sites",
            "A01,B09",
            "--months",
            "1",
            "--workers",
            "4",
            "--now",
            _NOW_SEPT_2022,
            "--sites-path",
            str(DEFAULT_SITES_PATH),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.FAILURE, result.output
    assert "['B09']" in result.output
    assert len(list_for_site(data_root, "A01")) == 6


def test_backfill_amont_injoignable_partout_exit_inconclusive_o2bis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O2bis : amont injoignable sur les 2 sites demandés -> exit INCONCLUSIVE (3),
    distinct de O2."""
    data_root = tmp_path / "data"
    settings_path = _write_settings(tmp_path, data_root=data_root)
    _patch_source(monkeypatch, _AlwaysUnreachableSource())

    result = runner.invoke(
        app,
        [
            "backfill",
            "--sites",
            "A01,B09",
            "--months",
            "1",
            "--now",
            _NOW_SEPT_2022,
            "--sites-path",
            str(DEFAULT_SITES_PATH),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.INCONCLUSIVE, result.output


def test_backfill_site_inconnu_exit_usage_avant_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--sites` avec un id inconnu -> exit USAGE (2), AVANT toute soumission au pool
    (aucun manifeste écrit)."""
    data_root = tmp_path / "data"
    settings_path = _write_settings(tmp_path, data_root=data_root)

    called = {"count": 0}

    class _CountingSource:
        def search(self, site: Site, window: Window) -> Envelope:
            called["count"] += 1
            raise AssertionError("ne doit jamais être appelé : usage invalide en amont")

    _patch_source(monkeypatch, _CountingSource())

    result = runner.invoke(
        app,
        [
            "backfill",
            "--sites",
            "ZZZ99",
            "--months",
            "1",
            "--now",
            _NOW_SEPT_2022,
            "--sites-path",
            str(DEFAULT_SITES_PATH),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.USAGE, result.output
    assert called["count"] == 0
    assert not data_root.exists()


def test_backfill_workers_defaut_vient_des_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sans `--workers`, le CLI passe `settings.backfill_workers` (ici forcé à 2 dans le
    fichier écrit) à l'orchestrateur — vérifié en interceptant `run_backfill`."""
    data_root = tmp_path / "data"
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        f"""
stac_url: "https://earth-search.aws.element84.com/v1"
stac_collection: "sentinel-2-l2a"
data_root: "{data_root.as_posix()}"
backfill_workers: 2
""",
        encoding="utf-8",
    )
    settings = Settings(
        stac_url="https://earth-search.aws.element84.com/v1",
        stac_collection="sentinel-2-l2a",
        data_root=str(data_root),
    )
    _patch_source(monkeypatch, FixtureSource(settings=settings))

    seen_workers: dict[str, int] = {}
    # `run_backfill` est importé (pas ré-exporté explicitement) dans cli/backfill.py — un
    # attribut de module réel à l'exécution (le monkeypatch qui suit le prouve), mais que
    # `--no-implicit-reexport` (strict) refuse de considérer comme public depuis l'extérieur.
    # Modifier cli/backfill.py (ajouter un `__all__`) est hors périmètre de cette fiche
    # (out-01 ne touche pas src/) — ignore nommé plutôt que src/ changé au passage.
    real_run_backfill = backfill_module.run_backfill  # type: ignore[attr-defined]

    def _spy_run_backfill(**kwargs: object) -> object:
        seen_workers["workers"] = kwargs["workers"]  # type: ignore[assignment]
        return real_run_backfill(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(backfill_module, "run_backfill", _spy_run_backfill)

    result = runner.invoke(
        app,
        [
            "backfill",
            "--sites",
            "A01",
            "--months",
            "1",
            "--now",
            _NOW_SEPT_2022,
            "--sites-path",
            str(DEFAULT_SITES_PATH),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.OK, result.output
    assert seen_workers["workers"] == 2


# ── obs-02 O4 : accusé de réception (D2), STDERR uniquement ───────────────────────────


def test_on_stop_requested_premier_message_3_infos_stderr_seulement_o4(
    capfd: pytest.CaptureFixture[str],
) -> None:
    """O4 : le 1er Ctrl+C, câblé de BOUT EN BOUT comme en production
    (`_request_stop(..., on_stop_requested=_on_stop_requested)`, D1 — PAS un appel direct
    à `_on_stop_requested`, pour que la mutation O8 — qui neutralise l'appel à
    `on_stop_requested` DANS `_request_stop` — fasse RÉELLEMENT rougir ce test), écrit sur
    STDERR un message portant les 3 informations de D2 — la demande est prise en compte,
    les fenêtres en cours vont à leur terme (rien de nouveau n'est lancé), un second
    Ctrl+C interrompt immédiatement. RIEN sur STDOUT. Capturé au niveau DESCRIPTEUR
    (`capfd`) : le message passe par `os.write(2, ...)` (D5), hors du `sys.stderr` Python
    que `capsys` intercepterait — `capfd` seul le voit."""
    stop_event = threading.Event()

    _request_stop(stop_event, 0, None, on_stop_requested=backfill_module._on_stop_requested)

    captured = capfd.readouterr()
    assert captured.out == ""
    assert "Ctrl+C" in captured.err
    assert "fenêtres en cours" in captured.err and "leur terme" in captured.err
    assert "aucune nouvelle" in captured.err
    assert "second Ctrl+C" in captured.err and "immédiatement" in captured.err


def test_on_stop_requested_second_message_puis_os_exit_130_d3_d4(
    capfd: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """D3/D4 : le 2e appel (already_requested=True) écrit le message des résidus
    possibles (D4) PUIS appelle `os._exit(130)` (D3). `os._exit` est monkeypatché ICI —
    l'appeler pour de vrai tuerait le process de test sans passer par pytest. L'appel
    RÉEL, de bout en bout via un vrai sous-processus et un vrai signal, est prouvé par
    O5/O6 ci-dessous."""
    exit_calls: list[int] = []
    # `os` est un module singleton (`sys.modules`) : le patcher ICI (import direct de ce
    # fichier de test) affecte exactement le même objet que celui référencé par `import
    # os` dans `cli/backfill.py` — sans passer par `backfill_module.os`, que mypy strict
    # (`--no-implicit-reexport`) refuse de considérer public (même contournement que
    # `real_run_backfill` plus haut dans ce fichier).
    monkeypatch.setattr(os, "_exit", exit_calls.append)

    backfill_module._on_stop_requested(True)

    captured = capfd.readouterr()
    assert captured.out == ""
    assert "manifeste" in captured.err
    assert "prochain run" in captured.err
    assert exit_calls == [130]


# ── obs-02 O5/O6/O7 : sous-processus RÉEL, VRAI signal SIGINT ─────────────────────────

# Script exécuté DANS le sous-processus (`python -c <script> backfill ...`) : monkeypatche
# `build_source` comme `_patch_source` le fait en-process (même point de couture que le
# reste du fichier), mais ici depuis un process SÉPARÉ — un monkeypatch pytest ne
# traverserait pas la frontière de process. Le site `blocking_site_id` bloque sur un
# rendez-vous FIFO POSIX (`open()` bloque tant que l'autre bout n'est pas ouvert) AVANT de
# déléguer à `FixtureSource` : c'est le pendant, à travers deux process, de
# `_BlockingThenRealSource` (`tests/test_backfill.py`) — aucun `time.sleep`, un vrai
# rendez-vous. Le site normal (A01) délègue directement et termine vite : c'est ce qui
# donne un manifeste RÉEL à vérifier après coup (O7), pas une preuve vide.
_CHILD_SCRIPT = """
import os
from dataclasses import dataclass

import tiny_wae.cli.backfill as backfill_module
from tiny_wae.adapters.fixture_source import FixtureSource
from tiny_wae.adapters.stac import StacSource
from tiny_wae.core.envelope import Envelope
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Site
from tiny_wae.core.windows import Window

_FIFO_PATH = {fifo_path}
_BLOCKING_SITE_ID = {blocking_site_id}


@dataclass(frozen=True, slots=True)
class _PartlyBlockingSource:
    delegate: StacSource

    def search(self, site: Site, window: Window) -> Envelope:
        if site.id == _BLOCKING_SITE_ID:
            with open(_FIFO_PATH) as fifo:
                fifo.read(1)
        return self.delegate.search(site, window)


def _build_source(settings: Settings) -> StacSource:
    return _PartlyBlockingSource(delegate=FixtureSource(settings=settings))


backfill_module.build_source = _build_source

from tiny_wae.__main__ import app

app()
"""


def _read_line_until(lines: queue.Queue[str], needle: str, *, timeout: float) -> str:
    """Consomme des lignes de `lines` (alimentée par un thread de drainage) jusqu'à en
    trouver une contenant `needle`, ou lève au bout de `timeout` secondes. Bloquant sur
    `queue.Queue.get(timeout=...)` — pas un `time.sleep` de sondage."""
    deadline = time.monotonic() + timeout
    seen: list[str] = []
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(
                f"aucune ligne contenant {needle!r} sous {timeout}s (lignes vues : {seen!r})"
            )
        try:
            line = lines.get(timeout=remaining)
        except queue.Empty:
            raise AssertionError(
                f"aucune ligne contenant {needle!r} sous {timeout}s (lignes vues : {seen!r})"
            ) from None
        seen.append(line)
        if needle in line:
            return line


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="O5/O6 : envoi d'un vrai SIGINT à un sous-processus, non portable win32 "
    "(même raison que l'oracle O3 de l0-04.1, qui teste le handler par appel direct).",
)
def test_backfill_sous_processus_sigint_accuse_puis_arret_immediat_o5_o6_o7(
    tmp_path: Path,
) -> None:
    """O5 : sous-processus réel, 1er SIGINT envoyé -> le message d'accusé de réception
    (O4) apparaît sur le FLUX STDERR AVANT que le process ne se termine (mesuré en direct :
    B09 reste bloqué sur son rendez-vous FIFO, jamais libéré -> le process NE PEUT PAS
    s'être terminé naturellement à cet instant).

    O6 : 2e SIGINT envoyé sur ce même process encore bloqué -> sortie IMMÉDIATE, code 130.
    Si `os._exit` ne fonctionnait pas, ce `proc.wait(timeout=...)` timeout-erait : B09 ne
    peut jamais finir tout seul (son rendez-vous n'est jamais libéré) — la preuve que
    l'arrêt est immédiat, pas une fin naturelle, est donc structurelle, pas temporelle.

    O7 : après coup, le manifeste écrit par A01 (complété normalement pendant que B09
    bloquait) reste intégralement relisible ; aucun résidu `.tmp` pour B09 (qui n'a jamais
    atteint l'écriture)."""
    data_root = tmp_path / "data"
    settings_path = _write_settings(tmp_path, data_root=data_root)
    fifo_path = tmp_path / "release.fifo"
    os.mkfifo(fifo_path)

    script = _CHILD_SCRIPT.format(fifo_path=repr(str(fifo_path)), blocking_site_id=repr("B09"))

    proc = subprocess.Popen(  # noqa: S603 — args entièrement littéraux/construits ici, aucune entrée externe.
        [
            sys.executable,
            "-c",
            script,
            "backfill",
            "--sites",
            "A01,B09",
            "--months",
            "1",
            "--workers",
            "2",
            "--now",
            _NOW_SEPT_2022,
            "--sites-path",
            str(DEFAULT_SITES_PATH),
            "--settings-path",
            str(settings_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

    stderr_lines: queue.Queue[str] = queue.Queue()

    def _drain_stderr() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_lines.put(line)

    drain_thread = threading.Thread(target=_drain_stderr, daemon=True)
    drain_thread.start()

    writer = None
    try:
        # Rendez-vous FIFO : bloque jusqu'à ce que B09 ait RÉELLEMENT atteint son
        # `open(_FIFO_PATH)` côté lecture — pas un délai fixe, un vrai rendez-vous POSIX.
        # Reste ouvert à dessein (garde B09 bloqué) — fermé au `finally` ci-dessous.
        writer = fifo_path.open("w")

        assert proc.poll() is None, "le sous-processus s'est terminé avant le rendez-vous"

        # Attend la ligne de progression PROPRE à A01 avant d'envoyer le moindre signal :
        # sans ça, A01 (qui tourne EN PARALLÈLE de B09, sur son propre thread du pool)
        # pourrait encore être en vol au moment du 2e Ctrl+C — la course serait alors
        # entre "A01 finit d'écrire son manifeste" et "os._exit(130) coupe le process",
        # ce qui rendrait O7 non déterministe (potentiellement 0 manifeste, ce que D4
        # documente comme un résultat POSSIBLE, mais qui ne prouverait alors rien sur la
        # relisibilité d'un manifeste RÉELLEMENT écrit). Cette ligne ne peut apparaître
        # qu'une fois `ingest_from_source` revenu, donc le manifeste déjà sur disque.
        a01_progress_line = _read_line_until(stderr_lines, "A01", timeout=15)
        assert "found_stac" in a01_progress_line, (
            f"ligne inattendue (pas la progression d'A01) : {a01_progress_line!r}"
        )

        proc.send_signal(signal.SIGINT)  # 1er Ctrl+C

        first_message = _read_line_until(stderr_lines, "interruption demandée", timeout=10)
        # O5 : le process est ENCORE VIVANT au moment où le message est observé — B09
        # reste bloqué sur le FIFO (jamais libéré), il ne peut pas s'être terminé seul.
        assert proc.poll() is None, "le process ne doit PAS se terminer sur le 1er Ctrl+C"
        assert "Ctrl+C" in first_message
        assert "fenêtres en cours" in first_message
        assert "aucune nouvelle" in first_message
        assert "second Ctrl+C" in first_message and "immédiatement" in first_message

        proc.send_signal(signal.SIGINT)  # 2e Ctrl+C -> arrêt immédiat attendu (D3)

        second_message = _read_line_until(stderr_lines, "arrêt immédiat", timeout=10)
        assert "manifeste" in second_message

        returncode = proc.wait(timeout=10)
        assert returncode == 130, "O6 : code de sortie attendu 130 (128 + SIGINT)"
    finally:
        if writer is not None:
            writer.close()
        if proc.poll() is None:  # pragma: no cover — filet de sécurité si l'assertion échoue avant.
            proc.kill()
            proc.wait(timeout=5)
        drain_thread.join(timeout=5)

    # O7 : état du data_root après l'arrêt brutal — A01 a eu le temps de finir (pas
    # bloqué) pendant que B09 restait coincé sur le rendez-vous : ses manifestes doivent
    # être intégralement relisibles, et B09 (jamais arrivé à l'écriture) n'en laisse aucun.
    a01_manifests = list_for_site(data_root, "A01")
    assert a01_manifests, "A01 aurait dû compléter sa fenêtre pendant que B09 bloquait"
    for manifest in a01_manifests:
        reread = read_manifest(data_root, "A01", manifest.item_id)
        assert reread.item_id == manifest.item_id
    assert list_for_site(data_root, "B09") == []
