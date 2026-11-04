#!/usr/bin/env python3
"""Verify evidence-page text against the original redacted datasets and all links."""
from collections import Counter
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit,unquote
import build_evidence_pages as builder

ROOT=Path(__file__).resolve().parents[1]
class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.ids=[];self.links=[];self.titles=[];self.canonicals=[];self.descriptions=[];self.details=[];self.current=None;self.texts={};self.title=False;self.h1=0
    def handle_starttag(self,t,a):
        a=dict(a)
        if a.get('id'):self.ids.append(a['id'])
        if t=='a'and a.get('href'):self.links.append(a['href'])
        if t=='pre'and a.get('id')in('original-prompt','original-answer'):self.current=a['id'];self.texts[self.current]=''
        if t=='title':self.title=True;self.titles.append('')
        if t=='h1':self.h1+=1
        if t=='link'and a.get('rel')=='canonical':self.canonicals.append(a['href'])
        if t=='meta'and a.get('name','').lower()=='description':self.descriptions.append(a.get('content',''))
        if t=='details':self.details.append('open'in a)
    def handle_data(self,s):
        if self.current:self.texts[self.current]+=s
        if self.title:self.titles[-1]+=s
    def handle_endtag(self,t):
        if t=='pre':self.current=None
        if t=='title':self.title=False

def main():
    entries=builder.entries();manifest=json.loads((ROOT/'evidence/manifest.json').read_text());assert len(entries)==len(manifest['responses'])==60
    pages={}
    for path in sorted((ROOT/'evidence').rglob('*.html')):
        p=Page();doc=path.read_text();p.feed(doc);pages[path.resolve()]=p
        assert'<html lang="en">'in doc and not re.search(r'[\u3400-\u9fff]',doc),path
        assert p.h1==1 and len(p.titles)==1 and p.titles[0] and len(p.descriptions)==1 and p.descriptions[0],path
        try:
            from site_metadata import canonical_url
            expected_canonical=canonical_url(str(path.relative_to(ROOT)))
        except ImportError:
            expected_canonical=builder.SITE+str(path.relative_to(ROOT)).removesuffix('index.html')
        assert len(p.canonicals)==1 and p.canonicals[0]==expected_canonical,path
        assert len(p.ids)==len(set(p.ids))and all(p.details),path
        assert path.stat().st_size<150_000,(path,path.stat().st_size)
    assert len(pages)==61
    assert len({p.titles[0]for p in pages.values()})==61
    assert len({p.descriptions[0]for p in pages.values()})==61
    checkedlinks=0
    for path,p in pages.items():
        for href in p.links:
            u=urlsplit(href)
            if u.scheme or u.netloc:assert u.scheme in('https','http');continue
            checkedlinks+=1;target=(path.parent/unquote(u.path)).resolve()if u.path else path
            if target.is_dir():target=target/'index.html'
            assert target.is_relative_to(ROOT)and target.is_file(),(path,href)
            if u.fragment:
                if target not in pages:
                    extra=Page();extra.feed(target.read_text());pages_for_ids=extra
                else:pages_for_ids=pages[target]
                assert unquote(u.fragment)in pages_for_ids.ids,(path,href)
    manifestby={e['path']:e for e in manifest['responses']}
    for e in entries:
        r=e['record'];p=pages[(ROOT/e['path']).resolve()];m=manifestby[e['path']]
        assert p.texts['original-prompt']==r['prompt'] and p.texts['original-answer']==r['answer_text'],r['id']
        assert hashlib.sha256(p.texts['original-answer'].encode()).hexdigest()==m['answer_sha256']
        assert hashlib.sha256(p.texts['original-prompt'].encode()).hexdigest()==m['prompt_sha256']
        raw_href=builder.href(e['path'],e['raw']);assert raw_href in p.links,(r['id'],'missingrawlink')
        for key,label,items in builder.source_groups(r):
            for item in items:
                url=item if isinstance(item,str)else item.get('url','')
                if url.startswith(('http://','https://')):assert url in p.links,(r['id'],key,url)
    counts=dict(Counter(e['stage']for e in entries));assert counts=={1:12,2:6,3:24,4:18}
    print(json.dumps({'evidence_pages':60,'index_pages':1,'stage_counts':counts,'exact_prompt_and_answer_text':'passed','recorded_source_URL_roles':'passed','local_links_checked':checkedlinks,'all_sections_expanded':True,'max_response_page_bytes':max((ROOT/e['path']).stat().st_size for e in entries)}))

if __name__=='__main__':main()
