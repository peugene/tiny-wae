#!/usr/bin/env python3
"""
backlog.py — le backlog-kit en Python : dashboard HTML + md→html. Zéro Node.

Port Python (2026-08-21) des scripts `build-dashboard.mjs` / `md-to-html.mjs` du kit
`_tools`/`_tools_js` — fusionnés en UN SEUL CLI à trois sous-commandes :

    python scripts/backlog.py dashboard [--project "Nom"] [--backlog docs/backlog]
    python scripts/backlog.py lots      [--project "Nom"] [--lots docs/lots]
    python scripts/backlog.py md2html <src.md> <dest.html> [titre] [bandeau]

Fiches et lots partagent la même grammaire visuelle : bandeau à en-tête détaillé, pastille
d'état, sommaire replié, précédent/suivant, navigation croisée.

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

    @property
    def is_documentaire(self) -> bool:
        """Fiche qui ENREGISTRE un travail déjà fait (rétroactive, décision, incident).

        Elle n'ordonne rien et n'est ordonnée par rien : sa place hors du graphe est
        normale, pas une anomalie."""
        return self.categorie == "documentaire"


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
.infos{background:#1c2333;border:1px solid #33415e;border-radius:10px;
padding:10px 20px;margin:0 0 22px;font-size:.86em;color:var(--muted)}
.infos ul{margin:6px 0 2px;padding-left:20px}
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
.xnav{margin:0 0 6px;font-size:.88em}.xnav a{text-decoration:none}
.xnav a:hover{text-decoration:underline}
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


def check_graph(fiches: list[Fiche], index: dict[str, Fiche]) -> tuple[list[str], list[str]]:
    """Contrôle mécanique de cohérence du graphe. Retourne la liste des anomalies.

    Remplace le « filet » grossier que constituaient les depends_on de chapeau : ids
    inexistants, cycles, sous-tâches non déclarées, chapeaux qui ordonnent, fiches
    orphelines (personne ne les déclare et elles ne déclarent personne).
    """
    anomalies: list[str] = []
    infos: list[str] = []
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
        # un chapeau se ferme quand ses sous-tâches sont fermées : le rappeler, sans l'imposer
        # (déplacer une fiche est un geste d'équipe, pas une erreur de graphe)
        subs = [index[s] for s in f.subtasks if s in index]
        if subs and f.state != "fait" and all(s.state == "fait" for s in subs):
            infos.append(
                f"{f.id} : chapeau en {f.state}/ alors que ses {len(subs)} sous-tâches "
                "sont en fait/ — à clore ?"
            )
    # fiches isolées : ni dépendance, ni dépendant, ni rattachement à un chapeau
    depended_on = {d for f in fiches for d in f.depends_on if d}
    for f in fiches:
        # un chapeau n'ordonne rien ; une fiche documentaire enregistre du déjà-fait :
        # ni l'un ni l'autre n'a de place dans le graphe, leur isolement est normal
        if f.is_chapeau or f.is_documentaire:
            continue
        if not any(f.depends_on) and f.id not in depended_on and not f.parent:
            anomalies.append(f"{f.id} : fiche isolée (aucun lien dans le graphe)")
    # feuilles : personne n'en dépend. Certaines sont légitimes (recette finale, doc
    # terminale) ; d'autres signalent une arête oubliée — c'est au PO de trancher, donc
    # on les LISTE sans les traiter en erreur.
    leaves = sorted(
        f.id
        for f in fiches
        if not f.is_chapeau
        and not f.is_documentaire  # une fiche documentaire est une feuille par construction
        and f.id not in depended_on
        and not f.subtasks
    )
    if leaves:
        infos.append("feuilles (aucun dépendant) — à relire : " + ", ".join(leaves))
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
    return sorted(set(anomalies)), sorted(set(infos))


def fiche_sequence(f: Fiche, index: dict[str, Fiche]) -> list[str]:
    """Ordre de lecture dans lequel situer la fiche pour le « précédent / suivant ».

    Une sous-tâche se lit dans l'ordre des `subtasks` de son chapeau (l'ordre voulu par le
    PO) ; une fiche sans chapeau, dans l'ordre des ids de son chantier."""
    parent = index.get(f.parent) if f.parent else None
    if parent is not None and f.id in parent.subtasks:
        return [s for s in parent.subtasks if s in index]
    return sorted(o.id for o in index.values() if o.chantier == f.chantier and not o.parent)


def render_fiche_page(f: Fiche, backlog: Path, index: dict[str, Fiche]) -> bool:
    """Dispatch .md -> .html d'une fiche : breadcrumb, pastille d'état, en-tête détaillé,
    sommaire, navigation parent/sœurs/enfants, précédent-suivant. Écrit à côté de la source.

    Retourne True si le .html a réellement été réécrit (cf. write_if_changed)."""
    here = f.path.parent
    text = f.path.read_text(encoding="utf-8")
    _, body_md = parse_frontmatter(text)
    # l'en-tête `**Champ** : …` éventuel remonte dans le bandeau (comme pour les lots)
    fields, body_md = split_header_fields(body_md)
    md = markdown.Markdown(extensions=MD_EXT)
    body = md.convert(body_md)
    body = body.replace("<table>", '<div class="tablewrap"><table>').replace(
        "</table>", "</table></div>"
    )
    # H1 retiré : le bandeau porte déjà « [id] titre » (le frontmatter fait foi)
    body = re.sub(r"<h1[^>]*>.*?</h1>", "", body, count=1, flags=re.DOTALL)
    toc_html = getattr(md, "toc", "")
    toc = ""
    if toc_html.count("<li>") >= 2:
        toc = f'<details class="toc-box" open><summary>Sommaire</summary>{toc_html}</details>'

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

    # ── bandeau = les ATTRIBUTS de la fiche (le graphe est en navigation, plus bas :
    # le lister ici aussi ferait deux fois la même liste à deux centimètres d'écart)
    rows: list[tuple[str, str]] = [("Effort", esc(f.effort) or "—")]
    if f.priority:
        rows.append(("Priorité", f'<span class="prio-{f.priority}">{f.priority}</span>'))
    rows.append(("Catégorie", esc(f.categorie) or "—"))
    if f.phase:
        rows.append(("Phase", esc(f.phase)))
    if f.chantier:
        rows.append(("Chantier", esc(f.chantier)))
    rows += [(k, inline_md(v)) for k, v in fields]
    meta = "<br>".join(f"<b>{esc(k)}</b> : {v}" for k, v in rows)

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
    elif f.is_documentaire:
        warn = (
            '<div class="note">📘 <b>Fiche documentaire</b> — ne se dispatche pas : '
            "elle enregistre un travail déjà réalisé, hors du graphe de dépendances.</div>"
        )

    # ── navigation : chaque fiche liée porte son ÉTAT, ce qui répond d'un coup d'œil à
    # « suis-je débloqué ? » et « où en sont mes sous-tâches ? »
    def item(fid: str, mark: str = "") -> str:
        o = index.get(fid)
        if o is None:
            return f"<li>{mark}<code>{esc(fid)}</code> — fiche inconnue</li>"
        return f"<li>{mark}{link_to(fid, index, here)} {esc(o.titre)} {pill(o.state)}</li>"

    nav = ""
    amont = [d for d in f.depends_on if d]
    aval = sorted((o.id for o in index.values() if f.id in o.depends_on), key=str)
    if amont:
        nav += f'<div class="nav"><b>Dépend de</b><ul>{"".join(item(d) for d in amont)}</ul></div>'
    if aval:
        nav += f'<div class="nav"><b>Débloque</b><ul>{"".join(item(a) for a in aval)}</ul></div>'
    if f.is_chapeau and f.subtasks:
        items = "".join(item(sid) for sid in f.subtasks)
        nav += f'<div class="nav"><b>Sous-tâches</b><ul>{items}</ul></div>'
    elif parent is not None and parent.subtasks:
        items = "".join(item(sid, "→ " if sid == f.id else "") for sid in parent.subtasks)
        nav += (
            f'<div class="nav"><b>Chapeau</b> : {link_to(parent.id, index, here)} '
            f"{esc(parent.titre)} {pill(parent.state)}<ul>{items}</ul></div>"
        )

    # ── précédent / suivant dans l'ordre de lecture (fratrie du chapeau, sinon chantier)
    seq = fiche_sequence(f, index)
    i = seq.index(f.id) if f.id in seq else -1

    def step(j: int) -> str:
        if i < 0 or not (0 <= j < len(seq)):
            return "<span></span>"
        o = index[seq[j]]
        arrow = "← " if j < i else ""
        suffix = "" if j < i else " →"
        return (
            f'<a href="{esc(fiche_href(o, here))}">{arrow}[{esc(o.id)}] {esc(o.titre)}{suffix}</a>'
        )

    prevnext = f'<div class="prevnext">{step(i - 1)}{step(i + 1)}</div>' if i >= 0 else ""

    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    return write_if_changed(
        f.path.with_suffix(".html"),
        f'<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>[{esc(f.id)}] {esc(f.titre)}</title><style>{LIGHT_CSS}</style></head><body>"
        f'<div class="banner"><div class="inner">{breadcrumb}'
        f"<h1>[{esc(f.id)}] {esc(f.titre)} {pill(f.state)}</h1>"
        f'<p class="meta">{meta}</p></div></div>'
        f"<article>{warn}{nav}{toc}{body}{prevnext}"
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
    # lien vers la feuille de route si elle a déjà été générée (navigation dans les deux sens)
    lots_index = backlog.parent / "lots" / "index.html"
    body = ""
    if lots_index.exists():
        rel = Path(os.path.relpath(lots_index, base)).as_posix()
        body = f'<p class="xnav"><a href="{esc(rel)}">📚 Feuille de route (lots)</a></p>'
    body += f'<div class="counters">{counters}</div>'
    anomalies, infos = check_graph(all_fiches, index)
    if anomalies:
        items = "".join(f"<li>{esc(a)}</li>" for a in anomalies)
        body += (
            f'<div class="anomalies"><b>⚠ Graphe — {len(anomalies)} anomalie(s)</b>'
            f"<ul>{items}</ul></div>"
        )
    if infos:
        items = "".join(f"<li>{esc(i)}</li>" for i in infos)
        body += f'<div class="infos"><b>ℹ À relire</b><ul>{items}</ul></div>'
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
    for i in infos:
        print(f"  ℹ {i}")
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
/* composants partagés fiches ↔ lots (pastille, sommaire, prev/next, tableaux larges) */
.badge,.pill{display:inline-block;padding:2px 12px;border-radius:999px;color:#fff;
font-size:.72em;font-weight:600;vertical-align:middle;letter-spacing:.3px}
.banner h1 .badge,.banner h1 .pill{margin-left:8px}
.banner .meta{margin:8px 0 0;opacity:.9;font-size:.88em;line-height:1.7}
.banner .meta b{opacity:.75;font-weight:600}
.prio-P1{color:#ffd7d7;font-weight:700}.prio-P2{color:#ffe9c2}.prio-P3{opacity:.8}
.toc-box{background:#eef4f8;border:1px solid #dbe6ee;border-radius:8px;padding:4px 20px 10px;
margin:0 0 22px;font-size:.93em}
.toc-box summary{cursor:pointer;font-weight:600;color:#1d4d66;padding:8px 0}
.toc-box ul{margin:4px 0;padding-left:20px}
.toc-box a{text-decoration:none;color:#2c6e91}.toc-box a:hover{text-decoration:underline}
.prevnext{display:flex;justify-content:space-between;gap:16px;margin:26px 0 0;font-size:.9em;
border-top:1px solid #e3e9ee;padding-top:14px}
.prevnext a{color:#2c6e91;text-decoration:none}.prevnext a:hover{text-decoration:underline}
.tablewrap{overflow-x:auto;margin:1.2em 0}
@media print{article{border:none;padding:0}.toc-box,.prevnext,.crumb{display:none}}
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


# ── lots (feuille de route) ─────────────────────────────────────────────────────
# Un LOT est une tranche de la feuille de route, pilotée par l'architecte/PO. C'est un
# objet DIFFÉRENT d'une fiche de backlog : pas de dossier-état, pas de graphe de
# dépendances — un statut lisible DANS la fiche, et un ordre de lecture.
# Pourquoi une sous-commande dédiée plutôt qu'un md2html par fichier : sans index, sans
# badge d'état et sans navigation, un dossier de lots redevient un tas de pages orphelines.

# (motif cherché dans le statut, libellé affiché, couleur) — ORDRE SIGNIFICATIF :
# le premier motif trouvé gagne, donc le plus spécifique d'abord.
LOT_STATUSES: list[tuple[str, str, str]] = [
    ("abandonn", "Abandonné", "#b91c1c"),
    ("obsol", "Obsolète", "#6b7280"),
    ("livr", "Livré", "#15803d"),
    ("valid", "Validé", "#15803d"),
    ("en cours", "En cours", "#1d4ed8"),
    ("maturation", "Maturation", "#8b7bd8"),
    ("brouillon", "Brouillon", "#b45309"),
    ("proposé", "Proposé", "#b45309"),
    ("pilotage", "Pilotage", "#5c6b76"),
]
LOT_INTRO = "README.md"  # la feuille de route elle-même : devient le corps de l'index


def lot_status(raw: str) -> tuple[str, str]:
    """Normalise un statut en texte libre vers (libellé court, couleur). Inconnu -> gris."""
    low = raw.lower()
    for key, label, color in LOT_STATUSES:
        if key in low:
            return label, color
    return (raw.strip()[:24] or "—"), "#6b7280"


def inline_md(s: str) -> str:
    """Échappe le HTML puis rend le markdown INLINE minimal (gras, code) d'un champ d'en-tête.

    Ces valeurs sont du markdown écrit à la main : les afficher en texte brut laisserait des
    `**` visibles dans le bandeau."""
    out = esc(s)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", out)


def lot_field_of(fields: list[tuple[str, str]], name: str) -> str:
    """Valeur d'un champ d'en-tête par son nom (insensible à la casse) ; "" si absent."""
    for key, val in fields:
        if key.lower() == name.lower():
            return val
    return ""


def split_header_fields(md_text: str) -> tuple[list[tuple[str, str]], str]:
    """Détache le bloc d'en-tête `**Champ** : valeur` qui suit le H1, du reste du corps.

    Ces champs sont réaffichés dans le bandeau de la page : les laisser AUSSI dans le corps
    produit un doublon visuel (et un badge d'état qui répète la ligne juste en dessous).
    Retourne ([(champ, valeur), …], corps sans ce bloc).
    """
    lines = md_text.splitlines()
    i = 0
    while i < len(lines) and (not lines[i].strip() or lines[i].lstrip().startswith("#")):
        i += 1  # saute le H1 et les lignes vides qui l'entourent
    fields: list[tuple[str, str]] = []
    j = i
    while j < len(lines):
        m = re.match(r"\s*\*\*([^*]+)\*\*\s*:\s*(.+?)\s*$", lines[j])
        if not m:
            break
        fields.append((m.group(1).strip(), m.group(2).strip()))
        j += 1
    if not fields:
        return [], md_text
    return fields, "\n".join(lines[:i] + lines[j:])


def lot_excerpt(text: str, limit: int = 200) -> str:
    """Premier paragraphe de prose (ni titre, ni champ d'en-tête, ni tableau, ni liste)."""
    for block in re.split(r"\n\s*\n", text):
        b = block.strip()
        if not b or b.startswith(("#", ">", "|", "-", "*", "!", "```", "---", "**")):
            continue
        clean = re.sub(r"[*_`#\[\]]", "", b.replace("\n", " ")).strip()
        if len(clean) > limit:
            clean = clean[: limit - 1].rsplit(" ", 1)[0] + "…"
        return clean
    return ""


@dataclass
class Lot:
    slug: str
    titre: str
    label: str
    color: str
    date: str
    excerpt: str
    body_md: str
    header: list[tuple[str, str]]
    path: Path
    order: tuple[int, str]


def load_lot(path: Path) -> Lot:
    """Charge une fiche de lot : frontmatter s'il y en a un, sinon en-tête `**Champ** :`."""
    meta, body_md = parse_frontmatter(path.read_text(encoding="utf-8"))
    titre = str(meta.get("titre", meta.get("title", "")))
    if not titre:
        m = re.search(r"^#\s+(.+?)\s*$", body_md, re.MULTILINE)
        titre = re.sub(r"[*_`]", "", m.group(1)).strip() if m else path.stem
    fields, body_md = split_header_fields(body_md)
    statut = str(meta.get("statut", meta.get("status", ""))) or lot_field_of(fields, "Statut")
    date_raw = str(meta.get("date", "")) or lot_field_of(fields, "Date")
    date = re.split(r"\s+[—–-]\s+", date_raw)[0].strip()[:40]
    label, color = lot_status(statut)
    # le bandeau reprend l'en-tête retiré du corps (+ les champs venus du frontmatter)
    header = fields or [(k, v) for k, v in (("Statut", statut), ("Date", date_raw)) if v]
    num = re.search(r"lot[ _-]?(\d+)", path.stem, re.IGNORECASE)
    return Lot(
        slug=path.stem,
        titre=titre,
        label=label,
        color=color,
        date=date,
        excerpt=lot_excerpt(body_md),
        body_md=body_md,
        header=header,
        path=path,
        order=(int(num.group(1)) if num else 999, path.stem),
    )


LOTS_CSS = (
    LIGHT_CSS
    + """
.wrap{max-width:1000px;margin:0 auto;padding:26px 16px 60px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:18px}
.card{background:#fff;border:1px solid #e3e9ee;border-radius:10px;padding:18px 20px;
box-shadow:0 1px 3px rgba(20,40,60,.06);display:flex;flex-direction:column;
transition:box-shadow .15s,transform .15s}
.card:hover{box-shadow:0 6px 18px rgba(20,40,60,.12);transform:translateY(-2px)}
.card h2{margin:0 0 8px;font-size:1.08em;line-height:1.35}
.card h2 a{color:#1d4d66;text-decoration:none}.card h2 a:hover{color:#2c6e91}
.card .excerpt{color:#5c6b76;font-size:.9em;flex:1;margin:10px 0 14px}
.card .foot{display:flex;justify-content:space-between;font-size:.82em;color:#5c6b76}
.counters{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 24px}
.counter{background:#fff;border:1px solid #e3e9ee;border-radius:10px;padding:10px 18px;
min-width:110px}
.counter b{font-size:1.4em;display:block}.counter span{color:#5c6b76;font-size:.8em}
.roadmap{margin-top:38px}
"""
)


def render_lot_page(lot: Lot, lots: list[Lot], dash: Path) -> bool:
    """Rend une fiche de lot : breadcrumb, badge d'état, sommaire, précédent/suivant."""
    here = lot.path.parent
    md = markdown.Markdown(extensions=MD_EXT)
    body = md.convert(lot.body_md)
    body = body.replace("<table>", '<div class="tablewrap"><table>').replace(
        "</table>", "</table></div>"
    )
    body = re.sub(r"<h1[^>]*>.*?</h1>", "", body, count=1, flags=re.DOTALL)  # H1 = le bandeau

    toc_html = getattr(md, "toc", "")
    toc = ""
    if toc_html.count("<li>") >= 2:
        toc = f'<details class="toc-box" open><summary>Sommaire</summary>{toc_html}</details>'

    crumbs = ['<a href="index.html">📚 Lots</a>']
    if dash.exists():
        crumbs.insert(
            0, f'<a href="{esc(Path(os.path.relpath(dash, here)).as_posix())}">🏠 Backlog</a>'
        )
    crumbs.append(f"<b>{esc(lot.slug)}</b>")

    i = lots.index(lot)
    prev = (
        f'<a href="{esc(lots[i - 1].slug)}.html">← {esc(lots[i - 1].titre)}</a>'
        if i
        else "<span></span>"
    )
    nxt = (
        f'<a href="{esc(lots[i + 1].slug)}.html">{esc(lots[i + 1].titre)} →</a>'
        if i + 1 < len(lots)
        else "<span></span>"
    )
    badge = f'<span class="badge" style="background:{lot.color}">{esc(lot.label)}</span>'
    meta = "<br>".join(f"<b>{esc(k)}</b> : {inline_md(v)}" for k, v in lot.header) or "&nbsp;"
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    return write_if_changed(
        lot.path.with_suffix(".html"),
        f'<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{esc(lot.titre)}</title><style>{LOTS_CSS}</style></head><body>"
        f'<div class="banner"><div class="inner">'
        f'<nav class="crumb">{" › ".join(crumbs)}</nav>'
        f"<h1>{esc(lot.titre)} {badge}</h1><p>{meta}</p></div></div>"
        f"<article>{toc}{body}"
        f'<div class="prevnext">{prev}{nxt}</div>'
        f'<p class="gen">Généré le {now} depuis {esc(lot.path.name)} — le .md fait foi.</p>'
        f"</article></body></html>",
    )


def cmd_lots(project: str, lots_dir: Path, backlog: Path) -> int:
    """Génère l'index des lots + une page par lot (états, sommaire, navigation)."""
    if not lots_dir.is_dir():
        print(f"✗ {lots_dir} : dossier introuvable — une fiche par lot (`lot-N-*.md`),")
        print("  plus un README.md optionnel qui sert de corps à l'index.")
        return 1
    dash = backlog / "maturation" / "etat.html"
    # `_*.md` = modèles et notes de travail (même convention que le backlog) ; README = l'intro.
    lots = sorted(
        (
            load_lot(p)
            for p in lots_dir.glob("*.md")
            if p.name != LOT_INTRO and not p.name.startswith("_")
        ),
        key=lambda x: x.order,
    )
    rewritten = sum(render_lot_page(lot, lots, dash) for lot in lots)

    counts: dict[str, tuple[int, str]] = {}
    for lot in lots:
        n, _ = counts.get(lot.label, (0, lot.color))
        counts[lot.label] = (n + 1, lot.color)
    counters = "".join(
        f'<div class="counter"><b style="color:{c}">{n}</b><span>{esc(lab)}</span></div>'
        for lab, (n, c) in sorted(counts.items())
    )
    cards = "".join(
        f'<div class="card"><h2><a href="{esc(lot.slug)}.html">{esc(lot.titre)}</a></h2>'
        f'<div><span class="badge" style="background:{lot.color}">{esc(lot.label)}</span></div>'
        f'<p class="excerpt">{esc(lot.excerpt)}</p>'
        f'<div class="foot"><span>{esc(lot.date)}</span><span>{esc(lot.path.name)}</span></div>'
        f"</div>"
        for lot in lots
    )
    # README.md (la feuille de route) devient le corps de l'index : une seule page à ouvrir.
    intro = ""
    intro_src = lots_dir / LOT_INTRO
    if intro_src.exists():
        _, intro_md = parse_frontmatter(intro_src.read_text(encoding="utf-8"))
        _, intro_md = split_header_fields(intro_md)  # l'en-tête du README n'est pas un lot
        html_intro = markdown.Markdown(extensions=MD_EXT).convert(intro_md)
        html_intro = re.sub(r"<h1[^>]*>.*?</h1>", "", html_intro, count=1, flags=re.DOTALL)
        html_intro = html_intro.replace("<table>", '<div class="tablewrap"><table>').replace(
            "</table>", "</table></div>"
        )
        intro = f'<article class="roadmap">{html_intro}</article>'
    nav = ""
    if dash.exists():
        rel = Path(os.path.relpath(dash, lots_dir)).as_posix()
        nav = f'<nav class="crumb"><a href="{esc(rel)}">🏠 Backlog du projet</a></nav>'

    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    out = lots_dir / "index.html"
    write_if_changed(
        out,
        f'<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{esc(project)} — lots</title><style>{LOTS_CSS}</style></head><body>"
        f'<div class="banner"><div class="inner">{nav}'
        f"<h1>{esc(project)} — feuille de route</h1>"
        f"<p>{len(lots)} lot(s) — le .md fait foi, cette page est dérivée.</p></div></div>"
        f'<div class="wrap"><div class="counters">{counters}</div>'
        f'<div class="cards">{cards}</div>{intro}'
        f'<p class="gen">Généré le {now} — ne pas éditer (écrasé).</p></div></body></html>',
    )
    for lot in lots:
        print(f"  {lot.label:<12} {lot.slug}")
    print(f"  {'Pages .html':<12} {rewritten}/{len(lots)} réécrite(s)")
    print(f"✓ index des lots : {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="backlog-kit Python : dashboard + lots + md2html")
    sp = ap.add_subparsers(dest="cmd", required=True)
    d = sp.add_parser("dashboard", help="génère maturation/etat.html + archives")
    d.add_argument("--project", default="Projet")
    d.add_argument("--backlog", default="docs/backlog", type=Path)
    lo = sp.add_parser("lots", help="génère l'index des lots + une page par lot")
    lo.add_argument("--project", default="Projet")
    lo.add_argument("--lots", default="docs/lots", type=Path)
    lo.add_argument("--backlog", default="docs/backlog", type=Path)
    m = sp.add_parser("md2html", help="convertit un .md en .html lisible/imprimable")
    m.add_argument("src", type=Path)
    m.add_argument("dest", type=Path)
    m.add_argument("title", nargs="?", default="Doc")
    m.add_argument("banner", nargs="?", default="")
    a = ap.parse_args()
    if a.cmd == "dashboard":
        return cmd_dashboard(a.project, a.backlog)
    if a.cmd == "lots":
        return cmd_lots(a.project, a.lots, a.backlog)
    return cmd_md2html(a.src, a.dest, a.title, a.banner)


if __name__ == "__main__":
    sys.exit(main())
