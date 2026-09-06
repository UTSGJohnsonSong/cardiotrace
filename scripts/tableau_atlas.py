"""Publish the reviewed Tableau snapshot only while its sources still match."""
import base64
import hashlib
import html
import json
from pathlib import Path, PurePosixPath
import zipfile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = 'tableau'
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
    source change must fail the site build rather than silently publish stale
    dashboard titles, intervals or sample counts beside a regenerated report.
    No Tableau installation or optional Hyper dependency is required in CI.
    """
    root = Path(root)
    directory = root / 'docs' / DIRECTORY
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
        actual = hashlib.sha256((root / rel).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        if actual != expected:
            raise ValueError(f'Tableau source changed: {rel}; rebuild and review the atlas')
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
    """Keep the complete report portable; interactive detail is an explicit link."""
    audit = validate(root)
    figures = []
    for anchor, filename, title, description, links in PANELS:
        image = base64.b64encode((Path(root) / 'docs' / DIRECTORY / filename).read_bytes()).decode('ascii')
        figures.append(f'<figure><a href="{SITE}explore.html#{anchor}">'
                       f'<img src="data:image/png;base64,{image}" '
                       f'alt="Tableau dashboard: {html.escape(description)}" loading="lazy" width="2760" height="1880" '
                       f'style="width:100%;height:auto"></a>'
                       f'<figcaption><b>{title}.</b> {description}</figcaption></figure>')
    return f'''<section id="tableau-atlas">
  <div class="sec-head"><div class="sec-num">A</div><h2>Tableau research atlas</h2></div>
  <div class="body-indent">
    <p class="lede measure">Three Tableau dashboards connect the burden, mortality and model-comparison results in this report.
    The previews below are embedded in this file for offline reading.
    <a href="{SITE}explore.html">Open the visual atlas</a> or
    <a href="{SITE}{DIRECTORY}/{WORKBOOK}">download the editable Tableau workbook</a> for hover details and provenance.</p>
    <p class="measure">These reviewed views use the same committed aggregates as the report, from research version
    <a href="https://github.com/UTSGJohnsonSong/cardiotrace/tree/{audit['source_commit']}">{audit['source_commit'][:7]}</a>.
    Source hashes are checked whenever the report is rebuilt. PCE remains a historical ranking benchmark;
    the endpoint mismatch and distinct analysis samples remain part of the interpretation.</p>
    {''.join(figures)}
  </div>
</section>'''


if __name__ == '__main__':
    audit = validate()
    print(f"Tableau atlas matches {len(audit['source_sha256'])} current source files")
