# justfile — tiny-wae  (lanceur de commandes ; cf. la fiche just-command-runner du kit)
# ⭐ Règle du kit : le gestionnaire d'environnement (pixi) est un DÉTAIL D'IMPLÉMENTATION
# caché derrière ces recettes. Aucune fiche, doc ou agent n'écrit `pixi run` : toujours `just …`.
# Le jour d'une bascule pixi↔uv, on ne touche QUE ce fichier (+ CI).

# Liste les recettes (recette par défaut : `just` sans argument).
default:
    @just --list

# installe/synchronise l'environnement (lockfile pixi)
install:
    pixi install

# dépendances seules (PostgreSQL + pgvector)
db:
    docker compose up -d

# arrêt (la base persiste dans le volume)
down:
    docker compose down

# reset base : volume supprimé, état connu
reset:
    docker compose down -v && docker compose up -d

# requête SQL rapide (ex. just psql "select 1")
psql sql:
    docker compose exec -T db psql -U app -d app -c "{{sql}}"

# style + lint (ruff : format + check)
lint:
    pixi run ruff format --check . && pixi run ruff check .

# corrige automatiquement ce qui peut l'être
fmt:
    pixi run ruff format . && pixi run ruff check --fix .

# types (mypy strict — le filet n°1 pour du code écrit par agents)
# ⚠ AUCUN chemin ici : un chemin en ligne de commande PRIME sur `files=` de pyproject.toml.
# C'est ce qui a fait que le gate n'analysait que src/ alors que la config demandait déjà
# src/ ET tests/ (constat de out-01) — le périmètre se règle dans pyproject.toml, ici on
# se contente de lancer mypy.
types:
    pixi run mypy

# tests (pytest) — accepte des arguments pytest (ex. just test -k concurrent -x)
test *args:
    pixi run pytest {{args}}

# exécute un CLI du projet (ex. just run ingest --help)
run *args:
    pixi run python -m tiny_wae {{args}}

# exécute un script de scripts/ dans l'environnement du projet
# (ex. just script record_stac_fixtures --sites C07) — évite tout `python …` à la main.
script name *args:
    pixi run python scripts/{{name}}.py {{args}}

# relevé RÉSEAU des tuiles de référence + calcul des grilles (l0-01.3, écrit sites.yaml)
# (ex. just survey-tiles -- --sites A01,C07 — re-passe ciblée après correction de coordonnées)
survey-tiles *args:
    pixi run python scripts/survey_tiles.py {{args}}

# aide à la revue humaine du centrage des sites (l0-03.H) : GeoJSON des emprises + page
# de liens vers le Copernicus Browser et OSM. Ne valide rien — outille l'œil humain.
review-sites *args:
    pixi run python scripts/site_review.py {{args}}

# smoke : le pipeline réel sur un périmètre minuscule (à câbler dès le Lot 0)
smoke:
    pixi run python scripts/smoke.py

# tableau de bord du backlog (ne pas éditer etat.html à la main)
dashboard:
    pixi run python scripts/backlog.py dashboard --project "tiny-wae"

# feuille de route : index des lots + une page par lot (états, sommaire, navigation)
lots:
    pixi run python scripts/backlog.py lots --project "tiny-wae"

# md → html : just md2html _roadmap.md roadmap.html "Titre"
md2html src dest title="Doc" banner="":
    pixi run python scripts/backlog.py md2html {{src}} {{dest}} "{{title}}" "{{banner}}"

# couverture — HORS gate, à la demande. Sert à repérer un module oublié, pas à produire
# un pourcentage à défendre.
coverage:
    pixi run pytest --cov=tiny_wae --cov-report=term-missing:skip-covered --cov-report=

# hygiène des dépendances : déclarée non utilisée, utilisée non déclarée, transitive
# utilisée directement. Angle mort de ruff ET de mypy — c'est ce défaut qui avait laissé
# `affine` hors du contrat de la wheel.
# `src` SEUL : `scripts/` n'est pas dans la wheel, ses dépendances (markdown…) sont des
# dépendances de DEV déclarées côté pixi, que deptry ne lit pas — l'y inclure produirait
# un faux positif permanent.
deptry:
    pixi run deptry src

# validation statique des tools/workflow CWL (cwltool --validate, un fichier à la fois :
# passer plusieurs chemins à --validate fait interpréter les suivants comme job order).
cwl:
    pixi run cwltool --validate assets/cwl/tools/search/1.0/tool.cwl
    pixi run cwltool --validate assets/cwl/tools/ingest/1.0/tool.cwl
    pixi run cwltool --validate assets/cwl/tools/update/1.0/tool.cwl
    pixi run cwltool --validate assets/cwl/workflows/tiny-wae/1.0/workflow.cwl

# exécution RÉELLE d'un tool/workflow CWL (hors gate — fait du réseau)
# ex. TINY_WAE_DATA_ROOT=/tmp/cwl-data just cwl-run assets/cwl/workflows/tiny-wae/1.0/workflow.cwl …
# --preserve-environment : cwltool n'expose au job qu'un environnement minimal, une variable
# posée dans le shell appelant ne l'atteint PAS sans ça (mesuré). C'est ce qui simule en local
# le worker PID-FLOW, où TINY_WAE_DATA_ROOT est posée par l'exécuteur — les .cwl ne la portent
# plus (EnvVarRequirement non supporté par PID-FLOW, cf. assets/cwl/README.md).
cwl-run file *args:
    pixi run cwltool --preserve-environment TINY_WAE_DATA_ROOT --outdir /tmp/cwl-run-out {{file}} {{args}}

# ⭐ lint + types + tests + smoke + cwl = définition de « fini ». À lancer AVANT de dire « fini ».
check:
    just lint && just types && just deptry && just test && just smoke && just cwl
