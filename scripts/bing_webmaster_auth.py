#!/usr/bin/env python3
"""Owner-completed Bing Webmaster readonly OAuth, with private local storage.

The registered redirect must be a fixed 127.0.0.1 loopback callback. Whether Bing
accepts that registered URI and returns state remains UNVERIFIED until a real
owner-completed flow succeeds. No PKCE capability is assumed or invented.
Official protocol: https://learn.microsoft.com/en-us/bingwebmaster/oauth2

This helper never opens a browser, prints consent URLs or credentials, copies
cookies, bypasses login protections, or changes Google authorization.
"""
import argparse
import ctypes
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit

from discoverability_bing import (BingAuthError, READ_SCOPE, TOKEN_ENDPOINT,
                                 default_requester, refresh_bing_oauth,
                                 utc_now, validate_bing_oauth)
from google_search_console_auth import (_keychain_api, _release,
                                        AuthError as NativeKeychainError)

AUTH_ENDPOINT = 'https://www.bing.com/webmasters/oauth/authorize'
KEYCHAIN_SERVICE = 'geo-lab-bing-webmaster'
KEYCHAIN_ACCOUNT = 'monitor-readonly'
REPOSITORY = 'helen-bird/geo-index-monitor'
SECRET_NAME = 'BING_OAUTH_CREDENTIALS'
ROOT = Path(__file__).resolve().parents[1]


def validate_redirect(value):
    """Require the exact registered, non-privileged IPv4 loopback URI."""
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (ValueError, TypeError, AttributeError):
        raise BingAuthError('FIXED_LOOPBACK_REDIRECT_REQUIRED') from None
    if (not isinstance(value, str) or parsed.scheme != 'http' or
            parsed.hostname != '127.0.0.1' or not port or
            not 1024 <= port <= 65535 or parsed.username or parsed.password or
            parsed.query or parsed.fragment or parsed.path != '/oauth2callback' or
            parsed.netloc != '127.0.0.1:' + str(port) or
            value != 'http://127.0.0.1:' + str(port) + '/oauth2callback'):
        raise BingAuthError('FIXED_LOOPBACK_REDIRECT_REQUIRED')
    return port


def _outside_public(path, category):
    supplied = Path(path).expanduser()
    if supplied.is_symlink():
        raise BingAuthError(category)
    actual = supplied.resolve()
    if actual == ROOT or actual.is_relative_to(ROOT):
        raise BingAuthError(category)
    return actual


def load_client(path):
    path = _outside_public(path, 'PRIVATE_CLIENT_FILE_REQUIRED')
    try:
        if path.stat().st_mode & 0o077:
            raise BingAuthError('PRIVATE_CLIENT_FILE_PERMISSIONS_REQUIRED')
        value = json.loads(path.read_text())
    except (OSError, ValueError, UnicodeError):
        raise BingAuthError('INVALID_PRIVATE_CLIENT_JSON') from None
    if (not isinstance(value, dict) or
            any(not isinstance(value.get(k), str) or not value[k].strip()
                for k in ('client_id', 'client_secret', 'redirect_uri'))):
        raise BingAuthError('INCOMPLETE_PRIVATE_CLIENT')
    if value.get('auth_uri', AUTH_ENDPOINT) != AUTH_ENDPOINT or value.get('token_uri', TOKEN_ENDPOINT) != TOKEN_ENDPOINT:
        raise BingAuthError('UNTRUSTED_OAUTH_ENDPOINT')
    validate_redirect(value['redirect_uri'])
    return {k: value[k] for k in ('client_id', 'client_secret', 'redirect_uri')}


def write_consent_url(path, url):
    destination = _outside_public(path, 'PRIVATE_CONSENT_URL_FILE_REQUIRED')
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(destination, flags, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(url)
    except OSError:
        raise BingAuthError('PRIVATE_CONSENT_URL_WRITE_FAILED') from None
    return destination


def callback_result(path, expected_state):
    """Pure callback validation; an invalid/missing state never yields a code."""
    try:
        parsed = urlsplit(path)
        if parsed.path != '/oauth2callback' or parsed.scheme or parsed.netloc or parsed.fragment:
            return {'ok': False, 'http_status': 400, 'reason': 'INVALID_CALLBACK_PATH'}
        params = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=12)
    except (ValueError, TypeError):
        return {'ok': False, 'http_status': 400, 'reason': 'INVALID_CALLBACK_QUERY'}
    states = params.get('state', [])
    if len(states) != 1 or not states[0]:
        return {'ok': False, 'http_status': 400, 'reason': 'CALLBACK_STATE_REQUIRED'}
    if (not isinstance(expected_state, str) or not expected_state or
            not secrets.compare_digest(states[0].encode(), expected_state.encode())):
        return {'ok': False, 'http_status': 400, 'reason': 'CALLBACK_STATE_MISMATCH'}
    codes, errors = params.get('code', []), params.get('error', [])
    if len(errors) == 1 and errors[0] and not codes:
        return {'ok': True, 'http_status': 200, 'error': 'OWNER_AUTHORIZATION_DECLINED'}
    if (len(codes) != 1 or not codes[0] or errors or len(codes[0]) > 8192 or
            any(ord(c) < 32 for c in codes[0])):
        return {'ok': False, 'http_status': 400, 'reason': 'INVALID_CALLBACK_RESULT'}
    return {'ok': True, 'http_status': 200, 'code': codes[0]}


def callback_handler(expected_state, port, outcome, rejections):
    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.headers.get('Host') != '127.0.0.1:' + str(port):
                result = {'ok': False, 'http_status': 400, 'reason': 'INVALID_CALLBACK_HOST'}
            else:
                result = callback_result(self.path, expected_state)
            if result['ok']:
                if not outcome:
                    outcome.update({k: result[k] for k in ('code', 'error') if k in result})
                message = b'Authorization received. Return to your local app. You may close this tab.'
            else:
                rejections.append(result['reason'])
                message = b'Invalid authorization callback. No credentials were exchanged.'
            self.send_response(result['http_status'])
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.end_headers()
            self.wfile.write(message)
    return Callback


def exchange_code(client, code, *, requester=None):
    body = urlencode({'grant_type': 'authorization_code', 'code': code,
                      'client_id': client['client_id'], 'client_secret': client['client_secret'],
                      'redirect_uri': client['redirect_uri']}).encode()
    try:
        status, _, payload = (requester or default_requester)('POST', TOKEN_ENDPOINT,
            {'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'}, body, 30)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        raise BingAuthError('CODE_EXCHANGE_UNCERTAIN_NO_RETRY') from None
    if not 200 <= status < 300:
        raise BingAuthError('CODE_EXCHANGE_REJECTED' if status in (400, 401, 403) else
                            'CODE_EXCHANGE_QUOTA_EXCEEDED' if status == 429 else 'CODE_EXCHANGE_HTTP_ERROR', status)
    if (not isinstance(payload, dict) or payload.get('_invalid_json') or
            str(payload.get('token_type', '')).lower() != 'bearer' or
            not isinstance(payload.get('access_token'), str) or not payload['access_token']):
        raise BingAuthError('INVALID_CODE_EXCHANGE_RESPONSE')
    declarations = {k: payload[k] for k in ('scope', 'scopes') if k in payload}
    credential = {'type': 'authorized_user', 'client_id': client['client_id'],
                  'client_secret': client['client_secret'], 'refresh_token': payload.get('refresh_token'),
                  'token_uri': TOKEN_ENDPOINT, 'scopes': [READ_SCOPE],
                  'scope_source': 'token_response' if declarations else 'requested_scope_unchanged_per_oauth_response',
                  'created_at': utc_now(), 'grant_source': 'owner_completed_authorization_code_flow'}
    # Validate all returned scope declarations; none may broaden the grant.
    validate_bing_oauth({**credential, **declarations})
    return validate_bing_oauth(credential)


def authorize(client_file, *, timeout=600, announce=None, authorization_url_file=None,
              server_factory=HTTPServer, requester=None, monotonic=time.monotonic):
    client = load_client(client_file)
    if announce is not None and not callable(announce):
        raise BingAuthError('INVALID_URL_ANNOUNCER')
    if announce is None and authorization_url_file is None:
        raise BingAuthError('PRIVATE_CONSENT_URL_DESTINATION_REQUIRED')
    port = validate_redirect(client['redirect_uri'])
    state = secrets.token_urlsafe(32)
    outcome, rejections = {}, []
    handler = callback_handler(state, port, outcome, rejections)
    try:
        server = server_factory(('127.0.0.1', port), handler)
    except OSError:
        raise BingAuthError('REGISTERED_LOOPBACK_PORT_UNAVAILABLE') from None
    try:
        server.timeout = 1
        url = AUTH_ENDPOINT + '?' + urlencode({'client_id': client['client_id'],
            'redirect_uri': client['redirect_uri'], 'response_type': 'code',
            'scope': READ_SCOPE, 'state': state})
        if authorization_url_file is not None:
            write_consent_url(authorization_url_file, url)
        if announce is not None:
            announce(url)
        deadline = monotonic() + max(1, min(timeout, 900))
        while not outcome and monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()
    if not outcome:
        if 'CALLBACK_STATE_REQUIRED' in rejections:
            raise BingAuthError('CALLBACK_STATE_NOT_RETURNED_NO_TOKEN_EXCHANGE')
        raise BingAuthError('AUTHORIZATION_TIMEOUT')
    if outcome.get('error'):
        raise BingAuthError(outcome['error'])
    return exchange_code(client, outcome['code'], requester=requester)


def _native_api(factory):
    try:
        return (factory or _keychain_api)()
    except NativeKeychainError as error:
        raise BingAuthError(error.code) from None


def keychain_load(*, api_factory=None):
    api = _native_api(api_factory)
    service, account = KEYCHAIN_SERVICE.encode(), KEYCHAIN_ACCOUNT.encode()
    length, data = ctypes.c_uint32(), ctypes.c_void_p()
    status = api.SecKeychainFindGenericPassword(None, len(service), service, len(account), account,
                                               ctypes.byref(length), ctypes.byref(data), None)
    if status == -25300:
        raise BingAuthError('AUTH_REQUIRED')
    if status:
        raise BingAuthError('KEYCHAIN_ACCESS_FAILED')
    try:
        try:
            value = json.loads(ctypes.string_at(data, length.value).decode())
        except (ValueError, UnicodeError):
            raise BingAuthError('INVALID_KEYCHAIN_CREDENTIAL_JSON') from None
    finally:
        api.SecKeychainItemFreeContent(None, data)
    return validate_bing_oauth(value)


def keychain_save(credentials, *, api_factory=None, releaser=None):
    credentials = validate_bing_oauth(credentials)
    api = _native_api(api_factory)
    service, account = KEYCHAIN_SERVICE.encode(), KEYCHAIN_ACCOUNT.encode()
    item = ctypes.c_void_p()
    value = json.dumps(credentials, separators=(',', ':')).encode()
    status = api.SecKeychainFindGenericPassword(None, len(service), service, len(account), account,
                                               None, None, ctypes.byref(item))
    try:
        if status == -25300:
            status = api.SecKeychainAddGenericPassword(None, len(service), service, len(account), account,
                                                      len(value), value, None)
        elif status == 0:
            status = api.SecKeychainItemModifyAttributesAndData(item, None, len(value), value)
        if status:
            raise BingAuthError('KEYCHAIN_WRITE_FAILED')
    finally:
        (releaser or _release)(item)


def install_github_secret(repository=REPOSITORY, *, credentials=None, runner=subprocess.run):
    if repository != REPOSITORY:
        raise BingAuthError('UNAPPROVED_PRIVATE_REPOSITORY')
    credential = validate_bing_oauth(keychain_load() if credentials is None else credentials)
    gh = shutil.which('gh') or str(Path.home()/'.local/bin/gh')
    result = runner([gh, 'api', 'repos/'+repository, '--jq', '{private,has_pages,full_name}'],
                    capture_output=True, text=True)
    if result.returncode:
        raise BingAuthError('GITHUB_REPOSITORY_CHECK_FAILED')
    try:
        metadata = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise BingAuthError('INVALID_GITHUB_REPOSITORY_RESPONSE') from None
    if (not isinstance(metadata, dict) or metadata.get('private') is not True or
            metadata.get('has_pages') is not False or metadata.get('full_name') != REPOSITORY):
        raise BingAuthError('PRIVATE_MONITOR_WITHOUT_PAGES_REQUIRED')
    payload = {k: credential[k] for k in ('type', 'client_id', 'client_secret', 'refresh_token', 'token_uri', 'scopes')}
    result = runner([gh, 'secret', 'set', SECRET_NAME, '--repo', repository],
                    input=json.dumps(payload), capture_output=True, text=True)
    if result.returncode:
        raise BingAuthError('GITHUB_SECRET_CONFIGURATION_FAILED')
    return {'configured': True, 'repository': repository, 'secret_name': SECRET_NAME,
            'scope': READ_SCOPE, 'credential_values_printed': False}


def check_monitor_credential(*, credentials=None, requester=None):
    refresh_bing_oauth(keychain_load() if credentials is None else credentials, requester=requester)
    return {'status': 'TOKEN_REFRESH_SUCCEEDED', 'scope': READ_SCOPE,
            'index_inspection_performed': False, 'credential_values_printed': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    auth = commands.add_parser('authorize')
    auth.add_argument('--client-file', required=True)
    auth.add_argument('--url-file', required=True, help='Private consent URL destination outside the public checkout; not printed.')
    auth.add_argument('--timeout', type=int, default=600)
    install = commands.add_parser('configure-github-secret')
    install.add_argument('--repository', default=REPOSITORY)
    commands.add_parser('check-monitor-credential')
    args = parser.parse_args(argv)
    try:
        if args.command == 'authorize':
            def announce(_):
                print(json.dumps({'status': 'WAITING_FOR_OWNER_READONLY_CONSENT',
                    'scope': READ_SCOPE, 'consent_url_printed': False}), flush=True)
            credential = authorize(args.client_file, timeout=args.timeout, announce=announce,
                                   authorization_url_file=args.url_file)
            keychain_save(credential)
            result = {'status': 'AUTHORIZED', 'scope': READ_SCOPE, 'stored_in': 'macOS Keychain',
                      'scope_source': credential['scope_source'], 'credential_values_printed': False,
                      'loopback_and_state_support': 'CONFIRMED_BY_THIS_COMPLETED_FLOW'}
        elif args.command == 'configure-github-secret':
            result = install_github_secret(args.repository)
        else:
            result = check_monitor_credential()
        print(json.dumps(result))
        return 0
    except BingAuthError as error:
        print(json.dumps({'status': 'AUTH_REQUIRED' if error.code == 'AUTH_REQUIRED' else 'AUTH_ERROR',
                          'error': error.code, 'http_status': error.status,
                          'credential_values_printed': False}))
        return 2
    except Exception:
        print(json.dumps({'status': 'AUTH_ERROR', 'error': 'INTERNAL_AUTHORIZATION_FAILURE',
                          'credential_values_printed': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
