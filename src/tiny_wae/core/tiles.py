"""core/tiles.py — géométrie pure du choix de tuile de référence (l0-01.3, règle D-c).

Zéro I/O, zéro réseau : ce module ne sait interroger ni earth-search ni aucun service. Il
prend en entrée des coordonnées et des emprises déjà mesurées (par ``scripts/survey_tiles.py``,
qui fait le réseau) et calcule : la bbox WGS84 approximative servant à la requête
``/aggregate`` du relevé, la position du chip en UTM, l'emprise nominale d'une tuile MGRS
depuis son origine (coin haut-gauche) mesurée, la marge géométrique chip↔bord de tuile, et
l'EPSG UTM déduit d'un code MGRS. ``choose_reference_tile`` applique la règle D-c (décision
Philippe 21/08) : marge géométrique maximale, la plus fournie en items en cas d'égalité.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pyproj import Transformer

# Côté nominal d'une tuile Sentinel-2 (109 800 m = 10 980 px @ 10 m — mesuré sur earth-search).
TILE_SIDE_M = 109_800.0

# Pas d'arrondi de l'origine de grille (décision chapeau l0-01, cf. core.sites.Grid).
GRID_ORIGIN_STEP_M = 20

# Bandes de latitude MGRS de C à M (sud) ; N à X (nord). Bandes I et O n'existent pas dans
# la nomenclature MGRS (évite la confusion visuelle avec 1/0), mais on ne les rejette pas
# explicitement ici : earth-search n'en produira jamais, une entrée malformée lève KeyError
# via l'indexation ``ord()`` plus bas — un site mal codé plante fort plutôt que de se taire.
_SOUTH_BAND_LETTERS = frozenset("CDEFGHJKLM")


class TileGeometryError(ValueError):
    """Erreur de géométrie de tuile — code MGRS malformé ou entrée hors domaine."""


def mgrs_zone_epsg(grid_code: str) -> int:
    """Déduit l'EPSG UTM (326xx nord / 327xx sud) d'un code MGRS type ``MGRS-52TEL`` ou ``52TEL``.

    Le préfixe ``MGRS-`` éventuel (tel que rendu par l'agrégation earth-search) est ignoré.
    Zone = les 1 ou 2 premiers chiffres ; bande de latitude = la lettre qui suit (C-M sud,
    N-X nord — I et O exclus de la nomenclature).
    """
    code = grid_code.removeprefix("MGRS-")
    digits = ""
    rest = code
    for char in code:
        if char.isdigit():
            digits += char
            rest = rest[1:]
        else:
            break
    if not digits or not rest:
        raise TileGeometryError(f"code MGRS malformé (zone/bande introuvable) : {grid_code!r}")
    try:
        zone = int(digits)
    except ValueError as exc:
        raise TileGeometryError(f"code MGRS malformé (zone non numérique) : {grid_code!r}") from exc
    if not (1 <= zone <= 60):
        raise TileGeometryError(f"code MGRS : zone UTM {zone} hors bornes [1, 60] : {grid_code!r}")
    band = rest[0].upper()
    base = 32700 if band in _SOUTH_BAND_LETTERS else 32600
    return base + zone


def latlon_to_epsg(lat: float, lon: float, epsg: int) -> tuple[float, float]:
    """Projette (lat, lon) en WGS84 vers ``(x, y)`` dans le CRS ``epsg`` (typiquement UTM)."""
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    x, y = transformer.transform(lon, lat)
    return x, y


def natural_utm_epsg(lat: float, lon: float) -> int:
    """Zone UTM « naturelle » d'un point (celle où il tombe), pour construire la bbox du
    relevé — indépendante de la tuile de référence qui sera choisie ensuite."""
    zone = int((lon + 180) / 6) + 1
    zone = min(max(zone, 1), 60)
    return (32700 if lat < 0 else 32600) + zone


def wgs84_survey_bbox(lat: float, lon: float, span_m: float) -> tuple[float, float, float, float]:
    """Bbox WGS84 (minlon, minlat, maxlon, maxlat) du chip centré sur (lat, lon), côté
    ``span_m`` — construite en projetant dans la zone UTM naturelle du point puis en
    reprojetant les 4 coins vers WGS84. Sert UNIQUEMENT à cadrer les requêtes réseau du
    relevé (``/aggregate``, ``/search``) : la marge géométrique se calcule, elle, dans le
    CRS de chaque tuile candidate (cf. ``candidate_margin_m``)."""
    epsg = natural_utm_epsg(lat, lon)
    cx, cy = latlon_to_epsg(lat, lon, epsg)
    half = span_m / 2
    corners_utm = [
        (cx - half, cy - half),
        (cx - half, cy + half),
        (cx + half, cy - half),
        (cx + half, cy + half),
    ]
    to_wgs84 = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    lons = []
    lats = []
    for x, y in corners_utm:
        clon, clat = to_wgs84.transform(x, y)
        lons.append(clon)
        lats.append(clat)
    return (min(lons), min(lats), max(lons), max(lats))


def chip_bounds_utm(
    center_x: float, center_y: float, span_m: float
) -> tuple[float, float, float, float]:
    """Emprise (minx, miny, maxx, maxy) du chip carré de côté ``span_m`` centré sur
    ``(center_x, center_y)``, dans le CRS déjà choisi par l'appelant."""
    half = span_m / 2
    return (center_x - half, center_y - half, center_x + half, center_y + half)


def tile_bounds(
    origin_x: float, origin_y: float, side_m: float = TILE_SIDE_M
) -> tuple[float, float, float, float]:
    """Emprise (minx, miny, maxx, maxy) nominale d'une tuile depuis son coin haut-gauche
    (origin_x = ULX, origin_y = ULY) mesuré via ``proj:transform`` — jamais recalculé
    depuis une convention supposée (cf. ancrage de la fiche)."""
    return (origin_x, origin_y - side_m, origin_x + side_m, origin_y)


def geometric_margin_m(
    chip: tuple[float, float, float, float], tile: tuple[float, float, float, float]
) -> float:
    """Marge géométrique (m) entre le chip et le bord de tuile le plus proche : le minimum
    des 4 distances chip↔bord. Négative si le chip déborde de la tuile (candidate à
    écarter — la fonction ne filtre pas, ``choose_reference_tile`` compare les valeurs)."""
    cminx, cminy, cmaxx, cmaxy = chip
    tminx, tminy, tmaxx, tmaxy = tile
    return min(cminx - tminx, tmaxx - cmaxx, cminy - tminy, tmaxy - cmaxy)


def candidate_margin_m(
    lat: float,
    lon: float,
    span_m: float,
    epsg: int,
    origin_x: float,
    origin_y: float,
    side_m: float = TILE_SIDE_M,
) -> float:
    """Marge géométrique chip↔bord pour UNE tuile candidate : projette (lat, lon) dans le
    CRS de la candidate (chaque candidate peut être une zone UTM distincte), construit
    l'emprise du chip et celle de la tuile, renvoie ``geometric_margin_m``."""
    cx, cy = latlon_to_epsg(lat, lon, epsg)
    chip = chip_bounds_utm(cx, cy, span_m)
    tile = tile_bounds(origin_x, origin_y, side_m)
    return geometric_margin_m(chip, tile)


def round_down_to_step(value: float, step: int = GRID_ORIGIN_STEP_M) -> float:
    """Arrondit ``value`` au multiple de ``step`` inférieur (floor) — utilisé pour caler
    l'origine de grille du chip (coin haut-gauche) sur la contrainte du chapeau l0-01."""
    return math.floor(value / step) * step


@dataclass(frozen=True, slots=True)
class TileCandidate:
    """Une tuile MGRS candidate pour un site : code, EPSG, origine mesurée, marge calculée
    et nombre d'items (fréquence du bucket ``/aggregate``) — sert au départage D-c."""

    code: str
    epsg: int
    origin_x: float
    origin_y: float
    margin_m: float
    item_count: int


def choose_reference_tile(candidates: list[TileCandidate]) -> TileCandidate:
    """Règle D-c (décision Philippe 21/08) : la tuile de marge géométrique maximale ;
    en cas d'égalité de marge, la plus fournie en items. Lève ``TileGeometryError`` si la
    liste est vide (site sans tuile candidate — le relevé réseau n'a rien trouvé)."""
    if not candidates:
        raise TileGeometryError("aucune tuile candidate à départager")
    return max(candidates, key=lambda c: (c.margin_m, c.item_count))


def chip_origin(lat: float, lon: float, epsg: int, span_m: float) -> tuple[float, float]:
    """Origine de grille (coin haut-gauche du chip, arrondi au multiple de 20 m inférieur)
    pour un site dont la tuile de référence est dans ``epsg``. Formule : projette
    (lat, lon) dans ``epsg``, prend le coin haut-gauche du chip centré (minx du chip,
    maxy du chip), arrondit chaque coordonnée au multiple de 20 m inférieur."""
    cx, cy = latlon_to_epsg(lat, lon, epsg)
    minx, _, _, maxy = chip_bounds_utm(cx, cy, span_m)
    return round_down_to_step(minx), round_down_to_step(maxy)
