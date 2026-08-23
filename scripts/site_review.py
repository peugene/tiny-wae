#!/usr/bin/env python3
"""Aide à la revue HUMAINE du centrage des 25 sites (fiche l0-03.H).

⚠ Cet outil ne valide RIEN et ne décide RIEN. La question de l0-03.H — « les coordonnées
posées de mémoire (±1-2 km) visent-elles la bonne infrastructure ? » — ne se répond qu'à
l'œil, sur de l'imagerie de référence. Ce script se contente de rendre ce trajet rapide :
il fabrique, pour les 25 sites, de quoi ouvrir le bon endroit à la bonne date en un clic.

Deux sorties, sous ``<data_root>/site-review/`` :

- ``sites.geojson`` — les 25 EMPRISES réellement découpées (polygones, en WGS84) et les 25
  POINTS visés (``lat``/``lon`` de ``sites.yaml``). À déposer dans QGIS ou sur geojson.io :
  l'écart entre un point et le centre de son carré se voit immédiatement.
- ``index.html`` — une ligne par site : vignette du chip retenu (le même que la planche),
  coordonnées, date, et les liens vers le Copernicus Browser et OpenStreetMap.

L'emprise n'est pas recalculée à la main : elle vient de ``core.geometry.chip_bounds``,
la fonction qui a réellement servi au découpage. Le chip affiché vient de
``latest_ingested_manifest``, celui-là même que la planche a retenu.
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image
from pyproj import Transformer

from tiny_wae.adapters.config_io import (
    DEFAULT_SETTINGS_PATH,
    DEFAULT_SITES_PATH,
    load_settings,
    load_sites,
)
from tiny_wae.adapters.contact_sheet import latest_ingested_manifest, render_rgb
from tiny_wae.core.artifacts import CHIP_10M_FILENAME
from tiny_wae.core.geometry import chip_bounds
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Site

# Côté de la vignette dans la page, en pixels. 180 suffit à reconnaître une piste ou un
# quai ; au-delà, la page devient lourde (25 images en base64 dans un fichier unique).
_VIGNETTE_PX = 180

# Zoom du Copernicus Browser. Le chip fait 5,12 km de côté : z=13 cadre environ 8 km de
# large sur un écran courant, donc l'emprise du chip tient dedans avec du contexte autour.
_ZOOM = 13

# ⚠ Identifiant de jeu de données du Copernicus Browser. `S2_L1C_CDAS` est documenté ;
# `S2_L2A_CDAS` en est déduit PAR SYMÉTRIE, pas lu dans la documentation. Si le lien daté
# n'ouvre pas la bonne couche, le sélecteur du Browser la corrige en un clic — et le lien
# « simple » (position seule), lui, ne dépend d'aucun identifiant.
_DATASET_L2A = "S2_L2A_CDAS"


@dataclass(frozen=True, slots=True)
class SiteReview:
    """Tout ce qu'une ligne de la page (et une paire d'entités GeoJSON) demande."""

    site: Site
    item_id: str | None
    date: str | None
    corners_wgs84: tuple[tuple[float, float], ...]
    center_wgs84: tuple[float, float]
    offset_m: float
    vignette_png: bytes | None


def _transformers(epsg: int) -> tuple[Transformer, Transformer]:
    """(site -> WGS84, WGS84 -> site). ``always_xy`` : on raisonne en (x, y) = (lon, lat)."""
    vers_wgs84 = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    vers_site = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    return vers_wgs84, vers_site


def _vignette(chip_path: Path) -> bytes | None:
    """Rend le chip en PNG réduit. ``None`` si le fichier a disparu du disque."""
    if not chip_path.is_file():
        return None
    image = render_rgb(chip_path)
    image = image.resize((_VIGNETTE_PX, _VIGNETTE_PX), Image.Resampling.LANCZOS)
    tampon = io.BytesIO()
    image.save(tampon, format="PNG")
    return tampon.getvalue()


def _review_site(site: Site, settings: Settings, data_root: Path) -> SiteReview:
    """Assemble la revue d'un site : emprise en WGS84, écart au point visé, vignette.

    ``offset_m`` est la distance entre le point déclaré dans ``sites.yaml`` et le CENTRE de
    l'emprise réellement découpée. Il ne dit PAS si le point est le bon — seulement si le
    découpage est bien centré sur ce qui a été demandé (accrochage à la grille de la tuile).
    """
    epsg = site.grid.epsg
    if epsg is None:
        raise ValueError(f"site {site.id} : grille non calculée — lancer `just survey-tiles`")

    minx, miny, maxx, maxy = chip_bounds(site.grid, settings)
    vers_wgs84, vers_site = _transformers(epsg)
    coins_site = ((minx, maxy), (maxx, maxy), (maxx, miny), (minx, miny))
    coins_wgs84 = tuple(vers_wgs84.transform(x, y) for x, y in coins_site)

    centre_x, centre_y = (minx + maxx) / 2, (miny + maxy) / 2
    centre_wgs84 = vers_wgs84.transform(centre_x, centre_y)
    vise_x, vise_y = vers_site.transform(site.lon, site.lat)
    offset_m = ((centre_x - vise_x) ** 2 + (centre_y - vise_y) ** 2) ** 0.5

    manifest = latest_ingested_manifest(data_root, site.id)
    item_id = manifest.item_id if manifest is not None else None
    date = manifest.datetime.split("T", 1)[0] if manifest is not None else None
    vignette = (
        _vignette(data_root / site.id / item_id / CHIP_10M_FILENAME)
        if item_id is not None
        else None
    )
    return SiteReview(
        site=site,
        item_id=item_id,
        date=date,
        corners_wgs84=coins_wgs84,
        center_wgs84=centre_wgs84,
        offset_m=offset_m,
        vignette_png=vignette,
    )


def _geojson(revues: list[SiteReview]) -> dict[str, Any]:
    """FeatureCollection : une emprise (Polygon) + un point visé (Point) par site.

    Le point porte ``role: "vise"`` et l'emprise ``role: "emprise"`` — de quoi les styler
    différemment dans QGIS sans avoir à les séparer en deux couches.
    """
    entites: list[dict[str, Any]] = []
    for revue in revues:
        site = revue.site
        commun = {
            "id": site.id,
            "name": site.name,
            "category": site.category,
            "note": site.note,
            "reference_tile": site.reference_tile,
            "epsg": site.grid.epsg,
            "item_id": revue.item_id,
            "date": revue.date,
            "offset_m": round(revue.offset_m, 1),
        }
        anneau = [list(coin) for coin in revue.corners_wgs84]
        anneau.append(anneau[0])  # un anneau GeoJSON se referme sur son premier point
        entites.append(
            {
                "type": "Feature",
                "properties": {**commun, "role": "emprise"},
                "geometry": {"type": "Polygon", "coordinates": [anneau]},
            }
        )
        entites.append(
            {
                "type": "Feature",
                "properties": {**commun, "role": "vise"},
                "geometry": {"type": "Point", "coordinates": [site.lon, site.lat]},
            }
        )
    return {"type": "FeatureCollection", "features": entites}


def _lien_copernicus(revue: SiteReview, *, date: bool) -> str:
    """Lien vers le Copernicus Browser. ``date=False`` = position seule, qui ne dépend
    d'aucun identifiant de jeu de données (cf. la note sur ``_DATASET_L2A``)."""
    site = revue.site
    base = f"https://browser.dataspace.copernicus.eu/?zoom={_ZOOM}&lat={site.lat}&lng={site.lon}"
    if not date or revue.date is None:
        return base
    return (
        f"{base}&datasetId={_DATASET_L2A}&dateMode=SINGLE"
        f"&fromTime={revue.date}T00:00:00.000Z&toTime={revue.date}T23:59:59.999Z"
    )


def _lien_osm(site: Site) -> str:
    return (
        f"https://www.openstreetmap.org/?mlat={site.lat}&mlon={site.lon}"
        f"#map={_ZOOM}/{site.lat}/{site.lon}"
    )


def _ligne_html(revue: SiteReview) -> str:
    site = revue.site
    if revue.vignette_png is not None:
        donnees = base64.b64encode(revue.vignette_png).decode("ascii")
        vignette = f'<img src="data:image/png;base64,{donnees}" alt="chip {site.id}">'
    else:
        vignette = '<div class="vide">aucun chip</div>'
    date = revue.date or "—"
    item = revue.item_id or "—"
    date_url = _lien_copernicus(revue, date=True)
    brut_url = _lien_copernicus(revue, date=False)
    osm_url = _lien_osm(site)
    return f"""    <tr>
      <td class="vignette">{vignette}</td>
      <td>
        <div class="titre">{html.escape(site.id)} — {html.escape(site.name)}</div>
        <div class="note">{html.escape(site.note)}</div>
        <div class="meta">{site.lat}, {site.lon} · tuile {html.escape(site.reference_tile or "—")}
          · écart au centre {revue.offset_m:.0f} m</div>
        <div class="meta">{html.escape(item)} · {html.escape(date)}</div>
      </td>
      <td class="liens">
        <a href="{date_url}" target="_blank" rel="noopener">Copernicus — à la date du chip</a>
        <a href="{brut_url}" target="_blank" rel="noopener">Copernicus — position seule</a>
        <a href="{osm_url}" target="_blank" rel="noopener">OpenStreetMap</a>
      </td>
    </tr>"""


def _html(revues: list[SiteReview], *, planche: Path, geojson_path: Path) -> str:
    lignes = "\n".join(_ligne_html(r) for r in revues)
    sans_chip = sum(1 for r in revues if r.item_id is None)
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<title>Revue de centrage des sites — l0-03.H</title>
<style>
  body {{ font: 15px/1.5 system-ui, sans-serif; margin: 2rem auto; max-width: 1100px;
         color: #1a1a1a; background: #fff; }}
  h1 {{ font-size: 1.5rem; margin-bottom: .2rem; }}
  .chapeau {{ color: #444; margin-bottom: 1.5rem; }}
  .chapeau code {{ background: #f2f4f6; padding: .1em .3em; border-radius: 3px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  td {{ border-top: 1px solid #e3e6e8; padding: .8rem .6rem; vertical-align: top; }}
  td.vignette {{ width: {_VIGNETTE_PX + 12}px; }}
  img {{ width: {_VIGNETTE_PX}px; height: {_VIGNETTE_PX}px; display: block; border-radius: 4px; }}
  .vide {{ width: {_VIGNETTE_PX}px; height: {_VIGNETTE_PX}px; background: #aaa; color: #fff;
           display: flex; align-items: center; justify-content: center; border-radius: 4px; }}
  .titre {{ font-weight: 600; }}
  .note, .meta {{ color: #566; font-size: .88rem; }}
  td.liens {{ width: 250px; }}
  td.liens a {{ display: block; margin-bottom: .35rem; }}
  .avertissement {{ background: #fff8e1; border-left: 3px solid #e0a800; padding: .7rem 1rem;
                    margin: 1rem 0; }}
</style></head><body>
<h1>Revue de centrage des sites — fiche l0-03.H</h1>
<p class="chapeau">{len(revues)} sites · {sans_chip} sans chip · vignettes identiques à celles de
la planche (<code>{html.escape(str(planche))}</code>) · emprises et points visés dans
<code>{html.escape(str(geojson_path))}</code>.</p>

<div class="avertissement">
  <b>Ce que l'« écart au centre » dit — et ne dit pas.</b> C'est la distance entre le point
  déclaré dans <code>sites.yaml</code> et le centre de l'emprise réellement découpée, donc
  l'effet de l'accrochage à la grille de la tuile. Il vaut quelques centaines de mètres au
  plus, et c'est normal. Il ne dit <b>rien</b> sur la question de la fiche : le point déclaré
  vise-t-il la bonne infrastructure ? Cette réponse-là est dans les images.
</div>

<table>
{lignes}
</table>
</body></html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Aide à la revue de centrage (l0-03.H).")
    parser.add_argument("--sites-path", type=Path, default=DEFAULT_SITES_PATH)
    parser.add_argument("--settings-path", type=Path, default=DEFAULT_SETTINGS_PATH)
    args = parser.parse_args()

    settings = load_settings(args.settings_path)
    sites = load_sites(args.sites_path)
    data_root = Path(settings.data_root)
    sortie = data_root / "site-review"
    sortie.mkdir(parents=True, exist_ok=True)

    revues = [_review_site(site, settings, data_root) for site in sites]

    geojson_path = sortie / "sites.geojson"
    geojson_path.write_text(
        json.dumps(_geojson(revues), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    index_path = sortie / "index.html"
    index_path.write_text(
        _html(revues, planche=data_root / "contact-sheet-latest.png", geojson_path=geojson_path),
        encoding="utf-8",
    )

    pire = max(revues, key=lambda r: r.offset_m)
    sans_chip = sum(1 for r in revues if r.item_id is None)
    print(f"site-review : {len(revues)} sites, {sans_chip} sans chip")
    print(f"site-review : écart au centre le plus grand — {pire.site.id} à {pire.offset_m:.0f} m")
    print(f"site-review : {geojson_path}")
    print(f"site-review : {index_path}")


if __name__ == "__main__":
    main()
