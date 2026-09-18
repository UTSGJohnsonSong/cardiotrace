"""Keep the reviewed Tableau snapshot attached to the evidence it visualises."""
import base64
import hashlib
import json
import shutil
from pathlib import Path
from urllib.parse import unquote, urlsplit
import zipfile
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup
import pytest

from scripts.tableau_atlas import PANELS, ROOT, WORKBOOK, report_appendix, validate, validate_snapshot


def test_reviewed_atlas_matches_frozen_research_sources():
    audit = validate_snapshot()
    assert len(audit['source_sha256']) == 12
    assert len(audit['charts']) == 12
    assert audit['participants_in_extract'] is False
    assert audit['analysis_refitted'] is False


def test_current_calibration_sources_are_not_certified_by_historical_review():
    with pytest.raises(ValueError, match='Tableau source changed: reports/model_results.json'):
        validate()


@pytest.mark.parametrize('changed', ['reports/pce_results.json', f'docs/tableau/{WORKBOOK}'])
def test_stale_sources_or_unreviewed_workbook_stop_publication(tmp_path, changed):
    audit = validate_snapshot()
    shutil.copytree(ROOT / 'docs/tableau', tmp_path / 'docs/tableau')
    for rel in audit['source_sha256']:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / 'docs/tableau/source-snapshot' / rel, target)
        target.write_bytes(target.read_bytes().replace(b'\r\n', b'\n'))
    validate(tmp_path)  # A Linux checkout of a Windows-reviewed source is valid.
    with (tmp_path / changed).open('ab') as stream:
        stream.write(b'\nchanged after review\n')
    with pytest.raises(ValueError, match='Tableau (source changed|workbook differs)'):
        validate(tmp_path)


@pytest.mark.parametrize('changed', [
    'source-snapshot/reports/model_results.json',
    WORKBOOK,
    '02-mortality-risk.png',
])
def test_altered_historical_sources_and_artifacts_are_rejected(tmp_path, changed):
    shutil.copytree(ROOT / 'docs/tableau', tmp_path / 'docs/tableau')
    validate_snapshot(tmp_path)
    with (tmp_path / 'docs/tableau' / changed).open('ab') as stream:
        stream.write(b'\nchanged after review\n')
    with pytest.raises(ValueError, match='Tableau (snapshot source changed|workbook differs|preview differs)'):
        validate_snapshot(tmp_path)


def test_snapshot_still_requires_embedded_portable_connections(tmp_path):
    directory = tmp_path / 'docs/tableau'
    shutil.copytree(ROOT / 'docs/tableau', directory)
    workbook = directory / WORKBOOK
    with zipfile.ZipFile(workbook) as archive:
        entries = [(item, archive.read(item.filename)) for item in archive.infolist()]
    with zipfile.ZipFile(workbook, 'w') as archive:
        for item, content in entries:
            if item.filename.endswith('.twb'):
                tree = ET.fromstring(content)
                tree.find('./datasources/datasource/connection').set('dbname', 'C:/unreviewed/data.hyper')
                content = ET.tostring(tree, encoding='utf-8')
            archive.writestr(item, content)
    # This fixture passes the digest gate deliberately to exercise the separate
    # portability gate. Production review manifests are never rewritten here.
    record = directory / 'verification.json'
    verification = json.loads(record.read_text(encoding='utf-8'))
    verification['workbook_sha256'] = hashlib.sha256(workbook.read_bytes()).hexdigest()
    record.write_text(json.dumps(verification), encoding='utf-8')
    with pytest.raises(ValueError, match='Tableau connection is not portable'):
        validate_snapshot(tmp_path)


def test_report_appendix_labels_and_collapses_the_historical_snapshot():
    appendix = BeautifulSoup(report_appendix(), 'html.parser').find(id='tableau-atlas')
    assert appendix.h2.get_text() == 'Historical Tableau snapshot (6 Sep 2026)'
    assert 'predate the Aalen–Johansen calibration correction' in appendix.get_text()
    assert 'do not represent the current results' in appendix.get_text()
    assert appendix.find('a', string='View the current charts')
    details = appendix.find('details')
    assert details and not details.has_attr('open')
    assert len(details.find_all('img')) == len(PANELS)


def test_report_atlas_links_and_offline_previews_resolve():
    docs = ROOT / 'docs'
    atlas = BeautifulSoup((docs / 'explore.html').read_text(encoding='utf-8'), 'html.parser')
    for a in atlas.select('a[href]'):
        url = urlsplit(a['href'])
        if url.scheme or url.netloc:
            continue
        target = docs / (unquote(url.path) or 'explore.html')
        assert target.is_file(), a['href']
        # HTML treats #top as the document top even without an element id.
        if url.fragment and url.fragment.lower() != 'top':
            document = BeautifulSoup(target.read_text(encoding='utf-8'), 'html.parser')
            assert document.find(id=unquote(url.fragment)), a['href']
    for anchor, image, _, _, links in PANELS:
        assert atlas.find(id=anchor)
        assert atlas.find('img', src=f'tableau/{image}')
        for page, _ in links:
            markup = (docs / page).read_text(encoding='utf-8')
            assert f'href="explore.html#{anchor}"' in markup
    for report in [docs / 'cardiotrace-report.html', ROOT / 'reports/cardiotrace-report.html']:
        soup = BeautifulSoup(report.read_text(encoding='utf-8'), 'html.parser')
        appendix = soup.find(id='tableau-atlas')
        assert appendix
        assert appendix.h2.get_text() == 'Historical Tableau snapshot (6 Sep 2026)'
        assert appendix.find('details')
        images = appendix.find_all('img')
        assert len(images) == len(PANELS)
        for image, (_, filename, *_) in zip(images, PANELS):
            assert image['src'].startswith('data:image/png;base64,')
            assert base64.b64decode(image['src'].split(',', 1)[1]) == (docs / 'tableau' / filename).read_bytes()
