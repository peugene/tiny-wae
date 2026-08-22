"""Tests d'empaquetage — le contrat de la wheel doit être COMPLET.

`[project.dependencies]` est la seule liste que voit un `pip install` de la wheel **hors
de notre atelier** : le venv du worker PID-FLOW, typiquement (cf. assets/cwl/README.md).
`pixi`, lui, installe aussi ce que déclare `[tool.pixi.dependencies]` — de sorte qu'une
dépendance oubliée au contrat du paquet reste **invisible en dev** : tout est vert ici,
`just check` compris, et l'installation ailleurs réussit… pour échouer à l'IMPORT, au
premier appel réel.

C'est exactement ce qui s'est produit : `rasterio`/`pyproj`/`pillow` n'étaient déclarés
que côté pixi et `numpy` nulle part (transitif de rasterio sous conda). Mesuré à
l'époque, venv nu + `pip install` : `ModuleNotFoundError: No module named 'numpy'` dès
`tiny-wae version`.

Ces deux tests sont le seul filet — aucun outil du gate ne regarde cette cohérence.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from importlib.metadata import packages_distributions
from pathlib import Path

_RACINE = Path(__file__).resolve().parent.parent
_SRC = _RACINE / "src"

# Nom de distribution en tête d'un specifier PEP 508 (`rasterio>=1.4` -> `rasterio`).
_NOM_DISTRIBUTION = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _normalise(nom: str) -> str:
    """Nom de distribution normalisé PEP 503 : `Pillow`, `pystac_client` et
    `pystac-client` doivent se comparer comme égaux."""
    return re.sub(r"[-_.]+", "-", nom).lower()


def _pyproject() -> dict[str, object]:
    return tomllib.loads((_RACINE / "pyproject.toml").read_text(encoding="utf-8"))


def _dependances_declarees() -> set[str]:
    """Noms normalisés de `[project.dependencies]`."""
    projet = _pyproject()["project"]
    assert isinstance(projet, dict)
    declarees: set[str] = set()
    for specifier in projet["dependencies"]:
        trouve = _NOM_DISTRIBUTION.match(str(specifier))
        assert trouve is not None, f"specifier illisible : {specifier!r}"
        declarees.add(_normalise(trouve.group(1)))
    return declarees


def _modules_racines_importes() -> set[str]:
    """Modules de PREMIER niveau importés par `src/`, hors stdlib et hors projet.

    Lecture par `ast`, pas par regex : un `from x import y` en milieu de fichier, un
    import conditionnel ou un import dans une fonction comptent tous — ce sont eux qui
    cassent en production, pas ceux qu'on voit en tête de fichier."""
    racines: set[str] = set()
    for fichier in _SRC.rglob("*.py"):
        arbre = ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Import):
                racines.update(alias.name.split(".")[0] for alias in noeud.names)
            elif isinstance(noeud, ast.ImportFrom) and noeud.level == 0 and noeud.module:
                racines.add(noeud.module.split(".")[0])
    return {
        racine
        for racine in racines
        if racine not in sys.stdlib_module_names and racine != "tiny_wae"
    }


def test_toute_dependance_tierce_importee_est_au_contrat_du_paquet() -> None:
    """Chaque module tiers importé par `src/` appartient à une distribution déclarée dans
    `[project.dependencies]`.

    La correspondance module -> distribution vient de `packages_distributions()`, pas
    d'une table écrite à la main : c'est ce qui fait que `PIL` -> `pillow` et
    `yaml` -> `pyyaml` se résolvent sans qu'on ait à les prévoir."""
    declarees = _dependances_declarees()
    par_module = packages_distributions()
    manquants: dict[str, list[str]] = {}
    for module in sorted(_modules_racines_importes()):
        distributions = par_module.get(module)
        assert distributions, (
            f"le module {module!r} est importé par src/ mais n'appartient à aucune "
            "distribution installée — dépendance fantôme ?"
        )
        if not any(_normalise(dist) in declarees for dist in distributions):
            manquants[module] = distributions
    assert not manquants, (
        "importés par src/ mais ABSENTS de [project.dependencies] — la wheel "
        f"s'installera et cassera à l'import : {manquants}"
    )


def test_les_dependances_conda_sont_aussi_au_contrat_du_paquet() -> None:
    """Tout ce que `[tool.pixi.dependencies]` déclare (hors `python` lui-même) est aussi
    dans `[project.dependencies]`.

    Cette section est un choix de SOURCE pour notre env de dev (builds natifs
    conda-forge), pas un contrat de livraison. Y déclarer un paquet runtime sans le
    déclarer aussi au projet, c'est le rendre disponible ici et nulle part ailleurs."""
    outillage = _pyproject()["tool"]
    assert isinstance(outillage, dict)
    pixi = outillage["pixi"]
    assert isinstance(pixi, dict)
    conda = pixi["dependencies"]
    assert isinstance(conda, dict)

    declarees = _dependances_declarees()
    oublies = sorted(nom for nom in conda if nom != "python" and _normalise(nom) not in declarees)
    assert not oublies, (
        f"{oublies} : déclarés pour pixi mais absents de [project.dependencies] — "
        "disponibles en dev, absents de la wheel livrée"
    )
