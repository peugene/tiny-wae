"""core/sites.py — modèles typés et validation pure des sites de veille.

Zéro I/O, zéro framework : ce module ne sait rien lire, il ne fait que représenter et
valider des données déjà en mémoire (dataclasses frozen). Le chargement YAML/env vit dans
``adapters/config_io.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

# Catégories autorisées pour un site (docs/lots/lot-0-sites.md §3).
VALID_CATEGORIES = frozenset({"nuclear-construction", "megaproject", "stable-watch"})

# Bornes géographiques valides.
_LAT_MIN, _LAT_MAX = -90.0, 90.0
_LON_MIN, _LON_MAX = -180.0, 180.0

# Pas de grille attendu pour l'origine (mètres) — l0-01.3 calcule les grilles.
_GRID_ORIGIN_STEP_M = 20


class SiteValidationError(ValueError):
    """Erreur de validation d'un site — le message nomme le site ET le champ en cause."""


@dataclass(frozen=True, slots=True)
class Grid:
    """Grille figée d'un site (posée par l0-01.3) : EPSG + origine coin haut-gauche.

    Les trois champs sont ``None`` tant que la grille n'a pas été calculée — c'est l'état
    par défaut posé par cette fiche (l0-01.1).
    """

    epsg: int | None = None
    origin_x: float | None = None
    origin_y: float | None = None

    def validate(self, *, site_id: str) -> None:
        """Vérifie que l'origine, si renseignée, est bien un multiple de 20 m (X et Y)."""
        for axis_name, value in (("origin_x", self.origin_x), ("origin_y", self.origin_y)):
            if value is None:
                continue
            if value % _GRID_ORIGIN_STEP_M != 0:
                raise SiteValidationError(
                    f"site {site_id} : grid.{axis_name}={value} n'est pas un multiple de "
                    f"{_GRID_ORIGIN_STEP_M} m"
                )


@dataclass(frozen=True, slots=True)
class Site:
    """Un site de veille : identité, position, catégorie, et grille (éventuellement vide)."""

    id: str
    name: str
    lat: float
    lon: float
    category: str
    note: str
    reference_tile: str | None = None
    grid: Grid = Grid()

    def validate(self) -> None:
        """Valide bornes lat/lon, catégorie connue, et la grille associée."""
        if not (_LAT_MIN <= self.lat <= _LAT_MAX):
            raise SiteValidationError(
                f"site {self.id} : lat={self.lat} hors bornes [{_LAT_MIN}, {_LAT_MAX}]"
            )
        if not (_LON_MIN <= self.lon <= _LON_MAX):
            raise SiteValidationError(
                f"site {self.id} : lon={self.lon} hors bornes [{_LON_MIN}, {_LON_MAX}]"
            )
        if self.category not in VALID_CATEGORIES:
            raise SiteValidationError(
                f"site {self.id} : category={self.category!r} inconnue "
                f"(attendu {sorted(VALID_CATEGORIES)})"
            )
        self.grid.validate(site_id=self.id)


def validate_sites(sites: list[Site]) -> None:
    """Valide chaque site individuellement, puis l'unicité des ids sur l'ensemble.

    Lève ``SiteValidationError`` au premier problème rencontré (site + champ nommés).
    """
    seen: set[str] = set()
    for site in sites:
        site.validate()
        if site.id in seen:
            raise SiteValidationError(f"site {site.id} : id dupliqué")
        seen.add(site.id)
