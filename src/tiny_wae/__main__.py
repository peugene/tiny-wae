"""Point d'entrée `python -m tiny_wae` — expose les CLIs typer du projet.

Chaque étape de pipeline = une sous-commande à I/O explicites (cf. CLAUDE.md, couches).

⭐ Ce fichier n'est PLUS JAMAIS modifié après l0-01.2 : les sous-commandes s'ajoutent en
déposant un module dans `cli/` qui expose `register(app: typer.Typer) -> None` — c'est
`cli.discovery.discover_commands` (appelée ci-dessous) qui les importe et les enregistre.
Un module de `cli/` sans `register` est ignoré (utilitaire interne, pas une commande).

Taxonomie fermée du lot (décision chapeau l0-01, 9 sous-commandes) : `version` (ci-dessous),
`sites-validate`, `sites-list` (l0-01.2), `search`, `ingest`, `backfill`, `update`, `report`,
`contact-sheet` (fiches aval — pas de stub tant qu'elles ne sont pas implémentées).
`smoke` n'en fait PAS partie : c'est un script (`scripts/smoke.py`), pas un module `cli/`.
"""

import typer

from tiny_wae.cli.discovery import discover_commands

app = typer.Typer(no_args_is_help=True, help="tiny-wae — CLIs du projet.")


@app.callback()
def _main() -> None:
    """Force le mode multi-commandes de typer (sans ce callback, une app à commande
    unique replie la sous-commande — `version` deviendrait la commande racine)."""


@app.command()
def version() -> None:
    """Affiche la version du package."""
    from tiny_wae import __version__

    typer.echo(__version__)


discover_commands(app)


if __name__ == "__main__":
    app()
