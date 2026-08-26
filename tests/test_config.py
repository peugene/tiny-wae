"""Tests config : chargement de config/sites.yaml et config/settings.yaml (l0-01.1).

Couvre l'oracle de la fiche :
- O1 : les ids chargés = exactement {A01..A08, B01..B09, C01..C08}, répartition 8/9/8.
- O2 : 5 mutations d'erreur (id dupliqué, lat=95, catégorie inconnue, origine=13,
  lon=200) lèvent une erreur nommant le site et le champ en cause.
- O3 : une surcharge d'environnement (TINY_WAE_CLOUD_PCT_MAX) gagne sur la valeur YAML.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tiny_wae.adapters.config_io import ConfigError, load_settings, load_sites
from tiny_wae.core.sites import SiteValidationError

SITES_PATH = Path("config/sites.yaml")
SETTINGS_PATH = Path("config/settings.yaml")

# O1 — répartition littérale attendue (source unique : docs/lots/lot-0-sites.md §3).
EXPECTED_IDS_A = ["A01", "A02", "A03", "A04", "A05", "A06", "A07", "A08"]
EXPECTED_IDS_B = ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B09"]
EXPECTED_IDS_C = ["C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08"]
EXPECTED_IDS = EXPECTED_IDS_A + EXPECTED_IDS_B + EXPECTED_IDS_C


def test_load_sites_nominal_o1() -> None:
    """O1 : les 25 ids chargés correspondent exactement à la liste littérale, 8/9/8."""
    sites = load_sites(SITES_PATH)
    assert [s.id for s in sites] == EXPECTED_IDS
    assert len(EXPECTED_IDS_A) == 8
    assert len(EXPECTED_IDS_B) == 9
    assert len(EXPECTED_IDS_C) == 8

    by_category: dict[str, int] = {}
    for site in sites:
        by_category[site.category] = by_category.get(site.category, 0) + 1
    assert by_category == {
        "nuclear-construction": 8,
        "megaproject": 9,
        "stable-watch": 8,
    }


def test_load_sites_lat_lon_are_float() -> None:
    """Garde-fou signe moins Unicode : toutes les lat/lon chargées sont des float."""
    sites = load_sites(SITES_PATH)
    assert len(sites) == 25
    for site in sites:
        assert isinstance(site.lat, float)
        assert isinstance(site.lon, float)

    # Les 7 sites à coordonnée négative documentés dans l'ancrage (U+2212 dans la source).
    negative_ids = {"A02", "A04", "A08", "B06", "B07", "B08", "C04"}
    for site in sites:
        if site.id in negative_ids:
            assert site.lat < 0 or site.lon < 0, f"{site.id} : coordonnée négative attendue"


def _write_sites_yaml(tmp_path: Path, sites: list[dict[str, object]]) -> Path:
    """Écrit un sites.yaml minimal (un seul site) pour tester une mutation d'erreur."""
    path = tmp_path / "sites.yaml"
    path.write_text(yaml.safe_dump({"sites": sites}), encoding="utf-8")
    return path


def _base_site(**overrides: object) -> dict[str, object]:
    """Un site nominal valide, à faire muter par les tests d'erreur (O2)."""
    site = {
        "id": "X01",
        "name": "Site test",
        "lat": 43.0,
        "lon": 1.0,
        "category": "stable-watch",
        "note": "",
    }
    site.update(overrides)
    return site


def test_o2_mutation_duplicate_id(tmp_path: Path) -> None:
    """O2 (1/5) : id dupliqué → erreur nommant le site."""
    path = _write_sites_yaml(tmp_path, [_base_site(id="X01"), _base_site(id="X01")])
    with pytest.raises(SiteValidationError, match="X01"):
        load_sites(path)


def test_o2_mutation_lat_out_of_bounds(tmp_path: Path) -> None:
    """O2 (2/5) : lat=95 (hors [-90, 90]) → erreur nommant le site et le champ lat."""
    path = _write_sites_yaml(tmp_path, [_base_site(id="X02", lat=95)])
    with pytest.raises(SiteValidationError, match=r"X02.*lat"):
        load_sites(path)


def test_o2_mutation_unknown_category(tmp_path: Path) -> None:
    """O2 (3/5) : catégorie inconnue → erreur nommant le site et le champ category."""
    path = _write_sites_yaml(tmp_path, [_base_site(id="X03", category="bogus")])
    with pytest.raises(SiteValidationError, match=r"X03.*category"):
        load_sites(path)


def test_o2_mutation_grid_origin_not_multiple_of_20(tmp_path: Path) -> None:
    """O2 (4/5) : origine de grille = 13 (pas multiple de 20) → erreur nommant le site."""
    path = _write_sites_yaml(
        tmp_path,
        [_base_site(id="X04", grid={"epsg": 32631, "origin_x": 13, "origin_y": 0})],
    )
    with pytest.raises(SiteValidationError, match=r"X04.*origin_x"):
        load_sites(path)


def test_o2_mutation_lon_out_of_bounds(tmp_path: Path) -> None:
    """O2 (5/5) : lon=200 (hors [-180, 180]) → erreur nommant le site et le champ lon."""
    path = _write_sites_yaml(tmp_path, [_base_site(id="X05", lon=200)])
    with pytest.raises(SiteValidationError, match=r"X05.*lon"):
        load_sites(path)


def test_load_sites_missing_file_raises_config_error(tmp_path: Path) -> None:
    """Un chemin inexistant lève ConfigError plutôt qu'une exception non maîtrisée."""
    with pytest.raises(ConfigError):
        load_sites(tmp_path / "absent.yaml")


def test_load_settings_nominal() -> None:
    """Chargement nominal de config/settings.yaml : valeurs livrées, pas d'env."""
    settings = load_settings(SETTINGS_PATH, env={})
    assert settings.stac_collection == "sentinel-2-l2a"
    assert settings.cloud_pct_max == 30
    assert len(settings.asset_keys) == 11  # cf. config/settings.yaml (dont scl)
    assert "scl" in settings.asset_keys


def test_o3_env_overrides_yaml() -> None:
    """O3 : TINY_WAE_CLOUD_PCT_MAX=40 (env) gagne sur cloud_pct_max=30 (YAML)."""
    settings = load_settings(SETTINGS_PATH, env={"TINY_WAE_CLOUD_PCT_MAX": "40"})
    assert settings.cloud_pct_max == 40


def test_chip_nodata_pct_max_default() -> None:
    """chip_nodata_pct_max (garde nodata, arbitrage n°3) vaut 1 dans la config livrée."""
    settings = load_settings(SETTINGS_PATH, env={})
    assert settings.chip_nodata_pct_max == 1


def test_chip_nodata_pct_max_env_override() -> None:
    """TINY_WAE_CHIP_NODATA_PCT_MAX=5 (env) gagne sur chip_nodata_pct_max=1 (YAML)."""
    settings = load_settings(SETTINGS_PATH, env={"TINY_WAE_CHIP_NODATA_PCT_MAX": "5"})
    assert settings.chip_nodata_pct_max == 5


def test_chip_nodata_pct_max_out_of_bounds_rejected() -> None:
    """Une valeur hors bornes [0, 100] pour chip_nodata_pct_max est rejetée, champ nommé."""
    with pytest.raises(Exception, match="chip_nodata_pct_max"):
        load_settings(SETTINGS_PATH, env={"TINY_WAE_CHIP_NODATA_PCT_MAX": "150"})


def test_settings_invalid_percentage_rejected(tmp_path: Path) -> None:
    """Une surcharge env hors bornes [0, 100] est rejetée par la validation pure."""
    path = tmp_path / "settings.yaml"
    path.write_text(
        yaml.safe_dump({"stac_url": "https://x", "stac_collection": "c"}),
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="cloud_pct_max"):
        load_settings(path, env={"TINY_WAE_CLOUD_PCT_MAX": "150"})


# ── O5 (l1-00) — expansion de hf_home ───────────────────────────────────────────────────
# Un `~` non expansé n'est pas une erreur : c'est un répertoire littéralement nommé `~`
# créé dans le CWD. Chaque worktree se fabriquerait alors son propre cache et
# re-téléchargerait plusieurs Go — la propriété que l1-07/O4 doit garantir. Sans ce test,
# le défaut ne se voit qu'à travers l1-07, trop tard et au mauvais endroit.


def test_o5_hf_home_expanded_absolute_regardless_of_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O5 : hf_home expansé rend le MÊME chemin absolu, depuis deux CWD différents."""
    home = str(Path.home())
    repo_root = Path(__file__).resolve().parent.parent
    settings_path_abs = (repo_root / SETTINGS_PATH).resolve()

    monkeypatch.chdir(tmp_path)
    settings_from_tmp = load_settings(settings_path_abs, env={})

    monkeypatch.chdir(repo_root)
    settings_from_repo_root = load_settings(SETTINGS_PATH, env={})

    assert settings_from_tmp.hf_home == settings_from_repo_root.hf_home
    assert Path(settings_from_tmp.hf_home).is_absolute()
    assert not settings_from_tmp.hf_home.startswith("~")
    assert settings_from_tmp.hf_home.startswith(home)


def test_o5_hf_home_relative_after_expansion_is_a_named_configuration_error(
    tmp_path: Path,
) -> None:
    """Témoin négatif O5 : un hf_home relatif (pas de `~`) lève une erreur nommant la clé."""
    path = tmp_path / "settings.yaml"
    path.write_text(
        yaml.safe_dump({"stac_url": "https://x", "stac_collection": "c", "hf_home": "./models"}),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="hf_home"):
        load_settings(path, env={})


def test_o5_hf_home_env_override_is_also_expanded(tmp_path: Path) -> None:
    """La surcharge TINY_WAE_HF_HOME passe par la même expansion que le défaut YAML."""
    settings = load_settings(SETTINGS_PATH, env={"TINY_WAE_HF_HOME": "~/.cache/x"})
    assert Path(settings.hf_home).is_absolute()
    assert not settings.hf_home.startswith("~")


def test_embed_cloud_pct_max_and_embed_workers_defaults_and_bounds() -> None:
    """Les deux autres clés pré-posées (l1-00) : défauts livrés, puis bornes vérifiées."""
    settings = load_settings(SETTINGS_PATH, env={})
    assert settings.embed_cloud_pct_max == 10
    assert settings.embed_workers == 4

    with pytest.raises(Exception, match="embed_cloud_pct_max"):
        load_settings(SETTINGS_PATH, env={"TINY_WAE_EMBED_CLOUD_PCT_MAX": "150"})
    with pytest.raises(Exception, match="embed_workers"):
        load_settings(SETTINGS_PATH, env={"TINY_WAE_EMBED_WORKERS": "0"})
