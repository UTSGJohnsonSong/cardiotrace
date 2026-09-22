"""Verify a reviewed Tableau atlas against current or explicitly frozen sources."""
import argparse
import base64
import hashlib
import html
import json
from pathlib import Path, PurePosixPath
import zipfile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = 'tableau'
CURRENT_DIRECTORY = 'tableau/current'
WORKBOOK = 'cardiotrace-atlas.twbx'
SITE = 'https://utsgjohnsonsong.github.io/cardiotrace/'
PANELS = (
    ('population', '01-population-burden.png', 'Population burden',
     'Crude and age-standardised prevalence, latest race–ethnicity intervals, and age patterns across survey cycles.',
     (('burden.html', 'Burden: trends and survey design'), ('pandemic.html', 'Pandemic: the limits of one post-period'))),
    ('mortality', '02-mortality-risk.png', 'Mortality risk',
     'Blood-pressure strata, adjusted associations checked in R, and five- and ten-year calibration.',
     (('cohort.html', 'Cohort: eligibility, associations and calibration'),)),
    ('models', '03-model-evidence.png', 'Model evidence',
     'Paired comparisons with historical PCE, the separate Part 4 learning experiment, and exploratory decision curves.',
     (('methods.html', 'Methods: the historical PCE benchmark'), ('learning.html', 'Predictive modeling: the Part 4 experiment'))),
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(root=ROOT):
    """Check current source bytes, reviewed previews and the portable workbook.

    Tableau images are reviewed snapshots, not Python-rendered artefacts. A
    source change must fail any attempt to present the atlas as current rather
    than silently publish stale titles, intervals or counts as current evidence.
    An explicitly labelled archive must use validate_snapshot instead.
    No Tableau installation or optional Hyper dependency is required in CI.
    """
    root = Path(root)
    return _validate(root, source_root=root, snapshot=False)


def validate_snapshot(root=ROOT):
    """Verify the historical atlas against its preserved, reviewed source bytes.

    This does not certify that the workbook represents current research.
    Callers must label it as the 6 September 2026 historical snapshot; the
    current-source validation above intentionally continues to reject drift.
    Workbook, preview and portable-connection checks are identical in both modes.
    """
    root = Path(root)
    return _validate(root, source_root=root / 'docs' / DIRECTORY / 'source-snapshot',
                     snapshot=True)


def validate_current(root=ROOT):
    """Verify the new native review against current aggregate source bytes."""
    root = Path(root)
    directory = root / 'docs' / CURRENT_DIRECTORY
    verification = json.loads((directory / 'verification.json').read_text(encoding='utf-8'))
    for requirement in ('native_saved', 'final_output_reopened_in_tableau',
                        'all_three_dashboards_rendered', 'tooltip_visually_verified',
                        'all_data_connections_embedded', 'source_hashes_match'):
        if verification.get(requirement) is not True:
            raise ValueError(f'Current Tableau native review is incomplete: {requirement}')
    if not verification.get('tables') or any(
            table.get('all_values_match') is not True for table in verification['tables']):
        raise ValueError('Current Tableau extract comparison is incomplete')
    audit = _validate(root, source_root=root, snapshot=False, directory=directory)
    tables = verification['tables']
    expected = [(chart['sheet'], chart['rows']) for chart in audit['charts']]
    if [(table.get('sheet'), table.get('rows')) for table in tables] != expected:
        raise ValueError('Current Tableau extract comparison does not cover every chart')
    if verification.get('rows') != sum(rows for _, rows in expected):
        raise ValueError('Current Tableau extract row total differs from its audit')
    return audit


def _validate(root, *, source_root, snapshot, directory=None):
    """Share artifact checks without allowing current-source validation to fall back."""
    directory = directory or root / 'docs' / DIRECTORY
    audit = json.loads((directory / 'data-audit.json').read_text(encoding='utf-8'))
    verification = json.loads((directory / 'verification.json').read_text(encoding='utf-8'))
    if audit['source_commit'] != verification['source_commit']:
        raise ValueError('Tableau source versions disagree')
    if not audit['source_sha256']:
        raise ValueError('Tableau has no source manifest')
    if set(audit['source_sha256_lf']) != set(audit['source_sha256']):
        raise ValueError('Tableau normalised source manifest is incomplete')
    # Git checks out CRLF on Windows and LF on Linux. Preserve the original
    # review digests, but compare source text with the same LF normalisation
    # used by the repository index. Binary workbook/preview hashes stay exact.
    for rel, expected in audit['source_sha256_lf'].items():
        path = PurePosixPath(rel)
        if ':' in rel or path.is_absolute() or '..' in path.parts:
            raise ValueError(f'Tableau source path is not relative: {rel}')
        actual = hashlib.sha256((source_root / rel).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        if actual != expected:
            kind = 'snapshot source' if snapshot else 'source'
            action = ('restore the preserved reviewed bytes' if snapshot
                      else 'rebuild and review the atlas')
            raise ValueError(f'Tableau {kind} changed: {rel}; {action}')
    workbook = directory / WORKBOOK
    if digest(workbook) != verification['workbook_sha256']:
        raise ValueError('Tableau workbook differs from its reviewed version')
    for _, filename, *_ in PANELS:
        if digest(directory / filename) != verification['previews'][filename]['sha256']:
            raise ValueError(f'Tableau preview differs from its reviewed version: {filename}')
    with zipfile.ZipFile(workbook) as archive:
        members = archive.namelist()
        twbs = [name for name in members if name.endswith('.twb')]
        if archive.testzip() or len(twbs) != 1:
            raise ValueError('Invalid Tableau package')
        tree = ET.fromstring(archive.read(twbs[0]))
        sheets = tree.findall('./worksheets/worksheet')
        dashboards = tree.findall('./dashboards/dashboard')
        if len(sheets) != len(audit['charts']) or len(dashboards) != len(PANELS):
            raise ValueError('Tableau sheet/dashboard inventory differs from its audit')
        connections = tree.findall('./datasources/datasource/connection')
        if not connections:
            raise ValueError('Tableau package contains no data connections')
        for connection in connections:
            path = connection.get('dbname', '')
            if (connection.get('class') != 'hyper' or path not in members
                    or ':' in path or PurePosixPath(path).is_absolute()
                    or '..' in PurePosixPath(path).parts):
                raise ValueError(f'Tableau connection is not portable: {path}')
    return audit


def report_appendix(root=ROOT):
    """Embed the current reviewed Tableau dashboards for offline reading."""
    audit = validate_current(root)
    figures = []
    for anchor, filename, title, description, links in PANELS:
        image = base64.b64encode((Path(root) / 'docs' / CURRENT_DIRECTORY / filename).read_bytes()).decode('ascii')
        figures.append(f'<figure><a href="{SITE}explore.html#{anchor}">'
                       f'<img src="data:image/png;base64,{image}" '
                       f'alt="Tableau dashboard: {html.escape(description)}" loading="lazy" '
                       f'style="width:100%;height:auto"></a>'
                       f'<figcaption><b>{title}.</b> {description}</figcaption></figure>')
    return f'''<section id="tableau-atlas">
  <div class="sec-head"><div class="sec-num">A</div><h2>Tableau dashboards</h2></div>
  <div class="body-indent">
    <p class="lede measure">Three combined views of population burden, mortality risk and model comparisons.
    The native Tableau workbook uses the current aggregate results, including Aalen–Johansen calibration.</p>
    <p class="measure">The previews are embedded for offline reading. Download the
    <a href="{SITE}{CURRENT_DIRECTORY}/{WORKBOOK}">editable Tableau workbook</a> for native charts and hover details.
    The reviewed workbook describes research version
    <a href="https://github.com/UTSGJohnsonSong/cardiotrace/tree/{audit['source_commit']}">{audit['source_commit'][:7]}</a>.
    The <a href="{SITE}explore.html#tableau-history">6 September snapshot</a> is preserved separately.</p>
    {''.join(figures)}
  </div>
</section>'''


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', action='store_true',
                        help='check the labelled historical snapshot against frozen sources')
    parser.add_argument('--current', action='store_true',
                        help='check the newly reviewed atlas against current source files')
    args = parser.parse_args()
    if args.snapshot and args.current:
        parser.error('choose either --snapshot or --current')
    audit = validate_current() if args.current else validate_snapshot() if args.snapshot else validate()
    source_kind = 'frozen historical' if args.snapshot else 'current'
    print(f"Tableau atlas matches {len(audit['source_sha256'])} {source_kind} source files")
