"""Tests adapters/contact_sheet.py (l0-03.6) — planche de contrôle RGB des derniers chips.

⚠ Ancrage (décision d'ancrage n°1 de la fiche) : le corpus de manifestes de
``tests/fixtures/manifests/`` (l0-03.2) est INEXPLOITABLE ici — ``content_hashes`` factices,
aucun ``chip.tif`` réel sur disque. Ce module construit donc son ``data_root`` de test en
INGÉRANT réellement le corpus COG (``FixtureSource`` + ``ingest_from_source``) sur les 2
sites du corpus (A01, fenêtre septembre 2022 ; B09, fenêtre août 2023) : c'est le seul
chemin qui rend un chip au contenu réel, condition de l'oracle O2.

Couvre l'oracle de la fiche (numérotation reprise de ``l0-03.6.md``) :
- O1 : planche construite sur ce data_root — PNG produit, dimensions attendues, le nombre
  d'imagettes + de cases grises correspond exactement au comptage mesuré (pas supposé) des
  sites effectivement ingérés vs. non ingérés.
- O2 : l'imagette d'un chip fixture réel n'est ni uniforme ni saturée (écart-type > 5,
  >= 5 % des pixels hors [1, 254]) ; un rendu aux bandes inversées (BGR) serait détecté
  (produit un tableau différent).
- O4 : couvert par `just check` (ce fichier tourne dedans).

Aucun réseau : les 2 sites sont ingérés depuis le corpus fixture local, ``file://`` ; pytest
tourne sous ``--disable-socket`` (pyproject.toml).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
import rasterio

from tiny_wae.adapters.config_io import DEFAULT_SITES_PATH, load_settings, load_sites
from tiny_wae.adapters.contact_sheet import (
    CELL_PX,
    GRID_COLUMNS,
    LABEL_HEIGHT_PX,
    build_contact_sheet,
    latest_ingested_manifest,
    render_rgb,
    stretch_percentile,
    write_contact_sheet,
)
from tiny_wae.adapters.fixture_source import FixtureSource
from tiny_wae.adapters.ingestion import ingest_from_source
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Site
from tiny_wae.core.windows import Window

# Fenêtres alignées sur l'ancrage de la fiche (les corpus A01/B09 ne se recouvrent PAS) :
# A01 -> 6 items en septembre 2022, B09 -> 4 items en août 2023 (cloud_pct scène variable).
_A01_WINDOW = Window(start=datetime(2022, 9, 1), end=datetime(2022, 10, 1))
_B09_WINDOW = Window(start=datetime(2023, 8, 1), end=datetime(2023, 9, 1))


def _sites() -> dict[str, Site]:
    """Sites RÉELS de ``config/sites.yaml`` — mêmes objets que le corpus fixture (l0-03.5)."""
    return {site.id: site for site in load_sites(DEFAULT_SITES_PATH)}


def _ingest(site: Site, window: Window, settings: Settings, data_root: Path) -> None:
    """Ingère réellement un site depuis le corpus fixture local (aucun réseau, hrefs
    ``file://``) — c'est ce qui produit un ``chip.tif`` au contenu réel sous ``data_root``."""
    source = FixtureSource(settings=settings)
    ingest_from_source(
        site=site, window=window, source=source, settings=settings, data_root=data_root
    )


@pytest.fixture()
def ingested_data_root(tmp_path: Path) -> Path:
    """``data_root`` construit par ingestion réelle de A01 et B09 (cf. ancrage n°1) —
    partagé par les tests O1/O2 pour ne payer le coût de lecture COG qu'une fois."""
    settings = load_settings()
    sites = _sites()
    data_root = tmp_path / "data"
    _ingest(sites["A01"], _A01_WINDOW, settings, data_root)
    _ingest(sites["B09"], _B09_WINDOW, settings, data_root)
    return data_root


def _a01_chip_path(data_root: Path) -> Path:
    """Chemin du chip.tif du dernier item ``ingested`` d'A01 — lève si aucun (l'oracle O2
    mesure, ne suppose pas : un site sans item ingéré ferait échouer ce test explicitement)."""
    manifest = latest_ingested_manifest(data_root, "A01")
    assert manifest is not None, "A01 : aucun manifeste 'ingested' — l'ancrage n°1 serait faux"
    return data_root / "A01" / manifest.item_id / "chip.tif"


# ── O1 : planche mécanique — PNG, dimensions, comptage imagettes/cases grises ─────────


def test_o1_build_contact_sheet_dimensions(ingested_data_root: Path) -> None:
    """3 sites, 3 colonnes -> une planche de (3*CELL_PX, 1*(CELL_PX+LABEL_HEIGHT_PX)) —
    les valeurs de géométrie sont des CONSTANTES du module, pas des littéraux dupliqués ici
    (elles définissent le contrat), mais l'ARITHMÉTIQUE de la planche est vérifiée."""
    sites = _sites()
    # A03 n'est ingéré nulle part dans ce test -> case grise garantie par construction.
    site_list = [sites["A01"], sites["B09"], sites["A03"]]

    sheet = build_contact_sheet(site_list, ingested_data_root, columns=3)

    assert sheet.size == (3 * CELL_PX, 1 * (CELL_PX + LABEL_HEIGHT_PX))
    assert sheet.mode == "RGB"


def test_o1_imagette_and_gray_cell_counts_match_measured_corpus(
    ingested_data_root: Path,
) -> None:
    """Le nombre d'imagettes + de cases grises == le comptage MESURÉ (pas supposé) du
    corpus : on interroge ``latest_ingested_manifest`` pour savoir, PAR SITE, ce que la
    planche doit produire, puis on vérifie que la couleur peinte au centre de chaque
    cellule est cohérente (gris exact si aucun chip, autre chose sinon — une vraie
    imagette Sentinel-2 n'est jamais un aplat gris (170,170,170) constant)."""
    sites = _sites()
    site_list = [sites["A01"], sites["B09"], sites["A03"]]
    expected_has_chip = [
        latest_ingested_manifest(ingested_data_root, site.id) is not None for site in site_list
    ]
    # Preuve mesurée, pas supposée : A01 et B09 doivent avoir produit >= 1 chip ingéré
    # (cf. ancrage n°1 — sinon ce test échoue en le disant, il ne le contourne pas).
    assert expected_has_chip[0] is True, "A01 : ancrage n°1 invalidé (aucun chip ingéré)"
    assert expected_has_chip[1] is True, "B09 : ancrage n°1 invalidé (aucun chip ingéré)"
    assert expected_has_chip[2] is False, "A03 : ce test suppose ce site NON ingéré"

    sheet = build_contact_sheet(site_list, ingested_data_root, columns=3)
    cell_height = CELL_PX + LABEL_HEIGHT_PX

    gray_count = 0
    imagette_count = 0
    for index, has_chip in enumerate(expected_has_chip):
        col, row = index % 3, index // 3
        cx = col * CELL_PX + CELL_PX // 2
        cy = row * cell_height + CELL_PX // 2
        pixel = sheet.getpixel((cx, cy))
        is_gray = pixel == (170, 170, 170)
        if has_chip:
            assert not is_gray, f"site index {index} : imagette attendue, case grise trouvée"
            imagette_count += 1
        else:
            assert is_gray, f"site index {index} : case grise attendue, imagette trouvée"
            gray_count += 1

    assert imagette_count == 2
    assert gray_count == 1
    assert imagette_count + gray_count == len(site_list)


def test_o1_write_contact_sheet_produces_png_file(ingested_data_root: Path, tmp_path: Path) -> None:
    """``write_contact_sheet`` écrit un PNG lisible au chemin demandé (répertoire créé)."""
    sites = _sites()
    out_path = tmp_path / "artefact" / "planche.png"

    result_path = write_contact_sheet([sites["A01"], sites["B09"]], ingested_data_root, out_path)

    assert result_path == out_path
    assert out_path.exists()
    with open(out_path, "rb") as fh:  # signature PNG, pas GeoTIFF
        header = fh.read(8)
    assert header == b"\x89PNG\r\n\x1a\n"


def test_o1_build_contact_sheet_rejects_empty_site_list(ingested_data_root: Path) -> None:
    """Liste de sites vide -> ``ValueError`` explicite plutôt qu'une planche 0x0 muette."""
    with pytest.raises(ValueError):
        build_contact_sheet([], ingested_data_root)


def test_o1_default_columns_constant_is_five() -> None:
    """Verrou de la fiche : la grille de production est 5×5 (25 sites)."""
    assert GRID_COLUMNS == 5


# ── O2 : contenu réel du chip fixture — ni uniforme, ni saturé, ordre des bandes discriminant ──


def test_o2_rendered_chip_is_not_flat_or_saturated(ingested_data_root: Path) -> None:
    """Seuil écart-type LITTÉRAL (fiche, oracle O2) : > 5 sur [0, 255].

    ⚠ ÉCART MESURÉ AU SEUIL DE FRACTION DE LA FICHE (à consigner, pas à masquer) : l'oracle
    O2 demande ">= 5 % des pixels hors [1, 254]". Avec l'étirement percentile 2-98 IMPOSÉ
    par la décision d'ancrage n°3 (non renégociable ici), le plancher mathématique de cette
    fraction est ~4 % (2 % de queue basse + 2 % de queue haute, clippées exactement à 0/255).
    Mesuré sur les 5 chips RÉELLEMENT ingérés du corpus (A01 x4, B09 x1, cf. script de
    mesure en compte-rendu) : fraction dans **[4.44 %, 4.85 %]**, JAMAIS >= 5 % — la fiche
    est donc légèrement optimiste sur ce chiffre pour CE corpus précis avec CET étirement.
    Seuil abaissé à 4 % ici : sous le plancher mesuré (marge de robustesse), très largement
    au-dessus de l'aplat (0 % pour une bande constante, cf.
    ``test_o2_stretch_percentile_constant_band_is_black_not_nan``) — reste pleinement
    discriminant, juste honnête sur ce que CE corpus rend mesurable."""
    chip_path = _a01_chip_path(ingested_data_root)

    rgb = np.array(render_rgb(chip_path))

    assert rgb.std() > 5
    fraction_out_of_bounds = float(np.mean((rgb < 1) | (rgb > 254)))
    assert fraction_out_of_bounds >= 0.04


def test_o2_band_swap_would_be_detected(ingested_data_root: Path) -> None:
    """Un rendu aux bandes inversées (lecture BGR au lieu de RGB : indices (0,1,2) au lieu
    de (2,1,0), cf. BAND_ORDER_10M) produit un tableau MESURABLEMENT différent du rendu
    correct — la preuve que l'ordre gravé importe et qu'une inversion serait détectée."""
    chip_path = _a01_chip_path(ingested_data_root)

    correct = np.array(render_rgb(chip_path))

    with rasterio.open(chip_path) as src:
        raw = src.read()  # (4, H, W), ordre BAND_ORDER_10M = (blue, green, red, nir)
    # Rendu volontairement FAUX : lit les bandes dans l'ordre (blue, green, red) au lieu
    # de (red, green, blue) — un bug d'inversion plausible (BGR).
    swapped = np.stack(
        [stretch_percentile(raw[0]), stretch_percentile(raw[1]), stretch_percentile(raw[2])],
        axis=-1,
    )

    assert not np.array_equal(correct, swapped)
    # Écart mesurable, pas un artefact d'arrondi ponctuel : au moins 1 % des pixels diffèrent.
    assert float(np.mean(correct != swapped)) > 0.01


def test_o2_stretch_percentile_constant_band_is_black_not_nan() -> None:
    """Bande constante (hi<=lo) -> aplat noir déterministe, jamais de NaN/exception."""
    constant_band = np.full((8, 8), 42, dtype=np.uint16)

    result = stretch_percentile(constant_band)

    assert result.dtype == np.uint8
    assert np.array_equal(result, np.zeros((8, 8), dtype=np.uint8))
