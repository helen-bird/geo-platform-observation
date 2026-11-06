#!/usr/bin/env python3
"""Offline checks of generated metadata/identity; no claim about real indexing."""
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
from site_metadata import ROOT, SITE, HUB_PATH, PERSON_ID, SITE_ID, SERIES_ID, canonical_url, finalize_page


class Metadata(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_head = False
        self.in_title = False
        self.title = ''
        self.canonicals = []
        self.meta = {}
        self.jsonld = []
        self.in_json = False
        self.in_body = False
        self.body_text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'head': self.in_head = True
        if tag == 'body': self.in_body = True
        if self.in_head and tag == 'title': self.in_title = True
        if self.in_head and tag == 'link' and 'canonical' in attrs.get('rel', '').lower().split():
            self.canonicals.append(attrs.get('href'))
        if self.in_head and tag == 'meta':
            key = attrs.get('name', attrs.get('property', '')).lower()
            self.meta.setdefault(key, []).append(attrs.get('content', ''))
        if self.in_head and tag == 'script' and attrs.get('type') == 'application/ld+json':
            self.in_json = True
            self.jsonld.append('')

    def handle_endtag(self, tag):
        if tag == 'head': self.in_head = False
        if tag == 'body': self.in_body = False
        if tag == 'title': self.in_title = False
        if tag == 'script': self.in_json = False

    def handle_data(self, text):
        if self.in_title: self.title += text
        if self.in_json: self.jsonld[-1] += text
        if self.in_body: self.body_text.append(text)


def _local(url):
    assert url.startswith(SITE), url
    path = unquote(urlsplit(url).path[len(urlsplit(SITE).path):])
    if not path or path.endswith('/'): path += 'index.html'
    target = (ROOT/path).resolve()
    assert target.is_relative_to(ROOT), url
    return target


def _fixture_checks():
    body = '<body><p>Original answer text.</p><a href="https://example.org/source?keep=1">Source URL</a></body></html>'
    doc = '<html><head><title>Original archive title</title><meta name="description" content="Original response archive C-Q1-R1 with real source links."></head>'+body
    for path, kind, stage in [('index.html', 'reader', 1), ('technical-appendix.html', 'appendix', 1), (HUB_PATH, 'hub', None), ('evidence/stage-01/C-Q1-R1.html', 'evidence', 1)]:
        result = finalize_page(doc, path, kind, stage)
        assert result[result.index('<body>'):] == body, 'Head metadata must not rewrite original answer text or URL'
        assert finalize_page(result, path, kind, stage) == result, 'Metadata must be idempotent'


def main():
    _fixture_checks()
    reports = json.loads((ROOT/'report-versions.json').read_text())['reports']
    targets = [(HUB_PATH, 'hub', None)]
    for report in reports:
        targets.append((report['path'], 'reader', report))
        targets.append((str(Path(report['path']).parent/'technical-appendix.html'), 'appendix', report))
    targets += [(p.relative_to(ROOT).as_posix(), 'evidence-index' if p.name == 'index.html' else 'evidence', None) for p in sorted((ROOT/'evidence').rglob('*.html'))]
    descriptions, titles, canonical_values = [], [], []
    for path, kind, report in targets:
        source = (ROOT/path).read_text()
        parsed = Metadata(); parsed.feed(source)
        expected = canonical_url(path)
        assert parsed.canonicals == [expected], (path, parsed.canonicals, expected)
        assert _local(expected).is_file(), (path, expected)
        for key in ('description', 'og:type', 'og:title', 'og:description', 'og:url'):
            assert len(parsed.meta.get(key, [])) == 1 and parsed.meta[key][0].strip(), (path, key)
        assert len(parsed.meta['description'][0]) >= 40
        assert parsed.meta['og:url'] == [expected]
        assert parsed.meta['og:title'] == [parsed.title]
        assert parsed.meta['og:description'] == parsed.meta['description']
        descriptions.append(parsed.meta['description'][0]); titles.append(parsed.title); canonical_values.append(expected)
        assert len(parsed.jsonld) == 1, (path, 'Expected one shared structured-data graph')
        structured = json.loads(parsed.jsonld[0])
        assert structured['@context'] == 'https://schema.org'
        graph = structured['@graph']; nodes = {node['@id']: node for node in graph}
        assert len(nodes) == len(graph), (path, 'Duplicate entity IDs')
        person = nodes[PERSON_ID]
        assert person == {'@type': 'Person', '@id': PERSON_ID, 'name': 'Helen Bird', 'url': canonical_url(HUB_PATH)}
        assert nodes[SITE_ID]['@type'] == 'WebSite' and nodes[SERIES_ID]['@type'] == 'CreativeWorkSeries'
        expected_series = [r for r in reports if kind not in {'evidence', 'evidence-index'} or r.get('record_type') != 'technical_learning_record']
        assert nodes[SERIES_ID]['hasPart'] == [{'@id': canonical_url(r['path'])+'#article'} for r in expected_series]
        breadcrumbs = [node for node in graph if node['@type'] == 'BreadcrumbList']
        assert len(breadcrumbs) == 1
        trail = breadcrumbs[0]['itemListElement']
        assert [part['position'] for part in trail] == list(range(1, len(trail)+1))
        assert trail[-1]['item'] == expected
        for part in trail:
            assert part['@type'] == 'ListItem' and part['name'] and _local(part['item']).is_file()
        body = ' '.join(parsed.body_text)
        assert 'Helen Bird' in body, (path, 'Publisher identity must also be visible')
        articles = [node for node in graph if node['@type'] == 'Article']
        if kind in ('reader', 'appendix'):
            assert len(articles) == 1
            article = articles[0]
            assert article['author'] == {'@id': PERSON_ID}
            assert article['datePublished'] == report['first_published']
            assert article['dateModified'] == report['last_revised']
            assert article['datePublished'] <= article['dateModified']
            assert article['datePublished'] in body and article['dateModified'] in body
            assert article['headline'] == parsed.title and article['url'] == expected
            assert nodes[article['mainEntityOfPage']['@id']]['@type'] == 'WebPage'
            assert 'breadcrumb' not in article, 'Breadcrumb belongs on the WebPage node'
        else:
            assert not articles, (path, 'AI response archives must not claim to be Helen-authored Articles')
            page = nodes[expected+'#webpage']
            if kind == 'hub':
                assert page['@type'] == 'CollectionPage'
                assert page['datePublished'] in body and page['dateModified'] in body
            elif kind == 'evidence':
                assert page['@type'] == 'WebPage' and 'author' not in page
        assert not re.search(r'\bnoindex\b|\bnofollow\b', ' '.join(parsed.meta.get('robots', [])), re.I)
    assert len(descriptions) == len(set(descriptions)), 'Descriptions must distinguish individual pages'
    assert len(titles) == len(set(titles)), 'Page titles must be unique'
    assert len(canonical_values) == len(set(canonical_values))
    print(json.dumps({'status':'passed','generated_pages':len(targets),'core_pages':2*len(reports)+1,'canonical_description_OG_consistency':True,'local_schema_syntax_identity_dates_breadcrumbs':'passed','original_body_fixture_unchanged':True,'effect_and_indexing_verified':False}))


if __name__ == '__main__':
    main()
