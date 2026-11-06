#!/usr/bin/env python3
"""Check the exact public release boundary, metrics and local links."""
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit, unquote
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT

class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.ids, self.details, self.language = [], set(), [], None
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'html':
            self.language = attrs.get('lang')
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        if tag == 'a' and 'href' in attrs:
            self.links.append(attrs['href'])
        if tag == 'details':
            self.details.append('open' in attrs)

def main():
    assert not subprocess.check_output(['git', 'ls-files', '--', 'audits'], cwd=ROOT, text=True).strip(), 'Local audit evidence must not be tracked for publication'
    texts = []
    files = [p for p in DIST.rglob('*') if p.is_file() and not {'.git', '__pycache__', 'audits'}.intersection(p.relative_to(DIST).parts)]
    for path in files:
        if path.suffix in ('.html', '.json', '.txt', '.md', '.py', '.xml'):
            value = path.read_text()
            assert not re.search(r'[\u3400-\u9fff]', value), ('Untranslated text', str(path.relative_to(DIST)))
            if path.suffix != '.py':
                texts.append((str(path.relative_to(DIST)), value))
    forbidden = {
        'private conversation': r'https?://(?:chatgpt\.com/(?:c|s|share)/|grok\.com/c/)',
        'local path': r'/Users/|(?:data/)(?:raw|recovery|screenshots|diagnostics|archive)/',
        'tracking parameter': r'[?&](?:(?:a?utm_)\w+|roistat_visit|_ga|_bhlid|fbclid|gclid)=',
        'personal X context': r'your (?:existing|own) X account|Given your focus on building GEO knowledge through original content on X|X engagement|publish on X|experiments on X|\u7528\u6237\u5728X\u4e0a\u7684\u80cc\u666f',
        'excluded personal plans': r'\bX account\b|illustrative publishing context|social-first content practice|personal background anonymized|platform anonymized|\u4e2a\u4eba\u53d1\u5e03\u80cc\u666f',
        # Cleanup-policy arrays may name a token parameter without containing a
        # credential. Require an assigned value, rather than a quoted key alone.
        'credential': r'Bearer [A-Za-z0-9._-]{16,}|(?:access_token|refresh_token|source_repository_credential)["\x27]?\s*[:=]\s*["\x27]?[A-Za-z0-9._/-]{12,}',
    }
    for name, value in texts:
        for label, pattern in forbidden.items():
            # These two patterns identify the Stage 1 personal passages. Stage 3
            # verbatim answers legitimately discuss generic account controls and
            # source channels; its dedicated check rejects identifying data.
            if name.startswith(('stages/03-question-sensitivity/', 'stages/04-creator-benchmark/', 'evidence/stage-03/', 'evidence/stage-04/')) and label in {'personal X context', 'excluded personal plans'}:
                continue
            assert not re.search(pattern, value, re.I), (name, label)
    page_paths = [DIST / name for name in ['index.html','technical-appendix.html',
        'stages/02-post-discovery/index.html','stages/02-post-discovery/technical-appendix.html',
        'stages/03-question-sensitivity/index.html','stages/03-question-sensitivity/technical-appendix.html',
        'stages/04-creator-benchmark/index.html','stages/04-creator-benchmark/technical-appendix.html',
        'stages/05-technical-discoverability/index.html','stages/05-technical-discoverability/technical-appendix.html']]
    pages = {}
    for path in page_paths:
        page = Page(); document = path.read_text(); page.feed(document); pages[path.resolve()] = page
        assert page.language == 'en', 'Report language must be English'
        assert all(page.details), 'All evidence details must remain expanded'
        assert 'data-report-series="v1"' in document and 'id="report-version"' in document
        assert all(label in document for label in ['#01 · AI Recommendations','#02 · Content Discovery','#03 · Prompt Sensitivity','#04 · Creator Benchmark','#05 · Technical Discoverability'])
        if path.name == 'index.html':
            assert path.stat().st_size < 100_000, 'Keep full evidence in the appendix'
    assert len(pages[(DIST/'technical-appendix.html').resolve()].details) >= 150
    for path, page in pages.items():
        for link in page.links:
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc:
                assert parsed.scheme in ('http', 'https'), 'Unexpected link protocol'
                continue
            target = (path.parent/unquote(parsed.path)).resolve() if parsed.path else path
            if target.is_dir(): target = target / 'index.html'
            assert target.is_relative_to(DIST) and target.is_file(), ('Broken public link', str(path), link)
            if parsed.fragment and target in pages:
                assert unquote(parsed.fragment) in pages[target].ids, ('Broken anchor',str(path),link)
    load = lambda name: json.loads((DIST / name).read_text())
    runs, attempts, history = load('data/runs.json'), load('data/attempts.json'), load('data/capture-history.json')
    assert (len(runs), len(attempts), len(history['captures'])) == (12, 10, 37)
    assert sum(len(r['observations']) for r in runs) == 142
    import build_report
    original = {'insights': build_report.summarize_insights(runs)}
    public = load('findings.json')
    assert public['insights'] == original['insights']
    mapping = load('data/stage1-entity-types.json')
    mapped = {x['entity']:x['category'] for x in mapping['mappings']}
    recommended = {o['entity'] for r in runs for o in r['observations'] if o.get('recommendation') is True}
    assert set(mapped) == recommended and len(mapped) == 56
    assert len(mapping['categories']) == 7
    audit = load('data/stage1-source-audit.json')
    assert len(audit['cases']) == 10 and audit['human_review'] is False
    assert all(len(x['entities']) == 5 for x in audit['platform_selection'])
    for case in audit['cases']:
        assert case['checked_urls']
        assert all(x['url'] in case['recorded_source_urls'] for x in case['checked_urls'])
        for platform in case['selected_for_platforms']:
            assert any(r['platform']==platform and r['question_id']=='Q3' and any(o['entity']==case['entity'] and o.get('recommendation') is True for o in r['observations']) for r in runs)
    versions = load('report-versions.json')['reports']
    assert len(versions) == 5 and {r['stage'] for r in versions} == {1,2,3,4,5}
    assert all(r['first_published'] <= r['last_revised'] for r in versions)
    follow = load('stages/02-post-discovery/data/post-publication-checks.json')
    assert follow['original_six_cell_outcomes_unchanged'] is True
    assert follow['checks'][0]['observed_on'] is None and follow['checks'][0]['evidence_level']=='user_reported_observation'
    assert follow['future_retest']['results']==[] and follow['future_retest']['automation_created'] is False
    with zipfile.ZipFile(DIST / 'public-data.zip') as archive:
        assert archive.testzip() is None
        expected = {str(p.relative_to(DIST)) for p in (DIST / 'data').rglob('*') if p.is_file() and p.suffix in {'.json','.md'}} | {'findings.json'}
        assert set(archive.namelist()) == expected
        for name in archive.namelist():
            assert archive.read(name) == (DIST / name).read_bytes()
    import check_stage2_publication
    check_stage2_publication.main()
    import check_stage3_publication
    check_stage3_publication.main()
    import check_stage4_publication
    check_stage4_publication.main()
    import check_stage5_publication
    check_stage5_publication.main()
    import build_learning_hub
    build_learning_hub.check()
    import check_site_metadata
    check_site_metadata.main()
    import check_sitemap
    check_sitemap.main()
    import check_evidence_pages
    check_evidence_pages.main()
    print(json.dumps({'privacy_check': 'passed', 'language_check': 'passed', 'public_files': len(files), 'report_pages':len(pages),'valid_links':sum(len(p.links) for p in pages.values()),'expanded_details':sum(len(p.details) for p in pages.values()), 'main_answers': 12, 'historical_attempts': 10, 'captures': 37, 'statistics_match': True,'source_audit_cases':10,'series_navigation_and_versions':'passed'}))

if __name__ == '__main__':
    main()
