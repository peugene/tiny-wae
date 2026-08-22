"""core/statuses.py — énumération normative des statuts d'item (chapeau l0-02).

Zéro I/O, zéro framework. Module dédié sur le patron de ``core/bands.py`` : la place d'une
énumération de DOMAINE est dans ``core/``, pas dans ``adapters/``.

⛔ ``MANIFEST_STATUSES`` (5 valeurs, = ces 6 moins ``skipped``) N'A PAS été remonté ici :
la constante existait dans ``adapters/manifests.py`` depuis sa création sans AUCUN
consommateur (vérifié sur ``src/``, ``tests/`` et ``scripts/``, à HEAD comme à d837c76),
et ``write_manifest`` ne valide pas le statut qu'on lui passe. Déplacer du code mort le
rend seulement plus visible ; elle a donc été supprimée. Faire APPLIQUER la règle
(« ``skipped`` n'est jamais écrit à un manifeste ») est un autre sujet, à instruire.

Motif (post-revue 1, constat A2) : ces 6 statuts vivaient dans ``adapters/manifests.py`` et
étaient RECOPIÉS à l'identique dans ``core/report.py`` — parce que ``core/`` ne doit jamais
importer ``adapters/``. La recopie était assumée en commentaire, mais rien n'empêchait les
deux listes de diverger. Les remonter ici respecte la couche ET supprime le double.
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
