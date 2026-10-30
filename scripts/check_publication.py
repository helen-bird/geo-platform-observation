#!/usr/bin/env python3
"""Check the exact public release boundary, metrics and local links."""
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, unquote
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT

class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.ids, self.details = [], set(), []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        if tag == 'a' and 'href' in attrs:
            self.links.append(attrs['href'])
        if tag == 'details':
            self.details.append('open' in attrs)

def main():
    texts = []
    files = [p for p in DIST.rglob('*') if p.is_file()]
    for path in files:
        if path.suffix in ('.html', '.json', '.txt'):
            texts.append((str(path.relative_to(DIST)), path.read_text()))
    forbidden = {
        'private conversation': r'https?://(?:chatgpt\.com/(?:c|share)/|grok\.com/c/)',
        'local path': r'/Users/|(?:data/)(?:raw|recovery|screenshots|diagnostics|archive)/',
        'tracking parameter': r'[?&](?:(?:a?utm_)\w+|roistat_visit|_ga|_bhlid|fbclid|gclid)=',
        'personal X context': r'your (?:existing|own) X account|Given your focus on building GEO knowledge through original content on X|X engagement|publish on X|experiments on X|用户在X上的背景',
        'credential': r'Bearer [A-Za-z0-9._-]{16,}|(?:access_token|refresh_token|source_repository_credential)\s*[":=]',
    }
    for name, value in texts:
        for label, pattern in forbidden.items():
            assert not re.search(pattern, value, re.I), (name, label)
    page = Page()
    page.feed((DIST / 'index.html').read_text())
    for link in page.links:
        parsed = urlsplit(link)
        if parsed.scheme or parsed.netloc:
            assert parsed.scheme in ('http', 'https'), 'Unexpected link protocol'
            continue
        if not parsed.path:
            assert not parsed.fragment or unquote(parsed.fragment) in page.ids, 'Broken anchor'
        else:
            target = (DIST / unquote(parsed.path).lstrip('/')).resolve()
            assert target.is_relative_to(DIST) and target.is_file(), ('Broken public link', parsed.path)
    assert page.details and all(page.details), 'All details must remain expanded'
    load = lambda name: json.loads((DIST / name).read_text())
    runs, attempts, history = load('data/runs.json'), load('data/attempts.json'), load('data/capture-history.json')
    assert (len(runs), len(attempts), len(history['captures'])) == (12, 10, 37)
    assert sum(len(r['observations']) for r in runs) == 142
    import build_report
    original = {'insights': build_report.summarize_insights(runs)}
    public = load('findings.json')
    assert public['insights'] == original['insights']
    with zipfile.ZipFile(DIST / 'public-data.zip') as archive:
        assert archive.testzip() is None
        expected = {str(p.relative_to(DIST)) for p in (DIST / 'data').rglob('*.json')} | {'findings.json'}
        assert set(archive.namelist()) == expected
        for name in archive.namelist():
            assert archive.read(name) == (DIST / name).read_bytes()
    print(json.dumps({'privacy_check': 'passed', 'public_files': len(files), 'valid_links': len(page.links), 'expanded_details': len(page.details), 'main_answers': 12, 'historical_attempts': 10, 'captures': 37, 'statistics_match': True}))

if __name__ == '__main__':
    main()
