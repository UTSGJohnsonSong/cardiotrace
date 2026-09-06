"""Render current handover facts from committed analysis artefacts."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START, END = "<!-- HANDOVER_STATUS_START -->", "<!-- HANDOVER_STATUS_END -->"


def build(root=ROOT):
    def read(name):
        return json.loads((root / "reports" / name).read_text(encoding="utf-8"))
    cohort, pce, tests = (read(name) for name in
                         ("cohort_results.json", "pce_results.json", "test_summary.json"))
    primary = pce["primary"]
    paired = primary["cascade"][-1]
    lines = [
        "**Generated from tracked results; edit the producers, not this block.**",
        "",
        f"**Tests:** {tests['collected']} collected. This includes conditional skips.",
        "The count is not a passed-test count; consult the actual pytest run and CI.",
        "",
        "| Cohort | Value |", "|---|---:|",
        f"| Participants | {cohort['n_participants']:,} |",
        f"| CVD deaths | {cohort['cvd_deaths']:,} |",
        f"| Competing deaths | {cohort['competing_deaths']:,} |",
        f"| Person-years | {cohort['person_years']:,.0f} |",
        f"| Median / maximum follow-up | {cohort['median_followup_years']:.2f} / {cohort['max_followup_years']:.2f} years |",
        "",
        f"**PCE primary paired sample:** {paired['n']:,} people / {paired['cvd_deaths']} deaths.",
        "",
        "| Temporal test | n | Published PCE weighted C | CardioTrace weighted C | Paired difference (95% interval) |",
        "|---|---:|---:|---:|---|",
    ]
    for horizon, test in primary["tests"].items():
        metrics = test["metrics"]
        a, b = metrics["1a_published_ascvd"], metrics["3_cardiotrace_refit"]
        delta = test["delta_c_vs_published_pce"]["3_cardiotrace_refit"]
        lines.append(f"| {horizon} | {a['n']:,} | {a['c']:.4f} | {b['c']:.4f} | "
                     f"{delta['delta']:+.4f} ({delta['lo']:+.4f}, {delta['hi']:+.4f}) |")
    lines += [
        "",
        "The published PCE score targets ten-year hard ASCVD and is used only as",
        "a ranking score at five years. This study observes CVD mortality.",
        "The paired differences do not establish discrimination superiority.",
        "Decision curves for mortality are exploratory and use illustrative thresholds.",
        "",
        "Sources: `reports/cohort_results.json`, `reports/pce_results.json`,",
        "`reports/test_summary.json`. Model, missingness and Part 4 details remain in",
        "their result JSON/CSV and the generated report. Design-node status has one",
        "authority: the current-status table in `docs/research-design.md`.",
        "Verification scope and commit live in `reports/verify_receipt.json`;",
        "run `python scripts/check_receipt.py` to check release freshness.",
    ]
    return "\n".join(lines)


def render(text, root=ROOT):
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError("Handover must contain exactly one status marker pair")
    before, rest = text.split(START)
    old, after = rest.split(END)
    return before + START + "\n" + build(root) + "\n" + END + after


if __name__ == "__main__":
    path = ROOT / "docs/handover.md"
    path.write_text(render(path.read_text(encoding="utf-8")), encoding="utf-8")
    print("Handover status rebuilt from tracked artefacts")

