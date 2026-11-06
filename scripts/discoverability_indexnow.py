#!/usr/bin/env python3
"""Change-only IndexNow notifications, independent of any engine's index state.

The verification key is a public ownership token, never a Bing Webmaster API
credential. Initial observations establish a baseline and send no notification.
"""
from __future__ import annotations
import copy
import hashlib
import json
import re
from urllib.parse import urlsplit
from urllib.error import URLError
from discoverability_openai import (PROPERTY, ProbeError, default_requester,
                                   get_url, page_signals, reviewed_urls, utc, validate_url)

ENDPOINT = 'https://api.indexnow.org/indexnow'

class IndexNowError(RuntimeError):
    def __init__(self, code): self.code = code; super().__init__(code)

def validate_config(config):
    if not isinstance(config, dict): raise IndexNowError('INVALID_CONFIG')
    key = config.get('key', '')
    if not re.fullmatch(r'[A-Za-z0-9-]{8,128}', key): raise IndexNowError('INVALID_VERIFICATION_KEY')
    if config.get('host') != 'helen-bird.github.io': raise IndexNowError('INVALID_HOST')
    if config.get('endpoint', ENDPOINT) != ENDPOINT: raise IndexNowError('UNTRUSTED_ENDPOINT')
    expected = PROPERTY + key + '.txt'
    if config.get('keyLocation') != expected: raise IndexNowError('INVALID_PROJECT_KEY_LOCATION')
    return {'host': 'helen-bird.github.io', 'key': key, 'keyLocation': expected, 'endpoint': ENDPOINT}

def _sha(body): return hashlib.sha256(body).hexdigest()

def observe_content(inventory, *, requester=None, checked_at=None, sleep=None, removed_urls=()):
    """Observe only reviewed desired routes and previously known removed URLs."""
    kwargs = {'requester': requester}
    if sleep is not None: kwargs['sleep'] = sleep
    rows = reviewed_urls(inventory); active = {r['url'] for r in rows}; observations = {}
    for url in sorted(active | {validate_url(u) for u in removed_urls}):
        result = get_url(url, **kwargs); signals = page_signals(result)
        headers = {k.lower(): v for k, v in result['headers'].items()}
        # Header values such as a changed ETag/cache date do not notify IndexNow.
        observations[url] = {'url': url, 'checked_at': checked_at or utc(), 'http_status': result['http_status'],
                             'body_sha256': _sha(result['body']) if result['http_status'] == 200 else None,
                             'noindex': signals.get('noindex'), 'canonical': signals.get('canonical'), 'content_sha256': signals.get('content_sha256'),
                             'possible_interstitial': signals.get('possible_interstitial'), 'error': result['error'],
                             'content_type': headers.get('content-type', ''), 'attempts': result['attempts']}
    return observations

def _desired_map(inventory): return {r['url']: r for r in reviewed_urls(inventory)}

def _content_fingerprint(record):
    # The actual deployed representation is checked, not repository timestamps.
    return record.get('content_sha256') or record.get('body_sha256')

def _valid_live(record, url):
    kind = record.get('content_type', '')
    return (record.get('http_status') == 200 and record.get('error') is None
            and record.get('noindex') is False and record.get('canonical') == [url]
            and record.get('possible_interstitial') is False
            and isinstance(record.get('body_sha256'), str)
            and re.fullmatch(r'[0-9a-f]{64}', record['body_sha256']) is not None
            and (not kind or 'text/html' in str(kind).lower()))

def plan_changes(inventory, observations, previous_state=None, config=None, *, checked_at=None):
    """Pure planner. No previous state means baseline only, never notify-all.

    Caller must pass observations of URLs removed from the reviewed manifest;
    only a real 404/410 can establish a deletion. Missing/timed-out data leaves
    the previous accepted observation in place rather than inventing a change.
    """
    if config is not None: validate_config(config)
    desired = _desired_map(inventory); when = checked_at or utc()
    if previous_state is not None and previous_state.get('property') != PROPERTY: raise IndexNowError('INVALID_STATE_PROPERTY')
    state = copy.deepcopy(previous_state) if previous_state is not None else {'schema_version': 1, 'property': PROPERTY, 'baseline_at': when, 'observed': {}, 'deliveries': {}, 'pending_changes': {}}
    if not isinstance(state.get('observed'), dict) or not isinstance(state.get('deliveries'), dict): raise IndexNowError('INVALID_STATE')
    previous = state['observed']; previous_observed_urls = set(previous); changes = []; pending = []
    outbox = state.setdefault('pending_changes', {})
    if not isinstance(outbox, dict): raise IndexNowError('INVALID_PENDING_STATE')
    for url in sorted(desired):
        observed = observations.get(url, {})
        if not _valid_live(observed, url): pending.append({'url': url, 'reason': 'DEPLOYMENT_NOT_VERIFIED_CANONICAL_INDEXABLE_HTML'}); continue
        older = previous.get(url)
        kind = 'ADDED' if older is None or older.get('deleted') else 'UPDATED'
        before = None if older is None else _content_fingerprint(older)
        after = _content_fingerprint(observed)
        if previous_state is not None and (older is None or older.get('deleted') or before != after):
            revision = (older or {}).get('revision', 0) + 1
            identity = _sha(json.dumps([url, kind, before, after, revision], separators=(',', ':')).encode())
            if identity not in state['deliveries']: changes.append({'change_id': identity, 'url': url, 'kind': kind, 'revision': revision, 'before_sha256': before, 'after_sha256': after})
        # Failed baseline observations become initial baselines later, rather
        # than retroactive new content notifications (handled below).
        previous[url] = {'body_sha256': observed['body_sha256'], 'content_sha256': observed.get('content_sha256'), 'revision': (older or {}).get('revision', 0) + (1 if previous_state is not None and (older is None or older.get('deleted') or before != after) else 0), 'checked_at': observed.get('checked_at', when), 'deleted': False}
    for url, older in list(previous.items()):
        validate_url(url)
        if url in desired or older.get('deleted'): continue
        observed = observations.get(url, {})
        if observed.get('http_status') not in {404, 410} or observed.get('error') is not None:
            pending.append({'url': url, 'reason': 'REMOVAL_NOT_CONFIRMED_BY_HTTP_404_OR_410'}); continue
        before = _content_fingerprint(older)
        revision = older.get('revision', 0) + 1
        identity = _sha(json.dumps([url, 'DELETED', before, None, revision], separators=(',', ':')).encode())
        if previous_state is not None and identity not in state['deliveries']:
            changes.append({'change_id': identity, 'url': url, 'kind': 'DELETED', 'revision': revision, 'before_sha256': before, 'after_sha256': None})
        previous[url] = {'body_sha256': None, 'revision': revision, 'checked_at': observed.get('checked_at', when), 'deleted': True}
    # Track first-seen manifest membership even if an initial fetch failed.
    previous_members = set(state.get('known_desired_urls', []))
    # Freeze initial manifest membership: a later genuinely new page whose
    # first deployment check failed must still notify when it becomes live.
    initial_members = set(state.setdefault('initial_baseline_urls', sorted(set(desired) if previous_state is None else previous_members or previous_observed_urls)))
    if previous_state is not None:
        changes = [c for c in changes if not (c['kind'] == 'ADDED' and c['url'] in initial_members and c['url'] not in previous_observed_urls)]
    for change in changes:
        # Coalesce only notifications that have never been attempted. An
        # uncertain delivery remains immutable and prevents blind replay.
        for identity, old in list(outbox.items()):
            if old.get('url') == change['url'] and identity not in state['deliveries']: del outbox[identity]
        outbox[change['change_id']] = change
    retryable = []
    for identity, change in outbox.items():
        if identity in state['deliveries']: continue
        url = validate_url(change.get('url')); observed = observations.get(url, {})
        if change.get('kind') == 'DELETED': valid = url not in desired and observed.get('http_status') in {404, 410} and not observed.get('error')
        else: valid = url in desired and _valid_live(observed, url) and _content_fingerprint(observed) == change.get('after_sha256')
        if valid: retryable.append(change)
    state['known_desired_urls'] = sorted(previous_members | set(desired)); state['last_observed_at'] = when
    return {'schema_version': 1, 'checked_at': when, 'property': PROPERTY, 'baseline_only': previous_state is None,
            'changes': retryable, 'pending': pending, 'allowed_urls': sorted(set(desired) | set(previous)), 'next_state': state, 'engine_index_status': 'UNKNOWN',
            'meaning': 'Changed-URL notifications only; no crawl or indexing assertion.'}

def apply_notifications(plan, state=None, config=None, *, requester=None, persist=None, checked_at=None):
    """Send a single non-retried POST after durable intent and public key check.

    persist(state) must save the private ledger atomically before network I/O.
    Failed/uncertain notification IDs are retained and never blindly replayed.
    If persist fails before POST, no transmission occurs. If it fails after
    POST, the pre-send UNCERTAIN ledger remains the durable safety boundary.
    """
    cfg = validate_config(config); requester = requester or default_requester
    state = copy.deepcopy(plan.get('next_state') if state is None else state)
    if state.get('property') != PROPERTY or plan.get('property') != PROPERTY: raise IndexNowError('INVALID_STATE_PROPERTY')
    if not callable(persist): raise IndexNowError('DURABLE_PERSIST_CALLBACK_REQUIRED')
    if plan.get('baseline_only') or not plan.get('changes'):
        persist(state)
        return {'status': 'BASELINE_ONLY' if plan.get('baseline_only') else 'NO_CHANGES', 'post_performed': False, 'url_count': 0, 'state': state, 'engine_index_status': 'UNKNOWN'}
    changes = []
    for change in plan['changes']:
        url = validate_url(change.get('url')); identity = change.get('change_id')
        if url not in set(plan.get('allowed_urls', [])): raise IndexNowError('URL_NOT_IN_REVIEWED_PLAN')
        if not isinstance(identity, str) or not re.fullmatch(r'[0-9a-f]{64}', identity): raise IndexNowError('INVALID_CHANGE_ID')
        if identity in state.setdefault('deliveries', {}): continue
        if change.get('kind') not in {'ADDED', 'UPDATED', 'DELETED'}: raise IndexNowError('INVALID_CHANGE_KIND')
        changes.append(change)
    if not changes:
        persist(state); return {'status': 'ALREADY_ATTEMPTED', 'post_performed': False, 'url_count': 0, 'state': state, 'engine_index_status': 'UNKNOWN'}
    if len(changes) > 10_000 or len({c['url'] for c in changes}) != len(changes): raise IndexNowError('INVALID_BATCH')
    # Ownership token is deliberately public; never substitute private API keys.
    key_check = get_url(cfg['keyLocation'], requester=requester)
    if key_check['http_status'] != 200 or key_check['body'].decode('utf-8', 'replace').strip() != cfg['key']:
        persist(state); return {'status': 'KEY_FILE_NOT_VERIFIED', 'post_performed': False, 'url_count': 0, 'state': state, 'engine_index_status': 'UNKNOWN'}
    when = checked_at or utc()
    for c in changes: state['deliveries'][c['change_id']] = {'url': c['url'], 'kind': c['kind'], 'attempted_at': when, 'status': 'UNCERTAIN', 'http_status': None}
    persist(state)
    payload = {'host': cfg['host'], 'key': cfg['key'], 'keyLocation': cfg['keyLocation'], 'urlList': [c['url'] for c in changes]}
    try:
        status, _, _ = requester('POST', ENDPOINT, {'Content-Type': 'application/json; charset=utf-8', 'Accept': 'application/json'}, json.dumps(payload).encode(), 30)
        outcome = 'RECEIVED' if status == 200 else 'KEY_VALIDATION_PENDING' if status == 202 else 'UNCERTAIN' if status >= 500 else 'REJECTED'
    except Exception: status = None; outcome = 'UNCERTAIN'
    for c in changes: state['deliveries'][c['change_id']].update(status=outcome, http_status=status, response_observed_at=utc())
    persist(state)
    return {'status': outcome, 'http_status': status, 'post_performed': True, 'url_count': len(changes), 'state': state,
            'engine_index_status': 'UNKNOWN', 'meaning': 'Receipt is not proof of crawl or indexing.'}
