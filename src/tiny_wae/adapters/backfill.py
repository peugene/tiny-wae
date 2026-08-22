"""adapters/backfill.py — boucle sites × fenêtres, pool de workers, isolation par site,
interruption propre (SIGINT / CTRL_BREAK_EVENT) pour la fiche l0-04.1.

Porte TOUTE l'orchestration (règle de couche, décision d'ancrage n°1 de la fiche) :
``cli/backfill.py`` ne fait QUE parser les options, appeler ce module et mapper le résultat
sur un code de sortie — c'est ce qui rend le pool testable sans sous-processus.

⛔ AUCUN retry ici (décision d'ancrage n°2) : ``ingest_from_source`` (l0-03.4) porte déjà le
retry, réservé aux erreurs réseau. En ajouter un second les multiplierait silencieusement.

Granularité du pool : une TÂCHE = un SITE (toutes ses fenêtres traitées SÉQUENTIELLEMENT à
l'intérieur de la tâche). La concurrence du pool joue donc UNIQUEMENT entre sites, jamais
entre deux fenêtres d'un même site — décision prise ICI, en écart du premier jet (une tâche
par couple site/fenêtre), après avoir mesuré la panne qu'il provoquait : deux fenêtres du
MÊME site qui terminent dans la MÊME seconde produisent le MÊME ``run_id`` (résolution à la
seconde, ``adapters/ingestion.py::_new_run_id``, hors périmètre de cette fiche), donc le
MÊME chemin de tmp-file (même PID : ce sont des THREADS du même process) dans
``manifests._write_json_atomic`` — une des deux écritures perd la course et lève
``FileNotFoundError`` au ``rename``. Sérialiser les fenêtres D'UN MÊME site élimine la
course par construction (un seul ``write_run`` en vol à la fois pour un site donné) sans
rien perdre de la parallélisation utile (25 sites en parallèle, chacun sur son historique).
L'isolation par site (décision d'ancrage n°7) en découle directement : une exception dans
une fenêtre n'arrête que les fenêtres SUIVANTES de CE site (elle est capturée, la boucle du
site continue), et ne touche jamais les autres sites — chaque ``Future`` du pool est un
site, indépendant des autres. ``assets_read`` ne remonte JAMAIS par un état partagé entre
threads : chaque fenêtre rend son propre ``IngestOutcome`` par valeur de retour (décision de
l0-03.3, motivée précisément par ce pool), agrégé ensuite dans le thread appelant.
"""

from __future__ import annotations

import functools
import signal
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tiny_wae.adapters.ingestion import IngestOutcome, ingest_from_source
from tiny_wae.adapters.stac import StacSource, StacUnreachable
from tiny_wae.core.settings import Settings
from tiny_wae.core.sites import Site
from tiny_wae.core.windows import Window


def _is_network_error(exc: BaseException) -> bool:
    """Classe une exception comme "d'origine réseau" — même règle que la décision
    d'ancrage n°10 de ``adapters/ingestion.py`` (``OSError`` couvre transport HTTP et
    lectures GDAL/rasterio, ``StacUnreachable`` n'hérite pas d'``OSError`` et est nommée
    explicitement). Dupliquée ici à dessein : cette fonction est privée à ``ingestion.py``
    et ``backfill.py`` n'a pas vocation à dépendre de son implémentation interne."""
    return isinstance(exc, OSError | StacUnreachable)


@dataclass(frozen=True, slots=True)
class TaskFailure:
    """Une tâche (site, fenêtre) qui a levé une exception non rattrapée par
    ``ingest_from_source`` (typiquement : amont injoignable après épuisement du retry)."""

    window: Window
    error: str
    is_network: bool


@dataclass(frozen=True, slots=True)
class SiteResult:
    """Résultat agrégé d'un site : les tâches réussies (un ``IngestOutcome`` par fenêtre
    traitée) et les tâches en échec. ``ok`` est faux dès qu'une seule fenêtre du site a
    échoué — c'est l'unité d'isolation nommée sur STDERR par le CLI."""

    site_id: str
    outcomes: list[IngestOutcome] = field(default_factory=list)
    failures: list[TaskFailure] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


@dataclass(frozen=True, slots=True)
class BackfillOutcome:
    """Résultat complet d'un backfill : un ``SiteResult`` par site sollicité, plus l'état
    d'interruption (SIGINT reçu en cours de run)."""

    site_results: list[SiteResult]
    interrupted: bool

    @property
    def failed_site_ids(self) -> list[str]:
        """Ids des sites en échec (au moins une fenêtre en échec), triés."""
        return sorted(result.site_id for result in self.site_results if not result.ok)

    @property
    def all_ok(self) -> bool:
        """Vrai ssi aucun site n'a échoué ET le run n'a pas été interrompu."""
        return not self.interrupted and not self.failed_site_ids

    @property
    def all_failures_network(self) -> bool:
        """Vrai ssi TOUTES les tâches en échec (tous sites confondus) sont d'origine
        réseau ET qu'aucune tâche n'a réussi — reprend la décision d'ancrage n°10 de
        ``adapters/ingestion.py`` (exit ``INCONCLUSIVE``) à l'échelle du backfill (O2bis :
        amont injoignable sur TOUS les sites, distinct d'un échec métier partiel)."""
        all_failures = [failure for result in self.site_results for failure in result.failures]
        if not all_failures:
            return False
        any_success = any(result.outcomes for result in self.site_results)
        return not any_success and all(failure.is_network for failure in all_failures)


def build_tasks(sites: list[Site], windows: list[Window]) -> dict[str, list[Window]]:
    """Associe à CHAQUE site la MÊME liste de fenêtres — construction par défaut consommée
    par le CLI (``--months N`` global). Un appelant qui veut des fenêtres différentes par
    site (ex. les corpus de test A01/B09 qui ne se recouvrent pas dans le temps, cf.
    ancrage de la fiche) construit son ``windows_by_site`` à la main et appelle
    ``run_backfill`` directement plutôt que de passer par cette fonction."""
    return {site.id: list(windows) for site in sites}


def _request_stop(stop_event: threading.Event, _signum: int, _frame: object) -> None:
    """Gestionnaire de signal — fonction PURE : ne fait QUE positionner ``stop_event``,
    aucun I/O, aucun accès au pool. Testable directement (appel de fonction, PAS un vrai
    signal — décision d'ancrage n°5 : le déclenchement du signal n'est pas portable
    linux-64/win-64, seul le comportement d'arrêt l'est)."""
    stop_event.set()


def _process_site(
    site: Site,
    windows: list[Window],
    *,
    source: StacSource,
    settings: Settings,
    data_root: Path,
    force: bool,
    stop_event: threading.Event,
) -> SiteResult:
    """Exécute TOUTES les fenêtres d'UN site, séquentiellement (jamais en concurrence
    entre elles — cf. docstring du module : c'est ce qui élimine la collision de
    ``run_id``). N'appelle QUE ``ingest_from_source`` (AUCUN retry propre, décision
    d'ancrage n°2). Une fenêtre en échec devient une ``TaskFailure`` et n'interrompt PAS
    les fenêtres suivantes du même site — seul ``stop_event`` (positionné avant le début
    d'une fenêtre) arrête la boucle plus tôt, sans jamais interrompre une fenêtre déjà
    engagée (« attente des items en cours », décision d'ancrage n°5)."""
    outcomes: list[IngestOutcome] = []
    failures: list[TaskFailure] = []
    for window in windows:
        if stop_event.is_set():
            break
        try:
            outcome = ingest_from_source(
                site=site,
                window=window,
                source=source,
                settings=settings,
                data_root=data_root,
                force=force,
            )
        except Exception as exc:  # noqa: BLE001 — isolation par site, jamais avalée en silence.
            failures.append(
                TaskFailure(window=window, error=str(exc), is_network=_is_network_error(exc))
            )
            continue
        outcomes.append(outcome)
    return SiteResult(site_id=site.id, outcomes=outcomes, failures=failures)


def run_backfill(
    *,
    sites: list[Site],
    windows_by_site: Mapping[str, list[Window]],
    source: StacSource,
    settings: Settings,
    data_root: Path,
    workers: int,
    force: bool = False,
    stop_event: threading.Event | None = None,
    install_signal_handlers: bool = True,
) -> BackfillOutcome:
    """Exécute le backfill : une tâche par (site, fenêtre) de ``windows_by_site``, dans un
    pool borné à ``workers``. Un site sans entrée dans ``windows_by_site`` n'est pas traité
    (rend un ``SiteResult`` vide et OK) — c'est la voie utilisée par les tests O2/O3 pour
    donner à chaque site sa PROPRE fenêtre, les corpus A01 (sept. 2022) et B09 (août 2023)
    ne se recouvrant pas dans le temps (ancrage de la fiche).

    ``stop_event`` : si fourni, piloté par l'appelant (test) — SANS installation de
    gestionnaire de signal réel (``install_signal_handlers=False`` obligatoire dans ce cas,
    sans quoi le test installerait un VRAI ``signal.signal`` dans le thread de test, ce que
    ``signal`` interdit hors thread principal). Si absent, un ``threading.Event`` interne
    est créé et, sauf ``install_signal_handlers=False``, câblé sur SIGINT et
    ``CTRL_BREAK_EVENT`` (Windows, absent sous Linux) pour la durée du run — les anciens
    gestionnaires sont restaurés dans tous les cas (``finally``).

    À l'arrêt (signal reçu, ou ``stop_event`` positionné par le test) : les tâches PAS
    ENCORE démarrées sont annulées (``Future.cancel()``), celles déjà en cours sont
    attendues jusqu'à leur terme — jamais interrompues à mi-item (l'atomicité de
    l'écriture des manifestes, l0-03.2, garantit qu'aucun manifeste tronqué ne peut en
    résulter ; vérifié, pas supposé, par le test O3)."""
    effective_stop_event = stop_event if stop_event is not None else threading.Event()

    restore: list[tuple[int, Any]] = []
    if install_signal_handlers:
        handler: Callable[[int, object], None] = functools.partial(
            _request_stop, effective_stop_event
        )
        restore.append((signal.SIGINT, signal.signal(signal.SIGINT, handler)))
        # SIGBREAK (Ctrl+Break) n'existe que sous Windows — absent de `signal` sous Linux.
        sigbreak = getattr(signal, "SIGBREAK", None)
        if sigbreak is not None:
            restore.append((sigbreak, signal.signal(sigbreak, handler)))

    try:
        # Sites sans fenêtre (absents de `windows_by_site`, ou liste vide) : aucune tâche
        # soumise — `SiteResult` vide et OK, construit directement, hors du pool.
        sites_with_windows = [site for site in sites if windows_by_site.get(site.id)]
        sites_without_windows = [site for site in sites if not windows_by_site.get(site.id)]

        results_by_site: dict[str, SiteResult] = {
            site.id: SiteResult(site_id=site.id) for site in sites_without_windows
        }
        interrupted = False

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _process_site,
                    site,
                    windows_by_site[site.id],
                    source=source,
                    settings=settings,
                    data_root=data_root,
                    force=force,
                    stop_event=effective_stop_event,
                ): site
                for site in sites_with_windows
            }
            for future in as_completed(futures):
                if effective_stop_event.is_set() and not interrupted:
                    interrupted = True
                    for other_future in futures:
                        if other_future is not future:
                            other_future.cancel()
                site = futures[future]
                try:
                    results_by_site[site.id] = future.result()
                except CancelledError:
                    interrupted = True
                    results_by_site[site.id] = SiteResult(site_id=site.id)

        if effective_stop_event.is_set():
            interrupted = True

        site_results = [results_by_site[site.id] for site in sites]
        return BackfillOutcome(site_results=site_results, interrupted=interrupted)
    finally:
        if install_signal_handlers:
            for signum, previous_handler in restore:
                signal.signal(signum, previous_handler)
