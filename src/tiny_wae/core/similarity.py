"""core/similarity.py — métriques de similarité et de séparabilité, pures (zéro I/O).

⭐ Premier module de ``core/`` à importer ``numpy`` — vérifié avant écriture : aucun autre
module de ``core/`` ne le fait. Ce n'est pas une entorse à la règle de couches : celle-ci
interdit l'I/O et les frameworks, pas une bibliothèque de calcul, et ``numpy`` est au
contrat du paquet depuis le Lot 0.

Convention normative du chapeau ``l1-05`` (fait foi en cas d'écart avec toute autre fiche) :

- toute grandeur de **proximité** est une **similarité cosinus**, dans ``[-1, 1]`` ;
- toute grandeur de **dérive** est une **distance** ``1 − cosine``, dans ``[0, 2]`` ;
- le cas défavorable d'une similarité est son **minimum**, celui d'une dérive son
  **maximum** ;
- la silhouette se calcule sur la distance ``1 − cosine`` — jamais sur l'euclidienne, qui
  donnerait un nombre différent, plausible, et incomparable aux seuils actés (cf. O4b :
  valeur littérale gelée dans les tests pour qu'un changement de convention rougisse).

Portée : vecteurs et labels fournis par l'appelant (fabriqués dans les tests, lus sur disque
dans la campagne ``l1-05.3a``). Aucune lecture de fichier ni instanciation de modèle ici.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
from numpy.typing import NDArray


class ZeroVectorError(ValueError):
    """Levée quand ``cosine`` reçoit un vecteur de norme nulle.

    Un ``nan`` silencieux se propagerait dans toute une campagne sans jamais se signaler —
    l'oracle O2 exige explicitement une erreur typée, pas une valeur invalide qui passe.
    """


class DegenerateGroupsError(ValueError):
    """Levée quand les labels ne permettent pas de calculer la grandeur demandée.

    Deux cas dégénérés couverts par l'oracle O6 : un seul label distinct (aucune paire
    inter-groupe) ou aucun groupe de taille >= 2 (aucune paire intra-groupe). Dans les deux
    cas, une moyenne sur un ensemble vide diviserait par zéro — on préfère une erreur
    explicite à un ``nan`` ou une valeur inventée.
    """


class UnknownReferenceError(ValueError):
    """Levée quand ``trajectory_drift`` reçoit un mode ``reference`` non reconnu."""


@dataclass(frozen=True, slots=True)
class IntraInter:
    """Séparabilité d'un ensemble de vecteurs étiquetés.

    ``intra`` : similarité cosinus moyenne entre vecteurs du même label.
    ``inter`` : similarité cosinus moyenne entre vecteurs de labels différents.
    ``margin`` : ``intra - inter`` — numérateur du rapport « discrimination par seconde »
    de ``l1-04.5``.
    """

    intra: float
    inter: float
    margin: float


def cosine(a: NDArray[np.floating], b: NDArray[np.floating]) -> float:
    """Similarité cosinus entre deux vecteurs 1D, dans ``[-1, 1]``.

    Lève ``ZeroVectorError`` si l'un des deux vecteurs est nul (norme 0) : la division
    produirait un ``nan`` qui se propagerait silencieusement (oracle O2).
    """
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0.0 or norm_b == 0.0:
        raise ZeroVectorError("cosine: vecteur de norme nulle — similarité indéfinie")
    return float(np.dot(a, b) / (norm_a * norm_b))


def _cosine_similarity_matrix(vectors: NDArray[np.floating]) -> NDArray[np.floating]:
    """Matrice ``n x n`` des similarités cosinus par paire, vectorisée (pas de boucle Python).

    Nécessaire pour rester utilisable sur le corpus réel (~5 793 vecteurs, ~16,8 M de
    paires — mesuré, cf. ancrage de la fiche) : une double boucle Python serait la seule
    approche qui romprait la promesse « faisable en numpy vectorisé ».
    Lève ``ZeroVectorError`` si un vecteur du lot est nul (même garde que ``cosine``).
    """
    norms = np.linalg.norm(vectors, axis=1)
    if np.any(norms == 0.0):
        raise ZeroVectorError("similarité: au moins un vecteur du lot est de norme nulle")
    normalized = vectors / norms[:, np.newaxis]
    result: NDArray[np.floating] = normalized @ normalized.T
    return result


def intra_inter(vectors: NDArray[np.floating], labels: list[str]) -> IntraInter:
    """Séparabilité intra/inter-groupe d'un ensemble de vecteurs étiquetés.

    ``vectors`` : tableau ``(n, d)``. ``labels`` : un label par vecteur (n éléments).
    Lève ``DegenerateGroupsError`` si aucune paire intra (tous les groupes à un seul
    élément) ou aucune paire inter (un seul label distinct) n'existe — cf. oracle O6.
    """
    n = len(labels)
    sim = _cosine_similarity_matrix(vectors)
    labels_arr = np.asarray(labels)
    same = labels_arr[:, np.newaxis] == labels_arr[np.newaxis, :]
    upper = np.triu(np.ones((n, n), dtype=bool), k=1)
    intra_mask = same & upper
    inter_mask = ~same & upper
    if not np.any(intra_mask):
        raise DegenerateGroupsError(
            "intra_inter: aucune paire intra-groupe (tous les groupes sont des singletons)"
        )
    if not np.any(inter_mask):
        raise DegenerateGroupsError("intra_inter: un seul label distinct — pas de paire inter")
    intra = float(sim[intra_mask].mean())
    inter = float(sim[inter_mask].mean())
    return IntraInter(intra=intra, inter=inter, margin=intra - inter)


def silhouette(vectors: NDArray[np.floating], labels: list[str]) -> float:
    """Coefficient de silhouette moyen, dans ``[-1, 1]``, sur la distance ``1 - cosine``.

    ⭐ La distance employée est ``1 - cosine`` (convention du chapeau, revue v3 E-6) —
    jamais l'euclidienne, qui donnerait un nombre différent et incomparable au seuil de
    0,2 acté par les campagnes (cf. O4b, valeur littérale gelée dans les tests).
    Pour un point d'un groupe de taille 1, ``a(i)`` est indéfini : convention usuelle
    (scikit-learn), silhouette du point = 0 plutôt qu'une exception ponctuelle, car un
    site à un seul chip ne doit pas faire échouer toute la mesure.
    Lève ``DegenerateGroupsError`` si un seul label distinct (silhouette exige au moins
    deux groupes pour définir ``b(i)``).
    """
    labels_arr = np.asarray(labels)
    unique_labels = np.unique(labels_arr)
    if unique_labels.size < 2:
        raise DegenerateGroupsError("silhouette: un seul label distinct — b(i) indéfini")
    sim = _cosine_similarity_matrix(vectors)
    dist = 1.0 - sim
    n = len(labels)
    scores = np.zeros(n, dtype=np.float64)
    for i in range(n):
        own_label = labels_arr[i]
        own_mask = labels_arr == own_label
        own_mask[i] = False
        if not np.any(own_mask):
            scores[i] = 0.0
            continue
        a_i = float(dist[i, own_mask].mean())
        b_i = min(
            float(dist[i, labels_arr == other].mean())
            for other in unique_labels
            if other != own_label
        )
        scores[i] = 0.0 if max(a_i, b_i) == 0.0 else (b_i - a_i) / max(a_i, b_i)
    return float(scores.mean())


def trajectory_drift(
    vectors: NDArray[np.floating],
    dates: list[date],
    reference: str = "first",
) -> list[float]:
    """Dérive ``1 - cosine(v_i, v_ref)`` d'une trajectoire, triée par date croissante.

    Bornée ``[0, 2]`` — c'est une DISTANCE (convention du chapeau) : le cas défavorable
    d'une dérive est son MAXIMUM, jamais son minimum. La sortie est ordonnée par date
    croissante (les entrées ne sont pas supposées déjà triées).
    Seul ``reference="first"`` (le vecteur le plus ancien) est supporté ; toute autre
    valeur lève ``UnknownReferenceError`` plutôt que d'être ignorée silencieusement.
    """
    if reference != "first":
        raise UnknownReferenceError(f"trajectory_drift: reference inconnue: {reference!r}")
    if len(vectors) != len(dates):
        raise ValueError("trajectory_drift: vectors et dates doivent avoir la même longueur")
    order = np.argsort(np.asarray(dates))
    sorted_vectors = vectors[order]
    ref = sorted_vectors[0]
    return [1.0 - cosine(v, ref) for v in sorted_vectors]
