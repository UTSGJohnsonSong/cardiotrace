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
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

ROOT = Path(__file__).parent.parent
REPORT = ROOT / "reports" / "cardiotrace-report.html"
DOCS = ROOT / "docs"
ASSETS = DOCS / "assets"

from src.descriptive import DESC_CYCLES, display_cycle  # noqa: E402
from scripts.tableau_atlas import PANELS, WORKBOOK, validate_current as validate_atlas, validate_snapshot  # noqa: E402

N_CYCLES = len(DESC_CYCLES)

REPO_URL = "https://github.com/UTSGJohnsonSong/cardiotrace"
SITE_URL = "https://utsgjohnsonsong.github.io/cardiotrace/"

AUTHOR = "Zekun Song"
AUTHOR_PROGRAM = "Computer Science &amp; Data Science, University of Toronto"

# The hero's positioning line, and it is NOT the LinkedIn headline verbatim.
# That one reads "Backend &amp; Data Engineer | Reliable Data Platforms &amp; Clinical
# AI", which is the right pitch on a profile a backend recruiter lands on and
# the wrong one on a site whose content is population health research: a
# research reader sees a backend engineer, a backend reader sees an
# epidemiology site, and neither finds what they came for. Same person, same
# facts, aimed at the page it sits on.
#
# The hireable signals are kept because they are what a recruiter scans for and
# cannot infer: the co-op window, work authorisation, and the stack.
AUTHOR_HEADLINE = (
    "Data &amp; Research Engineering &middot; Population Health, Clinical AI")
AUTHOR_CREDENTIALS = (
    "Python &middot; SQL &middot; PostgreSQL &middot; dbt &nbsp;|&nbsp; "
    "U of T CS + Data Science &nbsp;|&nbsp; "
    "Sep 2026 &ndash; Apr 2027 co-op &nbsp;|&nbsp; Canadian PR")
AUTHOR_STATEMENT = (
    "I designed and built CardioTrace end to end &mdash; from reproducible CDC "
    "data acquisition to survey-weighted inference and prospective risk modelling.")

# ── FILL THESE IN ───────────────────────────────────────────────────────────
# None of these three is known to this repository. An empty string means the
# thing is left off the site entirely and `main()` says so on stdout; nothing is
# ever rendered as a dead link or a "coming soon" page.
#
# The résumé is served from this repository rather than linked off-site, so the
# page cannot rot when a file-host link expires -- and so that what a reader
# downloads is a version this commit can be checked against.
#
# TABLEAU_VIZ is the workbook path out of a Tableau Public share URL, e.g.
# "CardioTraceExplorer/Dashboard1". Publishing is a manual step -- it needs a
# Tableau account -- and docs/tableau-dashboard.md is the recipe. Setting it
# here adds an interactive embed above the always-available reviewed previews.
RESUME_URL = "assets/Zekun_Song_Resume.pdf"
LINKEDIN_URL = "https://www.linkedin.com/in/zekun-song/"
EMAIL = "zekun.song@mail.utoronto.ca"
TABLEAU_VIZ = ""    # e.g. "CardioTraceExplorer/Dashboard1"
# ────────────────────────────────────────────────────────────────────────────

CARD = "assets/cardiotrace-card.png"
CARD_ALT = ("Crude and age-standardised cardiovascular disease prevalence in US "
            "adults, NHANES 1999-2023: the crude series rises while the "
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
          "cycles, with and without a common age distribution."),
    "3": ("pandemic.html", "Pandemic",
          "How the latest survey compares with the earlier trend, and what one post-pandemic "
          "observation can and cannot establish."),
    "4": ("cohort.html", "Cohort",
          "A prospective cohort of adults free of cardiovascular disease at "
          "baseline, followed for up to twenty years."),
    "5": ("learning.html", "Predictive Modeling",
          "Whether the prediction model is limited by the eleven variables it "
          "carries or by the form it takes, and what a systematic screen of "
          "additional candidate variables contribute."),
}
METHODS = ("methods.html", "Methods",
           "The comparison against the prespecified risk-score benchmark, the data "
           "sources, and what was done to them.")
EXPLORE = ("explore.html", "Tableau dashboards",
           "Three Tableau dashboards covering population trends, mortality risk and model comparisons.")

NAV = [("index.html", "Overview"), ("cardiotrace-report.html", "Read the report"),
       ("explore.html", "Tableau"), ("index.html#author", "About the author")]


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
  font-family: var(--sans); font-size: 14px; font-weight: 600;
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
  font-family: var(--sans); font-size: 13px; font-weight: 700;
  letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink);
  text-decoration: none; margin-right: auto;
}
.sitenav a {
  font-family: var(--sans); font-size: 14px; color: var(--ink-3);
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
  .sitenav a { font-size: 13.5px; padding: 3px 0; }
  .masthead { padding: 40px 0 26px; }     /* the bar already costs 46px */
  h1, h2, h3, [id] { scroll-margin-top: 62px; }
}

/* --- author line --------------------------------------------------------- */
.colophon { padding-top: 34px; }
.colophon h2 { font-size: clamp(21px, 2.4vw, 26px); }
.colophon-affil {
  font-family: var(--sans); font-size: 14.5px; color: var(--ink-2); margin: 0;
}
.colophon-stmt { font-size: 17px; line-height: 1.55; color: var(--ink-2);
                 margin: 14px 0 0; }
.colophon-links {
  display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 22px;
  margin-top: 18px; font-family: var(--sans); font-size: 14.5px;
}
.colophon-links a {
  font-weight: 600; text-decoration: none; color: var(--series-text);
  border-bottom: 1px solid var(--rule); padding-bottom: 2px;
}
.colophon-links a:hover { border-bottom-color: var(--series-text); }
.colophon-links a.lead::after { content: " \\2192"; }

/* --- front-page hero ------------------------------------------------------ */
/* The contact row sits in the first screen rather than at the foot: a reader
   who is convinced at the top should not have to scroll a 50,000-character
   report to act on it. */
.hero { padding-bottom: 12px; }
.cta {
  display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 20px;
  margin: 22px 0 4px; font-family: var(--sans); font-size: 15px;
}
.cta a {
  font-weight: 600; text-decoration: none; color: var(--series-text);
  border-bottom: 1px solid var(--rule); padding-bottom: 3px;
}
.cta a:hover { border-bottom-color: var(--series-text); }
.cta a.lead {
  border: 1px solid var(--series-text); border-radius: 3px; padding: 7px 14px;
  border-bottom-width: 1px;
}
.cta a.lead:hover { background: var(--series-text); color: var(--paper); }
/* The scannable facts a recruiter cannot infer from the work itself: stack,
   programme, availability, work authorisation. Under the contact row because
   that is where someone who has decided to act needs them. */
.credentials {
  margin: 16px 0 0; font-family: var(--sans); font-size: 13px;
  color: var(--ink-3); line-height: 1.6;
}

.stats.hero-strip {
  grid-template-columns: repeat(auto-fit, minmax(178px, 1fr));
  margin: 30px 0 0;
}
/* The thirty-second path, separated from the contact row by a rule so the two
   do not read as one undifferentiated list of links. */
.quickpath {
  display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 18px;
  margin-top: 26px; padding-top: 16px; border-top: 1px solid var(--rule-soft);
  font-family: var(--sans); font-size: 14.5px; color: var(--ink-3);
}
.quickpath span {
  font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase;
  font-size: 13.5px;
}
.quickpath a {
  color: var(--ink-2); text-decoration: none;
  border-bottom: 1px solid var(--rule); padding-bottom: 2px;
}
.quickpath a:hover { border-bottom-color: var(--ink-2); }
@media (max-width: 640px) {
  .cta { font-size: 14.5px; gap: 12px 16px; }
  /* 11px of vertical padding, not 8: the boxed links are the two the page most
     wants tapped, and at 8px they measured 41px tall against the 44px minimum
     target size. Measured, not assumed -- 41px is a thumb missing a link. */
  .cta a.lead { padding: 11px 14px; }
}

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
  font-size: 12px; font-weight: 700; letter-spacing: 0.11em;
  text-transform: uppercase; color: var(--ink-3); margin: 0 0 12px;
}
.toc ol { margin: 0; padding: 0; list-style: none; columns: 2; column-gap: 34px; }
@media (max-width: 700px) { .toc ol { columns: 1; } }
.toc li { margin: 0 0 8px; break-inside: avoid; font-size: 14.5px; line-height: 1.4; }
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
    font-family: var(--sans); font-size: 13px; font-weight: 700;
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
  font-family: var(--sans); font-size: 13.5px; font-weight: 600;
  letter-spacing: 0.02em; color: var(--ink-2);
}
.finding h3 { font-family: var(--serif); font-size: 19px; font-weight: 700;
              text-transform: none; letter-spacing: 0; color: var(--ink);
              margin: 8px 0 0; padding: 0; border: 0; }
.finding .fci {
  font-family: var(--sans); font-size: 13px; color: var(--ink-3);
  font-variant-numeric: tabular-nums; margin: 2px 0 0;
}
.finding .what { margin: 10px 0 0; color: var(--ink-2); font-size: 16px;
                 line-height: 1.5; max-width: 60ch; }
.finding .go { margin: 6px 0 0; font-family: var(--sans);
               font-size: 14px; font-weight: 600; }
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
.vizwrap > div { min-width: 1380px; }
.atlas-links { display: flex; flex-wrap: wrap; gap: 10px 22px; margin: 20px 0;
  font-family: var(--sans); font-size: 15px; }
.atlas-panel { padding-top: 42px; }
.atlas-panel img { display: block; width: 100%; height: auto;
  border: 1px solid var(--rule); background: #fff; }
.atlas-panel figure { margin: 22px 0; }
.atlas-note { border-left: 3px solid var(--series); padding: 12px 20px;
  background: var(--plate); font-family: var(--sans); font-size: 15px; }

/* --- footer -------------------------------------------------------------- */
.pagefoot {
  margin-top: 56px; padding-top: 24px; border-top: 1px solid var(--rule);
  display: flex; justify-content: space-between; gap: 20px; flex-wrap: wrap;
  font-family: var(--sans); font-size: 14px;
}
.pagefoot a { font-weight: 600; }
.pagefoot .byline { color: var(--ink-2); font-weight: 600; }
.pagefoot .footlinks { display: flex; flex-wrap: wrap; gap: 6px 18px; }
/* Reading revision: clear hierarchy, generous space, progressive detail. */
.sitenav-inner { align-items: center; gap: 26px; min-height: 64px; }
.sitenav .brand { letter-spacing: .07em; }
.hero { padding: 70px 0 32px; }
.hero h1 { max-width: 850px; font-size: clamp(36px, 4.5vw, 56px); line-height: 1.09; margin-bottom: 24px; }
.hero .standfirst { max-width: 64ch; font-size: 20px; }
.hero-answer { margin-top: 20px; font-size: 17px; color: var(--ink-2); max-width: 68ch; }
.hero-scope { font-family: var(--sans); font-size: 13px; color: var(--ink-3); margin: 24px 0 0; }
.cta { margin-top: 28px; gap: 16px 26px; }
.cta a.lead { background: var(--series-text); color: var(--paper); padding: 11px 18px; border-radius: 3px; }
.quickpath { margin-top: 30px; }
.findings { background: none; border: 0; gap: 0; margin-top: 16px; }
.finding { background: none; display: grid; grid-template-columns: 32px minmax(0, 1fr); column-gap: 20px;
  padding: 26px 0; border-bottom: 1px solid var(--rule-soft); }
.finding > * { grid-column: 2; }
.finding .finding-index { grid-column: 1; grid-row: 1 / span 4; font-family: var(--sans); font-size: 12px;
  font-weight: 600; color: var(--series-text); padding-top: 5px; }
.finding h3 { margin: 0; font-size: 22px; line-height: 1.3; }
.finding .what { max-width: 65ch; font-size: 17px; margin: 10px 0; }
.finding .fci { max-width: 72ch; font-size: 13px; line-height: 1.6; }
.finding .go { margin-top: 12px; }
.overview-figure figure { margin: 24px 0 0; }
.overview-figure img { display: block; width: 100%; height: auto; border: 1px solid var(--rule-soft); }
.overview-figure figcaption { margin-top: 14px; font-family: var(--sans); font-size: 14px; color: var(--ink-2); max-width: 78ch; }
.limits-grid { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 28px; margin-top: 26px; }
.limit-item { border-top: 2px solid var(--rule); padding-top: 18px; }
.limit-item h3 { font-family: var(--serif); font-size: 19px; text-transform: none; letter-spacing: 0; margin: 0 0 12px; padding: 0; border: 0; }
.limit-item p { font-size: 16px; color: var(--ink-2); }
.limit-item a { font-family: var(--sans); font-size: 13px; }
details.technical-details, details.technical-note, .body-indent > details { border: 1px solid var(--rule-soft); padding: 17px 20px; margin: 24px 0; background: var(--plate); }
summary { cursor: pointer; font-family: var(--sans); font-size: 15px; font-weight: 600; color: var(--ink-2); }
details[open] > summary { margin-bottom: 16px; }
details p:last-child { margin-bottom: 0; }
.reading-note { font-size: 15px; color: var(--ink-2); margin-top: 22px; }
.colophon { border-top: 1px solid var(--rule); margin-top: 64px; padding-top: 36px; }
.reading-layout { display: grid; grid-template-columns: 205px minmax(0,1fr); gap: 36px; align-items: start; }
.reading-layout .toc { position: sticky; top: 84px; max-height: calc(100vh - 108px); overflow-y: auto;
  padding: 18px 0; background: none; border: 0; border-top: 1px solid var(--rule); margin-top: 48px; }
.reading-layout .toc summary { font-size: 13px; }
.toc ol { columns: 1; }
.toc li { font-size: 13px; margin-bottom: 13px; line-height: 1.5; }
.reading-body { min-width: 0; }
.reading-body .body-indent { margin-left: 0; }
.reading-body .sec-num { min-width: 30px; }
.reading-body .stats { grid-template-columns: repeat(auto-fit,minmax(145px,1fr)); }
.reading-body section:first-child { padding-top: 44px; }
.reading-body h2 { font-size: clamp(24px,2.5vw,30px); }
.reading-body .pagefoot { font-size: 12px; }
.chart-guide figure { margin: 24px 0 34px; }
.chart-guide img { display:block; width:100%; height:auto; background:#fff; border:1px solid var(--rule-soft); }
.chart-guide figcaption { font-size:15px; color:var(--ink-2); margin-top:12px; max-width:78ch; }
.archive-note { border-left: 3px solid var(--rule); padding: 14px 18px; color: var(--ink-2); font-size:15px; }
.chart-guide h3 { font-family:var(--serif); font-size:22px; letter-spacing:0; text-transform:none; }
.atlas-archive { margin-top:40px; padding:22px; border:1px solid var(--rule); }
@media (max-width: 850px) {
  .reading-layout { display: block; }
  .reading-layout .toc { position: static; max-height: none; margin-top:24px; padding:16px 18px; background:var(--plate); border:1px solid var(--rule-soft); }
  .toc ol { columns:2; }
}
@media (max-width: 640px) {
  .sitenav-inner { gap:18px; min-height:54px; }
  .sitenav .brand { font-size:11px; }
  .sitenav a { font-size:12px; }
  .sitenav a:last-child { display:none; }
  .hero { padding-top:40px; }
  .desktop-break { display:none; }
  .hero .standfirst { font-size:18px; }
  .hero-answer { font-size:16px; }
  .finding { column-gap:10px; grid-template-columns:24px minmax(0,1fr); }
  .finding h3 { font-size:21px; }
  .limits-grid { grid-template-columns:1fr; gap:20px; }
  .toc ol { columns:1; }
  .pagefoot { font-size:12px; }
  .atlas-archive { padding:16px; }
}
@media print {
  .sitenav, .toplink, .toc, .quickpath, .cta { display:none !important; }
  .reading-layout { display:block; }
}

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
        "c_n":          tenyr["n_evaluable"],
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
    pce = json.loads((ROOT / "reports" / "pce_results.json").read_text(encoding="utf-8"))
    f["pce"] = pce
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
            f"pp per decade; its uncertainty interval includes zero."),
        "pandemic.html": (
            f"Pandemic &mdash; CardioTrace | {AUTHOR}",
            f"A descriptive comparison with the earlier cardiovascular prevalence trend: "
            f"{f['post_cycle']} sits {signed(f['gap'])} pp from the extrapolated "
            f"trend, with a 95% interval that contains zero."),
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
            f"Predictive Modeling &mdash; CardioTrace | {AUTHOR}",
            (f"Is the {f['harrell_c']:.3f} concordance limited by the variable "
             f"set or the model form? A screen of {f['n_candidates']} additional "
             f"candidates against the eleven, and gradient boosting against a "
             f"cause-specific Cox pair on the same held-out cycles."
             if "n_candidates" in f else
             f"Is the {f['harrell_c']:.3f} concordance limited by the variable "
             f"set or by the model form?")),
        "explore.html": (
            f"Tableau dashboards &mdash; CardioTrace | {AUTHOR}",
            "Three Tableau dashboards for population trends, mortality risk and model comparisons, with an editable workbook."),
        "cardiotrace-report.html": (
            f"Full report &mdash; CardioTrace | {AUTHOR}",
            f"The complete CardioTrace write-up in one file: every section, table "
            f"and figure for {num(f['n_adults'])} adults across {f['n_cycles']} "
            f"NHANES cycles and a {num(f['cohort_n'])}-person mortality cohort."),
    }


def author_links() -> str:
    """The page footer: source, and nothing else.

    It used to carry GitHub, Résumé and LinkedIn on every page, which put all
    three on the index a second time -- the first screen already asks. Repeating
    an ask does not strengthen it; it reads as a page that is worried the first
    one was missed. The footer keeps the source link, which is the one thing a
    reader might want from any page rather than from the front one.
    """
    return f'<a href="{REPO_URL}">GitHub</a>'


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
    """A compact native disclosure on mobile, expanded beside desktop reading."""
    items = ANCHORED.findall(html)
    if label == "Contents":
        items = [item for item in items if item[0] == "2"]
    if not items:
        return ""
    links = "".join(f'<li><a href="#{hid}">{plain(txt)}</a></li>' for _, hid, txt in items)
    return (f'<details class="toc" open><summary>{label}</summary>'
            f'<nav aria-label="{label}"><ol>{links}</ol></nav></details>')


def reading_layout(intro: str, section: str, label: str = "On this page") -> str:
    return f'{intro}<div class="reading-layout">{contents(section, label)}<div class="reading-body">{section}</div></div>'


def chapter_links(current: str) -> str:
    chapters = [("index.html", "Overview")] + [(value[0], value[1]) for value in PAGES.values()] + [METHODS[:2]]
    index = next(i for i, (name, _) in enumerate(chapters) if name == current)
    links = []
    if index:
        url, label = chapters[index - 1]
        links.append(f'<a rel="prev" href="{url}">&larr; {label}</a>')
    if index + 1 < len(chapters):
        url, label = chapters[index + 1]
        links.append(f'<a rel="next" href="{url}">{label} &rarr;</a>')
    return "".join(links)


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
<body id="top">
<a class="skip" href="#main">Skip to content</a>
{nav(current)}
<main class="wrap" id="main" tabindex="-1">
{body}
<div class="pagefoot">
  <span>CardioTrace &middot; NHANES 1999&ndash;August 2023 &middot; mortality follow-up through 2019<br>
  <span class="byline">{AUTHOR} &middot; {AUTHOR_PROGRAM}</span></span>
  <span class="footlinks">{prev_next}{author_links()}<a href="#top">Back to top &uarr;</a></span>
</div>
</main>
{TOPLINK}
</body>
</html>
"""


# ── the index ────────────────────────────────────────────────────────────────


def build_hero(f: dict) -> str:
    """Lead with the research question; give author information its own place."""
    return f"""<header class="masthead hero">
  <p class="eyebrow">Population health research &middot; NHANES</p>
  <h1>Understanding cardiovascular<br class="desktop-break"> burden and long-term risk.</h1>
  <p class="standfirst measure">How has cardiovascular disease changed across US surveys?
  Which information helps rank the risk of cardiovascular death years later?</p>
  <p class="hero-answer measure">CardioTrace uses public NHANES data to study population trends
  and long-term mortality risk. In this analysis, adding a kidney marker improved risk ranking.</p>
  <nav class="cta" aria-label="Start reading">
    <a class="lead" href="cardiotrace-report.html">Read the report <span aria-hidden="true">&rarr;</span></a>
    <a href="explore.html">Tableau dashboards</a>
  </nav>
  <p class="hero-scope">{num(f['n_adults'])} adults in the survey analysis &nbsp;&middot;&nbsp;
  {num(f['cohort_n'])} in the separate mortality cohort &nbsp;&middot;&nbsp;
  Mortality follow-up ends in 2019</p>
  <nav class="quickpath" aria-label="Overview contents">
    <a href="#findings">Findings</a><a href="#limits">Limits</a>
    <a href="#built">How it was built</a><a href="#author">Author</a>
  </nav>
</header>"""


def build_colophon() -> str:
    """Keep personal details together, outside the research narrative."""
    links = [(RESUME_URL, "Resume (PDF)"),
             (f"mailto:{EMAIL}" if EMAIL else "", "Email"), (LINKEDIN_URL, "LinkedIn")]
    contacts = "".join(f'<a href="{attr(url)}">{label}</a>' for url, label in links if url)
    return f"""<section class="colophon" id="author" aria-labelledby="colophon-h">
  <div class="sec-head"><div class="sec-num">AUTHOR</div>
  <h2 id="colophon-h">About {AUTHOR}</h2></div>
  <div class="body-indent">
    <p class="colophon-affil">{AUTHOR_PROGRAM}</p>
    <p class="colophon-stmt measure">{AUTHOR_STATEMENT}</p>
    <p class="measure">My work here includes tracing data problems across survey cycles,
    documenting analytical decisions, and turning results into a reproducible report.</p>
    <nav class="colophon-links" aria-label="About the author">{contacts}</nav>
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
        ("Survey cycles", num(f["n_cycles"]), "NHANES 1999&ndash;August 2023, harmonised"),
        ("Public-use files catalogued", num(f["n_files"]),
         "each recorded with the rule that kept or dropped it"),
        (f"Adults {f['age_floor']}+ analysed", num(f["n_adults"]),
         "survey-weighted, design-based intervals"),
    ]
    if "n_tests" in f:
        tiles.append(("Automated tests", num(f["n_tests"]),
                      "collected tests; suite successful, conditional skips included"))
    if "followup_years" in f:
        tiles.append(("Mortality follow-up", f"{f['followup_years']} yr",
                      "record linkage to the National Death Index"))
    cells = "".join(f'<div class="stat"><div class="k">{k}</div>'
                    f'<div class="v">{v}</div><div class="n">{n}</div></div>'
                    for k, v, n in tiles)
    return f"""<section class="evidence" id="built" aria-labelledby="evidence-h">
  <div class="sec-head"><div class="sec-num">BUILT</div>
  <h2 id="evidence-h">What it took to answer them</h2></div>
  <div class="body-indent">
    <div class="stats evidence-strip">{cells}</div>
  </div>
</section>"""


def build_findings(f: dict) -> str:
    """A conclusion first; its estimate and limits immediately underneath."""
    cards = [
        ("01", "burden.html", "The age-standardised trend remains uncertain.",
         "The overall and age-standardised series tell different stories. The pre-pandemic "
         "trend estimate is slightly downward, but its interval also allows no change.",
         f"{signed_html(f['std_slope'])} percentage points per decade; 95% CI "
         f"{signed_html(f['std_slope_ci'][0])} to {signed_html(f['std_slope_ci'][1])}.", "Population burden"),
        ("02", "pandemic.html", "The pandemic's impact remains unclear.",
         "The available data are insufficient to assess the pandemic's impact on cardiovascular disease. "
         "The later survey estimate is above the earlier trend, but the interval includes no difference.",
         f"Observed minus extrapolated: {signed_html(f['gap'])} percentage points; "
         f"95% CI {signed_html(f['gap_ci'][0])} to {signed_html(f['gap_ci'][1])}.", "The later survey"),
    ]
    if "delta_c_wide" in f:
        cards.append(("03", "learning.html", "Adding UACR helped in this model comparison.",
                      "Urine albumin-to-creatinine ratio, a kidney marker, added useful ranking "
                      "information. Gradient boosting on the existing inputs did not improve the tested model.",
                      f"Change in weighted C: {f['delta_c_wide']:+.4f} "
                      f"(95% CI {f['delta_c_wide_lo']:+.4f} to "
                      f"{f['delta_c_wide_hi']:+.4f}); evaluated on the same Part 4 sample.",
                      "Variables and models"))
    return "".join(
        f'<article class="finding"><span class="finding-index">{number}</span>'
        f'<h3>{title}</h3><p class="what">{what}</p><p class="fci">{estimate}</p>'
        f'<p class="go"><a href="{href}">{label} &rarr;</a></p></article>'
        for number, href, title, what, estimate, label in cards)


def build_limits(f: dict) -> str:
    """Short, visible boundaries on the conclusions above."""
    items = [
        ("Pandemic effects", "The available data are insufficient to assess the pandemic's "
         "impact on cardiovascular disease. Mortality follow-up ends in 2019.", "pandemic.html"),
        ("Death versus illness", "Non-fatal heart attacks and strokes are not outcomes in the linked "
         "mortality data. These predictions do not describe all cardiovascular illness.", "cohort.html"),
        ("Use beyond this sample", "Missing inputs can select who enters an analysis. Tests on later "
         "NHANES cycles do not establish clinical usefulness in other populations.", "methods.html"),
    ]
    cells = "".join(f'<div class="limit-item"><h3>{title}</h3><p>{text}</p>'
                    f'<a href="{href}">Read the limitation &rarr;</a></div>'
                    for title, text, href in items)
    return f"""<section id="limits" aria-labelledby="limits-h">
  <div class="sec-head"><div class="sec-num">LIMITS</div>
  <h2 id="limits-h">Limitations</h2></div>
  <div class="body-indent"><div class="limits-grid">{cells}</div></div>
</section>"""


def build_index(style: str, sections: dict[str, str], f: dict, meta: dict) -> str:
    title, desc = meta["index.html"]
    with Image.open(DOCS / "tableau/current/01-population-burden.png") as dashboard:
        dashboard_width, dashboard_height = dashboard.size
    body = f"""{build_hero(f)}
<section id="findings" aria-labelledby="findings-h">
  <div class="sec-head"><div class="sec-num">FINDINGS</div><h2 id="findings-h">Key findings</h2></div>
  <div class="body-indent"><div class="findings">{build_findings(f)}</div></div>
</section>
<section class="overview-figure" aria-labelledby="overview-figure-h">
  <div class="sec-head"><div class="sec-num">IN VIEW</div><h2 id="overview-figure-h">Population trends</h2></div>
  <div class="body-indent"><figure>
    <a href="explore.html#population"><img src="tableau/current/01-population-burden.png"
      width="{dashboard_width}" height="{dashboard_height}" loading="lazy" alt="Tableau dashboard combining cardiovascular prevalence trends, race and ethnicity estimates, and age patterns."></a>
    <figcaption>The pre-pandemic age-standardised trend is {signed_html(f['std_slope'])} percentage points per decade
    (95% CI {signed_html(f['std_slope_ci'][0])} to {signed_html(f['std_slope_ci'][1])}).
    <a href="explore.html#population">Open the Tableau dashboard &rarr;</a></figcaption>
  </figure></div>
</section>
{build_limits(f)}
<section id="built" aria-labelledby="built-h">
  <div class="sec-head"><div class="sec-num">PROCESS</div><h2 id="built-h">Data and methods</h2></div>
  <div class="body-indent"><p class="measure">Public survey files become a documented cohort,
  analysis tables, and this report. File inventories, variable mappings, and regression checks
  help catch the data losses found in earlier versions.</p>
  <details class="technical-details"><summary>Data, tools and reproducibility</summary>
    <p>The active analysis uses Python to read NHANES files, fit the models and generate the report.
    PostgreSQL and dbt remain an optional warehouse path. Independent R checks cover the original survey estimators.</p>
    <p>{num(f['n_files'])} files catalogued across {f['n_cycles']} survey cycles.
    <a href="methods.html">Methods and source records</a> &middot;
    <a href="{REPO_URL}">Code and reproducibility instructions</a></p>
  </details>
  <p class="reading-note">Prefer one continuous read? The <a href="cardiotrace-report.html">complete HTML report</a>
  includes every chapter and embeds its figures for offline reading.</p></div>
</section>
{build_colophon()}"""
    return page(title, desc, "", style, "index.html", body)


def atlas_report_link(filename: str) -> str:
    for anchor, _, title, _, links in PANELS:
        if filename in [link[0] for link in links]:
            return (f'<p class="atlas-note"><a href="explore.html#{anchor}">'
                    f'See the {title.lower()} charts &rarr;</a></p>')
    return ""


def build_explore(style: str, f: dict, meta: dict) -> str:
    """Three visible Tableau dashboards, with individual charts as supplements."""
    validate_atlas()
    audit = validate_snapshot()
    title, desc = meta["explore.html"]
    # Copy current generated figures explicitly, including ones absent from a chapter.
    figures = ["part1_standardisation.png", "part1_by_race.png", "cif_by_sbp.png",
               "calibration.png", "part4_arms.png"]
    for name in figures:
        (ASSETS / name).write_bytes((ROOT / "reports/figures" / name).read_bytes())
    def figure(name: str, alt: str, caption: str) -> str:
        return (f'<figure><a href="assets/{name}" aria-label="Open full-size chart: {attr(alt)}">'
                f'<img src="assets/{name}" loading="lazy" alt="{attr(alt)}"></a>'
                f'<figcaption>{caption}</figcaption></figure>')
    population = figure("part1_standardisation.png", "Crude and age-standardised cardiovascular prevalence over survey cycles",
        f"Pre-pandemic age-standardised trend: {signed_html(f['std_slope'])} percentage points per decade "
        f"(95% CI {signed_html(f['std_slope_ci'][0])} to {signed_html(f['std_slope_ci'][1])}). "
        "The interval includes zero. Standardisation changes the comparison; it does not establish what caused the change.")
    population += figure("part1_by_race.png", "Cardiovascular prevalence estimates by race and ethnicity",
        "Intervals describe uncertainty around group estimates. Lines guide reading across surveys; "
        "they do not fit a trend across the post-pandemic survey redesign. These are descriptive comparisons, not effects of group membership.")
    mortality = figure("cif_by_sbp.png", "Cardiovascular death incidence across baseline blood-pressure groups",
        "These curves describe observed cardiovascular deaths while accounting for competing deaths. "
        "Groups can differ in age and other characteristics; the plot does not estimate the effect of a blood-pressure intervention.")
    mortality += figure("calibration.png", "Predicted and observed cardiovascular mortality by risk group at five and ten years",
        "Calibration asks whether predicted risk agrees with observed risk. Observed risk uses weighted Aalen–Johansen estimates, "
        "accounting for early censoring and competing deaths. Intervals are not shown; group-level agreement alone is incomplete validation.")
    models = figure("part4_arms.png", "Paired changes in risk ranking for candidate inputs and model forms",
        "The Part 4 comparison holds the evaluation sample constant. Adding UACR improved the tested Cox model; "
        "the tested gradient boosting model did not. Intervals are conditional on the fitted training models.")
    dashboards = {}
    for anchor, image, panel_title, description, _ in PANELS:
        with Image.open(DOCS / "tableau/current" / image) as dashboard:
            width, height = dashboard.size
        dashboards[anchor] = (
            f'<figure class="tableau-dashboard"><a href="tableau/current/{image}" '
            f'aria-label="Open full-size Tableau dashboard: {attr(panel_title)}">'
            f'<img src="tableau/current/{image}" loading="lazy" width="{width}" height="{height}" '
            f'alt="Tableau dashboard: {attr(description)}"></a>'
            f'<figcaption><a href="tableau/current/{image}">Full-size dashboard</a> &middot; '
            f'<a href="tableau/current/{WORKBOOK}" download>Download workbook</a></figcaption></figure>')
    historical = []
    for anchor, image, panel_title, description, links in PANELS:
        historical.append(f'<figure id="historical-{anchor}"><img src="tableau/{image}" loading="lazy" '
                          f'width="2760" height="1880" alt="Historical Tableau snapshot: {attr(description)}">'
                          f'<figcaption>{panel_title}, reviewed 6 September 2026. '
                          f'<a href="tableau/{image}">Full-size historical PNG</a></figcaption></figure>')
    embed = ""
    if TABLEAU_VIZ:
        embed = (f'<p><a href="https://public.tableau.com/views/{attr(TABLEAU_VIZ)}">'
                 'Open the published Tableau view</a> (check its revision date before using its results).</p>')
    body = f"""<header class="masthead">
  <p class="eyebrow">CardioTrace &middot; Tableau</p><h1>Research dashboards</h1>
  <p class="standfirst measure">Three dashboards bring the related charts together.
  View them below, or open the workbook in Tableau to explore the data.</p>
  <p><a href="tableau/current/{WORKBOOK}" download>Download Tableau workbook (.twbx)</a></p>
  <nav class="atlas-links" aria-label="Chart groups"><a href="#population">Population burden</a>
  <a href="#mortality">Mortality risk</a><a href="#models">Model comparison</a></nav>
</header>
<section id="population" class="chart-guide atlas-panel" aria-labelledby="population-title">
  <h2 id="population-title">Population burden</h2><p class="lede measure">The overall prevalence and the age-standardised estimate describe different aspects of the same population.</p>
  {dashboards['population']}
  <p class="measure">The available data are insufficient to assess the pandemic's impact on cardiovascular disease.</p>
  <details class="technical-details"><summary>Individual charts</summary>{population}</details>
  <nav class="atlas-links" aria-label="Population methods"><a href="burden.html">Trends and survey design &rarr;</a>
  <a href="pandemic.html">Pandemic comparison &rarr;</a><a href="#mortality">Next: mortality risk &darr;</a></nav>
</section>
<section id="mortality" class="chart-guide atlas-panel" aria-labelledby="mortality-title">
  <h2 id="mortality-title">Mortality risk</h2><p class="lede measure">Risk ranking and risk calibration answer different questions.</p>
  <p class="measure">Weighted C = {f['harrell_c']:.3f} at {f['c_horizon']} years on {num(f['c_n'])} participants with complete inputs in later cycles.
  C measures ordering among comparable pairs; it is not the percentage of people whose outcome was predicted correctly.</p>
  {dashboards['mortality']}
  <details class="technical-details"><summary>Individual charts and calibration</summary>{mortality}</details>
  <nav class="atlas-links" aria-label="Mortality methods"><a href="cohort.html">Cohort and calibration &rarr;</a>
  <a href="#population">Previous: population burden &uarr;</a><a href="#models">Next: model comparison &darr;</a></nav>
</section>
<section id="models" class="chart-guide atlas-panel" aria-labelledby="models-title">
  <h2 id="models-title">Model comparison</h2><p class="lede measure">Compare model inputs, risk scores and ranking performance.</p>
  {dashboards['models']}
  <details class="technical-details"><summary>Individual chart and comparison details</summary>{models}
  <p class="measure">The paired PCE intervals include zero at both horizons.
  PCE targets hard ASCVD, including non-fatal events; this study records cardiovascular deaths.</p></details>
  <nav class="atlas-links" aria-label="Model methods"><a href="learning.html">Variables and models &rarr;</a>
  <a href="methods.html">PCE comparison &rarr;</a><a href="#mortality">Previous: mortality risk &uarr;</a></nav>
</section>
<details class="atlas-archive" id="tableau-history"><summary>Historical Tableau workbook &middot; 6 September 2026</summary>
  <p class="archive-note">This reviewed workbook is preserved as a historical snapshot. Its calibration views predate the early-censoring correction
  used in the current charts above. Use the current report for current results.</p>
  <p><a href="tableau/{WORKBOOK}" download>Download the historical Tableau workbook (.twbx)</a> &middot;
  <a href="tableau/README.md">Snapshot notes</a></p>{embed}
  <p class="measure">The workbook includes aggregate data and editable worksheets; open it in Tableau for editing and hover details.
  Its original source files, workbook and previews remain hash-verified against research version
  <a href="{REPO_URL}/tree/{audit['source_commit']}">{audit['source_commit'][:7]}</a>.</p>
  {''.join(historical)}
</details>
<p class="reading-note"><a href="cardiotrace-report.html">Read the complete report &rarr;</a></p>"""
    return page(title, desc, "explore.html", style, "explore.html", body,
                '<a href="index.html">&larr; Overview</a>')


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
         '<body id="top">\n<a class="skip" href="#main">Skip to content</a>\n'
         + nav('cardiotrace-report.html') + '\n<main class="wrap report-wrap" id="main" tabindex="-1">', "skip link and landmark")
    once("</div>\n</body>", f"</main>\n{TOPLINK}\n</body>", "closing landmark")

    raw = scrollable_tables(anchor_headings(raw, seen))
    once("</header>", "</header>\n<div class=\"reading-layout\">" + contents(raw, "Contents") + '<div class="reading-body">', "contents block")
    once("</main>", "</div></div></main>", "reading layout end")
    return raw


def main() -> None:
    validate_atlas()
    html = read_report()
    style = extract_style(html)
    sections = split_sections(html)
    f = facts()
    meta = titles_and_descriptions(f)

    DOCS.mkdir(exist_ok=True)
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    share_card()

    written = []

    body = build_index(style, sections, f, meta)
    (DOCS / "index.html").write_text(externalise_images(body), encoding="utf-8")
    written.append("index.html")

    order = [PAGES[k][0] for k in ("2", "3", "4", "5")] + [METHODS[0]]
    for i, key in enumerate(("2", "3", "4", "5")):
        fname, label, stand = PAGES[key]
        title, desc = meta[fname]
        seen: set[str] = set()
        sec = scrollable_tables(anchor_headings(sections[key], seen))
        sec = sec.replace('href="#analysis-assumptions"', 'href="methods.html#analysis-assumptions"')
        body = page(title, desc, fname, style, fname,
                    reading_layout(f'<header class="masthead"><p class="eyebrow">CardioTrace</p>'
                    f'<h1>{label}</h1><p class="standfirst measure">{stand}</p></header>'
                    f'{atlas_report_link(fname)}', sec), prev_next=chapter_links(fname))
        (DOCS / fname).write_text(externalise_images(body), encoding="utf-8")
        written.append(fname)

    fname, label, stand = METHODS
    title, desc = meta[fname]
    seen = set()
    sec = scrollable_tables(anchor_headings(sections["6"] + sections["7"], seen))
    body = page(title, desc, fname, style, fname,
                reading_layout(f'<header class="masthead"><p class="eyebrow">CardioTrace</p>'
                f'<h1>{label}</h1><p class="standfirst measure">{stand}</p></header>'
                f'{atlas_report_link(fname)}', sec), prev_next=chapter_links(fname))
    (DOCS / fname).write_text(externalise_images(body), encoding="utf-8")
    written.append(fname)

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
        print("  Tableau: reviewed previews and workbook download published; "
              "no Tableau Public embed configured.")
    for m in f["missing"]:
        print(f"  NOTE: evidence tile omitted -- {m}")


if __name__ == "__main__":
    main()
