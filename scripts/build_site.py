"""Split the single-file report into the pages served at GitHub Pages.

The site is not a second write-up. It is the same report, cut along its own
section boundaries and given navigation, so the two cannot say different things:
every page here is produced from `reports/cardiotrace-report.html`, which is
itself produced from the analysis artefacts. Editing prose means editing
`render_report.py`; this file only decides what goes on which page.

Figures become ordinary files under `docs/assets/` rather than inline data URIs.
The single-file report keeps them embedded, because that version exists to be
emailed and has to survive with no server behind it.
"""

from __future__ import annotations

import base64
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

ROOT = Path(__file__).parent.parent
REPORT = ROOT / "reports" / "cardiotrace-report.html"
DOCS = ROOT / "docs"
ASSETS = DOCS / "assets"

REPO_URL = "https://github.com/UTSGJohnsonSong/cardiotrace"

# Section number in the report -> (filename, nav label, short standfirst).
PAGES = {
    "2": ("burden.html", "Burden",
          "How the burden of cardiovascular disease moved across 25 years, once "
          "the ageing of the population is taken out of it."),
    "3": ("pandemic.html", "Pandemic",
          "Whether the pandemic bent the trend, and what a single post-pandemic "
          "observation can and cannot establish."),
    "4": ("cohort.html", "Cohort",
          "A prospective cohort of adults free of cardiovascular disease at "
          "baseline, followed for up to twenty years."),
}
METHODS = ("methods.html", "Methods",
           "The comparison against the clinical standard, the data sources, and "
           "what was done to them.")
NAV = [("index.html", "Overview"), ("burden.html", "Burden"),
       ("pandemic.html", "Pandemic"), ("cohort.html", "Cohort"),
       ("methods.html", "Methods")]

EXTRA_CSS = """
/* ── site chrome: the only styling the single-file report does not need ── */
.sitenav {
  position: sticky; top: 0; z-index: 10;
  background: color-mix(in srgb, var(--paper) 92%, transparent);
  backdrop-filter: saturate(1.2) blur(8px);
  border-bottom: 1px solid var(--rule-soft);
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
@media (max-width: 520px) { .sitenav-inner { padding: 0 18px; gap: 16px; } }

/* Index: the three analyses, each with what it actually found. */
.findings { display: grid; gap: 1px; background: var(--rule-soft);
            border: 1px solid var(--rule-soft); margin: 32px 0 8px; }
.finding { background: var(--plate); padding: 22px 24px;
           display: grid; grid-template-columns: 1fr auto; gap: 6px 24px;
           align-items: start; }
.finding h3 { font-family: var(--serif); font-size: 19px; font-weight: 700;
              text-transform: none; letter-spacing: 0; color: var(--ink);
              margin: 0; padding: 0; border: 0; grid-column: 1; }
.finding .what { grid-column: 1; margin: 0; color: var(--ink-2); font-size: 16px;
                 line-height: 1.5; max-width: 60ch; }
.finding .go { grid-column: 1; margin-top: 6px; font-family: var(--sans);
               font-size: 13px; font-weight: 600; }
.finding .chip { grid-column: 2; grid-row: 1; }
@media (max-width: 640px) {
  .finding { grid-template-columns: 1fr; }
  .finding .chip { grid-column: 1; grid-row: auto; justify-self: start; }
}

.pagefoot {
  margin-top: 56px; padding-top: 24px; border-top: 1px solid var(--rule);
  display: flex; justify-content: space-between; gap: 20px; flex-wrap: wrap;
  font-family: var(--sans); font-size: 13px;
}
.pagefoot a { font-weight: 600; }
"""


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
        num = re.search(r"<div class=\"sec-num\">(.*?)</div>", block, re.S)
        key = re.sub(r"&nbsp;|\s+", "", num.group(1)) if num else "?"
        out[key] = block
    return out


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


def nav(current: str) -> str:
    mark = ' aria-current="page"'
    links = "".join(
        '<a href="{}"{}>{}</a>'.format(href, mark if href == current else "", label)
        for href, label in NAV)
    return (f'<nav class="sitenav"><div class="sitenav-inner">'
            f'<a class="brand" href="index.html">CardioTrace</a>{links}'
            f'</div></nav>')


def page(title: str, style: str, current: str, body: str,
         prev_next: str = "") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{style}{EXTRA_CSS}</style>
</head>
<body>
{nav(current)}
<div class="wrap">
{body}
<div class="pagefoot">
  <span>CardioTrace &middot; NHANES 1999&ndash;2022 &middot; NCHS Linked Mortality File</span>
  <span>{prev_next}<a href="{REPO_URL}">Source on GitHub</a></span>
</div>
</div>
</body>
</html>
"""


def build_index(style: str, masthead: str, sections: dict[str, str]) -> str:
    """Overview: the masthead, why the three designs differ, and where to go."""
    findings = [
        ("burden.html", "The 25-year burden", "chip result",
         "Crude prevalence rose while the age-standardised series fell. The rise "
         "is the population ageing, not the disease spreading."),
        ("pandemic.html", "The pandemic", "chip quiet",
         "The observed 2021&ndash;2022 level sits above the pre-pandemic trend, "
         "but the interval contains zero. One post-pandemic cycle cannot settle it."),
        ("cohort.html", "Who dies of it", "chip result",
         "Blood pressure at examination predicts cardiovascular death up to twenty "
         "years later, validated forward in time rather than at random."),
    ]
    cards = "".join(
        f'<div class="finding"><h3>{name}</h3><span class="{cls}">'
        f'{"Result" if "result" in cls else "No detectable change"}</span>'
        f'<p class="what">{what}</p>'
        f'<div class="go"><a href="{href}">Read this part &rarr;</a></div></div>'
        for href, name, cls, what in findings)

    return page(
        "CardioTrace", style, "index.html",
        f"""{masthead}

<section>
  <div class="sec-head"><div class="sec-num">THE&nbsp;THREE</div>
  <h2>What each part asks, and what it found</h2></div>
  <div class="body-indent">
    <div class="findings">{cards}</div>
    <p class="measure" style="margin-top:26px">The full write-up is also available
    as <a href="cardiotrace-report.html">a single page</a>, which carries every
    section, table and figure in one file.</p>
  </div>
</section>

{sections["1"]}""")


def main() -> None:
    html = read_report()
    style = extract_style(html)
    masthead = extract_masthead(html)
    sections = split_sections(html)

    DOCS.mkdir(exist_ok=True)
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")

    written = []

    body = build_index(style, masthead, sections)
    (DOCS / "index.html").write_text(externalise_images(body), encoding="utf-8")
    written.append("index.html")

    order = [PAGES[k][0] for k in ("2", "3", "4")] + [METHODS[0]]
    for i, key in enumerate(("2", "3", "4")):
        fname, label, stand = PAGES[key]
        nxt = order[i + 1]
        body = page(f"CardioTrace &middot; {label}", style, fname,
                    f'<header class="masthead"><p class="eyebrow">CardioTrace</p>'
                    f'<h1>{label}</h1><p class="standfirst measure">{stand}</p></header>'
                    f'{sections[key]}',
                    prev_next=f'<a href="{nxt}">Next &rarr;</a> &nbsp;&middot;&nbsp; ')
        (DOCS / fname).write_text(externalise_images(body), encoding="utf-8")
        written.append(fname)

    fname, label, stand = METHODS
    body = page(f"CardioTrace &middot; {label}", style, fname,
                f'<header class="masthead"><p class="eyebrow">CardioTrace</p>'
                f'<h1>{label}</h1><p class="standfirst measure">{stand}</p></header>'
                f'{sections["5"]}{sections["6"]}')
    (DOCS / fname).write_text(externalise_images(body), encoding="utf-8")
    written.append(fname)

    shutil.copyfile(REPORT, DOCS / "cardiotrace-report.html")
    written.append("cardiotrace-report.html (single file)")

    for name in written:
        path = DOCS / name.split(" ")[0]
        print(f"  {name:<38s} {path.stat().st_size / 1024:6.0f} KB")
    print(f"  assets/  {len(list(ASSETS.glob('*.png')))} figures")


if __name__ == "__main__":
    main()
