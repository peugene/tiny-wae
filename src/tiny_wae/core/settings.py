"""core/settings.py — modèle typé des réglages applicatifs.

Zéro I/O, zéro framework : validation pure d'un ``Settings`` déjà construit. Le chargement
YAML + surcharges env vit dans ``adapters/config_io.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Les 9 clés d'assets source earth-search attendues (docs l0-01.1).
EXPECTED_ASSET_KEYS = (
    "blue",
    "green",
    "red",
    "nir",
    "rededge1",
    "rededge2",
    "rededge3",
    "nir08",
    "swir16",
    "swir22",
    "scl",
)


class SettingsValidationError(ValueError):
    """Erreur de validation des réglages — le message nomme le champ en cause."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Réglages applicatifs du pipeline tiny-wae (une instance = une configuration figée)."""

    stac_url: str
    stac_collection: str
    asset_keys: tuple[str, ...] = field(default=EXPECTED_ASSET_KEYS)
    cloud_pct_max: int = 30
    scene_cloud_max: int = 95
    invalid_pct_max: int = 1
    data_root: str = "./data"
    incremental_margin_days: int = 3
    http_retries: int = 3
    http_backoff_s: int = 2
    backfill_workers: int = 6
    chip_px_10m: int = 512
    chip_px_20m: int = 256

    def validate(self) -> None:
        """Vérifie les bornes de pourcentage et la présence d'au moins une clé d'asset."""
        for field_name, value in (
            ("cloud_pct_max", self.cloud_pct_max),
            ("scene_cloud_max", self.scene_cloud_max),
            ("invalid_pct_max", self.invalid_pct_max),
        ):
            if not (0 <= value <= 100):
                raise SettingsValidationError(f"settings.{field_name}={value} hors bornes [0, 100]")
        if not self.stac_url:
            raise SettingsValidationError("settings.stac_url : vide")
        if not self.stac_collection:
            raise SettingsValidationError("settings.stac_collection : vide")
        if not self.asset_keys:
            raise SettingsValidationError("settings.asset_keys : liste vide")
        for positive_field in (
            "incremental_margin_days",
            "http_retries",
            "http_backoff_s",
            "backfill_workers",
            "chip_px_10m",
            "chip_px_20m",
        ):
            value = getattr(self, positive_field)
            if value <= 0:
                raise SettingsValidationError(f"settings.{positive_field}={value} doit être > 0")
