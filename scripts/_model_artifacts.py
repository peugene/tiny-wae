"""scripts/_model_artifacts.py — catalogue des 3 artefacts de poids d'inférence (l1-00).

Source de vérité UNIQUE, partagée par `fetch_models.py` (télécharge) et `check_cache.py`
(vérifie) : c'est ce qui rend la garde réseau unique et cohérente dans les deux sens. Les
révisions sont ÉPINGLÉES (sha commit / sha de repo HF) — jamais `revision="main"`, qui
romprait la reproductibilité d'une exécution à l'autre.

Le sha256 attendu de chaque artefact a été relevé une fois, à l'implémentation de cette
fiche, à partir d'un téléchargement réel (`just fetch-models`, 26/08/2026) — c'est lui que
`check_cache.py` revérifie ensuite, sans retélécharger. Les trois valeurs correspondent à
l'`x-linked-etag` publié par l'API Hugging Face pour chaque fichier (recoupement fait à la
main avant de les épingler ici).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    """Un fichier de poids sur Hugging Face Hub, à une révision de repo épinglée."""

    name: str
    repo_id: str
    filename: str
    revision: str
    sha256: str


ARTIFACTS: tuple[ModelArtifact, ...] = (
    # Clay v1.5 (checkpoint principal) — apache-2.0. Le quickstart officiel propose un
    # `wget` direct : on ne le suit pas, `hf_hub_download` met le fichier sous HF_HOME et
    # donc sous la garde HF_HUB_OFFLINE (cf. fiche, section Contexte).
    ModelArtifact(
        name="clay-v1.5",
        repo_id="made-with-clay/Clay",
        filename="v1.5/clay-v1.5.ckpt",
        revision="70200ebcccdf67bf2a0cb9984c77ddee26c10ed2",
        sha256="21432069250b9b3f9a65ffd0071c5ad56b793247285ab0604edf7f531d4798d0",
    ),
    # TerraMind small — apache-2.0, poids via TerraTorch en amont (terramind_register.py).
    ModelArtifact(
        name="terramind-1.0-small",
        repo_id="ibm-esa-geospatial/TerraMind-1.0-small",
        filename="TerraMind_v1_small.pt",
        revision="960f7549bfe9d7a08946860042f83badd604c779",
        sha256="755e9cce9483fd61334ef66c79f805406db5151a8b44a685c8fbbe023c684701",
    ),
    # Teacher SAM de ClayMAE.__init__ (timm.create_model(..., pretrained=True)) — poids
    # mort en inférence (~360 Mo) mais instancié quand même par claymodel. Non contournable
    # sans patcher claymodel (cf. Notes de la fiche) : on le télécharge, on le consigne.
    ModelArtifact(
        name="samvit-teacher",
        repo_id="timm/samvit_base_patch16.sa1b",
        filename="model.safetensors",
        revision="c6db726d87cbba7788e026776b46c5db3aa1594b",
        sha256="31a9f4edc394c5ae7a96045576570189a354ada86094a5842bcc9a05a8939ea2",
    ),
)
