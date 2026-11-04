#!/usr/bin/env python3
"""Official Google index-state queries and private, append-only monitoring history.

The URL Inspection API reports Google's indexed version. It does not perform a
live URL test, request indexing, or use the restricted Google Indexing API.
Raw responses must stay outside the public Pages checkout.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, unquote
from urllib.request import Request, urlopen
import uuid
from email.utils import parsedate_to_datetime

PUBLIC_ROOT = Path(__file__).resolve().parents[1]
PROPERTY = 'https://helen-bird.github.io/geo-platform-observation/'
INSPECTION_ENDPOINT = 'https://searchconsole.googleapis.com/v1/urlInspection/index:inspect'
RAW_FIELDS = ('verdict', 'coverageState', 'indexingState', 'pageFetchState',
              'robotsTxtState', 'lastCrawlTime', 'googleCanonical',
              'userCanonical', 'sitemap', 'referringUrls')
FETCH_ERRORS = {'SOFT_404', 'BLOCKED_ROBOTS_TXT', 'NOT_FOUND', 'ACCESS_DENIED',
                'SERVER_ERROR', 'REDIRECT_ERROR', 'ACCESS_FORBIDDEN',
                'BLOCKED_4XX', 'INTERNAL_CRAWL_ERROR', 'INVALID_URL'}
NOT_INDEXED_COVERAGE = {
    'url is unknown to google', 'excluded by noindex tag',
    "excluded by 'noindex' tag", 'blocked by robots.txt',
    'not found (404)', 'soft 404', 'server error (5xx)',
    'page with redirect', 'alternate page with proper canonical tag',
    'duplicate without user-selected canonical',
    'duplicate, google chose different canonical than user',
    'blocked due to access forbidden (403)',
    'blocked due to unauthorized request (401)',
    'blocked due to other 4xx issue', 'redirect error',
}
INDEXED_COVERAGE = {'submitted and indexed', 'indexed, not submitted in sitemap',
                    'indexed', 'url is on google'}


def utc_now():
    return dt.datetime.now(dt.timezone.utc)


def iso(value):
    if isinstance(value, str):
        value = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('Monitoring times must include a timezone')
    return value.astimezone(dt.timezone.utc).isoformat()


def valid_timestamp(value):
    if not isinstance(value, str) or not value:
        return False
    try:
        return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo is not None
    except ValueError:
        return False


def _coverage(value):
    return re.sub(r'\s+', ' ', str(value or '').strip().lower().replace('\u2013', '-').replace('\u2014', '-'))


def classify_result(payload, url=None):
    """Conservative observation labels, keeping absent fields unknown.

    coverageState is free text; request language en-US and match only explicit
    meanings. No absence (including lastCrawlTime) is a non-index/crawl verdict.
    """
    result = payload.get('inspectionResult', {}) if isinstance(payload, dict) else {}
    raw = result.get('indexStatusResult', {}) if isinstance(result, dict) else {}
    if not isinstance(raw, dict):
        raw = {}
    verdict = str(raw.get('verdict', '')).upper()
    coverage = _coverage(raw.get('coverageState'))
    indexing = str(raw.get('indexingState', '')).upper()
    robots = str(raw.get('robotsTxtState', '')).upper()
    fetch = str(raw.get('pageFetchState', '')).upper()
    blockers = []
    if robots == 'DISALLOWED' or fetch == 'BLOCKED_ROBOTS_TXT':
        blockers.append('ROBOTS_BLOCKED')
    if indexing in {'BLOCKED_BY_META_TAG', 'BLOCKED_BY_HTTP_HEADER', 'BLOCKED_BY_ROBOTS_TXT'}:
        blockers.append('NOINDEX_OR_INDEXING_BLOCK')
    if fetch in FETCH_ERRORS:
        blockers.append('FETCH_'+fetch)
    if url and raw.get('googleCanonical') and raw['googleCanonical'] != url:
        blockers.append('GOOGLE_CANONICAL_DIFFERS')
    if url and raw.get('userCanonical') and raw['userCanonical'] != url:
        blockers.append('USER_CANONICAL_DIFFERS')
    discovered = 'discovered' in coverage and 'currently not indexed' in coverage
    crawled_not_indexed = 'crawled' in coverage and 'currently not indexed' in coverage
    negative_coverage = discovered or crawled_not_indexed or coverage in NOT_INDEXED_COVERAGE
    canonical_matches = bool(raw.get('googleCanonical')) and (url is None or raw['googleCanonical'] == url)
    indexed_evidence = verdict == 'PASS' and (coverage in INDEXED_COVERAGE or canonical_matches)
    # Crawl/index blocking signals are separate from index membership. A URL
    # can remain indexed while currently blocked to crawling; do not fabricate
    # an INDEXED -> NOT_INDEXED transition merely from a new fetch issue.
    if verdict == 'PASS' and negative_coverage:
        status, lifecycle = 'UNKNOWN', 'CRAWLED' if valid_timestamp(raw.get('lastCrawlTime')) else 'UNKNOWN'
        blockers.append('CONFLICTING_INDEX_EVIDENCE')
    elif indexed_evidence:
        status, lifecycle = 'INDEXED', 'CRAWLED' if valid_timestamp(raw.get('lastCrawlTime')) else 'UNKNOWN'
    elif discovered:
        status, lifecycle = 'DISCOVERED', 'DISCOVERED'
    elif crawled_not_indexed:
        status, lifecycle = 'CRAWLED', 'CRAWLED'
    elif coverage in NOT_INDEXED_COVERAGE or indexing in {
            'BLOCKED_BY_META_TAG', 'BLOCKED_BY_HTTP_HEADER', 'BLOCKED_BY_ROBOTS_TXT'} or robots == 'DISALLOWED' or fetch in FETCH_ERRORS:
        status = 'NOT_INDEXED'
        lifecycle = 'CRAWLED' if valid_timestamp(raw.get('lastCrawlTime')) else 'UNKNOWN'
    else:
        status = 'UNKNOWN'
        lifecycle = 'CRAWLED' if valid_timestamp(raw.get('lastCrawlTime')) else 'UNKNOWN'
    return {'status': status, 'lifecycle': lifecycle, 'blockers': sorted(set(blockers)),
            'index_status': 'INDEXED' if status == 'INDEXED' else
            ('NOT_INDEXED' if status in {'NOT_INDEXED', 'DISCOVERED', 'CRAWLED'} else 'UNKNOWN'),
            'classification_source': 'actual_url_inspection_fields',
            'classification_note': 'Indexed-version observation only; not a live URL test or indexing request.'}


def default_requester(method, url, headers, body, timeout):
    context = ssl.create_default_context()
    request = Request(url, data=body, headers=headers, method=method)
    try:
        response = urlopen(request, context=context, timeout=timeout)
    except HTTPError as error:
        response = error
    with response:
        content = response.read(5_000_001)
        if len(content) > 5_000_000:
            raise ValueError('Response exceeds bounded monitor limit')
        try:
            payload = json.loads(content.decode('utf-8'))
        except (ValueError, UnicodeError):
            payload = None
        return response.code, dict(response.headers.items()), payload


def error_category(status, payload):
    reasons = set()
    if isinstance(payload, dict) and isinstance(payload.get('error'), dict):
        reasons.add(payload['error'].get('status', ''))
        for item in payload['error'].get('errors', []):
            if isinstance(item, dict):
                reasons.add(item.get('reason', ''))
        for item in payload['error'].get('details', []):
            if isinstance(item, dict):
                reasons.add(item.get('reason', ''))
    lower = {re.sub(r'[^a-z0-9]', '', str(r).lower()) for r in reasons}
    if status == 401:
        return 'AUTH_REQUIRED', False
    if status == 403:
        if any('quota' in r or 'dailylimit' in r or 'resourceexhausted' in r for r in lower):
            return 'QUOTA_EXCEEDED', False
        if any('ratelimit' in r for r in lower):
            return 'RATE_LIMITED', True
        return 'PERMISSION_DENIED', False
    if status == 429:
        return 'RATE_LIMITED', True
    if status in (500, 502, 503, 504):
        return 'SERVER_ERROR', True
    if status in (400, 404):
        return 'INVALID_REQUEST', False
    return 'API_ERROR', False


def retry_delay(headers, attempt):
    value = next((v for k, v in headers.items() if k.lower() == 'retry-after'), None)
    if value is not None:
        try:
            return min(30.0, max(0.0, float(value)))
        except (ValueError, TypeError):
            try:
                moment = parsedate_to_datetime(value)
                return min(30.0, max(0.0, (moment-utc_now()).total_seconds()))
            except (ValueError, TypeError, OverflowError):
                pass
    return min(30.0, 2.0 ** attempt)


class InspectionClient:
    def __init__(self, token_provider, requester=None, sleep=time.sleep,
                 max_attempts=3, timeout=30):
        if not 1 <= max_attempts <= 4:
            raise ValueError('Retry attempts must remain bounded')
        self.token_provider = token_provider
        self.requester = requester or default_requester
        self.sleep, self.max_attempts, self.timeout = sleep, max_attempts, timeout

    def inspect(self, url, property_url=PROPERTY):
        try:
            token = self.token_provider() if self.token_provider else None
        except Exception:
            # Never print exception text from credential providers.
            return {'ok': False, 'error': {'category': 'AUTH_REQUIRED', 'attempts': 0}}
        if not isinstance(token, str) or not token.strip():
            return {'ok': False, 'error': {'category': 'AUTH_REQUIRED', 'attempts': 0}}
        body = json.dumps({'inspectionUrl': url, 'siteUrl': property_url,
                           'languageCode': 'en-US'}).encode()
        attempts = []
        for attempt in range(1, self.max_attempts+1):
            try:
                code, headers, payload = self.requester('POST', INSPECTION_ENDPOINT,
                    {'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'},
                    body, self.timeout)
            except (URLError, TimeoutError, OSError):
                code, headers, payload = None, {}, None
                category, can_retry = 'NETWORK_ERROR', True
            except (ValueError, TypeError):
                code, headers, payload = None, {}, None
                category, can_retry = 'INVALID_RESPONSE', False
            else:
                if code == 200:
                    result = payload.get('inspectionResult') if isinstance(payload, dict) else None
                    if isinstance(result, dict) and isinstance(result.get('indexStatusResult'), dict):
                        attempts.append({'attempt': attempt, 'http_status': code, 'outcome': 'SUCCESS'})
                        return {'ok': True, 'payload': payload, 'attempts': attempts,
                                'http_status': code}
                    category, can_retry = 'INVALID_RESPONSE', False
                else:
                    category, can_retry = error_category(code, payload)
            attempts.append({'attempt': attempt, 'http_status': code, 'outcome': category})
            if not can_retry or attempt == self.max_attempts:
                return {'ok': False, 'raw_error_response': payload,
                        'attempt_log': attempts,
                        'error': {'category': category, 'http_status': code,
                                  'attempts': attempt}}
            self.sleep(retry_delay(headers, attempt))
        raise AssertionError('Bounded retry loop did not return')


def load_inventory(path):
    inventory = json.loads(Path(path).read_text())
    property_url = inventory.get('property', inventory.get('property_url', PROPERTY))
    if property_url != PROPERTY:
        raise ValueError('This monitor is scoped to the approved URL-prefix property')
    selected = []
    for item in inventory.get('urls', []):
        if not isinstance(item, dict):
            raise ValueError('Each inventory item must describe a URL')
        if item.get('monitor') is not True:
            continue
        url = item.get('url', '')
        parsed = urlsplit(url)
        if not url.startswith(PROPERTY) or parsed.scheme != 'https' or parsed.query or parsed.fragment:
            raise ValueError('Monitored URLs must be canonical URLs inside the approved project')
        decoded_path = unquote(parsed.path)
        if any(part in {'.', '..'} for part in decoded_path.split('/')) or decoded_path.endswith('/index.html'):
            raise ValueError('Traversal and index.html aliases are not independent canonical content')
        if item.get('category') == 'excluded' or item.get('noindex') is True:
            raise ValueError('Excluded/noindex pages may not be silently monitored as primary content')
        selected.append(item)
    if not selected or len({x['url'] for x in selected}) != len(selected):
        raise ValueError('Expected a nonempty, duplicate-free monitored URL list')
    if len(selected) > 500:
        raise ValueError('Inventory exceeds the conservative per-run request bound')
    return property_url, selected


def _atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2)+'\n'
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                     prefix='.'+path.name+'.', delete=False) as stream:
        stream.write(data)
        temporary = Path(stream.name)
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _load_optional(path, default):
    if not path.exists():
        return default
    # Malformed persistent state is a hard error; never erase history silently.
    return json.loads(path.read_text())


def _safe_event(kind, url, before, after, checked_at, next_step, detail=None, episode=None):
    material = json.dumps([kind, url, before, after, detail, episode], sort_keys=True)
    event = {'kind': kind, 'url': url, 'before_status': before,
             'after_status': after, 'checked_at': checked_at,
             'evidence_source': 'official_google_url_inspection_api',
             'next_step': next_step,
             'fingerprint': hashlib.sha256(material.encode()).hexdigest()[:24]}
    if detail is not None:
        event['detail'] = detail
    return event


def compare(previous, current, checked_at):
    old = {r['url']: r for r in (previous or {}).get('results', [])}
    new = {r['url']: r for r in current}
    alerts = []
    episode = (previous or {}).get('snapshot_id', 'initial-observation')
    for url, record in new.items():
        before = old.get(url, {})
        prior = before.get('status', 'UNKNOWN')
        record['previous_status'] = prior
        record['status_changed'] = bool(record.get('query_success')) and prior != record['status']
        record['new_url'] = url not in old
        if not record.get('query_success'):
            continue
        if record['status'] == 'INDEXED' and prior != 'INDEXED':
            alerts.append(_safe_event('FIRST_INDEXED', url, prior, 'INDEXED', checked_at,
                'Record this observation; Google indexing does not prove AI discovery.', episode=episode))
        elif prior == 'INDEXED' and record['status'] in {'NOT_INDEXED', 'DISCOVERED', 'CRAWLED'}:
            alerts.append(_safe_event('INDEX_LOST', url, prior, record['status'], checked_at,
                'Review the indexed-version evidence in Search Console; use Live Test separately if needed.', episode=episode))
        new_blockers = sorted(set(record.get('blockers', []))-set(before.get('blockers', [])))
        if new_blockers:
            alerts.append(_safe_event('NEW_INDEXING_PROBLEM', url, prior, record['status'],
                checked_at, 'Inspect the stated robots, noindex, fetch or canonical issue before changing content.', new_blockers, episode=episode))
    return alerts, sorted(set(new)-set(old)), sorted(set(old)-set(new))


def _write_history(output, snapshot):
    path = output/'index-history.csv'
    fields = ['snapshot_id', 'checked_at', 'url', 'status', 'coverage_state',
              'last_crawl_time', 'google_canonical', 'user_canonical',
              'sitemap_association', 'status_changed', 'error']
    existed = path.exists()
    if existed:
        with path.open(newline='') as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != fields:
                raise ValueError('Existing index history uses a different schema')
            if any(row['snapshot_id'] == snapshot['snapshot_id'] for row in reader):
                return
    with path.open('a', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        if not existed:
            writer.writeheader()
        for record in snapshot['results']:
            writer.writerow({**{k: record.get(k) for k in fields},
                'snapshot_id': snapshot['snapshot_id'],
                'sitemap_association': json.dumps(record.get('sitemap_association'), ensure_ascii=False),
                'error': json.dumps(record.get('error'), ensure_ascii=False) if record.get('error') else ''})
    os.chmod(path, 0o600)


def _summary(snapshot):
    counts = snapshot['counts']
    lines = ['# Google index monitor', '',
        'Checked at: '+snapshot['checked_at'],
        'Run status: '+snapshot['run_status'],
        'Property: '+snapshot['property'], '',
        'This checks Google indexed-version status, not live URL tests or indexing requests.',
        'Private raw responses and referring URLs must not be published.', '',
        '| URL | Previous | Current | API outcome |', '| --- | --- | --- | --- |']
    for record in snapshot['results']:
        lines.append('| '+record['url']+' | '+record.get('previous_status', 'UNKNOWN')+' | '+record['status']+' | '+('SUCCESS' if record['query_success'] else record['error']['category'])+' |')
    lines += ['', 'Counts: '+json.dumps(counts, sort_keys=True),
              'New URLs: '+str(len(snapshot['added_urls'])),
              'Removed URLs: '+str(len(snapshot['removed_urls'])),
              'Consecutive unsuccessful runs: '+str(snapshot['consecutive_failures']), '',
              'A partial run never replaces the previous successful comparison snapshot.',
              'Missing fields remain unknown. Google indexing changes do not establish AI recommendation effects.', '']
    return '\n'.join(lines)


def _guard_private_output(output, private_runtime_verified):
    if not (output == PUBLIC_ROOT or output.is_relative_to(PUBLIC_ROOT)):
        return
    try:
        remote = subprocess.check_output(['git', 'config', '--get', 'remote.origin.url'],
            cwd=PUBLIC_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        remote = ''
    approved_private_remotes = {'https://github.com/helen-bird/geo-index-monitor.git',
        'https://github.com/helen-bird/geo-index-monitor',
        'git@github.com:helen-bird/geo-index-monitor.git'}
    if private_runtime_verified is True and remote in approved_private_remotes:
        return
    raise ValueError('Detailed monitoring output must be outside public Pages checkout or in verified approved private runtime')


def run_monitor(inventory_path, output_dir, token_provider=None, *, requester=None,
                now=None, sleep=time.sleep, sitemap_status=None,
                private_runtime_verified=False):
    property_url, entries = load_inventory(inventory_path)
    output = Path(output_dir).expanduser().resolve()
    _guard_private_output(output, private_runtime_verified)
    output.mkdir(parents=True, exist_ok=True)
    os.chmod(output, 0o700)
    checked_at = iso(now if now is not None else utc_now())
    snapshot_id = checked_at.replace(':', '').replace('+', '_')+'-'+uuid.uuid4().hex[:8]
    successful = _load_optional(output/'latest-successful-index-status.json', None)
    state = _load_optional(output/'monitor-state.json', {'consecutive_failures': 0})
    provider = token_provider or (lambda: os.environ.get('GOOGLE_ACCESS_TOKEN'))
    client = InspectionClient(provider, requester=requester, sleep=sleep)
    results, errors = [], []
    for entry in entries:
        url = entry['url']
        response = client.inspect(url, property_url)
        record = {'checked_at': iso(now if now is not None else utc_now()),
                  'url': url, 'category': entry.get('category', 'unspecified'),
                  'query_success': response['ok'], 'error': response.get('error')}
        if response['ok']:
            payload = response['payload']
            raw = payload['inspectionResult']['indexStatusResult']
            record.update(classify_result(payload, url))
            record.update({field: raw[field] for field in RAW_FIELDS if field in raw})
            record.update(raw_response=payload, raw_index_status=raw,
                          api_attempts=response['attempts'],
                          coverage_state=raw.get('coverageState'),
                          last_crawl_time=raw.get('lastCrawlTime'),
                          google_canonical=raw.get('googleCanonical'),
                          user_canonical=raw.get('userCanonical'),
                          sitemap_association=raw.get('sitemap'),
                          referring_urls=raw.get('referringUrls'))
        else:
            category = response['error']['category']
            record.update(status='AUTH_REQUIRED' if category in {'AUTH_REQUIRED', 'PERMISSION_DENIED'} else 'ERROR',
                          lifecycle='UNKNOWN', index_status='UNKNOWN', blockers=[],
                          raw_response=response.get('raw_error_response'),
                          api_attempts=response.get('attempt_log', []),
                          coverage_state=None, last_crawl_time=None,
                          google_canonical=None, user_canonical=None,
                          sitemap_association=None)
            errors.append({'url': url, **response['error']})
        results.append(record)
    complete = not errors
    failures = 0 if complete else state.get('consecutive_failures', 0)+1
    alerts, added, removed = compare(successful, results, checked_at)
    auth_failure = any(e['category'] in {'AUTH_REQUIRED', 'PERMISSION_DENIED'} for e in errors)
    if auth_failure:
        alerts.append(_safe_event('AUTHORIZATION_FAILED', PROPERTY, None, 'AUTH_REQUIRED', checked_at,
            'Renew the approved readonly OAuth grant or verify property access; never send credentials in chat.'))
    if failures >= 2:
        alerts.append(_safe_event('CONSECUTIVE_MONITOR_FAILURES', PROPERTY, None, 'MONITOR_FAILED', checked_at,
            'Review the private workflow error categories and restore the monitor before drawing index conclusions.'))
    if sitemap_status and (sitemap_status.get('accessible') is False or sitemap_status.get('processing_error') is True):
        alerts.append(_safe_event('SITEMAP_PROBLEM', PROPERTY+'sitemap.xml', None, 'SITEMAP_ERROR', checked_at,
            'Check the public XML and the official Search Console sitemap processing status separately.'))
    run_status = 'SUCCESS' if complete else ('AUTH_REQUIRED' if auth_failure else 'PARTIAL_FAILURE')
    api_attempt_count = sum(len(r.get('api_attempts', [])) for r in results)
    snapshot = {'schema_version': 1, 'snapshot_id': snapshot_id,
                'checked_at': checked_at, 'property': property_url,
                'source': 'official_url_inspection_api' if api_attempt_count else 'authorization_check_no_url_inspection',
                'api_requests_attempted': api_attempt_count,
                'api_inspections_succeeded': sum(r.get('query_success') is True for r in results),
                'inspection_mode': 'INDEXED_VERSION_ONLY',
                'inventory_sha256': hashlib.sha256(Path(inventory_path).read_bytes()).hexdigest(),
                'run_status': run_status, 'run_complete': complete,
                'counts': {status: sum(r['status'] == status for r in results)
                           for status in sorted({r['status'] for r in results})},
                'results': results, 'errors': errors, 'alerts': alerts,
                'added_urls': added, 'removed_urls': removed,
                'consecutive_failures': failures,
                'previous_successful_snapshot_id': (successful or {}).get('snapshot_id'),
                'live_test_performed': False, 'indexing_requested': False}
    path = output/'snapshots'/(snapshot_id+'.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive immutable snapshot creation, unlike the replaceable latest pointers.
    with path.open('x', encoding='utf-8') as stream:
        json.dump(snapshot, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    os.chmod(path, 0o600)
    _write_history(output, snapshot)
    _atomic(output/'latest-index-status.json', snapshot)
    if complete:
        _atomic(output/'latest-successful-index-status.json', snapshot)
    _atomic(output/'monitor-state.json', {'consecutive_failures': failures,
        'last_run_snapshot_id': snapshot_id,
        'last_successful_snapshot_id': snapshot_id if complete else state.get('last_successful_snapshot_id')})
    _atomic(output/'alerts.json', {'snapshot_id': snapshot_id, 'checked_at': checked_at, 'alerts': alerts})
    summary = output/'index-monitor-summary.md'
    summary.write_text(_summary(snapshot))
    os.chmod(summary, 0o600)
    return snapshot


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, default=PUBLIC_ROOT/'monitoring/google-index/urls.json')
    parser.add_argument('--output', type=Path, required=True,
                        help='Private state directory outside the public Pages checkout')
    args = parser.parse_args(argv)
    try:
        snapshot = run_monitor(args.inventory, args.output)
    except (ValueError, OSError, json.JSONDecodeError):
        # No path, credential, raw API error or payload is printed to Actions logs.
        print(json.dumps({'run_status': 'CONFIGURATION_ERROR',
                          'detail': 'Review the private inventory/output configuration.'}))
        return 4
    print(json.dumps({'snapshot_id': snapshot['snapshot_id'],
                      'run_status': snapshot['run_status'],
                      'counts': snapshot['counts'],
                      'alert_count': len(snapshot['alerts']),
                      'private_raw_responses_published': False}))
    return 0 if snapshot['run_complete'] else (2 if snapshot['run_status'] == 'AUTH_REQUIRED' else 3)


if __name__ == '__main__':
    sys.exit(main())
