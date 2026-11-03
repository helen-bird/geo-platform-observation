#!/usr/bin/env python3
"""Render Stage 4's local English reader and expanded evidence appendix.

No network, model requests, automatic semantic coding or source-data mutation.
Missing/incomplete answers and missing judgments remain unknown.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import html
import json
from pathlib import Path
import re
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
ENVIRONMENTS = ('OpenAI API + web search', 'Grok')
QUESTIONS = ('Q1', 'Q2', 'Q3')
METRICS = ('citation', 'mention', 'recommendation')
LABELS = {'citation': 'C', 'mention': 'M', 'recommendation': 'R', 'person_mention': 'Person name M', 'person_recommendation': 'Person R'}
CANDIDATE_LABELS = {'aleyda-solis': 'Aleyda Solis / Learning AI Search and related assets', 'kevin-indig': 'Kevin Indig / Growth Memo and related assets', 'artur-ferreira': 'Artur Ferreira / The GEO Lab'}
CSS = '\n:root{--ink:#182b36;--muted:#5e717c;--line:#dce5e9;--bg:#f3f6f8;--paper:#fff;--accent:#176a76;--soft:#eaf4f4;--bad:#a94635}\n*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:20px}body{margin:0;color:var(--ink);background:var(--bg);font:15px/1.6 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{color:var(--accent);text-decoration-thickness:1px;text-underline-offset:3px;overflow-wrap:anywhere}.layout{display:grid;grid-template-columns:235px minmax(0,1fr);min-height:100vh}nav{position:sticky;top:0;height:100vh;overflow:auto;background:#17343d;color:#edf7f7;padding:30px 22px}nav strong{display:block;font-size:19px;line-height:1.3;margin:0 0 12px}nav p{font-size:12px;color:#bed4db}nav a{display:block;color:#e0eeee;text-decoration:none;padding:7px 0;font-size:14px}nav .sub{padding-left:12px;font-size:12px;color:#b7d3db}main{max-width:1450px;width:100%;padding:36px 4vw 72px;min-width:0}h1{font-size:clamp(27px,3vw,42px);line-height:1.17;letter-spacing:-.035em;margin:8px 0 18px}h2{font-size:23px;line-height:1.3;margin:0 0 20px}h3{font-size:18px;margin:25px 0 12px}h4{font-size:15px;margin:18px 0 8px}p{margin:10px 0}section,.hero{background:var(--paper);border:1px solid var(--line);border-radius:15px;margin-bottom:24px;padding:26px;min-width:0}.eyebrow{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--accent);font-weight:750}.lead{font-size:17px;max-width:950px}.conclusions{padding-left:23px;margin:16px 0}.conclusions li{padding:4px 0}.counts{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:24px 0 4px}.count{padding:15px;background:var(--bg);border-radius:10px}.count strong{display:block;font-size:28px;line-height:1.25}.count span{font-size:12px;color:var(--muted)}blockquote{border-left:3px solid #7bafb5;background:var(--soft);margin:17px 0;padding:11px 17px;font-size:14px;color:#385560}blockquote p:first-child{margin-top:0}blockquote p:last-child{margin-bottom:0}.muted{color:var(--muted);font-size:13px}.preserve{white-space:pre-wrap}.table-scroll{overflow-x:auto;border:1px solid var(--line);border-radius:9px}table{border-collapse:collapse;width:100%;font-size:13px;text-align:left}td,th{padding:11px 12px;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}thead th{background:#edf3f5;white-space:nowrap}tbody tr:last-child>*{border-bottom:0}.matrix{min-width:1050px}.matrix td{min-width:105px}.badge{display:inline-block;white-space:normal;line-height:1.3;font-size:11px;font-weight:700;padding:5px 7px;border-radius:5px;background:#eef1f3;color:#52656f}.badge.good{background:#def1e8;color:#226246}.badge.bad{background:#fae7e2;color:var(--bad)}.badge.neutral{background:#edf0f3;color:#52656f}.badge.muted{background:transparent;color:#829099}.run{background:var(--paper);border:1px solid var(--line);border-radius:12px;margin:16px 0;overflow:hidden}details{border:1px solid var(--line);border-radius:8px;margin:15px 0}summary{cursor:pointer;font-weight:700;padding:15px 17px;background:#f7fafb;line-height:1.45}summary .badge{margin-left:13px}.detail-body{padding:3px 18px 18px}pre{font:13px/1.65 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;margin:10px 0;padding:14px;background:#f4f7f8;border:1px solid #e5ecef;border-radius:7px;max-width:100%}.keytable{display:grid;grid-template-columns:minmax(160px,23%) minmax(0,1fr);font-size:13px;margin:14px 0}.keytable dt,.keytable dd{border-bottom:1px solid var(--line);padding:9px 11px;margin:0;overflow-wrap:anywhere}.keytable dt{font-weight:650;background:#f5f8f9}.keytable dd pre{margin:0}ul{padding-left:21px}.definitions{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.definition{background:var(--bg);border-radius:9px;padding:14px}.definition strong{display:block}.definition p{font-size:13px;margin-bottom:0}.footer{font-size:12px;color:var(--muted)}\n@media(max-width:950px){.layout{grid-template-columns:190px minmax(0,1fr)}nav{padding:25px 17px}main{padding:24px}section,.hero{padding:20px}.counts{grid-template-columns:repeat(2,1fr)}.definitions{grid-template-columns:1fr}.keytable{grid-template-columns:145px minmax(0,1fr)}}\n@media(max-width:650px){.layout{display:block}nav{position:static;height:auto;padding:16px 20px}nav strong{margin-bottom:6px}nav p{margin:5px 0}nav .links{display:flex;flex-wrap:wrap;gap:2px 17px}nav a{font-size:12px;padding:3px 0}nav .sub{display:none}main{padding:18px 12px 45px}section,.hero{padding:18px 15px;border-radius:11px}h1{font-size:30px}h2{font-size:22px}.lead{font-size:15px}.keytable{grid-template-columns:1fr}.keytable dt{border-bottom:0;padding-bottom:3px}.keytable dd{padding-top:3px}.detail-body{padding:2px 12px 14px}summary{padding:12px}.run summary .badge{margin-top:6px;margin-left:0;display:table}pre{font-size:12px;padding:11px}}\n@media print{nav{display:none}.layout{display:block}main{max-width:none;padding:0}body{background:#fff}section,.hero,.run{break-inside:avoid;border-color:#bbb}a{color:inherit}summary{list-style:none}.table-scroll{overflow:visible}.matrix{min-width:0}table{font-size:9px}td,th{padding:5px}.counts{grid-template-columns:repeat(4,1fr)}}\n\nhtml{scrollbar-color:#7b9da5 #edf3f5}::selection{background:#b8dedf;color:#12383f}:focus-visible{outline:3px solid #176a76;outline-offset:4px}a:hover{text-decoration-thickness:2px}h1,h2,h3{text-wrap:balance}blockquote{border-left-width:1px}table,.bar-value{font-variant-numeric:tabular-nums}.reader{background:#fff}.reader main{max-width:1260px;padding:44px 5vw 80px}.reader section{border:0;border-radius:0;padding:0;margin:0 0 58px;background:transparent}.reader p,.reader li,.reader blockquote{max-width:72ch}.reader h1{max-width:24ch;margin-top:0}.reader h2{margin-bottom:18px}.reader h3{font-size:16px;margin:24px 0 10px}.reader .conclusions{font-size:17px;max-width:72ch}.reader .conclusions li{padding:6px 0 12px}.reader .boundary{margin:18px 0 24px;padding:14px 17px;border:1px solid #7bafb5;background:#eaf4f4;line-height:1.5}.reader .boundary strong{font-size:15px}.reader figure{margin:24px 0}.reader figcaption{font-size:14px;max-width:72ch;margin-bottom:20px}.chart-group{padding:15px 0 19px;border-top:1px solid #dce5e9}.chart-group h3{margin:0 0 10px}.chart-label{display:flex;justify-content:space-between;gap:12px;font-size:13px;margin-bottom:5px}.bar-row{margin:9px 0 13px}.bar-track{height:9px;background:#e8eff1;width:100%;max-width:720px}.bar-fill{height:100%;background:#176a76}.bar-fill.alternate{background:#607f88}.bar-fill.third{background:#a3b7bd}.bar-value{font-weight:650;white-space:nowrap}.chart-na{font-size:13px;padding:7px 0;color:#5e717c}.delta{font-size:13px;margin:8px 0 0}.figure-note{font-size:12px;color:#48636b}.reader .evidence-links{line-height:2}.appendix-intro{max-width:72ch}.appendix-intro h1{font-size:34px}.appendix-intro .summary-counts{font-size:14px}.appendix-review{margin-top:25px}.reader .table-scroll{margin:18px 0}.reader .footer{margin-top:45px}\n@media(max-width:650px){.reader main{padding:26px 20px 54px}.reader section{margin-bottom:42px}.reader h1{font-size:31px}.reader .conclusions{font-size:16px}.chart-label{display:block}.bar-value{display:block;margin-top:3px}.chart-group{padding-top:18px}.reader .boundary{padding:12px}.reader table{font-size:12px}.reader td,.reader th{padding:9px}.appendix-intro h1{font-size:28px}}\n@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}\n'
CSS += '''\n.reader .experiment-series{margin:20px 0;padding-top:15px;border-top:1px solid #385660}.experiment-series a[aria-current]{font-weight:750;text-decoration:underline}.measure{max-width:72ch}.status-line{font-size:14px;color:#385560}.reader .table-scroll{max-width:100%}.reader th{white-space:normal}.matrix{min-width:740px}.transcript{font:14px/1.65 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;white-space:pre-wrap;overflow-wrap:anywhere;background:#fff}.source-list{font-size:13px}.source-list li{margin:8px 0}.mono{font:12px ui-monospace,SFMono-Regular,Consolas,monospace}dt{font-weight:700}dd{margin:0 0 12px}.coverage{font-variant-numeric:tabular-nums}.candidate-chart{max-width:720px}.bar-title{font-size:13px;font-weight:650}.bar-row .bar-track{margin-top:4px}.pending{color:#5e717c}.reader .footer{border-top:1px solid #dce5e9;padding-top:20px}.reader .source-list{max-width:none}.reader .source-list li{max-width:90ch}.reader .table-scroll p{margin:0}.appendix main>section{max-width:none}.appendix .keytable{margin-bottom:22px}.skip-link{position:absolute;left:12px;top:-80px;background:#fff;padding:10px;z-index:10}.skip-link:focus{top:12px}.reader .source-audit{padding-top:6px}.reader .source-audit h3{font-size:18px}@media(max-width:650px){nav .experiment-series{display:flex;flex-wrap:wrap;gap:4px 17px;margin-top:12px;padding-top:9px}nav .experiment-series strong{width:100%;font-size:13px}.reader main{min-width:0}.transcript{font-size:13px}}'''


def esc(value):
    return html.escape(str(value), quote=True)


def load(root, name, default):
    path = root / name
    return json.loads(path.read_text()) if path.is_file() else default


def seq(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def scrub_text(value):
    """Omit unnecessary private paths, conversation links and API identifiers."""
    text = str(value)
    text = re.sub(r'https?://(?:chatgpt\.com/(?:c|s|share)/|grok\.com/(?:c|chat|share)/)[^\s<>\)\]]+', '[private conversation URL omitted]', text)
    text = re.sub(r'/Users/[^\s<>\"\']+', '[local path omitted]', text)
    text = re.sub(r'\b(?:resp|ws|msg|req)_[a-zA-Z0-9_-]{16,}\b', '[private service identifier omitted]', text)
    return text


def text(value):
    if value is None:
        return 'Unknown / not recorded'
    if value is True:
        return 'Yes'
    if value is False:
        return 'No'
    if isinstance(value, (dict, list)):
        return scrub_text(json.dumps(value, ensure_ascii=False, indent=2))
    return scrub_text(value)


def p(value, cls=''):
    return f'<p{(" class=" + chr(34) + cls + chr(34)) if cls else ""}>{esc(text(value))}</p>'


def notes(values):
    values = seq(values)
    return '<blockquote>' + ''.join(p(x) for x in values) + '</blockquote>' if values else ''


def items(values):
    return '<ul>' + ''.join('<li>' + esc(text(x)) + '</li>' for x in seq(values)) + '</ul>'


def link(url, label=None):
    url = str(url or '')
    try:
        parsed = urlparse(url)
        valid = parsed.scheme in ('http', 'https') and bool(parsed.netloc)
        valid &= not bool(re.match(r'https?://(?:chatgpt\.com/(?:c|s|share)/|grok\.com/(?:c|chat|share)/)', url))
    except ValueError:
        valid = False
    return f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(text(label or url))}</a>' if valid else esc(text(label or 'URL unavailable / private'))


def url_list(values):
    return '<ul class="source-list">' + ''.join('<li>' + link(x.get('url'), x.get('title') or x.get('label') or x.get('url')) + '</li>' if isinstance(x, dict) else '<li>' + link(x) + '</li>' for x in seq(values)) + '</ul>' if values else '<p class="pending">None recorded.</p>'


def plain_references(values):
    """Preserve textual source references without making them linked citations."""
    return '<ul class="source-list">' + ''.join('<li><span class="mono">' + esc(text(v)) + '</span></li>' for v in seq(values)) + '</ul>'


def distribution_record(audit, candidates):
    """Keep owned distribution, external coverage, indexes and leads distinct."""
    names = {c['id']: c['person'] for c in candidates}
    records = list(audit.get('distribution_evidence', []))
    for page in audit.get('selected_pages', []):
        for observation in seq(page.get('third_party_distribution')):
            if isinstance(observation, dict):
                records.append({'candidate_id': page.get('candidate_id'), 'related_selected_url': page.get('url'), **observation})
    labels = {
        'author_owned_distribution_on_external_platform': 'Author-owned distribution on an external platform',
        'third_party_index_of_first_party_research': 'External index of the authors’ own research',
        'unverified_search_lead': 'Unverified search lead · excluded',
    }
    # Explicit presentation labels for already reviewed sources, not a classifier.
    reviewed_labels = {
        'https://searchengineland.com/chatgpt-citations-content-study-469483': 'Third-party editorial coverage · a different work',
        'https://frankchiu.io/geo-course-recommendation/': 'External resource comparison',
        'https://www.womenintechseo.com/podcast/learning-seo/': 'Creator interview · related resource',
    }
    accepted, excluded, summary = [], [], {}
    seen = set()
    for row in records:
        key = (row.get('candidate_id'), row.get('url'))
        if key in seen:
            continue
        seen.add(key)
        classification = row.get('classification')
        label = labels.get(classification) or reviewed_labels.get(row.get('url')) or text(classification or 'External distribution observation · see evidence')
        limits = []
        if classification == 'author_owned_distribution_on_external_platform':
            limits.append('Self-distribution; not independent endorsement.')
        elif classification == 'third_party_index_of_first_party_research':
            limits.append('Indexing and an author abstract; not independent validation.')
        elif classification == 'unverified_search_lead':
            limits.append('Excluded from corroborated distribution evidence.')
        if row.get('exact_selected_page_citation_verified') is False:
            limits.append('A citation of a selected audit page was not verified.')
        if row.get('does_not_support'):
            limits.append(text(row['does_not_support']))
        if row.get('url') == 'https://www.womenintechseo.com/podcast/learning-seo/':
            limits.append('Related project coverage; not a verified citation of the selected AI-search subpage.')
        evidence = p(row.get('evidence', 'No bounded evidence description supplied.'))
        if row.get('underlying_original_url'):
            evidence += '<p>Related original: ' + link(row['underlying_original_url']) + '</p>'
        if row.get('access_status'):
            evidence += notes('Access: ' + text(row['access_status']))
        rendered = [esc(names.get(row.get('candidate_id'), row.get('candidate_id', 'Not assigned'))), esc(label), link(row.get('url')), evidence, items(limits) if limits else p('Distribution observed; reach, referral contribution and the mechanism of AI discovery were not measured.')]
        if classification == 'unverified_search_lead':
            excluded.append(rendered)
        else:
            accepted.append(rendered)
            summary.setdefault(row.get('candidate_id'), []).append(label)
    headers = ['Creator', 'Evidence classification', 'Observed URL', 'What the source supports', 'What it does not establish']
    body = notes('These are creator-level distribution observations, not extra holdout citations or independent verification of the research. Owned posts, external indexes, editorial coverage and unverified leads have different evidentiary roles.')
    body += table(headers, accepted, True) if accepted else p('No corroborated distribution observation recorded.')
    if excluded:
        body += '<h3>Excluded search lead</h3>' + table(headers, excluded, True)
    return body, summary


def supporting_context_record(audit, candidates):
    names = {c['id']: c['person'] for c in candidates}
    rows = []
    for row in audit.get('supporting_context', []):
        support = row.get('evidence') or row.get('access_status') or 'No additional content claim recorded.'
        limits = row.get('limitation') or 'Supporting context only; not an additional selected holdout-cited page or an independently validated causal explanation.'
        rows.append([esc(names.get(row.get('candidate_id'), row.get('candidate_id', 'Not assigned'))), link(row.get('url')), esc(text(row.get('role', 'Supporting context'))), esc(text(support)), esc(text(limits))])
    return notes('The following pages were followed during the audit for authorship, content organization or background. They remain separate from the ' + str(len(audit.get('selected_pages', []))) + ' selected own/bylined pages and do not increase the holdout citation counts.') + (table(['Creator', 'Context URL', 'Role', 'Observed evidence / access', 'Limit'], rows, True) if rows else p('No additional context page recorded.'))


def execution_record(protocol, attempts):
    """Display the registered order, actual order and local capture issues."""
    planned = protocol.get('design', {}).get('planned_order', [])
    actual = protocol.get('actual_order', [])
    by_id = {a.get('id'): a for a in attempts}
    rows = []
    for i in range(max(len(planned), len(actual))):
        intended = planned[i] if i < len(planned) else None
        observed = actual[i] if i < len(actual) else None
        rows.append([str(i + 1), esc(intended or 'No further planned position'),
                     esc(observed or 'Not yet submitted'),
                     esc(local_time(by_id.get(observed, {}).get('submitted_at'))) if observed else 'Not yet submitted',
                     'Matches plan' if intended == observed and observed else ('Different position' if observed else 'Pending')])
    order = table(['Sequence', 'Registered planned position', 'Actual submission', 'Actual submission time', 'Order status'], rows, True)
    order += notes(['The planned order remains unchanged. The actual sequence and submission times document execution; a different position is an order deviation, not a different prompt or a failed model answer. Pending positions are not negative discovery results.', *seq(protocol.get('execution_notes'))])
    incidents = protocol.get('capture_incidents', [])
    if incidents:
        incident_rows = []
        for i in incidents:
            # Exclude evidence-file paths and any service/account identifiers.
            incident_rows.append([esc(text(i.get('status'))), esc(text(i.get('new_submission'))),
                                  esc(text(i.get('summary'))), esc(text(i.get('effect_on_selected_body')))])
        recovery = table(['Local recovery status', 'New model submission?', 'What happened during capture', 'Effect on selected evidence'], incident_rows, True)
        recovery += notes('These are local collection or answer-association incidents. They are reported separately from model failures and do not add submissions when “New model submission?” is No. Original failure/recovery evidence is retained locally; the report exposes only the bounded incident summary.')
    else:
        recovery = p('No local capture incident is recorded in the protocol.')
    return '<h3>Registered plan versus actual submission order</h3>' + order + '<h3>Local capture incidents and recovery</h3>' + recovery


def table(headers, rows, wide=False):
    return '<div class="table-scroll"><table' + (' class="matrix"' if wide else '') + '><thead><tr>' + ''.join('<th scope="col">' + esc(h) + '</th>' for h in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + str(c) + '</td>' for c in row) + '</tr>' for row in rows) + '</tbody></table></div>'


def section(anchor, title, body):
    return f'<section id="{esc(anchor)}"><h2>{esc(title)}</h2>{body}</section>'


def detail(title, body, anchor=None):
    return '<details open' + (f' id="{esc(anchor)}"' if anchor else '') + '><summary>' + esc(title) + '</summary><div class="detail-body">' + body + '</div></details>'


def local_time(value):
    if not value:
        return 'Not recorded'
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S UTC+08:00')
    except (ValueError, TypeError):
        return text(value)


def complete(run):
    return run.get('body_complete') is True and run.get('status') == 'completed' and run.get('search_observed') is True and bool(run.get('answer_text', '').strip())


def coding_index(coding, runs):
    if isinstance(coding, dict):
        coding = coding.get('observations', coding.get('records', []))
    result = {}
    run_ids = {r['id'] for r in runs}
    for row in coding:
        key = (row['run_id'], row['candidate_id'])
        if key in result:
            raise ValueError(f'Duplicate coding row: {key}')
        if key[0] not in run_ids:
            raise ValueError(f'Coding refers to unknown planned slot: {key[0]}')
        for metric in (*METRICS, 'person_mention', 'person_recommendation'):
            if row.get(metric) is not None and type(row[metric]) is not bool:
                raise ValueError(f'{key}: {metric} must be boolean or null')
        result[key] = row
    return result


def metric_summary(runs, coded, candidate, metric):
    values = [coded.get((r['id'], candidate), {}).get(metric) if complete(r) else None for r in runs]
    known = sum(type(v) is bool for v in values)
    hits = sum(v is True for v in values)
    return {'hits': hits, 'known': known, 'planned': len(values), 'unknown': len(values) - known}


def count_label(s):
    if s['known'] == s['planned'] and s['planned']:
        return f"{s['hits']}/{s['planned']}"
    return f"{s['hits']} observed; {s['unknown']} unknown / {s['planned']} planned"


def metric_cell(runs, coded, candidate):
    return '<br>'.join('<strong>' + LABELS[m] + ':</strong> ' + esc(count_label(metric_summary(runs, coded, candidate, m))) for m in METRICS)


def candidate_urls(runs, coded, candidate, field):
    return list(dict.fromkeys(url for r in runs if complete(r) for url in seq(coded.get((r['id'], candidate), {}).get(field)) if isinstance(url, str)))


def source_url(row):
    return row.get('url') or row.get('href')


def source_rows(run):
    # answer_links is the body citation inventory; retrieval sources stay separate.
    return [r for r in run.get('answer_links', []) if isinstance(r, dict) and source_url(r)]


def keytable(rows):
    return '<dl class="keytable">' + ''.join('<dt>' + esc(k) + '</dt><dd>' + v + '</dd>' for k, v in rows) + '</dl>'


def shell(title, sections, body, appendix=False, public=False):
    other = ('report.html', 'Reader report') if appendix else ('technical-appendix.html', 'Complete technical appendix')
    nav = '<nav aria-label="Report contents"><strong>GEO Learning Log</strong><p>Lab #04 · Creator recommendations</p><div class="links">' + ''.join(f'<a href="#{esc(i)}">{esc(t)}</a>' for i, t in sections) + f'<a href="{other[0]}">{other[1]}</a></div><div class="experiment-series"><strong>Experiment series</strong>' + ''.join(link(u, label) for u, label in [('https://helen-bird.github.io/geo-platform-observation/', '#01 · AI recommendations'), ('https://helen-bird.github.io/geo-platform-observation/stages/02-post-discovery/', '#02 · Content discovery'), ('https://helen-bird.github.io/geo-platform-observation/stages/03-question-sensitivity/', '#03 · Prompt sensitivity')]) + '</div></nav>'
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + esc(title) + '</title><style>' + CSS + '</style></head><body class="' + ('appendix' if appendix else 'reader') + '"><a class="skip-link" href="#main">Skip to report</a><div class="layout">' + nav + '<main id="main"><h1>' + esc(title) + '</h1>' + body + '<p class="footer">GEO Lab #04 · ' + ('Redacted public learning record' if public else 'Local learning record') + ' · Descriptive, small-sample observations. No causal or long-term visibility claim.</p></main></div></body></html>'


def conditions(protocol, runs, config=None):
    config = config or {}
    rows = []
    controls = protocol.get('controls', {})
    for env, key in ((ENVIRONMENTS[0], 'openai_api'), (ENVIRONMENTS[1], 'grok')):
        c = controls.get(key, {})
        rs = [r for r in runs if r['platform'] == env]
        actual_models = list(dict.fromkeys(r.get('returned_model') or r.get('mode_label') or r.get('model_label') for r in rs if r.get('submitted_at')))
        times = [r.get('submitted_at') for r in rs if r.get('submitted_at')]
        rows.append([esc(env), esc(' / '.join(x for x in actual_models if x) or c.get('model') or c.get('mode') or 'Pending'), esc(c.get('reasoning_effort', 'Not independently selectable')), esc(c.get('search', 'Not recorded')), esc(f"{sum(r.get('search_observed') is True for r in rs)} observed / {len(rs)} planned"), esc(' to '.join([local_time(min(times)), local_time(max(times))]) if times else 'Pending')])
    api_runs = [r for r in runs if r['platform'] == ENVIRONMENTS[0]]
    reached = sum(r.get('tool_limit_reached') is True for r in api_runs)
    search = config.get('web_search', {})
    config_note = ('API fixed upper bounds: ' + text(config.get('max_tool_calls')) + ' built-in tool calls; '
                   + format(config['max_output_tokens'], ',') + ' generated output tokens. Search controls: tool_choice='
                   + text(config.get('tool_choice')) + '; live web access='
                   + str(search.get('external_web_access')).lower() + '; store='
                   + str(config.get('store')).lower() + '. '
                   + str(reached) + '/' + str(len(api_runs)) + ' selected API answers reached the tool-call cap.') if config else 'API execution-control configuration not recorded.'
    grok_runs = [r for r in runs if r['platform'] == ENVIRONMENTS[1]]
    off = bool(grok_runs) and all(r.get('personalize_using_x') is False and r.get('personalize_using_history') is False for r in grok_runs)
    restored = controls.get('grok', {}).get('settings_restored_to', {})
    restoration_verified = (controls.get('grok', {}).get('settings_restoration_pending') is False and restored.get('personalize_using_x') is True and restored.get('personalize_using_history') is True) or controls.get('grok', {}).get('restoration_completed') is True or protocol.get('restoration', {}).get('completed') is True
    personalization_note = ('Grok: both X and conversation-history personalization were OFF in all recorded runs.' if off else 'Grok test-personalization controls: see the per-run records.')
    personalization_note += (' Both were restored to their pre-test settings after collection.' if restoration_verified else ' Restoration to the original settings is not yet confirmed in this record.')
    minimum = protocol.get('design', {}).get('minimum_same_environment_submission_interval_seconds', 180)
    timing_checks = []
    for env in ENVIRONMENTS:
        times = sorted(datetime.fromisoformat(r['submitted_at'].replace('Z', '+00:00')) for r in runs if r['platform'] == env and r.get('submitted_at'))
        timing_checks.extend((b - a).total_seconds() >= minimum for a, b in zip(times, times[1:]))
    timing_note = (f'All recorded same-environment submission gaps meet the {minimum}-second minimum.' if timing_checks and all(timing_checks) else f'The registered minimum is {minimum} seconds between same-environment submissions; actual compliance is incomplete or not established.')
    timing_note += ' Gaps were often longer; this was not strict time balancing.'
    return table(['Environment', 'Model / visible mode', 'Reasoning', 'Search condition', 'Actual search evidence', 'Submission window'], rows) + notes(['OpenAI API + web search is not the consumer ChatGPT Search interface. Stage 1 used consumer ChatGPT Search; these records cannot isolate a longitudinal ChatGPT platform change.', config_note, personalization_note, timing_note, 'Grok’s Expert label does not reveal its exact backend model or provide a directly equivalent reasoning setting. Configured search and actual retrieval evidence are distinct.', 'Submission times use Asia/Shanghai (UTC+08:00). Exact prompts are unchanged; no candidate name or past answer is added.'])


def build(root, output):
    protocol = load(root, 'protocol.json', {})
    api_config = load(root, 'api-config.json', {})
    runs = load(root, 'runs.json', [])
    attempts = load(root, 'attempts.json', [])
    coding = load(root, 'coding.json', [])
    audit = load(root, 'audit/source-audit.json', {})
    editorial = load(root, 'findings-editorial.json', {})
    candidates = protocol.get('selection', {}).get('candidates', [])
    coded = coding_index(coding, runs)
    if len({r['id'] for r in runs}) != len(runs):
        raise ValueError('Duplicate planned slot IDs')
    planned = protocol.get('design', {}).get('planned_answers', 18)
    if len(runs) != planned:
        raise ValueError(f'Expected {planned} planned slots; found {len(runs)}. Missing positions must be retained as pending slots.')
    for env in ENVIRONMENTS:
        for q in QUESTIONS:
            if len([r for r in runs if r['platform'] == env and r['prompt_id'] == q]) != 3:
                raise ValueError(f'Expected exactly three planned repetitions for {env} / {q}.')
    valid_candidates = {c['id'] for c in candidates}
    if any(cid not in valid_candidates for _, cid in coded):
        raise ValueError('Coding refers to an unregistered candidate.')
    done = sum(complete(r) for r in runs)
    outstanding = max(0, planned - done)
    status = p(f'{done} complete selected answers / {planned} planned · {len(attempts)} recorded submissions · {outstanding} positions not yet complete.', 'status-line coverage')
    status += '<p><strong>OpenAI API + native web search · gpt-5.6-sol / medium versus Grok Expert · 3 November 2026</strong><br>The API condition does not represent consumer ChatGPT Search.</p>'
    if done < planned:
        status += notes('Collection or review is incomplete. Unknown positions are not coded as “not discovered”; summaries are provisional until all planned answers and judgments are available.')
    status += notes('This experiment describes whether three historically selected creators or their associated content assets appear in a new short-term sample. It does not establish why an AI recommends them, prove a GEO tactic works, or measure business conversions.')
    findings = editorial.get('findings', [])
    conclusion = '<ul class="conclusions">' + ''.join('<li><strong>' + esc(text(f.get('title', ''))) + '</strong> ' + esc(text(f.get('detail', ''))) + '</li>' for f in findings) + '</ul>' if findings else p('Findings are pending full-answer collection, observational coding and source review.', 'pending')
    conclusion += notes(editorial.get('limitations', []))

    definitions = notes(['C = answer-body hyperlink to confirmed own/bylined content; M = explicit person or verified associated-asset mention; R = active recommendation. These overlapping indicators are not mutually exclusive.', 'Person name M means the personal name appears. Person R means the person is actively recommended. Person-or-asset R includes either target; a resource-brand recommendation alone is not a personal recommendation.'])
    api_runs = [r for r in runs if r['platform'] == ENVIRONMENTS[0]]
    reached = sum(r.get('tool_limit_reached') is True for r in api_runs)
    comparison_limit = f'Comparison limit: {reached}/{len(api_runs)} API answers reached the fixed {api_config.get("max_tool_calls", 8)}-tool-call upper bound; all three were Q2 answers. Answers are complete, but retrieval may have been constrained. Interfaces and retrieval controls differ, so source-count differences cannot be assigned to model preference.'

    overview_rows = []
    by_question = []
    for q in QUESTIONS:
        rows = []
        for c in candidates:
            label = CANDIDATE_LABELS.get(c['id'], c['person'])
            overview = [esc(q), esc(label)]
            row = [esc(label)]
            for env in ENVIRONMENTS:
                rs = [r for r in runs if r['platform'] == env and r['prompt_id'] == q]
                overview.append(esc(count_label(metric_summary(rs, coded, c['id'], 'recommendation'))))
                row.append(metric_cell(rs, coded, c['id']))
                row.append('<strong>Person name M:</strong> ' + esc(count_label(metric_summary(rs, coded, c['id'], 'person_mention'))) + '<br><strong>Person R:</strong> ' + esc(count_label(metric_summary(rs, coded, c['id'], 'person_recommendation'))))
            overview_rows.append(overview)
            rows.append(row)
        q_limit = ('All three API Q2 answers reached the eight-call cap. This is a retrieval-budget and interface confound, not evidence that an environment intrinsically prefers or rejects these authors.' if q == 'Q2' else comparison_limit)
        interpretation = notes('Q2 requests credible experiments on effects of GEO tactics; Q1 and Q3 ask more broadly for resources or practical tutorials. No C/M/R for these three candidates in Q2 does not establish that they lack research ability.') if q == 'Q2' else ''
        by_question.append('<h3>' + esc(q + ' · ' + {'Q1': 'Free learning resources', 'Q2': 'Credible experiments', 'Q3': 'Practical creators'}[q]) + '</h3>' + notes(protocol.get('prompts', {}).get(q, 'Prompt unavailable')) + table(['Creator / associated assets', 'OpenAI API · C/M/R', 'OpenAI API · person only', 'Grok · C/M/R', 'Grok · person only'], rows, True) + notes(q_limit) + interpretation)
    question_overview = table(['Question', 'Creator / associated assets', 'OpenAI API · person-or-asset R', 'Grok · person-or-asset R'], overview_rows)
    question_overview += notes(['Each result uses three answers to the same original question in one environment. Q1, Q2 and Q3 represent different user needs and are not interchangeable measurements.', comparison_limit])
    by_question_html = question_overview + definitions + ''.join(by_question)
    by_question_html += notes('These small denominators are short-term observations, not long-term stability or a pure platform effect. All three candidates are displayed, including zeros and Aleyda’s API Q3 1/3 result.')

    identity_rows = []
    pooled = []
    for c in candidates:
        label = CANDIDATE_LABELS.get(c['id'], c['person'])
        row = [esc(label)]
        for env in ENVIRONMENTS:
            rs = [r for r in runs if r['platform'] == env]
            row.append(metric_cell(rs, coded, c['id']))
            identity_rows.append([esc(label), esc(env), esc(count_label(metric_summary(rs, coded, c['id'], 'recommendation'))), esc(count_label(metric_summary(rs, coded, c['id'], 'person_mention'))), esc(count_label(metric_summary(rs, coded, c['id'], 'person_recommendation')))])
        pooled.append(row)
    identity_html = p('A content brand can be recommended while its author remains unnamed. The GEO Lab received person-or-asset R in 5/9 Grok answers, but Artur’s name appeared in 2/9; the API recommended the site in 1/9 without naming him.')
    identity_html += table(['Creator / associated assets', 'Environment', 'Person-or-asset R', 'Person name M', 'Person R'], identity_rows)
    identity_html += notes(['The denominator of nine mixes three different user questions. Use the question-level results above for intent-specific comparisons.', comparison_limit])
    identity_html += p('For Helen Bird, future measurements should distinguish a helen-bird.github.io page citation, a GEO Lab content-brand recommendation, and an explicit Helen Bird name mention or recommendation. Clear and consistent author attribution is a candidate change to test; its effect is not established here.')

    pooled_html = table(['Creator / associated assets', 'OpenAI API · C/M/R', 'Grok · C/M/R'], pooled, True)
    pooled_html += notes(['Secondary pooled view: nine planned answers per environment across three different questions. It describes this prompt bank, not a general recommendation probability. Unknown authorship remains unknown C.', comparison_limit])
    chart = '<figure class="candidate-chart"><figcaption><strong>Secondary pooled person-or-asset recommendations.</strong> The question-level results above are primary. Bars use nine planned answers per environment; they do not count explicit personal recommendations alone.</figcaption>'
    for c in candidates:
        chart += '<div class="chart-group"><h3>' + esc(CANDIDATE_LABELS.get(c['id'], c['person'])) + '</h3>'
        for n, env in enumerate(ENVIRONMENTS):
            summary = metric_summary([r for r in runs if r['platform'] == env], coded, c['id'], 'recommendation')
            chart += '<div class="bar-row"><div class="chart-label"><span>' + esc(env) + '</span><span class="bar-value">' + esc(count_label(summary)) + '</span></div>'
            if summary['planned'] and summary['known'] == summary['planned']:
                chart += '<div class="bar-track" aria-hidden="true"><div class="bar-fill' + (' alternate' if n else '') + '" style="width:' + str(round(100 * summary['hits'] / summary['planned'], 4)) + '%"></div></div>'
            chart += '</div>'
        chart += '</div>'
    chart += '</figure>' + notes(comparison_limit)

    selected = audit.get('selected_pages', [])
    distribution_html, distribution_summary = distribution_record(audit, candidates)
    context_html = supporting_context_record(audit, candidates)
    comparison = []
    for c in candidates:
        pages = [a for a in selected if a.get('candidate_id') == c['id']]
        own = candidate_urls(runs, coded, c['id'], 'own_content_urls')
        third = candidate_urls(runs, coded, c['id'], 'third_party_urls')
        strategies = list(dict.fromkeys(text(a.get('content_strategy')) for a in pages if a.get('content_strategy')))
        reusable = list(dict.fromkeys(text(x) for a in pages for x in seq(a.get('reusable'))))
        channels = distribution_summary.get(c['id'], [])
        channel_summary = items(channels) + '<p><a href="#distribution">Read classifications and limits</a></p>' if channels else p('No corroborated distribution observation recorded.', 'pending')
        comparison.append([esc(c['person']), url_list(own), url_list(third), items(strategies) if strategies else p('Audit pending / no eligible page observed.', 'pending'), channel_summary, items(reusable) if reusable else p('Pending evidence review.', 'pending')])
    comparison_html = table(['Creator', 'Own/bylined pages actually cited', 'Third-party body sources about creator', 'Observed content approach', 'Distribution / context', 'Low-cost practices to test'], comparison, True)
    comparison_html += notes(['A page’s appearance in a retrieval list is not a body citation. The source audit prioritizes two to three distinct actual body-cited own/bylined pages per creator; fewer eligible pages are reported as a shortfall rather than replaced with presumed successes.', 'Any wider context page or distribution evidence is supporting audit material. It does not become a new holdout citation or prove which channel caused an AI recommendation.'])

    audit_html = notes(audit.get('access_method'))
    for a in selected:
        c = next((c for c in candidates if c['id'] == a.get('candidate_id')), {})
        audit_html += '<article class="source-audit"><h3>' + esc(c.get('person', a.get('candidate_id', 'Candidate'))) + ' · ' + link(a.get('url'), a.get('title') or a.get('url')) + '</h3>'
        audit_html += keytable([('Access / byline', esc(text(a.get('access_status'))) + '<br>' + esc(text(a.get('byline')))), ('Observed in new answers', esc(', '.join(seq(a.get('run_ids'))))), ('Why this page was selected', esc(text(a.get('selection_reason')))), ('Evidence and practical content', items(a.get('evidence'))), ('Content organization', esc(text(a.get('content_strategy'))) + url_list(a.get('internal_links'))), ('Low-cost reusable practices', items(a.get('reusable')))])
        audit_html += notes(seq(a.get('background_advantages')) + seq(a.get('limitations'))) + '</article>'
    if not selected:
        audit_html += p('Page selection and audit are pending. No creator is treated as a proven strategy case before actual source review.', 'pending')
    audit_html += notes(audit.get('shortfalls', [])) + notes(audit.get('notes', []))

    hypotheses = audit.get('review_hypotheses', audit.get('hypotheses', []))
    hyp_html = table(['Observable feature', 'Untested hypothesis', 'Practical next test', 'Evidence boundary'], [[esc(text(x.get('observable_feature', x.get('evidence')))), esc(text(x.get('hypothesis', x.get('practice')))), esc(text(x.get('next_test'))), esc(text(x.get('causal_status', 'Hypothesis; not established by this observational study.')))] for x in hypotheses]) if hypotheses else p('Candidate hypotheses are pending the source audit.', 'pending')
    hyp_html += notes('Reputation, existing audience, years of professional experience, paid data partnerships and distribution access are background advantages. Copying a visible page feature does not reproduce those advantages or establish a causal GEO mechanism.')

    history_rows = [[esc(c['person']), '<br>'.join(esc(k) + ': ' + esc(v) + '/2' for k, v in c.get('historical_recommendations', {}).items()), esc(c.get('historical_identity_note', 'Personal name and associated content assets were historically grouped; the new sample separates them.'))] for c in candidates]
    history = table(['Candidate', 'Stage 1 recommendation observations', 'Identity qualification'], history_rows) + notes([protocol.get('selection', {}).get('limitation', 'Historical selection is not new validation evidence.'), 'The candidates were selected using Stage 1. Only new answers contribute to Stage 4 counts; the old two-repeat observations are not reused as validation samples.'])
    count_rows = []
    for env in ENVIRONMENTS:
        ar = [a for a in attempts if a.get('platform') == env]
        rr = [r for r in runs if r['platform'] == env]
        count_rows.append([esc(env), str(len(rr)), str(len(ar)), str(sum(complete(r) for r in rr)), str(sum(a.get('status') != 'completed' for a in ar))])
    data_html = table(['Environment', 'Planned positions', 'Recorded submissions', 'Complete selected answers', 'Submissions not completed / reviewed'], count_rows) + p('All original submission records, including partial or failed attempts, remain in the local evidence set. No missing answer is silently replaced or treated as a negative discovery result.') + f'<p><a href="technical-appendix.html">Read full original answers, actual body URLs, observed search activity, coding evidence and failure records.</a></p>'
    api = protocol.get('api_collection', {})
    if api.get('estimated_spend_usd') is not None:
        data_html += notes('Estimated OpenAI API spend: US$' + format(api['estimated_spend_usd'], '.6f') + ' against the user-approved US$10 cap. This usage-priced estimate is not a reconciled provider invoice.')
    body = status + section('findings', 'Main findings', conclusion) + section('questions', 'Results by user question · primary comparison', by_question_html) + section('identity', 'Personal name and content brand are different outcomes', identity_html) + section('recommendations', 'All-question C/M/R · secondary summary', chart + pooled_html) + section('comparison', 'Three creator cases', comparison_html) + section('source-audit', 'What the actual pages show', audit_html) + section('distribution', 'Distribution evidence, with boundaries', distribution_html) + section('supporting-context', 'Supporting context, outside the holdout sample', context_html) + section('next-tests', 'Observable features → hypotheses to test', hyp_html) + section('historical-selection', 'Why these three candidates?', history) + section('conditions', 'Experiment conditions', conditions(protocol, runs, api_config)) + section('data', 'Data coverage and preserved attempts', data_html)
    sections = [('findings', 'Main findings'), ('questions', 'By user question · primary'), ('identity', 'Person and content brand'), ('recommendations', 'Pooled C/M/R · secondary'), ('comparison', 'Creator comparison'), ('source-audit', 'Source audit'), ('distribution', 'Distribution evidence'), ('supporting-context', 'Supporting context'), ('next-tests', 'Practices to test'), ('historical-selection', 'Historical selection'), ('conditions', 'Conditions'), ('data', 'Data and attempts')]

    # The appendix contains only explicitly allowed metadata, never raw response IDs,
    # account data, private conversation URLs, credential locations or full request dumps.
    app_sections = [('coverage', 'Coverage and limits'), ('prompts', 'Exact prompts'), ('answers', 'Original selected answers'), ('coding', 'Observation evidence'), ('attempts', 'All submissions'), ('execution', 'Order and capture recovery'), ('audit-context', 'Distribution and context'), ('rules', 'Coding and audit rules')]
    app = status + section('coverage', 'Coverage and limits', notes(protocol.get('limits', [])) + data_html + conditions(protocol, runs, api_config))
    app += section('prompts', 'Exact original prompts', ''.join(detail(q, '<pre>' + esc(protocol.get('prompts', {}).get(q, 'Not recorded')) + '</pre>') for q in QUESTIONS))
    all_answers = ''
    for r in runs:
        meta = [('Position', esc(r['id'])), ('Platform / interface', esc(text(r.get('platform'))) + '<br>' + esc(text(r.get('interface')))), ('Status / complete body', esc(text(r.get('status'))) + ' / ' + esc(text(r.get('body_complete')))), ('Submitted', esc(local_time(r.get('submitted_at')))), ('Captured', esc(local_time(r.get('captured_at')))), ('Requested model / returned model / visible mode', '<br>'.join(esc(text(r.get(k))) for k in ('requested_model', 'returned_model', 'mode_label', 'model_label'))), ('Reasoning effort', esc(text(r.get('reasoning_effort')))), ('Search configured / actual search observed', esc(text(r.get('search_enabled_api', r.get('search_enabled_ui')))) + ' / ' + esc(text(r.get('search_observed')))), ('Private / X personalization / history personalization', ' / '.join(esc(text(r.get(k))) for k in ('private', 'personalize_using_x', 'personalize_using_history')))]
        body_links = source_rows(r)
        urls = table(['Citation label', 'Actual body URL', 'Domain', 'Capture kind'], [[esc(x.get('title') or x.get('text') or x.get('label') or ''), link(source_url(x)), esc(urlparse(source_url(x)).netloc.lower()), esc(x.get('kind', 'Observable body link'))] for x in body_links]) if body_links else p('No body citation URL captured.' if complete(r) else 'Body source coverage pending.')
        activity = [dict((k, a.get(k)) for k in ('status', 'action') if k in a) for a in r.get('search_calls', [])]
        # Search source URLs and queries are task evidence; tool/response identifiers are omitted.
        activity_html = ''
        if activity:
            activity_html += '<h4>Returned API search operations</h4><pre>' + esc(text(activity)) + '</pre>'
        if r.get('search_activity_text'):
            activity_html += '<h4>Native search activity · verbatim capture</h4><pre>' + esc(text(r['search_activity_text'])) + '</pre>'
            activity_html += notes('Native activity is preserved in the interface’s original language. Search queries, visited pages and activity labels describe observable retrieval behavior; they are separate from answer-body citations.')
        if r.get('search_query_labels'):
            activity_html += '<h4>Recorded exact query labels</h4>' + items(r['search_query_labels'])
        if not activity_html:
            activity_html = p('No detailed search operation or native activity text recorded. See the separately recorded search-observed state and coverage note.')
        retrieval = r.get('retrieval_sources', [])
        retrieval_urls = list(dict.fromkeys(source_url(x) for x in retrieval if isinstance(x, dict) and source_url(x)))
        raw = '<h3>Original answer body</h3><pre class="transcript">' + esc(scrub_text(r.get('answer_text') or '[No complete answer captured.]')) + '</pre>'
        raw += '<h3>Answer-body citation inventory</h3>' + urls
        raw += notes([r.get('source_inventory_scope')] if r.get('source_inventory_scope') else [])
        raw += '<h3>Observed search activity</h3>' + activity_html + notes([r.get('search_evidence')] if r.get('search_evidence') else [])
        if retrieval_urls:
            raw += detail('Retrieval sources · not automatically body citations', url_list(retrieval_urls))
        raw += notes(seq(r.get('notes')) + seq(r.get('review_note')))
        if r.get('tool_limit_reached'):
            raw += notes('The response used the fixed maximum number of built-in tool calls. This execution limit is retained as an experimental condition.')
        all_answers += detail(r['id'] + ' · ' + str(r.get('status', 'pending')), keytable(meta) + raw, 'answer-' + r['id'])
    app += section('answers', 'Full selected answer records', all_answers)
    observation_html = ''
    for r in runs:
        rows = []
        for c in candidates:
            row = coded.get((r['id'], c['id']))
            if not complete(r) or row is None:
                rows.append([esc(CANDIDATE_LABELS.get(c['id'], c['person'])), 'Unknown', 'Unknown', 'Unknown', 'Unknown', 'Unknown', 'Not yet eligible for a completed observation.'])
                continue
            evidence = items(row.get('evidence')) + notes(row.get('note'))
            evidence += '<strong>Own/bylined body citations</strong>' + url_list(row.get('own_content_urls'))
            evidence += '<strong>Third-party body sources</strong>' + url_list(row.get('third_party_urls'))
            if row.get('textual_source_references'):
                evidence += '<strong>Plain-text source references · excluded from strict linked C</strong>' + plain_references(row['textual_source_references'])
                evidence += notes('These source addresses appeared as plain text rather than observable inline citation hyperlinks. They are preserved as textual-reference evidence and do not enter the strict linked Citation count.')
            evidence += '<strong>Retrieval only</strong>' + url_list(row.get('retrieval_only_urls'))
            evidence += notes('Asset mentions: ' + ', '.join(row.get('asset_mentions', [])) + '; asset recommendation targets: ' + ', '.join(row.get('asset_recommendations', [])) + '; explicit person recommendation: ' + text(row.get('person_recommendation')))
            rows.append([esc(CANDIDATE_LABELS.get(c['id'], c['person'])), esc(text(row.get('citation'))), esc(text(row.get('mention'))), esc(text(row.get('recommendation'))), esc(text(row.get('person_mention'))), esc(text(row.get('person_recommendation'))), evidence])
        observation_html += detail(r['id'], table(['Creator / associated assets', 'C', 'M', 'Person-or-asset R', 'Person name M', 'Person R', 'Observation and source evidence'], rows, True))
    app += section('coding', 'Candidate-level observational evidence', notes('These are assistant observational judgments. They are not independent human double coding or an external audit of every factual claim made by a test model.') + observation_html)
    attempt_rows = []
    for a in attempts:
        attempt_rows.append([esc(a.get('id', 'Not recorded')), esc(a.get('slot_id', 'Not recorded')), esc(a.get('platform', 'Not recorded')), esc(local_time(a.get('submitted_at'))), esc(a.get('status', 'Not recorded')), esc(text(a.get('body_complete'))), esc(text(a.get('search_observed'))), esc(text(a.get('error') or a.get('review_note') or a.get('notes') or 'No additional note.'))])
    app += section('attempts', 'Every recorded submission', table(['Attempt', 'Planned position', 'Environment', 'Submitted', 'Status', 'Complete body', 'Search observed', 'Failure / recovery / review note'], attempt_rows, True) + notes('A failed, incomplete or unreviewed submission is retained as such. Attempt count and complete selected-answer count are different quantities. Recovery of one existing answer is not a new prompt submission.'))
    app += section('execution', 'Execution order and local capture recovery', execution_record(protocol, attempts))
    app += section('audit-context', 'Distribution and supporting context', p('The reader report separates owned distribution, external indexing, editorial coverage and excluded leads, and lists the actual supporting-context URLs.') + '<p><a href="report.html#distribution">Read classified distribution evidence</a> · <a href="report.html#supporting-context">Read supporting context</a></p>')
    app += section('rules', 'Registered coding and audit rules', ''.join(detail(k.replace('_', ' ').capitalize(), notes(v)) for k, v in protocol.get('coding', {}).items()) + ''.join(detail('Source audit · ' + k.replace('_', ' '), notes(v)) for k, v in protocol.get('source_audit', {}).items()) + notes('Historical selection and the new validation sample are separate. The API environment differs from historical consumer ChatGPT Search, and no content intervention was performed.'))
    output.mkdir(parents=True, exist_ok=True)
    reader = output / 'report.html'
    appendix = output / 'technical-appendix.html'
    reader.write_text(shell('GEO Lab #04: Which creators and content brands get recommended?', sections, body, public=bool(protocol.get('public_edition'))))
    appendix.write_text(shell('GEO Lab #04: Complete evidence appendix', app_sections, app, True, public=bool(protocol.get('public_edition'))))
    return {'reader': str(reader), 'appendix': str(appendix), 'planned_answers': planned, 'complete_selected_answers': done, 'recorded_submissions': len(attempts), 'coding_rows': len(coded), 'audited_pages': len(selected)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.data_dir.resolve(), (args.output_dir or args.data_dir).resolve()), indent=2))
