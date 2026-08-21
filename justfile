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

# types (mypy strict sur src/ — le filet n°1 pour du code écrit par agents)
types:
    pixi run mypy src

# tests (pytest)
test:
    pixi run pytest

# exécute un CLI du projet (ex. just run ingest --help)
run *args:
    pixi run python -m tiny_wae {{args}}

# exécute un script de scripts/ dans l'environnement du projet
# (ex. just script record_stac_fixtures --sites C07) — évite tout `python …` à la main.
script name *args:
    pixi run python scripts/{{name}}.py {{args}}

# smoke : le pipeline réel sur un périmètre minuscule (à câbler dès le Lot 0)
smoke:
    pixi run python scripts/smoke.py

# tableau de bord du backlog (ne pas éditer etat.html à la main)
dashboard:
    pixi run python scripts/backlog.py dashboard --project "tiny-wae"

# md → html : just md2html _roadmap.md roadmap.html "Titre"
md2html src dest title="Doc" banner="":
    pixi run python scripts/backlog.py md2html {{src}} {{dest}} "{{title}}" "{{banner}}"

# ⭐ lint + types + tests + smoke = définition de « fini ». À lancer AVANT de dire « fini ».
check:
    just lint && just types && just test && just smoke
