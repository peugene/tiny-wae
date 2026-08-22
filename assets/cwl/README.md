# assets/cwl/ — emballage CWL des CLI tiny-wae, au format PID-FLOW

Fiches `l0-06.1` + `l0-06.2` (chapeau `l0-06`). Périmètre **fermé** : 3
`CommandLineTool` (`search`, `ingest`, `update`) + 1 `Workflow` (`tiny-wae`,
`search → ingest`). CWL v1.2.

**⛔ Hors périmètre, décision de chapeau** : pas d'enregistrement server PID-FLOW réel,
pas de `pid:Milestone` (scope creep pointé en revue v2 — le consommateur, l'IHM
PID-FLOW, est hors lot ; à réintroduire dans une fiche d'enregistrement future).
Ici, **validation locale `cwltool` uniquement**.

## Structure — symétrique du `cwl-store` PID-FLOW

```
assets/cwl/
├── workflows/tiny-wae/1.0/workflow.cwl     → cwl-store/workflows/
└── tools/<nom>/1.0/tool.cwl                → cwl-store/tools/
    ├── search/1.0/tool.cwl
    ├── ingest/1.0/tool.cwl
    └── update/1.0/tool.cwl
```

Reprise de la convention du dépôt `cwl-assets` (elle-même alignée sur l'ADR-0010 /
EVO-42 de PID-FLOW). Trois règles en découlent, toutes vérifiées par `tests/test_cwl.py` :

- **Le nom de l'artefact est le nom du RÉPERTOIRE**, pas celui du fichier — les fichiers
  s'appellent tous `tool.cwl` ou `workflow.cwl`. C'est ce nom qui identifie la brique
  côté cwl-store, avec sa version : `(nom, version)` est unique, il n'y a pas de `latest`.
- **La classe doit correspondre au répertoire** : `class: Workflow` sous `workflows/`,
  `class: CommandLineTool` sous `tools/`. Une discordance est **rejetée au scan** par
  PID-FLOW (log ERROR + skip) — silencieusement, du point de vue de qui a poussé.
- **Les 3 tools sont PARTAGÉS** (`tools/<nom>/<version>/`), pas embarqués dans le
  workflow (`workflows/<nom>/<version>/tools/`). Le workflow les référence en relatif :
  `run: ../../../tools/search/1.0/tool.cwl`. C'est le bon choix ici parce qu'`update`
  ne participe à aucun workflow et que les lots suivants recomposeront les mêmes briques ;
  la règle cwl-assets est « interne tant qu'un seul workflow s'en sert, partagé dès 2 ».

**Version unique : `1.0`** pour les 4 artefacts. Rien ici n'a encore été enregistré côté
server, donc rien n'est figé — le jour où ça le sera, une modification de contrat imposera
un bump (pas d'écrasement possible à `(nom, version)` constant).

## Écart assumé vs cwl-assets : pas de script rsyncé

Le cas standard cwl-assets est un script Python déployé par `rsync` sous
`WORKER_PYTHON_SCRIPTS_ROOT`, appelé par `baseCommand: [<sous-rep>/<script>.py]` — le
worker réécrit ce chemin relatif en
`${WORKER_PYTHON_COMMAND} ${WORKER_PYTHON_SCRIPTS_ROOT}/<sous-rep>/<script>.py`.

Ici, `tiny_wae` est un **package Python installé** qui expose un **point d'entrée
console** (`[project.scripts]` du `pyproject.toml`) : `pip` génère un exécutable
`tiny-wae` dans le `bin/` de l'environnement d'installation, et c'est lui qu'appellent les
`baseCommand` — `baseCommand: [tiny-wae, search]`. Rien à rsyncer.

C'est un écart délibéré, pas un oubli — mais il déplace la contrainte de déploiement au
lieu de la supprimer : le worker n'a aucun script à recevoir, en revanche **la wheel
`tiny_wae` doit être installée dans le venv du worker**, et **le `bin/` de ce venv doit
être sur le PATH des jobs**. Les deux modèles exigent un déploiement, simplement pas le
même.

### Pourquoi `tiny-wae` et pas `python -m tiny_wae`

Les deux formes échappent à la réécriture du worker (elle ne s'applique qu'aux
`baseCommand` pointant un `.py` relatif) : dans les deux cas l'exécutable est résolu sur
le **PATH du job**. Mais la ressemblance s'arrête là.

`python` est le nom le plus surchargé du système. S'il se résout sur un autre interpréteur
que celui du venv, l'appel **réussit à démarrer** et échoue plus loin sur un
`No module named tiny_wae` — une erreur qui parle d'un module alors que le problème est un
interpréteur. `tiny-wae` est unique au projet : absent du PATH, il échoue immédiatement et
sans ambiguïté. À fragilité égale, on préfère l'échec franc à l'échec trompeur.

Mesuré : `cwltool` transmet au job **l'intégralité du PATH parent** (seuls `HOME`, `PWD` et
`TMPDIR` sont recréés). En local, `bin/tiny-wae` de l'environnement pixi est donc trouvé
sans rien déclarer — exactement comme `ruff` l'est. C'est ce qui permet à `just cwl-run` de
rester une seule ligne, sans le `pack` + réécriture `jq` que `bin/run-local.sh` doit faire
dans `cwl-assets` pour ses `baseCommand` relatifs.

⚠ **La contrepartie est côté ops** : il faut que le job du worker voie ce `bin/`. Si le
worker ne garantit que `WORKER_PYTHON_COMMAND` sans activer le venv, il faudra basculer sur
la convention native (wrappers `.py` sous `WORKER_PYTHON_SCRIPTS_ROOT`) — et porter aussi
l'équivalent de `bin/run-local.sh` pour que l'exécution locale survive.

Le hint de capability, lui, reste celui de la convention :

```yaml
hints:
  - class: SoftwareRequirement
    packages:
      - package: python
```

⚠ **Ce hint n'est pas décoratif** : un worker sans `python` dans ses `WORKER_CAPABILITIES`
**ne prend pas** la tâche. Elle reste en attente — pas en erreur. Si rien ne démarre, c'est
la première chose à regarder.

### Pourquoi pas `just` dans le `baseCommand`

La règle façade du projet (« `pixi` ne s'écrit jamais hors du `justfile` ») s'applique
aux recettes, à la doc et aux prompts d'agents — bref, à tout ce qui s'exécute
**dans ce dépôt, par une main ou un agent qui a `just` sous la main**. Un fichier
`.cwl` est destiné à un **exécuteur externe** (typiquement un worker PID-FLOW) qui ne
connaît ni ce dépôt, ni `just`, ni `pixi` — seulement l'environnement dans lequel le
`baseCommand` s'exécute. `tiny-wae <cmd>` est donc le seul appel qui a un sens depuis
l'extérieur ; ce n'est pas une entorse à la règle façade, c'est son domaine d'application
qui s'arrête à la frontière du dépôt. Ne pas « corriger » ces fichiers pour y mettre
`just` — ça ne s'exécuterait nulle part en dehors du développeur qui a le dépôt cloné.

## ⛔ Exigences CWL non supportées par PID-FLOW

**PID-FLOW ne supporte aujourd'hui ni `InlineJavascriptRequirement` ni
`EnvVarRequirement`, et n'évalue AUCUNE expression CWL.** Aucun des 4 fichiers ne les
déclare ni n'en contient, et il ne faut pas les y remettre : un tool qui les exige ne
tournerait pas chez le consommateur visé, alors même
que `cwltool --validate` (`just cwl`) reste **vert** en local — l'exécuteur de
développement est plus permissif que celui de production. C'est l'angle mort que couvre
`tests/test_cwl.py` (`test_aucun_cwl_ne_declare_d_exigence_non_supportee_par_pid_flow`),
qui balaie les 4 fichiers sous les deux formes CWL (clé de map, entrée `{class: …}` de
liste) et jusque dans les steps de workflow.

### Aucune expression CWL, même une simple référence de paramètre

`cwltool` résout parfaitement une **référence de paramètre** — le sous-ensemble restreint
que la spec CWL rend toujours disponible, sans exigence à déclarer. Vérifié dans le moteur
(`cwl_utils/expression.py`, `evaluator()`) : elle est résolue directement, le drapeau
`fullJS` (= `InlineJavascriptRequirement`) n'est consulté que dans la branche de repli.
Mesuré : avec l'exigence déclarée et un `node` délibérément saboté (`exit 127`), le run
reste vert — le moteur JS n'est jamais sollicité.

**Mais PID-FLOW, lui, ne les évalue pas** : le dépôt `cwl-assets` porte le constat noir sur
blanc (tool `AppendToFile`, TOOL-6 — un glob `$(inputs.input_file.basename)` « était une
expression et ne matchait rien », remplacé par un nom littéral), et aucun de ses 40 tools
n'utilise d'expression ailleurs que dans les tools legacy Docker. Le mode de défaillance
est le pire possible : la sortie n'est **pas capturée**, et **rien n'échoue**.

D'où la règle ici : **aucun `$(...)`, nulle part** (garde-fou :
`test_aucune_expression_cwl_dans_les_fichiers`, qui scanne le texte brut des 4 fichiers).
La seule conséquence concrète est dans le tool `search` : son `outputBinding.glob` est le
littéral `"acquisitions.json"`, tenu synchronisé avec le défaut de l'input `json_out` par
`test_search_glob_litteral_colle_au_default` — un lien qu'une expression aurait porté
gratuitement, et qu'il faut donc tester.

### `InlineJavascriptRequirement` — il désarme en plus un garde-fou

Sans lui, une expression mal formée est refusée avec un message explicite
(« *Syntax error in parameter reference … could be due to using Javascript code without
specifying InlineJavascriptRequirement* ») ; avec lui, la même expression part au moteur
JS et s'évalue silencieusement. C'est précisément ce message qui
doit sonner le jour où quelqu'un écrit du vrai JavaScript ici — parce que ce jour-là, le
tool cesse d'être exécutable par PID-FLOW.

### `EnvVarRequirement` — la variable vient du worker

`ingest`/`update` n'ont **aucune option `--data-root`** : la racine de stockage vient de
`settings.data_root` (`config/settings.yaml`), surchargeable par la variable
d'environnement `TINY_WAE_DATA_ROOT` (mécanisme `TINY_WAE_*` d'`adapters/config_io.py`).
Les tools posaient cette variable eux-mêmes, via un `EnvVarRequirement` alimenté par un
input `data_root` ; **les deux ont été retirés** — `TINY_WAE_DATA_ROOT` est désormais
**posée dans l'environnement du worker** PID-FLOW, hors CWL. Corollaire : ne pas
réintroduire l'input `data_root`, il n'aurait plus par quel moyen atteindre le process
(garde-fou : `test_aucun_cwl_ne_declare_d_input_data_root`).

⚠ **En local, une variable posée dans le shell appelant n'atteint PAS le job** : `cwltool`
n'expose au process qu'un environnement minimal. La recette `just cwl-run` passe donc
`--preserve-environment TINY_WAE_DATA_ROOT`, ce qui reproduit le comportement du worker.
Mesuré : sans l'option la variable arrive absente, avec elle elle arrive intacte, et son
absence pure et simple ne casse rien (repli sur `settings.data_root`). C'est exactement ce
que fait `bin/run-local.sh` dans `cwl-assets` pour `SPATIO_ROOT` — même contrainte, même
réponse.

## Codes de sortie et `successCodes`

Les CLI `search`/`ingest` partagent la même convention (`cli/exit_codes.py`) :
`0` OK · `1` FAILURE (échec métier, ≥ 1 item en échec) · `2` USAGE (config/usage
invalide) · `3` INCONCLUSIVE (amont injoignable / aucun item n'a abouti).

- **`search`** : `successCodes: [0]` uniquement. Un endpoint STAC injoignable
  (INCONCLUSIVE) ou une config invalide (USAGE) doivent arrêter le workflow — il n'y
  a rien à ingérer si la recherche a échoué.
- **`ingest`** : `successCodes: [0, 1]`. Un `FAILURE` (≥ 1 item en échec, mais au
  moins un succès) est un **résultat métier légitime** — le forcer en erreur CWL
  ferait échouer le workflow sur des runs par ailleurs sains (idempotence au grain
  item : les items ratés seront retentés au run suivant). `USAGE` (2) et
  `INCONCLUSIVE` (3, aucun item n'a abouti) restent des échecs CWL.

- **`update`** : `successCodes: [0, 1]`, même raisonnement que `ingest` mais
  avec un cas de plus. `update` renvoie `FAILURE` (1) aussi bien pour un échec
  métier classique (≥ 1 site en échec avec au moins un succès) que pour un **site
  vierge** (aucun manifeste connu, cf. `cli/update.py` — le CLI pointe alors vers
  `backfill`, hors périmètre d'`update`). Les deux cas restent un résultat légitime
  d'un run quotidien sur un parc en évolution (site ajouté à `sites.yaml` sans
  backfill préalable), pas un incident d'exécution — le forcer en erreur CWL
  casserait le run planifié sur un parc par ailleurs sain. `USAGE` (2) et
  `INCONCLUSIVE` (3, tous les échecs sont d'origine réseau et aucun site n'a
  abouti) restent des échecs CWL : un run qui ne fait QUE des erreurs réseau doit
  remonter en échec, c'est le CLI du cron, celui que personne ne regarde tourner.

## Racine de stockage et sorties

La racine de stockage se pilote par `TINY_WAE_DATA_ROOT` (cf. section précédente) — c'est
ce qui permet de pointer deux racines vierges et distinctes lors d'une comparaison run CWL
/ run CLI direct (oracle O2).

⚠ **`ingest` n'a AUCUNE sortie CWL déclarée** (`outputs: []`). Essayé puis retiré,
mesuré à l'exécution (oracle O2) : la spec CWL interdit un `outputBinding.glob`
commençant par `/`, or `TINY_WAE_DATA_ROOT` est justement pensée pour recevoir un chemin
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

Valide les 4 fichiers **un par un** (`cwltool --validate <fichier>`) — passer
plusieurs chemins d'un coup à `--validate` fait interpréter les arguments suivants
comme un job order, pas comme des tools à valider séparément. Intégré dans
`just check`.

Ce que `cwltool --validate` **ne couvre pas** — deux angles morts, tous deux comblés par
`tests/test_cwl.py` :

1. **Il ignore tout des CLI réels du projet.** Si une option est renommée dans
   `cli/search.py` ou `cli/ingest.py` sans toucher au tool correspondant, la validation
   reste verte et le workflow casse silencieusement à l'exécution. Le test confronte donc
   chaque `inputBinding.prefix` aux options réellement exposées par le CLI, via
   introspection `click`/`typer` (`typer.main.get_command`, pas un parsing de `--help`).
2. **Il est plus permissif que PID-FLOW.** Structure de dépôt, classe cohérente avec le
   répertoire, `label` = nom d'artefact, capability `python`, exigences interdites,
   absence d'expression, référence de tool partagé : `cwltool` accepte tout ça sans
   broncher, PID-FLOW non. Les tests `..._pid_flow` (et voisins) codifient ces règles —
   c'est la seule barrière avant le register.

## Run local (hors gate, réseau)

```
TINY_WAE_DATA_ROOT=/tmp/cwl-run-data just cwl-run assets/cwl/workflows/tiny-wae/1.0/workflow.cwl \
    --site A01 --from_date 2026-01-01 --to_date 2026-01-10 \
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

et comparer les ensembles `(item_id, statut)` des deux racines (manifestes
`run.json`, `adapters/manifests.py`).

## Run local du tool `update` (oracle O2 de `l0-06.2`, hors gate, réseau)

⚠ **`update` ne peut rien ingérer sur une racine totalement vierge** : sans
aucun manifeste connu, le site est déclaré « vierge » (`NoManifests` → exit 1,
pointant vers `backfill`) — ce n'est pas un bug, c'est la même logique que
`cli/update.py`. L'oracle « idempotence d'un run à l'autre » exige donc un
**amorçage préalable** par `ingest` avant le premier run du tool `update` :

```
TINY_WAE_DATA_ROOT=/tmp/cwl-update-data just run ingest \
    --site A01 --from <J-20> --to <J-1> \
    --sites-path config/sites.yaml --settings-path config/settings.yaml

TINY_WAE_DATA_ROOT=/tmp/cwl-update-data just cwl-run assets/cwl/tools/update/1.0/tool.cwl \
    --sites A01 \
    --sites_path config/sites.yaml --settings_path config/settings.yaml
# 1er run : rattrape la fenêtre [J-1, maintenant] laissée ouverte par l'amorçage —
# ingested/assets_read potentiellement > 0, c'est attendu.

TINY_WAE_DATA_ROOT=/tmp/cwl-update-data just cwl-run assets/cwl/tools/update/1.0/tool.cwl \
    --sites A01 \
    --sites_path config/sites.yaml --settings_path config/settings.yaml
# 2e run, quelques minutes après : c'est CE run que l'oracle mesure. Sur un parc
# stable, il doit rendre ingested == 0 et assets_read == 0 (idempotence, cf.
# STDERR "status=up_to_date").
```

Deux formulations plus courtes ont été essayées et rejetées (cf. `l0-06.2`) : lancer
le tool `update` sur la racine déjà peuplée de `l0-06.1` (fenêtre déjà close → il
retrouve du neuf, pas un test d'idempotence propre) et le lancer sur une
racine vierge sans amorçage (`NoManifests` dès le 1er run — rien à mesurer).
L'amorçage par `ingest` est donc une étape obligatoire du protocole, pas une
option.
