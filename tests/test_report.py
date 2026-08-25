"""Regressions for the report renderer and the site split.

Both of these shipped. `decision()` takes plain strings, so a `{...}` written
inside one is never interpolated by the surrounding f-string and reaches the
published page verbatim: the live Pandemic page showed `{p1['dispersion']:.2f}`
and `{cp['crit95']:.1f}` where two numbers should have been. Nothing else
catches it -- the renderer succeeds, the HTML is valid, and the defect is
invisible to every test that checks the analysis rather than the page.

The rendered check is deliberately absolute: outside `<style>` and `<script>`
the report body contains no braces at all, so any `{...}` there is an
un-interpolated expression. If prose ever genuinely needs a brace, write it as
`&#123;` / `&#125;` rather than loosening the pattern -- a looser pattern is how
a leak of a shape nobody anticipated gets through next time.

The source check is the same defect one step earlier and reports a line number.
It skips the stylesheet constants by assignment target, because those are the
only plain strings in this project that legitimately contain braces.
"""

import ast
import re

import pandas as pd
from pathlib import Path

import pytest

from scripts import render_report

ROOT = Path(__file__).parent.parent

# A brace pair with something inside it. Bounded, so a stray `{` in one place
# and a stray `}` far away cannot span half the document and report a match
# that is really two unrelated characters.
INTERPOLATION = re.compile(r"\{[^{}]{1,200}\}")

PUBLISHED = sorted(p.relative_to(ROOT) for p in
                   [*(ROOT / "docs").glob("*.html"),
                    ROOT / "reports" / "cardiotrace-report.html"])


def prose_only(html: str) -> str:
    """Everything a reader sees, with the stylesheet and any script removed.

    Stripping by tag is exact. A brace-content heuristic would have to guess
    which braces are CSS, and guessing is what makes a check like this either
    noisy enough to be deleted or lax enough to miss the next leak.
    """
    html = re.sub(r"<style\b[^>]*>.*?</style>", "", html, flags=re.S | re.I)
    return re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.S | re.I)


def test_the_stylesheet_is_why_the_check_strips_style_first():
    """Pins the reason `prose_only` exists, so nobody removes it as ceremony.

    The stylesheet carries dozens of brace pairs. A check run over the whole
    file would drown in them, which is exactly why the two real leaks survived
    on the live site for as long as they did.
    """
    html = render_report.build()
    assert len(INTERPOLATION.findall(html)) > 40
    assert "--paper:" in html and "--paper:" not in prose_only(html)


def test_no_python_expression_survives_into_the_rendered_report():
    """A `{...}` in the body means an f-string prefix was forgotten upstream."""
    leaked = INTERPOLATION.findall(prose_only(render_report.build()))
    assert leaked == [], f"unsubstituted expressions in the report: {leaked}"


@pytest.mark.parametrize("rel", PUBLISHED, ids=str)
def test_no_python_expression_survives_into_the_published_pages(rel):
    """The pages on disk are what GitHub Pages serves.

    Rendering cleanly is not enough. `docs/` is only refreshed when someone runs
    `build_site.py`, so a fixed renderer and a stale site still ship the bug to
    readers. Failing here until the pipeline has been rerun is the point.
    """
    leaked = INTERPOLATION.findall(prose_only((ROOT / rel).read_text(encoding="utf-8")))
    assert leaked == [], f"{rel} carries unsubstituted expressions: {leaked}"


# A cell whose entire content is the literal "nan". Anchored on the tags so it
# cannot match the letters inside an ordinary word.
NAN_CELL = re.compile(r">\s*nan\s*<", re.I)


@pytest.mark.parametrize("rel", PUBLISHED, ids=str)
def test_no_missing_value_is_published_as_the_word_nan(rel):
    """The sibling of the brace check, and the leak it did not cover.

    An f-string renders float('nan') as the literal text "nan". Nine cells of
    the candidate table published it in the column headed "Into the forward
    path?" -- including the row for eGFR, which is the variable the PREVENT
    comparison turns on. The cause was two steps apart: an empty string written
    to CSV comes back from pandas as float('nan'), and float('nan') is TRUTHY,
    so the renderer's `value or fallback` never fired.

    Both ends are fixed -- every state has a name in the data, and the renderer
    tests for absence with pd.isna rather than falsiness -- but the failure was
    invisible to every existing test, which is why this one exists.
    """
    found = NAN_CELL.findall(prose_only((ROOT / rel).read_text(encoding="utf-8")))
    assert found == [], (
        f"{rel} publishes {len(found)} missing value(s) as the word 'nan'")


def stylesheet_constants(tree: ast.Module) -> set[int]:
    """Ids of the constants that legitimately carry braces.

    Two kinds: anything assigned to a `*CSS` name, and the inline `*_SVG` icon,
    whose `<style>` element is a stylesheet living inside a string. Excluded by
    assignment target rather than by pattern, so the exemption is a decision
    someone made about one named constant and not a hole a future brace can
    slip through.
    """
    return {id(node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            for t in node.targets
            if isinstance(t, ast.Name)
            and (t.id.endswith("CSS") or t.id.endswith("_SVG"))}


@pytest.mark.parametrize("name", ["render_report.py", "build_site.py"])
def test_no_plain_string_in_the_generators_carries_a_format_field(name):
    """Catch the missing `f` at its source, with a line number.

    An f-string's literal segments never hold a bare brace -- the parser has
    already consumed them -- so every `ast.Constant` still carrying `{...}` is
    either a stylesheet or a string that was meant to be interpolated and is
    not. `decision()`, `stat()` and `ledger()` all take strings, and a plain one
    handed to any of them reaches the page unchanged.
    """
    tree = ast.parse((ROOT / "scripts" / name).read_text(encoding="utf-8"))
    skip = stylesheet_constants(tree)
    bad = [(n.lineno, n.value[:80]) for n in ast.walk(tree)
           if isinstance(n, ast.Constant) and isinstance(n.value, str)
           and id(n) not in skip and INTERPOLATION.search(n.value)]
    assert bad == [], f"{name}: plain strings carrying format fields at {bad}"


# ── nothing on the page asserts a quantity the model did not produce ─────────

def _published_pages():
    root = Path(__file__).parent.parent
    pages = sorted((root / "docs").glob("*.html"))
    report = root / "reports" / "cardiotrace-report.html"
    if report.exists():
        pages.append(report)
    return pages


def _visible(path):
    """Page text with CSS and embedded images removed.

    Base64 image payloads are megabytes of arbitrary characters and will match
    almost any pattern, so a scan that leaves them in reports noise.
    """
    h = path.read_text(encoding="utf-8")
    h = re.sub(r"<style>.*?</style>", "", h, flags=re.S)
    return re.sub(r'data:image/[^"]*', "", h)


def test_no_published_p_value_is_exactly_zero():
    """`fit_aetiologic` rounds p to four decimals, so anything below 5e-5
    becomes 0.0 -- and the Cox table was rendered from the CSV verbatim, so six
    of its nine rows published a p-value of zero.

    A zero probability is not a value any model returns, and unlike a NaN it
    reads as a result rather than as an absence. The rounding is deliberate, so
    the fix is at the point of display.
    """
    offenders = {p.name: n for p in _published_pages()
                 if (n := len(re.findall(r"<td>0\.0+</td>", _visible(p))))}
    assert not offenders, f"p-value of exactly zero on: {offenders}"


def test_no_published_cell_carries_more_precision_than_it_earned():
    """The log columns are left unrounded on purpose -- that was the fix for
    the hazard-ratio scaling bug -- so dumping the CSV printed
    0.011474575653970712 beside hazard ratios given to four decimals."""
    offenders = {p.name: n for p in _published_pages()
                 if (n := len(re.findall(r">\s*-?\d\.\d{10,}", _visible(p))))}
    assert not offenders, f"over-precise cells on: {offenders}"


def test_the_p_value_formatter_states_a_bound_rather_than_a_zero():
    import importlib.util

    root = Path(__file__).parent.parent
    src = (root / "scripts" / "render_report.py").read_text(encoding="utf-8")
    ns = {"pd": pd}
    start = src.index("def _pval")
    exec(src[start:src.index("\n\n\n", start)], ns)
    pval = ns["_pval"]

    assert pval(0.0) == "&lt;0.0001"
    assert pval(1e-9) == "&lt;0.0001"
    assert pval(0.0005) == "0.0005"
    assert pval(0.1058) == "0.1058"
    assert pval(float("nan")) == "&mdash;"
    assert importlib.util  # the import is the documentation of why exec is used
