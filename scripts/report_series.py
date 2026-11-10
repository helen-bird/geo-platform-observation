"""Shared offline navigation and version notes for the public learning reports."""
from html import escape, unescape
import json
from pathlib import Path
import posixpath
import re
from urllib.parse import urlsplit
from site_metadata import finalize_page, relative_canonical

ROOT = Path(__file__).resolve().parents[1]
INTERIM_READER = 'reviews/interim-review/historical-replication/index.html'
INTERIM_LABEL = 'Interim Review · Part 1'
CSS = '''
.experiment-series{grid-column:1/-1;margin:0 0 22px;padding:0 0 18px;border-bottom:1px solid currentColor}
.experiment-series strong{font-size:15px;letter-spacing:0;margin:0 0 8px}
.experiment-series a{display:block;font-size:13px;line-height:1.5;padding:7px 0;text-decoration:none}
.experiment-series a[aria-current]{font-weight:750;text-decoration:underline;text-underline-offset:4px}
.experiment-series a:focus-visible{outline:2px solid currentColor;outline-offset:3px}
.report-version{margin-top:38px;font-size:13px;line-height:1.65;border:1px solid #b9cdd1;background:#edf5f5;color:#243d46;padding:16px 18px;overflow-wrap:anywhere}
.report-version p{margin:5px 0}.report-version a{color:#155b65}
@media(max-width:650px){.experiment-series{margin-bottom:12px;padding-bottom:10px}.experiment-series strong{font-size:14px}.experiment-series a{display:inline-block;padding:6px 0;margin-right:14px;font-size:12px}.report-version{padding:12px}}
'''


def series_navigation(reports, directory, selected_path, kind='reader'):
    entries = [('learning-hub/index.html', 'Learning Hub · Start with a question')]
    entries += [(r['path'], f'#{r["stage"]:02d} · {r["title"]}') for r in reports]
    entries += [(INTERIM_READER, INTERIM_LABEL), ('evidence/index.html', 'Evidence library · Individual answers')]
    active = 'page' if kind == 'reader' else 'step'
    links = ''.join(
        '<a href="'+escape(relative_canonical(path, directory), quote=True)+'"'+
        (f' aria-current="{active}"' if path == selected_path else '')+'>'+escape(label)+'</a>'
        for path, label in entries
    )
    return '<div class="experiment-series" data-report-series="v1" aria-label="GEO Lab learning series"><strong>GEO Lab learning records</strong>'+links+'</div>'


def finish_page(document, stage, kind='reader'):
    """Add a series selector and a provenance note, without editing answer text."""
    if 'data-report-series="v1"' in document:
        raise ValueError('Series navigation has already been inserted')
    reports = json.loads((ROOT/'report-versions.json').read_text())['reports']
    selected = next(r for r in reports if r['stage'] == stage)
    directory = posixpath.dirname(selected['path']) or '.'
    relative = lambda path: posixpath.relpath(path, directory)
    series = series_navigation(reports, directory, selected['path'], kind)
    match = re.search(r'<nav\b[^>]*>.*?</nav>',document,re.S)
    if not match:
        raise ValueError('Report has no navigation element')
    nav = match.group()
    # The Stage 4 local reader has an earlier standalone series block. Replace
    # it with the same versioned navigation used by every public report.
    nav = re.sub(r'<div class="experiment-series"[^>]*>.*?</div>', '', nav, flags=re.S)
    # Remove superseded simple stage links only in the page's own navigation.
    nav = re.sub(r'<a\b[^>]*>Stage [123](?: report|: Question sensitivity)?</a>', '',nav)
    nav = re.sub(r'(<nav\b[^>]*>)',lambda m:m.group(1)+series,nav,count=1)
    nav = nav.replace('</nav>','<a href="#report-version">Report version</a></nav>')
    known_readers = {r['path'] for r in reports} | {'learning-hub/index.html', 'evidence/index.html'}
    def canonical_navigation(match):
        value = unescape(match.group(1)); parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc or not parsed.path:
            return match.group()
        target = posixpath.normpath(posixpath.join(directory, parsed.path))
        if target not in known_readers:
            return match.group()
        href = relative_canonical(target, directory)
        if parsed.fragment: href += '#'+parsed.fragment
        return 'href="'+escape(href, quote=True)+'"'
    nav = re.sub(r'href="([^"]*)"', canonical_navigation, nav)
    document = document[:match.start()] + nav + document[match.end():]
    fields = [('Author','Helen Bird'),('Observation period' if selected.get('record_type')=='technical_learning_record' else 'Experiment date',selected['experiment_dates']),('First published',selected['first_published']),('Last revised',selected['last_revised']),('Version','v'+selected['version'])]
    note = '<blockquote class="report-version" id="report-version"><p>'+' · '.join('<strong>'+escape(k)+':</strong> '+escape(v) for k,v in fields)+'</p><p>'+escape(selected['revision_note'])+'</p><p><a href="'+relative('report-versions.json')+'">Version metadata</a> · <a href="'+relative('CHANGELOG.md')+'">Revision history</a> · <a href="'+relative('reviews/2026-11-02-stages-01-02.md')+'">Cross-report review decisions</a> · <a href="'+relative('reviews/2026-11-03-stage04.md')+'">Stage 4 review decisions</a> · <a href="'+relative('reviews/2026-11-04-technical-maintenance.md')+'">Technical maintenance</a></p></blockquote>'
    document = document.replace('</main>',note+'</main>',1)
    document = document.replace('</head>','<style>'+CSS+'</style></head>',1)
    page_path = selected['path'] if kind == 'reader' else posixpath.join(directory, 'technical-appendix.html')
    return finalize_page(document, page_path, kind=kind, stage=stage)
