"""core/embedding.py — spec d'entrée modèle et ordre normatif des bandes (l1-01.1).

Module pur : zéro I/O, zéro framework (pas de torch, pas de fichier). Fournit :

- ``BAND_ORDER_EMBED`` — l'ordre des bandes attendu par Clay (et TerraMind, sensor-
  agnostic), relevé dans ``configs/metadata.yaml`` du dépôt Clay
  (``sentinel-2-l2a.band_order``) par les revues v1/v3. Ce n'est PAS
  ``BAND_ORDER_10M + BAND_ORDER_20M`` du Lot 0 : ``nir`` est en 7e position ici, en 4e
  dans la concaténation du Lot 0 — un vecteur construit par position plutôt que par nom
  serait plausible et faux.
- ``EmbeddingSpec`` — spec gelée d'une entrée modèle.
- ``spec_hash`` — signature canonique d'idempotence, insensible au type numérique.
- ``validate_spec`` — vérifie la disponibilité des bandes et interdit ``tiling="tiles"``.
- ``to_reflectance`` — conversion physique DN -> réflectance, outil de contrôle/
  plausibilité uniquement : les modèles consomment du DN z-scoré, pas de la réflectance.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

# Ordre normatif des bandes pour l'embedding — source : configs/metadata.yaml du dépôt
# Clay, clé sentinel-2-l2a.band_order (relevé par les revues v1 et v3 ; non contre-
# vérifiable depuis cet environnement, le paquet claymodel installé ne packe pas ce YAML).
# Tout vecteur de stats (waves, mean, std) doit être construit par LOOKUP PAR NOM depuis
# ce tuple, jamais par position.
BAND_ORDER_EMBED: tuple[str, ...] = (
    "blue",
    "green",
    "red",
    "rededge1",
    "rededge2",
    "rededge3",
    "nir",
    "nir08",
    "swir16",
    "swir22",
)


class MissingBandError(ValueError):
    """Levée par ``validate_spec`` quand une bande de la spec est absente du jeu disponible."""


@dataclass(frozen=True)
class EmbeddingSpec:
    """Spec gelée d'une entrée modèle d'embedding.

    ``normalization`` ne porte que l'identifiant du schéma de normalisation (les stats
    elles-mêmes vivent dans l'adapter du modèle) ; il entre néanmoins dans le hash, car un
    changement de schéma invalide les embeddings déjà calculés.
    """

    bands: tuple[str, ...]
    size_px: int
    resolution_m: float
    tiling: Literal["whole_chip", "tiles"]
    normalization: str


def spec_hash(spec: EmbeddingSpec) -> str:
    """Signature canonique sha256 de ``spec``, insensible au type numérique.

    Reprend la forme du patron ``grid_hash`` (``adapters/manifests.py``) : chaîne
    canonique ``"|"``-séparée, valeurs numériques normalisées par ``int()`` avant hachage
    (``size_px=256`` et ``256.0`` produisent le MÊME hash), puis ``hashlib.sha256``.
    ``resolution_m`` peut être non entier (ex. 10.0 m) : normalisée séparément via un
    format flottant canonique plutôt que ``int()``, pour ne pas confondre 10 m et 10.5 m.
    """
    canonical = "|".join(
        [
            ",".join(spec.bands),
            str(int(spec.size_px)),
            f"{float(spec.resolution_m):.6f}",
            spec.tiling,
            spec.normalization,
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_spec(spec: EmbeddingSpec, available_bands: tuple[str, ...]) -> None:
    """Vérifie que ``spec`` est exploitable : bandes disponibles, tiling implémenté.

    Lève ``MissingBandError`` nommant la première bande manquante, ou
    ``NotImplementedError`` si ``spec.tiling == "tiles"`` (variante non implémentée dans
    ce lot — garde-fou posé sur le chemin réellement parcouru par le chargeur, l1-01.2).
    """
    available = set(available_bands)
    for band in spec.bands:
        if band not in available:
            raise MissingBandError(
                f"validate_spec : bande manquante '{band}' — disponibles : {sorted(available)}"
            )
    if spec.tiling == "tiles":
        raise NotImplementedError(
            "validate_spec : tiling='tiles' n'est pas implémenté dans ce lot "
            "(seul 'whole_chip' est supporté)"
        )


def to_reflectance(
    array: float,
    scale: float,
    offset: float,
    *,
    boa_offset_applied: bool,
) -> float:
    """Convertit un DN en réflectance de surface (outil de contrôle/plausibilité).

    ``reflectance = array * scale + offset`` sauf si ``boa_offset_applied`` est vrai,
    auquel cas l'offset BOA a déjà été appliqué en amont (traitement L2A) et ne doit pas
    l'être une seconde fois : ``reflectance = array * scale``. N'est PAS le chemin des
    modèles (Clay et TerraMind consomment du DN z-scoré avec leurs propres stats) ; sert
    uniquement aux bornes de plausibilité.
    """
    if boa_offset_applied:
        return array * scale
    return array * scale + offset
