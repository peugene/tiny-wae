"""Tests du système de logging + progression du backfill (obs-01).

Couvre l'oracle O1 à O11bis de la fiche (O12 est la non-régression globale, couverte par
``just check`` ; O10 est une mutation MANUELLE — cf. le compte-rendu de dispatch, pas un
test permanent ici). Tout se joue sur ``FixtureSource`` (aucun réseau) pour O1-O6, comme
``tests/test_cli_backfill.py`` — sauf O7 (volume/concurrence), qui a besoin des 25 sites
réels mais d'AUCUN de leurs corpus enregistrés (seuls A01/B09 en ont un) : un double
``StacSource`` rapide (``_InstantEmptySource``) y sert des enveloppes vides mais valides.

⛔ Les logs vont sur STDERR (D2) : `CliRunner` (click 8.4.2 / typer 0.27.1) sépare bien
`result.stdout` de `result.stderr` — vérifié à l'ancrage de la fiche, ré-exploité ici.
"""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from re import Match

import pytest
from typer.testing import CliRunner

import tiny_wae.cli.backfill as backfill_module
from tiny_wae.__main__ import app
from tiny_wae.adapters.backfill import _eta_seconds, _eta_uncertain, _format_eta
from tiny_wae.adapters.config_io import DEFAULT_SITES_PATH
from tiny_wae.adapters.fixture_source import FixtureSource
from tiny_wae.adapters.stac import StacSource
from tiny_wae.cli import exit_codes
from tiny_wae.core.envelope import Envelope
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Site
from tiny_wae.core.windows import Window

runner = CliRunner()

_NOW_SEPT_2022 = "2022-09-30"

# Motif figé (fiche, « Format de ligne (figé) ») d'une ligne de PROGRESSION (pas la ligne
# d'ouverture, qui ne porte pas de `n/total`) : horodatage, niveau, `n/total (pct%) ETA
# ...`, id du site, bornes de fenêtre `start→end`, charge utile variable (compteurs non
# nuls, ou `ÉCHEC : ...`, éventuellement vide).
_PROGRESS_LINE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} (?P<level>INFO|WARNING)\s+"
    r"backfill  (?P<n>\d+)/(?P<total>\d+) \(\s*\d+\.\d%\) "
    r"ETA (?P<eta>—|\d+h\d{2}\??|\d+min\d{2}\??)  "
    r"(?P<site>[A-Za-z0-9]+)  "
    r"(?P<start>\d{4}-\d{2}-\d{2})→(?P<end>\d{4}-\d{2}-\d{2})  "
    r"(?P<payload>.*)$"
)


def _progress_lines(stderr: str) -> list[Match[str]]:
    """Lignes de STDERR qui matchent le motif figé d'une ligne de progression."""
    matches = []
    for line in stderr.splitlines():
        match = _PROGRESS_LINE_RE.match(line)
        if match:
            matches.append(match)
    return matches


def _write_settings(tmp_path: Path, *, data_root: Path) -> Path:
    """Recopie ``config/settings.yaml`` réel avec un ``data_root`` isolé — même patron que
    ``tests/test_cli_backfill.py::_write_settings`` (duplication assumée, 2 fichiers de
    test, aucun 3e module utilitaire pour ça)."""
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        f"""
stac_url: "https://earth-search.aws.element84.com/v1"
stac_collection: "sentinel-2-l2a"
data_root: "{data_root.as_posix()}"
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
    réelle pour les autres — même double que ``tests/test_cli_backfill.py``."""

    delegate: StacSource
    failing_site_id: str

    def search(self, site: Site, window: Window) -> Envelope:
        if site.id == self.failing_site_id:
            raise ValueError(f"panne injectée pour {site.id}")
        return self.delegate.search(site, window)


@dataclass(frozen=True, slots=True)
class _InstantEmptySource:
    """Double ``StacSource`` sans AUCUNE E/S (ni réseau, ni fixture COG) : rend une
    enveloppe vide mais valide (conservation triviale : 4 compteurs à 0, 0 item) pour
    N'IMPORTE QUEL site. Utilisé UNIQUEMENT par O7 (volume/concurrence, 25 sites réels —
    seuls A01/B09 ont un corpus ``FixtureSource`` enregistré) : le contenu des fenêtres y
    est hors-sujet, seule la mécanique de progression compte."""

    def search(self, site: Site, window: Window) -> Envelope:
        return Envelope(
            schema_version=1,
            site_id=site.id,
            window={"start": window.start.isoformat(), "end": window.end.isoformat()},
            counters={
                "found_stac": 0,
                "skipped_scene_cloud": 0,
                "off_tile": 0,
                "found_tile": 0,
            },
            items=[],
        )


def _patch_source(monkeypatch: pytest.MonkeyPatch, source: StacSource) -> None:
    monkeypatch.setattr(backfill_module, "build_source", lambda settings: source)


# ── O1 + O2 : une ligne par fenêtre, n forme une permutation de 1..total ─────────────


def test_o1_o2_une_ligne_par_fenetre_permutation_1_a_total(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O1 : chaque ligne de progression porte `n/total`, un `%`, l'id du site et les deux
    bornes de la fenêtre. O2 : les `n` de TOUTES les lignes forment exactement une
    permutation de `1..total` (aucun doublon, aucun trou) ; le `total` annoncé partout ==
    le nombre de fenêtres réellement soumises (2 sites × 6 mois = 12)."""
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
            "A01,B09",
            "--months",
            "6",
            "--workers",
            "2",
            "--now",
            _NOW_SEPT_2022,
            "--sites-path",
            str(DEFAULT_SITES_PATH),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.OK, result.stderr
    matches = _progress_lines(result.stderr)
    assert len(matches) == 12  # O1 : une ligne PAR fenêtre traitée (2 sites x 6 fenêtres).

    for match in matches:
        assert match.group("total") == "12"
        assert match.group("site") in ("A01", "B09")
        assert match.group("start") < match.group("end")

    ns = sorted(int(match.group("n")) for match in matches)
    assert ns == list(range(1, 13))  # O2 : permutation exacte de 1..12, sans doublon/trou.


# ── O3 : STDOUT ne porte jamais le log ───────────────────────────────────────────────


def test_o3_stdout_vide(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """O3 : sur le même run qu'O1/O2, `result.stdout == ""` — le log ne touche jamais le
    canal de données (D2)."""
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

    assert result.exit_code == exit_codes.OK, result.stderr
    assert result.stdout == ""
    assert len(_progress_lines(result.stderr)) >= 1


# ── O4 : une fenêtre en échec loggue en WARNING, le run continue ────────────────────


def test_o4_echec_logue_en_warning_le_run_continue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O4 : source qui lève sur B09 -> >= 1 ligne WARNING nommant le site, la fenêtre et
    le message d'erreur ; A01 continue d'être traité (ligne INFO présente)."""
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
            "--now",
            _NOW_SEPT_2022,
            "--sites-path",
            str(DEFAULT_SITES_PATH),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.FAILURE, result.stderr
    matches = _progress_lines(result.stderr)
    warning_matches = [m for m in matches if m.group("level") == "WARNING"]
    info_matches = [m for m in matches if m.group("level") == "INFO"]

    assert len(warning_matches) == 1
    assert warning_matches[0].group("site") == "B09"
    assert "panne injectée pour B09" in warning_matches[0].group("payload")
    assert warning_matches[0].group("payload").startswith("ÉCHEC :")

    assert len(info_matches) == 1  # A01 : le run continue malgré l'échec de B09.
    assert info_matches[0].group("site") == "A01"


# ── O5 : --log-level WARNING supprime la progression, garde les échecs ─────────────


def test_o5_log_level_warning_supprime_progression_garde_echecs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O5 : `--log-level WARNING` sur un run avec un échec -> 0 ligne de progression
    (INFO), la ligne d'échec (WARNING) subsiste."""
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
            "--log-level",
            "WARNING",
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

    assert result.exit_code == exit_codes.FAILURE, result.stderr
    matches = _progress_lines(result.stderr)
    info_matches = [m for m in matches if m.group("level") == "INFO"]
    warning_matches = [m for m in matches if m.group("level") == "WARNING"]

    assert info_matches == []  # 0 ligne de progression (opening line incluse : elle est INFO).
    assert "ouverture" not in result.stderr
    assert len(warning_matches) == 1
    assert warning_matches[0].group("site") == "B09"


# ── O6 : TINY_WAE_LOG_LEVEL, précédence de --log-level ──────────────────────────────


def test_o6_env_var_precedence_cli_gagne(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """O6 : `TINY_WAE_LOG_LEVEL=WARNING` seul -> même résultat qu'O5 (0 ligne INFO).
    Les DEUX ensemble (env WARNING + `--log-level INFO`) -> l'option de ligne de commande
    GAGNE (les lignes INFO réapparaissent)."""
    data_root = tmp_path / "data"
    settings_path = _write_settings(tmp_path, data_root=data_root)
    settings = Settings(
        stac_url="https://earth-search.aws.element84.com/v1",
        stac_collection="sentinel-2-l2a",
        data_root=str(data_root),
    )
    source = _FailingSiteSource(delegate=FixtureSource(settings=settings), failing_site_id="B09")
    _patch_source(monkeypatch, source)
    base_args = [
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
    ]

    monkeypatch.setenv("TINY_WAE_LOG_LEVEL", "WARNING")
    result_env_only = runner.invoke(app, base_args)
    assert result_env_only.exit_code == exit_codes.FAILURE, result_env_only.stderr
    info_env_only = [
        m for m in _progress_lines(result_env_only.stderr) if m.group("level") == "INFO"
    ]
    assert info_env_only == []

    result_both = runner.invoke(app, ["--log-level", "INFO", *base_args])
    assert result_both.exit_code == exit_codes.FAILURE, result_both.stderr
    info_both = [m for m in _progress_lines(result_both.stderr) if m.group("level") == "INFO"]
    assert len(info_both) == 1  # --log-level (CLI) gagne sur TINY_WAE_LOG_LEVEL (env).
    assert info_both[0].group("site") == "A01"


# ── O7 : concurrence, 25 sites réels, workers=6, >= 50 fenêtres, 100 % bien formées ──


def test_o7_concurrence_workers_6_lignes_bien_formees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O7 : `--sites all --months 3 --workers 6` (25 sites x 3 = 75 fenêtres >= 50) ->
    100 % des lignes de progression sont bien formées (aucune ligne entrelacée, tronquée
    ou fusionnée) — `logging` sérialise l'écriture malgré 6 threads concurrents."""
    data_root = tmp_path / "data"
    settings_path = _write_settings(tmp_path, data_root=data_root)
    _patch_source(monkeypatch, _InstantEmptySource())

    result = runner.invoke(
        app,
        [
            "backfill",
            "--sites",
            "all",
            "--months",
            "3",
            "--workers",
            "6",
            "--now",
            _NOW_SEPT_2022,
            "--sites-path",
            str(DEFAULT_SITES_PATH),
            "--settings-path",
            str(settings_path),
        ],
    )

    assert result.exit_code == exit_codes.OK, result.stderr
    lines = result.stderr.splitlines()
    eta_lines = [line for line in lines if " ETA " in line]
    malformed = [line for line in eta_lines if not _PROGRESS_LINE_RE.match(line)]
    assert malformed == []  # 0 ligne mal formée (entrelacée/tronquée/fusionnée).

    matches = _progress_lines(result.stderr)
    assert len(matches) == 75  # 25 sites x 3 fenêtres, dénominateur réel (>= 50 requis).
    assert all(match.group("total") == "75" for match in matches)
    ns = sorted(int(match.group("n")) for match in matches)
    assert ns == list(range(1, 76))  # 100 % des n, sans doublon ni trou.


# ── O8 : _eta_seconds, valeurs exactes par appel direct ────────────────────────────


def test_o8_eta_seconds_valeurs_exactes() -> None:
    """O8 : `_eta_seconds(10, 100, 30.0)` == 270.0 EXACTEMENT ; `(0, ...)` -> None (aucune
    division par zéro) ; `(total, total, ...)` -> 0.0 (aucun négatif)."""
    assert _eta_seconds(10, 100, 30.0) == 270.0
    assert _eta_seconds(0, 100, 30.0) is None
    assert _eta_seconds(100, 100, 30.0) == 0.0


# ── O9 : rendu de l'ETA — tiret / incertain / certain ───────────────────────────────


def test_o9_eta_tiret_avant_la_premiere_fenetre() -> None:
    """O9 (moment 1) : avant la 1re fenêtre terminée (`done=0`), l'ETA vaut `—`, quelle
    que soit la valeur d'`uncertain` — `eta_seconds` est `None` (D11/D12)."""
    eta = _eta_seconds(0, 1200, 0.0)
    assert eta is None
    assert _format_eta(eta, done=0, total=1200, uncertain=True) == "—"
    assert _format_eta(eta, done=0, total=1200, uncertain=False) == "—"


def test_o9_eta_tiret_sur_la_derniere_ligne() -> None:
    """Non-régression D11 (couvert par le même mécanisme qu'O9) : sur la DERNIÈRE ligne
    (`done == total`), l'ETA vaut aussi `—` — un `0min00` littéral serait du bruit."""
    eta = _eta_seconds(1200, 1200, 999.0)
    assert eta == 0.0
    assert _format_eta(eta, done=1200, total=1200, uncertain=False) == "—"


def test_o9_eta_incertaine_moments_2_et_3() -> None:
    """O9 (moments 2 et 3) : le `?` disparaît EXACTEMENT quand la condition D11 change,
    testé par appel direct sur `_eta_uncertain`/`_format_eta` — c'est l'INTERPRÉTATION
    EXACTE de D11 (2 conditions : échantillon < 5 %, OU phase de queue = moins de
    `workers` sites encore actifs, i.e. n'ayant pas encore produit TOUTES leurs
    fenêtres) qui sert d'oracle, plutôt qu'une simulation de pool réelle (non
    déterministe dans son entrelacement, donc impropre à un test exact — cf. compte-rendu
    de dispatch de la fiche pour le détail de ce choix).

    - Moment 2 ("sites partiellement démarrés") : échantillon confortable (900/1200 =
      75 % > 5 %) MAIS phase de queue active (4 sites encore actifs < 6 workers) -> `?`.
    - Moment 3 ("25 sites démarrés") : même échantillon, mais 25 sites encore actifs
      (>= 6 workers, plus de phase de queue) -> `?` disparaît."""
    total, workers, done, elapsed = 1200, 6, 900, 5000.0
    eta = _eta_seconds(done, total, elapsed)
    assert eta is not None

    uncertain_queue_phase = _eta_uncertain(done=done, total=total, sites_active=4, workers=workers)
    assert uncertain_queue_phase is True
    rendered_2 = _format_eta(eta, done=done, total=total, uncertain=uncertain_queue_phase)
    assert rendered_2 != "—"
    assert rendered_2.endswith("?")

    uncertain_healthy = _eta_uncertain(done=done, total=total, sites_active=25, workers=workers)
    assert uncertain_healthy is False
    rendered_3 = _format_eta(eta, done=done, total=total, uncertain=uncertain_healthy)
    assert rendered_3 != "—"
    assert not rendered_3.endswith("?")


def test_o9_eta_incertaine_echantillon_trop_court() -> None:
    """Complément O9 (condition 1 de D11, isolée) : sous 5 % du total, `?` même avec
    largement plus de sites actifs que de workers (aucune phase de queue)."""
    assert _eta_uncertain(done=59, total=1200, sites_active=25, workers=6) is True
    assert _eta_uncertain(done=60, total=1200, sites_active=25, workers=6) is False


# ── Complément « Définition de terminé » (hors table O1-O12, cheap et mécanisable) ──


def test_niveau_de_log_invalide_sort_en_usage_pas_en_trace_python() -> None:
    """« Définition de terminé » : un niveau de log invalide sort en `exit_codes.USAGE`
    (2), via un `typer.Exit` propre (donc un `SystemExit` attendu) — jamais une AUTRE
    exception Python non rattrapée qui remonterait en trace."""
    result = runner.invoke(app, ["--log-level", "BOGUS", "version"])
    assert result.exit_code == exit_codes.USAGE
    assert isinstance(result.exception, SystemExit)
    assert "BOGUS" in result.stderr


# ── O11 : core/ reste vierge de tout logging ────────────────────────────────────────


def test_o11_core_zero_logging() -> None:
    """O11 : `grep -rn "logging" src/tiny_wae/core/` -> 0 résultat (D3 : `core/` est du
    métier pur, zéro I/O, jamais de logger)."""
    core_dir = Path("src/tiny_wae/core")
    hits = [
        path
        for path in sorted(core_dir.rglob("*.py"))
        if "logging" in path.read_text(encoding="utf-8")
    ]
    assert hits == []


# ── O11bis : aucun emoji dans les chaînes AFFICHÉES de src/ ────────────────────────

# Les 4 emoji que la convention projet bannit des sorties console (D13) — la même liste
# que celle nommée dans la fiche, plus ✅ (même famille, jamais utilisé nulle part dans
# des chaînes affichées à ce jour : ajout défensif, sans faux positif mesuré).
_BANNED_EMOJI = "⚠⭐⛔✅"

# Méthodes de LOGGING dont le 1er argument positionnel est le message affiché (D7).
_LOG_METHODS = frozenset({"debug", "info", "warning", "error", "critical", "log"})


def _displayed_string_segments(source: str) -> list[str]:
    """Extrait le texte SOURCE du 1er argument positionnel de chaque appel
    `typer.echo(...)` ou `<logger>.<niveau>(...)` d'un module — la définition
    opérationnelle de « chaîne affichée » pour O11bis : ni une docstring, ni un
    commentaire n'y entre (ils sont massivement porteurs d'emoji dans ce dépôt, D13 ne
    les vise pas), seule une valeur envoyée à un canal de sortie (STDOUT/STDERR) compte.
    Une valeur composée dynamiquement (variable, pas un littéral) échappe par
    construction — on ne peut pas interdire un emoji dans une donnée runtime qu'on ne
    maîtrise pas."""
    tree = ast.parse(source)
    segments: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        is_echo = node.func.attr == "echo"
        is_log = node.func.attr in _LOG_METHODS
        if not (is_echo or is_log) or not node.args:
            continue
        # Pour `<logger>.log(level, msg, ...)`, le message est le 2e argument.
        arg_index = 1 if node.func.attr == "log" and len(node.args) > 1 else 0
        segment = ast.get_source_segment(source, node.args[arg_index])
        if segment is not None:
            segments.append(segment)
    return segments


def _count_displayed_emoji(sources: dict[str, str]) -> int:
    """Nombre de chaînes affichées (au sens ci-dessus), tous fichiers confondus, qui
    contiennent au moins un des emoji bannis."""
    count = 0
    for content in sources.values():
        for segment in _displayed_string_segments(content):
            if any(ch in segment for ch in _BANNED_EMOJI):
                count += 1
    return count


def _current_src_sources() -> dict[str, str]:
    root = Path("src/tiny_wae")
    return {str(path): path.read_text(encoding="utf-8") for path in sorted(root.rglob("*.py"))}


def _git_show_tree(ref: str, root: str) -> dict[str, str]:
    """Contenu de tous les `.py` sous `root` tels qu'ils existaient à `ref` (via
    `git ls-tree`/`git show`) — indépendant de l'arbre de travail courant. ``ref``/``root``
    viennent du corps du test (littéraux), jamais d'une entrée externe — chemin complet de
    l'exécutable résolu via ``shutil.which`` (S607)."""
    git = shutil.which("git")
    assert git is not None, "git introuvable sur PATH"
    listing = subprocess.run(  # noqa: S603 — args entièrement littéraux, aucune entrée externe.
        [git, "ls-tree", "-r", "--name-only", ref, root],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    sources: dict[str, str] = {}
    for path in listing:
        if path.endswith(".py"):
            sources[path] = subprocess.run(  # noqa: S603 — idem (path vient de git ls-tree).
                [git, "show", f"{ref}:{path}"], capture_output=True, text=True, check=True
            ).stdout
    return sources


def test_o11bis_zero_emoji_dans_les_chaines_affichees_de_src() -> None:
    """O11bis (volet « 0 occurrence ») : aucune chaîne affichée de `src/tiny_wae/` ne
    porte plus l'un des emoji bannis, après retrait des 4 occurrences trouvées (2 dans
    `cli/backfill.py`, nommées par la fiche, + 2 dans `cli/ingest.py`/`cli/update.py`,
    NON nommées par la fiche mais mesurées au même titre — cf. compte-rendu de dispatch)."""
    assert _count_displayed_emoji(_current_src_sources()) == 0


def test_o11bis_baisse_mesuree_vs_head_a6724e0() -> None:
    """O11bis (volet « compte global sur src/ ») : mesuré à HEAD `a6724e0` (l'ancrage de
    la fiche), le compte RÉEL est de 4 chaînes affichées avec emoji dans `src/` — pas 2
    (la fiche n'en nommait que 2, dans `cli/backfill.py` ; `cli/ingest.py` et
    `cli/update.py` en portaient chacun 1 de plus, non nommés). Le compte courant est 0 :
    la baisse mesurée est donc de 4, pas de 2 — un delta STRICTEMENT supérieur au
    minimum attendu par la fiche satisfait sa lettre (« diminué de 2 ») tout en la
    dépassant, ce qui est reporté tel quel plutôt que maquillé en « exactement 2 »."""
    baseline_sources = _git_show_tree("a6724e0", "src/tiny_wae")
    baseline_count = _count_displayed_emoji(baseline_sources)
    current_count = _count_displayed_emoji(_current_src_sources())

    assert baseline_count == 4
    assert current_count == 0
    assert baseline_count - current_count == 4
    assert baseline_count - current_count >= 2  # exigence littérale de la fiche.
