"""adapters/fixture_source.py — ``FixtureSource``, implémentation ``StacSource`` hors ligne
servant le corpus de fixtures enregistré par ``scripts/record_cog_fixtures.py`` (l0-03.5).

Aucun mock HTTP (D-a, chapeau l0-03) : ce module lit les enveloppes STAC brutes déjà
enregistrées (``tests/fixtures/stac/cog_<site_id>.json``, format ``{"items": [<item
brut>]}`` — décision d'ancrage n°2, IDENTIQUE à ``record_stac_fixtures.py``, JAMAIS un
``Envelope.to_dict()`` sérialisé), réécrit les hrefs des assets mappés vers les GeoTIFF
locaux clippés (``tests/fixtures/cog/<item_id>/<clé>.tif``, ``file://`` absolu — oracle
O3), **filtre sur la fenêtre demandée**, puis délègue le filtrage qualité/tuile à
``adapters.stac.build_envelope`` — la MÊME fonction pure qu'``EarthSearchSource``
(décision d'ancrage n°3) : c'est ce qui rend la substituabilité au port ``StacSource``
réellement vérifiée, pas seulement déclarée.

⭐ Le filtrage temporel (ajouté au run N6) fait partie du contrat, pas du confort :
``EarthSearchSource`` le délègue au serveur earth-search, donc son ``found_stac`` ne
compte que la fenêtre. Sans lui ici, les deux sources auraient la même signature et des
comportements différents — une substituabilité vraie pour mypy, fausse à l'exécution.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from tiny_wae.adapters.stac import StacSourceError, build_envelope
from tiny_wae.core.envelope import Envelope
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Site
from tiny_wae.core.windows import Window

# Répertoires par défaut du corpus enregistré (mêmes chemins que le script d'enregistrement).
DEFAULT_STAC_DIR = Path("tests/fixtures/stac")
DEFAULT_COG_DIR = Path("tests/fixtures/cog")


class FixtureNotFoundError(StacSourceError):
    """Aucune fixture STAC enregistrée pour ce site — ``search`` refuse plutôt que
    d'inventer une enveloppe vide silencieuse (un corpus manquant doit se voir)."""


def _localize_hrefs(item: dict[str, Any], *, cog_dir: Path) -> dict[str, Any]:
    """Copie ``item`` et réécrit les hrefs de ses assets vers les GeoTIFF locaux de
    ``cog_dir/<item_id>/<clé>.tif`` quand ce fichier existe (``file://`` absolu — oracle
    O3). Un asset sans fichier local enregistré (clé non mappée, ex. ``cloud``/``snow``
    des items S2C) garde son href d'origine, inoffensif : ``build_envelope``/``parse_item``
    ne lisent jamais les clés hors ``asset_keys``."""
    localized = copy.deepcopy(item)
    item_id = localized["id"]
    for key, asset in localized.get("assets", {}).items():
        local_path = cog_dir / item_id / f"{key}.tif"
        if local_path.exists():
            asset["href"] = local_path.resolve().as_uri()
    return localized


def _item_datetime(item: dict[str, Any]) -> datetime:
    """Parse ``properties.datetime`` d'un item STAC en ``datetime`` NAÏF (UTC).

    earth-search rend un RFC3339 suffixé ``Z`` (``2022-09-01T10:39:03.240000Z``). Le
    fuseau est retiré après parsing : les bornes de ``Window`` sont **naïves** et exprimées
    en UTC par convention du projet — comparer un ``datetime`` aware à un naïf lève un
    ``TypeError``. Le ``replace("Z", "+00:00")`` est une ceinture (Python 3.12 accepte
    déjà le ``Z``), qui garde la fonction lisible sur la forme exacte attendue.
    """
    raw = str(item["properties"]["datetime"])
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=None)


def _in_window(item: dict[str, Any], window: Window) -> bool:
    """Vrai si l'item tombe dans la fenêtre demi-ouverte ``[start, end[``."""
    moment = _item_datetime(item)
    return window.start <= moment < window.end


@dataclass(frozen=True, slots=True)
class FixtureSource:
    """Implémentation ``StacSource`` servant le corpus de fixtures COG local (l0-03.5).

    Signature calquée sur ``EarthSearchSource`` (``settings`` en premier champ) : c'est ce
    qui permet à ``_consume(source: StacSource) -> Envelope`` (oracle O1) d'accepter les
    deux implémentations sans distinction. ``stac_dir``/``cog_dir`` ont des défauts pour un
    usage direct depuis les tests, mais restent overridables (ex. corpus réduit en test).
    """

    settings: Settings
    stac_dir: Path = field(default=DEFAULT_STAC_DIR)
    cog_dir: Path = field(default=DEFAULT_COG_DIR)

    def _load_raw_items(self, site_id: str) -> list[dict[str, Any]]:
        """Charge ``{"items": [...]}`` depuis ``stac_dir/cog_<site_id minuscule>.json``.

        Lève ``FixtureNotFoundError`` si le fichier n'existe pas — un site sans fixture
        enregistrée ne doit jamais rendre silencieusement une enveloppe vide.
        """
        path = self.stac_dir / f"cog_{site_id.lower()}.json"
        if not path.exists():
            raise FixtureNotFoundError(
                f"aucune fixture COG enregistrée pour le site {site_id!r} ({path})"
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        items: list[dict[str, Any]] = data["items"]
        return items

    def search(self, site: Site, window: Window) -> Envelope:
        """Rend l'enveloppe du corpus enregistré du site, **filtrée sur ``window``**.

        ⭐ Le filtrage temporel est essentiel à la substituabilité RÉELLE au port :
        ``EarthSearchSource`` passe la fenêtre à earth-search, qui filtre **côté serveur** —
        donc son ``found_stac`` ne compte que les items de la fenêtre. Une ``FixtureSource``
        qui rendrait tout le corpus quelle que soit la fenêtre aurait la même *signature*
        mais pas le même *comportement* : les deux sources ne seraient interchangeables
        qu'aux yeux du typage. (Défaut corrigé au dispatch du run N6, quand les oracles de
        l0-04.1 et l0-05.2 — qui comptent sur des fenêtres discriminantes — l'ont révélé.)

        Fenêtre **demi-ouverte** ``[start, end[``, comme ``core.windows.Window``. Le
        filtrage précède ``build_envelope`` : ``found_stac`` compte donc bien les items
        rendus pour la fenêtre, avant tout filtre qualité — dénominateur identique à celui
        d'earth-search (décision E-a du chapeau l0-02).

        Lève ``StacSourceError`` si ``site.reference_tile`` n'est pas posée (même garde
        qu'``EarthSearchSource``).
        """
        if site.reference_tile is None:
            raise StacSourceError(f"site {site.id} : reference_tile non posée — recherche refusée")

        raw_items = [item for item in self._load_raw_items(site.id) if _in_window(item, window)]
        localized_items = [_localize_hrefs(item, cog_dir=self.cog_dir) for item in raw_items]

        return build_envelope(
            site_id=site.id,
            window=window,
            raw_items=localized_items,
            reference_tile=site.reference_tile,
            scene_cloud_max=self.settings.scene_cloud_max,
            asset_keys=self.settings.asset_keys,
        )
