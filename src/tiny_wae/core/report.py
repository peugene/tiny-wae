"""core/report.py — agrégation PURE des rapports d'ingestion (l0-04.2).

⚠ Décision d'ancrage n°1 de la fiche (résolue ICI) : ``core/`` ne peut pas importer
``adapters/manifests.Manifest`` sans casser la règle de couche. La solution retenue est le
**``Protocol`` structurel local** : ``ManifestLike`` ci-dessous ne fait que NOMMER les
attributs consommés par ce module. N'importe quelle dataclass qui les porte — en premier
lieu ``adapters.manifests.Manifest``, sans jamais l'importer — le satisfait au sens du
« duck typing statique » de mypy : l'appelant (``cli/report.py``) passe ses vrais
``Manifest`` directement, aucune conversion, aucun import de ce module vers ``adapters/``.

Toutes les fonctions ici sont pures : entrées déjà chargées (listes de manifestes/dicts de
compteurs), sortie = valeurs Python ou chaîne Markdown. Aucun accès disque, aucun réseau.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

# Les 6 statuts normatifs (chapeau l0-02) — recopiés en ANCRAGE, jamais redéfinis
# différemment (cf. adapters/manifests.RUN_STATUSES, la même énumération).
RUN_STATUSES: tuple[str, ...] = (
    "ingested",
    "rejected_clouds",
    "rejected_invalid",
    "rejected_nodata",
    "failed",
    "skipped",
)

# Fichiers attendus au manifeste d'un item ingéré (chip 10 m, chip 20 m, masque SCL).
EXPECTED_FILES: tuple[str, ...] = ("chip.tif", "chip_20m.tif", "scl.tif")

# Classes SCL mises en avant par l'instrument V3 différé (2 = ombre de nuage, 11 = neige).
SCL_HIGHLIGHT_CLASSES: tuple[str, ...] = ("2", "11")

# Seuil légitime unique de la recette (chapeau l0-04, critère 4) : failed / found_tile.
FAILED_PCT_MAX = 1.0


class ManifestLike(Protocol):
    """Attributs de ``Manifest`` réellement lus par ce module (Protocol structurel local,
    décision d'ancrage n°1 ci-dessus) : toute dataclass qui les porte convient, sans
    import d'``adapters``.

    ⚠ Déclarés en ``@property`` (membres EN LECTURE SEULE, cf. PEP 544) et non en simples
    annotations : un ``Manifest`` (``frozen=True``) expose ses champs comme des attributs
    **non réassignables** — mypy en fait des « read-only attributes » côté implémentation,
    incompatibles avec un membre de Protocol en simple annotation (qui exige un attribut
    RÉASSIGNABLE, donc invariant en écriture). Sans ce détail, ``Manifest`` échoue le
    matching structurel avec un message opaque (« expected settable variable, got
    read-only attribute ») — mesuré ici, pas déduit à l'avance.
    """

    @property
    def item_id(self) -> str: ...
    @property
    def status(self) -> str: ...
    @property
    def files(self) -> list[str]: ...
    @property
    def content_hashes(self) -> dict[str, str]: ...
    @property
    def grid_hash(self) -> str: ...
    @property
    def chip_nodata_pct(self) -> float: ...
    @property
    def scl_class_counts(self) -> dict[str, int]: ...
    @property
    def bytes_written(self) -> int: ...
    @property
    def datetime(self) -> str: ...


@dataclass(frozen=True, slots=True)
class IntegrityIssue:
    """Une violation du critère d'intégrité (O3 du chapeau l0-04) sur UN item ingéré."""

    item_id: str
    cause: str


@dataclass(frozen=True, slots=True)
class SiteReport:
    """Rapport agrégé d'un site — tout ce qu'il faut pour une ligne + une section détail."""

    site_id: str
    counters: dict[str, int]
    conservation_ok: bool
    failed_pct: float
    integrity_issues: tuple[IntegrityIssue, ...]
    scl_class_counts: dict[str, int]
    bytes_written: int

    @property
    def integrity_ok(self) -> bool:
        """Verdict global du critère d'intégrité : ROUGE si au moins un item fautif."""
        return not self.integrity_issues

    @property
    def ingested_ratio(self) -> float:
        """``ingested / found_tile`` — 0.0 si ``found_tile`` == 0 (site jamais instruit)."""
        found_tile = self.counters.get("found_tile", 0)
        if found_tile == 0:
            return 0.0
        return self.counters["ingested"] / found_tile


@dataclass(frozen=True, slots=True)
class CompletenessResult:
    """Écart entre les ids manifestés (arbitrage n°2) et les ids attendus de la source."""

    site_id: str
    missing: frozenset[str]
    extra: frozenset[str]

    @property
    def ok(self) -> bool:
        """Tolérance 0 (fiche) : OK ssi aucun id manquant ET aucun id en trop."""
        return not self.missing and not self.extra


def check_conservation(counters: dict[str, int]) -> bool:
    """Vérifie les deux invariants de conservation du chapeau l0-02 sur un ``counters``
    déjà agrégé : ``found_stac == skipped_scene_cloud + off_tile + found_tile`` ET
    ``found_tile == somme des 6 statuts``. Rend ``False`` (jamais d'exception) — c'est un
    verdict de rapport, pas une garde d'écriture (celle-ci vit déjà dans
    ``adapters.manifests.write_run``)."""
    envelope_sum = counters["skipped_scene_cloud"] + counters["off_tile"] + counters["found_tile"]
    status_sum = sum(counters[status] for status in RUN_STATUSES)
    return counters["found_stac"] == envelope_sum and counters["found_tile"] == status_sum


def compute_failed_pct(counters: dict[str, int]) -> float:
    """``100 * failed / found_tile`` — 0.0 si ``found_tile`` == 0 (division évitée,
    jamais de site « en échec » faute d'avoir été instruit)."""
    found_tile = counters.get("found_tile", 0)
    if found_tile == 0:
        return 0.0
    return 100.0 * counters["failed"] / found_tile


def check_integrity(
    manifest: ManifestLike, *, current_grid_hash: str, chip_nodata_pct_max: float
) -> list[str]:
    """Vérifie le critère d'intégrité (O3, chapeau l0-04) pour UN manifeste ``ingested``,
    à partir des seuls champs du manifeste (aucune relecture de raster) :
    - les 3 fichiers attendus (``EXPECTED_FILES``) sont listés dans ``files`` ;
    - chaque fichier listé porte une entrée dans ``content_hashes`` ;
    - ``grid_hash`` == la grille COURANTE du site (détecte les chips orphelins d'une
      correction de coordonnées — un ``grid_hash`` périmé est une intégrité rompue même si
      les 3 fichiers existent) ;
    - ``chip_nodata_pct`` sous le seuil configuré.

    Rend la liste des causes (chaînes factuelles, une par violation) — liste vide == OK.
    Plusieurs causes peuvent coexister sur le même item ; toutes sont rendues, pas
    seulement la première trouvée.
    """
    causes: list[str] = []

    missing_files = [name for name in EXPECTED_FILES if name not in manifest.files]
    if missing_files:
        causes.append(f"fichiers manquants: {missing_files}")

    missing_hashes = [name for name in manifest.files if name not in manifest.content_hashes]
    if missing_hashes:
        causes.append(f"content_hashes manquants: {missing_hashes}")

    if manifest.grid_hash != current_grid_hash:
        causes.append(
            f"grid_hash périmé: {manifest.grid_hash[:8]}… != courant {current_grid_hash[:8]}…"
        )

    if manifest.chip_nodata_pct >= chip_nodata_pct_max:
        causes.append(f"chip_nodata_pct={manifest.chip_nodata_pct} >= seuil {chip_nodata_pct_max}")

    return causes


def _merge_scl_class_counts(manifests: Sequence[ManifestLike]) -> dict[str, int]:
    """Somme ``scl_class_counts`` (par classe) sur une liste de manifestes ``ingested``."""
    totals: dict[str, int] = {}
    for manifest in manifests:
        for scl_class, count in manifest.scl_class_counts.items():
            totals[scl_class] = totals.get(scl_class, 0) + count
    return totals


def build_site_report(
    site_id: str,
    counters: dict[str, int],
    manifests: Sequence[ManifestLike],
    *,
    current_grid_hash: str,
    chip_nodata_pct_max: float,
) -> SiteReport:
    """Construit le ``SiteReport`` d'un site : conservation, ``failed_pct``, intégrité (sur
    les seuls manifestes ``ingested``, item par item), agrégat SCL, octets stockés.

    ``counters`` est le résultat déjà agrégé (``adapters.manifests.aggregate_counters`` —
    somme des runs, donnée de VOLUME, cf. sa docstring) ; ``manifests`` est la liste
    complète des manifestes du site (``adapters.manifests.list_for_site``).
    """
    ingested = [m for m in manifests if m.status == "ingested"]
    issues: list[IntegrityIssue] = []
    for manifest in ingested:
        for cause in check_integrity(
            manifest, current_grid_hash=current_grid_hash, chip_nodata_pct_max=chip_nodata_pct_max
        ):
            issues.append(IntegrityIssue(item_id=manifest.item_id, cause=cause))

    return SiteReport(
        site_id=site_id,
        counters=dict(counters),
        conservation_ok=check_conservation(counters),
        failed_pct=compute_failed_pct(counters),
        integrity_issues=tuple(issues),
        scl_class_counts=_merge_scl_class_counts(ingested),
        bytes_written=sum(m.bytes_written for m in ingested),
    )


def check_completeness(
    site_id: str, manifest_ids: set[str], source_ids: set[str]
) -> CompletenessResult:
    """Compare l'ensemble EXACT des ids manifestés (``item_ids_for_site``, arbitrage n°2)
    à l'ensemble des ids attendus par la source (``/search`` déjà filtré par les TROIS
    filtres du pipeline — bbox, tuile, ``eo:cloud_cover`` — c'est la responsabilité de
    l'appelant de fournir ``source_ids`` déjà filtré ainsi, ce module ne fait qu'un ``set``
    diff PUR). Tolérance 0 (fiche) : le moindre écart, dans un sens ou l'autre, est nommé.
    """
    return CompletenessResult(
        site_id=site_id,
        missing=frozenset(source_ids - manifest_ids),
        extra=frozenset(manifest_ids - source_ids),
    )


def _conservation_cell(report: SiteReport) -> str:
    return "OK" if report.conservation_ok else "ROUGE"


def _integrity_cell(report: SiteReport) -> str:
    return "OK" if report.integrity_ok else "ROUGE"


def _worst_case_line(report: SiteReport) -> str:
    """Phrase d'explication factuelle automatique (fiche : « pires cas en tête »)."""
    counters = report.counters
    causes = []
    if counters.get("off_tile", 0) > 0:
        causes.append(f"multi-tuiles : off_tile={counters['off_tile']}/{counters['found_stac']}")
    if counters.get("rejected_clouds", 0) > 0:
        causes.append(
            f"nuages : rejected_clouds={counters['rejected_clouds']}/{counters['found_tile']}"
        )
    cause_text = " ; ".join(causes) if causes else "aucune cause dominante mesurée"
    return (
        f"- **{report.site_id}** : ingested/found_tile = "
        f"{counters.get('ingested', 0)}/{counters.get('found_tile', 0)} — {cause_text}"
    )


def render_report(reports: list[SiteReport]) -> str:
    """Rend le rapport Markdown complet (fiche l0-04.2) : table par site (colonnes de
    conservation, ``failed_pct``, verdicts ``conservation``/``integrite``), section
    « pires cas en tête » triée sur ``ingested / found_tile`` croissant, agrégat
    ``scl_class_counts`` (classes 2/11 mises en avant) et volumes.

    ``bytes_downloaded`` n'est PAS agrégé ici : la fiche (décision E-d) exige que ce champ
    porte sa mention de portée (STAC seul, GDAL non instrumentable) — ce module reçoit des
    ``SiteReport`` qui ne portent QUE ``bytes_written`` (octets stockés, mesurés) ; le champ
    transféré au sens système est hors instrument et n'apparaît pas ici (l0-04.H).
    """
    lines: list[str] = ["# Rapport d'ingestion — tiny-wae", ""]

    lines.append(
        "| site | found_stac | skipped_scene_cloud | off_tile | found_tile | ingested | "
        "rejected_clouds | rejected_invalid | rejected_nodata | failed | skipped | "
        "failed_pct | conservation | integrite |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for report in reports:
        counters = report.counters
        lines.append(
            "| {site_id} | {found_stac} | {skipped_scene_cloud} | {off_tile} | {found_tile} | "
            "{ingested} | {rejected_clouds} | {rejected_invalid} | {rejected_nodata} | "
            "{failed} | {skipped} | {failed_pct:.1f} % | {conservation} | {integrite} |".format(
                site_id=report.site_id,
                found_stac=counters.get("found_stac", 0),
                skipped_scene_cloud=counters.get("skipped_scene_cloud", 0),
                off_tile=counters.get("off_tile", 0),
                found_tile=counters.get("found_tile", 0),
                ingested=counters.get("ingested", 0),
                rejected_clouds=counters.get("rejected_clouds", 0),
                rejected_invalid=counters.get("rejected_invalid", 0),
                rejected_nodata=counters.get("rejected_nodata", 0),
                failed=counters.get("failed", 0),
                skipped=counters.get("skipped", 0),
                failed_pct=report.failed_pct,
                conservation=_conservation_cell(report),
                integrite=_integrity_cell(report),
            )
        )

    lines.append("")
    lines.append(
        "> `failed_pct` seuil légitime unique : > "
        f"{FAILED_PCT_MAX:.0f} % signalé (chapeau l0-04, critère 4)."
    )

    conservation_rows = [r for r in reports if not r.conservation_ok]
    if conservation_rows:
        lines.append("")
        lines.append("## ⚠ Conservation ROUGE — en tête (identité comptable violée)")
        lines.append("")
        for report in conservation_rows:
            lines.append(f"- **{report.site_id}** : conservation: ROUGE — {report.counters}")

    integrity_rows = [r for r in reports if not r.integrity_ok]
    if integrity_rows:
        lines.append("")
        lines.append("## Intégrité — items fautifs")
        lines.append("")
        for report in integrity_rows:
            for issue in report.integrity_issues:
                lines.append(f"- **{report.site_id}** / `{issue.item_id}` : {issue.cause}")

    lines.append("")
    lines.append(
        "## Pires cas en tête (ingested / found_tile, sans seuil — caractéristique de site)"
    )
    lines.append("")
    for report in sorted(reports, key=lambda r: r.ingested_ratio):
        lines.append(_worst_case_line(report))

    lines.append("")
    lines.append("## Classes SCL agrégées (2 = ombre de nuage, 11 = neige — instrument V3)")
    lines.append("")
    scl_totals: dict[str, int] = {}
    bytes_written_total = 0
    for report in reports:
        for scl_class, count in report.scl_class_counts.items():
            scl_totals[scl_class] = scl_totals.get(scl_class, 0) + count
        bytes_written_total += report.bytes_written
    for scl_class in SCL_HIGHLIGHT_CLASSES:
        lines.append(f"- classe **{scl_class}** : {scl_totals.get(scl_class, 0)} pixels")
    lines.append(f"- total toutes classes : {sum(scl_totals.values())} pixels")

    lines.append("")
    lines.append("## Volumes")
    lines.append("")
    lines.append(
        "- `bytes_downloaded` : STAC seul — les lectures d'assets par GDAL ne sont pas "
        "instrumentables depuis Python (décision E-d). Non agrégé ici."
    )
    lines.append(
        f"- octets **stockés** (somme des `bytes_written` des manifestes) : {bytes_written_total}"
    )
    lines.append(
        "- octets réellement **transférés** en campagne : hors instrument — mesure "
        "système, à porter par la fiche humaine l0-04.H."
    )

    return "\n".join(lines) + "\n"
