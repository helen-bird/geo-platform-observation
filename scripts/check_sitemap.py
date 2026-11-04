#!/usr/bin/env python3
"""Validate the generated canonical sitemap without network or site mutation."""
import json
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
import build_sitemap as builder


def main():
    expected = builder.entries()
    tree = ET.parse(builder.ROOT/'sitemap.xml')
    namespace = '{'+builder.NAMESPACE+'}'
    root = tree.getroot()
    assert root.tag == namespace+'urlset', 'Wrong Sitemap XML namespace/root'
    nodes = root.findall(namespace+'url')
    assert len(nodes) == len(expected) == 9
    observed = []
    for node in nodes:
        locs = node.findall(namespace+'loc')
        mods = node.findall(namespace+'lastmod')
        assert len(locs) == 1 and len(mods) <= 1
        loc = locs[0].text
        assert loc and loc.startswith(builder.SITE)
        assert not urlsplit(loc).query and not urlsplit(loc).fragment
        observed.append({'loc': loc, 'lastmod': mods[0].text if mods else None})
    assert len({r['loc'] for r in observed}) == 9
    assert observed == [{'loc': e['loc'], 'lastmod': e.get('lastmod')} for e in expected], 'Sitemap differs from recorded canonical routes/dates'
    for entry in expected:
        doc = builder.read_page(entry['path'])
        assert doc.canonicals == [entry['loc']], (entry['path'], 'HTML must declare exactly this canonical', doc.canonicals)
        if entry.get('lastmod'):
            builder.validated_date(entry['lastmod'])
    result = {'sitemap': 'sitemap.xml', 'canonical_HTML_urls': len(observed),
              'namespace_unique_paths_dates_and_HTML_canonicals': 'passed',
              'network_requests': 0,
              'limit': 'Offline validation; HTTP access and search-engine discovery/indexing require separate observations.'}
    print(json.dumps(result))
    return result


if __name__ == '__main__':
    main()
