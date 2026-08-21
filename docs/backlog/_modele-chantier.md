---
id: mon-chantier
label: Mon chantier (libellé lisible)
desc: Une phrase qui décrit le périmètre du chantier.
phases: O1=Socle | O2=Médias | O3=Finitions
---

# Chantier — Mon chantier

> **Manifeste de chantier** (`_chantier.md`) : placé dans un sous-dossier d'état
> (ex. `maturation/mon-chantier/`), il décrit un **chantier autonome**.
>
> - `label` / `desc` : titre et résumé affichés sur le dashboard.
> - `phases` : `id=libellé` séparés par `|` (ou `,`). Les fiches du chantier portant
>   `phase: <id>` sont regroupées sous ces phases, dans cet ordre. Optionnel.
>
> Le **statut du chantier = le dossier d'état** où vit le sous-dossier :
> `maturation/` (en analyse) · `a-faire/` · `en-cours/` · `fait/` (→ page d'archive auto).
>
> Documents du chantier (méthode deux phases, optionnelle) :
> - `_roadmap.md` → `roadmap.html` (roadmap indicative, phase 1).
> - `_revue.md`  → `revue.html`  (revue de cohérence adversariale, phase 2).
> Le dashboard lie automatiquement `roadmap.html` / `revue.html` s'ils existent.
