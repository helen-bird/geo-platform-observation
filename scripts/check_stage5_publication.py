#!/usr/bin/env python3
"""Check Lab 05's bounded public summary, not private engine evidence."""
from html.parser import HTMLParser
import json,re,zipfile
from pathlib import Path
from urllib.parse import urlsplit,unquote

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'stages/05-technical-discoverability'
class Page(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self.details=[];self.ids=set()
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='a'and'href'in a:self.links.append(a['href'])
        if tag=='details':self.details.append('open'in a)
        if 'id'in a:self.ids.add(a['id'])

def main():
    summary=json.loads((FOLDER/'data/summary.json').read_text())
    assert summary['record_type']=='technical_learning_record'
    assert summary['ai_answer_experiments_run']is False
    assert summary['google']['indexed']+summary['google']['not_indexed']==summary['google']['scope_urls']
    good=summary['bing']['successful_batch'];bad=summary['bing']['later_joint_attempt']
    assert good['queries_succeeded']+good['query_errors']==good['url_queries']==good['index_membership_unknown']==good['crawl_lifecycle_unknown']
    assert bad['queries_succeeded']+bad['query_errors']+bad['unqueried_after_block']==bad['planned_urls']
    assert good['minimum_observed_response_gap_seconds']>=good['configured_interval_seconds']
    assert summary['openai_search']['real_crawler_visit']==summary['openai_search']['openai_index']=='UNKNOWN'
    assert summary['indexnow']['post_count']==0
    assert all('raw_response'not in p.read_text()for p in (FOLDER/'data').glob('*.json'))
    pages={}
    for name in ['index.html','technical-appendix.html']:
        p=FOLDER/name;doc=p.read_text();parsed=Page();parsed.feed(doc);pages[p.resolve()]=parsed
        assert '<html lang="en">'in doc and not re.search(r'[\u3400-\u9fff]',doc)
        assert all(parsed.details)
        assert not re.search(r'https?://github\.com/helen-bird/geo-index-monitor|/Users/|AuthenticationCode|DnsVerificationCode',doc,re.I)
        assert all(x in doc for x in ['Helen Bird','2026-11-06','UNKNOWN','IndexNow','data-report-series="v1"'])
        assert 'not an AI-answer experiment'in doc or 'not an archive of new AI answers'in doc
    for p,parsed in pages.items():
        for href in parsed.links:
            url=urlsplit(href)
            if url.scheme or url.netloc:continue
            target=(p.parent/unquote(url.path)).resolve()if url.path else p
            if target.is_dir():target=target/'index.html'
            assert target.is_relative_to(ROOT)and target.is_file(),(p,href)
            if url.fragment and target in pages:assert unquote(url.fragment)in pages[target].ids,(p,href)
    with zipfile.ZipFile(FOLDER/'public-data.zip')as archive:
        assert archive.testzip()is None
        assert set(archive.namelist())=={'data/summary.json','data/publication-notes.json'}
        for name in archive.namelist():assert archive.read(name)==(FOLDER/name).read_bytes()
    print(json.dumps({'stage':5,'record_type':'technical_learning_record','authored_pages':2,'AI_answer_count':0,'private_raw_responses_published':False,'aggregate_arithmetic_privacy_links_and_download':'passed'}))
if __name__=='__main__':main()
