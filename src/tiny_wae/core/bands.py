"""core/bands.py — ordre canonique des bandes par résolution (Clay v1.5 nominal, D-b).

Zéro I/O, zéro framework. Module dédié (et non ``core/geometry.py``, dispatché en
parallèle sur l0-03.1) pour ne pas produire de conflit de merge, et pour que
``adapters/chips.py`` (l0-03.3) puisse lire ces ordres sans dépendre de
``adapters/manifests.py``. Référencé par la formule canonique du ``grid_hash``
(chapeau l0-03) et par ``adapters/manifests.py``.
"""

from __future__ import annotations

# 4 bandes du chip 10 m (chip.tif, 512x512).
BAND_ORDER_10M: tuple[str, ...] = ("blue", "green", "red", "nir")

# 6 bandes du chip 20 m (chip_20m.tif, 256x256) — D-b : Clay v1.5 nominal, coût total x1.41.
BAND_ORDER_20M: tuple[str, ...] = (
    "rededge1",
    "rededge2",
    "rededge3",
    "nir08",
    "swir16",
    "swir22",
)
