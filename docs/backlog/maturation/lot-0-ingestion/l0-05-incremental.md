---
id: l0-05-incremental
titre: Ingestion incrémentale quotidienne (fenêtre depuis le dernier manifeste)
effort: S
categorie: pipeline
phase: O3
depends_on: [l0-04-backfill]
---

# [l0-05] — Mode incrémental quotidien

> Fiche de backlog : brief pour l'IA. En `a-faire/`, ce brief doit être autonome.

## Objectif

Le run quotidien : « quoi de neuf depuis la dernière fois ? » — même pipeline que le
backfill, fenêtre auto-bornée. La plupart des runs seront courts ou vides (revisite S2
~5 jours, publication L2A quelques heures à ~2 jours après acquisition) : c'est normal et
ça doit se voir dans la sortie.

## Contexte et périmètre

- CLI `update [--sites all]` : pour chaque site, borne basse = date du dernier manifeste
  (moins 3 jours de marge — les acquisitions se publient en retard), borne haute =
  maintenant. Réutilise `ingest` tel quel ; l'idempotence (l0-03) absorbe le recouvrement
  de la marge.
- Sortie : une ligne par site avec compteurs, résumé final honnête (« 25 sites, 4 avec du
  nouveau, 21 à jour, 0 échec »). Exit 0 si aucun échec.
- Ordonnancement (cron NAS ou déclencheur) : hors périmètre fiche — documenter la commande
  dans le README, c'est tout (geste d'infra = Philippe).

## Définition de « terminé »

- [ ] `just run update` fonctionne après un backfill (et après un update précédent).
- [ ] Test : bornes calculées depuis manifestes fixtures (dernier jour, marge, site vierge
      → refuse et pointe vers backfill).

## Oracle / recette (figé AVANT implémentation)

| # | Critère mesuré | Seuil de succès |
|---|---|---|
| O1 | `update` juste après backfill | ~0 nouveau (fenêtre ≤ marge), 100 % à jour, exit 0 |
| O2 | **`update` × 2 d'affilée** | 2e run : zéro ingestion, zéro re-téléchargement |
| O3 | `update` avec un trou simulé (manifestes du dernier mois retirés sur 1 site de test) | le trou est rattrapé, les autres sites intacts |

**Non testé par cette fiche** : le cron réel (décision d'infra Philippe).

---

## Résumé de réalisation

*(à remplir avant de déplacer la fiche dans `fait/`)*
