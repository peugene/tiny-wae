"""Point d'entrée `python -m tiny_wae` — expose les CLIs typer du projet.

Chaque étape de pipeline = une sous-commande à I/O explicites (cf. CLAUDE.md, couches).
"""

import typer

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


if __name__ == "__main__":
    app()
