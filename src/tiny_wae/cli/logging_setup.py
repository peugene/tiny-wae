"""cli/logging_setup.py — configuration du logging applicatif (obs-01).

SEUL module du projet qui installe un handler ``logging`` (décision D3 de la fiche) : un
module de bibliothèque (``adapters/``) se contente de ``logging.getLogger(__name__)`` et
n'installe jamais rien lui-même — c'est ``__main__.py`` qui appelle ``configure_logging``
une fois, avant toute sous-commande.

⛔ STDERR exclusivement (D2) : STDOUT porte des données machine (JSON de ``search`` /
``sites-list``, cf. ancrage de la fiche) — jamais un log ne doit s'y mêler.
"""

from __future__ import annotations

import logging
import sys

# Colonnes fixes (fiche, « Format de ligne (figé) ») : horodatage, niveau (8 car. utiles,
# le plus long -- WARNING -- occupe 7), message. Le nom du logger n'entre PAS dans le
# format global : il varie d'un module à l'autre (`tiny_wae.adapters.backfill`, etc.), ce
# qui casserait l'alignement en colonnes que la fiche fige pour la charge utile du message
# — c'est donc le message lui-même (composé par l'appelant) qui porte le label du module.
_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Niveaux reconnus (ceux de la stdlib, cf. `logging.getLevelNamesMapping` sans le
# doublon numérique "WARN"/"FATAL" — D1 : rien de maison).
_VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class InvalidLogLevelError(ValueError):
    """Niveau de log demandé (option ``--log-level`` ou variable d'environnement) qui ne
    correspond à aucun niveau `logging` connu — le CLI la mappe sur ``exit_codes.USAGE``."""


def resolve_log_level(cli_value: str | None, env_value: str | None) -> str:
    """Résout le niveau effectif selon la précédence D4 : ``--log-level`` >
    ``TINY_WAE_LOG_LEVEL`` > ``INFO``. Lève ``InvalidLogLevelError`` si la valeur retenue
    (une fois normalisée en MAJUSCULES) n'est pas un niveau reconnu — jamais de niveau
    silencieusement ignoré."""
    if cli_value is not None:
        raw = cli_value
    elif env_value:
        raw = env_value
    else:
        raw = "INFO"
    level = raw.upper()
    if level not in _VALID_LEVELS:
        raise InvalidLogLevelError(
            f"niveau de log {raw!r} invalide (attendu : {', '.join(_VALID_LEVELS)})"
        )
    return level


def configure_logging(level: str) -> None:
    """Installe LE handler STDERR unique du projet sur le logger racine, en remplaçant
    tout handler déjà présent — c'est ce qui rend l'appel idempotent d'une invocation CLI
    à l'autre dans le MÊME process (tests inclus) : sans ce remplacement, un handler
    d'une invocation précédente resterait accroché à un flux STDERR déjà refermé.

    Ne configure QUE le logger racine : les modules de bibliothèque n'ont rien à faire
    eux-mêmes (D3), leur niveau effectif est hérité de la racine par la hiérarchie
    standard de `logging`."""
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
