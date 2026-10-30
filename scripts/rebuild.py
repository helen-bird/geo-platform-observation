#!/usr/bin/env python3
"""Reproduce the Stage 1 public report from versioned observations, offline."""
import json
from pathlib import Path
import re
import zipfile
import build_report

ROOT = Path(__file__).resolve().parents[1]
SITE_URL = 'https://helen-bird.github.io/geo-platform-observation/'

def main():
    read = lambda path: json.loads((ROOT / path).read_text())
    runs, attempts, history = read('data/runs.json'), read('data/attempts.json'), read('data/capture-history.json')
    assert (len(runs), len(attempts), len(history['captures'])) == (12, 10, 37)
    for record in runs + attempts:
        assert read(record['raw_file']) == record, 'Individual record differs from aggregate data'
    findings = build_report.aggregate(runs, attempts, history)
    findings['insights'] = build_report.summarize_insights(runs)
    (ROOT / 'findings.json').write_text(json.dumps(findings, ensure_ascii=True, indent=2) + '\n')
    html = build_report.render(runs, findings, attempts, history)
    notice = ('<blockquote class="report-note"><strong>Stage 1 · Public record</strong>'
              '<p>Unrelated personal-context passages have been omitted and marked. Tracking parameters have been removed from public source links. '
              'Recommended entities, citation attribution and statistics are preserved. Private conversations, screenshots and complete local archives are excluded.</p>'
              '<p>The report and annotations are in English. Verbatim platform answers remain unchanged apart from marked privacy edits. '
              'Captured non-English UI tokens are preserved using Unicode escapes.</p>'
              '<p><a href="public-data.zip">Download Stage 1 public data</a> · '
              '<a href="data/publication-notes.json">Publication scope</a> · '
              '<a href="https://github.com/helen-bird/geo-platform-observation">Learning log and stage index</a></p></blockquote>')
    html = html.replace('</header>', '</header>' + notice, 1)
    html = re.sub(r'<title>.*?</title>', '<title>GEO Learning Log | Stage 1: ChatGPT and Grok</title>', html, count=1)
    metadata = (f'<link rel="canonical" href="{SITE_URL}">'
                '<meta name="description" content="An ongoing GEO learning log. Stage 1 compares recommendations, citations and C/M/R patterns in 12 ChatGPT Search and Grok answers. These observations cannot establish GEO effectiveness.">'
                '<meta property="og:type" content="website">'
                '<meta property="og:title" content="GEO Learning Log | Stage 1">'
                '<meta property="og:description" content="An ongoing record of GEO learning and experiments, starting with a ChatGPT Search and Grok comparison.">'
                f'<meta property="og:url" content="{SITE_URL}">')
    html = html.replace('</head>', metadata + '</head>')
    (ROOT / 'index.html').write_text(html)
    (ROOT / '404.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Page not found</title><h1>Page not found</h1><p><a href="/geo-platform-observation/">Return to the GEO Learning Log</a></p></html>')
    with zipfile.ZipFile(ROOT / 'public-data.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((ROOT / 'data').rglob('*.json')):
            archive.write(path, path.relative_to(ROOT))
        archive.write(ROOT / 'findings.json', 'findings.json')
    print(json.dumps({'main_answers': len(runs), 'historical_attempts': len(attempts), 'captures': len(history['captures']), 'observations': findings['insights']['observation_count']}))

if __name__ == '__main__':
    main()
