#!/usr/bin/env python3
"""smoke.py — le pipeline RÉEL sur un périmètre minuscule (gate `just smoke`).

À câbler dès le premier lot : exécuter le vrai chemin de bout en bout (vraies I/O,
petit volume), et asserter un résultat mesurable. Tant qu'aucun pipeline n'existe,
ce placeholder passe en le signalant — il DOIT être remplacé par la fiche qui pose
le premier pipeline (règle : le gate vert appartient à la fiche qui le casse).
"""

import sys

print("smoke: placeholder — aucun pipeline câblé encore (OK par convention de scaffold)")
sys.exit(0)
