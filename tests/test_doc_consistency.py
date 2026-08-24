"""
The documents have to agree with the artefacts, and a test has to say so.

docs/consistency-audit.md found 36 places where they did not. Most were one of
two kinds, and each kind has a mechanism here rather than a correction:

  STATUS DRIFT   Two status systems lived in research-design.md -- a roadmap
                 column and a decision log -- and only one was maintained, so
                 six nodes read one way at the top of the file and another way
                 at the bottom. There is one system now, and these tests fail if
                 a second one grows back.

  NUMBER DRIFT   Cohort counts were hand-copied into prose and then the cohort
                 changed. The numbers below are read from the artefacts and
                 required to appear in the documents that claim them.

A test that only checked the current values would pass again the moment someone
pasted a stale number somewhere new, so several of these assert the SHAPE of the
document -- no status column, no status emoji in a heading, no bare cycle key on
a published page -- which is the thing that actually recurs.
"""

import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).parent.parent
DOCS = ROOT / "docs"
DESIGN = DOCS / "research-design.md"
STATUS_EMOJI = "\U0001f512\U0001f504⬜✅"
CYCLE_KEY = "2021-2022"


@pytest.fixture(scope="module")
def design() -> str:
    return DESIGN.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def strobe() -> pd.DataFrame:
    return pd.read_csv(ROOT / "reports" / "tables" / "strobe_part3.csv")


@pytest.fixture(scope="module")
def cascade() -> pd.DataFrame:
    return pd.read_csv(ROOT / "reports" / "tables" / "pce_cascade.csv")


# -- one status system --------------------------------------------------------

def test_only_the_status_table_carries_status(design):
    """The roadmap must not grow its status column back.

    It had one, it went stale on 2026-08-09, and the file then answered "what
    state is node 12 in?" two different ways depending on where you read.
    """
    roadmap = design[design.index("## 路线图"):design.index("## 节点 1")]
    for line in roadmap.splitlines():
        if line.startswith("|"):
            assert not any(e in line for e in STATUS_EMOJI), (
                f"the roadmap carries a status marker again: {line!r}")


def test_no_section_heading_carries_its_own_status(design):
    """A heading marked with a status is a third status system, and it drifted
    too: three headings said locked while the roadmap said not started."""
    for line in design.splitlines():
        if line.startswith("## ") or line.startswith("### "):
            assert not any(e in line for e in STATUS_EMOJI), (
                f"heading carries a status marker: {line!r}")


def test_every_node_has_exactly_one_row_in_the_status_table(design):
    table = design[design.index("## 当前状态"):design.index("## 路线图")]
    nodes = [int(m) for m in re.findall(r"^\| (\d+) \|", table, re.M)]
    assert nodes == list(range(1, 17)), (
        f"the status table covers {nodes}, not nodes 1-16")


def test_every_landing_path_in_the_status_table_exists(design):
    """A status pointing at a deleted file is a status nobody can check.

    This is the whole reason the table carries a landing column: without it,
    "locked" is an assertion with no way to be wrong.
    """
    table = design[design.index("## 当前状态"):design.index("## 路线图")]
    paths = {m for m in re.findall(r"`([\w./-]+\.(?:py|R|csv|gz|md|sql))`", table)}
    assert len(paths) >= 15, (
        f"only found {len(paths)} landing paths; the table looks truncated")
    missing = sorted(p for p in paths if not (ROOT / p).exists())
    assert not missing, f"the status table points at files that do not exist: {missing}"


def test_the_decision_log_is_labelled_as_history(design):
    log = design[design.index("## 决策记录"):]
    head = log[:400]
    assert "历史" in head and "当前状态" in head, (
        "the decision log must say it is history and point at the status table; "
        "it is append-only and reading it top-to-bottom gives superseded answers")


# -- numbers come from artefacts ----------------------------------------------

def test_the_cohort_counts_in_prose_match_the_strobe_table(strobe):
    """20,736 / 925 are the published cohort. Both were once written as 20,737
    and 2,513 -- the second being a count from four rungs up the ladder."""
    final = strobe.iloc[-1]
    n, events = int(final["n"]), int(final["cvd_deaths"])
    assert (n, events) == (20736, 925), (
        f"the cohort changed to {n:,}/{events}; update this test and every "
        f"document listed below in the same commit")

    for doc in ("research-design.md", "advisor-briefing.md", "meeting-03-followup.md"):
        text = (DOCS / doc).read_text(encoding="utf-8")
        assert f"{n:,}" in text, f"{doc} does not carry the cohort size {n:,}"


def test_the_pce_cascade_starts_where_the_strobe_ladder_ends(strobe, cascade):
    """The cascade used to build a second cohort with three fewer exclusions,
    so it reported the cost of a filter against 35 people who are not in the
    study. Now it reads the published one, and this pins the join."""
    cohort_end = int(cascade[cascade.section == "cohort"]["n"].iloc[-1])
    inputs_start = int(cascade[cascade.section == "pce_inputs"]["n"].iloc[0])
    assert cohort_end == int(strobe["n"].iloc[-1]) == inputs_start


def test_the_complete_case_subsample_is_quoted_from_the_cascade(cascade):
    """17,464 / 756 came from the ladder that no longer exists. Anywhere the
    complete-case subsample is named, it has to be the current one."""
    last = cascade[cascade.section == "pce_inputs"].iloc[-1]
    n, events = int(last["n"]), int(last["cvd_deaths"])
    bench = (DOCS / "pce-benchmark.md").read_text(encoding="utf-8")
    assert f"{n:,}" in bench and str(events) in bench
    assert "17,464" not in bench, "the superseded complete-case count is back"


def test_the_complete_case_filter_costs_more_events_than_people(cascade):
    """The reason it is disclosed as selection rather than as attrition. If this
    ever flips, the limitation paragraph is describing something else."""
    coh = cascade[cascade.section == "cohort"].iloc[-1]
    cc = cascade[cascade.section == "pce_inputs"].iloc[-1]
    lost_people = 1 - int(cc["n"]) / int(coh["n"])
    lost_events = 1 - int(cc["cvd_deaths"]) / int(coh["cvd_deaths"])
    assert lost_events > lost_people, (
        f"complete-case now drops {lost_people:.1%} of people and "
        f"{lost_events:.1%} of events; the disclosure says the opposite")


def test_the_readme_badge_and_its_prose_report_the_same_suite():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    badge = re.search(r"badge/tests-(\d+)%20passing", readme)
    assert badge, "the README has no passing-tests badge to check"
    prose = set(re.findall(r"\b(\d+) (?:tests|regressions)\b", readme))
    assert prose, "no prose mention of the test count; the sync has nothing to keep honest"
    assert prose == {badge.group(1)}, (
        f"badge says {badge.group(1)}, prose says {sorted(prose)}")


# -- the redesigned cycle is not the eleventh of the same kind ----------------

def test_no_published_page_prints_the_bare_cycle_key():
    """The key is the NHANES file suffix. That cycle ran August 2021 to August
    2023 on a redesigned sample, and printing the key beside ten genuine
    two-year cycles tells the reader it is one of them."""
    pages = sorted((ROOT / "docs").glob("*.html"))
    assert pages, "no published pages found; run scripts/build_site.py"
    offenders = {}
    for f in pages:
        h = f.read_text(encoding="utf-8")
        h = re.sub(r"<style>.*?</style>", "", h, flags=re.S)
        h = re.sub(r'data:image/[^"]*', "", h)
        n = len(re.findall(CYCLE_KEY, h))
        if n:
            offenders[f.name] = n
    assert not offenders, f"bare cycle key on published pages: {offenders}"


def test_display_cycle_relabels_only_the_redesigned_cycle():
    from src.descriptive import display_cycle
    assert display_cycle(CYCLE_KEY) == "Aug 2021&ndash;Aug 2023"
    assert display_cycle(CYCLE_KEY, dash="–") == "Aug 2021–Aug 2023"
    assert display_cycle("2013-2014") == "2013-2014"


# -- the retired competing-risk model is not still described as current -------

def test_fine_gray_is_not_described_as_the_prediction_model():
    """The 2026-08-10 decision replaced it with two cause-specific fits. Four
    tables kept listing it, in the row a reader checks to see what was run."""
    # A line may name Fine-Gray as long as it names it as something NOT used:
    # struck through, superseded, pointed at the section that explains the
    # replacement, or discussed as the alternative that was considered.
    allowed = ("不拟合", "不再拟合", "没有拟合", "~~",
               "见 4.4", "必须换成", "次分布风险")
    for doc in ("research-design.md", "advisor-briefing.md"):
        text = (DOCS / doc).read_text(encoding="utf-8")
        for line in text.splitlines():
            if "Fine-Gray" not in line:
                continue
            assert any(a in line for a in allowed), (
                f"{doc} still presents Fine-Gray as current: {line[:110]!r}")


def test_the_frozen_review_says_it_is_frozen():
    head = (DOCS / "methodology-review.md").read_text(encoding="utf-8")[:900]
    assert "历史审查快照" in head and "632e92e" in head


def test_the_narrative_briefing_defers_to_the_authorities():
    head = (DOCS / "advisor-briefing.md").read_text(encoding="utf-8")[:900]
    assert "不是权威版本" in head
    assert "research-design.md" in head and "reports/" in head
