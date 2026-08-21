"""core/acquisition.py — contrat ``Acquisition`` (l0-02.1).

Zéro I/O, zéro framework : une ``Acquisition`` est un item STAC déjà parsé et normalisé
(l'adapter earth-search fait ce travail dans ``adapters/stac.py``), avec round-trip JSON
via ``to_dict``/``from_dict``.

⭐ Arbitrage n°1 (21/08, cf. fiche) : ``radiometry`` est un dict PAR CLÉ D'ASSET
(``scale``/``offset`` mesurés sur ``assets[clé].raster:bands[0]``), pas deux scalaires
d'item — les 10 bandes de réflectance portent ``0.0001 / -0.1``, ``aot``/``wvp`` portent
``0.001 / 0``, et ``scl`` n'en porte aucun (``None``). Un contrat lossy ici se paierait par
une ré-lecture complète du STAC au Lot 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Type d'un couple (scale, offset) radiométrique, ou None si l'asset n'en porte pas.
Radiometry = tuple[float, float] | None


@dataclass(frozen=True, slots=True)
class Acquisition:
    """Un item S2 L2A déjà parsé — clés STAC source documentées dans la fiche l0-02.1.

    ``tile`` est le code MGRS NU (``52TEL``, jamais ``MGRS-52TEL``) : la normalisation du
    préfixe vendeur ``MGRS-`` est la responsabilité de l'adapter, pas de ce contrat.
    ``sequence`` est une CHAÎNE (``"0"``, pas un entier — earth-search la rend ainsi).
    """

    item_id: str
    datetime: str
    platform: str
    tile: str
    sequence: str
    scene_cloud_cover: float
    nodata_pixel_pct: float
    processing_baseline: str
    boa_offset_applied: bool
    proj_epsg: int
    assets: dict[str, str]
    radiometry: dict[str, Radiometry]

    def to_dict(self) -> dict[str, Any]:
        """Sérialise en dict JSON-compatible (les tuples radiométriques deviennent des listes)."""
        return {
            "item_id": self.item_id,
            "datetime": self.datetime,
            "platform": self.platform,
            "tile": self.tile,
            "sequence": self.sequence,
            "scene_cloud_cover": self.scene_cloud_cover,
            "nodata_pixel_pct": self.nodata_pixel_pct,
            "processing_baseline": self.processing_baseline,
            "boa_offset_applied": self.boa_offset_applied,
            "proj_epsg": self.proj_epsg,
            "assets": dict(self.assets),
            "radiometry": {
                key: (list(value) if value is not None else None)
                for key, value in self.radiometry.items()
            },
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Acquisition:
        """Reconstruit une ``Acquisition`` depuis son dict JSON (inverse de ``to_dict``)."""
        radiometry: dict[str, Radiometry] = {}
        for key, value in data["radiometry"].items():
            radiometry[key] = None if value is None else (float(value[0]), float(value[1]))
        return Acquisition(
            item_id=data["item_id"],
            datetime=data["datetime"],
            platform=data["platform"],
            tile=data["tile"],
            sequence=data["sequence"],
            scene_cloud_cover=data["scene_cloud_cover"],
            nodata_pixel_pct=data["nodata_pixel_pct"],
            processing_baseline=data["processing_baseline"],
            boa_offset_applied=data["boa_offset_applied"],
            proj_epsg=data["proj_epsg"],
            assets=dict(data["assets"]),
            radiometry=radiometry,
        )
