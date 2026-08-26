#!/usr/bin/env python3
"""scripts/check_cache.py — vérifie la présence et la conformité des 3 poids (l1-00).

VERSIONNÉ, pas jetable : c'est le consommateur qui rend les oracles de `l1-07` falsifiables
(cache chaud avant un run qui en dépend), et le SEUL autre script du projet autorisé à
parler à `huggingface_hub` en dehors de `fetch_models.py`.

Ne télécharge et n'instancie RIEN : `hf_hub_download(..., local_files_only=True)` ne fait
que résoudre un chemin dans le cache local (`HF_HOME`, lu depuis `config/settings.yaml`
comme dans `fetch_models.py`) — zéro requête réseau. Le sha256 relu depuis le fichier local
est comparé au sha256 ÉPINGLÉ de `_model_artifacts.py` : une existence de chemin ne suffit
pas (un `local_files_only=True` qui rendrait un chemin sans rien lire passerait un test
de seule existence — c'est la faille que cette vérification ferme, cf. oracle O2).

Sort en erreur en NOMMANT l'artefact manquant/corrompu et la commande de remède
(`just fetch-models`). Codes de sortie (`cli.exit_codes`) : 0 tous conformes ·
1 au moins un artefact manquant ou dont le sha256 diffère.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from _model_artifacts import ARTIFACTS, ModelArtifact
from tiny_wae.adapters.config_io import load_settings
from tiny_wae.cli import exit_codes

_HASH_CHUNK_BYTES = 8 * 1024 * 1024


def _prepare_hf_home() -> Path:
    """Charge `Settings` et pose `HF_HOME` — même contrat que `fetch_models.py`.

    Doit précéder tout import de `huggingface_hub` : ses chemins de cache se figent à
    l'import, depuis la variable d'environnement lue à cet instant.

    `HF_HUB_DISABLE_XET=1` : même contrat que `fetch_models.py` — sans lui, la résolution
    de chemin en cache (elle-même en cache chaud, donc sans réseau ici) reste cohérente
    avec le mode dans lequel le fichier a été écrit.
    """
    settings = load_settings()
    os.environ["HF_HOME"] = settings.hf_home
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    return Path(settings.hf_home)


def _sha256_of(path: Path) -> str:
    """Sha256 d'un fichier, lu par blocs — jamais chargé entièrement en mémoire."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_cached_path(artifact: ModelArtifact) -> Path | None:
    """Rend le chemin local de l'artefact SI présent dans le cache, sans réseau.

    `local_files_only=True` : aucune requête, même de vérification d'etag. Rend `None`
    (jamais d'exception non maîtrisée) si l'artefact n'est pas dans le cache.
    """
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import LocalEntryNotFoundError

    try:
        return Path(
            hf_hub_download(
                repo_id=artifact.repo_id,
                filename=artifact.filename,
                revision=artifact.revision,
                local_files_only=True,
            )
        )
    except LocalEntryNotFoundError:
        return None


def check_artifact(artifact: ModelArtifact) -> str | None:
    """Vérifie un artefact (présence + sha256). Rend `None` si conforme, sinon le motif."""
    local_path = _resolve_cached_path(artifact)
    if local_path is None or not local_path.exists():
        return f"absent du cache ({artifact.repo_id}@{artifact.revision[:12]})"
    actual_sha256 = _sha256_of(local_path)
    if actual_sha256 != artifact.sha256:
        return f"sha256 non conforme : attendu {artifact.sha256}, obtenu {actual_sha256}"
    return None


def main() -> int:
    """Vérifie les 3 artefacts, publie le verdict de chacun. Rend un code de sortie."""
    hf_home = _prepare_hf_home()
    print(f"HF_HOME = {hf_home}")
    failures: list[str] = []
    for artifact in ARTIFACTS:
        motif = check_artifact(artifact)
        if motif is None:
            print(f"OK   {artifact.name}")
        else:
            print(f"ECHEC {artifact.name} : {motif}")
            failures.append(artifact.name)
    if failures:
        print(f"{len(failures)} artefact(s) manquant(s) ou non conforme(s) : {failures}")
        print("Remède : just fetch-models")
        return exit_codes.FAILURE
    return exit_codes.OK


if __name__ == "__main__":
    raise SystemExit(main())
