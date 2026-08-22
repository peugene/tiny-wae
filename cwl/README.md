# cwl/ — emballage CWL des CLI tiny-wae

Fiche `l0-06.1` (chapeau `l0-06`). Périmètre **fermé** : 3 `CommandLineTool`
(`search.cwl`, `ingest.cwl` — `update.cwl` viendra en `l0-06.2`) + 1 `Workflow`
(`workflow.cwl`, `search → ingest`). CWL v1.2.

**⛔ Hors périmètre, décision de chapeau** : pas d'enregistrement server PID-FLOW réel,
pas de `pid:Milestone` (scope creep pointé en revue v2 — le consommateur, l'IHM
PID-FLOW, est hors lot ; à réintroduire dans une fiche d'enregistrement future).
Ici, **validation locale `cwltool` uniquement**.

## Écart assumé vs cwl-assets

Les tools cwl-assets classiques embarquent des scripts rsyncés à côté du `.cwl`.
Ici, `tiny_wae` est un **package Python installé** dans l'environnement (pixi) : le
`baseCommand` appelle directement `python -m tiny_wae <cmd>`, sans script à
déployer. C'est un écart délibéré, pas un oubli.

## Pourquoi `python` en dur dans le `baseCommand` (et pas `just`)

La règle façade du projet (« `pixi` ne s'écrit jamais hors du `justfile` ») s'applique
aux recettes, à la doc et aux prompts d'agents — bref, à tout ce qui s'exécute
**dans ce dépôt, par une main ou un agent qui a `just` sous la main**. Un fichier
`.cwl` est destiné à un **exécuteur externe** (typiquement un worker PID-FLOW) qui ne
connaît ni ce dépôt, ni `just`, ni `pixi` — seulement l'environnement dans lequel le
`baseCommand` s'exécute. `python -m tiny_wae <cmd>` est donc le seul appel qui a un
sens depuis l'extérieur ; ce n'est pas une entorse à la règle façade, c'est son
domaine d'application qui s'arrête à la frontière du dépôt. Ne pas « corriger » ces
fichiers pour y mettre `just` — ça ne s'exécuterait nulle part en dehors du
développeur qui a le dépôt cloné.

## Codes de sortie et `successCodes`

Les CLI `search`/`ingest` partagent la même convention (`cli/exit_codes.py`) :
`0` OK · `1` FAILURE (échec métier, ≥ 1 item en échec) · `2` USAGE (config/usage
invalide) · `3` INCONCLUSIVE (amont injoignable / aucun item n'a abouti).

- **`search.cwl`** : `successCodes: [0]` uniquement. Un endpoint STAC injoignable
  (INCONCLUSIVE) ou une config invalide (USAGE) doivent arrêter le workflow — il n'y
  a rien à ingérer si la recherche a échoué.
- **`ingest.cwl`** : `successCodes: [0, 1]`. Un `FAILURE` (≥ 1 item en échec, mais au
  moins un succès) est un **résultat métier légitime** — le forcer en erreur CWL
  ferait échouer le workflow sur des runs par ailleurs sains (idempotence au grain
  item : les items ratés seront retentés au run suivant). `USAGE` (2) et
  `INCONCLUSIVE` (3, aucun item n'a abouti) restent des échecs CWL.

## `TINY_WAE_DATA_ROOT` (levier de l'oracle O2)

`ingest` n'a **aucune option `--data-root`** : la racine de stockage vient de
`settings.data_root` (`config/settings.yaml`), surchargeable par la variable
d'environnement `TINY_WAE_DATA_ROOT` (mécanisme `TINY_WAE_*` de
`adapters/config_io.py`). `ingest.cwl` déclare un `EnvVarRequirement` qui pose cette
variable à partir de l'input `data_root` (défaut `./data`, comme le YAML) — c'est ce
qui permet de pointer deux racines de stockage vierges et distinctes lors d'une
comparaison run CWL / run CLI direct.

⚠ **`ingest.cwl` n'a AUCUNE sortie CWL déclarée** (`outputs: []`). Essayé puis retiré,
mesuré à l'exécution (oracle O2) : la spec CWL interdit un `outputBinding.glob`
commençant par `/`, or `data_root` est justement pensé pour recevoir un chemin
**absolu**, hors du répertoire de travail du tool — c'est même le cas d'usage de
l'oracle O2 (deux racines vierges arbitraires). Capturer la racine comme sortie
`Directory` casserait donc précisément l'usage pour lequel elle existe. Le succès de
l'ingestion reste signalé par le code de sortie (`successCodes`) ; le contenu écrit se
vérifie directement sur disque (`run.json`, cf. `adapters/manifests.py`), pas via une
sortie CWL.

⚠ **`sites_path`/`settings_path` ne sont PAS de simples options facultatives en
pratique** : le CLI utilise, en leur absence, un chemin **relatif** au CWD
(`config/sites.yaml`, `config/settings.yaml`). Or `cwltool` exécute chaque job dans un
répertoire de staging temporaire, où ce chemin relatif n'existe pas — l'échec observé
n'est pas « fichier introuvable » mais un `Settings.__init__() missing ... arguments`
(le fallback silencieux de `config_io.py` sur un dict vide masque l'absence de
fichier). **En pratique, `sites_path`/`settings_path` sont donc à passer explicitement
à chaque run CWL réel** (cf. exemple de commande ci-dessous) — les laisser vides
casse, ce n'est pas juste une omission de confort.

## Validation

```
just cwl
```

Valide les 3 fichiers **un par un** (`cwltool --validate <fichier>`) — passer
plusieurs chemins d'un coup à `--validate` fait interpréter les arguments suivants
comme un job order, pas comme des tools à valider séparément. Intégré dans
`just check`.

Ce que `cwltool --validate` **ne couvre pas** : il ignore tout des CLI réels du
projet — si une option est renommée dans `cli/search.py` ou `cli/ingest.py` sans
toucher au `.cwl` correspondant, la validation reste verte et le workflow casse
silencieusement à l'exécution. C'est pourquoi `tests/test_cwl.py` confronte chaque
`inputBinding.prefix` déclaré ici aux options réellement exposées par le CLI, via
introspection `click`/`typer` (`typer.main.get_command`, pas un parsing de
`--help`) — le seul test de cette fiche qui échouerait sur du code faux.

## Run local (hors gate, réseau)

```
just cwl-run cwl/workflow.cwl \
    --site A01 --from_date 2026-01-01 --to_date 2026-01-10 \
    --data_root /tmp/cwl-run-data \
    --sites_path config/sites.yaml --settings_path config/settings.yaml
```

(`--sites_path`/`--settings_path` explicites : le CLI défaut sur un chemin **relatif**
au CWD, qui n'est pas le dépôt dans le répertoire de staging temporaire de `cwltool` —
cf. avertissement plus haut. Les omettre casse le run avec une erreur trompeuse,
`Settings.__init__() missing ... arguments`, pas « fichier introuvable ».)

(exécution réelle, pas `--validate` : hors gate — `just cwl` ne fait QUE de la
validation statique, cf. plus haut. La recette `cwl-run` existe précisément pour que
`pixi` ne s'écrive nulle part ailleurs que dans le `justfile` : la règle façade vaut
aussi pour la doc et pour un run ponctuel, sinon la bascule d'un gestionnaire
d'environnement à l'autre se paie en chasse aux occurrences dispersées.)

Comparer avec le run CLI direct équivalent :

```
just run search --site A01 --from 2026-01-01 --to 2026-01-10 --json /tmp/acq.json
TINY_WAE_DATA_ROOT=./data-cli-test just run ingest --acquisitions /tmp/acq.json
```

et comparer les ensembles `(item_id, statut)` des deux `data_root` (manifestes
`run.json`, `adapters/manifests.py`).
