"""core/statuses.py — énumération normative des statuts d'item (chapeau l0-02).

Zéro I/O, zéro framework. Module dédié sur le patron de ``core/bands.py`` : la place d'une
énumération de DOMAINE est dans ``core/``, pas dans ``adapters/``.

``MANIFEST_STATUSES`` (5 valeurs, = ces 6 moins ``skipped``) avait été supprimée au commit
``c67bfc1`` (post-revue 1, constat A2) : la constante vivait dans ``adapters/manifests.py``
depuis sa création sans AUCUN consommateur (vérifié sur ``src/``, ``tests/`` et
``scripts/``), et ``write_manifest`` ne validait pas le statut qu'on lui passait — déplacer
du code mort la rendait seulement plus visible. La fiche l0-07 la réintroduit ici,
**dérivée** (jamais re-listée à la main), cette fois avec le consommateur qui lui manquait :
``write_manifest`` (``adapters/manifests.py``) refuse d'écrire un manifeste dont le statut
n'y figure pas — garde symétrique à celle déjà posée sur les compteurs de run
(``_validate_counters`` / ``ConservationError``).

Motif de l'origine des 6 statuts (post-revue 1, constat A2) : ils vivaient dans
``adapters/manifests.py`` et étaient RECOPIÉS à l'identique dans ``core/report.py`` — parce
que ``core/`` ne doit jamais importer ``adapters/``. La recopie était assumée en
commentaire, mais rien n'empêchait les deux listes de diverger. Les remonter ici respecte
la couche ET supprime le double.
"""

from __future__ import annotations

# Les 6 statuts de run.json (énumération normative : chapeau l0-02).
RUN_STATUSES: tuple[str, ...] = (
    "ingested",
    "rejected_clouds",
    "rejected_invalid",
    "rejected_nodata",
    "failed",
    "skipped",
)

# Les 5 statuts légitimes d'un manifest.json — DÉRIVÉE de RUN_STATUSES, jamais re-listée à
# la main (fiche l0-07) : un item déjà ingéré au grid_hash courant n'est jamais retraité,
# donc "skipped" n'est jamais écrit à un manifeste.
MANIFEST_STATUSES: frozenset[str] = frozenset(RUN_STATUSES) - {"skipped"}
