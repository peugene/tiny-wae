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

## ⚠ Ancrage dans le code réel (22/08/2026, avant dispatch — run N8)

Vérifié sur `develop` après la clôture complète du lot 0 côté agents. **Cette fiche part
SEULE** : elle touche `pyproject.toml` et potentiellement tous les fichiers de `tests/`,
aucune parallélisation n'est possible. C'est la raison de son `depends_on: [l0-06.2]`.

### Mesure fraîche (refaite après le merge de l0-04.2)

`mypy tests` → **30 erreurs dans 11 fichiers**, sur 26 analysés. Le compte est monté de 27 à
30 avec les tests de l0-04.2, comme prévu.

**Par code d'erreur** : `attr-defined` **13** · `type-arg` 5 · `no-any-return` 5 ·
`unused-ignore` 4 · `var-annotated` 2 · `misc` 1.

**Par fichier** : `test_cli_search.py` **14** · `test_report.py` 3 · `test_manifests.py` 3 ·
`test_config.py` 2 · `test_cli_ingest.py` 2 · puis 1 chacun dans `test_stac.py`,
`test_smoke.py`, `test_ingestion.py`, `test_contact_sheet.py`, `test_cli_backfill.py`,
`test_chips.py`.

⭐ **Les 13 `attr-defined` viennent d'UN SEUL endroit** : `tests/test_cli_search.py` annote
son helper `_invoke(...) -> object`, puis lit `result.exit_code` / `result.stdout` /
`result.stderr` dessus. Corriger cette annotation en `click.testing.Result` en règle **la
moitié du lot d'un coup**. Commence par là : le reste paraîtra beaucoup plus petit.

### L'existant

- `pyproject.toml` → `[tool.mypy] strict = true · files = ["src"] · ignore_missing_imports = true`.
  ⚠ `ignore_missing_imports` a été posé pour `src/` avec un motif explicite : « pragmatique
  sur l'écosystème (libs géospatiales mal typées) ». Le même motif vaut pour `tests/`, qui
  manipule numpy et rasterio directement — c'est de là que viennent les `no-any-return` et
  les `type-arg`.
- Le gate est `lint && types && test && smoke && cwl` — **235 tests** verts, `just types`
  couvre aujourd'hui **34 fichiers** de `src/`.
- `just test -k <motif>` cible un test sans lancer la suite (utile ici : la suite prend ~90 s).
- Les 4 `unused-ignore` sont des `# type: ignore` devenus faux avec le temps — ⭐ c'est en
  soi un argument pour la fiche : un ignore posé à l'aveugle **pourrit sans que rien ne le
  signale**, tant que `tests/` n'est pas analysé.

### Décisions d'ancrage (prises ici — ne pas rouvrir)

1. **`files = ["src", "tests"]` d'un seul bloc**, en gardant `strict = true`. ⛔ Pas de régime
   dégradé pour `tests/` : les 30 erreurs mesurées sont **mécaniques** (annotations
   manquantes, retours `Any` de libs), aucune ne demande d'assouplir `strict`. Si une
   catégorie s'avérait réellement irréductible, la traiter par une **exclusion nommée et
   justifiée**, jamais par un abaissement global.
2. ⛔ **Aucun `# type: ignore` posé en masse** pour faire passer le gate — c'est exactement ce
   que la fiche existe pour éviter, et les 4 `unused-ignore` déjà présents montrent où ça
   mène. Un `ignore` n'est acceptable que **nommé** (`# type: ignore[code]`) et accompagné
   d'un commentaire disant pourquoi le typage ne peut pas exprimer la chose.
3. ⛔ **Ne modifie AUCUN comportement de test.** Cette fiche annote, elle ne corrige pas de
   logique. Si une annotation révèle un vrai bug dans un test, **arrête-toi et signale-le**
   dans ton compte-rendu au lieu de le réparer au passage — un test dont le comportement
   change dans une fiche de typage est un test qu'on ne relit plus.
4. ⭐ **La VALEUR de la fiche est la conformité aux Protocols, pas le ménage d'annotations.**
   Le motif d'origine : l'oracle O1 de l0-03.5 vérifiait que `FixtureSource` est substituable
   à `EarthSearchSource` derrière le `Protocol` `StacSource` — via une fonction annotée dans
   `tests/`, donc **jamais vérifiée**. Une fois `tests/` sous mypy, **prouve-le par mutation** :
   casse temporairement la signature de `FixtureSource.search` (renomme un paramètre, change
   un type de retour), vérifie que **`just types` devient ROUGE**, restaure, et **publie la
   sortie d'erreur obtenue** dans ton compte-rendu. Sans cette démonstration, la fiche n'aura
   fait que du ménage.
5. **Mesure et publie la durée de `just types` avant et après** : le gate passe de 34 à
   ~60 fichiers analysés, et il est lancé à chaque itération de chaque agent.
6. Une **découverte de l0-04.2 à connaître** : un `Protocol` structurel destiné à recevoir des
   dataclasses `frozen=True` du projet doit déclarer ses membres en **`@property`**, pas en
   annotations planes (une annotation plane exige un attribut réassignable — mypy dit
   « expected settable variable, got read-only attribute »). Si tu croises ce message, c'est
   la cause.

## Quand la faire (motif du `depends_on`)

Après **l0-06.2**, la dernière fiche dispatchable du lot 0. La faire plus tôt obligerait à
retyper les tests que les fiches restantes (l0-03.6, l0-03.7, l0-04.1, l0-04.2, l0-05.2,
l0-06.2) vont ajouter — le même travail, deux fois. Rien dans out-01 ne bloque ces fiches.

## Non couvert par cette fiche

Le choix d'un `runtime_checkable` sur `StacSource` (rejeté à l'ancrage de l0-03.5 : ce
serait rendre la production dépendante d'un besoin de test).
