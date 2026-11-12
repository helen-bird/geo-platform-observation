#!/usr/bin/env python3
"""Public intent-only canonical URL inventory; never contains Search Console data."""
import json,re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from site_metadata import appendix_path

ROOT=Path(__file__).resolve().parents[1]
SITE='https://helen-bird.github.io/geo-platform-observation/'
class Page(HTMLParser):
    def __init__(self):super().__init__();self.canonical=[];self.noindex=False
    def handle_starttag(self,t,attrs):
        a=dict(attrs)
        if t=='link'and'canonical'in a.get('rel','').lower().split():self.canonical.append(a.get('href'))
        if t=='meta'and a.get('name','').lower()in('robots','googlebot')and'noindex'in a.get('content','').lower():self.noindex=True
def build():
    reports = json.loads((ROOT/'report-versions.json').read_text())['reports']
    primary = {'learning-hub/index.html', 'evidence/index.html'} | {r['path'] for r in reports}
    appendices = {path for r in reports if (path := appendix_path(r))}
    outside_monitor = {r['path'] for r in reports if r.get('monitor') is False}
    urls, excluded, known = [], [], set()
    for p in sorted(ROOT.rglob('*.html')):
        name=p.relative_to(ROOT).as_posix()
        if {'.git','audits','__pycache__'}.intersection(p.relative_to(ROOT).parts):continue
        page=Page();page.feed(p.read_text());important=name in primary|appendices
        if important and len(page.canonical)!=1:raise ValueError('Important page needs one actual canonical: '+name)
        canonical=page.canonical[0]if len(page.canonical)==1 else SITE+name
        parsed=urlsplit(canonical)
        if not canonical.startswith(SITE)or parsed.scheme!='https'or parsed.query or parsed.fragment:raise ValueError('Out-of-property canonical: '+name)
        if canonical in known:raise ValueError('Duplicate canonical content: '+canonical)
        known.add(canonical);category='primary_content'if name in primary else'technical_appendix'if name in appendices else'excluded'
        monitor=important and name not in outside_monitor
        reason=('Original research and learning-navigation entry'if category=='primary_content'else'Independent original answer/method/failure/source archive'if category=='technical_appendix'else'Supplemental individual response archive, kept crawlable but outside the initial editorial monitor'if name.startswith('evidence/')else'Verification, error template or non-editorial support file')
        if name in outside_monitor:
            reason = 'Editorial report included in the sitemap; outside the active monitoring scope'
        row={'url':canonical,'source_file':name,'category':category,'monitor':monitor,'sitemap_include':important and not page.noindex,'indexing_desired':monitor or name.startswith('evidence/'),'decision_reason':reason}
        (urls if monitor else excluded).append(row)
    expected=len(primary | appendices)-len(outside_monitor)
    assert len(urls)==expected,(len(urls),expected)
    value={'schema_version':1,'site_url':SITE,'source_repository':'helen-bird/geo-platform-observation','inventory_policy':'Important authored reports, learning/evidence indexes and full technical appendices. Editorial reports can be listed in the sitemap outside the active monitoring scope. Original response views remain crawlable but outside the initial editorial monitor. Verification/error assets excluded. Contains no Google index status or private API data.','urls':urls,'excluded_urls':excluded}
    destination=ROOT/'monitoring/google-index/urls.json';destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(json.dumps(value,ensure_ascii=True,indent=2)+'\n')
    return{'monitored_canonical_urls':len(urls),'excluded_from_initial_monitor':len(excluded),'private_search_console_data':False}
if __name__=='__main__':print(json.dumps(build()))
