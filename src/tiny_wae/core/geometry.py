"""core/geometry.py — emprise du chip et transform affine, purs (zéro I/O).

Ce module ne lit aucun fichier : il dérive l'emprise géographique d'un chip et le
transform affine attendu de sortie à partir d'une ``Grid`` (site) et des tailles de chip
lues dans ``Settings``. La fenêtre rasterio (col_off/row_off dans la source) se calcule en
aval, dans l'adapter d'ingestion (l0-03.3), car elle dépend du transform du fichier lu.

⚠ Prémisse posée ici et vérifiée par les tests : les origines de tuiles Sentinel-2 sont
des multiples de 60 m (mesuré : 699960/4900020, 499980/4600020, 399960/5700000). L'origine
de grille du site (déjà un multiple de 20 m — cf. ``core.sites.Grid.validate``) rend donc
la fenêtre 20 m entière sans arrondi supplémentaire : 20 m divise 60 m, et l'emprise 10 m
(moitié de la taille en pixels, même pas) coïncide exactement avec l'emprise 20 m. Si cette
prémisse tombe (nouvelle source à origine non alignée), l'alignement ×2 n'est plus garanti.
"""

from __future__ import annotations

from affine import Affine

from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Grid


class GridNotComputedError(ValueError):
    """Levée quand la grille du site n'a pas encore été calculée (epsg/origin à None)."""


class InconsistentChipSizesError(ValueError):
    """Levée quand ``chip_px_10m``/``chip_px_20m`` ne couvrent pas la même surface au sol.

    L'invariant du lot (emprise 10 m == emprise 20 m, cf. prémisse d'alignement en tête de
    module) dépend de ce que 10 × ``chip_px_10m`` == 20 × ``chip_px_20m``. Un réglage qui
    viole cet invariant ne peut pas produire un chip 10 m et un chip 20 m superposables.
    """


def _require_computed(grid: Grid) -> tuple[int, float, float]:
    """Vérifie que la grille est calculée et renvoie ses trois champs non-None.

    Lève ``GridNotComputedError`` (typée) plutôt que de laisser l'arithmétique aval
    échouer sur un ``TypeError`` — c'est l'état par défaut du parc tant que l0-01.3
    (relevé réseau) n'a pas posé les grilles.
    """
    if grid.epsg is None or grid.origin_x is None or grid.origin_y is None:
        raise GridNotComputedError(
            "grille non calculée (epsg/origin_x/origin_y à None) — l0-01.3 doit s'exécuter "
            "avant de dériver une emprise de chip"
        )
    return grid.epsg, grid.origin_x, grid.origin_y


def chip_bounds(grid: Grid, settings: Settings) -> tuple[float, float, float, float]:
    """Emprise (minx, miny, maxx, maxy) du chip dans le CRS du site.

    Unique : l'emprise 10 m et l'emprise 20 m couvrent par construction la même surface
    au sol (``chip_px_10m`` × 10 m == ``chip_px_20m`` × 20 m — vérifié, pas supposé, sinon
    ``InconsistentChipSizesError``). Les tailles sont lues sur ``settings``
    (``chip_px_10m``/``chip_px_20m`` — jamais 512/256 en dur). L'origine de grille
    (``origin_x``/``origin_y``) est le coin haut-gauche.
    """
    _, origin_x, origin_y = _require_computed(grid)
    span_10m = settings.chip_px_10m * 10
    span_20m = settings.chip_px_20m * 20
    if span_10m != span_20m:
        raise InconsistentChipSizesError(
            f"chip_px_10m×10={span_10m} m != chip_px_20m×20={span_20m} m — "
            "les deux résolutions doivent couvrir la même emprise au sol"
        )
    minx = origin_x
    maxy = origin_y
    maxx = minx + span_10m
    miny = maxy - span_10m
    return (minx, miny, maxx, maxy)


def transform_for(grid: Grid, resolution: int) -> Affine:
    """Transform affine attendu des sorties, pour une résolution donnée (10 ou 20 m).

    Type ``affine.Affine`` — c'est celui que rasterio consomme nativement en l0-03.3.
    ``affine`` est une bibliothèque de maths sans I/O : l'importer ici ne viole pas la
    règle de couche (zéro framework I/O dans ``core/``).
    """
    _, origin_x, origin_y = _require_computed(grid)
    return Affine(resolution, 0.0, origin_x, 0.0, -resolution, origin_y)
