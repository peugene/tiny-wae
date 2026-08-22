"""Tests des CLIs branchés (l0-01.2) : version, sites-validate, sites-list.

Couvre O2, O3, O4 de la fiche (O1 et O5 sont couverts ailleurs : test_cli_discovery.py et
`just check`). Invoque `tiny_wae.__main__.app`, l'app réelle telle qu'assemblée par
`discover_commands` — pas un mock.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from tiny_wae import __version__
from tiny_wae.__main__ import app

# Import ré-exporté explicitement : sous `--no-implicit-reexport` (mypy strict), un
# `from tiny_wae.cli import exit_codes` seul est refusé, le package ne ré-exportant pas son
# sous-module. Erreur devenue visible quand le gate a cessé de n'analyser que `src/` (out-01).
from tiny_wae.cli import exit_codes as exit_codes  # noqa: PLC0414

runner = CliRunner()

SITES_PATH = Path("config/sites.yaml")
FIXTURE_BAD_LAT = Path("tests/fixtures/config/broken_sites_bad_lat.yaml")
FIXTURE_MISSING_KEY = Path("tests/fixtures/config/broken_sites_missing_key.yaml")


def test_version_unchanged_o4() -> None:
    """O4 : `version` reste inchangée, affiche la version réelle du package (0.1.0)."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == exit_codes.OK
    assert result.output.strip() == __version__ == "0.1.0"


def test_sites_validate_nominal_o2() -> None:
    """O2 : `sites-validate` sur la config livrée sort en OK (0)."""
    result = runner.invoke(app, ["sites-validate", "--path", str(SITES_PATH)])
    assert result.exit_code == exit_codes.OK


def test_sites_validate_broken_lat_o3() -> None:
    """O3 (volet SiteValidationError) : lat hors bornes -> USAGE (2), id + champ sur STDERR."""
    result = runner.invoke(app, ["sites-validate", "--path", str(FIXTURE_BAD_LAT)])
    assert result.exit_code == exit_codes.USAGE
    stderr = result.output
    assert "X01" in stderr
    assert "lat" in stderr


def test_sites_validate_broken_missing_key_o3() -> None:
    """O3 (volet ConfigError) : racine YAML sans clé 'sites' -> USAGE (2) également."""
    result = runner.invoke(app, ["sites-validate", "--path", str(FIXTURE_MISSING_KEY)])
    assert result.exit_code == exit_codes.USAGE


def test_sites_validate_missing_file_o3() -> None:
    """O3 (volet ConfigError) : fichier absent -> USAGE (2)."""
    result = runner.invoke(app, ["sites-validate", "--path", "config/does_not_exist.yaml"])
    assert result.exit_code == exit_codes.USAGE


def test_sites_list_nominal() -> None:
    """`sites-list` texte : les 25 sites livrés apparaissent, un par ligne.

    D10 (obs-01) : sur `result.stdout`, pas `result.output` — ce test vérifie le canal de
    DONNÉES, `result.output` (qui inclut STDERR sous click 8.4.2) l'exposerait au premier
    log émis en amont (ex. la ligne d'ouverture de `backfill`, hors-sujet ici)."""
    result = runner.invoke(app, ["sites-list", "--path", str(SITES_PATH)])
    assert result.exit_code == exit_codes.OK
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 25
    assert "A01" in result.stdout


def test_sites_list_json() -> None:
    """`sites-list --json` : sortie JSON valide, liste de 25 objets avec la clé `id`.

    D10 (obs-01) : `result.stdout`, pas `result.output` (même raison que ci-dessus)."""
    import json

    result = runner.invoke(app, ["sites-list", "--path", str(SITES_PATH), "--json"])
    assert result.exit_code == exit_codes.OK
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    assert len(payload) == 25
    assert {entry["id"] for entry in payload} >= {"A01", "C08"}


def test_sites_list_broken_o3() -> None:
    """`sites-list` propage la même erreur USAGE que `sites-validate` sur une config cassée."""
    result = runner.invoke(app, ["sites-list", "--path", str(FIXTURE_BAD_LAT)])
    assert result.exit_code == exit_codes.USAGE
    assert "X01" in result.output
    assert "lat" in result.output
