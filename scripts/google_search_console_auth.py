#!/usr/bin/env python3
"""Minimal Google installed-app OAuth helpers; credentials never enter logs/argv.

Monitor credentials are readonly. A separate temporary local grant is used for
Sitemaps submission. No browser session/cookie or service-account extraction.
"""
import argparse
import base64
import ctypes
import datetime
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import ssl
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

READONLY_SCOPE = 'https://www.googleapis.com/auth/webmasters.readonly'
WRITE_SCOPE = 'https://www.googleapis.com/auth/webmasters'
TOKEN_URI = 'https://oauth2.googleapis.com/token'
AUTH_URI = 'https://accounts.google.com/o/oauth2/v2/auth'
KEYCHAIN_SERVICE = 'geo-lab-search-console'
ACCOUNTS = {'monitor': 'monitor-readonly', 'sitemap': 'sitemap-once'}


class AuthError(RuntimeError):
    """Safe public error; never contains provider bodies or credential values."""
    def __init__(self, code, status=None):
        self.code, self.status = code, status
        super().__init__(code + (f' (HTTP {status})' if status else ''))


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def scopes_of(value):
    if isinstance(value, str): return set(value.split())
    if isinstance(value, list) and all(isinstance(x, str) for x in value): return set(value)
    return set()


def validate_credentials(credentials, mode='monitor'):
    if mode not in ACCOUNTS: raise AuthError('INVALID_AUTH_MODE')
    if not isinstance(credentials, dict) or credentials.get('type', 'authorized_user') != 'authorized_user':
        raise AuthError('UNSUPPORTED_CREDENTIAL_TYPE')
    if credentials.get('token_uri', TOKEN_URI) != TOKEN_URI:
        raise AuthError('UNTRUSTED_TOKEN_ENDPOINT')
    if not all(isinstance(credentials.get(k), str) and credentials[k] for k in ('client_id', 'client_secret', 'refresh_token')):
        raise AuthError('AUTH_REQUIRED')
    required = {READONLY_SCOPE if mode == 'monitor' else WRITE_SCOPE}
    if scopes_of(credentials.get('scopes')) != required:
        raise AuthError('READONLY_SCOPE_REQUIRED' if mode == 'monitor' else 'SITEMAP_WRITE_SCOPE_REQUIRED')
    result = dict(credentials)
    result.setdefault('type', 'authorized_user')
    result.setdefault('token_uri', TOKEN_URI)
    result['scopes'] = sorted(required)
    return result


def load_credentials_from_env(env=None):
    env = os.environ if env is None else env
    value = env.get('GOOGLE_OAUTH_CREDENTIALS')
    if not value: raise AuthError('AUTH_REQUIRED')
    try: data = json.loads(value)
    except (TypeError, ValueError): raise AuthError('INVALID_CREDENTIAL_JSON') from None
    return validate_credentials(data, 'monitor')


def _keychain_api():
    if sys.platform != 'darwin': raise AuthError('KEYCHAIN_UNAVAILABLE')
    api = ctypes.CDLL('/System/Library/Frameworks/Security.framework/Security')
    api.SecKeychainFindGenericPassword.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p)]
    api.SecKeychainFindGenericPassword.restype = ctypes.c_int32
    api.SecKeychainAddGenericPassword.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
    api.SecKeychainAddGenericPassword.restype = ctypes.c_int32
    api.SecKeychainItemModifyAttributesAndData.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p]
    api.SecKeychainItemModifyAttributesAndData.restype = ctypes.c_int32
    api.SecKeychainItemFreeContent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    api.SecKeychainItemFreeContent.restype = ctypes.c_int32
    api.SecKeychainItemDelete.argtypes = [ctypes.c_void_p]
    api.SecKeychainItemDelete.restype = ctypes.c_int32
    return api


def _release(ref):
    if ref:
        cf = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        cf.CFRelease.argtypes = [ctypes.c_void_p]
        cf.CFRelease(ref)


def keychain_load(mode='monitor'):
    if mode not in ACCOUNTS: raise AuthError('INVALID_AUTH_MODE')
    api = _keychain_api(); service = KEYCHAIN_SERVICE.encode(); account = ACCOUNTS[mode].encode()
    length = ctypes.c_uint32(); data = ctypes.c_void_p()
    status = api.SecKeychainFindGenericPassword(None, len(service), service, len(account), account, ctypes.byref(length), ctypes.byref(data), None)
    if status == -25300: raise AuthError('AUTH_REQUIRED')
    if status: raise AuthError('KEYCHAIN_ACCESS_FAILED')
    try:
        try: credentials = json.loads(ctypes.string_at(data, length.value).decode())
        except (ValueError, UnicodeError): raise AuthError('INVALID_CREDENTIAL_JSON') from None
    finally: api.SecKeychainItemFreeContent(None, data)
    return validate_credentials(credentials, mode)


def keychain_save(credentials, mode='monitor'):
    credentials = validate_credentials(credentials, mode)
    api = _keychain_api(); service = KEYCHAIN_SERVICE.encode(); account = ACCOUNTS[mode].encode(); item = ctypes.c_void_p()
    value = json.dumps(credentials, separators=(',', ':')).encode()
    status = api.SecKeychainFindGenericPassword(None, len(service), service, len(account), account, None, None, ctypes.byref(item))
    try:
        if status == -25300:
            status = api.SecKeychainAddGenericPassword(None, len(service), service, len(account), account, len(value), value, None)
        elif status == 0:
            status = api.SecKeychainItemModifyAttributesAndData(item, None, len(value), value)
        if status: raise AuthError('KEYCHAIN_WRITE_FAILED')
    finally: _release(item)


def keychain_delete(mode='sitemap'):
    if mode not in ACCOUNTS: raise AuthError('INVALID_AUTH_MODE')
    api = _keychain_api(); service = KEYCHAIN_SERVICE.encode(); account = ACCOUNTS[mode].encode(); item = ctypes.c_void_p()
    status = api.SecKeychainFindGenericPassword(None, len(service), service, len(account), account, None, None, ctypes.byref(item))
    try:
        if status == -25300: return
        if status: raise AuthError('KEYCHAIN_ACCESS_FAILED')
        if api.SecKeychainItemDelete(item): raise AuthError('KEYCHAIN_DELETE_FAILED')
    finally: _release(item)


def load_credentials(mode='monitor'):
    if mode == 'monitor' and os.environ.get('GOOGLE_OAUTH_CREDENTIALS'):
        return load_credentials_from_env()
    return keychain_load(mode)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _opener():
    context = ssl.create_default_context(cafile='/etc/ssl/cert.pem' if Path('/etc/ssl/cert.pem').is_file() else None)
    return build_opener(_NoRedirect(), HTTPSHandler(context=context))


def _token_request(parameters, *, opener=None, sleep=time.sleep):
    opener = _opener() if opener is None else opener
    for attempt in range(3):
        try:
            request = Request(TOKEN_URI, data=urlencode(parameters).encode(), method='POST', headers={'Content-Type': 'application/x-www-form-urlencoded'})
            with opener.open(request, timeout=30) as response:
                data = json.loads(response.read(1_000_001))
            if not isinstance(data, dict): raise AuthError('INVALID_TOKEN_RESPONSE')
            return data
        except HTTPError as error:
            status = error.code
            try: payload = json.loads(error.read(100_000))
            except (ValueError, OSError): payload = {}
            finally: error.close()
            if status == 429 or 500 <= status < 600:
                if attempt < 2:
                    retry = error.headers.get('Retry-After', '')
                    delay = min(float(retry), 30) if re.fullmatch(r'\d+(?:\.\d+)?', retry) else 2 ** (attempt+1)
                    sleep(delay); continue
            code = payload.get('error') if isinstance(payload, dict) else None
            if code in ('invalid_grant', 'invalid_client', 'unauthorized_client', 'access_denied'):
                raise AuthError('AUTH_EXPIRED' if code == 'invalid_grant' else 'AUTH_REJECTED', status) from None
            raise AuthError('TOKEN_ENDPOINT_FAILED', status) from None
        except (URLError, TimeoutError, OSError):
            if attempt < 2: sleep(2 ** (attempt+1)); continue
            raise AuthError('TOKEN_NETWORK_ERROR') from None
        except (ValueError, UnicodeError): raise AuthError('INVALID_TOKEN_RESPONSE') from None
    raise AuthError('TOKEN_ENDPOINT_FAILED')


def refresh_access_token(credentials, *, opener=None, sleep=time.sleep):
    # Both local purposes are accepted, but a broad grant cannot masquerade as
    # the monitor's readonly credential.
    granted = scopes_of(credentials.get('scopes')) if isinstance(credentials, dict) else set()
    mode = 'monitor' if granted == {READONLY_SCOPE} else 'sitemap'
    credentials = validate_credentials(credentials, mode)
    payload = _token_request({'grant_type': 'refresh_token', 'client_id': credentials['client_id'], 'client_secret': credentials['client_secret'], 'refresh_token': credentials['refresh_token']}, opener=opener, sleep=sleep)
    if 'scope' in payload and scopes_of(payload['scope']) != granted:
        raise AuthError('GRANTED_SCOPE_CHANGED')
    if not isinstance(payload.get('access_token'), str) or not payload['access_token']:
        raise AuthError('INVALID_TOKEN_RESPONSE')
    if payload.get('token_type', 'Bearer').lower() != 'bearer': raise AuthError('INVALID_TOKEN_RESPONSE')
    return payload['access_token']


def load_desktop_client(client_file):
    try:
        decoded = json.loads(Path(client_file).expanduser().read_text())
    except (OSError, ValueError): raise AuthError('INVALID_DESKTOP_CLIENT_FILE') from None
    client = decoded.get('installed', {}) if isinstance(decoded, dict) else {}
    if not isinstance(client, dict): raise AuthError('DESKTOP_CLIENT_REQUIRED')
    if not all(isinstance(client.get(k), str) and client[k] for k in ('client_id', 'client_secret')):
        raise AuthError('DESKTOP_CLIENT_REQUIRED')
    official_auth_uris = {AUTH_URI, 'https://accounts.google.com/o/oauth2/auth'}
    if client.get('token_uri', TOKEN_URI) != TOKEN_URI or client.get('auth_uri', AUTH_URI) not in official_auth_uris:
        raise AuthError('UNTRUSTED_OAUTH_ENDPOINT')
    return client


def authorize(client_file, mode='monitor', *, timeout=300, announce=print):
    if mode not in ACCOUNTS: raise AuthError('INVALID_AUTH_MODE')
    client = load_desktop_client(client_file)
    state = secrets.token_urlsafe(32); verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    outcome = {}
    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            parsed = urlsplit(self.path); params = parse_qs(parsed.query)
            if parsed.path != '/oauth2callback' or not secrets.compare_digest(params.get('state', [''])[0], state):
                self.send_response(400); self.end_headers(); self.wfile.write(b'Invalid OAuth callback.'); return
            if params.get('error'): outcome['error'] = 'USER_AUTHORIZATION_DECLINED'
            elif params.get('code'): outcome['code'] = params['code'][0]
            else: outcome['error'] = 'INVALID_OAUTH_CALLBACK'
            self.send_response(200); self.send_header('Content-Type', 'text/plain; charset=utf-8'); self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(b'Google authorization received. Return to the local terminal. You can close this tab.')
    with HTTPServer(('127.0.0.1', 0), Callback) as server:
        server.timeout = 1
        redirect = f'http://127.0.0.1:{server.server_port}/oauth2callback'
        scope = READONLY_SCOPE if mode == 'monitor' else WRITE_SCOPE
        url = AUTH_URI+'?'+urlencode({'client_id': client['client_id'], 'redirect_uri': redirect, 'response_type': 'code', 'scope': scope, 'access_type': 'offline', 'prompt': 'consent', 'include_granted_scopes': 'false', 'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256'})
        announce('Open the following Google consent URL in your own browser. Do not send tokens or callback URLs in chat:')
        announce(url)
        deadline = time.monotonic()+timeout
        while not outcome and time.monotonic() < deadline: server.handle_request()
        if not outcome: raise AuthError('AUTHORIZATION_TIMEOUT')
        if outcome.get('error'): raise AuthError(outcome['error'])
        payload = _token_request({'grant_type': 'authorization_code', 'code': outcome['code'], 'client_id': client['client_id'], 'client_secret': client['client_secret'], 'redirect_uri': redirect, 'code_verifier': verifier})
    actual_scopes = scopes_of(payload.get('scope', scope))
    credentials = {'type': 'authorized_user', 'client_id': client['client_id'], 'client_secret': client['client_secret'], 'refresh_token': payload.get('refresh_token'), 'token_uri': TOKEN_URI, 'scopes': sorted(actual_scopes), 'created_at': utc(), 'scope_source': 'token_response' if 'scope'in payload else 'requested_scope_unchanged_per_oauth_response'}
    return validate_credentials(credentials, mode)


def install_github_secret(repository, *, credentials=None, runner=subprocess.run):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository): raise AuthError('INVALID_REPOSITORY')
    credentials = validate_credentials(keychain_load('monitor') if credentials is None else credentials, 'monitor')
    gh = shutil.which('gh') or str(Path.home()/'.local/bin/gh')
    response = runner([gh, 'api', 'repos/'+repository, '--jq', '.private'], capture_output=True, text=True)
    if response.returncode or response.stdout.strip() != 'true': raise AuthError('PRIVATE_MONITOR_REPOSITORY_REQUIRED')
    payload = {k: credentials[k] for k in ('type', 'client_id', 'client_secret', 'refresh_token', 'token_uri', 'scopes')}
    # Secret content is supplied through stdin, never a --body argv value.
    result = runner([gh, 'secret', 'set', 'GOOGLE_OAUTH_CREDENTIALS', '--repo', repository], input=json.dumps(payload), capture_output=True, text=True)
    if result.returncode: raise AuthError('GITHUB_SECRET_CONFIGURATION_FAILED')
    return {'configured': True, 'secret_name': 'GOOGLE_OAUTH_CREDENTIALS', 'repository': repository, 'scope': READONLY_SCOPE, 'secret_value_printed': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    auth = commands.add_parser('authorize'); auth.add_argument('--mode', choices=ACCOUNTS, required=True); auth.add_argument('--client-file', required=True)
    auth.add_argument('--no-open-browser', action='store_true', help='Explicit print-only mode; this is already the default. No browser automation is performed.')
    auth.add_argument('--timeout', type=int, default=300, help='Seconds to wait for the user-completed loopback callback.')
    install = commands.add_parser('configure-github-secret'); install.add_argument('--repository', required=True)
    commands.add_parser('check-monitor-credential')
    args = parser.parse_args(argv)
    try:
        if args.command == 'authorize':
            creds = authorize(args.client_file, args.mode, timeout=max(30, min(args.timeout, 900))); keychain_save(creds, args.mode)
            print(json.dumps({'status': 'AUTHORIZED', 'mode': args.mode, 'stored_in': 'macOS Keychain', 'credential_value_printed': False, 'scope': creds['scopes']}))
        elif args.command == 'configure-github-secret': print(json.dumps(install_github_secret(args.repository)))
        else:
            refresh_access_token(load_credentials('monitor'))
            print(json.dumps({'status': 'TOKEN_REFRESH_SUCCEEDED', 'scope': READONLY_SCOPE, 'index_inspection_performed': False}))
    except AuthError as error:
        print(json.dumps({'status': 'AUTH_REQUIRED' if error.code in ('AUTH_REQUIRED','AUTH_EXPIRED') else 'AUTH_ERROR', 'error': error.code, 'http_status': error.status}))
        return 2
    return 0


if __name__ == '__main__': raise SystemExit(main())
