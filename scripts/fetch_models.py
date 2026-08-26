#!/usr/bin/env python3
"""scripts/fetch_models.py — télécharge les 3 artefacts de poids d'inférence (l1-00).

SEULE commande du projet autorisée à faire du réseau pour des poids — `just fetch-models`.
Hors de `just check` (ce n'est pas un test, c'est une opération d'approvisionnement).

Passe par `huggingface_hub.hf_hub_download` sur des révisions ÉPINGLÉES (jamais `wget`, ni
`revision="main"`) : le fichier atterrit sous `HF_HOME` et hérite donc de la garde
`HF_HUB_OFFLINE` posée ailleurs dans le pipeline (l1-02.3). `HF_HOME` est lu depuis
`config/settings.yaml` (clé `hf_home`, expansée par `adapters/config_io`) — jamais recalculé
ici.

Publie, pour chacun des 3 artefacts : chemin local, taille et sha256 — c'est cette sortie
que `check_cache.py` revérifie ensuite sans retélécharger (O1/O2 de la fiche).

Codes de sortie (`cli.exit_codes`) : 0 OK · 3 réseau injoignable (aucun artefact modifié en
cas d'échec partiel — `hf_hub_download` télécharge dans un fichier temporaire puis renomme,
jamais d'écriture partielle visible sous HF_HOME).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from _model_artifacts import ARTIFACTS, ModelArtifact
from tiny_wae.adapters.config_io import load_settings
from tiny_wae.cli import exit_codes

# Taille de bloc de lecture pour le hachage — évite de charger un fichier de plusieurs Go
# en mémoire (le ckpt Clay pèse ~5 Go).
_HASH_CHUNK_BYTES = 8 * 1024 * 1024


def _prepare_hf_home() -> Path:
    """Charge `Settings` et pose `HF_HOME` dans l'environnement du PROCESSUS courant.

    Doit être appelé AVANT tout import de `huggingface_hub` : la bibliothèque fige ses
    chemins de cache à l'import, depuis la variable d'environnement lue à cet instant.

    ⭐ Pose aussi `HF_HUB_DISABLE_XET=1` — constat à l'implémentation (26/08, réseau réel) :
    le backend Xet (protocole CAS chunké, utilisé par défaut par `huggingface_hub>=0.34`
    pour les gros fichiers) échoue de façon répétée dans cet environnement
    (`Connection reset by peer` sur `.../xet-read-token/...`, 5 tentatives puis abandon),
    alors que le téléchargement HTTP classique (résolution LFS + `Range`) réussit sans
    accroc sur les mêmes URLs. Ne pas imposer cette variable ferait échouer `O1` sur un
    problème de transport sans rapport avec la conformité des poids eux-mêmes.
    """
    settings = load_settings()
    os.environ["HF_HOME"] = settings.hf_home
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    return Path(settings.hf_home)


def _sha256_of(path: Path) -> str:
    """Sha256 d'un fichier, lu par blocs (jamais chargé entièrement en mémoire)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _human_mb(num_bytes: int) -> str:
    """Formate une taille en octets en Mo décimal, une décimale (lisible en console)."""
    return f"{num_bytes / 1_000_000:.1f} Mo"


def _fetch_one(artifact: ModelArtifact) -> tuple[Path, int, str]:
    """Télécharge un artefact (révision épinglée), rend (chemin local, taille, sha256)."""
    from huggingface_hub import hf_hub_download

    local_path = Path(
        hf_hub_download(
            repo_id=artifact.repo_id,
            filename=artifact.filename,
            revision=artifact.revision,
        )
    )
    size_bytes = local_path.stat().st_size
    sha256 = _sha256_of(local_path)
    return local_path, size_bytes, sha256


def main() -> int:
    """Télécharge les 3 artefacts, publie taille + sha256 de chacun. Rend un code sortie."""
    hf_home = _prepare_hf_home()
    print(f"HF_HOME = {hf_home}")
    for artifact in ARTIFACTS:
        print(f"-- {artifact.name} ({artifact.repo_id}@{artifact.revision[:12]}) --")
        try:
            local_path, size_bytes, sha256 = _fetch_one(artifact)
        except Exception as exc:  # noqa: BLE001 — réseau injoignable, code 3 nommé
            print(f"   ECHEC réseau : {exc}")
            return exit_codes.INCONCLUSIVE
        print(f"   chemin  : {local_path}")
        print(f"   taille  : {_human_mb(size_bytes)} ({size_bytes} octets)")
        print(f"   sha256  : {sha256}")
    return exit_codes.OK


if __name__ == "__main__":
    raise SystemExit(main())
