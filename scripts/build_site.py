"""Split the single-file report into the pages served at GitHub Pages.

The site is not a second write-up. It is the same report, cut along its own
section boundaries and given navigation, so the two cannot say different things:
every page here is produced from `reports/cardiotrace-report.html`, which is
itself produced from the analysis artefacts. Editing prose means editing
`render_report.py`; this file only decides what goes on which page.

Figures become ordinary files under `docs/assets/` rather than inline data URIs.
The single-file report keeps them embedded, because that version exists to be
emailed and has to survive with no server behind it.

The chrome this file adds -- the author line, the evidence strip, the finding
cards, the meta descriptions -- states numbers, and the same rule applies to
them: `facts()` reads every one from the artefact that produced it, and a
missing artefact leaves the tile off the page rather than falling back to a
literal. Two of those facts had no producer at all until now: the suite writes
its own size from `tests/conftest.py`, and the follow-up length comes from
`build_cohort_results.py`.
"""

from __future__ import annotations

import base64
import csv
import html as htmlmod
import json
import re
import shutil
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

ROOT = Path(__file__).parent.parent
REPORT = ROOT / "reports" / "cardiotrace-report.html"
DOCS = ROOT / "docs"
ASSETS = DOCS / "assets"

from src.descriptive import DESC_CYCLES, display_cycle  # noqa: E402

N_CYCLES = len(DESC_CYCLES)

REPO_URL = "https://github.com/UTSGJohnsonSong/cardiotrace"
SITE_URL = "https://utsgjohnsonsong.github.io/cardiotrace/"

AUTHOR = "Zekun Song"
AUTHOR_PROGRAM = "Computer Science &amp; Data Science, University of Toronto"
AUTHOR_STATEMENT = (
    "I designed and built CardioTrace end to end &mdash; from reproducible CDC "
    "data acquisition to survey-weighted inference and prospective risk modelling.")

# ── FILL THESE IN ───────────────────────────────────────────────────────────
# None of these three is known to this repository. An empty string means the
# thing is left off the site entirely and `main()` says so on stdout; nothing is
# ever rendered as a dead link or a "coming soon" page.
#
# TABLEAU_VIZ is the workbook path out of a Tableau Public share URL, e.g.
# "CardioTraceExplorer/Dashboard1". Publishing is a manual step -- it needs a
# Tableau account -- and docs/tableau-dashboard.md is the recipe. Setting it
# here adds the Explore page and its nav entry; leaving it empty adds neither.
RESUME_URL = ""     # e.g. "https://.../zekun-song-resume.pdf"
LINKEDIN_URL = ""   # e.g. "https://www.linkedin.com/in/<handle>/"
TABLEAU_VIZ = ""    # e.g. "CardioTraceExplorer/Dashboard1"
# ────────────────────────────────────────────────────────────────────────────

CARD = "assets/cardiotrace-card.png"
CARD_ALT = ("Crude and age-standardised cardiovascular disease prevalence in US "
            "adults, NHANES 1999-2022: the crude series rises while the "
            "age-standardised series falls.")

# An ECG trace in the categorical series blue on the paper ground, so the tab
# icon carries the same two colours as the figures. Inline, because the site is
# allowed no external requests.
FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<style>.g{fill:#f7f6f2}@media(prefers-color-scheme:dark){.g{fill:#16161a}}</style>'
    '<rect class="g" width="32" height="32" rx="6"/>'
    '<path d="M2 20h5.2l2.6-7.4 4.2 14.2 4.1-19 2.9 12.2H30" fill="none" '
    'stroke="#2a78d6" stroke-width="2.6" stroke-linecap="round" '
    'stroke-linejoin="round"/></svg>')
FAVICON = "data:image/svg+xml," + urllib.parse.quote(FAVICON_SVG, safe="")

# Section number in the report -> (filename, nav label, short standfirst).
PAGES = {
    "2": ("burden.html", "Burden",
          f"How the burden of cardiovascular disease moved across {N_CYCLES} NHANES "
          "cycles, once the ageing of the population is taken out of it."),
    "3": ("pandemic.html", "Pandemic",
          "Whether the pandemic bent the trend, and what a single post-pandemic "
          "observation can and cannot establish."),
    "4": ("cohort.html", "Cohort",
          "A prospective cohort of adults free of cardiovascular disease at "
          "baseline, followed for up to twenty years."),
    "5": ("learning.html", "Learning",
          "Whether the prediction model is limited by the eleven variables it "
          "carries or by the form it takes, and what a systematic screen of the "
          "laboratory finds."),
}
METHODS = ("methods.html", "Methods",
           "The comparison against the prespecified risk-score benchmark, the data "
           "sources, and what was done to them.")
EXPLORE = ("explore.html", "Explore",
           "The estimates the report had no room for: six conditions across "
           f"{N_CYCLES} cycles, by age band and by race and ethnicity.")

NAV = [("index.html", "Overview"), ("burden.html", "Burden"),
       ("pandemic.html", "Pandemic"), ("cohort.html", "Cohort"),
       ("learning.html", "Learning"), ("methods.html", "Methods")]
if TABLEAU_VIZ:
    NAV.append((EXPLORE[0], EXPLORE[1]))

EXTRA_CSS = """
/* ── site chrome: the only styling the single-file report does not need ── */

/* --- accessibility -------------------------------------------------------
   Measured against --paper #f7f6f2 (WCAG 2.x):
     --ink-3 was #898781 3.32:1,  --series #2a78d6 4.08:1,  --flag #eb6834 2.96:1
   All three failed the 4.5:1 that normal-size text needs. --series and --flag
   are also the categorical slots the matplotlib figures draw with, so they do
   NOT move: render_report.py darkens --ink-3 (text everywhere but one dot) and
   adds --series-text / --flag-text for the two places those two colours carry
   text. As marks they were always fine -- #eb6834 on the figure plate is
   3.12:1, above the 3:1 WCAG 1.4.11 asks of a graphical object. ------------ */
.skip {
  /* fixed, not absolute: absolute resolves against the initial containing
     block, so on a scrolled page the focused link lands at document top and is
     never seen. */
  position: fixed; left: 8px; top: -64px; z-index: 40;
  font-family: var(--sans); font-size: 13px; font-weight: 600;
  background: var(--ink); color: var(--paper);
  padding: 10px 16px; border-radius: 2px; text-decoration: none;
  transition: top 120ms ease;
}
.skip:focus { top: 8px; }
main.wrap:focus { outline: none; }

:root { scroll-behavior: smooth; }
@media (prefers-reduced-motion: reduce) { :root { scroll-behavior: auto; } }
/* the sticky bar would otherwise sit on top of whatever was jumped to */
h1, h2, h3, [id] { scroll-margin-top: 78px; }

/* The report styles only a:focus-visible. Everything else made focusable here
   -- the table regions, the main landmark -- needs a ring of its own. */
:focus-visible { outline: 2px solid var(--series); outline-offset: 3px; }
.twrap:focus-visible { outline-offset: 2px; }

/* --- site nav ------------------------------------------------------------ */
.sitenav {
  position: sticky; top: 0; z-index: 10;
  background: var(--paper);
  border-bottom: 1px solid var(--rule-soft);
}
@supports (background: color-mix(in srgb, red 50%, transparent)) {
  .sitenav {
    background: color-mix(in srgb, var(--paper) 92%, transparent);
    backdrop-filter: saturate(1.2) blur(8px);
  }
}
.sitenav-inner {
  max-width: 1080px; margin: 0 auto; padding: 0 32px;
  display: flex; align-items: baseline; gap: 28px; flex-wrap: wrap;
  min-height: 54px;
}
.sitenav .brand {
  font-family: var(--sans); font-size: 12px; font-weight: 700;
  letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink);
  text-decoration: none; margin-right: auto;
}
.sitenav a {
  font-family: var(--sans); font-size: 13px; color: var(--ink-3);
  text-decoration: none; padding: 4px 0; border-bottom: 2px solid transparent;
}
.sitenav a:hover { color: var(--ink-2); }
.sitenav a[aria-current="page"] {
  color: var(--ink); border-bottom-color: var(--series); font-weight: 600;
}

@media (max-width: 640px) {
  /* One line that scrolls, instead of three lines that eat the viewport. */
  .sitenav-inner {
    flex-wrap: nowrap; overflow-x: auto; overscroll-behavior-x: contain;
    scroll-snap-type: x proximity; scrollbar-width: none;
    align-items: center; gap: 20px; padding: 0 18px; min-height: 46px;
  }
  .sitenav-inner::-webkit-scrollbar { width: 0; height: 0; }
  .sitenav-inner > * { flex: 0 0 auto; scroll-snap-align: start; }
  /* margin-right:auto strands every link off-screen inside a scroller. */
  .sitenav .brand { margin-right: 6px; }
  .sitenav a { font-size: 12.5px; padding: 3px 0; }
  .masthead { padding: 40px 0 26px; }     /* the bar already costs 46px */
  h1, h2, h3, [id] { scroll-margin-top: 62px; }
}

/* --- author line --------------------------------------------------------- */
.colophon { padding-top: 34px; }
.colophon h2 { font-size: clamp(21px, 2.4vw, 26px); }
.colophon-affil {
  font-family: var(--sans); font-size: 13.5px; color: var(--ink-2); margin: 0;
}
.colophon-stmt { font-size: 17px; line-height: 1.55; color: var(--ink-2);
                 margin: 14px 0 0; }
.colophon-links {
  display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 22px;
  margin-top: 18px; font-family: var(--sans); font-size: 13.5px;
}
.colophon-links a {
  font-weight: 600; text-decoration: none; color: var(--series-text);
  border-bottom: 1px solid var(--rule); padding-bottom: 2px;
}
.colophon-links a:hover { border-bottom-color: var(--series-text); }
.colophon-links a.lead::after { content: " \\2192"; }

/* --- evidence strip ------------------------------------------------------ */
.evidence { padding-top: 46px; }
.stats.evidence-strip {
  grid-template-columns: repeat(auto-fit, minmax(164px, 1fr));
  margin: 4px 0 0;
}

/* --- contents ------------------------------------------------------------ */
.toc {
  margin: 32px 0 0; padding: 18px 22px 14px;
  background: var(--plate); border: 1px solid var(--rule-soft);
  font-family: var(--sans);
}
.toc-label {
  font-size: 10px; font-weight: 700; letter-spacing: 0.11em;
  text-transform: uppercase; color: var(--ink-3); margin: 0 0 12px;
}
.toc ol { margin: 0; padding: 0; list-style: none; columns: 2; column-gap: 34px; }
@media (max-width: 700px) { .toc ol { columns: 1; } }
.toc li { margin: 0 0 8px; break-inside: avoid; font-size: 13.5px; line-height: 1.4; }
.toc li.toc-h3 { padding-left: 16px; }
.toc a { color: var(--ink-2); text-decoration: none;
         border-bottom: 1px solid transparent; }
.toc a:hover { color: var(--ink); border-bottom-color: var(--rule); }

/* --- back to top ---------------------------------------------------------
   The guaranteed path is the "Back to top" link in .pagefoot, present in the
   DOM on every page and reachable by keyboard everywhere. The floating pill is
   a pointer affordance and is inert -- visibility:hidden, so not focusable --
   until the page has been scrolled, which modern browsers can do with a
   scroll-driven animation and no script at all. Browsers without it simply
   never see the pill and lose nothing. ------------------------------------- */
.toplink { display: none; }
@supports (animation-timeline: scroll()) {
  .toplink {
    position: fixed; right: 20px; bottom: 20px; z-index: 20;
    display: inline-flex; align-items: center; gap: 6px;
    font-family: var(--sans); font-size: 11.5px; font-weight: 700;
    letter-spacing: 0.09em; text-transform: uppercase;
    color: var(--ink-2); background: var(--plate);
    border: 1px solid var(--rule); border-radius: 2px;
    padding: 9px 13px; text-decoration: none;
    box-shadow: 0 1px 3px rgb(0 0 0 / 0.10);
    opacity: 0; visibility: hidden;
    animation: toplink-in linear both;
    animation-timeline: scroll(root block);
    animation-range: 620px 1100px;
  }
  @keyframes toplink-in {
    from { opacity: 0; visibility: hidden; }
    to   { opacity: 1; visibility: visible; }
  }
}

/* --- finding cards: the number first ------------------------------------- */
.findings { display: grid; gap: 1px; background: var(--rule-soft);
            border: 1px solid var(--rule-soft); margin: 32px 0 8px; }
.finding { background: var(--plate); padding: 22px 24px;
           display: grid; grid-template-columns: 1fr auto; gap: 4px 24px;
           align-items: start; }
.finding > * { grid-column: 1; }
.finding .chip { grid-column: 2; grid-row: 1; }
.finding .fnum { grid-row: 1; margin: 0; display: flex;
                 align-items: baseline; flex-wrap: wrap; gap: 4px 10px; }
.finding .fnum b {
  font-family: var(--sans); font-size: 30px; font-weight: 700;
  font-variant-numeric: tabular-nums; letter-spacing: -0.025em;
  line-height: 1.05; color: var(--ink);
}
.finding .fnum span {
  font-family: var(--sans); font-size: 12.5px; font-weight: 600;
  letter-spacing: 0.02em; color: var(--ink-2);
}
.finding h3 { font-family: var(--serif); font-size: 19px; font-weight: 700;
              text-transform: none; letter-spacing: 0; color: var(--ink);
              margin: 8px 0 0; padding: 0; border: 0; }
.finding .fci {
  font-family: var(--sans); font-size: 12px; color: var(--ink-3);
  font-variant-numeric: tabular-nums; margin: 2px 0 0;
}
.finding .what { margin: 10px 0 0; color: var(--ink-2); font-size: 16px;
                 line-height: 1.5; max-width: 60ch; }
.finding .go { margin: 6px 0 0; font-family: var(--sans);
               font-size: 13px; font-weight: 600; }
@media (max-width: 640px) {
  .finding { grid-template-columns: 1fr; }
  /* fnum has to give up its pinned row here, or the chip auto-places after it
     and the reading order becomes number, chip, heading. */
  .finding .fnum { grid-row: auto; }
  .finding .chip { grid-column: 1; grid-row: auto; justify-self: start;
                   order: -1; margin-bottom: 8px; }
  .finding .fnum b { font-size: 26px; }
}

/* --- the explorer, when one is published --------------------------------- */
.vizwrap {
  margin: 30px 0; background: var(--plate);
  border: 1px solid var(--rule); border-radius: 3px; padding: 14px;
  overflow-x: auto;
}
.vizwrap > div { min-width: 1000px; }

/* --- footer -------------------------------------------------------------- */
.pagefoot {
  margin-top: 56px; padding-top: 24px; border-top: 1px solid var(--rule);
  display: flex; justify-content: space-between; gap: 20px; flex-wrap: wrap;
  font-family: var(--sans); font-size: 13px;
}
.pagefoot a { font-weight: 600; }
.pagefoot .byline { color: var(--ink-2); font-weight: 600; }
.pagefoot .footlinks { display: flex; flex-wrap: wrap; gap: 6px 18px; }
"""


# ── artefact-derived facts ───────────────────────────────────────────────────

def signed(x: float, dp: int = 2) -> str:
    """Percentage points, plain ASCII sign -- for meta-tag attribute values."""
    return f"{100 * x:+.{dp}f}"


def signed_html(x: float, dp: int = 2) -> str:
    """Percentage points with a typographic minus -- for prose."""
    return signed(x, dp).replace("-", "&minus;")


def num(n: int) -> str:
    return f"{n:,}"


def facts() -> dict:
    """Every number the site chrome states, read from the artefact that made it.

    Nothing in this file may type a statistic. A fact whose artefact is missing
    is left off the page rather than falling back to a literal, because a
    literal that outlived its analysis is exactly the failure this project
    already had: six numbers wrong at once the moment the age base changed.
    """
    desc = json.loads(
        (ROOT / "reports" / "descriptive_results.json").read_text(encoding="utf-8"))
    model = json.loads(
        (ROOT / "reports" / "model_results.json").read_text(encoding="utf-8"))
    p1, p2 = desc["part1"], desc["part2"]

    catalog = ROOT / "data" / "catalog" / "nhanes_file_catalog.csv"
    with catalog.open(newline="", encoding="utf-8") as fh:
        n_files = sum(1 for _ in csv.reader(fh)) - 1          # minus the header

    with (ROOT / "reports" / "tables" / "strobe_part3.csv").open(encoding="utf-8") as fh:
        final = list(csv.DictReader(fh))[-1]

    # Selected on the horizon, not on the dict key: that key carries an en dash
    # and a year range, and would break the moment either is relabelled.
    tenyr = next(v for v in model["prediction"].values() if v["horizon_years"] == 10.0)

    f = {
        "n_cycles":     p1["n_cycles"],
        "n_adults":     p1["n_adults"],
        "age_floor":    p1["age_floor"],
        "n_files":      n_files,
        "cohort_n":     int(final["n"]),
        "cvd_deaths":   int(float(final["cvd_deaths"])),
        "std_slope":    p1["std_slope_per_decade"],
        "std_slope_ci": p1["std_slope_ci"],
        "gap":          p2["gap"],
        "gap_ci":       p2["gap_ci"],
        # display_cycle here, not at each of the four use sites: the last one
        # to be added would have been the one that forgot.
        "post_cycle":   display_cycle(p2["post_cycle"]),
        "post_cycle_key": p2["post_cycle"],
        "harrell_c":    tenyr["harrell_c"],
        "c_horizon":    int(tenyr["horizon_years"]),
        "c_n":          tenyr["n"],
        "missing":      [],
    }

    p4 = ROOT / "reports" / "part4_learning_results.json"
    if p4.exists():
        learn = json.loads(p4.read_text(encoding="utf-8"))
        gain = next(v for k, v in learn["arms"]["deltas"].items() if k == "cox_wide")
        f |= {"n_candidates": learn["screen"]["n_candidates"],
              "n_selected": len(learn["screen"]["selected"]),
              "delta_c_wide": gain["delta"], "delta_c_wide_lo": gain["lo"],
              "delta_c_wide_hi": gain["hi"],
              "delta_c_gbm": learn["arms"]["deltas"]["gbm_p"]["delta"],
              "n_top5_forbidden": learn["importance"]["n_top5_not_admissible"]}
    else:
        f["missing"].append(
            "the fourth finding -- run scripts/build_learning_results.py")

    cohort_json = ROOT / "reports" / "cohort_results.json"
    if cohort_json.exists():
        f["followup_years"] = int(
            json.loads(cohort_json.read_text(encoding="utf-8"))["max_followup_years"])
    else:
        f["missing"].append(
            "mortality follow-up -- run scripts/build_cohort_results.py")

    tests_json = ROOT / "reports" / "test_summary.json"
    if tests_json.exists():
        t = json.loads(tests_json.read_text(encoding="utf-8"))
        if t["failed"] == 0 and t["exit_status"] == 0:
            f["n_tests"] = t["collected"]
        else:
            f["missing"].append(
                f"test count -- the last full run had {t['failed']} failure(s)")
    else:
        f["missing"].append(
            "test count -- run the whole suite: .venv/Scripts/python.exe -m pytest")
    return f


# ── reading the report apart ─────────────────────────────────────────────────

def read_report() -> str:
    return REPORT.read_text(encoding="utf-8")


def extract_style(html: str) -> str:
    return re.search(r"<style>(.*?)</style>", html, re.S).group(1)


def extract_masthead(html: str) -> str:
    return re.search(r"(<header class=\"masthead\">.*?</header>)", html, re.S).group(1)


def split_sections(html: str) -> dict[str, str]:
    """Section number -> its full <section> markup."""
    out = {}
    for block in re.findall(r"<section>.*?</section>", html, re.S):
        found = re.search(r"<div class=\"sec-num\">(.*?)</div>", block, re.S)
        key = re.sub(r"&nbsp;|\s+", "", found.group(1)) if found else "?"
        out[key] = block
    return out


def share_card() -> None:
    """Build the social card from the headline figure.

    No text is drawn on it. The figure already renders its own title and
    subtitle from the artefacts, so the card cannot state a number this project
    did not compute, and it needs no font file to do it.
    """
    from PIL import Image, ImageDraw

    src = ROOT / "reports" / "figures" / "part1_standardisation.png"
    fig = Image.open(src).convert("RGBA")
    w, h, pad = 1200, 630, 56
    s = min((w - 2 * pad) / fig.width, (h - 2 * pad - 40) / fig.height)
    fig = fig.resize((round(fig.width * s), round(fig.height * s)), Image.LANCZOS)

    card = Image.new("RGB", (w, h), (252, 252, 251))   # --plate: matches the figure
    top = pad + round((h - 2 * pad - 40 - fig.height) * 0.42)   # optically centred
    card.paste(fig, ((w - fig.width) // 2, top), fig)
    d = ImageDraw.Draw(card)
    d.rectangle([pad, h - 52, w - pad, h - 51], fill=(225, 224, 217))  # --rule-soft
    d.rectangle([0, h - 10, w, h], fill=(42, 120, 214))               # --series keel
    ASSETS.mkdir(parents=True, exist_ok=True)
    card.save(ASSETS / "cardiotrace-card.png", optimize=True)


def externalise_images(html: str) -> str:
    """Write each inlined PNG to docs/assets and point the page at the file.

    Names come from the figure the report inlined, recovered by matching the
    decoded bytes against the files on disk -- so a renamed figure breaks loudly
    here rather than shipping a page with a missing image.
    """
    known = {p.read_bytes(): p.name for p in (ROOT / "reports" / "figures").glob("*.png")}
    ASSETS.mkdir(parents=True, exist_ok=True)

    def repl(m: re.Match) -> str:
        raw = base64.b64decode(m.group(1))
        name = known.get(raw)
        if name is None:
            raise SystemExit("an inlined figure matches no file in reports/figures")
        shutil.copyfile(ROOT / "reports" / "figures" / name, ASSETS / name)
        return f'src="assets/{name}"'

    return re.sub(r'src="data:image/png;base64,([A-Za-z0-9+/=]+)"', repl, html)


# ── head, navigation, page shell ─────────────────────────────────────────────

def attr(s: str) -> str:
    """Safe inside a double-quoted attribute, without flattening entities.

    Escaping the whole string would turn `&mdash;` into `&amp;mdash;` and print
    it literally in a search result. Only the quote can actually break out.
    """
    return s.replace('"', "&quot;")


def head(title: str, description: str, canonical: str, style: str) -> str:
    """Title, description, canonical, author, favicon and one social card.

    Everything is same-origin or inline: the site is allowed no external
    requests, so the icon is an inline SVG data URI and the card is a PNG this
    script writes into docs/assets/.
    """
    url = SITE_URL + canonical
    t, d = attr(title), attr(description)
    return f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{d}">
<meta name="author" content="{AUTHOR}">
<meta name="color-scheme" content="light dark">
<link rel="canonical" href="{url}">
<link rel="icon" href="{FAVICON}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="CardioTrace">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{d}">
<meta property="og:url" content="{url}">
<meta property="og:locale" content="en_US">
<meta property="og:image" content="{SITE_URL}{CARD}">
<meta property="og:image:type" content="image/png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{CARD_ALT}">
<meta property="article:author" content="{AUTHOR}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{t}">
<meta name="twitter:description" content="{d}">
<meta name="twitter:image" content="{SITE_URL}{CARD}">
<meta name="twitter:image:alt" content="{CARD_ALT}">
<style>{style}{EXTRA_CSS}</style>"""


def titles_and_descriptions(f: dict) -> dict[str, tuple[str, str]]:
    """filename -> (<title>, meta description).

    The descriptions carry statistics, so they are formatted from `facts()` like
    everything else on the site.
    """
    return {
        "index.html": (
            f"CardioTrace &mdash; Population Cardiovascular Research | {AUTHOR}",
            f"Survey-weighted analysis of cardiovascular disease in "
            f"{num(f['n_adults'])} US adults across {f['n_cycles']} NHANES cycles, "
            f"with a linked-mortality cohort of {num(f['cohort_n'])}. Designed and "
            f"built end to end by {AUTHOR}."),
        "burden.html": (
            f"Burden &mdash; CardioTrace | {AUTHOR}",
            f"Age-standardised cardiovascular prevalence across {f['n_cycles']} "
            f"NHANES cycles: the standardised series moves {signed(f['std_slope'])} "
            f"pp per decade while the crude series rises with the ageing of the "
            f"population."),
        "pandemic.html": (
            f"Pandemic &mdash; CardioTrace | {AUTHOR}",
            f"Whether COVID-19 bent the cardiovascular prevalence trend: "
            f"{f['post_cycle']} sits {signed(f['gap'])} pp from the extrapolated "
            f"counterfactual, with a 95% interval that contains zero."),
        "cohort.html": (
            f"Cohort &mdash; CardioTrace | {AUTHOR}",
            f"A prospective cohort of {num(f['cohort_n'])} US adults free of "
            f"cardiovascular disease at baseline, {num(f['cvd_deaths'])} "
            f"cardiovascular deaths, competing risks modelled; Harrell C "
            f"{f['harrell_c']:.3f} at {f['c_horizon']} years on held-out cycles."),
        "methods.html": (
            f"Methods &mdash; CardioTrace | {AUTHOR}",
            f"Sources, estimation and reproducibility: {num(f['n_files'])} NHANES "
            f"public-use files catalogued before anything was downloaded, "
            f"design-based variance, and the benchmark against the ASCVD Pooled "
            f"Cohort Equations."),
        # Guarded like every other consumer of `facts()`. Without this the
        # build dies here with a bare KeyError, hundreds of lines before the
        # loop that explains which artefact is missing and how to make it.
        "learning.html": (
            f"Learning &mdash; CardioTrace | {AUTHOR}",
            (f"Is the {f['harrell_c']:.3f} concordance limited by the variable "
             f"set or the model form? A screen of {f['n_candidates']} laboratory "
             f"candidates against the eleven, and gradient boosting against a "
             f"cause-specific Cox pair on the same held-out cycles."
             if "n_candidates" in f else
             f"Is the {f['harrell_c']:.3f} concordance limited by the variable "
             f"set or by the model form?")),
        "explore.html": (
            f"Explore &mdash; CardioTrace | {AUTHOR}",
            f"Every published estimate, pivotable: six conditions across "
            f"{f['n_cycles']} NHANES cycles, by age band and by race and "
            f"ethnicity, with design-based intervals."),
        "cardiotrace-report.html": (
            f"Full report &mdash; CardioTrace | {AUTHOR}",
            f"The complete CardioTrace write-up in one file: every section, table "
            f"and figure for {num(f['n_adults'])} adults across {f['n_cycles']} "
            f"NHANES cycles and a {num(f['cohort_n'])}-person mortality cohort."),
    }


def author_links(lead: bool = False) -> str:
    """Explore / Methodology / GitHub / Resume / LinkedIn.

    Resume and LinkedIn are dropped entirely while their constants are empty:
    a link to nowhere is worse than no link.
    """
    items = []
    if lead:
        items += [("#findings", "Explore findings", "lead"),
                  ("methods.html", "View methodology", "lead")]
    items.append((REPO_URL, "GitHub", ""))
    if RESUME_URL:
        items.append((RESUME_URL, "Resume", ""))
    if LINKEDIN_URL:
        items.append((LINKEDIN_URL, "LinkedIn", ""))
    return "".join(
        '<a href="{}"{}>{}</a>'.format(href, f' class="{cls}"' if cls else "", text)
        for href, text, cls in items)


def nav(current: str) -> str:
    mark = ' aria-current="page"'
    links = "".join(
        '<a href="{}"{}>{}</a>'.format(href, mark if href == current else "", label)
        for href, label in NAV)
    return (f'<nav class="sitenav" aria-label="Sections of this report">'
            f'<div class="sitenav-inner">'
            f'<a class="brand" href="index.html">CardioTrace</a>{links}'
            f'</div></nav>')


ENTITY = re.compile(r"<[^>]+>")
HEADING = re.compile(r"<h([23])>(.*?)</h\1>", re.S)
ANCHORED = re.compile(r'<h([23]) id="([^"]+)">(.*?)</h\1>', re.S)
TWRAP = re.compile(r'<div class="twrap">(\s*<table>\s*<caption>(.*?)</caption>)', re.S)


def plain(markup: str) -> str:
    return re.sub(r"\s+", " ", htmlmod.unescape(ENTITY.sub(" ", markup))).strip()


def slugify(markup: str, seen: set[str]) -> str:
    t = re.sub(r"[^a-z0-9]+", "-", plain(markup).lower()).strip("-")
    if len(t) > 56:
        t = t[:56].rsplit("-", 1)[0]
    base = t or "section"
    t, n = base, 1
    while t in seen:
        n += 1
        t = f"{base}-{n}"
    seen.add(t)
    return t


def anchor_headings(html: str, seen: set[str]) -> str:
    """Give every h2/h3 a stable id, so a contents block can point at it."""
    return HEADING.sub(
        lambda m: f'<h{m.group(1)} id="{slugify(m.group(2), seen)}">'
                  f'{m.group(2)}</h{m.group(1)}>',
        html)


def contents(html: str, label: str = "On this page") -> str:
    """A static table of contents.

    No JavaScript: the ids are known at build time, so a scroll-spy would add a
    runtime dependency to reproduce what the anchor already does.
    """
    items = ANCHORED.findall(html)
    if len(items) < 3:
        return ""
    lis = "".join(f'<li class="toc-h{lvl}"><a href="#{hid}">{plain(txt)}</a></li>'
                  for lvl, hid, txt in items)
    return (f'<nav class="toc" aria-label="{label}"><p class="toc-label">{label}</p>'
            f'<ol>{lis}</ol></nav>')


def scrollable_tables(html: str) -> str:
    """A horizontally scrolling box with nothing focusable inside cannot be
    reached, let alone scrolled, from the keyboard. Make each one a labelled
    focusable region, named by the caption it already carries.
    """
    def repl(m: re.Match) -> str:
        cap = htmlmod.escape(plain(m.group(2)), quote=True)
        return (f'<div class="twrap" role="region" tabindex="0" '
                f'aria-label="Table: {cap}. Scrollable.">{m.group(1)}')
    return TWRAP.sub(repl, html)


# Guaranteed keyboard path back to the top, in the DOM on every page. The
# floating control in the CSS is a pointer affordance and nothing more.
TOPLINK = ('<a class="toplink" href="#top" aria-label="Back to top of page">'
           'Top <span aria-hidden="true">&uarr;</span></a>')


def page(title: str, description: str, canonical: str, style: str, current: str,
         body: str, prev_next: str = "") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
{head(title, description, canonical, style)}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
{nav(current)}
<main class="wrap" id="main" tabindex="-1">
{body}
<div class="pagefoot">
  <span>CardioTrace &middot; NHANES 1999&ndash;2022 &middot; NCHS Linked Mortality File<br>
  <span class="byline">{AUTHOR} &middot; {AUTHOR_PROGRAM}</span></span>
  <span class="footlinks">{prev_next}{author_links()}<a href="#top">Back to top &uarr;</a></span>
</div>
</main>
{TOPLINK}
</body>
</html>
"""


# ── the index ────────────────────────────────────────────────────────────────

def build_colophon() -> str:
    """The author line, in the register a journal uses: name, affiliation and a
    contribution statement, set in the same gutter grid as every section head.
    """
    return f"""<section class="colophon" aria-labelledby="colophon-h">
  <div class="sec-head"><div class="sec-num">AUTHOR</div>
  <h2 id="colophon-h">{AUTHOR}</h2></div>
  <div class="body-indent">
    <p class="colophon-affil">{AUTHOR_PROGRAM}</p>
    <p class="colophon-stmt measure">{AUTHOR_STATEMENT}</p>
    <nav class="colophon-links" aria-label="Author and project links">
      {author_links(lead=True)}
    </nav>
  </div>
</section>"""


def build_evidence(f: dict) -> str:
    """Engineering scale, every tile read from the artefact that produced it.

    n_cycles / n_adults  reports/descriptive_results.json  -> part1
    n_files              data/catalog/nhanes_file_catalog.csv (rows - header)
    n_tests              reports/test_summary.json  (written by tests/conftest.py)
    followup_years       reports/cohort_results.json (build_cohort_results.py)

    The last two are omitted, not invented, when their artefact is absent.
    """
    tiles = [
        ("Survey cycles", num(f["n_cycles"]), "NHANES 1999&ndash;2022, harmonised"),
        ("Public-use files catalogued", num(f["n_files"]),
         "each recorded with the rule that kept or dropped it"),
        (f"Adults {f['age_floor']}+ analysed", num(f["n_adults"]),
         "survey-weighted, design-based intervals"),
    ]
    if "n_tests" in f:
        tiles.append(("Automated tests", num(f["n_tests"]),
                      "the whole suite, green, on synthetic fixtures"))
    if "followup_years" in f:
        tiles.append(("Mortality follow-up", f"{f['followup_years']} yr",
                      "record linkage to the National Death Index"))
    cells = "".join(f'<div class="stat"><div class="k">{k}</div>'
                    f'<div class="v">{v}</div><div class="n">{n}</div></div>'
                    for k, v, n in tiles)
    return f"""<section class="evidence" aria-labelledby="evidence-h">
  <div class="sec-head"><div class="sec-num">BUILT</div>
  <h2 id="evidence-h">What it took to answer them</h2></div>
  <div class="body-indent">
    <div class="stats evidence-strip">{cells}</div>
  </div>
</section>"""


def build_findings(f: dict) -> str:
    """Three cards, each leading with its own number.

    slope + CI   reports/descriptive_results.json  part1.std_slope_per_decade,
                                                   part1.std_slope_ci
    gap   + CI   reports/descriptive_results.json  part2.gap, part2.gap_ci,
                                                   part2.post_cycle
    Harrell C    reports/model_results.json        prediction[horizon 10y].harrell_c
    """
    cards = [
        ("burden.html", f"The burden across {f['n_cycles']} cycles",
         "chip result", "Result",
         f"{signed_html(f['std_slope'])}&nbsp;pp", "per decade, age-standardised",
         f"95% CI {signed_html(f['std_slope_ci'][0])} to "
         f"{signed_html(f['std_slope_ci'][1])} pp",
         "Crude prevalence rose while the age-standardised series fell. The rise "
         "is the population ageing, not the disease spreading."),
        ("pandemic.html", "The pandemic", "chip quiet", "No detectable change",
         f"{signed_html(f['gap'])}&nbsp;pp",
         f"{f['post_cycle']} against the extrapolated trend",
         f"95% CI {signed_html(f['gap_ci'][0])} to {signed_html(f['gap_ci'][1])} pp "
         f"&mdash; contains zero",
         "The observed level sits above the pre-pandemic trend, but the interval "
         "contains zero. One post-pandemic cycle cannot settle it."),
        ("cohort.html", "Who dies of it", "chip result", "Result",
         f"{f['harrell_c']:.3f}", f"Harrell C, {f['c_horizon']}-year risk",
         f"held-out later cycles, n&nbsp;=&nbsp;{num(f['c_n'])}",
         "Blood pressure at examination predicts cardiovascular death up to twenty "
         "years later, validated forward in time rather than at random."),
    ]
    if "delta_c_wide" in f:
        cards.append(
            ("learning.html", "What limits it", "chip result", "Result",
             f"{f['delta_c_wide']:+.3f}".replace("-", "&minus;"),
             "Harrell C, from one screened variable",
             f"95% CI {f['delta_c_wide_lo']:+.3f} to {f['delta_c_wide_hi']:+.3f}"
             f" &mdash; gradient boosting on the same eleven: "
             f"{f['delta_c_gbm']:+.3f}".replace("-", "&minus;"),
             "The variable set was the binding constraint, not the model form. "
             f"And {f['n_top5_forbidden']} of the five variables the prediction "
             "leans on hardest are ones the causal model may not simply adjust "
             "for."))
    return "".join(
        f'<article class="finding"><span class="{cls}">{chip}</span>'
        f'<p class="fnum"><b>{value}</b> <span>{unit}</span></p>'
        f'<h3>{name}</h3><p class="fci">{ci}</p><p class="what">{what}</p>'
        f'<p class="go"><a href="{href}">Read this part &rarr;</a></p></article>'
        for href, name, cls, chip, value, unit, ci, what in cards)


def build_index(style: str, masthead: str, sections: dict[str, str],
                f: dict, meta: dict) -> str:
    """Overview: who made it, what it took, and what each part found."""
    title, desc = meta["index.html"]
    seen: set[str] = set()
    explore = ""
    if TABLEAU_VIZ:
        explore = ('<p class="measure" style="margin-top:14px">Every published '
                   f'estimate is also <a href="{EXPLORE[0]}">pivotable</a> &mdash; '
                   'the cells these three pages had no room for.</p>')
    body = f"""{masthead}

{build_colophon()}

{build_evidence(f)}

<section id="findings">
  <div class="sec-head"><div class="sec-num">THE&nbsp;PARTS</div>
  <h2>What each part asks, and what it found</h2></div>
  <div class="body-indent">
    <div class="findings">{build_findings(f)}</div>
    <p class="measure" style="margin-top:26px">The full write-up is also available
    as <a href="cardiotrace-report.html">a single page</a>, which carries every
    section, table and figure in one file.</p>{explore}
  </div>
</section>

{scrollable_tables(anchor_headings(sections["1"], seen))}"""
    return page(title, desc, "", style, "index.html", body)


def build_explore(style: str, f: dict, meta: dict) -> str:
    """The Tableau workbook, on a page of its own.

    Its own page for one reason. The embed loads a script from public.tableau.com,
    so this becomes the single page on the site that makes an external request
    and depends on a third party staying up. Every other page, including the
    emailed single-file report, stays self-contained -- and stays intact if
    Tableau Public changes its embed API or withdraws the workbook.
    """
    title, desc = meta["explore.html"]
    fname, label, stand = EXPLORE
    body = f"""<header class="masthead"><p class="eyebrow">CardioTrace</p>
<h1>{label}</h1><p class="standfirst measure">{stand}</p></header>

<section>
  <div class="sec-head"><div class="sec-num">7</div>
  <h2>The cells the report had no room for</h2></div>
  <div class="body-indent">
    <p class="lede measure">Each of the three analyses chooses one view, because
    an argument needs a spine. The estimates underneath cover six conditions,
    {f['n_cycles']} cycles, six age bands and five race-ethnicity groups. This
    page exists so a reader can ask a question those views did not.</p>

    <div class="vizwrap">
      <div class="tableauPlaceholder" id="viz-cardiotrace">
        <object class="tableauViz" style="display:none">
          <param name="host_url" value="https%3A%2F%2Fpublic.tableau.com%2F">
          <param name="embed_code_version" value="3">
          <param name="site_root" value="">
          <param name="name" value="{TABLEAU_VIZ}">
          <param name="tabs" value="no">
          <param name="toolbar" value="yes">
          <param name="showAppBanner" value="false">
        </object>
      </div>
    </div>
    <script src="https://public.tableau.com/javascripts/api/viz_v1.js"></script>

    <div class="note">
      <b>Read the intervals with the design in mind.</b> Age-band rows carry a
      crude rate and no interval: an age-specific rate has nothing left to
      standardise, and no design-based interval was computed for those cells.
      Where an interval does appear it is design-based, and the honest measure
      of how much independent information a cell holds is its variance-unit
      count, not its sample size.
    </div>

    <p class="measure">The workbook reads one file,
    <code>data/tableau/cardiotrace_prevalence.csv</code>, written by
    <code>scripts/build_tableau_extract.py</code>. That script copies values out
    of <code>reports/tables/</code> and recomputes nothing, so this page cannot
    disagree with the report; if it ever does, the cause is that one file rather
    than two analyses that drifted apart.</p>
  </div>
</section>"""
    return page(title, desc, fname, style, fname, body)


# ── the single-file report ───────────────────────────────────────────────────

def chrome_single_file(html: str, meta: dict) -> str:
    """Give the emailed report the same head, landmarks and contents.

    Every substitution is asserted. A silent no-match would ship a 22,000 px
    page with no metadata, no skip link and no contents, and nothing downstream
    would notice.
    """
    title, desc = meta["cardiotrace-report.html"]
    seen: set[str] = set()
    raw = html

    def once(pattern: str, repl: str, label: str, regex: bool = False) -> None:
        nonlocal raw
        before = raw
        raw = (re.sub(pattern, repl, raw, count=1, flags=re.S) if regex
               else raw.replace(pattern, repl, 1))
        if raw == before:
            raise SystemExit(f"single-file chrome: {label} matched nothing")

    # Its own charset and viewport come out first, or head() re-emits both and
    # the page ships two of each.
    once('<meta charset="utf-8">\n', "", "strip charset")
    once('<meta name="viewport" content="width=device-width, initial-scale=1">\n',
         "", "strip viewport")
    once(r"<title>.*?</title>",
         head(title, desc, "cardiotrace-report.html", "").split("<style>")[0].rstrip(),
         "head block", regex=True)
    once("</style>", EXTRA_CSS + "</style>", "chrome CSS")
    once('<body>\n<div class="wrap">',
         '<body>\n<a class="skip" href="#main">Skip to content</a>\n'
         '<main class="wrap" id="main" tabindex="-1">', "skip link and landmark")
    once("</div>\n</body>", f"</main>\n{TOPLINK}\n</body>", "closing landmark")

    raw = scrollable_tables(anchor_headings(raw, seen))
    once("</header>", "</header>\n" + contents(raw, "Contents"), "contents block")
    return raw


def main() -> None:
    html = read_report()
    style = extract_style(html)
    masthead = extract_masthead(html)
    sections = split_sections(html)
    f = facts()
    meta = titles_and_descriptions(f)

    DOCS.mkdir(exist_ok=True)
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    share_card()

    written = []

    body = build_index(style, masthead, sections, f, meta)
    (DOCS / "index.html").write_text(externalise_images(body), encoding="utf-8")
    written.append("index.html")

    order = [PAGES[k][0] for k in ("2", "3", "4", "5")] + [METHODS[0]]
    for i, key in enumerate(("2", "3", "4", "5")):
        fname, label, stand = PAGES[key]
        title, desc = meta[fname]
        seen: set[str] = set()
        sec = scrollable_tables(anchor_headings(sections[key], seen))
        body = page(title, desc, fname, style, fname,
                    f'<header class="masthead"><p class="eyebrow">CardioTrace</p>'
                    f'<h1>{label}</h1><p class="standfirst measure">{stand}</p></header>'
                    f'{contents(sec)}{sec}',
                    prev_next=f'<a href="{order[i + 1]}">Next &rarr;</a> &nbsp;&middot;&nbsp; ')
        (DOCS / fname).write_text(externalise_images(body), encoding="utf-8")
        written.append(fname)

    fname, label, stand = METHODS
    title, desc = meta[fname]
    seen = set()
    sec = scrollable_tables(anchor_headings(sections["6"] + sections["7"], seen))
    body = page(title, desc, fname, style, fname,
                f'<header class="masthead"><p class="eyebrow">CardioTrace</p>'
                f'<h1>{label}</h1><p class="standfirst measure">{stand}</p></header>'
                f'{contents(sec)}{sec}')
    (DOCS / fname).write_text(externalise_images(body), encoding="utf-8")
    written.append(fname)

    if TABLEAU_VIZ:
        (DOCS / EXPLORE[0]).write_text(build_explore(style, f, meta), encoding="utf-8")
        written.append(EXPLORE[0])

    # Deliberately NOT externalise_images: this is the copy a reader saves or
    # forwards, and the index promises it "carries every section, table and
    # figure in one file". Pointing it at docs/assets/ would cut it from 985 KB
    # to 85 KB and make that sentence false the moment anyone saved it.
    (DOCS / "cardiotrace-report.html").write_text(
        chrome_single_file(html, meta), encoding="utf-8")
    written.append("cardiotrace-report.html (single file)")

    for name in written:
        path = DOCS / name.split(" ")[0]
        print(f"  {name:<38s} {path.stat().st_size / 1024:6.0f} KB")
    n_fig = len([p for p in ASSETS.glob("*.png") if p.name != "cardiotrace-card.png"])
    print(f"  assets/  {n_fig} figures + 1 share card")
    if not RESUME_URL or not LINKEDIN_URL:
        print("  NOTE: RESUME_URL / LINKEDIN_URL are empty; those links were omitted.")
    if not TABLEAU_VIZ:
        print("  NOTE: TABLEAU_VIZ is empty; the Explore page was not built. "
              "See docs/tableau-dashboard.md.")
    for m in f["missing"]:
        print(f"  NOTE: evidence tile omitted -- {m}")


if __name__ == "__main__":
    main()
