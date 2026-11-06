#!/usr/bin/env python3
"""Official Bing Webmaster REST observations, separate from Google and AI indexing.

GetUrlInfo's documented IsPage is not an index-membership verdict. Preserve its
actual fields and crawl evidence while leaving membership UNKNOWN. This module
never submits ordinary URLs. SubmitFeed is a separate, explicitly called helper.

Official references:
https://learn.microsoft.com/en-us/bingwebmaster/oauth2
https://learn.microsoft.com/en-us/dotnet/api/microsoft.bing.webmaster.api.interfaces.iwebmasterapi.geturlinfo
https://learn.microsoft.com/en-us/dotnet/api/microsoft.bing.webmaster.api.interfaces.iwebmasterapi.getfeeds
https://learn.microsoft.com/en-us/dotnet/api/microsoft.bing.webmaster.api.interfaces.iwebmasterapi.submitfeed
"""
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, quote_plus, unquote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

PROPERTY = 'https://helen-bird.github.io/geo-platform-observation/'
SITEMAP = PROPERTY + 'sitemap.xml'
READ_SCOPE = 'Webmaster.read'
MANAGE_SCOPE = 'Webmaster.manage'
OAUTH_BASE = 'https://www.bing.com/webmaster/api.svc/json/'
API_KEY_BASE = 'https://ssl.bing.com/webmaster/api.svc/json/'
TOKEN_ENDPOINT = 'https://www.bing.com/webmasters/oauth/token'
ROOT = Path(__file__).resolve().parents[1]
GET_METHODS = {'GetUserSites', 'GetUrlInfo', 'GetFeeds'}


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def canonical_guard(url):
    if not isinstance(url, str):
        raise ValueError('URL_OUTSIDE_APPROVED_PROPERTY')
    parsed = urlsplit(url)
    decoded = unquote(parsed.path)
    if (not url.startswith(PROPERTY) or parsed.scheme != 'https' or
            parsed.netloc != 'helen-bird.github.io' or parsed.query or
            parsed.fragment or parsed.username or parsed.password or
            any(p in {'.', '..'} for p in decoded.split('/')) or
            decoded.endswith('/index.html')):
        raise ValueError('URL_OUTSIDE_APPROVED_PROPERTY')
    return url


def normalize_bing_date(value):
    """Normalize ISO or Microsoft JSON dates, retaining raw values separately.

    The numeric JSON value is epoch milliseconds; a trailing timezone suffix is
    metadata and must not be added to that epoch a second time. Year-one default
    dates are absent evidence, not a proof of a historic crawl.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        match = re.fullmatch(r'/Date\((-?\d+)([+-]\d{4})?\)/', value)
        if match:
            stamp = dt.datetime.fromtimestamp(int(match.group(1)) / 1000, dt.timezone.utc)
        else:
            stamp = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
            if stamp.tzinfo is None:
                return None
        if stamp.year <= 1970:
            return None
        return stamp.astimezone(dt.timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def unwrap(payload):
    return payload.get('d') if isinstance(payload, dict) and 'd' in payload else payload


def classify_url_info(payload):
    raw = unwrap(payload)
    if not isinstance(raw, dict):
        raw = {}
    discovered = normalize_bing_date(raw.get('DiscoveryDate'))
    crawled = normalize_bing_date(raw.get('LastCrawledDate'))
    return {
        'status': 'UNKNOWN', 'index_status': 'UNKNOWN',
        'lifecycle': 'CRAWLED' if crawled else 'DISCOVERED' if discovered else 'UNKNOWN',
        'discovery_time': discovered, 'last_crawl_time': crawled,
        'raw_discovery_date': raw.get('DiscoveryDate'),
        'raw_last_crawled_date': raw.get('LastCrawledDate'),
        'classification_source': 'official_bing_get_url_info_fields',
        'classification_note': 'Documented GetUrlInfo fields do not establish index membership; IsPage, HTTP status and crawl dates are not indexing verdicts.',
    }


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def default_requester(method, url, headers, body, timeout):
    context = ssl.create_default_context(cafile='/etc/ssl/cert.pem' if Path('/etc/ssl/cert.pem').is_file() else None)
    opener = build_opener(_NoRedirect(), HTTPSHandler(context=context))
    try:
        response = opener.open(Request(url, data=body, headers=headers, method=method), timeout=timeout)
    except HTTPError as error:
        response = error
    with response:
        data = response.read(4_000_001)
        if len(data) > 4_000_000:
            raise ValueError('RESPONSE_TOO_LARGE')
        try:
            payload = json.loads(data) if data.strip() else None
        except (ValueError, UnicodeError):
            payload = {'_invalid_json': True}
        return response.code, dict(response.headers.items()), payload


class BingAuthError(RuntimeError):
    """Safe error category only; never carries credentials or provider text."""
    def __init__(self, code, status=None):
        self.code, self.status = code, status
        super().__init__(code)


def _declared_readonly_scope(value):
    if isinstance(value, str):
        values = value.split()
    elif isinstance(value, (list, tuple)) and all(isinstance(s, str) for s in value):
        values = list(value)
    else:
        return False
    return bool(values) and {s.lower() for s in values} == {READ_SCOPE.lower()}


def validate_bing_oauth(credentials):
    """Validate the grant metadata supplied through Keychain/Actions Secret.

    The declared scope must originate from the owner-approved OAuth grant. This
    function cannot introspect a provider token or independently prove a grant.
    """
    if not isinstance(credentials, dict) or credentials.get('type') != 'authorized_user':
        raise BingAuthError('AUTHORIZED_USER_CREDENTIAL_REQUIRED')
    declared = [credentials[k] for k in ('scopes', 'scope') if k in credentials]
    if not declared or not all(_declared_readonly_scope(value) for value in declared):
        raise BingAuthError('EXACT_READONLY_SCOPE_REQUIRED')
    if credentials.get('token_uri', TOKEN_ENDPOINT) != TOKEN_ENDPOINT:
        raise BingAuthError('UNTRUSTED_TOKEN_ENDPOINT')
    if any(not isinstance(credentials.get(key), str) or not credentials[key].strip()
           for key in ('client_id', 'client_secret', 'refresh_token')):
        raise BingAuthError('INCOMPLETE_OAUTH_CREDENTIAL')
    return credentials


def load_bing_oauth_from_env(env=None):
    """Read an encrypted-secret injection, never a credential file or argv."""
    value = (os.environ if env is None else env).get('BING_OAUTH_CREDENTIALS')
    if not isinstance(value, str) or not value:
        raise BingAuthError('AUTH_REQUIRED')
    if len(value) > 100_000:
        raise BingAuthError('INVALID_OAUTH_SECRET_JSON')
    try:
        decoded = json.loads(value)
    except (ValueError, TypeError):
        raise BingAuthError('INVALID_OAUTH_SECRET_JSON') from None
    return validate_bing_oauth(decoded)


def refresh_bing_oauth(credentials=None, *, requester=None):
    """Exchange a validated readonly grant for one ephemeral bearer token.

    Exactly one request: refresh can rotate provider state, so uncertainty is not
    blindly retried. A changed refresh token requires a separate secure Secret
    update; it is never written to monitoring state or returned to the caller.
    The caller must mask the returned access token before its next API call.
    """
    credentials = validate_bing_oauth(load_bing_oauth_from_env() if credentials is None else credentials)
    body = urlencode({'grant_type': 'refresh_token', 'client_id': credentials['client_id'],
                      'client_secret': credentials['client_secret'],
                      'refresh_token': credentials['refresh_token']}).encode()
    headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json',
               'User-Agent': 'GEO-Lab-Bing-Monitor/1.0'}
    try:
        status, _, payload = (requester or default_requester)('POST', TOKEN_ENDPOINT, headers, body, 30)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        raise BingAuthError('TOKEN_REQUEST_UNCERTAIN_NO_RETRY') from None
    if status == 429:
        raise BingAuthError('TOKEN_QUOTA_EXCEEDED', status)
    if 500 <= status < 600:
        raise BingAuthError('TOKEN_SERVER_ERROR_NO_RETRY', status)
    if not 200 <= status < 300:
        code = payload.get('error') if isinstance(payload, dict) else None
        raise BingAuthError('AUTH_EXPIRED' if code == 'invalid_grant' else 'TOKEN_AUTH_REJECTED' if status in (400, 401, 403) else 'TOKEN_HTTP_ERROR', status)
    if not isinstance(payload, dict) or payload.get('_invalid_json'):
        raise BingAuthError('INVALID_TOKEN_RESPONSE', status)
    for key in ('scope', 'scopes'):
        if key in payload and not _declared_readonly_scope(payload[key]):
            raise BingAuthError('GRANTED_SCOPE_CHANGED', status)
    returned_refresh = payload.get('refresh_token')
    if returned_refresh is not None and returned_refresh != credentials['refresh_token']:
        raise BingAuthError('ROTATION_REQUIRES_SECURE_SECRET_UPDATE', status)
    token = payload.get('access_token')
    if (not isinstance(token, str) or not token or
            str(payload.get('token_type', '')).lower() != 'bearer'):
        raise BingAuthError('INVALID_TOKEN_RESPONSE', status)
    return token


class BingClient:
    """A fixed-property client. Credentials never enter returned state/errors.

    requester signature: (method, url, headers, body_bytes_or_none, timeout)
    -> (http_status, response_headers, decoded_json_or_none).
    OAuth scope spelling follows Microsoft's listed Webmaster.read/manage.
    API keys are account-wide credentials and are never described as readonly.
    """
    def __init__(self, access_token=None, api_key=None, *, scope=READ_SCOPE,
                 allow_write=False, requester=None, sleep=time.sleep):
        if access_token and api_key:
            raise ValueError('SELECT_ONE_BING_AUTHENTICATION_METHOD')
        if scope not in {READ_SCOPE, MANAGE_SCOPE, 'webmaster.read', 'webmaster.manage'}:
            raise ValueError('UNEXPECTED_BING_SCOPE')
        self._access_token, self._api_key = access_token, api_key
        self.scope, self.allow_write = scope, allow_write
        self.requester, self.sleep = requester or default_requester, sleep

    @property
    def authenticated(self):
        return bool(self._access_token or self._api_key)

    @property
    def authentication(self):
        return {'method': 'oauth_bearer' if self._access_token else 'api_key' if self._api_key else 'none',
                'scope': self.scope if self._access_token else None,
                'scope_validation': 'Caller-declared scope; opaque access token is not introspected by this client' if self._access_token else None,
                'readonly_scoped': bool(self._access_token) and self.scope.lower() == READ_SCOPE.lower(),
                'api_key_scope_note': 'Account-wide verified-site credential; not readonly-scoped' if self._api_key else None}

    def _safe(self, value):
        """Retain API fields while removing any echoed credential values."""
        forbidden = {'apikey', 'api_key', 'access_token', 'refresh_token', 'client_secret', 'authorization'}
        if isinstance(value, dict):
            return {k: self._safe(v) for k, v in value.items() if str(k).lower() not in forbidden}
        if isinstance(value, list):
            return [self._safe(v) for v in value]
        if isinstance(value, str):
            # Provider faults may echo a full request URL. Remove credential
            # query parameters entirely, not just their values: durable-state
            # scanning rejects even a redacted apiKey query parameter.
            pattern = r'([?&])(?:apikey|api_key|access_token|refresh_token|client_secret|authorization)=[^&\s"<>]*(&?)'
            # Re-run for adjacent credential parameters whose separating '&'
            # was consumed by the previous substitution.
            while re.search(pattern, value, flags=re.I):
                value = re.sub(pattern, lambda match: match.group(1) if match.group(2) else '', value, flags=re.I)
            for secret in (self._access_token, self._api_key):
                if secret:
                    for encoded in {secret, quote(secret, safe=''), quote_plus(secret, safe='')}:
                        value = value.replace(encoded, '[REDACTED]')
            return value
        return value

    def _call(self, operation, params=None, *, method='GET'):
        if operation not in GET_METHODS | {'SubmitFeed'} or method not in {'GET', 'POST'}:
            raise ValueError('UNAPPROVED_BING_OPERATION')
        if (operation == 'SubmitFeed') != (method == 'POST'):
            raise ValueError('UNAPPROVED_BING_METHOD')
        if not self.authenticated:
            return {'ok': False, 'query_status': 'AUTH_REQUIRED', 'error': {'category': 'AUTH_REQUIRED'}, 'attempts': [], 'raw_response': None}
        if method == 'POST' and (not self.allow_write or (self._access_token and self.scope.lower() != MANAGE_SCOPE.lower())):
            return {'ok': False, 'query_status': 'PERMISSION_DENIED', 'error': {'category': 'WRITE_AUTHORIZATION_REQUIRED'}, 'attempts': [], 'raw_response': None}
        params = dict(params or {})
        base = OAUTH_BASE if self._access_token else API_KEY_BASE
        query = dict(params) if method == 'GET' else {}
        if self._api_key:
            query['apikey'] = self._api_key
        url = base + operation + ('?' + urlencode(query) if query else '')
        headers = {'Accept': 'application/json', 'User-Agent': 'GEO-Lab-Bing-Monitor/1.0'}
        if self._access_token:
            headers['Authorization'] = 'Bearer ' + self._access_token
        body = json.dumps(params).encode() if method == 'POST' else None
        if body is not None:
            headers['Content-Type'] = 'application/json; charset=utf-8'
        attempts = []
        for attempt in range(1, (3 if method == 'GET' else 1) + 1):
            try:
                status, response_headers, payload = self.requester(method, url, headers, body, 30)
            except (HTTPError, URLError, TimeoutError, OSError, ValueError):
                attempts.append({'operation': operation, 'method': method, 'attempt': attempt, 'checked_at': utc_now(), 'error': 'NETWORK_OR_INVALID_RESPONSE'})
                if method == 'GET' and attempt < 3:
                    self.sleep(2 ** (attempt - 1)); continue
                return {'ok': False, 'query_status': 'ERROR', 'error': {'category': 'NETWORK_OR_INVALID_RESPONSE'}, 'attempts': attempts, 'raw_response': None, 'delivery_uncertain': method == 'POST'}
            attempts.append({'operation': operation, 'method': method, 'attempt': attempt, 'checked_at': utc_now(), 'http_status': status})
            if status == 429 or 500 <= status < 600:
                if method == 'GET' and attempt < 3:
                    retry = response_headers.get('Retry-After', '')
                    self.sleep(min(30, int(retry)) if str(retry).isdigit() else 2 ** (attempt - 1)); continue
                category = 'QUOTA_EXCEEDED' if status == 429 else 'SERVER_ERROR'
            elif status == 401:
                category = 'AUTH_REQUIRED'
            elif status == 403:
                category = 'PERMISSION_DENIED'
            elif not 200 <= status < 300:
                category = 'HTTP_ERROR'
            elif isinstance(payload, dict) and payload.get('_invalid_json'):
                category = 'INVALID_API_RESPONSE'
            elif isinstance(unwrap(payload), dict) and any(k in unwrap(payload) for k in ('ErrorCode', 'ErrorMessage')):
                category = 'API_FAULT'
            else:
                return {'ok': True, 'query_status': 'SUCCESS', 'http_status': status, 'payload': self._safe(payload), 'raw_response': self._safe(payload), 'attempts': attempts}
            return {'ok': False, 'query_status': category if category in {'AUTH_REQUIRED', 'PERMISSION_DENIED', 'QUOTA_EXCEEDED'} else 'ERROR',
                    'error': {'category': category, 'http_status': status}, 'raw_response': self._safe(payload), 'attempts': attempts,
                    'delivery_uncertain': method == 'POST' and (status >= 500 or category == 'INVALID_API_RESPONSE')}

    def get_user_sites(self):
        response = self._call('GetUserSites')
        if response['ok'] and not isinstance(unwrap(response.get('payload')), list):
            return {**response, 'ok': False, 'query_status': 'ERROR', 'error': {'category': 'INVALID_SITES_RESPONSE'}}
        return response

    def get_url_info(self, url):
        response = self._call('GetUrlInfo', {'siteUrl': PROPERTY, 'url': canonical_guard(url)})
        if response['ok'] and not isinstance(unwrap(response.get('payload')), dict):
            return {**response, 'ok': False, 'query_status': 'ERROR', 'error': {'category': 'INVALID_URL_INFO_RESPONSE'}}
        return response

    def get_feeds(self):
        return self._call('GetFeeds', {'siteUrl': PROPERTY})

    def submit_feed(self):
        return self._call('SubmitFeed', {'siteUrl': PROPERTY, 'feedUrl': SITEMAP}, method='POST')


def sitemap_observation(client, checked_at=None):
    response = client.get_feeds()
    feeds = unwrap(response.get('payload'))
    if response['ok'] and not isinstance(feeds, list):
        response = {**response, 'ok': False, 'query_status': 'ERROR', 'error': {'category': 'INVALID_FEEDS_RESPONSE'}}
    selected = [f for f in feeds if isinstance(f, dict) and f.get('Url') == SITEMAP] if isinstance(feeds, list) else []
    feed = selected[0] if selected else None
    return {'engine': 'bing', 'source': 'official_bing_get_feeds_api', 'checked_at': checked_at or utc_now(),
            'property': PROPERTY, 'sitemap_url': SITEMAP, 'query_status': response['query_status'], 'query_success': response['ok'],
            'registered': bool(feed) if response['ok'] else None, 'registration_status': 'REGISTERED' if feed else 'NOT_RETURNED' if response['ok'] else 'UNKNOWN',
            'processing_status': feed.get('Status') if feed else 'UNKNOWN',
            'submitted_time': normalize_bing_date(feed.get('Submitted')) if feed else None,
            'last_crawl_time': normalize_bing_date(feed.get('LastCrawled')) if feed else None,
            'raw_submitted': feed.get('Submitted') if feed else None,
            'raw_last_crawled': feed.get('LastCrawled') if feed else None,
            'raw_response': response.get('raw_response'), 'error': response.get('error'), 'attempts': response.get('attempts', []),
            'matching_feed_count': len(selected),
            'note': 'Feed registration and crawl status are separate from individual URL indexing; not returned does not prove never submitted.'}


def property_site_observation(response):
    """Minimize an account-wide GetUserSites result to this exact property.

    Keep the provider's matching-row values, but not unrelated websites or
    top-level account metadata. This is explicitly a filtered response, not an
    assertion that the account has no other sites.
    """
    original = response.get('raw_response')
    sites = unwrap(original)
    matching = [row for row in sites if isinstance(row, dict) and row.get('Url') == PROPERTY] if isinstance(sites, list) else None
    filtered = {'d': matching} if isinstance(original, dict) and 'd' in original and matching is not None else matching
    return {'query_status': response['query_status'], 'raw_response': filtered,
            'filtered': True, 'filter_rule': 'Exact Url match to approved PROPERTY only; unrelated sites and account metadata omitted',
            'property': PROPERTY, 'matching_site_count': len(matching) if matching is not None else None,
            'error': response.get('error'), 'attempts': response['attempts']}


def inspect_urls(entries, client=None, checked_at=None):
    client = client or BingClient()
    stamp = checked_at or utc_now()
    urls = [e['url'] if isinstance(e, dict) else e for e in entries]
    if not urls or len(urls) > 250 or len(set(urls)) != len(urls):
        raise ValueError('INVALID_CANONICAL_URL_LIST')
    for url in urls:
        canonical_guard(url)
    sites = client.get_user_sites()
    rows = []
    for url in urls:
        response = client.get_url_info(url)
        row = {'engine': 'bing', 'source': 'official_bing_get_url_info_api' if response['attempts'] else 'not_queried_auth_required',
               'url': url, 'checked_at': utc_now() if checked_at is None else stamp,
               'query_success': response['ok'], 'query_status': response['query_status'], 'error': response.get('error'),
               'raw_response': response.get('raw_response'), 'api_attempts': response['attempts']}
        row.update(classify_url_info(response.get('payload')))
        rows.append(row)
    sitemap = sitemap_observation(client, stamp)
    complete = all(r['query_success'] for r in rows) and sites['ok'] and sitemap['query_success']
    auth_failed = not client.authenticated or any(r['query_status'] == 'AUTH_REQUIRED' for r in rows)
    return {'engine': 'bing', 'schema_version': 1, 'checked_at': stamp, 'property': PROPERTY,
            'source': 'official_bing_webmaster_rest_api', 'authentication': client.authentication,
            'site_access_observation': property_site_observation(sites),
            'results': rows, 'counts': {'INDEXED': 0, 'NOT_INDEXED': 0, 'UNKNOWN': len(rows)},
            'queries_succeeded': sum(r['query_success'] for r in rows),
            'api_inspections_succeeded': sum(r['query_success'] for r in rows),
            'api_requests_attempted': len(sites['attempts']) + sum(len(r['api_attempts']) for r in rows) + len(sitemap['attempts']),
            'run_complete': complete,
            'url_queries_complete': all(r['query_success'] for r in rows),
            'run_status': 'SUCCESS_WITH_UNKNOWN_MEMBERSHIP' if complete else 'AUTH_REQUIRED' if auth_failed else 'PARTIAL_FAILURE',
            'sitemap_observation': sitemap,
            'indexing_requested': False, 'live_test_performed': False,
            'membership_note': 'The documented GetUrlInfo API has no definitive index-membership field. Actual returned crawl evidence is retained independently.'}


def _write_private(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True); stream.write('\n')
    os.replace(temporary, path)


def _private_ledger_path(path, private_runtime_verified=False):
    supplied = Path(path).expanduser()
    if supplied.is_symlink():
        raise ValueError('PRIVATE_LEDGER_JSON_REQUIRED')
    path = supplied.resolve()
    if path == ROOT or path.is_relative_to(ROOT):
        allowed = False
        if private_runtime_verified:
            try:
                remote = subprocess.check_output(['git', 'config', '--get', 'remote.origin.url'], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip().removesuffix('.git')
                allowed = remote in {'https://github.com/helen-bird/geo-index-monitor', 'git@github.com:helen-bird/geo-index-monitor'}
            except (OSError, subprocess.CalledProcessError):
                pass
        if not allowed:
            raise ValueError('PRIVATE_LEDGER_REQUIRED')
    if path.suffix != '.json' or path.is_symlink():
        raise ValueError('PRIVATE_LEDGER_JSON_REQUIRED')
    return path


def submit_sitemap_once(client, ledger_path, *, checked_at=None, private_runtime_verified=False):
    """Explicit setup operation; never called by routine inspect_urls.

    Existing exact registration is preserved without another POST. An uncertain
    attempt is never blindly retried even if later GetFeeds has not returned it.
    """
    path = _private_ledger_path(ledger_path, private_runtime_verified)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = path.parent / 'sitemap-submission.lock'
    with lock.open('a+') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        ledger = json.loads(path.read_text()) if path.exists() else {'engine': 'bing', 'property': PROPERTY, 'sitemap_url': SITEMAP, 'events': [], 'submission_status': 'NOT_ATTEMPTED'}
        if ledger.get('engine') != 'bing' or ledger.get('property') != PROPERTY or ledger.get('sitemap_url') != SITEMAP:
            raise ValueError('INVALID_BING_SUBMISSION_LEDGER')
        observation = sitemap_observation(client, checked_at)
        ledger['latest_observation'] = observation
        stamp = checked_at or utc_now()
        if ledger['submission_status'] in {'SUBMITTED', 'ALREADY_REGISTERED', 'REGISTERED_AFTER_UNCERTAIN_ATTEMPT'}:
            _write_private(path, ledger); return ledger
        if observation['registered'] is True:
            uncertain = ledger['submission_status'] in {'ATTEMPT_STARTED', 'UNCERTAIN'}
            ledger['submission_status'] = 'REGISTERED_AFTER_UNCERTAIN_ATTEMPT' if uncertain else 'ALREADY_REGISTERED'
            ledger['events'].append({'event': ledger['submission_status'], 'observed_at': stamp, 'note': 'Exact feed is already returned by Bing; no new submission attributed to this helper.'})
        elif ledger['submission_status'] in {'ATTEMPT_STARTED', 'UNCERTAIN', 'REJECTED'}:
            if ledger['submission_status'] == 'ATTEMPT_STARTED':
                ledger['submission_status'] = 'UNCERTAIN'
            ledger['events'].append({'event': 'NO_AUTOMATIC_RESUBMISSION', 'observed_at': stamp})
        elif not observation['query_success']:
            ledger['submission_status'] = 'AUTH_REQUIRED' if observation['query_status'] == 'AUTH_REQUIRED' else 'PRECHECK_FAILED'
        elif not client.allow_write or (client.authentication['method'] == 'oauth_bearer' and client.scope.lower() != MANAGE_SCOPE.lower()):
            ledger['submission_status'] = 'WRITE_AUTHORIZATION_REQUIRED'
        else:
            ledger['submission_status'] = 'ATTEMPT_STARTED'
            ledger['events'].append({'event': 'SUBMISSION_STARTED', 'at': stamp})
            _write_private(path, ledger)
            response = client.submit_feed()
            ledger['submission_response'] = response
            ledger['submission_status'] = 'SUBMITTED' if response['ok'] else 'UNCERTAIN' if response.get('delivery_uncertain') else 'REJECTED'
            ledger['events'].append({'event': ledger['submission_status'], 'at': utc_now(), 'http_status': response.get('http_status', (response.get('error') or {}).get('http_status'))})
            if response['ok']:
                ledger['latest_observation'] = sitemap_observation(client)
        _write_private(path, ledger)
        return ledger
