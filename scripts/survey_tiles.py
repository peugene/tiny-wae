#!/usr/bin/env python3
"""survey_tiles.py — relevé RÉSEAU des tuiles de référence + calcul des grilles (l0-01.3).

Interroge earth-search pour chaque site de `config/sites.yaml` :
    1. `/aggregate?…&aggregations=grid_code_frequency` sur la bbox du chip -> tuiles
       candidates (codes MGRS + fréquence d'items).
    2. Pour chaque candidate, `/search?limit=1&query={grid:code}` -> lit `proj:transform`
       (origine ULX/ULY) et `proj:shape` de l'asset `blue` (mesure, pas de convention
       recalculée — cf. ancrage de la fiche).
    3. Règle D-c (décision Philippe 21/08, core.tiles.choose_reference_tile) : la tuile de
       marge géométrique maximale chip↔bord ; en cas d'égalité, la plus fournie en items.
    4. `grid.origin_x/origin_y` : coin haut-gauche du chip 512×512@10 m centré sur
       (lat, lon), arrondi au multiple de 20 m inférieur (core.tiles.chip_origin).

Écrit `config/sites.yaml` par ÉDITION TEXTUELLE CIBLÉE (pas de yaml.safe_dump du document
entier — le fichier porte 11 lignes de commentaires, dont un avertissement critique sur le
signe moins Unicode, qu'un dump effacerait) et `scripts/survey_tiles_report.json` (trace de
la donnée : par site, buckets bruts, tuile choisie, marge calculée).

Rejouable et ciblable : `just survey-tiles` (tous les sites) ou
`just survey-tiles --sites A01,C07` (re-passe ciblée, ex. après correction de coordonnées).

Codes de sortie (`cli.exit_codes`, réutilisés — pas redéfinis) :
    0 OK · 1 échec métier (site sans tuile candidate) · 3 réseau injoignable (sites.yaml
    strictement inchangé).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from tiny_wae.adapters.config_io import (
    DEFAULT_SETTINGS_PATH,
    DEFAULT_SITES_PATH,
    ConfigError,
    load_settings,
    load_sites,
)
from tiny_wae.cli import exit_codes
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import SiteValidationError
from tiny_wae.core.tiles import (
    TILE_SIDE_M,
    TileCandidate,
    TileGeometryError,
    candidate_margin_m,
    chip_origin,
    choose_reference_tile,
    mgrs_zone_epsg,
    wgs84_survey_bbox,
)

REPORT_PATH = Path("scripts/survey_tiles_report.json")
DATETIME_RANGE_MONTHS = 48
HTTP_TIMEOUT_S = 30.0


class SurveyNetworkError(RuntimeError):
    """Amont réseau injoignable — mappé sur exit_codes.INCONCLUSIVE (O3)."""


class SurveyDataError(RuntimeError):
    """Site sans tuile candidate ou données incohérentes — mappé sur exit_codes.FAILURE."""


@dataclass(frozen=True, slots=True)
class SiteSurveyResult:
    """Résultat du relevé pour un site : tuile choisie, grille, et trace des candidates."""

    site_id: str
    reference_tile: str
    epsg: int
    origin_x: float
    origin_y: float
    candidates: list[dict[str, Any]]


def _datetime_range(months: int = DATETIME_RANGE_MONTHS) -> str:
    """Fenêtre temporelle RFC3339 des `months` derniers mois (fixe la borne haute à
    aujourd'hui, en UTC) — earth-search exige un intervalle explicite, pas de raccourci."""
    now = datetime.now(UTC)
    start_year = now.year - months // 12
    start_month = now.month - months % 12
    if start_month <= 0:
        start_month += 12
        start_year -= 1
    start = now.replace(
        year=start_year, month=start_month, day=1, hour=0, minute=0, second=0, microsecond=0
    )
    return f"{start.isoformat().replace('+00:00', 'Z')}/{now.isoformat().replace('+00:00', 'Z')}"


def _bbox_param(bbox: tuple[float, float, float, float]) -> str:
    """Formate une bbox (minlon, minlat, maxlon, maxlat) pour les query params earth-search."""
    return ",".join(f"{v:.6f}" for v in bbox)


def _fetch_grid_code_frequency(
    client: httpx.Client, stac_url: str, collection: str, bbox: tuple[float, float, float, float]
) -> list[tuple[str, int]]:
    """Interroge `/aggregate` -> liste (code MGRS, fréquence) triée par fréquence décroissante."""
    params = {
        "collections": collection,
        "bbox": _bbox_param(bbox),
        "datetime": _datetime_range(),
        "aggregations": "grid_code_frequency",
    }
    try:
        resp = client.get(f"{stac_url}/aggregate", params=params, timeout=HTTP_TIMEOUT_S)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise SurveyNetworkError(f"/aggregate injoignable : {exc}") from exc
    data = resp.json()
    buckets: list[tuple[str, int]] = []
    for agg in data.get("aggregations", []):
        if agg.get("name") != "grid_code_frequency":
            continue
        for bucket in agg.get("buckets", []):
            buckets.append((bucket["key"], int(bucket["frequency"])))
    buckets.sort(key=lambda item: item[1], reverse=True)
    return buckets


def _fetch_tile_transform(
    client: httpx.Client, stac_url: str, collection: str, grid_code: str, asset_key: str = "blue"
) -> tuple[float, float]:
    """`/search?limit=1` filtré sur `grid:code` -> (ULX, ULY) lus dans `proj:transform` de
    l'asset `blue` — mesure, jamais une convention recalculée (cf. ancrage de la fiche)."""
    params: dict[str, Any] = {
        "collections": collection,
        "limit": 1,
        "query": json.dumps({"grid:code": {"eq": grid_code}}),
    }
    try:
        resp = client.get(f"{stac_url}/search", params=params, timeout=HTTP_TIMEOUT_S)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise SurveyNetworkError(f"/search injoignable ({grid_code}) : {exc}") from exc
    data = resp.json()
    features = data.get("features", [])
    if not features:
        raise SurveyDataError(f"{grid_code} : aucun item trouvé via /search")
    asset = features[0].get("assets", {}).get(asset_key)
    if not asset or "proj:transform" not in asset:
        raise SurveyDataError(f"{grid_code} : proj:transform absent de l'asset {asset_key!r}")
    transform = asset["proj:transform"]
    # affine [a, b, ULX, d, e, ULY, ...] — GDAL/STAC : indices 2 et 5.
    return float(transform[2]), float(transform[5])


def survey_site(
    client: httpx.Client, site_id: str, lat: float, lon: float, settings: Settings
) -> SiteSurveyResult:
    """Relevé complet d'UN site : candidates -> emprises mesurées -> choix D-c -> grille."""
    span_m = float(settings.chip_px_10m * 10)
    bbox = wgs84_survey_bbox(lat, lon, span_m)
    buckets = _fetch_grid_code_frequency(client, settings.stac_url, settings.stac_collection, bbox)
    if not buckets:
        raise SurveyDataError(f"site {site_id} : aucune tuile candidate (/aggregate vide)")

    candidates: list[TileCandidate] = []
    trace: list[dict[str, Any]] = []
    for grid_code, item_count in buckets:
        epsg = mgrs_zone_epsg(grid_code)
        origin_x, origin_y = _fetch_tile_transform(
            client, settings.stac_url, settings.stac_collection, grid_code
        )
        margin = candidate_margin_m(lat, lon, span_m, epsg, origin_x, origin_y, TILE_SIDE_M)
        candidates.append(TileCandidate(grid_code, epsg, origin_x, origin_y, margin, item_count))
        trace.append(
            {
                "grid_code": grid_code,
                "item_count": item_count,
                "epsg": epsg,
                "origin_x": origin_x,
                "origin_y": origin_y,
                "margin_m": margin,
            }
        )

    chosen = choose_reference_tile(candidates)
    origin_x, origin_y = chip_origin(lat, lon, chosen.epsg, span_m)
    short_code = chosen.code.removeprefix("MGRS-")
    return SiteSurveyResult(
        site_id=site_id,
        reference_tile=short_code,
        epsg=chosen.epsg,
        origin_x=origin_x,
        origin_y=origin_y,
        candidates=trace,
    )


def _apply_results(raw_text: str, results: list[SiteSurveyResult]) -> str:
    """Édition TEXTUELLE ciblée de `sites.yaml` : remplace `reference_tile:`/`grid:` du
    bloc de chaque site relevé, préserve tout le reste caractère pour caractère (commentaires
    de tête, mise en page, sites non relevés) — jamais de `yaml.safe_dump` du document entier."""
    lines = raw_text.splitlines(keepends=True)
    by_id = {r.site_id: r for r in results}

    output: list[str] = []
    current_site: str | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("- id:"):
            current_site = stripped.split(":", 1)[1].strip()
        result = by_id.get(current_site) if current_site else None

        if result is not None and stripped.startswith("reference_tile:"):
            indent = line[: len(line) - len(line.lstrip(" "))]
            output.append(f"{indent}reference_tile: {result.reference_tile}\n")
            i += 1
            continue
        if result is not None and stripped.startswith("grid:"):
            indent = line[: len(line) - len(line.lstrip(" "))]
            output.append(f"{indent}grid:\n")
            i += 1
            # Consomme les 3 lignes epsg/origin_x/origin_y existantes (vides ou déjà remplies).
            field_indent = indent + "  "
            for field_name, value in (
                ("epsg", result.epsg),
                ("origin_x", result.origin_x),
                ("origin_y", result.origin_y),
            ):
                if i < len(lines) and lines[i].strip().startswith(f"{field_name}:"):
                    i += 1
                output.append(f"{field_indent}{field_name}: {value}\n")
            continue

        output.append(line)
        i += 1
    return "".join(output)


def _write_atomic(path: Path, content: str) -> None:
    """Écrit `content` dans `path` de façon atomique (tmp + rename même filesystem)."""
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".sites-", suffix=".yaml.tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(content)
        Path(tmp_path).replace(path)
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def run(site_filter: list[str] | None) -> int:
    """Orchestre le relevé : lit la config, interroge le réseau, réécrit sites.yaml (sous
    condition de relecture réussie) et le rapport. Renvoie le code de sortie du processus."""
    settings = load_settings(DEFAULT_SETTINGS_PATH)
    try:
        existing_sites = load_sites(DEFAULT_SITES_PATH)
    except (ConfigError, SiteValidationError) as exc:
        print(f"survey-tiles : sites.yaml invalide en entrée : {exc}", file=sys.stderr)
        return exit_codes.USAGE

    targets = existing_sites
    if site_filter:
        wanted = set(site_filter)
        targets = [s for s in existing_sites if s.id in wanted]
        missing = wanted - {s.id for s in targets}
        if missing:
            print(f"survey-tiles : id(s) inconnu(s) : {sorted(missing)}", file=sys.stderr)
            return exit_codes.USAGE

    results: list[SiteSurveyResult] = []
    try:
        with httpx.Client() as client:
            for site in targets:
                print(f"survey-tiles : {site.id} …", file=sys.stderr)
                result = survey_site(client, site.id, site.lat, site.lon, settings)
                results.append(result)
                print(
                    f"survey-tiles : {site.id} -> {result.reference_tile} "
                    f"(epsg={result.epsg}, origin=({result.origin_x}, {result.origin_y}))",
                    file=sys.stderr,
                )
    except SurveyNetworkError as exc:
        print(f"survey-tiles : réseau injoignable, sites.yaml inchangé : {exc}", file=sys.stderr)
        return exit_codes.INCONCLUSIVE
    except SurveyDataError as exc:
        print(f"survey-tiles : échec métier, sites.yaml inchangé : {exc}", file=sys.stderr)
        return exit_codes.FAILURE
    except TileGeometryError as exc:
        print(f"survey-tiles : géométrie invalide, sites.yaml inchangé : {exc}", file=sys.stderr)
        return exit_codes.FAILURE

    sites_path = DEFAULT_SITES_PATH
    raw_text = sites_path.read_text(encoding="utf-8")
    new_text = _apply_results(raw_text, results)

    # Relecture-validation AVANT écriture (décision d'ancrage n°3) : toute erreur laisse
    # sites.yaml strictement inchangé.
    fd, tmp_check = tempfile.mkstemp(suffix=".yaml")
    try:
        Path(tmp_check).write_text(new_text, encoding="utf-8")
        try:
            reloaded = load_sites(Path(tmp_check))
        except (ConfigError, SiteValidationError) as exc:
            print(
                f"survey-tiles : relecture du résultat invalide, sites.yaml inchangé : {exc}",
                file=sys.stderr,
            )
            return exit_codes.FAILURE
    finally:
        os.close(fd)
        Path(tmp_check).unlink(missing_ok=True)

    _write_atomic(sites_path, new_text)

    report = {
        "generated_for": [r.site_id for r in results],
        "sites": [asdict(r) for r in results],
    }
    REPORT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(
        f"survey-tiles : {len(results)} site(s) relevé(s) sur {len(reloaded)} au total "
        f"dans sites.yaml — rapport : {REPORT_PATH}",
        file=sys.stderr,
    )
    return exit_codes.OK


def main() -> None:
    """Point d'entrée argparse : `--sites A01,C07` (défaut : tous les sites de sites.yaml)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sites",
        type=str,
        default=None,
        help="Liste d'ids séparés par des virgules (ex. A01,C07). Défaut : tous les sites.",
    )
    args = parser.parse_args()
    site_filter = [s.strip() for s in args.sites.split(",") if s.strip()] if args.sites else None
    sys.exit(run(site_filter))


if __name__ == "__main__":
    main()
