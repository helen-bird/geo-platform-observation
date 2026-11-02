"""Shared offline navigation and version notes for the three public reports."""
from html import escape
import json
from pathlib import Path
import posixpath
import re

ROOT = Path(__file__).resolve().parents[1]
CSS = '''
.experiment-series{margin:0 0 22px;padding:0 0 18px;border-bottom:1px solid currentColor}
.experiment-series strong{font-size:15px;letter-spacing:0;margin:0 0 8px}
.experiment-series a{display:block;font-size:13px;line-height:1.5;padding:7px 0;text-decoration:none}
.experiment-series a[aria-current]{font-weight:750;text-decoration:underline;text-underline-offset:4px}
.experiment-series a:focus-visible{outline:2px solid currentColor;outline-offset:3px}
.report-version{margin-top:38px;font-size:13px;line-height:1.65;border:1px solid #b9cdd1;background:#edf5f5;color:#243d46;padding:16px 18px;overflow-wrap:anywhere}
.report-version p{margin:5px 0}.report-version a{color:#155b65}
@media(max-width:650px){.experiment-series{margin-bottom:12px;padding-bottom:10px}.experiment-series strong{font-size:14px}.experiment-series a{display:inline-block;padding:6px 0;margin-right:14px;font-size:12px}.report-version{padding:12px}}
'''


def finish_page(document, stage, kind='reader'):
    """Add a series selector and a provenance note, without editing answer text."""
    if 'data-report-series="v1"' in document:
        raise ValueError('Series navigation has already been inserted')
    reports = json.loads((ROOT/'report-versions.json').read_text())['reports']
    selected = next(r for r in reports if r['stage'] == stage)
    directory = posixpath.dirname(selected['path']) or '.'
    relative = lambda path: posixpath.relpath(path, directory)
    links = ''.join(
        '<a href="'+escape(relative(r['path']),quote=True)+'"'+
        (' aria-current="'+('page' if kind=='reader' else 'step')+'"' if r['stage']==stage else '')+'>'+
        escape(f'#{r["stage"]:02d} · {r["title"]}')+'</a>' for r in reports)
    series = '<div class="experiment-series" data-report-series="v1" aria-label="GEO Lab experiment series"><strong>GEO Lab experiments</strong>'+links+'</div>'
    match = re.search(r'<nav\b[^>]*>.*?</nav>',document,re.S)
    if not match:
        raise ValueError('Report has no navigation element')
    nav = match.group()
    # Remove superseded simple stage links only in the page's own navigation.
    nav = re.sub(r'<a\b[^>]*>Stage [123](?: report|: Question sensitivity)?</a>', '',nav)
    nav = re.sub(r'(<nav\b[^>]*>)',lambda m:m.group(1)+series,nav,count=1)
    nav = nav.replace('</nav>','<a href="#report-version">Report version</a></nav>')
    document = document[:match.start()] + nav + document[match.end():]
    fields = [('Experiment date',selected['experiment_dates']),('First published',selected['first_published']),('Last revised',selected['last_revised']),('Version','v'+selected['version'])]
    note = '<blockquote class="report-version" id="report-version"><p>'+' · '.join('<strong>'+escape(k)+':</strong> '+escape(v) for k,v in fields)+'</p><p>'+escape(selected['revision_note'])+'</p><p><a href="'+relative('report-versions.json')+'">Version metadata</a> · <a href="'+relative('CHANGELOG.md')+'">Revision history</a> · <a href="'+relative('reviews/2026-11-02-stages-01-02.md')+'">Cross-report review decisions</a></p></blockquote>'
    document = document.replace('</main>',note+'</main>',1)
    document = document.replace('</head>','<style>'+CSS+'</style></head>',1)
    return document
