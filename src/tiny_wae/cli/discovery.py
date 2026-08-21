"""cli/discovery.py — auto-découverte des sous-commandes typer.

Convention retenue (décision d'ancrage l0-01.2, chapeau l0-01) : chaque module déposé dans
`cli/` expose une fonction `register(app: typer.Typer) -> None` qui enregistre sa/ses
commande(s) sur l'app. Un module sans `register` est simplement ignoré (permet des modules
utilitaires dans le package sans qu'ils soient traités comme des commandes).

Le package à balayer est un PARAMÈTRE (défaut `tiny_wae.cli`) — c'est ce qui rend la
découverte testable sans écrire dans le `src/` installé : un test peut construire un
package temporaire et le passer ici.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

import typer

DEFAULT_PACKAGE_NAME = "tiny_wae.cli"


def discover_commands(app: typer.Typer, package_name: str = DEFAULT_PACKAGE_NAME) -> None:
    """Importe chaque module de `package_name` et appelle son `register(app)` s'il existe.

    N'importe QUE les modules directement enfants du package (pas de récursion dans des
    sous-packages) ; l'ordre suit `pkgutil.iter_modules` (alphabétique sur la plupart des
    plateformes, non garanti — les commandes n'ont pas d'ordre à respecter entre elles).
    """
    package: ModuleType = importlib.import_module(package_name)
    package_path = getattr(package, "__path__", None)
    if package_path is None:
        raise ValueError(f"{package_name} : pas un package (pas d'attribut __path__)")

    for module_info in pkgutil.iter_modules(package_path, prefix=f"{package_name}."):
        module = importlib.import_module(module_info.name)
        register = getattr(module, "register", None)
        if callable(register):
            register(app)
