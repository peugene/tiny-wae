"""adapters/contact_sheet.py — planche de contrôle RGB des derniers chips ingérés par site
(l0-03.6, artefact validé humainement par l0-03.H).

Le rendu et la composition vivent ICI (I/O : lecture des ``chip.tif`` déjà ingérés, écriture
du PNG) — décision d'ancrage n°2 de la fiche : la règle de couche prime sur le fait que la
fiche ne nomme que le CLI. ``cli/contact_sheet.py`` n'est que le wiring typer.

``build_contact_sheet`` est délibérément paramétrable (``columns``) plutôt qu'un CLI
monolithique figé à 25 sites : le mode ``--first-last`` (l0-04.2) étendra ce module sans le
réécrire — exception actée à l'invariant add-only (cf. fiche).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image, ImageDraw, ImageFont

from tiny_wae.adapters.manifests import Manifest, list_for_site
from tiny_wae.core.bands import BAND_ORDER_10M
from tiny_wae.core.sites import Site

# Indices RGB dans l'ordre gravé BAND_ORDER_10M = (blue, green, red, nir) — décision
# d'ancrage n°3 de la fiche : un rendu RGB lit les bandes dans l'ordre (red, green, blue),
# donc (2, 1, 0). Les inverser (BGR) donne une image bleutée plausible mais fausse.
_RGB_BAND_INDICES: tuple[int, int, int] = (
    BAND_ORDER_10M.index("red"),
    BAND_ORDER_10M.index("green"),
    BAND_ORDER_10M.index("blue"),
)

# Bornes de l'étirement percentile (décision d'ancrage n°3).
STRETCH_LOW_PERCENTILE = 2.0
STRETCH_HIGH_PERCENTILE = 98.0

# Géométrie de la planche (une imagette carrée + un bandeau d'étiquette en dessous).
CELL_PX = 200
LABEL_HEIGHT_PX = 34
# Taille des libellés, en points (n'a d'effet qu'avec une police TrueType).
LABEL_FONT_PX = 12
GRID_COLUMNS = 5

_GRAY_CELL_COLOR = (170, 170, 170)
_LABEL_BG_COLOR = (20, 20, 20)
_LABEL_FG_COLOR = (255, 255, 255)
_NO_CHIP_LABEL = "aucun chip"


def stretch_percentile(
    band: np.ndarray,
    *,
    low: float = STRETCH_LOW_PERCENTILE,
    high: float = STRETCH_HIGH_PERCENTILE,
) -> np.ndarray:
    """Étire linéairement une bande numérique vers ``uint8`` [0, 255] sur les percentiles
    ``[low, high]`` (sature au-delà). Une bande constante (``hi <= lo``) rend un aplat noir
    plutôt qu'une division par zéro — cas dégénéré, pas d'exception pour un rendu de
    contrôle visuel."""
    lo, hi = np.percentile(band, [low, high])
    if hi <= lo:
        return np.zeros(band.shape, dtype=np.uint8)
    clipped = np.clip(band, lo, hi)
    stretched: np.ndarray = (((clipped - lo) / (hi - lo)) * 255.0).astype(np.uint8)
    return stretched


def render_rgb(chip_path: Path) -> Image.Image:
    """Lit ``chip.tif`` (4 bandes blue/green/red/nir @ 10 m, uint16) et rend une image PIL
    RGB : bandes red/green/blue étirées percentile 2-98 chacune (décision d'ancrage n°3)."""
    with rasterio.open(chip_path) as src:
        array = src.read()  # (4, H, W)
    red_idx, green_idx, blue_idx = _RGB_BAND_INDICES
    red = stretch_percentile(array[red_idx])
    green = stretch_percentile(array[green_idx])
    blue = stretch_percentile(array[blue_idx])
    rgb = np.stack([red, green, blue], axis=-1)
    return Image.fromarray(rgb, mode="RGB")


def latest_ingested_manifest(data_root: Path, site_id: str) -> Manifest | None:
    """Renvoie le manifeste ``ingested`` le plus récent d'un site (tri sur ``datetime``
    ISO 8601, comparable lexicalement), ou ``None`` si le site n'a aucun chip ingéré."""
    ingested = [m for m in list_for_site(data_root, site_id) if m.status == "ingested"]
    if not ingested:
        return None
    return max(ingested, key=lambda m: m.datetime)


@dataclass(frozen=True, slots=True)
class SheetCell:
    """Une cellule de la planche : soit une imagette rendue, soit une case grise motivée
    (``image is None``) — jamais les deux, jamais une imagette cassée en silence."""

    site_id: str
    label_lines: tuple[str, ...]
    image: Image.Image | None


def _build_cell(site: Site, data_root: Path) -> SheetCell:
    """Construit la cellule d'un site : imagette rendue si un chip ``ingested`` existe,
    sinon case grise labellisée « aucun chip » (décision d'ancrage n°3)."""
    manifest = latest_ingested_manifest(data_root, site.id)
    if manifest is None:
        return SheetCell(
            site_id=site.id,
            label_lines=(f"{site.id} - {site.name}", _NO_CHIP_LABEL),
            image=None,
        )
    chip_path = Path(data_root) / site.id / manifest.item_id / "chip.tif"
    image = render_rgb(chip_path)
    date_label = manifest.datetime.split("T", 1)[0]
    return SheetCell(
        site_id=site.id,
        label_lines=(f"{site.id} - {site.name}", date_label),
        image=image,
    )


# Polices TrueType cherchées, dans l'ordre, pour les libellés (aucune n'est une dépendance :
# on retombe proprement sur la police intégrée si aucune n'est présente).
_FONT_CANDIDATES = (
    "DejaVuSans.ttf",  # linux (fonts-dejavu-core)
    "LiberationSans-Regular.ttf",
    "NotoSans-Regular.ttf",
    "arial.ttf",  # windows
    "Arial.ttf",
)


def _load_font(
    size: int = LABEL_FONT_PX,
) -> tuple[ImageFont.ImageFont | ImageFont.FreeTypeFont, bool]:
    """Police des libellés, et si elle sait rendre les caractères accentués.

    ⚠ Mesuré sur la première planche réelle des 25 sites (22/08/2026) : la police intégrée
    de Pillow (``load_default``) rend un **tofu** — le carré du glyphe manquant — pour
    ``é``, ``ê``, ``ï`` comme pour le tiret cadratin. « Aéroport King Salman » s'y lisait
    « A□roport ». Le piège est qu'un tofu ALLUME des pixels : compter les pixels non nuls
    ne prouve pas que le bon glyphe a été tracé, il faut regarder l'image.

    Renvoie ``(police, accents_ok)``. Quand aucune TrueType n'est trouvée, l'appelant
    translittère les libellés en ASCII (``_to_ascii``) : mieux vaut « Aeroport » lisible
    qu'un carré vide, et le rendu reste **déterministe** d'une plateforme à l'autre.
    """
    for candidate in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size), True
        except OSError:
            continue
    return ImageFont.load_default(), False


def _to_ascii(text: str) -> str:
    """Translittère en ASCII (``Forêt`` -> ``Foret``) — filet quand la police n'a pas les
    glyphes accentués. Décompose puis retire les diacritiques, sans dépendance externe."""
    decomposed = unicodedata.normalize("NFKD", text)
    return decomposed.encode("ascii", "ignore").decode("ascii")


def _paste_cell(
    sheet: Image.Image, draw: ImageDraw.ImageDraw, cell: SheetCell, *, box: tuple[int, int]
) -> None:
    """Peint une cellule (imagette redimensionnée ou aplat gris) + son bandeau
    d'étiquette dans ``sheet``, au coin haut-gauche ``box``."""
    x0, y0 = box
    if cell.image is not None:
        thumb = cell.image.resize((CELL_PX, CELL_PX))
        sheet.paste(thumb, (x0, y0))
    else:
        draw.rectangle([x0, y0, x0 + CELL_PX, y0 + CELL_PX], fill=_GRAY_CELL_COLOR)

    label_y0 = y0 + CELL_PX
    draw.rectangle([x0, label_y0, x0 + CELL_PX, label_y0 + LABEL_HEIGHT_PX], fill=_LABEL_BG_COLOR)
    font, accents_ok = _load_font()
    for i, line in enumerate(cell.label_lines):
        text = line if accents_ok else _to_ascii(line)
        draw.text((x0 + 4, label_y0 + 2 + i * 12), text, fill=_LABEL_FG_COLOR, font=font)


def build_contact_sheet(
    sites: Sequence[Site], data_root: Path, *, columns: int = GRID_COLUMNS
) -> Image.Image:
    """Compose la planche : une cellule par site, dans l'ORDRE de ``sites`` — imagette RGB
    étirée si un chip ``ingested`` existe, case grise « aucun chip » sinon.

    Le nombre de lignes suit ``ceil(len(sites) / columns)`` : la fiche fixe une grille 5×5
    pour les 25 sites de production, mais la fonction reste paramétrable (sous-corpus de
    test, ``--first-last`` à venir en l0-04.2).
    """
    if not sites:
        raise ValueError("build_contact_sheet : la liste de sites est vide")
    rows = -(-len(sites) // columns)  # division entière arrondie au supérieur, sans math.ceil
    cell_height = CELL_PX + LABEL_HEIGHT_PX
    sheet = Image.new("RGB", (columns * CELL_PX, rows * cell_height), color=(0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    for index, site in enumerate(sites):
        cell = _build_cell(site, data_root)
        col, row = index % columns, index // columns
        _paste_cell(sheet, draw, cell, box=(col * CELL_PX, row * cell_height))
    return sheet


def write_contact_sheet(
    sites: Sequence[Site], data_root: Path, out_path: Path, *, columns: int = GRID_COLUMNS
) -> Path:
    """Compose la planche puis l'écrit en PNG à ``out_path`` (répertoire créé si besoin)."""
    sheet = build_contact_sheet(sites, data_root, columns=columns)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, format="PNG")
    return out_path
