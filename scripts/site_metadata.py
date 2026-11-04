"""Truthful, shared page metadata; leaves the complete body and source URLs intact.

Schema vocabulary references: https://schema.org/Article,
https://schema.org/CreativeWorkSeries and https://schema.org/BreadcrumbList.
This markup is an identity description, not a claim about indexing or GEO effects.
"""
from html import escape, unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import posixpath
import re
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SITE = 'https://helen-bird.github.io/geo-platform-observation/'
HUB_PATH = 'learning-hub/index.html'
PERSON_ID = SITE + 'learning-hub/#helen-bird'
SITE_ID = SITE + '#website'
SERIES_ID = SITE + 'learning-hub/#geo-lab'
DESCRIPTIONS = {
    'index.html': 'GEO Lab 01 compares recommended entities and cited sources in 12 ChatGPT Search and Grok answers. Original observations, methods and limitations are preserved.',
    'technical-appendix.html': 'GEO Lab 01 evidence: 12 selected answers, historical attempts, source URLs, C/M/R observations, model conditions and capture history. Redacted originals are preserved.',
    'stages/02-post-discovery/index.html': 'GEO Lab 02 tests direct X-post access, exact-excerpt search and natural discovery in six selected answers. Collection qualifications and limits remain explicit.',
    'stages/02-post-discovery/technical-appendix.html': 'GEO Lab 02 evidence: exact prompts, six selected answers, all ten submissions, returned source links, technical failures and qualified recovery records.',
    'stages/03-question-sensitivity/index.html': 'GEO Lab 03 compares repeated and reworded questions in 24 OpenAI API web-search and Grok Expert answers. Results measure sensitivity, not GEO effectiveness.',
    'stages/03-question-sensitivity/technical-appendix.html': 'GEO Lab 03 evidence: 24 selected answers, 27 submissions, API/search controls, citations, coding and normalization checks. API results do not represent ChatGPT web.',
    'stages/04-creator-benchmark/index.html': 'GEO Lab 04 compares three creator families in 18 OpenAI API web-search and Grok Expert answers, separating personal names from content brands. No causal GEO claim.',
    'stages/04-creator-benchmark/technical-appendix.html': 'GEO Lab 04 evidence: 18 original answers, 54 creator-by-answer judgments, exact source URLs, search activity, eight cited-page audits and preserved recovery records.',
    HUB_PATH: "Helen Bird's question-oriented GEO Learning Hub connects four experiments with their reports, original public data, complete evidence and limitations.",
}


class _Tag(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tag = None
        self.attrs = {}

    def handle_starttag(self, tag, attrs):
        self.tag, self.attrs = tag, dict(attrs)


def _relative_path(path):
    path = str(path).replace('\\', '/')
    if path.startswith(SITE):
        path = path[len(SITE):]
    elif Path(path).is_absolute():
        path = Path(path).resolve().relative_to(ROOT).as_posix()
    if urlsplit(path).scheme or '?' in path or '#' in path:
        raise ValueError('Metadata needs an in-project file path without query/fragment')
    if path.endswith('/'):
        path += 'index.html'
    path = posixpath.normpath(path)
    if path == '..' or path.startswith('../'):
        raise ValueError('Metadata path leaves the project')
    if path in ('.', ''):
        return 'index.html'
    return path


def canonical_path(path):
    """Preferred URL path; only index.html aliases become directory URLs."""
    path = _relative_path(path)
    if path == 'index.html':
        return ''
    if path.endswith('/index.html'):
        return path[:-len('index.html')]
    return path


def canonical_url(path):
    return SITE + canonical_path(path)


def relative_canonical(path, from_directory='.'):
    preferred = canonical_path(path)
    relative = posixpath.relpath(preferred.rstrip('/') or '.', from_directory)
    return relative + '/' if preferred.endswith('/') or not preferred else relative


def _metadata_attributes(tag):
    parsed = _Tag()
    parsed.feed(tag)
    return parsed.attrs


def _strip_replaced_metadata(head):
    def strip(match):
        tag = match.group()
        attrs = _metadata_attributes(tag)
        if tag.lower().startswith('<link') and 'canonical' in attrs.get('rel', '').lower().split():
            return ''
        if tag.lower().startswith('<meta'):
            if attrs.get('name', '').lower() in {'description', 'author'}:
                return ''
            if attrs.get('property', '').lower() in {'og:type', 'og:title', 'og:description', 'og:url'}:
                return ''
        return tag
    head = re.sub(r'<(?:meta|link)\b[^>]*>', strip, head, flags=re.I)
    return re.sub(r'<script\b(?=[^>]*\bid=["\']geo-site-structured-data["\'])[^>]*>.*?</script>', '', head, flags=re.I | re.S)


def _reports():
    return json.loads((ROOT/'report-versions.json').read_text())['reports']


def _description(path, head, title):
    if path in DESCRIPTIONS:
        return DESCRIPTIONS[path]
    for tag in re.findall(r'<meta\b[^>]*>', head, re.I):
        attrs = _metadata_attributes(tag)
        if attrs.get('name', '').lower() == 'description' and attrs.get('content', '').strip():
            return attrs['content'].strip()
    return title + '. Original public evidence and source links are preserved; this archive does not establish GEO effectiveness.'


def _structured(path, kind, stage, title, description):
    reports = _reports()
    selected = next((r for r in reports if r['stage'] == stage), None)
    url = canonical_url(path)
    person = {'@type': 'Person', '@id': PERSON_ID, 'name': 'Helen Bird', 'url': canonical_url(HUB_PATH)}
    website = {'@type': 'WebSite', '@id': SITE_ID, 'name': 'GEO Learning Log', 'url': SITE, 'publisher': {'@id': PERSON_ID}, 'inLanguage': 'en'}
    series = {'@type': 'CreativeWorkSeries', '@id': SERIES_ID, 'name': 'GEO Lab', 'url': canonical_url(HUB_PATH), 'author': {'@id': PERSON_ID}, 'isPartOf': {'@id': SITE_ID}, 'hasPart': [{'@id': canonical_url(r['path'])+'#article'} for r in reports]}
    is_own_article = kind in {'reader', 'appendix'} and selected is not None
    page_type = 'CollectionPage' if kind in {'hub', 'evidence-index'} else ('Article' if is_own_article else 'WebPage')
    page_id = url + ('#article' if is_own_article else '#webpage')
    page = {'@type': page_type, '@id': page_id, 'url': url, 'name': title, 'description': description, 'inLanguage': 'en', 'publisher': {'@id': PERSON_ID}, 'isPartOf': [{'@id': SITE_ID}, {'@id': SERIES_ID}]}
    if is_own_article:
        page.update(headline=title, author={'@id': PERSON_ID}, mainEntityOfPage=url, datePublished=selected['first_published'], dateModified=selected['last_revised'])
        if kind == 'appendix':
            page['about'] = {'@id': canonical_url(selected['path'])+'#article'}
    elif kind == 'hub':
        page.update(author={'@id': PERSON_ID}, datePublished='2026-11-03', dateModified=max(r['last_revised'] for r in reports), about={'@id': SERIES_ID})
    # Evidence pages describe an archive curated/published by Helen Bird, not
    # authorship of the original platform-generated answer. No author is added.
    trail = [('GEO Learning Log', SITE)]
    if path not in {'index.html', HUB_PATH}:
        trail.append(('GEO Learning Hub', canonical_url(HUB_PATH)))
    if selected and path != selected['path']:
        trail.append((f'GEO Lab #{stage:02d} · '+selected['title'], canonical_url(selected['path'])))
    if trail[-1][1] != url:
        trail.append((title, url))
    breadcrumb = {'@type': 'BreadcrumbList', '@id': url+'#breadcrumb', 'itemListElement': [{'@type': 'ListItem', 'position': i+1, 'name': name, 'item': item} for i, (name, item) in enumerate(trail)]}
    graph = [person, website, series, page, breadcrumb]
    if is_own_article:
        # breadcrumb is a WebPage property; keep the authored Article separate
        # rather than attaching page-only properties to a CreativeWork subtype.
        webpage = {'@type': 'WebPage', '@id': url+'#webpage', 'url': url, 'name': title,
                   'description': description, 'inLanguage': 'en',
                   'isPartOf': {'@id': SITE_ID}, 'mainEntity': {'@id': page_id},
                   'breadcrumb': {'@id': breadcrumb['@id']}}
        page['mainEntityOfPage'] = {'@id': webpage['@id']}
        graph.append(webpage)
    else:
        page['breadcrumb'] = {'@id': breadcrumb['@id']}
    return {'@context': 'https://schema.org', '@graph': graph}


def finalize_page(document, path, kind='reader', stage=None):
    """Replace page metadata in head only; do not alter original answer bodies."""
    path = _relative_path(path)
    match = re.search(r'<head\b[^>]*>(.*?)</head>', document, re.I | re.S)
    if not match:
        raise ValueError('Metadata requires an explicit head element')
    head = match.group(1)
    title_match = re.search(r'<title\b[^>]*>(.*?)</title>', head, re.I | re.S)
    if not title_match:
        raise ValueError('Metadata requires an existing truthful page title')
    title = unescape(re.sub(r'<[^>]*>', '', title_match.group(1))).strip()
    description = _description(path, head, title)
    head = _strip_replaced_metadata(head)
    attrs = lambda value: escape(value, quote=True)
    metadata = '<link rel="canonical" href="'+attrs(canonical_url(path))+'">'
    metadata += '<meta name="description" content="'+attrs(description)+'">'
    if kind in {'reader', 'appendix', 'hub'}:
        metadata += '<meta name="author" content="Helen Bird">'
    metadata += '<meta property="og:type" content="'+('article' if kind in {'reader', 'appendix'} else 'website')+'">'
    metadata += '<meta property="og:title" content="'+attrs(title)+'">'
    metadata += '<meta property="og:description" content="'+attrs(description)+'">'
    metadata += '<meta property="og:url" content="'+attrs(canonical_url(path))+'">'
    structured = json.dumps(_structured(path, kind, stage, title, description), ensure_ascii=True, separators=(',', ':')).replace('<', '\\u003c')
    metadata += '<script type="application/ld+json" id="geo-site-structured-data">'+structured+'</script>'
    start, end = match.span(1)
    return document[:start] + head + metadata + document[end:]
