"""adapters/stac.py — port ``StacSource`` + implémentation earth-search (l0-02.1).

Répond à « quels items S2 L2A couvrent ce site sur cette fenêtre ? » : ``EarthSearchSource``
interroge earth-search via ``pystac-client``, ``build_envelope`` (pur, zéro I/O) parse les
items bruts et applique les DEUX filtres du chapeau l0-02 — bbox du chip TOUJOURS dans la
requête réseau, ``eo:cloud_cover < scene_cloud_max`` et tuile de référence appliqués ICI,
côté client, sur les items déjà reçus.

⭐ **Normalisation du code de tuile (décision n°1 de la fiche, CORRIGÉE au ré-ancrage)** :
le domaine utilise le code MGRS NU (``52TEL``), earth-search rend ``properties.grid:code``
préfixé (``MGRS-52TEL``) — ``parse_item`` retire ce préfixe vendeur, qui disparaîtrait à
une bascule CDSE, au même titre que ``earthsearch:boa_offset_applied``.

⚠ **Garde href** : pour les clés d'assets MAPPÉES (``Settings.asset_keys``) uniquement,
tout href ``s3://`` fait lever ``StacSourceError`` — les assets non mappés des items S2C
(``cloud``, ``snow`` — restent en ``s3://`` chez earth-search) sont ignorés sans erreur,
qu'ils soient mappés ou non n'entre pas en jeu puisqu'on ne les regarde jamais.

⚠ **Écart mesuré vs la fiche (21/08/2026, fixtures live)** : les items earth-search actuels
ne portent PLUS ``properties.proj:epsg`` (la clé documentée par la fiche) — seulement
``properties.proj:code`` (``"EPSG:32631"``, l'extension ``proj`` a migré). ``_extract_epsg``
accepte les deux formes ; voir sa docstring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pystac_client import Client

from tiny_wae.core.acquisition import Acquisition, Radiometry
from tiny_wae.core.envelope import Envelope
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Site
from tiny_wae.core.tiles import wgs84_survey_bbox
from tiny_wae.core.windows import Window

# earth-search rend le code MGRS préfixé par ce marqueur vendeur (à retirer — décision n°1).
_MGRS_VENDOR_PREFIX = "MGRS-"


class StacSourceError(ValueError):
    """Erreur de parsing ou de filtrage d'un item STAC (href s3:// sur un asset mappé…)."""


class StacSource(Protocol):
    """Port : recherche des items S2 L2A pour un site sur une fenêtre temporelle."""

    def search(self, site: Site, window: Window) -> Envelope:
        """Renvoie l'enveloppe (items retenus + compteurs) pour ``site`` sur ``window``."""
        ...


def _extract_epsg(props: dict[str, Any]) -> int:
    """Lit l'EPSG UTM depuis les propriétés d'un item — ``proj:epsg`` (entier, forme datée
    de l'extension ``proj``) SI présent, sinon ``proj:code`` (``"EPSG:32631"``, forme
    actuelle mesurée sur earth-search au 21/08/2026 — la clé ``proj:epsg`` documentée par
    la fiche n'apparaît PLUS dans les items live, l'extension ``proj`` ayant migré vers
    ``proj:code`` entretemps). Les deux formes sont acceptées pour rester robuste à un
    retour en arrière côté vendeur.

    Lève ``StacSourceError`` si ni l'une ni l'autre n'est exploitable.
    """
    if "proj:epsg" in props:
        return int(props["proj:epsg"])
    code = props.get("proj:code")
    if isinstance(code, str) and code.upper().startswith("EPSG:"):
        try:
            return int(code.split(":", 1)[1])
        except ValueError as exc:
            raise StacSourceError(f"proj:code malformé : {code!r}") from exc
    raise StacSourceError("ni proj:epsg ni proj:code exploitable dans les propriétés de l'item")


def _parse_radiometry(asset: dict[str, Any]) -> Radiometry:
    """Lit ``raster:bands[0].{scale,offset}`` d'UN asset — ``None`` si absent (ex. ``scl``).

    ⭐ Propriété PAR ASSET (arbitrage n°1 de la fiche), jamais par item : les 10 bandes de
    réflectance portent ``0.0001 / -0.1``, ``aot``/``wvp`` portent ``0.001 / 0``.
    """
    bands = asset.get("raster:bands")
    if not bands:
        return None
    band0 = bands[0]
    if "scale" not in band0 or "offset" not in band0:
        return None
    return (float(band0["scale"]), float(band0["offset"]))


def parse_item(item: dict[str, Any], asset_keys: tuple[str, ...]) -> Acquisition:
    """Parse UN item STAC brut (dict, tel que rendu par earth-search) en ``Acquisition``.

    Ne regarde que les clés d'assets de ``asset_keys`` (les clés mappées) : un asset non
    mappé absent de la liste (ex. ``cloud``, ``snow`` des items S2C) n'est jamais lu, donc
    jamais soumis à la garde anti-``s3://`` ci-dessous. Un asset mappé absent de l'item est
    silencieusement omis (n'ajoute pas d'entrée à ``assets``/``radiometry``).

    Lève ``StacSourceError`` si un asset MAPPÉ porte un href ``s3://`` (garde du chapeau).
    """
    props = item["properties"]
    raw_assets = item.get("assets", {})

    assets: dict[str, str] = {}
    radiometry: dict[str, Radiometry] = {}
    for key in asset_keys:
        asset = raw_assets.get(key)
        if asset is None:
            continue
        href = asset["href"]
        if href.startswith("s3://"):
            raise StacSourceError(
                f"item {item['id']!r} : asset mappé {key!r} en s3:// ({href!r}) — refusé"
            )
        assets[key] = href
        radiometry[key] = _parse_radiometry(asset)

    return Acquisition(
        item_id=item["id"],
        datetime=props["datetime"],
        platform=props["platform"],
        tile=str(props["grid:code"]).removeprefix(_MGRS_VENDOR_PREFIX),
        sequence=props["s2:sequence"],
        scene_cloud_cover=float(props["eo:cloud_cover"]),
        nodata_pixel_pct=float(props["s2:nodata_pixel_percentage"]),
        processing_baseline=props["s2:processing_baseline"],
        boa_offset_applied=bool(props["earthsearch:boa_offset_applied"]),
        proj_epsg=_extract_epsg(props),
        assets=assets,
        radiometry=radiometry,
    )


def build_envelope(
    *,
    site_id: str,
    window: Window,
    raw_items: list[dict[str, Any]],
    reference_tile: str,
    scene_cloud_max: int,
    asset_keys: tuple[str, ...],
) -> Envelope:
    """Parse ``raw_items`` et applique les filtres qualité + tuile — fonction PURE.

    Fonction de ``(items, tuile)`` uniquement (ne lit ni réseau ni ``sites.yaml``) : c'est
    ce qui permet à l'oracle O4 de la fiche de passer ``reference_tile`` en littéral, sans
    dépendre du relevé réseau de l0-01.3. Compte ``skipped_scene_cloud`` (``eo:cloud_cover
    >= scene_cloud_max``) puis ``off_tile`` (``tile != reference_tile``, sur le reste) — un
    item nuageux hors tuile compte dans ``skipped_scene_cloud``, jamais dans ``off_tile``
    (ordre de filtre fixé par le périmètre de la fiche).
    """
    found_stac = len(raw_items)
    skipped_scene_cloud = 0
    off_tile = 0
    kept: list[Acquisition] = []

    for raw in raw_items:
        acquisition = parse_item(raw, asset_keys)
        if acquisition.scene_cloud_cover >= scene_cloud_max:
            skipped_scene_cloud += 1
            continue
        if acquisition.tile != reference_tile:
            off_tile += 1
            continue
        kept.append(acquisition)

    counters = {
        "found_stac": found_stac,
        "skipped_scene_cloud": skipped_scene_cloud,
        "off_tile": off_tile,
        "found_tile": len(kept),
    }
    return Envelope(
        schema_version=1,
        site_id=site_id,
        window={"start": window.start.isoformat(), "end": window.end.isoformat()},
        counters=counters,
        items=kept,
    )


@dataclass(frozen=True, slots=True)
class EarthSearchSource:
    """Implémentation ``StacSource`` pour earth-search (``pystac-client``).

    La bascule CDSE (hors lot) se ferait en écrivant une seconde classe portant le même
    protocole ``StacSource`` — ce module n'a alors rien à changer côté appelant.
    """

    settings: Settings

    def search(self, site: Site, window: Window) -> Envelope:
        """Interroge earth-search sur la bbox du chip du site et la fenêtre, puis filtre.

        Lève ``StacSourceError`` si ``site.reference_tile`` n'est pas encore posé (aucune
        tuile à filtrer). ``datetime`` est passé en objets ``datetime`` natifs à
        ``pystac-client`` — RFC3339 complet, earth-search rejette une plage date seule
        (découverte de terrain de l0-01.3, cf. ancrage de la fiche).
        """
        if site.reference_tile is None:
            raise StacSourceError(f"site {site.id} : reference_tile non posée — recherche refusée")

        span_m = float(self.settings.chip_px_10m * 10)
        bbox = wgs84_survey_bbox(site.lat, site.lon, span_m)

        client = Client.open(self.settings.stac_url)
        item_search = client.search(
            collections=[self.settings.stac_collection],
            bbox=bbox,
            datetime=(window.start, window.end),
        )
        raw_items = [item.to_dict() for item in item_search.items()]

        return build_envelope(
            site_id=site.id,
            window=window,
            raw_items=raw_items,
            reference_tile=site.reference_tile,
            scene_cloud_max=self.settings.scene_cloud_max,
            asset_keys=self.settings.asset_keys,
        )
