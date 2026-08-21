"""Test sanité du scaffold — à remplacer par les vrais tests dès la première fiche."""

from tiny_wae import __version__


def test_version() -> None:
    """Le package s'importe et expose une version."""
    assert __version__
