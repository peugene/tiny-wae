"""core/artifacts.py — noms canoniques des fichiers écrits pour un item (chapeau l0-03).

Zéro I/O, zéro framework. Même patron et même motif que ``core/statuses.py`` (post-revue 1,
constat A4) : ces noms étaient définis dans ``adapters/chips.py``, écrits EN DUR trois fois
dans ``adapters/contact_sheet.py``, et re-listés dans ``core/report.py`` (``EXPECTED_FILES``).
Renommer un artefact de sortie demandait de connaître les quatre endroits.
"""

from __future__ import annotations

# Noms de fichiers figés (décision d'ancrage n°6 de l0-03.3).
CHIP_10M_FILENAME = "chip.tif"
CHIP_20M_FILENAME = "chip_20m.tif"
SCL_FILENAME = "scl.tif"

# Les 3 fichiers attendus au manifeste d'un item ingéré — DÉRIVÉS des noms ci-dessus,
# jamais re-listés (c'est la recopie qui avait produit le constat A4).
EXPECTED_FILES: tuple[str, ...] = (CHIP_10M_FILENAME, CHIP_20M_FILENAME, SCL_FILENAME)
