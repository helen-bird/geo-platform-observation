#!/usr/bin/env python3
"""Build a small canonical-HTML sitemap offline from actual report records.

Only editorial report routes belong here. Public data, evidence archives,
error pages and source code remain available through their ordinary links.
"""
from datetime import date
from html.parser import HTMLParser
import json
from pathlib import Path
import posixpath
import re
from urllib.parse import urljoin, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SITE = 'https://helen-bird.github.io/geo-platform-observation/'
NAMESPACE = 'http://www.sitemaps.org/schemas/sitemap/0.9'
ET.register_namespace('', NAMESPACE)


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.canonicals = []
        self.visible = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style', 'head'):
            self.hidden += 1
        if tag == 'link' and 'canonical' in attrs.get('rel', '').lower().split():
            self.canonicals.append(attrs.get('href', ''))

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'head'):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, value):
        if not self.hidden:
            self.visible.append(value)


def validated_date(value):
    """Require an explicit recorded calendar date; do not use build time/mtime."""
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Expected an explicit YYYY-MM-DD revision date')
    date.fromisoformat(value)
    return value


def canonical_url(path):
    """Directory form is the established preference for index documents."""
    if path == 'index.html':
        path = ''
    elif path.endswith('/index.html'):
        path = path[:-len('index.html')]
    return urljoin(SITE, path)


def read_page(path):
    destination = (ROOT / path).resolve()
    if not destination.is_relative_to(ROOT) or not destination.is_file():
        raise ValueError('Sitemap source must be an existing project file: '+path)
    parsed = Page()
    parsed.feed(destination.read_text())
    return parsed


def entries():
    """Use only confirmed routes; the hub date comes from its visible text."""
    reports = json.loads((ROOT/'report-versions.json').read_text())['reports']
    result = []
    for report in reports:
        path = report['path']
        if not path.endswith('index.html'):
            raise ValueError('Unexpected report reader route: '+path)
        revision = validated_date(report['last_revised'])
        for source in (path, posixpath.join(posixpath.dirname(path), 'technical-appendix.html')):
            read_page(source)
            result.append({'path': source, 'loc': canonical_url(source), 'lastmod': revision,
                           'lastmod_source': 'report-versions.json: stage '+str(report['stage'])+' last_revised'})
    hub_path = 'learning-hub/index.html'
    hub = read_page(hub_path)
    dates = set(re.findall(r'\bUpdated:\s*(\d{4}-\d{2}-\d{2})', ' '.join(hub.visible)))
    entry = {'path': hub_path, 'loc': canonical_url(hub_path)}
    if len(dates) == 1:
        entry.update(lastmod=validated_date(next(iter(dates))), lastmod_source='Visible Learning Hub Updated field')
    result.insert(1, entry)
    # The evidence index is a useful navigation page in the monitoring scope.
    # Its response timestamps are not the page modification date: omit lastmod.
    evidence_path = 'evidence/index.html'
    read_page(evidence_path)
    result.append({'path': evidence_path, 'loc': canonical_url(evidence_path)})
    urls = [e['loc'] for e in result]
    expected_count = 2 * len(reports) + 2
    if len(result) != expected_count or len(set(urls)) != len(result):
        raise ValueError('Expected unique routes for each report, appendix and both navigation indexes')
    if any(not u.startswith(SITE) or urlsplit(u).query or urlsplit(u).fragment for u in urls):
        raise ValueError('Sitemap URLs must stay canonical and within the project')
    manifest=ROOT/'monitoring/google-index/urls.json'
    if manifest.exists():
        intended={r['url']for r in json.loads(manifest.read_text())['urls']if r.get('sitemap_include')is True}
        if intended!=set(urls):raise ValueError('Sitemap must match the reviewed canonical monitoring inventory')
    return result


def build():
    listing = entries()
    root = ET.Element(ET.QName(NAMESPACE, 'urlset'))
    for entry in listing:
        node = ET.SubElement(root, ET.QName(NAMESPACE, 'url'))
        ET.SubElement(node, ET.QName(NAMESPACE, 'loc')).text = entry['loc']
        if entry.get('lastmod'):
            ET.SubElement(node, ET.QName(NAMESPACE, 'lastmod')).text = entry['lastmod']
    ET.indent(root, space='  ')
    document = ET.tostring(root, encoding='utf-8', xml_declaration=True)+b'\n'
    destination = ROOT/'sitemap.xml'
    destination.write_bytes(document)
    return {'sitemap': 'sitemap.xml', 'canonical_HTML_urls': len(listing),
            'lastmod_policy': 'Recorded editorial revision dates; hub visible Updated field or omitted',
            'network_requests': 0, 'search_console_submission': False}


if __name__ == '__main__':
    print(json.dumps(build()))
