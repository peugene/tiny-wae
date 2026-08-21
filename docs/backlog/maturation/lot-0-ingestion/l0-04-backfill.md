---
id: l0-04-backfill
titre: Backfill 48 mois × 25 sites + rapport de recette chiffré + planche visuelle
effort: M
categorie: pipeline
phase: O2
depends_on: [l0-03-chip-ingest]
---

# [l0-04] — Backfill historique et recette du lot

> Fiche de backlog : brief pour l'IA. En `a-faire/`, ce brief doit être autonome.

## Objectif

Constituer l'historique : 48 mois glissants pour les 25 sites, avec le rapport chiffré et
la planche de contrôle visuel qui font la recette du Lot 0 (oracles O1/O2/O5 de la fiche
d'origine `LOT0-fiche-sites.md`).

## Contexte et périmètre

- CLI `backfill [--sites all|A01,B02] [--months 48]` : boucle sites × fenêtre sur `ingest`
  (l0-03), reprise sur erreur (backoff, un site en échec n'arrête pas les autres), compteurs
  agrégés. Séquentiel d'abord (Q-C) — paralléliser seulement si la mesure l'exige.
- CLI `report` : agrège les manifestes → `data/report.md` (+ .html via `just md2html`) —
  par site : acquisitions trouvées / ingérées / rejetées nuages / échecs, période couverte,
  volume ; totaux et **pires cas mis en avant**.
- CLI `contact-sheet` : planche PNG par site (premier chip, dernier chip, RGB) → gate
  visuel Philippe : centrage + correction éventuelle des coordonnées dans `sites.yaml`
  (puis ré-ingestion ciblée du site corrigé).
- Exécution réelle du backfill : lancée par Philippe ou l'équipe sur la machine cible
  (données sur NAS) — la fiche livre l'outillage ET le premier run complet.

## Définition de « terminé »

- [ ] Backfill complet exécuté sur les 25 sites (échecs résiduels documentés).
- [ ] `data/report.md` généré, chiffres par site, pires cas inclus.
- [ ] Planche visuelle produite ; **gate Philippe passé** : 25/25 sites identifiables et
      centrés (corrections de coordonnées faites et ré-ingérées le cas échéant).

## Oracle / recette (figé AVANT implémentation)

| # | Critère mesuré | Seuil de succès |
|---|---|---|
| O1 | Acquisitions exploitables (< 30 % nuages chip) par site sur 48 mois | ≥ 60 par site ; **chiffre par site publié, y compris les pires** — un site sous le seuil = documenté, pas masqué (les récents type Sizewell/Chancay s'expliquent, cf. roadmap §3) |
| O2 | Centrage visuel | 25/25 validés par Philippe (gate humain) |
| O3 | Intégrité | 100 % des chips ingérés lisibles, 4 bandes, géoréférencés |
| O4 | Volume total + durée du backfill | publiés (baseline — l'estimation ~15-25 Go se confronte au réel) |

**Non testé par cette fiche** : fraîcheur au fil de l'eau (l0-05), CDSE.

## Notes / pistes

Verrou avant `a-faire/` : Q-C (parallélisme) à confirmer en revue. Le rapport et la planche
sont des CLIs rejouables — ils resserviront à chaque extension du parc de sites.

---

## Résumé de réalisation

*(à remplir avant de déplacer la fiche dans `fait/`)*
