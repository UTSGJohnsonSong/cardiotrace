"""Keep the reviewed Tableau snapshot attached to the evidence it visualises."""
import base64
import shutil
from pathlib import Path
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup
import pytest

from scripts.tableau_atlas import PANELS, ROOT, WORKBOOK, validate


def test_reviewed_atlas_matches_current_research_sources():
    audit = validate()
    assert len(audit['source_sha256']) == 12
    assert len(audit['charts']) == 12
    assert audit['participants_in_extract'] is False
    assert audit['analysis_refitted'] is False


@pytest.mark.parametrize('changed', ['reports/pce_results.json', f'docs/tableau/{WORKBOOK}'])
def test_stale_sources_or_unreviewed_workbook_stop_publication(tmp_path, changed):
    audit = validate()
    shutil.copytree(ROOT / 'docs/tableau', tmp_path / 'docs/tableau')
    for rel in audit['source_sha256']:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, target)
        target.write_bytes(target.read_bytes().replace(b'\r\n', b'\n'))
    validate(tmp_path)  # A Linux checkout of a Windows-reviewed source is valid.
    with (tmp_path / changed).open('ab') as stream:
        stream.write(b'\nchanged after review\n')
    with pytest.raises(ValueError, match='Tableau (source changed|workbook differs)'):
        validate(tmp_path)


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
        images = appendix.find_all('img')
        assert len(images) == len(PANELS)
        for image, (_, filename, *_) in zip(images, PANELS):
            assert image['src'].startswith('data:image/png;base64,')
            assert base64.b64decode(image['src'].split(',', 1)[1]) == (docs / 'tableau' / filename).read_bytes()
