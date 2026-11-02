#!/usr/bin/env python3
"""Build the redacted public Stage 3 page, findings, and data archive.

Usage: python3 scripts/build_stage3_report.py [--data-dir DIR]
Outputs: stages/03-question-sensitivity/{index.html,findings.json,public-data.zip}.

Semantic judgments come only from coding/*.json. Complete bodies and a matching
source-record digest are required. Missing/incomplete/uncoded answers never
become empty discovery sets. No network access or additional model queries.
"""
from __future__ import annotations

import argparse
import hashlib
import html
from itertools import combinations
import json
import os
import re
import zipfile
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / 'stages/03-question-sensitivity'
SITE_URL = 'https://helen-bird.github.io/geo-platform-observation/stages/03-question-sensitivity/'

OPENAI_PLATFORM = 'OpenAI API + web search'
PLATFORMS = (OPENAI_PLATFORM, 'Grok')
PROMPTS = ('M1', 'M2', 'V1', 'V2')
METRICS = {
    'recommended_tools': 'Recommended tools / services / surfaces',
    'mentioned_tools': 'Mentioned tools / services / surfaces',
    'cited_domains': 'Cited domains · mapping complete',
    'observed_cited_domains': 'Observed inline cited domains · coverage qualified',
    'source_categories': 'Observed cited-source categories · provisional',
}
CSS = '\n:root{--ink:#182b36;--muted:#5e717c;--line:#dce5e9;--bg:#f3f6f8;--paper:#fff;--accent:#176a76;--soft:#eaf4f4;--bad:#a94635}\n*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:20px}body{margin:0;color:var(--ink);background:var(--bg);font:15px/1.6 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{color:var(--accent);text-decoration-thickness:1px;text-underline-offset:3px;overflow-wrap:anywhere}.layout{display:grid;grid-template-columns:235px minmax(0,1fr);min-height:100vh}nav{position:sticky;top:0;height:100vh;overflow:auto;background:#17343d;color:#edf7f7;padding:30px 22px}nav strong{display:block;font-size:19px;line-height:1.3;margin:0 0 12px}nav p{font-size:12px;color:#bed4db}nav a{display:block;color:#e0eeee;text-decoration:none;padding:7px 0;font-size:14px}nav .sub{padding-left:12px;font-size:12px;color:#b7d3db}main{max-width:1450px;width:100%;padding:36px 4vw 72px;min-width:0}h1{font-size:clamp(27px,3vw,42px);line-height:1.17;letter-spacing:-.035em;margin:8px 0 18px}h2{font-size:23px;line-height:1.3;margin:0 0 20px}h3{font-size:18px;margin:25px 0 12px}h4{font-size:15px;margin:18px 0 8px}p{margin:10px 0}section,.hero{background:var(--paper);border:1px solid var(--line);border-radius:15px;margin-bottom:24px;padding:26px;min-width:0}.eyebrow{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--accent);font-weight:750}.lead{font-size:17px;max-width:950px}.conclusions{padding-left:23px;margin:16px 0}.conclusions li{padding:4px 0}.counts{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:24px 0 4px}.count{padding:15px;background:var(--bg);border-radius:10px}.count strong{display:block;font-size:28px;line-height:1.25}.count span{font-size:12px;color:var(--muted)}blockquote{border-left:3px solid #7bafb5;background:var(--soft);margin:17px 0;padding:11px 17px;font-size:14px;color:#385560}blockquote p:first-child{margin-top:0}blockquote p:last-child{margin-bottom:0}.muted{color:var(--muted);font-size:13px}.preserve{white-space:pre-wrap}.table-scroll{overflow-x:auto;border:1px solid var(--line);border-radius:9px}table{border-collapse:collapse;width:100%;font-size:13px;text-align:left}td,th{padding:11px 12px;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}thead th{background:#edf3f5;white-space:nowrap}tbody tr:last-child>*{border-bottom:0}.matrix{min-width:1050px}.matrix td{min-width:105px}.badge{display:inline-block;white-space:normal;line-height:1.3;font-size:11px;font-weight:700;padding:5px 7px;border-radius:5px;background:#eef1f3;color:#52656f}.badge.good{background:#def1e8;color:#226246}.badge.bad{background:#fae7e2;color:var(--bad)}.badge.neutral{background:#edf0f3;color:#52656f}.badge.muted{background:transparent;color:#829099}.run{background:var(--paper);border:1px solid var(--line);border-radius:12px;margin:16px 0;overflow:hidden}details{border:1px solid var(--line);border-radius:8px;margin:15px 0}summary{cursor:pointer;font-weight:700;padding:15px 17px;background:#f7fafb;line-height:1.45}summary .badge{margin-left:13px}.detail-body{padding:3px 18px 18px}pre{font:13px/1.65 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;margin:10px 0;padding:14px;background:#f4f7f8;border:1px solid #e5ecef;border-radius:7px;max-width:100%}.keytable{display:grid;grid-template-columns:minmax(160px,23%) minmax(0,1fr);font-size:13px;margin:14px 0}.keytable dt,.keytable dd{border-bottom:1px solid var(--line);padding:9px 11px;margin:0;overflow-wrap:anywhere}.keytable dt{font-weight:650;background:#f5f8f9}.keytable dd pre{margin:0}ul{padding-left:21px}.definitions{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.definition{background:var(--bg);border-radius:9px;padding:14px}.definition strong{display:block}.definition p{font-size:13px;margin-bottom:0}.footer{font-size:12px;color:var(--muted)}\n@media(max-width:950px){.layout{grid-template-columns:190px minmax(0,1fr)}nav{padding:25px 17px}main{padding:24px}section,.hero{padding:20px}.counts{grid-template-columns:repeat(2,1fr)}.definitions{grid-template-columns:1fr}.keytable{grid-template-columns:145px minmax(0,1fr)}}\n@media(max-width:650px){.layout{display:block}nav{position:static;height:auto;padding:16px 20px}nav strong{margin-bottom:6px}nav p{margin:5px 0}nav .links{display:flex;flex-wrap:wrap;gap:2px 17px}nav a{font-size:12px;padding:3px 0}nav .sub{display:none}main{padding:18px 12px 45px}section,.hero{padding:18px 15px;border-radius:11px}h1{font-size:30px}h2{font-size:22px}.lead{font-size:15px}.keytable{grid-template-columns:1fr}.keytable dt{border-bottom:0;padding-bottom:3px}.keytable dd{padding-top:3px}.detail-body{padding:2px 12px 14px}summary{padding:12px}.run summary .badge{margin-top:6px;margin-left:0;display:table}pre{font-size:12px;padding:11px}}\n@media print{nav{display:none}.layout{display:block}main{max-width:none;padding:0}body{background:#fff}section,.hero,.run{break-inside:avoid;border-color:#bbb}a{color:inherit}summary{list-style:none}.table-scroll{overflow:visible}.matrix{min-width:0}table{font-size:9px}td,th{padding:5px}.counts{grid-template-columns:repeat(4,1fr)}}\n'


def esc(value):
    encoded = html.escape(str(value), quote=True)
    # Preserve transcript whitespace in rendered text without trailing source spaces.
    return re.sub(r'[ \t]+(?=\n|$)', lambda m: ''.join('&#32;' if c == ' ' else '&#9;' for c in m.group()), encoded)


def show(value):
    if value is None:
        return 'Unknown / not recorded'
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    return json.dumps(value, ensure_ascii=False, indent=2) if isinstance(value, (dict, list)) else str(value)


def pre(value):
    return '<pre>' + esc(show(value)) + '</pre>'


def notes(value):
    if not value:
        return ''
    values = value if isinstance(value, list) else [value]
    return '<blockquote>' + ''.join('<p class="preserve">' + esc(show(v)) + '</p>' for v in values) + '</blockquote>'


def table(headers, rows):
    return '<div class="table-scroll"><table><thead><tr>' + ''.join('<th>' + esc(h) + '</th>' for h in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + str(cell) + '</td>' for cell in row) + '</tr>' for row in rows) + '</tbody></table></div>'


def detail(title, body, anchor=None):
    return f'<details open{(" id=" + chr(34) + esc(anchor) + chr(34)) if anchor else ""}><summary>{esc(title)}</summary><div class="detail-body">{body}</div></details>'


def http_link(url, label=None):
    try:
        parsed = urlparse(str(url))
        valid = parsed.scheme.lower() in ('http', 'https') and bool(parsed.netloc)
    except ValueError:
        valid = False
    return f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(label or url)}</a>' if valid else esc(label or url or 'No URL')


def public_path(path):
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        raise ValueError('A file reference leaves the public repository.') from None
    return resolved


def local_link(path, root, label=None):
    if not path:
        return 'Not recorded'
    value = str(path)
    if Path(value).is_absolute():
        raise ValueError('Public references must use repository-relative paths.')
    target = public_path(STAGE / value if value in {'index.html','findings.json','public-data.zip'} else root / value)
    href = quote(os.path.relpath(target, STAGE).replace(os.sep, '/'), safe='/.-_')
    missing = ' <span class="muted">(missing public file)</span>' if not target.is_file() and value not in {'index.html','findings.json','public-data.zip'} else ''
    return f'<a href="{esc(href)}">{esc(label or path)}</a>{missing}'


def time_text(value, zone='Asia/Shanghai'):
    if not value:
        return 'Not recorded'
    try:
        when = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if when.tzinfo is None:
            return str(value) + ' (zone not recorded)'
        return when.astimezone(ZoneInfo(zone)).strftime('%Y-%m-%d %H:%M:%S %z')
    except (ValueError, KeyError):
        return str(value)


def read_json(path, issues, default=None):
    try:
        return json.loads(public_path(path).read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        issues.append(f'{path.name}: {error}')
        return default


def digest(path):
    return hashlib.sha256(public_path(path).read_bytes()).hexdigest()


def complete(record):
    return (record.get('status') in ('completed', 'recovered') and record.get('body_complete') is True
            and isinstance(record.get('answer_text'), str) and bool(record['answer_text'].strip()))


def first_present(record, *keys):
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    return None


def api_metadata(record):
    estimate = first_present(record, 'estimated_cost', 'cost_estimate')
    cost_value = first_present(record, 'cost_estimate_usd', 'estimated_cost_usd')
    if cost_value is None and isinstance(estimate, dict):
        cost_value = estimate.get('estimated_usd')
    return {
        'interface': record.get('interface'),
        'configured_model_label': record.get('model_label'),
        'requested_model': first_present(record, 'requested_model', 'model_requested', 'request_model'),
        'returned_model': first_present(record, 'returned_model', 'model_returned', 'response_model'),
        'reasoning_effort': first_present(record, 'reasoning_effort', 'reasoning'),
        'returned_reasoning': record.get('returned_reasoning'),
        'search_enabled_api': first_present(record, 'search_enabled_api', 'web_search_enabled'),
        'search_observed': record.get('search_observed'),
        'token_usage': first_present(record, 'usage', 'token_usage'),
        'tool_usage': record.get('tool_usage'),
        'transport_body_complete': record.get('transport_body_complete'),
        'cost_estimate_usd': cost_value,
        'cost_estimate_detail': estimate,
        'cost_estimate_basis': first_present(record, 'cost_estimate_basis', 'pricing_basis'),
    }


def model_summary(record):
    if record.get('platform') == OPENAI_PLATFORM:
        meta = api_metadata(record)
        return ('Configured: ' + show(meta['configured_model_label']) + '; requested: ' + show(meta['requested_model']) + '; returned: ' + show(meta['returned_model'])
                + '; effort: ' + show(meta['reasoning_effort']))
    return '; '.join(show(record.get(key)) for key in ('model_label','mode_label','reasoning_effort'))


def search_enabled(record):
    return api_metadata(record)['search_enabled_api'] if record.get('platform') == OPENAI_PLATFORM else record.get('search_enabled_ui')


def slots():
    # CHATGPT remains a stable historical position prefix, not the API condition's identity.
    return [(f'S3-{"CHATGPT" if p == OPENAI_PLATFORM else "GROK"}-{q}-R{r}', p, q, r)
            for q in PROMPTS for p in PLATFORMS for r in range(1, 4)]


def load(root):
    issues, hashes = [], {}
    protocol = read_json(root / 'protocol.json', issues, {})
    config_path = root / 'api-config.json'
    if config_path.is_file():
        config = read_json(config_path, issues, {})
        allowed = ('provider','platform','interface','model','reasoning_effort','budget_usd',
                   'pre_request_budget_reserve_usd','maximum_submissions','minimum_submission_interval_seconds',
                   'max_output_tokens','max_tool_calls','timeout_seconds','store','tool_choice','web_search',
                   'include','pricing','budget_notes','condition_notes')
        protocol['_report_api_config'] = {key:config[key] for key in allowed if key in config}
        hashes['api-config.json'] = digest(config_path)
    setup_path = root / 'setup-history.json'
    setup_history = read_json(setup_path, issues, []) if setup_path.is_file() else []
    if isinstance(setup_history, dict):
        setup_history = setup_history.get('events', setup_history.get('entries', []))
    protocol['_report_setup_history'] = [{**entry, 'file': 'setup-history.json'} for entry in setup_history if isinstance(entry, dict)]
    for name in ('setup-history.json','settings-summary.json','publication-notes.json'):
        if (root / name).is_file():
            hashes[name] = digest(root / name)
    protocol['_report_settings_summary'] = read_json(root / 'settings-summary.json', issues, {}) if (root / 'settings-summary.json').is_file() else {}
    protocol['_report_publication_notes'] = read_json(root / 'publication-notes.json', issues, {}) if (root / 'publication-notes.json').is_file() else {}
    raw_runs = read_json(root / 'runs.json', issues, [])
    attempts = read_json(root / 'attempts.json', issues, [])
    if isinstance(raw_runs, dict):
        raw_runs = raw_runs.get('runs', [])
    if isinstance(attempts, dict):
        attempts = attempts.get('attempts', [])
    if not isinstance(raw_runs, list) or not isinstance(attempts, list):
        raise ValueError('runs.json and attempts.json must contain arrays.')
    unique_attempts = {}
    for item in attempts:
        if item.get('id') in unique_attempts:
            issues.append('Duplicate actual attempt ID: ' + str(item.get('id')))
        unique_attempts[item['id']] = item
    attempts = list(unique_attempts.values())
    selected = {item.get('slot_id') or item['id']: item for item in raw_runs}
    if len(selected) != len(raw_runs):
        issues.append('Duplicate selected plan position; last record retained.')
    coding = {}
    for path in sorted((root / 'coding').glob('*.json')):
        item = read_json(path, issues, {})
        if item.get('id'):
            coding[item['id']] = {**item, '_file': str(path.relative_to(root))}
        hashes[str(path.relative_to(root))] = digest(path)
    runs = []
    for sid, platform, prompt_id, repeat in slots():
        main = selected.get(sid, {})
        attempt_id = main.get('selected_attempt_id')
        attempt = unique_attempts.get(attempt_id, {})
        raw_path = main.get('raw_file') or attempt.get('raw_file')
        raw = read_json(root / raw_path, issues, {}) if raw_path else {}
        record = {**raw, **attempt, **main, 'id': sid, 'platform': platform, 'prompt_id': prompt_id, 'repeat': repeat}
        record['_observed_attempt_platform'] = attempt.get('platform') or raw.get('platform')
        record['_condition_mismatch'] = bool(attempt_id and record['_observed_attempt_platform'] != platform)
        if record['_condition_mismatch']:
            issues.append(f'{sid}: selected attempt belongs to {record["_observed_attempt_platform"]!r}, not the current {platform!r} condition; excluded from analysis.')
        record.setdefault('status', 'not_started')
        record['_coding'] = coding.get(attempt_id, {}) if attempt_id else {}
        record['_raw'] = raw
        record['_raw_file'] = raw_path
        record['_planned_prompt'] = not bool(record.get('prompt'))
        record.setdefault('prompt', protocol.get('prompts', {}).get(prompt_id, ''))
        record['_prompt_mismatch'] = bool(attempt_id and record.get('prompt') != protocol.get('prompts', {}).get(prompt_id))
        if record['_prompt_mismatch']:
            issues.append(f'{sid}: submitted prompt differs from the registered prompt.')
        if attempt_id and attempt_id not in unique_attempts:
            issues.append(f'{sid}: selected attempt is absent from attempts.json.')
        if raw_path and (root / raw_path).is_file():
            hashes[raw_path] = digest(root / raw_path)
        runs.append(record)
    for name in ('protocol.json', 'runs.json', 'attempts.json', 'analysis-plan.md'):
        if (root / name).is_file():
            hashes[name] = digest(root / name)
    return protocol, runs, attempts, issues, hashes


def eligible_sets(record, root, issues):
    code = record['_coding']
    reasons = []
    if not complete(record):
        reasons.append('Selected body is not complete.')
    if record.get('_prompt_mismatch'):
        reasons.append('Prompt differs from the registered variant.')
    if record.get('_condition_mismatch'):
        reasons.append('Selected attempt belongs to a historical or different interface condition.')
    if not code:
        reasons.append('No manual coding for this selected attempt.')
    hash_match = None
    if code:
        if code.get('coding_complete') is False or code.get('coding_status') in ('partial','pending','incomplete','unreviewed'):
            reasons.append('Coding is explicitly marked incomplete or unreviewed.')
        source = root / str(code.get('source_record', ''))
        expected = code.get('source_record_sha256')
        hash_match = bool(source.is_file() and expected and digest(source) == expected)
        if not hash_match:
            reasons.append('Coding source digest missing or mismatched; review required.')
        if code.get('capture_scope', {}).get('body_complete') is not True:
            reasons.append('Coding does not confirm complete body coverage.')
        if record.get('answer_text') != record.get('_raw', {}).get('answer_text'):
            reasons.append('Selected body differs from the public body reviewed by coding.')
        if str(code.get('source_record')) != str(record.get('_raw_file')):
            reasons.append('Coding points to a different public record.')
    result = {'body_complete': complete(record), 'platform': record.get('platform'),
              'selected_attempt_id': record.get('selected_attempt_id'), 'observed_attempt_platform': record.get('_observed_attempt_platform'),
              'api_metadata': api_metadata(record) if record.get('platform') == OPENAI_PLATFORM else None,
              'coding_present': bool(code), 'coding_source_hash_match': hash_match,
              'coding_eligible': not reasons, 'exclusion_reasons': reasons, 'sets': {}, 'metric_reasons': {}, 'domain_mapping': []}
    for metric in METRICS:
        result['sets'][metric] = None
    if reasons:
        return result
    entities = code.get('entity_observations')
    for metric, field in (('recommended_tools', 'recommendation'), ('mentioned_tools', 'mention')):
        if not isinstance(entities, list) or any(e.get(field) is not True and e.get(field) is not False for e in entities):
            result['metric_reasons'][metric] = 'Tool inventory or one or more judgments unresolved; no exhaustive set assigned.'
            continue
        result['sets'][metric] = sorted({e['entity'] for e in entities if e.get(field) is True
            and not e.get('supplied_in_prompt') and not e.get('excluded_from_default_overlap')})
        recorded_summary = code.get('summary', {}).get('default_recommended_tools' if field == 'recommendation' else 'default_mentioned_tools')
        if isinstance(recorded_summary, list) and set(recorded_summary) != set(result['sets'][metric]):
            issues.append(f'{record["id"]}: derived {metric} differs from coding summary; entity-level judgments used.')
    sources = code.get('answer_sources')
    if not isinstance(sources, list):
        result['metric_reasons']['observed_cited_domains'] = 'No scoped answer-source inventory in coding.'
        return result
    mapping = code.get('registrable_domain_mapping', {}).get('mapping', {})
    domains, valid = set(), True
    raw_urls = {s.get('url') for s in record.get('answer_links', []) if isinstance(s, dict)}
    coded_urls = {s.get('url') for s in sources if isinstance(s, dict)}
    if raw_urls - coded_urls:
        valid = False
        issues.append(f'{record["id"]}: recorded inline URLs are absent from source coding; domain/category sets withheld pending review.')
    for source in sources:
        url = source.get('url', '')
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or '').lower().rstrip('.')
        except ValueError:
            host = ''
        if url not in raw_urls:
            valid = False
            issues.append(f'{record["id"]}: coded answer source is not in the recorded inline URL inventory: {url}')
        normalized = mapping.get(host)
        method = 'Manual mapping recorded in coding'
        if normalized is None and host.startswith('www.'):
            normalized = mapping.get(host[4:], host[4:])
            method = 'Leading www removed; remaining exact hostname retained unless manually mapped'
        if normalized is None and host:
            normalized = host
            method = 'Exact hostname retained; registrable-domain boundary unresolved'
        if not host:
            valid = False
        if normalized:
            domains.add(normalized)
        result['domain_mapping'].append({'url': url, 'observed_target': source.get('observed_target'), 'hostname': host,
            'normalized_domain': normalized, 'method': method, 'provenance': source.get('provenance'),
            'source_category': source.get('source_category'), 'classification_status': source.get('classification_status')})
    if valid:
        result['sets']['observed_cited_domains'] = sorted(domains)
        if code.get('capture_scope', {}).get('citation_mapping_complete') is True:
            result['sets']['cited_domains'] = sorted(domains)
        else:
            result['metric_reasons']['cited_domains'] = 'Citation mapping is not confirmed complete; use separately labeled observed-link comparisons.'
        categories = set()
        for source in sources:
            categories.add(source.get('source_category') or 'Other / unresolved')
            for category in source.get('secondary_categories', []) or []:
                categories.add(category)
        result['sets']['source_categories'] = sorted(categories)
    else:
        result['metric_reasons']['observed_cited_domains'] = 'One or more coded URLs cannot be matched to the actual inline inventory.'
    result['citation_mapping_complete'] = code.get('capture_scope', {}).get('citation_mapping_complete')
    result['source_badge_hits'] = code.get('capture_scope', {}).get('source_badge_hits', record.get('source_panel_declared_hits'))
    result['observed_inline_URL_occurrences'] = len(record.get('answer_links', []))
    result['unique_observed_inline_URLs'] = len(raw_urls)
    return result


def overlap(left, right):
    if left is None or right is None:
        return {'value': None, 'reason': 'Unavailable: one or both sets are ineligible or unrecorded.'}
    left, right = set(left), set(right)
    union, intersection = left | right, left & right
    if not union:
        return {'value': None, 'reason': 'N/A: both eligible sets are empty.', 'intersection': 0, 'union': 0, 'shared': [], 'left_size': 0, 'right_size': 0}
    return {'value': len(intersection) / len(union), 'intersection': len(intersection), 'union': len(union),
            'shared': sorted(intersection), 'left_size': len(left), 'right_size': len(right)}


def pair_summary(pairs):
    values = [pair['value'] for pair in pairs if pair.get('value') is not None]
    return {'available_numeric_pairs': len(values), 'mean': sum(values) / len(values) if values else None,
            'minimum': min(values) if values else None, 'maximum': max(values) if values else None,
            'both_empty_pairs': sum(p.get('union')==0 and p.get('value') is None for p in pairs),
            'unavailable_pairs': sum(p.get('value') is None and p.get('union') != 0 for p in pairs)}


def api_cost_summary(attempts):
    api=[record for record in attempts if record.get('platform')==OPENAI_PLATFORM]
    estimates=[];billable=[]
    for record in api:
        value=api_metadata(record)['cost_estimate_usd']
        if value is not None:
            try:
                number=Decimal(str(value))
                if number.is_finite() and number>=0:
                    estimates.append(number)
            except InvalidOperation:
                pass
        count=record.get('tool_usage',{}).get('web_search',{}).get('num_requests')
        if isinstance(count,int) and not isinstance(count,bool):
            billable.append(count)
    return {'api_attempts':len(api),'estimates_available':len(estimates),'missing_estimates':len(api)-len(estimates),
        'known_estimate_sum_usd':str(sum(estimates,Decimal('0'))) if estimates else None,
        'all_attempt_estimates_available':bool(api) and len(estimates)==len(api),
        'billing_reconciled':bool(api) and all((first_present(r,'estimated_cost','cost_estimate') or {}).get('billing_reconciled') is True for r in api),
        'reported_billable_searches':sum(billable) if billable else None,'billable_search_count_coverage':len(billable),
        'answer_url_citation_occurrences':sum(len(r.get('answer_links',[])) for r in api) if api else None,
        'citation_occurrence_rule':'Count each recorded url_citation annotation once; corresponding Markdown representations are not added again.'}


def chronology(attempts):
    periods={};parsed={}
    for platform in PLATFORMS:
        times=[]
        for record in attempts:
            if record.get('platform')!=platform or not record.get('submitted_at'):
                continue
            try:
                when=datetime.fromisoformat(record['submitted_at'].replace('Z','+00:00'))
                if when.tzinfo is not None:
                    times.append(when)
            except ValueError:
                pass
        times.sort();parsed[platform]=times
        periods[platform]={'timestamped_submissions':len(times),'first_submission':times[0].isoformat() if times else None,
            'last_submission':times[-1].isoformat() if times else None,
            'minimum_same_platform_interval_seconds':min((b-a).total_seconds() for a,b in zip(times,times[1:])) if len(times)>1 else None}
    left,right=parsed[OPENAI_PLATFORM],parsed['Grok']
    return {'platform_periods':periods,'all_recorded_API_after_Grok':min(left)>max(right) if left and right else None,
            'interpretation':'Collection order and elapsed time are confounded with interface/platform; not a causal platform effect.'}


def platform_summaries(runs,analyzed):
    summaries=[]
    for platform in PLATFORMS:
        group=[r for r in runs if r['platform']==platform]
        coded=[r for r in group if analyzed[r['id']]['coding_eligible']]
        rows=[entity for r in coded for entity in r['_coding'].get('entity_observations',[])
              if not entity.get('supplied_in_prompt') and not entity.get('excluded_from_default_overlap')]
        cmr={field:{'true':sum(e.get(field) is True for e in rows),'false':sum(e.get(field) is False for e in rows),
                   'unresolved':sum(e.get(field) is not True and e.get(field) is not False for e in rows),
                   'known_denominator':sum(isinstance(e.get(field),bool) for e in rows)} for field in ('citation','mention','recommendation')}
        combos={label:0 for label in ('None','C','M','R','CM','CR','MR','CMR','Unresolved')}
        for entity in rows:
            values=[entity.get(key) for key in ('citation','mention','recommendation')]
            label='Unresolved' if any(not isinstance(v,bool) for v in values) else ''.join(letter for letter,value in zip('CMR',values) if value) or 'None'
            combos[label]+=1
        rec=group_stats(group,'recommended_tools',analyzed)
        category_group=[r for r in group if analyzed[r['id']]['sets']['source_categories'] is not None]
        primary_sets=[{s.get('source_category') or 'Other / unresolved' for s in r['_coding'].get('answer_sources',[])} for r in category_group]
        categories=sorted(set().union(*primary_sets)) if primary_sets else []
        summaries.append({'platform':platform,'eligible_coded_answers':len(coded),'entity_answer_rows':len(rows),'cmr':cmr,'cmr_combinations':combos,
            'entity_scope':'Tool/service/feature/channel entity × answer rows; excludes supplied target platforms, generic methods and citation-only source publishers. C is own-content Citation, not every cited source.',
            'recommended_tool_inventory':rec,'empty_recommendation_sets':sum(analyzed[r['id']]['sets']['recommended_tools']==[] for r in group),
            'nonempty_recommendation_sets':sum(bool(analyzed[r['id']]['sets']['recommended_tools']) for r in group),
            'primary_source_category_prevalence':{category:{'numerator':sum(category in s for s in primary_sets),'denominator':len(primary_sets)} for category in categories},
            'source_category_prevalence_observed':group_stats(group,'source_categories',analyzed),
            'source_category_scope':'Per-answer prevalence in observed inline cited-source inventories; classifications provisional, candidate categories excluded. Not a complete retrieval-source inventory.'})
    return summaries


def group_stats(group, metric, analyzed):
    eligible = [r for r in group if analyzed[r['id']]['sets'][metric] is not None]
    sets = [set(analyzed[r['id']]['sets'][metric]) for r in eligible]
    union = set().union(*sets) if sets else None
    return {'eligible_denominator': len(eligible), 'planned_positions': len(group), 'eligible_ids': [r['id'] for r in eligible],
            'union': sorted(union) if union is not None else None,
            'prevalence': {entity: {'numerator': sum(entity in one for one in sets), 'denominator': len(sets)} for entity in sorted(union or [])}}


def analyze(protocol, runs, attempts, root, issues, hashes):
    analyzed = {r['id']: eligible_sets(r, root, issues) for r in runs}
    cells = []
    for prompt_id in PROMPTS:
        for platform in PLATFORMS:
            group = [r for r in runs if r['platform'] == platform and r['prompt_id'] == prompt_id]
            cell = {'platform': platform, 'prompt_id': prompt_id, 'metrics': {}, 'complete_bodies': sum(complete(r) for r in group),
                    'coded_eligible': sum(analyzed[r['id']]['coding_eligible'] for r in group)}
            for metric in METRICS:
                pairs = []
                for left, right in combinations(group, 2):
                    pairs.append({'left': left['id'], 'right': right['id'], **overlap(analyzed[left['id']]['sets'][metric], analyzed[right['id']]['sets'][metric])})
                stats = group_stats(group, metric, analyzed)
                stats.update(pairs=pairs, pair_summary=pair_summary(pairs),
                    shared_across_all_three=sorted(set.intersection(*(set(analyzed[r['id']]['sets'][metric]) for r in group))) if stats['eligible_denominator'] == 3 else None)
                cell['metrics'][metric] = stats
            reviewed = [r for r in group if analyzed[r['id']]['coding_eligible']]
            types = {}
            for r in reviewed:
                kind = r['_coding'].get('answer_type', {}).get('primary')
                if kind:
                    types[kind] = types.get(kind, 0) + 1
            cell['answer_types'] = {'counts': types, 'denominator': sum(types.values())}
            complete_group = [r for r in group if complete(r)]
            cell['search_observed'] = {'yes': sum(r.get('search_observed') is True for r in complete_group),
                'no': sum(r.get('search_observed') is False for r in complete_group),
                'unknown': sum(r.get('search_observed') is None for r in complete_group), 'complete_body_denominator': len(complete_group)}
            cells.append(cell)
    contrasts = []
    for platform in PLATFORMS:
        for intent in ('M', 'V'):
            left = next(c for c in cells if c['platform'] == platform and c['prompt_id'] == intent+'1')
            right = next(c for c in cells if c['platform'] == platform and c['prompt_id'] == intent+'2')
            contrasts.append({'platform': platform, 'intent': intent, 'metrics': {metric: {
                'left': left['metrics'][metric], 'right': right['metrics'][metric],
                'union_overlap': overlap(left['metrics'][metric]['union'], right['metrics'][metric]['union'])} for metric in METRICS}})
    intents = []
    for platform in PLATFORMS:
        item = {'platform': platform, 'metrics': {}}
        for metric in METRICS:
            grouped = {key: group_stats([r for r in runs if r['platform'] == platform and (r['prompt_id'] == key if len(key) == 2 else r['prompt_id'].startswith(key))], metric, analyzed) for key in ('M1','M2','M','V1','V2','V')}
            grouped['pooled_overlap'] = overlap(grouped['M']['union'], grouped['V']['union'])
            item['metrics'][metric] = grouped
        intents.append(item)
    flags = {}
    flag_names = sorted({name for r in runs if analyzed[r['id']]['coding_eligible'] for name in r['_coding'].get('content_flags', {})})
    for flag in flag_names:
        flags[flag] = {}
        for cell in cells:
            values = [r['_coding'].get('content_flags', {}).get(flag, {}).get('value') for r in runs
                      if r['platform'] == cell['platform'] and r['prompt_id'] == cell['prompt_id'] and analyzed[r['id']]['coding_eligible']]
            flags[flag][cell['platform']+' / '+cell['prompt_id']] = {'numerator': sum(v is True for v in values), 'denominator': sum(v is True or v is False for v in values), 'unknown': sum(v is not True and v is not False for v in values)}
    return {'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'schema_version': 2,
        'scope': 'Descriptive partial observation; assistant semantic coding, no independent human double-coding or external fact-check.',
        'conditions': {'main_platforms': list(PLATFORMS), 'historical_slot_prefix': 'S3-CHATGPT-* position IDs are retained for continuity; current OpenAI attempts use the API condition.',
            'comparison_limit': 'OpenAI Responses API with web_search versus the Grok consumer interface. This is not a consumer ChatGPT Search comparison. Interface, collection timing and execution-path differences confound platform contrasts.',
            'model_identity_limit':'Requested and returned gpt-5.6-sol is an undated identifier. The actual backend/snapshot is not independently established; a fixed ID and medium effort do not prove a fixed backend or equivalence to consumer ChatGPT Search.'},
        'api_attempt_metadata': [{'id': r['id'], **api_metadata(r)} for r in attempts if r.get('platform') == OPENAI_PLATFORM],
        'api_cost_summary':api_cost_summary(attempts),'collection_chronology':chronology(attempts),
        'setup_history':protocol.get('_report_setup_history',[]),'platform_summaries':platform_summaries(runs,analyzed),
        'counts': {'planned_cells': 8, 'planned_response_positions': 24, 'actual_submissions': len(attempts),
            'api_submissions': sum(r.get('platform') == OPENAI_PLATFORM for r in attempts),
            'grok_consumer_submissions': sum(r.get('platform') == 'Grok' for r in attempts),
            'historical_chatgpt_ui_submissions': sum(r.get('platform') == 'ChatGPT Search' for r in attempts),
            'complete_selected_bodies': sum(complete(r) for r in runs), 'eligible_coded_bodies': sum(a['coding_eligible'] for a in analyzed.values()),
            'technical_failure_attempts': sum(r.get('status') == 'technical_failure' for r in attempts),
            'incomplete_capture_attempts': sum(r.get('status') in ('capture_incomplete','incomplete') for r in attempts)},
        'per_answer': analyzed, 'cells': cells, 'wording_contrasts': contrasts, 'intent_contrasts': intents,
        'content_flags': flags, 'input_sha256': hashes, 'validation_issues': issues}


def ratio(entry):
    return f"{entry['numerator']} / {entry['denominator']}" if entry and entry.get('denominator') else 'Unavailable · no eligible denominator'


def jaccard(value):
    if value.get('value') is None:
        return esc(value.get('reason', 'Unavailable'))
    return (f'<strong>{value["value"]:.1%}</strong> <span class="muted">({value["intersection"]} / {value["union"]})</span>'
            + f'<span style="display:block;width:115px;height:5px;background:#e2eaee;margin:5px 0;border-radius:3px"><span style="display:block;height:5px;border-radius:3px;background:#176a76;width:{value["value"]*100:.3f}%"></span></span>'
            + f'<span class="muted">Set sizes: {value.get("left_size", "?")} / {value.get("right_size", "?")}</span>')


def set_text(value):
    return 'Unavailable · no eligible answers' if value is None else esc(', '.join(value)) if value else 'None observed within this eligible set'


def variation(summary):
    if not summary['available_numeric_pairs']:
        return f'No numeric comparison · {summary.get("both_empty_pairs",0)} both-empty N/A; {summary.get("unavailable_pairs",0)} unavailable'
    return f'{summary["minimum"]:.1%}–{summary["maximum"]:.1%}; mean {summary["mean"]:.1%}, from {summary["available_numeric_pairs"]} / 3 planned pairs; {summary.get("both_empty_pairs",0)} both-empty N/A'


def prevalence_table(groups, labels):
    union = sorted(set().union(*(set(groups[k]['union'] or []) for k in labels)))
    if not union:
        return notes('No observed items in eligible inventories.' if any(groups[k]['eligible_denominator'] for k in labels) else 'No eligible coded inventories. This is not evidence of no recommendations or no sources.')
    rows = []
    for entity in union:
        row = [esc(entity)]
        for key in labels:
            group = groups[key]
            value = group['prevalence'].get(entity, {'numerator': 0, 'denominator': group['eligible_denominator']})
            row.append(esc(ratio(value)))
        rows.append(row)
    return table(['Coded item'] + [f'{k} · {groups[k]["eligible_denominator"]}/{groups[k]["planned_positions"]} eligible' for k in labels], rows)


def links_table(links):
    if not links:
        return '<p class="muted">No URLs recorded in this field. Completeness and source role are reported separately.</p>'
    rows = []
    for link in links:
        if isinstance(link, str):
            link = {'url': link}
        rows.append([esc(link.get('text') or link.get('title') or ''), http_link(link.get('url','')),
                     esc(link.get('domain','')), esc(link.get('kind','')), esc(link.get('provenance',''))])
    return table(['Label', 'Public URL', 'Recorded host', 'Role', 'Capture provenance'], rows)


def references(record, root):
    found = set()
    def visit(value, key=''):
        if isinstance(value, dict):
            for k, v in value.items():
                visit(v, k)
        elif isinstance(value, list):
            for v in value:
                visit(v, key)
        elif isinstance(value, str) and ('file' in key.lower() or key == 'source_record') and not value.startswith(('http://','https://')) and Path(value).suffix.lower() in {'.json','.txt','.html','.md','.png','.jpg'}:
            found.add(value)
    visit(record)
    return '<ul>' + ''.join('<li>' + local_link(path, root) + '</li>' for path in sorted(found)) + '</ul>'


def coding_view(code, root):
    if not code:
        return notes('Not coded. No entity or source absence is inferred.')
    rows = []
    for entity in code.get('entity_observations', []):
        rows.append([esc(entity.get('entity')), esc(entity.get('observed_name','')), esc(show(entity.get('citation'))),
            esc(show(entity.get('mention'))), esc(show(entity.get('recommendation'))),
            esc(entity.get('recommendation_stance','')), esc(entity.get('free_budget_fit','')),
            esc(entity.get('evidence','')) + notes(entity.get('notes')), '<br>'.join(http_link(url) for url in entity.get('source_urls',[]))])
    sources = []
    for source in code.get('answer_sources', []):
        sources.append([http_link(source.get('url','')), esc(source.get('source_category','Other / unresolved')),
            esc(source.get('candidate_category','')), esc(source.get('classification_status','')),
            esc(source.get('classification_evidence','')), esc(source.get('recommendation_role',''))])
    core={'id','slot_id','platform','interface','source_record','source_record_sha256','coding_method','coding_scope','answer_type',
          'content_flags','entity_observations','supplied_entities','operational_entities','contextual_non_tool_entities','generic_methods',
          'metric_definitions_observed','answer_sources','explicit_body_links','cited_hostname_set','registrable_domain_mapping','capture_scope','summary','coding_cautions','_file'}
    additional={key:value for key,value in code.items() if key not in core}
    return (notes(code.get('coding_method')) + '<p>' + local_link(code.get('_file'), root) + '</p>'
        + detail('C / M / R coding and evidence', table(['Canonical entity','Observed name','C','M','R','Stance','Budget claim','Evidence / note','Supporting URLs'], rows))
        + detail('Cited-page category coding · provisional', table(['URL','Assigned primary category','Candidate only · not aggregated','Classification status','Evidence','Role'], sources))
        + (detail('Explicit body URLs · parallel representation, not additional citation counts',notes('These manually reviewed Markdown/body links are preserved separately. When they represent the same annotated source occurrence, they are not added again to citation counts or domain sets.')+links_table(code['explicit_body_links'])) if 'explicit_body_links' in code else '')
        + detail('Metric definitions returned by the model · not adopted instruments',notes('The definitions, scores, sampling quantities and example dashboards below describe model advice. They do not become this experiment’s scoring rules or measured outcomes. Mention-based numerators remain distinct from active-recommendation judgments.')+pre(code.get('metric_definitions_observed',[])))
        + (detail('Additional reviewed coding · publishers, generated rules and cost checks',notes('Generated scoring thresholds or sampling rules are not independently validated. Source-publisher observations are separate from the default tool/entity distributions.')+pre(additional)) if additional else '')
        + detail('Answer type, advice flags, scope and exclusions', pre({k:code[k] for k in ('coding_scope','answer_type','content_flags','supplied_entities','operational_entities','contextual_non_tool_entities','generic_methods','metric_definitions_observed','capture_scope','registrable_domain_mapping') if k in code}))
        + notes(code.get('coding_cautions')))


def answer_view(record, result, protocol, root, anchor):
    code = record.get('_coding', {})
    metadata = {k:v for k,v in record.items() if not k.startswith('_') and k not in {'answer_text','prompt','answer_links','sources','retrieval_sources','notes','search_queries','observed_composer_text','request_id','response_id','conversation_url'}}
    summary = f'{record["id"]} · {record.get("platform", "Platform not recorded")} · {record.get("status","unknown")}'
    body = notes(record.get('notes'))
    if result:
        body += notes(result['exclusion_reasons'])
        body += table(['Analysis set','Observed members'], [[esc(METRICS[k]), set_text(v)] for k,v in result['sets'].items()])
        body += notes(result.get('metric_reasons'))
    body += detail('Full original prompt', notes('Planned prompt; no submission recorded.' if record.get('_planned_prompt') else 'Recorded submission; unchanged wording.') + pre(record.get('prompt')))
    body += detail('Captured answer body', pre(record.get('answer_text') or 'No readable answer body captured. This is not a negative discovery observation.'))
    if record.get('platform') == OPENAI_PLATFORM:
        body += detail('API request, response, search, tokens, and estimated cost', notes('Requested/configured model and returned model are distinct. Transport completeness is not reviewed answer completeness. Costs are recorded estimates, not reconciled billing, unless the input explicitly establishes reconciliation.') + pre(api_metadata(record)))
    body += detail('Model, search, time, capture and recovery evidence', pre(metadata) + pre(record.get('search_queries', [])) + references(record, root))
    body += detail('Actual answer links · not the retrieval badge', links_table(record.get('answer_links',[])))
    body += detail('Retrieval-panel sources · not matched answer citations', links_table(record.get('retrieval_sources',[])))
    body += coding_view(code, root)
    return detail(summary, body, anchor)


def render(protocol, runs, attempts, findings, root):
    counts, analyzed, cells = findings['counts'], findings['per_answer'], findings['cells']
    title = protocol.get('title', 'Stage 3: Sensitivity to question design')
    platform_counts = {p:sum(complete(r) for r in runs if r['platform']==p) for p in PLATFORMS}
    available_tool_pairs = sum(c['metrics']['recommended_tools']['pair_summary']['available_numeric_pairs'] for c in cells)
    finding_evidence=[];authored=[]
    anchors={r['id']:r['id'] for r in runs};anchors.update({r['selected_attempt_id']:r['id'] for r in runs if r.get('selected_attempt_id')})
    for index,finding in enumerate(protocol.get('findings',[]),1):
        if not isinstance(finding,dict):
            continue
        refs=[]
        for reference in finding.get('evidence',[]):
            refs.append(f'<a href="#{esc(anchors[reference])}">{esc(reference)}</a>' if reference in anchors else
                        '<a href="#answers">coding/ · full answer coding</a>' if reference=='coding/' else local_link(reference,root))
        anchor=f'finding-evidence-{index}'
        authored.append(f'<li><strong>{esc(finding.get("title",""))}</strong> {esc(finding.get("detail",""))} <a class="muted" href="#{anchor}">Evidence</a></li>')
        finding_evidence.append(detail(finding.get('title','Finding evidence'),'<p>'+' · '.join(refs)+'</p>',anchor))
    headline='<ul class="conclusions">'+''.join(authored)+'</ul>' if authored else notes('No authored findings have been recorded; the tables below contain the available descriptive analysis.')
    coverage_note=notes(f'{counts["complete_selected_bodies"]}/24 selected bodies and {counts["eligible_coded_bodies"]}/24 assistant semantic coding records are complete/eligible. {OPENAI_PLATFORM}: {platform_counts[OPENAI_PLATFORM]}/12; Grok: {platform_counts["Grok"]}/12. Actual submissions: {counts["api_submissions"]} API + {counts["grok_consumer_submissions"]} Grok + {counts["historical_chatgpt_ui_submissions"]} historical ChatGPT UI = {counts["actual_submissions"]}. Historical failures: {counts["technical_failure_attempts"]} technical, {counts["incomplete_capture_attempts"]} incomplete capture. These are collection counts, not success rates.')
    snapshot_note=('Complete selected-body and coding snapshot; citation mapping still has its recorded coverage limits.' if counts['eligible_coded_bodies']==24 and counts['complete_selected_bodies']==24 else 'Partial collection/coding snapshot; unknown, incomplete and uncoded positions are not empty discovery sets.')
    coverage_rows = []
    for cell in cells:
        metrics=cell['metrics']
        coverage_rows.append([esc(cell['platform']),esc(cell['prompt_id']),f'{cell["complete_bodies"]} / 3',f'{cell["coded_eligible"]} / 3',
            f'{metrics["recommended_tools"]["eligible_denominator"]} / 3',f'{metrics["cited_domains"]["eligible_denominator"]} / 3',
            f'{metrics["observed_cited_domains"]["eligible_denominator"]} / 3',esc(show(cell['search_observed'])),esc(show(cell['answer_types']))])
    coverage = table(['Platform','Prompt','Complete bodies','Coded eligible','Tool sets','Mapped domains','Observed domains','Actual search · complete bodies only','Primary answer types'],coverage_rows)
    repeat_sections=[]
    for cell in cells:
        metrics=cell['metrics']; rows=[]
        for index,pair in enumerate(metrics['recommended_tools']['pairs']):
            rows.append([esc(pair['left'].rsplit('-',1)[-1]+' ↔ '+pair['right'].rsplit('-',1)[-1]), jaccard(pair),
                jaccard(metrics['cited_domains']['pairs'][index]),jaccard(metrics['observed_cited_domains']['pairs'][index])])
        summaries=table(['Set','Numeric-pair range / mean','Shared across all 3'],[[esc(METRICS[m]),esc(variation(metrics[m]['pair_summary'])),('Unavailable · requires all 3 eligible answers' if metrics[m]['shared_across_all_three'] is None else set_text(metrics[m]['shared_across_all_three']))] for m in ('recommended_tools','cited_domains','observed_cited_domains')])
        repeat_sections.append(detail(f'{cell["prompt_id"]} · {cell["platform"]}',table(['Repeated answers','Recommended tools','Domains · complete mapping','Observed inline domains · qualified'],rows)+summaries))
    wording=[]
    for contrast in findings['wording_contrasts']:
        parts=[]
        for metric in ('recommended_tools','cited_domains','observed_cited_domains'):
            data=contrast['metrics'][metric]; left=contrast['intent']+'1'; right=contrast['intent']+'2'
            parts.append(detail(METRICS[metric],f'<p><strong>Pooled union overlap:</strong> {jaccard(data["union_overlap"])}</p>'
                + notes([f'{left} repeat context: '+variation(data['left']['pair_summary']),f'{right} repeat context: '+variation(data['right']['pair_summary'])])
                + table(['Variant','Eligible answers','Union'],[[left,f'{data["left"]["eligible_denominator"]} / 3',set_text(data['left']['union'])],[right,f'{data["right"]["eligible_denominator"]} / 3',set_text(data['right']['union'])]])
                + prevalence_table({left:data['left'],right:data['right']},[left,right])))
        wording.append(detail(f'{contrast["platform"]} · {contrast["intent"]}1 versus {contrast["intent"]}2',''.join(parts)))
    intent_sections=[]
    for item in findings['intent_contrasts']:
        parts=[]
        for metric in ('source_categories','recommended_tools'):
            data=item['metrics'][metric]
            parts.append(detail(METRICS[metric],'<p><strong>M pooled versus V pooled:</strong> '+jaccard(data['pooled_overlap'])+'</p>'+prevalence_table(data,['M1','M2','M','V1','V2','V'])))
        intent_sections.append(detail(item['platform'],''.join(parts)))
    flag_rows=[[esc(flag.replace('_',' '))]+[esc(ratio(values.get(c['platform']+' / '+c['prompt_id']))) for c in cells] for flag,values in findings['content_flags'].items()]
    flags=table(['Returned-advice flag']+[c['platform']+' / '+c['prompt_id'] for c in cells],flag_rows)
    cmr_rows=[];combo_rows=[];category_rows=[]
    for summary in findings['platform_summaries']:
        cmr_rows.append([esc(summary['platform']),str(summary['entity_answer_rows'])]+[f'{summary["cmr"][key]["true"]} / {summary["cmr"][key]["known_denominator"]} ({summary["cmr"][key]["unresolved"]} unresolved)' for key in ('citation','mention','recommendation')]
            +[f'{summary["nonempty_recommendation_sets"]} / {summary["recommended_tool_inventory"]["eligible_denominator"]}',str(summary['empty_recommendation_sets'])])
        combo_rows.append([esc(summary['platform'])]+[str(summary['cmr_combinations'][key]) for key in ('C','M','R','CM','CR','MR','CMR','None','Unresolved')])
        for category,value in summary['primary_source_category_prevalence'].items():
            category_rows.append([esc(summary['platform']),esc(category),esc(ratio(value))])
    distributions=(notes('C/M/R counts use tool/service/feature/channel entity × answer rows, not every source publisher. Supplied ChatGPT/Grok targets, generic methods and citation-only publishers are excluded. Citation means the entity’s own content under the codebook. C, M and R overlap and must not be added as disjoint totals.')
        +table(['Interface','Entity × answer rows','C / known','M / known','R / known','Answers with named R set','Eligible empty R sets'],cmr_rows)
        +detail('Exact C/M/R combinations',table(['Interface','C only','M only','R only','C+M','C+R','M+R','C+M+R','None','Unresolved'],combo_rows))
        +notes('Primary source-category prevalence below counts each category once per eligible observed-source answer. Categories overlap across sources. Provisional Other / unresolved is not evidence that a page is vendor research or that its contents were verified.')
        +table(['Interface','Primary source-page category','Answers / observed-source denominator'],category_rows))
    mapping_rows=[]
    for run in runs:
        for item in analyzed[run['id']]['domain_mapping']:
            mapping_rows.append([esc(run['id']),http_link(item['url']),esc(item['hostname']),esc(item['normalized_domain']),esc(item['method']),esc(item['provenance'])])
    position_rows=[]
    for run in runs:
        value=analyzed[run['id']]
        position_rows.append([f'<a href="#{esc(run["id"])}">{esc(run["id"])}</a>',esc(run['platform']),esc(run.get('selected_attempt_id') or 'Unresolved'),esc(run.get('status')),esc(show(value['coding_eligible'])),
            esc(model_summary(run)),
            esc(show(search_enabled(run))),esc(show(run.get('search_observed'))),esc(time_text(run.get('submitted_at'))),local_link(run.get('raw_file'),root)])
    selected_ids={r.get('selected_attempt_id'):r['id'] for r in runs if r.get('selected_attempt_id')}
    attempt_rows=[];history=[]
    for attempt in attempts:
        aid=attempt['id']; anchor=selected_ids.get(aid,'attempt-'+aid)
        attempt_rows.append([f'<a href="#{esc(anchor)}">{esc(aid)}</a>',esc(attempt.get('slot_id')),esc(attempt.get('platform','Not recorded')),esc(attempt.get('interface','Not recorded')),esc(attempt.get('status')),esc('Selected evidence' if aid in selected_ids else 'Historical / not selected'),esc(time_text(attempt.get('submitted_at'))),local_link(attempt.get('raw_file'),root)])
        if aid not in selected_ids:
            history.append(answer_view(attempt,None,protocol,root,anchor))
    api_rows=[]
    for attempt in attempts:
        if attempt.get('platform') != OPENAI_PLATFORM:
            continue
        meta=api_metadata(attempt)
        api_rows.append([esc(attempt['id']),esc(attempt.get('status','Unknown')),esc(show(meta['requested_model'])),
            esc(show(meta['returned_model'])),esc(show(meta['reasoning_effort'])),esc(show(meta['search_enabled_api'])),
            esc(show(meta['search_observed'])),pre(meta['token_usage']),pre(meta['tool_usage']),pre(meta['cost_estimate_detail'] if meta['cost_estimate_detail'] is not None else meta['cost_estimate_usd'])])
    api_collection_html=(table(['Attempt','Status','Requested model','Returned model','Effort','Search configured','Search observed','Token usage','Tool usage','Recorded estimated cost'],api_rows)
        if api_rows else notes('No formal API submission is recorded. There is no API answer sample or recorded usage/cost estimate to analyze; the approved budget is not a statement of incurred spend.'))
    cost=findings['api_cost_summary']
    api_collection_html=notes(f'Recorded API estimates sum to US${cost["known_estimate_sum_usd"]} across {cost["estimates_available"]}/{cost["api_attempts"]} submissions with estimates.' if cost['known_estimate_sum_usd'] is not None else 'No recorded API cost estimates to sum.')+api_collection_html
    api_collection_html += notes('Only recorded estimates are summed; no new price calculation is performed. These are not reconciled provider charges. Missing usage or cost remains unknown; configured caps and reserves are not actual spend.')+pre(cost)
    api_collection_html += detail('Authorized API condition and budget',pre(protocol.get('api_collection')))
    if protocol.get('_report_api_config'):
        api_collection_html += detail('Recorded collector configuration and budget guardrails',notes('Pricing and limits below are recorded collector configuration. They were not independently rechecked by this offline report.') + pre(protocol['_report_api_config']) + '<p>'+local_link('api-config.json',root)+'</p>')
    setup_rows=[]
    for event in findings['setup_history']:
        status_snapshot = event.get('record_kind') == 'historical_setup_status_snapshot'
        setup_rows.append([esc(time_text(event.get('checked_at') or event.get('recorded_at'))),esc(event.get('kind') or event.get('status','Historical setup status')),
            'N/A · status snapshot' if status_snapshot else esc(show(event.get('http_status'))),
            'No request · status snapshot' if status_snapshot else esc(show(event.get('generation_submitted'))),
            pre({k:v for k,v in event.items() if k not in ('checked_at','recorded_at','file','kind','http_status','generation_submitted')}),local_link(event['file'],root)])
    snapshot_count = sum(event.get('record_kind') == 'historical_setup_status_snapshot' for event in findings['setup_history'])
    check_count = len(findings['setup_history']) - snapshot_count
    api_collection_html += detail('Historical setup/access checks · not answer submissions',notes(f'The ledger below contains {check_count} access-check records and {snapshot_count} historical status snapshot(s). A snapshot is not another request. TLS trust-chain failure, an expired-key HTTP 401, and the later successful GET model-access check are setup history. They do not submit the study prompt, are not API answer failures, and do not increase the attempts ledger. Earlier blocked status is historical; see completed generation records for subsequent collection.')+table(['Time · UTC+8','Recorded check / historical status','HTTP status','Generation submitted','Evidence summary','Public record'],setup_rows))
    api_collection_html += detail('Recorded collection chronology',notes('All API requests were collected after Grok in the recorded timestamps. Time/order is therefore confounded with interface and platform; these observations do not isolate a causal platform effect.' if findings['collection_chronology']['all_recorded_API_after_Grok'] is True else 'The chronology below records collection timing without assuming an interleaved design.')+pre(findings['collection_chronology']))
    run_sections=''.join(answer_view(r,analyzed[r['id']],protocol,root,r['id']) for r in runs)
    plan=(root/'analysis-plan.md').read_text() if (root/'analysis-plan.md').is_file() else 'Analysis plan missing.'
    methods=notes(['The user authorized replacing the consumer ChatGPT web condition with OpenAI Responses API web_search, requesting gpt-5.6-sol with medium reasoning and a total US$10 API budget. The original prompts and S3-CHATGPT-* position IDs are retained; those IDs are historical identifiers, not a claim that API answers came from consumer ChatGPT Search. New API attempt IDs use S3-OPENAIAPI-*.',
        'The formal comparison is Grok in its consumer interface versus OpenAI through the Responses API. Interface, retrieval implementation, request context, model identity and time can all differ. Same-name model labels do not prove equivalent execution or answers. Historical ChatGPT UI failures remain in the attempt ledger and are not pooled with the API answers.',
        'The requested and returned gpt-5.6-sol value is an undated model identifier, not an independently established backend or dated snapshot. A fixed identifier plus medium effort does not prove that the backend stayed identical, or that consumer ChatGPT Search uses the same backend. All API requests were collected after the Grok batch; this is not a platform causal-effect experiment.',
        'API search enabled in the request, actual returned web-search calls, and answer citation annotations are separate evidence fields. Transport completion does not establish a reviewed complete answer. Awaiting credentials, awaiting body review, missing usage and unknown cost remain unresolved rather than zero.',
        'Coded entities are assistant semantic judgments, not keyword classification or independent human double-coding. Tools/services/surfaces retain their reviewed canonical names. Supplied ChatGPT/Grok targets, generic methods and citation-only publishers are excluded from default tool sets.',
        'A missing or unresolved judgment is not false. Entire metric sets are withheld when relevant judgments are unresolved. Prevalence denominators include only complete selected bodies with matching source digests and eligible coding for that metric. Zero prevalence refers only to those reviewed inventories.',
        'Jaccard = intersection / union. Both-empty eligible sets are N/A; one empty and one nonempty eligible set yields zero. Sparse or empty named-tool lists may accompany a substantive unbranded workflow; zero set overlap is not by itself evidence of unstable advice. Means use only numeric eligible pairs and expose the count. Shared-across-three is withheld until all three are eligible.',
        'Cited-domain overlap with complete mapping requires citation_mapping_complete=true. Observed-inline-domain overlap is separate and coverage-qualified. The first three native Grok captures may omit URL schemes or leading www; standardized HTTPS links are not independently verified exact hrefs. Later DOM hrefs do not repair earlier URL precision.',
        'Domain normalization uses recorded manual hostname mappings and leading-www removal; otherwise it retains the exact hostname. It never takes the last two labels blindly. Exact source URL records remain separate from domain deduplication.',
        'Source categories use only the manually assigned primary category and explicit secondary categories. Candidate categories are not promoted. Category prevalence is per answer, not per citation occurrence; unresolved and provisional categories remain labeled. The observed-source denominator is not a complete retrieval-inventory denominator.',
        'A retrieval/source badge is not an answer-citation count. A complete answer with zero observable inline anchors can have many retrieval hits. Workspace-explored activity and visible personalization controls do not establish audited account isolation.',
        'Wording contrasts change registered phrase packages, not just synonyms: M1 asks to reliably measure with no GEO budget; M2 asks for a free, repeatable workflow as a bootstrapped builder. V1 explicitly says no GEO budget; V2 says bootstrapped. Budget and action cues differ. Interpret sensitivity to these full versions, not a pure lexical effect.',
        'M-versus-V changes the requested task. None of these contrasts supports GEO intervention effectiveness, tool-score validity, or stable platform recommendation probabilities. Generated 0–3 or −1/0–4 rubrics, weights, sample sizes and illustrative dashboard percentages are model advice, not this experiment’s validated measurement instrument. In particular, the M2-R2 recommendation-visibility numerator counts mentions in the returned advice; it is not substituted for our separate R coding.'])
    nav=[('overview','Findings first'),('coverage','Collection and coding'),('repeats','Identical-prompt repeats'),('wording','Wording within intent'),('intents','M versus V'),('distributions','C/M/R and source mix'),('flags','Answer types and flags'),('api','API condition and cost'),('method','Method and limits'),('positions','24 planned positions'),('answers','Full answers and coding'),('attempts','Actual submissions'),('domains','Domain provenance'),('publication','Publication notes')]
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{CSS}</style></head><body><div class="layout"><nav aria-label="Contents"><strong>GEO Learning Log</strong><p>Stage 3 · public research record<br>November 2, 2026</p><div class="links"><a href="https://github.com/helen-bird/geo-platform-observation">Repository / GEO Learning Log</a><a href="../../index.html">Stage 1 report</a><a href="../02-post-discovery/index.html">Stage 2 report</a><a href="public-data.zip">Download public data</a>{''.join(f'<a href="#{key}">{esc(label)}</a>' for key,label in nav)}</div></nav><main>
<header class="hero" id="overview"><div class="eyebrow">8 cells · 24 planned positions · {counts['actual_submissions']} actual submissions</div><h1>{esc(title)}</h1><div style="border:3px solid #176a76;background:#eaf4f4;padding:16px 18px;border-radius:10px;margin:18px 0"><strong>OpenAI API + web search, not consumer ChatGPT Search. These results do not represent ChatGPT web app performance.</strong></div>{headline}<blockquote><p><strong>Interpretation limit:</strong> Three answers per prompt and interface. OpenAI Responses API web_search is not consumer ChatGPT Search; the API batch followed Grok, so interface and time are confounded. The undated gpt-5.6-sol ID does not establish an exact backend/snapshot.</p><p>{esc(snapshot_note)} Categories and external claims remain provisional; both-empty recommendation sets are N/A.</p></blockquote><div class="counts">{''.join(f'<div class="count"><strong>{number}</strong><span>{label}</span></div>' for number,label in [(24,'Planned positions'),(counts['actual_submissions'],'Actual submissions'),(counts['complete_selected_bodies'],'Complete selected bodies'),(counts['eligible_coded_bodies'],'Eligible coded bodies')])}</div></header>
<section id="coverage"><h2>Collection and coding coverage</h2>{coverage_note}{coverage}{notes(findings['validation_issues'])}</section>
<section id="repeats"><h2>1 · Identical-prompt repeat variation</h2>{notes(f'{available_tool_pairs}/24 planned tool-set pairs have numeric Jaccard values. Each cell has R1–R2, R1–R3, R2–R3. Both-empty sets are N/A, not 0% or 100%; sparse named-tool sets are not by themselves an instability finding. Missing pairs remain unavailable. The observed-domain column is a separate coverage-qualified view.')}{''.join(repeat_sections)}</section>
<section id="wording"><h2>2 · Wording variants within the same intent</h2>{notes('M1 versus M2 and V1 versus V2 compare variant unions and per-answer prevalence. Inspect repeat variation alongside these contrasts. The variants change context as well as phrasing; small unequal eligible samples cannot isolate wording effects.')}{''.join(wording)}</section>
<section id="intents"><h2>3 · Measurement intent versus validation intent</h2>{notes('Variant results appear separately before the pooled M and V columns. Each pooled intent has up to six eligible answers. Changing the requested task changes what an answer should contain; this comparison primarily describes categories and recommendation sets.')}{''.join(intent_sections)}</section>
<section id="distributions"><h2>Citation, Mention, Recommendation, and source mix</h2>{distributions}</section>
<section id="flags"><h2>Answer types and returned-advice flags</h2>{notes('Primary answer-type counts are in the coverage table. Nonexclusive flags below describe returned advice, not verified best practices. Each cell displays true judgments / known judgments; missing flag coding is excluded.')}{flags}</section>
<section id="api"><h2>API condition, request evidence, and estimated cost</h2>{api_collection_html}</section>
<section id="method"><h2>Method, controls, and limits</h2>{methods}{detail('Evidence for the authored findings',''.join(finding_evidence))}{detail('Registered prompts',table(['Prompt','Original wording'],[[q,esc(protocol.get('prompts',{}).get(q,''))] for q in PROMPTS]))}{detail('Historical collection protocol, controls and amendments',notes('This archived protocol preserves authorization, setup and collection status as recorded at the time. The public release is a separately authorized redacted edition; historical restrictions do not describe the current publication status.')+pre({k:v for k,v in protocol.items() if k not in ('prompts','findings','preview_verification') and not k.startswith('_')}))}{detail('Historical analysis plan and amendments',notes('The collection plan is retained for provenance, including then-known limitations. Public-edition edits and review scope are documented in Publication notes.')+pre(plan))}</section>
<section id="positions"><h2>24 planned response positions</h2>{notes('S3-CHATGPT-* is the retained position-ID prefix. Its current formal platform is OpenAI API + web search; S3-OPENAIAPI-* identifies new API submissions. Original prompt text still refers to ChatGPT and Grok, unchanged.')}{table(['Position','Formal platform','Selected attempt','Capture status','Coding eligible','Configured / requested / returned model and effort','Search enabled API / UI','Search observed','Submitted · UTC+8','Public record'],position_rows)}</section>
<section id="answers"><h2>Full answers, returned links, and coding evidence</h2>{notes('All sections are expanded. Registered prompts and redacted public answer copies are shown with public evidence records. Personal context and tracking parameters may have been removed; original annotation character offsets are not claimed after these edits. No external claims are endorsed merely by reproducing a platform answer.')}{run_sections}</section>
<section id="attempts"><h2>Every actual submission and retained failure</h2>{notes('The attempts ledger already includes selected submissions and historical ChatGPT consumer-UI diagnostics. Do not add it to the 24 planned positions. Recovery captures of an existing answer are not extra submissions. Technical and body-capture failures do not establish absence of tools or sources. Historical UI attempts keep their original platform label and are not API answers.')}{table(['Attempt','Position','Actual platform','Interface','Status','Selection','Submitted · UTC+8','Public record'],attempt_rows)}{''.join(history)}</section>
<section id="domains"><h2>Hostname mapping and source provenance</h2>{table(['Answer','Public source URL','Recorded hostname','Analysis domain','Mapping basis','Precision / provenance'],mapping_rows)}{notes('URLs shown from native target displays retain their capture qualification; hostname normalization does not verify the original scheme or exact destination. Source URLs retain their recorded precision limits; the cited external claims were not independently fact-checked for this study.')}<p>{local_link('findings.json',root)} · {local_link('analysis-plan.md',root)} · {local_link('protocol.json',root)} · {local_link('runs.json',root)} · {local_link('attempts.json',root)}</p><p class="footer">Public redacted edition generated {esc(findings['generated_at'])}. Rebuilds do not make model queries or change accounts. See Publication notes for privacy edits and review scope.</p></section><section id="publication"><h2>Publication notes and downloads</h2><blockquote><p>This is the separately authorized public edition of Stage 3. Private credentials, account context, conversation links, opaque provider IDs and local-only captures are excluded. Citation URLs were cleaned of tracking parameters; annotation offsets are not guaranteed after public-copy edits. These edits preserve the study’s coded observations and declared limitations.</p></blockquote><p><a href="public-data.zip">Download public data and findings</a> · {local_link('publication-notes.json',root)} · {local_link('settings-summary.json',root)}</p>{detail('Publication notes',pre(protocol.get('_report_publication_notes')))}{detail('Public settings summary',pre(protocol.get('_report_settings_summary')))}</section></main></div></body></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=STAGE / 'data')
    args = parser.parse_args()
    root = public_path(args.data_dir)
    if not root.is_dir():
        parser.error('The public data directory is not ready.')
    protocol, runs, attempts, issues, hashes = load(root)
    findings = analyze(protocol, runs, attempts, root, issues, hashes)
    findings['edition'] = 'Public redacted Stage 3 edition'
    findings['public_data_root'] = 'data/'
    findings['annotation_positions'] = 'Original annotation positions are not guaranteed after privacy and URL edits; omitted from public records.'
    report = render(protocol, runs, attempts, findings, root)
    STAGE.mkdir(parents=True, exist_ok=True)
    (STAGE / 'findings.json').write_text(json.dumps(findings, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (STAGE / 'index.html').write_text(report, encoding='utf-8')
    with zipfile.ZipFile(STAGE / 'public-data.zip', 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(root.rglob('*')):
            if path.is_file():
                public_path(path)
                if path.is_symlink() or path.suffix.lower() not in {'.json','.md','.txt'}:
                    raise ValueError('Unexpected file type or symbolic link in public data archive.')
                archive.write(path, 'data/' + str(path.relative_to(root)).replace(os.sep, '/'))
        archive.write(STAGE / 'findings.json', 'findings.json')
    print(json.dumps({'counts': findings['counts'], 'validation_issues': issues, 'outputs': ['index.html','findings.json','public-data.zip']}))


if __name__ == '__main__':
    main()
