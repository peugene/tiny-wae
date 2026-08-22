---
id: out-01
titre: Étendre mypy strict à tests/ — la substituabilité aux Protocols n'est vérifiée nulle part
effort: M
categorie: outillage
phase: O3
depends_on: [l0-06.2]   # après la dernière fiche codée du lot — cf. « Quand la faire »
parent:
---

# [out-01] — mypy sur `tests/`

> **Fiche différée**, rédigée pendant le run N5 (22/08/2026) au lieu d'interrompre le run.
> Elle capture un trou d'oracle constaté en clôturant l0-03.5, pas une idée d'amélioration.

## Le problème constaté

L'oracle O1 de **l0-03.5** demandait de vérifier que `FixtureSource` est **substituable** à
`EarthSearchSource` derrière le port `StacSource`. La décision d'ancrage retenue s'appuyait
sur mypy : `StacSource` est un `typing.Protocol` **non** `runtime_checkable`, donc sa
conformité se vérifie **statiquement**, c'est même toute sa raison d'être.

Or `pyproject.toml` porte `[tool.mypy] files = ["src"]` : **`tests/` n'est pas typé**. Le
test écrit pour O1 (`def _consume(source: StacSource) -> Envelope` appelée avec les deux
implémentations) est donc du **texte non vérifié** — il documente l'intention sans rien
garantir. Une `FixtureSource` dont la signature de `search` dériverait passerait le gate.

Le même angle mort couvre tous les tests du dépôt : ~**160 tests écrits par des agents**,
dont aucun n'est confronté au typage.

## Mesure (22/08/2026, `develop` @ run N5)

`mypy tests` → **24 erreurs dans 7 fichiers** sur 19 fichiers analysés. Échantillon :

- `tests/test_cli_search.py:177` — `"object" has no attribute "stdout"` (le `Result` de
  `CliRunner` est annoté `object` par le test lui-même) ;
- `tests/test_cli_ingest.py:123` — `Need type annotation for "array"` ;
- `tests/test_cli_ingest.py:213`, `tests/test_chips.py:294` — `Returning Any from function
  declared to return …` (numpy/rasterio rendent `Any`).

Aucune de ces 24 erreurs ne révèle un bug : ce sont des annotations manquantes et des
retours `Any` d'API géospatiales mal typées. Le travail est **mécanique mais réel**.

## Ce qu'il faudra trancher

1. **`files = ["src", "tests"]`** d'un coup, ou `tests/` en mode moins strict (les libs
   géospatiales rendent `Any` en permanence — cf. `ignore_missing_imports = true` déjà posé
   pour la même raison) ?
2. Faut-il un `disallow_any_expr` relâché sur `tests/` seulement, pour ne pas transformer
   chaque `array.mean()` en erreur ?
3. Le gate s'allonge : `just types` passerait de 26 à ~45 fichiers.

## Pourquoi ça vaut le coup

Sur un dépôt dont la quasi-totalité du code est écrite par des agents, le typage est le
**filet n°1** (c'est déjà le motif écrit dans `CLAUDE.md` pour `src/`). Le laisser s'arrêter
à la frontière des tests revient à ne pas vérifier précisément le code qui **atteste** que
le reste est correct — et les Protocols du projet (`StacSource`, et ceux du Lot 1 à venir)
n'ont **aucun** autre mécanisme de vérification.

## Quand la faire (motif du `depends_on`)

Après **l0-06.2**, la dernière fiche dispatchable du lot 0. La faire plus tôt obligerait à
retyper les tests que les fiches restantes (l0-03.6, l0-03.7, l0-04.1, l0-04.2, l0-05.2,
l0-06.2) vont ajouter — le même travail, deux fois. Rien dans out-01 ne bloque ces fiches.

## Non couvert par cette fiche

Le choix d'un `runtime_checkable` sur `StacSource` (rejeté à l'ancrage de l0-03.5 : ce
serait rendre la production dépendante d'un besoin de test).
