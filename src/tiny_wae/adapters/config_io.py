"""adapters/config_io.py — chargement YAML + env vers les modèles typés.

Seul endroit du projet qui lit `config/*.yaml` et l'environnement : c'est le "parse aux
frontières" — tout le reste du code manipule des ``Settings``/``Site`` déjà typés et
validés, jamais des dicts YAML bruts.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import fields
from pathlib import Path
from typing import Any

import yaml

from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Grid, Site, validate_sites

# Préfixe commun à toutes les variables de surcharge (une variable par clé de Settings).
ENV_PREFIX = "TINY_WAE_"

DEFAULT_SITES_PATH = Path("config/sites.yaml")
DEFAULT_SETTINGS_PATH = Path("config/settings.yaml")

# Champs de Settings dont le type est une liste de chaînes (surcharge env = CSV).
_LIST_FIELDS = frozenset({"asset_keys"})
# Champs de Settings dont le type est entier.
_INT_FIELDS = frozenset(
    {
        "cloud_pct_max",
        "scene_cloud_max",
        "invalid_pct_max",
        "chip_nodata_pct_max",
        "incremental_margin_days",
        "http_retries",
        "http_backoff_s",
        "backfill_workers",
        "chip_px_10m",
        "chip_px_20m",
    }
)


class ConfigError(ValueError):
    """Erreur de chargement/parse de configuration (YAML malformé, champ manquant…)."""


def _coerce_env_value(field_name: str, raw: str) -> Any:
    """Convertit la chaîne d'une variable d'env vers le type attendu du champ Settings."""
    if field_name in _INT_FIELDS:
        try:
            return int(raw)
        except ValueError as exc:
            raise ConfigError(
                f"env {ENV_PREFIX}{field_name.upper()}={raw!r} : entier attendu"
            ) from exc
    if field_name in _LIST_FIELDS:
        return tuple(item.strip() for item in raw.split(",") if item.strip())
    return raw


def load_settings(
    path: Path = DEFAULT_SETTINGS_PATH,
    env: Mapping[str, str] | None = None,
) -> Settings:
    """Charge Settings depuis `path` (YAML), puis applique les surcharges TINY_WAE_* de `env`.

    Priorité : variable d'environnement > valeur YAML > défaut du dataclass.
    """
    env = os.environ if env is None else env

    raw: dict[str, Any] = {}
    if path.exists():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ConfigError(f"{path} : racine YAML doit être un mapping")
        raw = loaded

    if "asset_keys" in raw and raw["asset_keys"] is not None:
        raw["asset_keys"] = tuple(raw["asset_keys"])

    known_fields = {f.name for f in fields(Settings)}
    for field_name in known_fields:
        env_key = f"{ENV_PREFIX}{field_name.upper()}"
        if env_key in env:
            raw[field_name] = _coerce_env_value(field_name, env[env_key])

    unknown = set(raw) - known_fields
    if unknown:
        raise ConfigError(f"{path} : champ(s) inconnu(s) {sorted(unknown)}")

    try:
        settings = Settings(**raw)
    except TypeError as exc:
        raise ConfigError(f"{path} : {exc}") from exc

    settings.validate()
    return settings


def _grid_from_dict(data: dict[str, Any] | None) -> Grid:
    """Construit un Grid depuis le sous-mapping YAML `grid` (peut être vide/absent)."""
    if not data:
        return Grid()
    return Grid(
        epsg=data.get("epsg"),
        origin_x=data.get("origin_x"),
        origin_y=data.get("origin_y"),
    )


def _site_from_dict(data: dict[str, Any]) -> Site:
    """Construit un Site depuis une entrée YAML `sites[]`, avec lat/lon forcés en float."""
    try:
        site_id = data["id"]
    except KeyError as exc:
        raise ConfigError(f"site sans champ 'id' : {data!r}") from exc

    try:
        return Site(
            id=site_id,
            name=data["name"],
            lat=float(data["lat"]),
            lon=float(data["lon"]),
            category=data["category"],
            note=data.get("note", ""),
            reference_tile=data.get("reference_tile"),
            grid=_grid_from_dict(data.get("grid")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigError(f"site {site_id} : champ invalide ou manquant ({exc})") from exc


def load_sites(path: Path = DEFAULT_SITES_PATH) -> list[Site]:
    """Charge et valide la liste des sites depuis `path` (YAML). Lève ConfigError sinon."""
    if not path.exists():
        raise ConfigError(f"{path} : fichier introuvable")

    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict) or "sites" not in loaded:
        raise ConfigError(f"{path} : racine YAML doit contenir une clé 'sites'")

    entries = loaded["sites"]
    if not isinstance(entries, list):
        raise ConfigError(f"{path} : 'sites' doit être une liste")

    sites = [_site_from_dict(entry) for entry in entries]
    validate_sites(sites)
    return sites
