"""Point d'entrée `python -m tiny_wae` — expose les CLIs typer du projet.

Chaque étape de pipeline = une sous-commande à I/O explicites (cf. CLAUDE.md, couches).

⭐ AUCUNE sous-commande ne se câble ici : elles s'ajoutent en déposant un module dans
`cli/` qui expose `register(app: typer.Typer) -> None` — c'est
`cli.discovery.discover_commands` (appelée ci-dessous) qui les importe et les enregistre.
Un module de `cli/` sans `register` est ignoré (utilitaire interne, pas une commande).
L'invariant est vérifié mécaniquement par
`tests/test_cli_discovery.py::test_main_module_has_no_per_command_wiring` — c'est LUI la
règle : ce fichier peut évoluer par ailleurs (option globale, callback), tant qu'il ne
référence aucun module de commande par son nom.

Taxonomie fermée du lot (décision chapeau l0-01, 9 sous-commandes) : `version` (ci-dessous),
`sites-validate`, `sites-list` (l0-01.2), `search`, `ingest`, `backfill`, `update`, `report`,
`contact-sheet` (fiches aval — pas de stub tant qu'elles ne sont pas implémentées).
`smoke` n'en fait PAS partie : c'est un script (`scripts/smoke.py`), pas un module `cli/`.

Porte aussi l'option GLOBALE `--log-level` (obs-01, D8) : c'est le seul endroit légitime
puisqu'elle s'applique à TOUTES les sous-commandes, avant leur exécution — une option de
sous-commande resterait, elle, interdite ici par l'invariant ci-dessus.
"""

import os

import typer

from tiny_wae.cli import exit_codes
from tiny_wae.cli.discovery import discover_commands
from tiny_wae.cli.logging_setup import InvalidLogLevelError, configure_logging, resolve_log_level

app = typer.Typer(no_args_is_help=True, help="tiny-wae — CLIs du projet.")


@app.callback()
def _main(
    log_level: str | None = typer.Option(
        None,
        "--log-level",
        help="Niveau de log (DEBUG/INFO/WARNING/ERROR/CRITICAL). Précédence : "
        "--log-level > TINY_WAE_LOG_LEVEL > INFO.",
    ),
) -> None:
    """Force le mode multi-commandes de typer (sans ce callback, une app à commande
    unique replie la sous-commande — `version` deviendrait la commande racine) et
    configure le logging applicatif (obs-01, D8) avant toute sous-commande."""
    try:
        level = resolve_log_level(log_level, os.environ.get("TINY_WAE_LOG_LEVEL"))
    except InvalidLogLevelError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=exit_codes.USAGE) from exc
    configure_logging(level)


@app.command()
def version() -> None:
    """Affiche la version du package."""
    from tiny_wae import __version__

    typer.echo(__version__)


discover_commands(app)


if __name__ == "__main__":
    app()
