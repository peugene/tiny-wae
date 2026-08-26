"""Tests core/similarity.py (l1-05.1).

Couvre l'oracle de la fiche :
- O1 : cosine sur cas littéraux (identiques, orthogonaux, opposés).
- O2 : cosine sur un vecteur nul -> erreur typée.
- O3 : intra_inter sur deux groupes séparés (marge > 0,5) ET sur du bruit sans structure
  (|marge| < 0,1) — le témoin négatif n'est pas optionnel (cf. Notes de la fiche).
- O4 : silhouette sur les deux mêmes jeux (> 0,5 séparé, |silhouette| < 0,05 aléatoire).
- O4b : silhouette sur 4 vecteurs littéraux, valeur calculée à la main sur 1 - cosine
  (== 11/21 exactement, cf. calcul détaillé ci-dessous) — seul témoin qui rougit si la
  distance change de convention (une silhouette euclidienne donnerait un autre nombre :
  les 4 vecteurs sont unitaires donc euclidien == sqrt(2 * (1-cosine)), transformation non
  linéaire qui change le ratio (b-a)/max(a,b)).
- O5 : trajectory_drift croissant sur une suite qui s'éloigne, non monotone sur une suite
  qui oscille.
- O6 : cas dégénérés (groupe à un seul élément, labels tous identiques) -> erreur typée,
  jamais de division par zéro.

Politique de test du lot (cf. fiche) : pas de paramétrage sur des dizaines de bruits — un
seed fixe par cas, choisi pour que les deux sens de chaque oracle passent avec marge.
"""

from __future__ import annotations

from datetime import date
from itertools import pairwise

import numpy as np
import pytest

from tiny_wae.core.similarity import (
    DegenerateGroupsError,
    UnknownReferenceError,
    ZeroVectorError,
    cosine,
    intra_inter,
    silhouette,
    trajectory_drift,
)


def test_cosine_o1_cas_litteraux() -> None:
    """O1 : identiques -> 1,0 ; orthogonaux -> 0,0 ; opposés -> -1,0, au 1e-9 près."""
    a = np.array([1.0, 0.0])
    assert cosine(a, a) == pytest.approx(1.0, abs=1e-9)
    assert cosine(a, np.array([0.0, 1.0])) == pytest.approx(0.0, abs=1e-9)
    assert cosine(a, np.array([-1.0, 0.0])) == pytest.approx(-1.0, abs=1e-9)


def test_cosine_o2_vecteur_nul_leve_erreur_typee() -> None:
    """O2 : un vecteur nul lève ZeroVectorError, jamais un nan silencieux."""
    with pytest.raises(ZeroVectorError):
        cosine(np.array([0.0, 0.0]), np.array([1.0, 0.0]))


def _groupes_separes() -> tuple[np.ndarray, list[str]]:
    """Deux groupes fabriqués sur deux directions orthogonales bruitées (seed fixe)."""
    rng = np.random.default_rng(0)
    dim = 16
    n = 30
    base_a = np.zeros(dim)
    base_a[0] = 1.0
    base_b = np.zeros(dim)
    base_b[1] = 1.0
    noise_scale = 0.05
    group_a = base_a + rng.normal(scale=noise_scale, size=(n, dim))
    group_b = base_b + rng.normal(scale=noise_scale, size=(n, dim))
    vectors = np.vstack([group_a, group_b])
    labels = ["A"] * n + ["B"] * n
    return vectors, labels


def _vecteurs_aleatoires_sans_structure() -> tuple[np.ndarray, list[str]]:
    """Mêmes labels que les groupes séparés, mais vecteurs tirés au hasard sans structure.

    Témoin négatif de O3/O4 : une métrique qui rendrait un score élevé ici invaliderait
    toute la campagne, sans que ça se voie — c'est le cas que la fiche interdit de sauter.
    """
    rng = np.random.default_rng(0)
    dim = 16
    n = 30
    vectors = rng.normal(size=(2 * n, dim))
    labels = ["A"] * n + ["B"] * n
    return vectors, labels


def test_intra_inter_o3_deux_sens() -> None:
    """O3 : marge > 0,5 sur des groupes séparés ; |marge| < 0,1 sur du bruit (témoin négatif)."""
    vectors, labels = _groupes_separes()
    result = intra_inter(vectors, labels)
    assert result.margin > 0.5

    noise_vectors, noise_labels = _vecteurs_aleatoires_sans_structure()
    noise_result = intra_inter(noise_vectors, noise_labels)
    assert abs(noise_result.margin) < 0.1


def test_silhouette_o4_deux_sens() -> None:
    """O4 : silhouette > 0,5 sur des groupes séparés ; |silhouette| < 0,05 sur du bruit."""
    vectors, labels = _groupes_separes()
    assert silhouette(vectors, labels) > 0.5

    noise_vectors, noise_labels = _vecteurs_aleatoires_sans_structure()
    assert abs(silhouette(noise_vectors, noise_labels)) < 0.05


def test_silhouette_o4b_valeur_litterale_gelee_sur_1_moins_cosine() -> None:
    """O4b : 4 vecteurs littéraux (2 groupes de 2), silhouette calculée à la main == 11/21.

    Vecteurs unitaires : v1=(1,0), v2=(3/5,4/5) [groupe A], v3=(0,1), v4=(-4/5,3/5)
    [groupe B]. Similarités cosinus : A-A = 0,6 ; B-B = 0,6 ; croisées = 0, -0,8, 0,8, 0.
    Distances (1-cosine) : d12=0,4 ; d34=0,4 ; d13=1 ; d14=1,8 ; d23=0,2 ; d24=1.
    a(i) = distance à l'unique autre point du même groupe (groupes de taille 2) :
    a1=a2=a3=a4=0,4. b(i) = moyenne des distances vers l'autre groupe :
    b1=mean(d13,d14)=1,4 ; b2=mean(d23,d24)=0,6 ; b3=mean(d13,d23)=0,6 ; b4=mean(d14,d24)=1,4.
    s(i)=(b-a)/max(a,b) : s1=1/1,4=5/7 ; s2=0,2/0,6=1/3 ; s3=1/3 ; s4=5/7.
    Moyenne = (2*5/7 + 2*1/3)/4 = (44/21)/4 = 11/21 = 0,5238095238095238.
    Si la distance utilisée était l'euclidienne, ces 4 vecteurs étant unitaires,
    euclidien = sqrt(2*(1-cosine)) — transformation non linéaire qui change le ratio
    (b-a)/max(a,b) : cette valeur littérale rougirait sous ce changement de convention.
    """
    vectors = np.array(
        [
            [1.0, 0.0],
            [3.0 / 5.0, 4.0 / 5.0],
            [0.0, 1.0],
            [-4.0 / 5.0, 3.0 / 5.0],
        ]
    )
    labels = ["A", "A", "B", "B"]
    assert silhouette(vectors, labels) == pytest.approx(11.0 / 21.0, abs=1e-9)


def test_trajectory_drift_o5_croissant_puis_non_monotone() -> None:
    """O5 : suite qui s'éloigne régulièrement -> monotone croissante ; oscillante -> non."""
    dim = 8
    origin = np.zeros(dim)
    origin[0] = 1.0
    dates = [date(2026, 1, i + 1) for i in range(5)]

    # S'éloigne régulièrement : l'angle avec l'origine croît, le vecteur s'incline de
    # plus en plus vers un deuxième axe orthogonal.
    away_vectors = np.array(
        [
            np.cos(theta) * np.array([1.0] + [0.0] * (dim - 1)) + np.sin(theta) * np.eye(dim)[1]
            for theta in [0.0, 0.2, 0.5, 0.9, 1.4]
        ]
    )
    away_drift = trajectory_drift(away_vectors, dates, reference="first")
    assert all(a < b for a, b in pairwise(away_drift))

    # Oscille autour de l'origine : l'angle va et vient.
    oscillating_vectors = np.array(
        [
            np.cos(theta) * np.array([1.0] + [0.0] * (dim - 1)) + np.sin(theta) * np.eye(dim)[1]
            for theta in [0.0, 0.6, 0.1, 0.7, 0.05]
        ]
    )
    oscillating_drift = trajectory_drift(oscillating_vectors, dates, reference="first")
    assert not all(a < b for a, b in pairwise(oscillating_drift))


def test_trajectory_drift_reference_inconnue_leve_erreur_typee() -> None:
    """UnknownReferenceError si reference != 'first' — jamais ignoré silencieusement."""
    vectors = np.array([[1.0, 0.0], [0.0, 1.0]])
    dates = [date(2026, 1, 1), date(2026, 1, 2)]
    with pytest.raises(UnknownReferenceError):
        trajectory_drift(vectors, dates, reference="mean")


def test_o6_groupe_a_un_seul_element_leve_erreur_typee() -> None:
    """O6 : tous les groupes sont des singletons -> DegenerateGroupsError, pas de nan."""
    vectors = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
    labels = ["A", "B", "C"]
    with pytest.raises(DegenerateGroupsError):
        intra_inter(vectors, labels)


def test_o6_labels_tous_identiques_leve_erreur_typee() -> None:
    """O6 : un seul label distinct -> DegenerateGroupsError pour intra_inter et silhouette."""
    vectors = np.array([[1.0, 0.0], [0.9, 0.1], [0.8, 0.2]])
    labels = ["A", "A", "A"]
    with pytest.raises(DegenerateGroupsError):
        intra_inter(vectors, labels)
    with pytest.raises(DegenerateGroupsError):
        silhouette(vectors, labels)
