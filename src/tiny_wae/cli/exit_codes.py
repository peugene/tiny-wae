"""cli/exit_codes.py — codes de sortie figés, partagés par TOUS les CLIs du projet.

Décision chapeau l0-01 : `0` succès · `1` échec métier · `2` erreur config/usage ·
`3` non concluant (amont injoignable — obligatoire pour `search`/`ingest`/`backfill`/`update`,
cf. `docs/backlog/maturation/lot-0-ingestion/l0-01.md`). Zéro logique ici, uniquement des
constantes : chaque CLI les importe et lève `typer.Exit(code=...)`.
"""

from __future__ import annotations

OK = 0
FAILURE = 1
USAGE = 2
INCONCLUSIVE = 3
