#!/usr/bin/env python3
"""Check Stage 2 publication scope, source roles, counts and working local links."""
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / 'stages/02-post-discovery'
DATA = STAGE / 'data'


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.ids, self.details = [], set(), []
        self.language = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'html':
            self.language = attrs.get('lang')
        if 'id' in attrs:
            assert attrs['id'] not in self.ids, ('Duplicate anchor', attrs['id'])
            self.ids.add(attrs['id'])
        if tag == 'a' and 'href' in attrs:
            self.links.append(attrs['href'])
        if tag == 'details':
            self.details.append('open' in attrs)


def main():
    read = lambda name: json.loads((DATA / name).read_text())
    protocol, runs, attempts = [read(name + '.json') for name in ('protocol', 'runs', 'attempts')]
    assert len(runs) == 6 and len(attempts) == 10
    assert len({r['id'] for r in runs}) == 6 and len({r['id'] for r in attempts}) == 10
    indexed = {r['id']: r for r in attempts}
    assert all(r['body_complete'] is True and r['status'] in {'completed', 'recovered'} for r in runs)
    for attempt in attempts:
        assert attempt['prompt'] == protocol['prompts'][attempt['condition']]
        assert read(attempt['raw_file']) == attempt
    for run in runs:
        selected = indexed[run['selected_attempt_id']]
        comparable = lambda r: {k: v for k, v in r.items() if k not in {'id', 'selected_attempt_id'}}
        assert comparable(run) == comparable(selected), ('Selected answer differs', run['id'])
    early_c = [indexed['S2-CHATGPT-C' + suffix] for suffix in ('', '-R2', '-R3', '-R4')]
    assert early_c[0]['status'] == 'technical_failure'
    assert all(r['body_complete'] is False and r['assessment']['outcome'] == 'indeterminate' for r in early_c[1:])
    c = indexed['S2-CHATGPT-C-R5']
    assert c['temporary'] is None and c['personalization'] is None and c['submitted_at'] is None
    assert len(c['answer_links']) == 11 and len({r['url'] for r in c['answer_links']}) == 11
    assert sum(bool(r['recommendation']) for r in c['entity_observations']) == 8
    assert sum(not r['recommendation'] for r in c['entity_observations']) == 3
    artur = next(r for r in c['entity_observations'] if 'Artur Ferreira' in r['entity'])
    assert artur['citation'] and artur['mention'] and not artur['recommendation']
    target = read('target-post.json')
    excerpt = protocol['exact_search_excerpt']
    assert len(excerpt) == 86 and excerpt in target['body_text']
    assert protocol['exact_excerpt_verification']['exact_unicode_substring'] is True
    assert protocol['publication_date'] == '2026-11-01'
    forbidden = {
        'private conversation/share URL': r'https?://(?:chatgpt\.com/(?:c|s|share)/|grok\.com/c/)',
        'local path or evidence file': r'/Users/|(?<!\w)(?:raw|screenshots)/[\w./-]+',
        'private identifier field': r'"(?:conversation_url|original_conversation_url|saved_conversation_url|share_url|recovered_message_id|automation_id|screenshot_file|answer_dom_file|capture_file|artifacts)"\s*:',
        'tracking parameter': r'[?&](?:(?:a?utm_)\w+|roistat_visit|_ga|_bhlid|fbclid|gclid)=',
        'credential': r'Bearer [A-Za-z0-9._-]{16,}|(?:access_token|refresh_token)\s*[":=]',
        'untranslated annotation': r'[\u3400-\u9fff]',
    }
    files = [p for p in STAGE.rglob('*') if p.is_file()]
    assert not any(p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.har', '.log'} for p in files)
    for path in files:
        if path.suffix in {'.json', '.html', '.md', '.txt'}:
            value = path.read_text()
            for label, pattern in forbidden.items():
                assert not re.search(pattern, value, re.I), (str(path.relative_to(ROOT)), label)
    document = (STAGE / 'index.html').read_text()
    assert 'file unavailable' not in document and 'private local evidence links' not in document
    page = Page()
    page.feed(document)
    assert page.language == 'en' and page.details and all(page.details)
    for link in page.links:
        parsed = urlsplit(link)
        if parsed.scheme or parsed.netloc:
            assert parsed.scheme in {'http', 'https'}
            continue
        path = (STAGE / unquote(parsed.path)).resolve() if parsed.path else STAGE / 'index.html'
        assert path.is_relative_to(ROOT), ('Escaping public repository', link)
        if path.is_dir():
            path = path / 'index.html'
        assert path.is_file(), ('Broken Stage 2 link', link)
        if parsed.fragment and path == STAGE / 'index.html':
            assert unquote(parsed.fragment) in page.ids, ('Broken Stage 2 anchor', link)
    expected = {str(p.relative_to(STAGE)) for p in DATA.rglob('*.json')}
    with zipfile.ZipFile(STAGE / 'public-data.zip') as archive:
        assert archive.testzip() is None and set(archive.namelist()) == expected
        for name in archive.namelist():
            assert archive.read(name) == (STAGE / name).read_bytes()
    print(json.dumps({'stage': 2, 'selected_answers': 6, 'actual_submissions': 10,
                      'earlier_C_failures_or_partial_captures': 4, 'manual_C_urls': 11,
                      'privacy_check': 'passed', 'expanded_details': len(page.details),
                      'valid_report_links': len(page.links)}))


if __name__ == '__main__':
    main()
