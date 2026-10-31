"""The HTML page and its trace.

Every value from a file is written through ``Page.ref`` and comes out as
``<span class="n" data-src="<file key>" data-path='<json path>' data-op="<op>">value</span>``; the same
record goes into the trace sidecar. The page's own words are the fixed vocabulary and a few labels; they
carry no digits, so a test can read the page back and check that every digit on it sits inside a traced
span and that each span's value is the value at that path in that file.

Model text (vote reasons, verdict reasons, probe claims) is shown verbatim inside ``<q class="model">`` and
labelled as the model's words; the board neither edits nor summarises it.

``blind=True`` makes a page that can leave the machine: strip ids become ``strip_a``, ``strip_b``, ... in
every string, pixel positions, the score section (it names sites and pieces), file paths and the ledger's
start time are dropped. The leak guard is run over the result and the build fails if anything is left.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from landers.board.load import ALL_GRADES, CandidateCase, Case, Ref, Source, StripCase
from landers.models import leak

LABELS = {"found": "mask returned"}  # a file's key that is not a board word


def label(key: str) -> str:
    """A file's key as a column label; the only change is a unit digit, so the page's own words stay digit free."""
    return LABELS.get(key, key.replace("km2", "km²"))


VOCABULARY = (
    "Grades: candidate, needs second look, likely natural, not assessed. "
    "A later stage can lower a grade and never raise one; a model's opinion lowers, never raises. "
    "Test outcomes: pass, fail, unsure, not run. Votes: hardware, natural, unsure. "
    "Review actions: keep, lower. Nothing on this page is a finding; every value is copied from the file "
    "named in its tooltip."
)
CSS = """
body{font:14px/1.4 system-ui,sans-serif;margin:1.5em auto;max-width:96em;padding:0 1em;color:#1b2a38}
h1{font-size:1.5em}h2{font-size:1.2em;margin-top:2em;border-bottom:1px solid #ccd}
h3{font-size:1em;margin-top:1.4em}h4,h5{font-size:.95em;margin:.8em 0 .2em}
table{border-collapse:collapse;margin:.6em 0;font-size:13px}
th,td{border:1px solid #d6dbe3;padding:.2em .5em;text-align:left;vertical-align:top}
th{background:#eef3f8}
.n{border-bottom:1px dotted #8aa;cursor:help}
.grade-candidate{background:#e4f2e6}.grade-needs-second-look{background:#fdf1e4}
.grade-likely-natural{background:#f1f1f1}.grade-not-assessed{background:#f6e9f2}
q.model{font-style:italic;color:#444}q.model:before{content:"model: \\201C"}q.model:after{content:"\\201D"}
.flag{color:#8a1c1c;font-weight:600}.note{color:#555}
.vocab{background:#eef3f8;padding:.6em 1em;border-left:4px solid #5b7a99}
details{margin:.3em 0 .8em}summary{cursor:pointer;color:#345}
"""


def fmt(v) -> str:
    if v is None:
        return "–"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int | float):
        return json.dumps(v)
    if isinstance(v, str):
        return v
    return json.dumps(v, separators=(", ", ": "))


def slug(grade: str) -> str:
    return "grade-" + grade.replace(" ", "-")


class Page:
    def __init__(self, sources: list[Source], blind_map: dict[str, str] | None = None):
        self.parts: list[str] = []
        self.trace: list[dict] = []
        self.sources = {s.key: s for s in sources}
        self.blind_map = blind_map or {}

    # -- text

    def blind(self, s: str) -> str:
        for k in sorted(self.blind_map, key=len, reverse=True):
            s = s.replace(k, self.blind_map[k])
        return s

    def t(self, s: str) -> str:
        return html.escape(self.blind(str(s)))

    def add(self, s: str) -> None:
        self.parts.append(s)

    def p(self, text: str, cls: str = "") -> None:
        c = f' class="{cls}"' if cls else ""
        self.add(f"<p{c}>{self.t(text)}</p>")

    def ref(self, r: Ref | None, cls: str = "") -> str:
        """The traced span for a Ref; a dash for an absent value."""
        if r is None:
            return "–"
        path = self.blind(json.dumps(list(r.path)))
        src = self.blind(r.source)
        value = json.loads(self.blind(json.dumps(r.value)))
        self.trace.append({"source": src, "path": json.loads(path), "op": r.op, "value": value})
        title = self.t(f"{r.source} {r.path_text}" + (f" ({r.op})" if r.op else ""))
        c = " " + cls if cls else ""
        return (
            f'<span class="n{c}" data-src="{html.escape(src)}" data-path="{html.escape(path)}" '
            f'data-op="{html.escape(r.op)}" title="{title}">{self.t(fmt(r.value))}</span>'
        )

    def q(self, r: Ref | None) -> str:
        """Model text, verbatim and marked as such."""
        if r is None or r.value in (None, ""):
            return "–"
        return f'<q class="model">{self.ref(r)}</q>'

    def grade(self, r: Ref | None) -> str:
        if r is None:
            return "–"
        return f'<span class="{slug(r.value)}">{self.ref(r)}</span>'

    # -- structure

    def table(self, headers: list[str], rows: list[list[str]]) -> None:
        self.add("<table><tr>" + "".join(f"<th>{self.t(h)}</th>" for h in headers) + "</tr>")
        for row in rows:
            self.add("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>")
        self.add("</table>")

    def key(self, src: Source, path: tuple, k: str) -> str:
        """A dict key as a label. A key with a digit in it (a histogram bin, a strip id) is a value of the
        file and is traced like one."""
        if any(ch.isdigit() for ch in k):
            return self.ref(Ref(k, src.key, path, "key"))
        return self.t(label(k))

    def generic(self, src: Source, path: tuple, depth: int = 0) -> None:
        """Any JSON shape as nested tables, every scalar traced; for files whose shape the board does not
        know (the coverage map, registration summaries, check results)."""
        obj = src.walk(path)
        if isinstance(obj, dict):
            scalars = [(k, v) for k, v in obj.items() if not isinstance(v, dict | list)]
            nested = [(k, v) for k, v in obj.items() if isinstance(v, dict | list)]
            if scalars:
                self.table(
                    ["field", "value"], [[self.key(src, path, k), self.ref(src.get(*path, k))] for k, _ in scalars]
                )
            for k, _ in nested:
                if depth >= 3:
                    self.table([self.key(src, path, k)], [[self.ref(src.get(*path, k))]])
                    continue
                self.add(f"<h{min(3 + depth, 5)}>{self.key(src, path, k)}</h{min(3 + depth, 5)}>")
                self.generic(src, path + (k,), depth + 1)
        elif isinstance(obj, list):
            if obj and all(isinstance(x, dict) for x in obj) and depth < 3:
                keys = sorted({k for x in obj for k in x if not isinstance(x[k], dict | list)})
                rows = [[self.ref(src.get(*path, i, k)) for k in keys] for i in range(len(obj))]
                self.table([self.key(src, path, k) for k in keys], rows)
                deep = sorted({k for x in obj for k in x if isinstance(x[k], dict | list)})
                for k in deep:
                    self.add(f"<h{min(4 + depth, 5)}>{self.key(src, path, k)}</h{min(4 + depth, 5)}>")
                    for i in range(len(obj)):
                        if k in obj[i]:
                            self.generic(src, path + (i, k), depth + 1)
            else:
                flat = [i for i, x in enumerate(obj) if not isinstance(x, dict | list)]
                if flat:
                    self.table(["value"], [[self.ref(src.get(*path, i))] for i in flat])
                for i, x in enumerate(obj):
                    if isinstance(x, dict | list):
                        self.generic(src, path + (i,), depth + 1)
        else:
            self.table(["value"], [[self.ref(Ref(obj, src.key, path))]])


# ----------------------------------------------------------------------------------------------- sections


def _header(pg: Page, case: Case, blind: bool) -> None:
    pg.add("<h1>Case board</h1>")
    pg.add(f'<p class="vocab">{pg.t(VOCABULARY)}</p>')
    pg.table(
        ["run", "detector version", "code commit"],
        [[pg.ref(case.run), pg.ref(case.detector), pg.ref(case.git_commit)]],
    )
    if blind:
        pg.p("Blind page: strip ids are replaced by neutral keys and pixel positions are not shown.", "note")
    for n in case.notes:
        pg.p(n, "note")


def _strip_summary(pg: Page, st: StripCase, blind: bool) -> None:
    pg.add(f"<h2>Strip {pg.t(st.strip)}</h2>")
    pg.table(
        ["valid area km²", "scale m per px", "tiles", "candidates in the list"],
        [[pg.ref(st.valid_area_km2), pg.ref(st.scale_m), pg.ref(st.tiles), pg.ref(st.n_candidates)]],
    )
    if st.manifest_note:
        pg.p(st.manifest_note, "flag")
    pg.add(f"<h3>Grades over the whole list, after the {pg.t(st.list_stage)} stage</h3>")
    pg.table([g for g in ALL_GRADES], [[pg.ref(st.list_grade_counts[g]) for g in ALL_GRADES]])
    pg.add("<h3>Final grades over the candidates shown below</h3>")
    pg.table([g for g in ALL_GRADES], [[pg.ref(st.shown_grade_counts[g]) for g in ALL_GRADES]])


def _persistence(pg: Page, st: StripCase) -> None:
    if not st.directions:
        pg.p("Persistence: no second date in these files; grades stay at the detector stage.", "note")
        return
    pg.add("<h3>Persistence</h3>")
    for d in st.directions:
        pg.add(f"<h4>from {pg.ref(d.from_strip)} to {pg.ref(d.to_strip)} ({pg.t(d.source)})</h4>")
        pg.table(
            ["match radius px", "counts", "by branch", "inject check"],
            [[pg.ref(d.match_radius_px), pg.ref(d.counts), pg.ref(d.by_branch), pg.ref(d.inject_check)]],
        )
        if d.registration is not None:
            pg.add("<details><summary>registration</summary>")
            pg.generic(pg.sources[d.source], d.path + ("registration",), 2)
            pg.add("</details>")


def _candidates(pg: Page, st: StripCase, blind: bool) -> None:
    pg.add("<h3>Candidates</h3>")
    if not st.model_files:
        pg.p("No model files for this strip: SAM, votes and review columns are empty.", "note")
    heads = [
        "id",
        "rank",
        "branch",
        "score",
        "like it per km² of this strip, same branch, other half",
        "grade chain",
        "final",
        "seen on second date",
        "mask",
        "diameter m",
        "elongation",
        "edge contrast",
    ]
    heads += ["size", "shape", "edge", "votes", "review"]
    if not blind:
        heads += ["row", "col"]
    rows = []
    for c in st.candidates:
        chain = " → ".join(f"{pg.t(s.name)} {pg.grade(s.after)}" for s in c.chain)
        sam = c.sam or {}
        tests = c.tests
        votes = "–"
        if c.votes is not None:
            votes = ", ".join(f"{pg.ref(v['verdict'])} {pg.ref(v['confidence'])}" for v in c.votes)
        review = "–"
        if c.verdict is not None and "action" in c.verdict:
            review = pg.ref(c.verdict["action"])
        elif c.verdict is not None:
            review = "not reviewed"
        rank = Ref(c.rank, "candidates", ("strips", st.strip, "candidates"), "rank by score")
        row = [
            f'<a href="#{pg.t(st.strip)}-{c.cid}">{pg.t(c.cid)}</a>',
            pg.ref(rank),
            pg.ref(c.branch),
            pg.ref(c.score),
            f"below {pg.ref(c.half_rate_below)}" if c.half_rate_below is not None else pg.ref(c.half_rate),
            chain,
            f'<span class="{slug(c.final)}">{pg.t(c.final)}</span>',
            pg.ref((c.persist or {}).get("seen")),
            pg.ref(sam.get("found")),
            pg.ref(sam.get("equiv_diameter_m")),
            pg.ref(sam.get("elongation")),
            pg.ref(sam.get("edge_contrast")),
            pg.ref(tests.get("sam_size", {}).get("outcome")),
            pg.ref(tests.get("sam_shape", {}).get("outcome")),
            pg.ref(tests.get("sam_edge", {}).get("outcome")),
            votes,
            review,
        ]
        if not blind:
            row += [pg.ref(c.row), pg.ref(c.col)]
        rows.append(row)
    pg.table(heads, rows)
    for c in st.candidates:
        _detail(pg, st, c, blind)


def _detail(pg: Page, st: StripCase, c: CandidateCase, blind: bool) -> None:
    pg.add(
        f'<details id="{pg.t(st.strip)}-{c.cid}"><summary>{pg.t(c.cid)}: {pg.ref(c.branch)}, '
        f"final grade {pg.t(c.final)}</summary>"
    )
    for f in c.flags:
        pg.p(f, "flag")
    for nr in c.not_run:
        pg.add(f'<p class="note">not run: {pg.ref(nr)}</p>')
    if c.shape or c.area_px is not None:
        pg.add("<h4>detector</h4>")
        keys = ["area_px", *c.shape]
        pg.table(keys, [[pg.ref(c.area_px), *[pg.ref(c.shape[k]) for k in c.shape]]])
    if c.persist:
        pg.add("<h4>persistence</h4>")
        keys = [k for k in ("seen", "distance_px", "branch_b", "score_b", "note") if k in c.persist]
        pg.table(keys, [[pg.ref(c.persist[k]) for k in keys]])
    if c.tests:
        pg.add("<h4>tests</h4>")
        pg.table(
            ["test", "outcome", "value", "limit"],
            [[pg.t(n), pg.ref(t["outcome"]), pg.ref(t["value"]), pg.ref(t["limit"])] for n, t in c.tests.items()],
        )
    if c.sam:
        pg.add("<h4>SAM mask</h4>")
        keys = ["found", "confidence", *[k for k in c.sam if k not in ("found", "confidence") and c.sam[k] is not None]]
        pg.table([label(k) for k in keys] + ["box"], [[pg.ref(c.sam[k]) for k in keys] + [pg.ref(c.sam_box)]])
    if c.probe:
        pg.add("<h4>recognition probe</h4>")
        keys = [k for k in ("n", "recognised", "max_confidence") if k in c.probe]
        pg.table(keys + ["claims"], [[pg.ref(c.probe[k]) for k in keys] + [pg.q(c.probe.get("claims"))]])
    if c.votes is not None:
        pg.add("<h4>votes</h4>")
        pg.table(
            ["verdict", "confidence", "off schema", "reason"],
            [
                [pg.ref(v["verdict"]), pg.ref(v["confidence"]), pg.ref(v["off_schema"]), pg.q(v["reason"])]
                for v in c.votes
            ],
        )
        if c.vote_note is not None:
            pg.add(f"<p>after the votes: {pg.ref(c.vote_note)}</p>")
    if c.verdict is not None:
        pg.add("<h4>review</h4>")
        if "action" in c.verdict:
            pg.table(
                ["action", "cites", "reason"],
                [[pg.ref(c.verdict["action"]), pg.ref(c.verdict["cites"]), pg.q(c.verdict["reason"])]],
            )
        else:
            pg.p("no verdict recorded for this candidate", "note")
    if c.checks:
        pg.add("<h4>checks ordered by the reviewer</h4>")
        pg.table(["check"], [[pg.ref(ch)] for ch in c.checks])
    pg.add("</details>")


def _models(pg: Page, st: StripCase) -> None:
    if st.probe_total:
        pg.add("<h3>Recognition probe</h3>")
        pg.add(f"<p>candidates probed: {pg.ref(st.probe_total['candidates'])}</p>")
        rows = []
        for c in st.candidates:
            if c.probe:
                rows.append(
                    [
                        pg.t(c.cid),
                        pg.ref(c.probe.get("n")),
                        pg.ref(c.probe.get("recognised")),
                        pg.ref(c.probe.get("max_confidence")),
                        pg.q(c.probe.get("claims")),
                    ]
                )
        pg.table(["id", "crops asked", "answers that recognised the place", "highest confidence", "claims"], rows)
    if st.review:
        r = st.review
        pg.add("<h3>Review</h3>")
        pg.table(
            [
                "turns",
                "stopped",
                "verdicts",
                "lowered",
                "tool calls",
                "checks",
                "in the final answer but never recorded",
            ],
            [
                [
                    pg.ref(r["backend_turns"]),
                    pg.ref(r["stopped"]),
                    pg.ref(r["verdicts"]),
                    pg.ref(r["lowered"]),
                    pg.ref(r["tool_calls"]),
                    pg.ref(r["checks"]),
                    pg.ref(r["unrecorded"]),
                ]
            ],
        )
        if r["by_tool"]:
            pg.table(list(r["by_tool"]), [[pg.ref(v) for v in r["by_tool"].values()]])


def _ledger(pg: Page, led: Source | None, blind: bool) -> None:
    pg.add("<h2>Ledger</h2>")
    if led is None:
        pg.p("No ledger file: no model call is recorded for this case.", "note")
        return
    pg.table(
        ["backend", "total cost usd"] + ([] if blind else ["started"]),
        [
            [pg.ref(led.get("backend")), pg.ref(led.get("total_cost_usd"))]
            + ([] if blind else [pg.ref(led.get("started"))])
        ],
    )
    models = list(led.walk(("entries",), {}) or {})
    cols = ["units", "attempts", "ok", "failed", "refused", "input_tokens", "output_tokens", "cost_usd"]
    rows = []
    for m in models:
        rows.append(
            [pg.t(m), pg.ref(led.get("units", m)), pg.ref(led.get("caps", m))]
            + [pg.ref(led.get("entries", m, c)) for c in cols]
        )
    pg.table(["model", "unit", "cap"] + cols, rows)


def _coverage(pg: Page, case: Case) -> None:
    pg.add("<h2>Coverage</h2>")
    if case.coverage is None:
        pg.p("No coverage map in these files.", "note")
        return
    if case.coverage_figure is not None:
        pg.add(f'<p><img src="{html.escape(case.coverage_figure.name)}" alt="coverage map" style="max-width:100%"></p>')
    pg.generic(case.coverage, ())


def _score(pg: Page, sc: Source | None) -> None:
    if sc is None:
        return
    pg.add("<h2>Score against the tuning key</h2>")
    pg.table(
        [
            "recall at N",
            "N",
            "pieces recorded",
            "pieces at rank N or better",
            "median false alarms per km²",
            "passed",
            "matching",
        ],
        [
            [
                pg.ref(sc.get("recall_at_n")),
                pg.ref(sc.get("top_n")),
                pg.ref(sc.get("n_pieces_recorded")),
                pg.ref(sc.get("n_pieces_found")),
                pg.ref(sc.get("median_false_alarms_per_km2")),
                pg.ref(sc.get("passed")),
                pg.ref(sc.get("matching")),
            ]
        ],
    )
    pieces = sc.walk(("pieces",), []) or []
    if pieces:
        pg.add("<h3>Pieces</h3>")
        keys = ["site", "piece", "kind", "strip", "rank", "distance_px", "branch"]
        pg.table(keys, [[pg.ref(sc.get("pieces", i, k)) for k in keys] for i in range(len(pieces))])
    strips = sc.walk(("strips",), []) or []
    if strips:
        pg.add("<h3>Strips</h3>")
        keys = ["strip", "n_candidates", "n_true_hits", "false_alarms", "valid_area_km2", "false_alarms_per_km2"]
        pg.table([label(k) for k in keys], [[pg.ref(sc.get("strips", i, k)) for k in keys] for i in range(len(strips))])
    skipped = sc.walk(("skipped",), []) or []
    if skipped:
        pg.add("<h3>Not scored</h3>")
        pg.table(["reason"], [[pg.ref(sc.get("skipped", i))] for i in range(len(skipped))])


def _files(pg: Page, case: Case, blind: bool) -> None:
    pg.add("<h2>Files this page was built from</h2>")
    rows = []
    for s in case.sources:
        sha = Ref(s.sha256, s.key, (), "sha256 of the file")
        where = Ref(str(s.path), s.key, (), "path of the file")
        rows.append([pg.t(s.key)] + ([] if blind else [pg.ref(where)]) + [pg.ref(sha)])
    pg.table(["key", *([] if blind else ["path"]), "file hash"], rows)


# ----------------------------------------------------------------------------------------------- entry


def blind_map(case: Case) -> dict[str, str]:
    """Strip ids to neutral keys; persistence file keys too, since they are named after a site or a pair."""
    letters = "abcdefghijklmnopqrstuvwxyz"

    def key(i: int) -> str:
        return letters[i] if i < 26 else str(i)

    out = {sid: f"strip_{key(i)}" for i, sid in enumerate(sorted(st.strip for st in case.strips))}
    pers = [s.key for s in case.sources if s.key.startswith("persist:")]
    out.update({k: f"persist:{key(i)}" for i, k in enumerate(pers)})
    return out


def render(case: Case, blind: bool = False) -> tuple[str, dict]:
    """The page and its trace. With ``blind`` the leak guard runs over the page and a leak raises."""
    pg = Page(case.sources, blind_map(case) if blind else None)
    _header(pg, case, blind)
    for st in case.strips:
        _strip_summary(pg, st, blind)
        _persistence(pg, st)
        _candidates(pg, st, blind)
        _models(pg, st)
    _ledger(pg, case.ledger, blind)
    _coverage(pg, case)
    if not blind:
        _score(pg, case.score)
    _files(pg, case, blind)
    body = "\n".join(pg.parts)
    head = f'<head><meta charset="utf-8"><title>Case board</title><style>{CSS}</style></head>'
    page = f'<!doctype html><html lang="en">{head}<body>\n{body}\n</body></html>\n'
    trace = {
        "blind": blind,
        "sources": {
            pg.blind(s.key): ({} if blind else {"path": str(s.path)}) | {"sha256": s.sha256} for s in case.sources
        },
        "values": pg.trace,
    }
    if blind:
        leak.check_text(page, "board page")
        leak.check_strings(trace, "board trace")
    return page, trace


def write(case: Case, out: Path, blind: bool = False) -> tuple[Path, Path]:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    page, trace = render(case, blind)
    out.write_text(page)
    tp = out.with_name(out.stem + "_trace.json")
    tp.write_text(json.dumps(trace, indent=1) + "\n")
    if (
        case.coverage_figure is not None
        and case.coverage_figure.resolve() != (out.parent / case.coverage_figure.name).resolve()
    ):
        (out.parent / case.coverage_figure.name).write_bytes(case.coverage_figure.read_bytes())
    return out, tp
