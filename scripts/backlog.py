#!/usr/bin/env python3
"""
backlog.py — le backlog-kit en Python : dashboard HTML + md→html. Zéro Node.

Port Python (2026-08-21) des scripts `build-dashboard.mjs` / `md-to-html.mjs` du kit
`_tools`/`_tools_js` — fusionnés en UN SEUL CLI à deux sous-commandes :

    python scripts/backlog.py dashboard [--project "Nom"] [--backlog docs/backlog]
    python scripts/backlog.py md2html <src.md> <dest.html> [titre] [bandeau]

Dépendance unique : `markdown` (pip/conda-forge). Le reste est stdlib.
Principes inchangés : le .md est la source (canal IA), le HTML est la vue humaine
DÉRIVÉE (jamais éditée à la main) ; le dossier fait foi pour le statut.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import markdown

STATES = ["maturation", "a-faire", "en-cours", "fait"]
STATE_LABELS = {
    "maturation": "Maturation",
    "a-faire": "À faire",
    "en-cours": "En cours",
    "fait": "Fait",
}
STATE_COLORS = {
    "maturation": "#8b7bd8",
    "a-faire": "#d8a657",
    "en-cours": "#5aa7d8",
    "fait": "#69b076",
}
MD_EXT = ["tables", "fenced_code", "toc", "attr_list", "sane_lists"]


# ── frontmatter (parser minimal : clé: valeur + listes [a, b] — suffisant pour nos fiches) ──
def parse_frontmatter(text: str) -> tuple[dict[str, str | list[str]], str]:
    """Extrait le frontmatter YAML simplifié d'une fiche. Retourne (meta, corps)."""
    m = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return {}, text
    meta: dict[str, str | list[str]] = {}
    for line in m.group(1).splitlines():
        line = line.split(" #")[0].rstrip()  # commentaires de fin de ligne
        if ":" not in line or line.startswith((" ", "\t")):
            continue
        key, _, val = line.partition(":")
        val = val.strip().strip("\"'")
        if val.startswith("[") and val.endswith("]"):
            items = [v.strip().strip("\"'") for v in val[1:-1].split(",")]
            meta[key.strip()] = [v for v in items if v]
        else:
            meta[key.strip()] = val
    return meta, text[m.end() :]


@dataclass
class Fiche:
    id: str
    titre: str
    effort: str
    categorie: str
    phase: str
    depends_on: list[str]
    state: str
    chantier: str | None
    path: Path
    priority: str = ""
    parent: str = ""
    subtasks: list[str] = field(default_factory=list)

    @property
    def is_chapeau(self) -> bool:
        return self.categorie == "chapeau" or bool(self.subtasks)

    @property
    def is_humaine(self) -> bool:
        return self.categorie == "humain"


@dataclass
class Chantier:
    id: str
    label: str
    desc: str
    state: str
    phases: list[tuple[str, str]] = field(default_factory=list)  # (id, libellé)
    fiches: list[Fiche] = field(default_factory=list)
    docs: list[str] = field(default_factory=list)  # *.html présents dans le dossier
    path: Path | None = None


def load_fiche(path: Path, state: str, chantier: str | None) -> Fiche | None:
    """Charge une fiche si elle a un `id:` (sinon : INDEX, analyse… → ignorée)."""
    meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
    fid = meta.get("id")
    if not isinstance(fid, str) or not fid:
        return None
    dep = meta.get("depends_on", [])
    sub = meta.get("subtasks", [])
    return Fiche(
        id=fid,
        titre=str(meta.get("titre", meta.get("title", fid))),
        effort=str(meta.get("effort", meta.get("size", ""))),
        categorie=str(meta.get("categorie", meta.get("category", ""))),
        phase=str(meta.get("phase", "")),
        depends_on=dep if isinstance(dep, list) else [dep],
        state=state,
        chantier=chantier,
        path=path,
        parent=str(meta.get("parent", "")),
        subtasks=sub if isinstance(sub, list) else [sub],
    )


def load_chantier(dirpath: Path, state: str) -> Chantier:
    """Charge un sous-dossier chantier : manifeste + fiches + docs liés."""
    manifest = dirpath / "_chantier.md"
    cid, label, desc, phases = dirpath.name, dirpath.name, "", []
    if manifest.exists():
        meta, _ = parse_frontmatter(manifest.read_text(encoding="utf-8"))
        cid = str(meta.get("id", cid))
        label = str(meta.get("label", label))
        desc = str(meta.get("desc", ""))
        raw = str(meta.get("phases", ""))
        if raw:  # format : "O1=Libellé un | O2=Libellé deux"
            for part in raw.split("|"):
                pid, _, plabel = part.strip().partition("=")
                if pid:
                    phases.append((pid.strip(), plabel.strip() or pid.strip()))
    ch = Chantier(id=cid, label=label, desc=desc, state=state, phases=phases, path=dirpath)
    for f in sorted(dirpath.glob("*.md")):
        if f.name.startswith("_"):
            continue
        fiche = load_fiche(f, state, cid)
        if fiche:
            ch.fiches.append(fiche)
    # docs liés = les .html qui ne sont PAS des rendus de fiches (roadmap, revue, analyses)
    fiche_stems = {f.path.stem for f in ch.fiches}
    ch.docs = sorted(p.name for p in dirpath.glob("*.html") if p.stem not in fiche_stems)
    return ch


def load_priorities(backlog: Path) -> dict[str, str]:
    """Lit les priorités P1/P2/P3 depuis maturation/INDEX.md (slug backtické par ligne)."""
    index = backlog / "maturation" / "INDEX.md"
    prios: dict[str, str] = {}
    if index.exists():
        for line in index.read_text(encoding="utf-8").splitlines():
            pm = re.search(r"\bP([123])\b", line)
            sm = re.search(r"`([^`]+)`", line)
            if pm and sm:
                prios[sm.group(1)] = f"P{pm.group(1)}"
    return prios


def scan(backlog: Path) -> tuple[list[Fiche], list[Chantier]]:
    """Parcourt les 4 dossiers d'état : fiches à plat + chantiers (sous-dossiers)."""
    fiches: list[Fiche] = []
    chantiers: list[Chantier] = []
    for state in STATES:
        d = backlog / state
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if (
                p.is_file()
                and p.suffix == ".md"
                and not p.name.startswith("_")
                and p.name != "INDEX.md"
            ):
                fiche = load_fiche(p, state, None)
                if fiche:
                    fiches.append(fiche)
            elif p.is_dir():
                chantiers.append(load_chantier(p, state))
    prios = load_priorities(backlog)
    for f in fiches + [f for c in chantiers for f in c.fiches]:
        f.priority = prios.get(f.id, "")
    return fiches, chantiers


# ── rendu HTML ──────────────────────────────────────────────────────────────────
DARK_CSS = """
:root{--bg:#14171c;--panel:#1c2129;--line:#2a3140;--text:#d5dbe4;--muted:#8b95a5;
--accent:#5aa7d8;}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font-family:'Segoe UI',system-ui,sans-serif;line-height:1.55;font-size:15px}
.wrap{max-width:1080px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:1.45em;margin:.2em 0 .1em}
.sub{color:var(--muted);font-size:.88em;margin-bottom:22px}
.counters{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0 26px}
.counter{background:var(--panel);border:1px solid var(--line);border-radius:10px;
padding:12px 20px;min-width:120px;text-decoration:none;display:block}
.counter:hover{border-color:var(--accent)}
.counter b{font-size:1.5em;display:block}
.counter span{color:var(--muted);font-size:.82em}
.anomalies{background:#3a2020;border:1px solid #7a3030;border-radius:10px;
padding:12px 20px;margin:0 0 22px;font-size:.9em}
.anomalies ul{margin:8px 0 2px;padding-left:20px}.anomalies li{margin:2px 0}
tr.child td:first-child{padding-left:26px}
tr.child{background:rgba(255,255,255,.02)}
td a{color:var(--accent);text-decoration:none}
td a:hover{text-decoration:underline}
section{margin-top:30px}
h2{font-size:1.05em;border-left:4px solid var(--accent);padding-left:10px}
h3{font-size:.95em;color:var(--muted);margin:14px 0 6px}
table{border-collapse:collapse;width:100%;font-size:.88em;background:var(--panel);
border-radius:8px;overflow:hidden}
th{background:#242b36;text-align:left;padding:7px 12px;font-weight:600;color:var(--muted)}
td{padding:6px 12px;border-top:1px solid var(--line);vertical-align:top}
code{background:#242b36;padding:1px 6px;border-radius:4px;font-size:.9em}
.pill{display:inline-block;padding:1px 10px;border-radius:99px;font-size:.78em;
font-weight:600;color:#fff}
.prio-P1{color:#e06c75;font-weight:700}.prio-P2{color:#d8a657}.prio-P3{color:var(--muted)}
.chantier{background:var(--panel);border:1px solid var(--line);border-radius:10px;
padding:16px 20px;margin:14px 0}
.chantier .desc{color:var(--muted);font-size:.88em;margin:2px 0 10px}
.docs a{color:var(--accent);margin-right:14px;font-size:.85em}
a{color:var(--accent)}
.gen{color:var(--muted);font-size:.78em;margin-top:36px;text-align:center}
"""


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def pill(state: str) -> str:
    return (
        f'<span class="pill" style="background:{STATE_COLORS[state]}">{STATE_LABELS[state]}</span>'
    )


def fiche_href(f: Fiche, base: Path) -> str:
    """Lien relatif (depuis `base`, le dossier du dashboard) vers le rendu HTML de la fiche."""
    return Path(os.path.relpath(f.path.with_suffix(".html"), base)).as_posix()


def link_to(fid: str, index: dict[str, Fiche], base: Path, label: str = "") -> str:
    """Lien hypertexte vers une fiche par son id (texte brut si la fiche est inconnue)."""
    txt = esc(label or fid)
    target = index.get(fid)
    if target is None:
        return f"<code>{txt}</code>"
    return f'<a href="{esc(fiche_href(target, base))}"><code>{txt}</code></a>'


def fiche_rows(fiches: list[Fiche], base: Path, index: dict[str, Fiche]) -> str:
    """Table de fiches ; les sous-tâches sont imbriquées sous leur chapeau."""
    rows = []

    def row(f: Fiche, child: bool = False) -> str:
        dep = ", ".join(link_to(d, index, base) for d in f.depends_on if d) or "—"
        mark = "↳ " if child else ("▣ " if f.is_chapeau else "")
        cls = ' class="child"' if child else ""
        cat = f.categorie + (" ⛔" if f.is_humaine else "")
        return (
            f"<tr{cls}><td>{mark}"
            f'<a href="{esc(fiche_href(f, base))}"><code>{esc(f.id)}</code></a></td>'
            f"<td>{esc(f.titre)}</td>"
            f'<td class="prio-{f.priority}">{f.priority}</td>'
            f"<td>{esc(f.effort)}</td><td>{esc(cat)}</td><td>{dep}</td></tr>"
        )

    shown: set[str] = set()
    for f in sorted(fiches, key=lambda x: (x.priority or "P9", x.id)):
        if f.parent and f.parent in {x.id for x in fiches}:
            continue  # affichée sous son chapeau
        rows.append(row(f))
        shown.add(f.id)
        if f.is_chapeau:
            for sid in f.subtasks:
                child = next((x for x in fiches if x.id == sid), None)
                if child is not None:
                    rows.append(row(child, child=True))
                    shown.add(child.id)
    # sous-tâches dont le chapeau est dans un AUTRE état (ex. chapeau encore en maturation)
    for f in sorted(fiches, key=lambda x: x.id):
        if f.id not in shown:
            rows.append(row(f, child=bool(f.parent)))
    if not rows:
        return '<p style="color:var(--muted);font-size:.85em">Aucune fiche.</p>'
    return (
        "<table><tr><th>id</th><th>titre</th><th>prio</th><th>effort</th>"
        "<th>catégorie</th><th>depends_on</th></tr>" + "".join(rows) + "</table>"
    )


def chantier_block(ch: Chantier, base: Path, index: dict[str, Fiche]) -> str:
    docs = "".join(
        f'<a href="{esc(Path(os.path.relpath(ch.path / d, base)).as_posix())}">📄 {esc(d)}</a>'
        for d in ch.docs
        if ch.path is not None
    )
    body = ""
    if ch.phases:
        by_phase: dict[str, list[Fiche]] = {}
        for f in ch.fiches:
            by_phase.setdefault(f.phase or "?", []).append(f)
        for pid, plabel in ch.phases:
            body += f"<h3>{esc(pid)} — {esc(plabel)}</h3>" + fiche_rows(
                by_phase.pop(pid, []), base, index
            )
        for pid, extra in sorted(by_phase.items()):
            body += f"<h3>{esc(pid)} (phase non déclarée)</h3>" + fiche_rows(extra, base, index)
    else:
        body = fiche_rows(ch.fiches, base, index)
    return (
        f'<div class="chantier"><b>{esc(ch.label)}</b> {pill(ch.state)}'
        f'<div class="desc">{esc(ch.desc)}</div>'
        f'<div class="docs">{docs}</div>{body}</div>'
    )


# Horodatage de génération : la seule ligne qui bouge d'une génération à l'autre.
GEN_STAMP_RE = re.compile(r"Généré le \d{2}/\d{2}/\d{4}(?: \d{2}:\d{2})?")


def write_if_changed(path: Path, content: str) -> bool:
    """Écrit `content` UNIQUEMENT si le fichier diffère ailleurs que sur son horodatage.

    Sans ce filtre, chaque génération réécrit tous les .html avec une date fraîche : le
    diff git se remplit de fichiers au contenu identique, et le churn masque les vraies
    évolutions du backlog. Retourne True si le fichier a été écrit.
    """
    if path.exists():
        old = path.read_text(encoding="utf-8")
        if GEN_STAMP_RE.sub("", old) == GEN_STAMP_RE.sub("", content):
            return False
    path.write_text(content, encoding="utf-8")
    return True


def page(title: str, sub: str, body: str, css: str = DARK_CSS) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    return (
        f'<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{esc(title)}</title><style>{css}</style></head><body>"
        f'<div class="wrap"><h1>{esc(title)}</h1><p class="sub">{esc(sub)}</p>'
        f'{body}<p class="gen">Généré le {now} — ne pas éditer (écrasé).'
        f"</p></div></body></html>"
    )


def check_graph(fiches: list[Fiche], index: dict[str, Fiche]) -> list[str]:
    """Contrôle mécanique de cohérence du graphe. Retourne la liste des anomalies.

    Remplace le « filet » grossier que constituaient les depends_on de chapeau : ids
    inexistants, cycles, sous-tâches non déclarées, chapeaux qui ordonnent, fiches
    orphelines (personne ne les déclare et elles ne déclarent personne).
    """
    anomalies: list[str] = []
    for f in fiches:
        for d in f.depends_on:
            if d and d not in index:
                anomalies.append(f"{f.id} : depends_on « {d} » — fiche inexistante")
        for s in f.subtasks:
            if s not in index:
                anomalies.append(f"{f.id} : subtasks « {s} » — fiche inexistante")
            elif index[s].parent != f.id:
                anomalies.append(f"{s} : parent « {index[s].parent or '∅'} » ≠ chapeau {f.id}")
        if f.parent and f.parent not in index:
            anomalies.append(f"{f.id} : parent « {f.parent} » — fiche inexistante")
        if f.is_chapeau and any(f.depends_on):
            anomalies.append(f"{f.id} : un CHAPEAU ne doit pas porter de depends_on")
    # fiches isolées : ni dépendance, ni dépendant, ni rattachement à un chapeau
    depended_on = {d for f in fiches for d in f.depends_on if d}
    for f in fiches:
        if f.is_chapeau:
            continue
        if not any(f.depends_on) and f.id not in depended_on and not f.parent:
            anomalies.append(f"{f.id} : fiche isolée (aucun lien dans le graphe)")
    # cycles (DFS sur les seules fiches dispatchables)
    color: dict[str, int] = {}

    def visit(fid: str, stack: list[str]) -> None:
        if color.get(fid) == 2:
            return
        if color.get(fid) == 1:
            cycle = " → ".join(stack[stack.index(fid) :] + [fid])
            anomalies.append(f"cycle : {cycle}")
            return
        color[fid] = 1
        for d in index[fid].depends_on if fid in index else []:
            if d in index:
                visit(d, stack + [fid])
        color[fid] = 2

    for f in fiches:
        visit(f.id, [])
    return sorted(set(anomalies))


def render_fiche_page(f: Fiche, backlog: Path, index: dict[str, Fiche]) -> bool:
    """Dispatch .md -> .html d'une fiche : breadcrumb, navigation parent/sœurs/enfants,
    dépendances cliquables. Écrit à côté de la source (vue humaine dérivée).

    Retourne True si le .html a réellement été réécrit (cf. write_if_changed)."""
    here = f.path.parent
    text = f.path.read_text(encoding="utf-8")
    _, body_md = parse_frontmatter(text)
    body = markdown.Markdown(extensions=MD_EXT).convert(body_md)

    dash = Path(os.path.relpath(backlog / "maturation" / "etat.html", here)).as_posix()
    # ── breadcrumb : dashboard › chantier › [chapeau ›] fiche
    crumbs = [f'<a href="{esc(dash)}">🏠 Backlog</a>']
    if f.chantier:
        crumbs.append(f"<span>{esc(f.chantier)}</span>")
    parent = index.get(f.parent) if f.parent else None
    if parent is not None:
        crumbs.append(link_to(parent.id, index, here, f"▣ {parent.id}"))
    crumbs.append(f"<b>{esc(f.id)}</b>")
    breadcrumb = '<nav class="crumb">' + " › ".join(crumbs) + "</nav>"

    dep = ", ".join(link_to(d, index, here) for d in f.depends_on if d) or "—"
    meta = (
        f"{STATE_LABELS.get(f.state, f.state)} · effort {f.effort or '—'} · "
        f"{f.categorie or '—'}{' · phase ' + f.phase if f.phase else ''}"
    )
    warn = ""
    if f.is_humaine:
        warn = (
            '<div class="warn">⛔ <b>Fiche humaine</b> — ne pas dispatcher à un agent : '
            "elle est réalisée par un humain, et bloque volontairement ses dépendants.</div>"
        )
    elif f.is_chapeau:
        warn = (
            '<div class="note">▣ <b>Fiche chapeau</b> — ne se dispatche pas : '
            "elle porte le contexte de ses sous-tâches.</div>"
        )

    # ── navigation latérale : sous-tâches (chapeau) ou fratrie (sous-tâche)
    nav = ""
    if f.is_chapeau and f.subtasks:
        items = "".join(
            f"<li>{link_to(sid, index, here)} {esc(index[sid].titre) if sid in index else ''}</li>"
            for sid in f.subtasks
        )
        nav = f'<div class="nav"><b>Sous-tâches</b><ul>{items}</ul></div>'
    elif parent is not None and parent.subtasks:
        items = "".join(
            f"<li>{'→ ' if sid == f.id else ''}{link_to(sid, index, here)} "
            f"{esc(index[sid].titre) if sid in index else ''}</li>"
            for sid in parent.subtasks
        )
        nav = (
            f'<div class="nav"><b>Chapeau</b> : {link_to(parent.id, index, here)} '
            f"{esc(parent.titre)}<ul>{items}</ul></div>"
        )
    # fiches qui dépendent de celle-ci (navigation aval)
    aval = [o for o in index.values() if f.id in o.depends_on]
    if aval:
        items = "".join(f"<li>{link_to(o.id, index, here)} {esc(o.titre)}</li>" for o in aval)
        nav += f'<div class="nav"><b>Débloque</b><ul>{items}</ul></div>'

    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    return write_if_changed(
        f.path.with_suffix(".html"),
        f'<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>[{esc(f.id)}] {esc(f.titre)}</title><style>{LIGHT_CSS}</style></head><body>"
        f'<div class="banner"><div class="inner">{breadcrumb}'
        f"<h1>[{esc(f.id)}] {esc(f.titre)}</h1>"
        f"<p>{esc(meta)} · depends_on : {dep}</p></div></div>"
        f"<article>{warn}{nav}{body}"
        f'<p class="gen">Généré le {now} — le .md fait foi.</p></article></body></html>',
    )


def cmd_dashboard(project: str, backlog: Path) -> int:
    fiches, chantiers = scan(backlog)
    all_fiches = fiches + [f for c in chantiers for f in c.fiches]
    index = {f.id: f for f in all_fiches}
    # dispatch .md -> .html de TOUTES les fiches (les ids du dashboard pointent dessus)
    rewritten = sum(render_fiche_page(f, backlog, index) for f in all_fiches)
    counters = "".join(
        f'<a class="counter" href="#{s}"><b style="color:{STATE_COLORS[s]}">'
        f"{sum(1 for f in all_fiches if f.state == s)}</b>"
        f"<span>{STATE_LABELS[s]}</span></a>"
        for s in STATES
    )
    base = backlog / "maturation"
    body = f'<div class="counters">{counters}</div>'
    anomalies = check_graph(all_fiches, index)
    if anomalies:
        items = "".join(f"<li>{esc(a)}</li>" for a in anomalies)
        body += (
            f'<div class="anomalies"><b>⚠ Graphe — {len(anomalies)} anomalie(s)</b>'
            f"<ul>{items}</ul></div>"
        )
    for state in STATES:
        flat = [f for f in fiches if f.state == state]
        chs = [c for c in chantiers if c.state == state]
        if not flat and not chs:
            continue
        body += f'<section id="{state}"><h2>{STATE_LABELS[state]}</h2>'
        for ch in chs:
            body += chantier_block(ch, base, index)
        if flat:
            body += fiche_rows(flat, base, index)
        body += "</section>"
    out = backlog / "maturation" / "etat.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_if_changed(
        out,
        page(
            f"{project} — backlog",
            "Le dossier fait foi. Cycle : maturation → à-faire → en-cours → fait.",
            body,
        ),
    )
    # archives des chantiers terminés
    for ch in (c for c in chantiers if c.state == "fait"):
        apath = backlog / "maturation" / f"chantier-{ch.id}.html"
        write_if_changed(
            apath,
            page(f"Chantier {ch.label} — archive", ch.desc, chantier_block(ch, base, index)),
        )
        print(f"  archive : {apath.name}")
    for s in STATES:
        n = sum(1 for f in all_fiches if f.state == s)
        print(f"  {STATE_LABELS[s]:<12} {n}")
    print(f"  {'Fiches .html':<12} {rewritten}/{len(all_fiches)} réécrite(s)")
    for a in anomalies:
        print(f"  ⚠ {a}")
    print(f"✓ dashboard : {out}" + (f" — {len(anomalies)} anomalie(s)" if anomalies else ""))
    return 0


LIGHT_CSS = """
body{margin:0;background:#f6f8fa;color:#24323d;font-family:'Segoe UI',system-ui,
sans-serif;line-height:1.65;font-size:16px}
.banner{background:linear-gradient(120deg,#1d4d66,#2c6e91);color:#fff;padding:26px 24px}
.banner h1{margin:0;font-size:1.5em}.banner p{margin:4px 0 0;opacity:.85;font-size:.9em}
.banner a{color:#fff}.banner code{background:rgba(255,255,255,.15);color:#fff}
.inner{max-width:880px;margin:0 auto;padding:0 8px}
.crumb{font-size:.85em;opacity:.9;margin-bottom:10px}
.crumb a{text-decoration:none}.crumb a:hover{text-decoration:underline}
.warn{background:#fdecea;border-left:4px solid #b91c1c;padding:12px 16px;
border-radius:0 8px 8px 0;margin-bottom:18px}
.note{background:#eef4f8;border-left:4px solid #2c6e91;padding:12px 16px;
border-radius:0 8px 8px 0;margin-bottom:18px}
.nav{background:#f6f8fa;border:1px solid #e3e9ee;border-radius:8px;padding:10px 18px;
margin:0 0 18px;font-size:.92em}
.nav ul{margin:6px 0 2px;padding-left:20px}.nav li{margin:2px 0}
.gen{color:#5c6b76;font-size:.8em;text-align:center;margin-top:30px}
article{max-width:880px;margin:26px auto 60px;background:#fff;border:1px solid #e3e9ee;
border-radius:10px;padding:34px 44px}
article h1{color:#1d4d66;border-bottom:3px solid #2c6e91;padding-bottom:8px}
article h2{color:#1d4d66;margin-top:1.8em}article a{color:#2c6e91}
blockquote{border-left:4px solid #2c6e91;background:#eef4f8;margin:1em 0;
padding:10px 18px;border-radius:0 8px 8px 0}
code{background:#eef2f5;padding:2px 6px;border-radius:5px;font-size:.88em}
pre{background:#20303c;color:#e8eef2;padding:16px;border-radius:8px;overflow-x:auto}
pre code{background:none;color:inherit}
table{border-collapse:collapse;width:100%;font-size:.92em;margin:1.2em 0}
th{background:#1d4d66;color:#fff;text-align:left;padding:8px 12px}
td{padding:7px 12px;border-bottom:1px solid #e7ecf0}
tbody tr:nth-child(even){background:#f3f7fa}
@media print{article{border:none;padding:0}}
"""


def cmd_md2html(src: Path, dest: Path, title: str, banner: str) -> int:
    text = src.read_text(encoding="utf-8")
    _, body_md = parse_frontmatter(text)
    body = markdown.Markdown(extensions=MD_EXT).convert(body_md)
    now = datetime.now().strftime("%d/%m/%Y")
    written = write_if_changed(
        dest,
        f'<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{esc(title)}</title><style>{LIGHT_CSS}</style></head><body>"
        f'<div class="banner"><div class="inner"><h1>{esc(title)}</h1>'
        f"<p>{esc(banner or f'Généré le {now} depuis {src.name} — le .md fait foi.')}"
        f"</p></div></div><article>{body}</article></body></html>",
    )
    print(f"✓ {src} -> {dest}" if written else f"= {dest} inchangé")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="backlog-kit Python : dashboard + md2html")
    sp = ap.add_subparsers(dest="cmd", required=True)
    d = sp.add_parser("dashboard", help="génère maturation/etat.html + archives")
    d.add_argument("--project", default="Projet")
    d.add_argument("--backlog", default="docs/backlog", type=Path)
    m = sp.add_parser("md2html", help="convertit un .md en .html lisible/imprimable")
    m.add_argument("src", type=Path)
    m.add_argument("dest", type=Path)
    m.add_argument("title", nargs="?", default="Doc")
    m.add_argument("banner", nargs="?", default="")
    a = ap.parse_args()
    if a.cmd == "dashboard":
        return cmd_dashboard(a.project, a.backlog)
    return cmd_md2html(a.src, a.dest, a.title, a.banner)


if __name__ == "__main__":
    sys.exit(main())
