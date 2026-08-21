"""core/envelope.py — enveloppe JSON versionnée d'une recherche STAC (chapeau l0-02).

Zéro I/O : ``Envelope`` regroupe le résultat d'un ``StacSource.search`` (``adapters/stac.py``)
avec ses compteurs. Consommée par ``ingest --acquisitions`` (l0-03.4) et le step CWL (l0-06).

⭐ Deux dénominateurs (décision Philippe E-a, chapeau l0-02 — le mot ``found`` seul est
BANNI du lot) : ``found_stac`` (avant tout filtre) et ``found_tile`` = ``found_stac -
skipped_scene_cloud - off_tile`` (les items réellement instruits). L'invariant de
conservation ``found_stac == skipped_scene_cloud + off_tile + found_tile`` ET
``found_tile == len(items)`` est vérifié À LA CONSTRUCTION — une ``Envelope`` incohérente
ne peut pas exister.

⛔ ``ConservationError`` est définie ICI, pas importée depuis ``adapters/manifests.py`` :
``core/`` ne dépend jamais d'``adapters/`` (règle de couche). La duplication du nom entre
les deux modules est assumée (décision n°2 de l'ancrage de la fiche).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tiny_wae.core.acquisition import Acquisition

SCHEMA_VERSION = 1

# Les 4 compteurs obligatoires de l'enveloppe (décision E-a du chapeau l0-02).
_COUNTER_KEYS: tuple[str, ...] = ("found_stac", "skipped_scene_cloud", "off_tile", "found_tile")


class ConservationError(ValueError):
    """Invariant de conservation de l'enveloppe violé (décision E-a, chapeau l0-02)."""


@dataclass(frozen=True, slots=True)
class Envelope:
    """Résultat versionné d'une recherche STAC pour un site sur une fenêtre.

    ``window`` est un mapping ``{"start": ..., "end": ...}`` (chaînes ISO). L'invariant de
    conservation des compteurs est vérifié dans ``__post_init__`` : construire une
    ``Envelope`` avec des compteurs incohérents lève ``ConservationError`` immédiatement,
    plutôt que de laisser une donnée fausse partir en aval (ingest, CWL).
    """

    schema_version: int
    site_id: str
    window: dict[str, str]
    counters: dict[str, int]
    items: list[Acquisition]

    def __post_init__(self) -> None:
        """Vérifie la présence des 4 compteurs puis les deux invariants de conservation."""
        missing = [key for key in _COUNTER_KEYS if key not in self.counters]
        if missing:
            raise ConservationError(f"envelope.counters : clé(s) manquante(s) {missing}")

        envelope_sum = (
            self.counters["skipped_scene_cloud"]
            + self.counters["off_tile"]
            + self.counters["found_tile"]
        )
        if self.counters["found_stac"] != envelope_sum:
            raise ConservationError(
                "invariant violé : found_stac="
                f"{self.counters['found_stac']} != "
                f"skipped_scene_cloud+off_tile+found_tile={envelope_sum}"
            )
        if self.counters["found_tile"] != len(self.items):
            raise ConservationError(
                f"invariant violé : found_tile={self.counters['found_tile']} != "
                f"len(items)={len(self.items)}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Sérialise en dict JSON-compatible (délègue aux items pour leur propre forme)."""
        return {
            "schema_version": self.schema_version,
            "site_id": self.site_id,
            "window": dict(self.window),
            "counters": dict(self.counters),
            "items": [item.to_dict() for item in self.items],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Envelope:
        """Reconstruit une ``Envelope`` depuis son dict JSON (inverse de ``to_dict``).

        Revalide les invariants de conservation (``__post_init__``) : une enveloppe lue
        d'un fichier corrompu lève ``ConservationError`` au même titre qu'à la construction.
        """
        return Envelope(
            schema_version=data["schema_version"],
            site_id=data["site_id"],
            window=dict(data["window"]),
            counters=dict(data["counters"]),
            items=[Acquisition.from_dict(item) for item in data["items"]],
        )
