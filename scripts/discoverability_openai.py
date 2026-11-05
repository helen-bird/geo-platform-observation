#!/usr/bin/env python3
"""Observable OpenAI search crawl eligibility; never evidence of real bot visits.

All network output is returned to the private caller. No API keys, logs or model
requests are used. A self-declared user-agent is explicitly a simulation.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
from html.parser import HTMLParser
import re
import ssl
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler

PROPERTY = 'https://helen-bird.github.io/geo-platform-observation/'
ORIGIN = 'https://helen-bird.github.io'
ROBOTS_URL = ORIGIN + '/robots.txt'
MONITOR_UA = 'GEO-Lab-Discoverability-Monitor/1.0'
OAI_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36; compatible; OAI-SearchBot/1.4; +https://openai.com/searchbot'
MAX_BYTES = 2_000_000

class ProbeError(RuntimeError):
    def __init__(self, code): self.code = code; super().__init__(code)

def utc(): return dt.datetime.now(dt.timezone.utc).isoformat()

def validate_url(url):
    if not isinstance(url, str) or not url.startswith(PROPERTY): raise ProbeError('OUT_OF_PROPERTY_URL')
    p = urlsplit(url)
    if p.scheme != 'https' or p.netloc != 'helen-bird.github.io' or p.query or p.fragment: raise ProbeError('NON_CANONICAL_URL')
    decoded = p.path
    for _ in range(4):
        new = unquote(decoded)
        if new == decoded: break
        decoded = new
    if '\\' in decoded or any(x in {'.', '..'} for x in decoded.split('/')) or not decoded.startswith('/geo-platform-observation/'):
        raise ProbeError('UNSAFE_URL_PATH')
    return url

def reviewed_urls(inventory):
    if not isinstance(inventory, dict) or inventory.get('site_url') != PROPERTY: raise ProbeError('INVALID_INVENTORY_PROPERTY')
    result = []; seen = set()
    for item in list(inventory.get('urls', [])) + list(inventory.get('excluded_urls', [])):
        if not isinstance(item, dict): raise ProbeError('INVALID_INVENTORY_ROW')
        if item.get('indexing_desired') is not True: continue
        url = validate_url(item.get('url'))
        if url in seen: raise ProbeError('DUPLICATE_CANONICAL_URL')
        seen.add(url); result.append(dict(item))
    return result

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None

def default_requester(method, url, headers, body, timeout):
    context = ssl.create_default_context(cafile='/etc/ssl/cert.pem' if sys.platform == 'darwin' else None)
    opener = build_opener(_NoRedirect(), HTTPSHandler(context=context))
    try: response = opener.open(Request(url, data=body, headers=headers, method=method), timeout=timeout)
    except HTTPError as error: response = error
    with response:
        value = response.read(MAX_BYTES + 1)
        if len(value) > MAX_BYTES: raise ProbeError('RESPONSE_TOO_LARGE')
        return response.code, dict(response.headers.items()), value

def header_values(headers, key):
    out = []
    for name, value in (headers or {}).items():
        if name.lower() == key.lower(): out.extend(value if isinstance(value, list) else [str(value)])
    return out

def get_url(url, *, user_agent=MONITOR_UA, requester=None, sleep=time.sleep, attempts=3, allow_robots=False):
    if not (allow_robots and url == ROBOTS_URL): validate_url(url)
    requester = requester or default_requester
    events = []
    for attempt in range(1, min(max(attempts, 1), 3) + 1):
        try:
            status, headers, body = requester('GET', url, {'User-Agent': user_agent, 'Accept': 'text/html,text/plain;q=0.9,*/*;q=0.1'}, None, 30)
            if not isinstance(body, bytes) or len(body) > MAX_BYTES: raise ProbeError('INVALID_OR_OVERSIZED_BODY')
            events.append({'attempt': attempt, 'http_status': status})
            if status == 429 or 500 <= status <= 599:
                if attempt < min(max(attempts, 1), 3):
                    retry = next(iter(header_values(headers, 'Retry-After')), '')
                    sleep(min(30, int(retry)) if retry.isdigit() else min(8, 2 ** attempt)); continue
            return {'http_status': status, 'headers': headers, 'body': body, 'attempts': events, 'error': None}
        except (URLError, TimeoutError, OSError):
            events.append({'attempt': attempt, 'error': 'NETWORK_ERROR'})
            if attempt < min(max(attempts, 1), 3): sleep(min(8, 2 ** attempt)); continue
            return {'http_status': None, 'headers': {}, 'body': b'', 'attempts': events, 'error': 'NETWORK_ERROR'}
        except ProbeError as error:
            return {'http_status': None, 'headers': {}, 'body': b'', 'attempts': events, 'error': error.code}
    raise ProbeError('INVALID_RETRY_STATE')

def _octets(value):
    """RFC comparison: decode unreserved ASCII, preserve reserved escapes."""
    unreserved = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~'
    value = re.sub(r'%([0-9a-fA-F]{2})', lambda m: chr(int(m[1], 16)) if chr(int(m[1], 16)) in unreserved else '%' + m[1].upper(), value)
    return ''.join(c if ord(c) < 128 else ''.join('%%%02X' % b for b in c.encode('utf-8')) for c in value)

def robots_decision(text, url, agent='OAI-SearchBot'):
    groups = []; agents = []; rules = []; saw_rule = False
    def flush():
        if agents: groups.append((list(agents), list(rules)))
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if ':' not in line: continue
        key, value = (x.strip() for x in line.split(':', 1)); key = key.lower()
        if key == 'user-agent':
            if saw_rule: flush(); agents = []; rules = []; saw_rule = False
            if value: agents.append(value.lower())
        elif key in {'allow', 'disallow'} and agents:
            saw_rule = True
            if value and value.startswith('/'): rules.append((key, value))
    flush()
    token = agent.lower(); relevant = []; specificity = -1
    for names, rules in groups:
        score = max((0 if n == '*' else len(n) for n in names if n == '*' or n in token), default=-1)
        if score > specificity: specificity = score; relevant = list(rules)
        elif score >= 0 and score == specificity: relevant.extend(rules)
    path = _octets(urlsplit(url).path + ('?' + urlsplit(url).query if urlsplit(url).query else ''))
    matches = []
    for kind, pattern in relevant:
        pattern = _octets(pattern)
        terminal = pattern.endswith('$')
        if terminal: pattern = pattern[:-1]
        regex = '^' + '.*'.join(re.escape(part) for part in pattern.split('*')) + ('$' if terminal else '')
        if re.search(regex, path):
            # Specificity is octet length, excluding wildcard/end-marker syntax.
            literal = pattern.replace('*', '')
            length = len(re.sub(r'%[0-9A-F]{2}', 'x', literal))
            matches.append((length, kind == 'allow', kind, pattern + ('$' if terminal else '')))
    winner = max(matches, default=None)
    return {'status': 'ALLOWED' if winner is None or winner[1] else 'DISALLOWED', 'matched_rule': None if winner is None else winner[2] + ': ' + winner[3], 'agent_group_specificity': specificity}

class _Page(HTMLParser):
    def __init__(self):
        super().__init__(); self.directives = []; self.canonicals = []; self.title = ''; self.in_title = False
        self.in_body = False; self.hidden = 0; self.visible = []; self.links = []; self.metadata = []; self.structured = []; self.in_structured = False
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'title': self.in_title = True
        if tag == 'body': self.in_body = True
        if tag in {'script', 'style'}: self.hidden += 1
        if tag == 'script' and attrs.get('type', '').lower() == 'application/ld+json': self.in_structured = True
        if self.in_body and tag == 'a' and attrs.get('href'): self.links.append(attrs['href'])
        if self.in_body and tag == 'img': self.visible.append(attrs.get('alt', ''))
        if tag == 'meta' and attrs.get('name', attrs.get('property', '')).lower() in {'description', 'og:title', 'og:description', 'robots', 'oai-searchbot'}:
            self.metadata.append([attrs.get('name', attrs.get('property', '')).lower(), attrs.get('content', '')])
        if tag == 'meta' and attrs.get('name', '').lower() in {'robots', 'oai-searchbot'}:
            self.directives.append(attrs.get('content', '').lower())
        if tag == 'link' and 'canonical' in attrs.get('rel', '').lower().split(): self.canonicals.append(attrs.get('href', ''))
    def handle_endtag(self, tag):
        if tag == 'title': self.in_title = False
        if tag == 'body': self.in_body = False
        if tag in {'script', 'style'}: self.hidden = max(0, self.hidden - 1)
        if tag == 'script': self.in_structured = False
    def handle_data(self, data):
        if self.in_title: self.title += data
        if self.in_body and not self.hidden: self.visible.append(data)
        if self.in_structured: self.structured.append(data)

def page_signals(response):
    page = _Page()
    try: page.feed(response.get('body', b'').decode('utf-8', 'replace'))
    except Exception: return {'noindex': None, 'error': 'HTML_PARSE_ERROR', 'canonical': [], 'possible_interstitial': False}
    directives = list(page.directives)
    for line in header_values(response.get('headers'), 'X-Robots-Tag'):
        applies = True
        for chunk in line.split(','):
            chunk = chunk.strip().lower()
            if ':' in chunk:
                scope, chunk = chunk.split(':', 1); applies = scope.strip() in {'oai-searchbot', '*'}
            if applies: directives.append(chunk)
    tokens = {v for item in directives for v in re.split(r'[\s,;]+', item) if v}
    semantic = {'title': ' '.join(page.title.split()), 'text': ' '.join(' '.join(page.visible).split()), 'links': page.links, 'metadata': page.metadata, 'canonical': page.canonicals, 'structured': [' '.join(s.split()) for s in page.structured]}
    return {'noindex': bool(tokens & {'noindex', 'none'}), 'directives': sorted(tokens), 'canonical': page.canonicals,
            'content_sha256': hashlib.sha256(json.dumps(semantic, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
            'possible_interstitial': page.title.strip().lower() in {'just a moment...', 'attention required! | cloudflare', 'access denied'}, 'error': None}

def _safe_response(value):
    return {'http_status': value['http_status'], 'error': value['error'], 'attempts': value['attempts'],
            'body_sha256': hashlib.sha256(value['body']).hexdigest() if value['http_status'] is not None else None,
            'content_type': header_values(value['headers'], 'Content-Type'), 'x_robots_tag': header_values(value['headers'], 'X-Robots-Tag')}

def probe_openai(inventory, *, requester=None, checked_at=None, sleep=time.sleep):
    """Read-only probes, no real crawl/index verdicts; caller persists privately."""
    urls = reviewed_urls(inventory); when = checked_at or utc()
    robot = get_url(ROBOTS_URL, requester=requester, sleep=sleep, allow_robots=True)
    robot_status = robot['http_status']; text = robot['body'].decode('utf-8', 'replace') if robot_status == 200 else ''
    root = dict(url=ROBOTS_URL, **_safe_response(robot)); root['rules_text'] = text
    root['project_path_robots_is_effective'] = False
    results = []
    for item in urls:
        url = item['url']; url_checked_at = checked_at or utc()
        if robot_status == 200: decision = robots_decision(text, url)
        elif robot_status is not None and 400 <= robot_status <= 499: decision = {'status': 'ALLOWED', 'matched_rule': None, 'basis': 'RFC9309_UNAVAILABLE_NO_EFFECTIVE_RULES'}
        else: decision = {'status': 'UNKNOWN', 'matched_rule': None, 'conservative_crawler_assumption': 'DISALLOWED', 'basis': 'ROBOTS_UNREACHABLE_OR_REDIRECT_NOT_RESOLVED'}
        normal = get_url(url, requester=requester, sleep=sleep); simulation = get_url(url, user_agent=OAI_UA, requester=requester, sleep=sleep)
        signals = page_signals(normal); blockers = []
        if decision['status'] == 'DISALLOWED': blockers.append('ROBOTS_DISALLOWED')
        if normal['http_status'] is not None and 400 <= normal['http_status'] < 500: blockers.append('PUBLIC_HTTP_ACCESS_'+str(normal['http_status']))
        if signals['noindex']: blockers.append('NOINDEX')
        if signals['possible_interstitial']: blockers.append('POSSIBLE_ACCESS_INTERSTITIAL')
        if signals.get('canonical') and signals['canonical'] != [url]: blockers.append('CANONICAL_DIFFERS')
        normal_ok = normal['http_status'] == 200 and not normal['error'] and not signals['error']
        configuration = 'BLOCKED' if blockers else 'ALLOWED' if normal_ok and decision['status'] == 'ALLOWED' else 'UNKNOWN'
        sim_signals = page_signals(simulation)
        sim_status = 'INTERSTITIAL_OBSERVED' if sim_signals.get('possible_interstitial') else 'FETCH_SUCCEEDED' if simulation['http_status'] == 200 and not simulation['error'] else 'HTTP_ACCESS_BLOCKED' if simulation['http_status'] in {401, 403, 429} else 'UNKNOWN'
        results.append({'url': url, 'checked_at': url_checked_at, 'category': item.get('category'), 'configuration_status': configuration, 'robots': decision,
                        'public_access': _safe_response(normal), 'page_signals': signals, 'blockers': blockers,
                        'ua_simulation': dict(_safe_response(simulation), status=sim_status, user_agent=OAI_UA, source='monitor_host_not_openai_ip'),
                        'real_crawl': {'status': 'UNKNOWN', 'last_crawl_time': None, 'source': 'NO_TRUSTED_SERVER_OR_CDN_LOGS'},
                        'openai_index_status': 'UNKNOWN', 'chatgpt_recommendation_status': 'NOT_TESTED'})
    return {'schema_version': 1, 'checked_at': when, 'engine': 'OpenAI Search Crawl Eligibility', 'source': 'public_http_and_user_agent_simulation',
            'root_robots': root, 'results': results, 'url_count': len(results), 'real_crawl_status': 'UNKNOWN', 'real_crawl_time': None,
            'interpretation': 'Configuration and simulated access do not establish real OpenAI crawling, indexing, or recommendations.'}
