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

⭐ Progression et ETA (obs-01, D6/D7/D9/D11/D12) : ce module loggue directement via son
logger de module (``logging.getLogger(__name__)``, D3/D7 — c'est de l'I/O, la couche
``adapters/`` y a droit) — une ligne d'ouverture puis une ligne PAR FENÊTRE TERMINÉE
(succès ou échec, D6). ``_process_site`` tournant dans N threads, ``n`` (le numérateur
``n/total``) est distribué par ``_Progress.record_window``, sous verrou : c'est ce qui
garantit qu'il forme une permutation de ``1..total`` sans doublon ni trou malgré la
concurrence (oracle O2), `logging` sérialisant ensuite l'écriture elle-même. L'ETA
(``_eta_seconds``/``_format_eta``, D12) est une extrapolation linéaire PURE, testée par
appel direct — son incertitude (D11) est portée par un ``?`` suffixé sous deux conditions :
échantillon < 5 % du total, OU phase de queue (moins de ``workers`` sites encore actifs,
c.-à-d. n'ayant pas encore produit TOUTES leurs fenêtres).

Accusé de réception et interruption immédiate (obs-02, D1) : ``_request_stop`` reste une
fonction PURE — elle positionne ``stop_event`` et, si fourni, notifie l'appelant via
``on_stop_requested(already_requested)``. C'est le SEUL point d'extension : ce module ne
décide jamais de ce qu'un 2e Ctrl+C doit faire (message, sortie brutale) — cette politique
vit dans ``cli/backfill.py``.
"""

from __future__ import annotations

import functools
import logging
import signal
import threading
import time
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

logger = logging.getLogger(__name__)

# Seuil D11 (condition « échantillon trop court ») : moins de 5 % du total de fenêtres
# soumises. Nommé ici (jamais recopié en littéral) — c'est ce que O8/O9 exercent.
_ETA_MIN_SAMPLE_RATIO = 0.05


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


def _eta_seconds(done: int, total: int, elapsed_s: float) -> float | None:
    """Extrapolation linéaire (D12, fonction PURE) : ``restant = (total − done) ×
    elapsed_s / done``. Rend ``None`` avant la première fenêtre terminée (``done <= 0`` —
    aucune division par zéro), ``0.0`` sur la dernière (``done >= total`` — plus rien à
    attendre), sinon la valeur exacte de la formule. Jamais de négatif : ``done`` et
    ``total`` sont des compteurs, ``total >= done`` par construction du run."""
    if done <= 0:
        return None
    if done >= total:
        return 0.0
    return (total - done) * elapsed_s / done


def _eta_uncertain(*, done: int, total: int, sites_active: int, workers: int) -> bool:
    """Vrai si l'ETA doit porter le suffixe ``?`` (D11) — une SEULE des deux conditions
    suffit : l'échantillon est trop court (``done`` < 5 % de ``total``), OU le run est en
    phase de queue (``sites_active``, le nombre de sites n'ayant PAS ENCORE produit
    TOUTES leurs fenêtres, est inférieur au nombre de ``workers`` — le parallélisme
    s'effondre mécaniquement, cf. ancrage de la fiche)."""
    sample_too_small = done < total * _ETA_MIN_SAMPLE_RATIO
    queue_phase = sites_active < workers
    return sample_too_small or queue_phase


def _format_duration(seconds: float) -> str:
    """Formate une durée en ``<H>h<MM>`` au-delà d'une heure, sinon ``<M>min<SS>`` —
    format FIGÉ de la fiche (ex. ``2h11``)."""
    total_seconds = round(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h{minutes:02d}"
    return f"{minutes}min{secs:02d}"


def _format_eta(eta_seconds: float | None, *, done: int, total: int, uncertain: bool) -> str:
    """Rend le champ ETA d'une ligne de progression (D11/D12, fonction PURE) : ``—`` avant
    la première fenêtre terminée ET sur la dernière ligne (``done >= total`` : il n'y a
    plus rien à attendre, un ``0min00`` littéral serait du bruit) ; sinon une durée
    formatée, suffixée de ``?`` ssi ``uncertain``."""
    if eta_seconds is None or done >= total:
        return "—"
    suffix = "?" if uncertain else ""
    return f"{_format_duration(eta_seconds)}{suffix}"


def _format_counters(counters: Mapping[str, int]) -> str:
    """Rend les compteurs NON NULS d'un run, triés par clé (fiche : « une ligne à 12
    compteurs à zéro est illisible »). ``aucun item`` si TOUS les compteurs sont nuls
    (correction post-revue : une fenêtre sans acquisition est un cas RÉEL et fréquent — un
    site sans item sur un mois — la laisser sans charge utile la rendrait indistinguable
    d'un défaut d'affichage sur un run de 1200 lignes, et terminerait la ligne par un
    espace)."""
    rendered = " ".join(f"{key}={value}" for key, value in sorted(counters.items()) if value != 0)
    return rendered if rendered else "aucun item"


@dataclass
class _Progress:
    """État de progression PARTAGÉ entre tous les threads du pool (un par run) : verrou
    unique protégeant ``done``/``sites_done`` — c'est ce qui garantit que ``n`` (le
    numérateur distribué par ``record_window``) forme une permutation de ``1..total``
    malgré la concurrence réelle entre sites (oracle O2), et que la paire
    ``(done, sites_active)`` lue pour une ligne donnée est une vue cohérente (jamais
    calculée hors verrou)."""

    total: int
    workers: int
    sites_total: int
    start: float = field(default_factory=time.monotonic)
    lock: threading.Lock = field(default_factory=threading.Lock)
    done: int = 0
    sites_done: int = 0

    def record_window(self, *, site_finished: bool) -> tuple[int, float, int]:
        """Enregistre UNE fenêtre terminée (succès ou échec) ; incrémente aussi le
        compteur de sites terminés si ``site_finished`` (c'est la dernière fenêtre
        planifiée de son site). Rend ``(n, elapsed_s, sites_active)``, calculé DANS le
        verrou pour éviter toute vue incohérente entre threads."""
        with self.lock:
            self.done += 1
            if site_finished:
                self.sites_done += 1
            n = self.done
            elapsed = time.monotonic() - self.start
            sites_active = self.sites_total - self.sites_done
        return n, elapsed, sites_active


def _request_stop(
    stop_event: threading.Event,
    _signum: int,
    _frame: object,
    on_stop_requested: Callable[[bool], None] | None = None,
) -> None:
    """Gestionnaire de signal — fonction PURE (obs-02, D1) : ne fait QUE positionner
    ``stop_event`` et, si fourni, appeler ``on_stop_requested(already_requested)``. Aucun
    I/O direct, aucun accès au pool, aucune décision : « que faire du second Ctrl+C » est
    une politique qui appartient au CLI, pas à cet adaptateur — ``on_stop_requested`` est
    le seul point d'extension, câblé par ``run_backfill`` via ``functools.partial``.
    ``already_requested`` est lu AVANT de positionner ``stop_event`` (donc vrai ssi un
    appel précédent l'avait déjà fait) : aucun compteur supplémentaire n'est nécessaire,
    l'état « déjà demandé » se lit sur l'``Event`` lui-même (piste écartée dans la fiche).
    Testable directement (appel de fonction, PAS un vrai signal — décision d'ancrage n°5
    de l0-04.1 : le déclenchement du signal n'est pas portable linux-64/win-64, seul le
    comportement d'arrêt l'est)."""
    already_requested = stop_event.is_set()
    stop_event.set()
    if on_stop_requested is not None:
        on_stop_requested(already_requested)


def _log_progress_line(
    *,
    level: int,
    n: int,
    total: int,
    elapsed_s: float,
    sites_active: int,
    workers: int,
    site_id: str,
    window: Window,
    payload: str,
) -> None:
    """Compose et émet UNE ligne de progression (D6/D7), colonnes fixes à gauche
    (``n/total``, ``%``, ``ETA``) puis charge utile variable à droite (fiche : « Format de
    ligne (figé) »). ``payload`` porte soit les compteurs non nuls, soit ``ÉCHEC : ...``
    (à charge de l'appelant, D6)."""
    pct = (n / total * 100) if total > 0 else 0.0
    eta_seconds = _eta_seconds(n, total, elapsed_s)
    uncertain = _eta_uncertain(done=n, total=total, sites_active=sites_active, workers=workers)
    eta = _format_eta(eta_seconds, done=n, total=total, uncertain=uncertain)
    bounds = f"{window.start:%Y-%m-%d}→{window.end:%Y-%m-%d}"
    logger.log(
        level,
        "backfill  %d/%d (%5.1f%%) ETA %s  %s  %s  %s",
        n,
        total,
        pct,
        eta,
        site_id,
        bounds,
        payload,
    )


def _process_site(
    site: Site,
    windows: list[Window],
    *,
    source: StacSource,
    settings: Settings,
    data_root: Path,
    force: bool,
    stop_event: threading.Event,
    progress: _Progress,
) -> SiteResult:
    """Exécute TOUTES les fenêtres d'UN site, séquentiellement (jamais en concurrence
    entre elles — cf. docstring du module : c'est ce qui élimine la collision de
    ``run_id``). N'appelle QUE ``ingest_from_source`` (AUCUN retry propre, décision
    d'ancrage n°2). Une fenêtre en échec devient une ``TaskFailure`` et n'interrompt PAS
    les fenêtres suivantes du même site — seul ``stop_event`` (positionné avant le début
    d'une fenêtre) arrête la boucle plus tôt, sans jamais interrompre une fenêtre déjà
    engagée (« attente des items en cours », décision d'ancrage n°5).

    Une ligne de progression est loguée pour CHAQUE fenêtre TERMINÉE (D6), succès (INFO)
    ou échec (WARNING) — jamais pour une fenêtre annulée par ``stop_event`` avant d'avoir
    démarré. ``site_finished`` (dernier index de ``windows``) alimente ``progress`` pour
    la condition « phase de queue » de l'ETA (D11) ; un site interrompu en cours de route
    par ``stop_event`` n'atteint jamais cet index, ce qui est le comportement voulu (son
    dernier statut connu reste « actif »)."""
    outcomes: list[IngestOutcome] = []
    failures: list[TaskFailure] = []
    last_index = len(windows) - 1
    for index, window in enumerate(windows):
        if stop_event.is_set():
            break
        site_finished = index == last_index
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
            n, elapsed_s, sites_active = progress.record_window(site_finished=site_finished)
            _log_progress_line(
                level=logging.WARNING,
                n=n,
                total=progress.total,
                elapsed_s=elapsed_s,
                sites_active=sites_active,
                workers=progress.workers,
                site_id=site.id,
                window=window,
                payload=f"ÉCHEC : {exc}",
            )
            continue
        outcomes.append(outcome)
        n, elapsed_s, sites_active = progress.record_window(site_finished=site_finished)
        _log_progress_line(
            level=logging.INFO,
            n=n,
            total=progress.total,
            elapsed_s=elapsed_s,
            sites_active=sites_active,
            workers=progress.workers,
            site_id=site.id,
            window=window,
            payload=_format_counters(outcome.run.counters),
        )
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
    on_stop_requested: Callable[[bool], None] | None = None,
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

    ``on_stop_requested`` (obs-02, D1) : transmis TEL QUEL au handler de signal via
    ``functools.partial`` — c'est le seul canal par lequel le CLI observe un Ctrl+C (accusé
    de réception au 1er, sortie immédiate au 2e) sans que ce module décide de rien lui-même.

    À l'arrêt (signal reçu, ou ``stop_event`` positionné par le test) : les tâches PAS
    ENCORE démarrées sont annulées (``Future.cancel()``), celles déjà en cours sont
    attendues jusqu'à leur terme — jamais interrompues à mi-item (l'atomicité de
    l'écriture des manifestes, l0-03.2, garantit qu'aucun manifeste tronqué ne peut en
    résulter ; vérifié, pas supposé, par le test O3)."""
    effective_stop_event = stop_event if stop_event is not None else threading.Event()

    restore: list[tuple[int, Any]] = []
    if install_signal_handlers:
        handler: Callable[[int, object], None] = functools.partial(
            _request_stop, effective_stop_event, on_stop_requested=on_stop_requested
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

        # Total EXACT des fenêtres réellement soumises au pool (pas ``len(windows) *
        # len(sites)`` : les corpus A01/B09 des tests O2/O2bis diffèrent par site) —
        # c'est ce total, annoncé sur la ligne d'ouverture, que O2 confronte à la
        # permutation `1..total` effectivement observée.
        total = sum(len(windows_by_site[site.id]) for site in sites_with_windows)
        progress = _Progress(total=total, workers=workers, sites_total=len(sites_with_windows))
        logger.info(
            "backfill  ouverture : %d site(s), %d fenêtre(s) au total, workers=%d",
            len(sites_with_windows),
            total,
            workers,
        )

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
                    progress=progress,
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
