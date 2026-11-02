#!/usr/bin/env python3
"""Validate the frozen Stage 3 public data, privacy boundary and offline report."""
import collections
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT/'stages/03-question-sensitivity'
DATA = STAGE/'data'


class Page(HTMLParser):
    def __init__(self):
        super().__init__(); self.ids=[]; self.links=[]; self.details=[]; self.language=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='html':self.language=a.get('lang')
        if 'id'in a:self.ids.append(a['id'])
        if tag=='a'and'href'in a:self.links.append(a['href'])
        if tag=='details':self.details.append('open'in a)


def main():
    load=lambda name:json.loads((DATA/name).read_text())
    protocol,runs,attempts=[load(x+'.json')for x in ['protocol','runs','attempts']]
    assert len(runs)==24 and len(attempts)==27
    assert len({a['id']for a in attempts})==27
    assert len({r['id']for r in runs})==24
    assert set(collections.Counter((r['platform'],r['prompt_id'])for r in runs).values())=={3}
    by={a['id']:a for a in attempts}
    for a in attempts:
        assert a['prompt']==protocol['prompts'][a['prompt_id']]
        assert load(a['raw_file'])==a
        assert a['public_answer_characters']==len(a.get('answer_text',''))
        if a.get('interface')=='Responses API':
            request=load(a['request_file']); response=load(a['response_file'])
            assert request['input']==a['prompt']
            assert request['model']=='gpt-5.6-sol'and request['reasoning']['effort']=='medium'
            assert request['tool_choice']=='required'and request['tools'][0]['type']=='web_search'
            assert request['tools'][0]['external_web_access']is True and request['store']is False
            assert not {'instructions','conversation','previous_response_id','Authorization','api_key'}&request.keys()
            assert a['returned_model']=='gpt-5.6-sol'and a['returned_reasoning']['effort']=='medium'
            assert a['search_observed']and a['body_complete']and a['status']=='completed'
            content=[c for item in response['output']if item['type']=='message'for c in item['content']if c['type']=='output_text']
            assert '\n\n'.join(c['text']for c in content)==a['answer_text']
            annotations=[ann for c in content for ann in c.get('annotations',[])if ann['type']=='url_citation']
            assert [x['url']for x in annotations]==[x['url']for x in a['answer_links']]
    for run in runs:
        a=by[run['selected_attempt_id']]
        assert run['body_complete']and run['platform']==a['platform']
        comparable={k:v for k,v in run.items()if k not in {'selected_attempt_id','historical_ui_attempt_ids'}}
        comparable['id']=a['id']
        assert comparable==a
        code=load('coding/'+a['id']+'.json')
        assert code['source_record']==a['raw_file']
        assert code['source_record_sha256']==hashlib.sha256((DATA/a['raw_file']).read_bytes()).hexdigest()
        assert code['capture_scope']['answer_characters']==len(a['answer_text'])
        for row in code['entity_observations']:
            if isinstance(row.get('evidence'),str):assert row['evidence']in a['answer_text'],(a['id'],'Evidence excerpt differs')
    historical=[a for a in attempts if a['platform']=='ChatGPT Search']
    assert len(historical)==3 and not any(a['body_complete']for a in historical)
    assert collections.Counter(a['status']for a in historical)=={'technical_failure':1,'capture_incomplete':2}
    setup=load('setup-history.json')
    assert len(setup)==4 and sum(x['record_kind']=='non_generation_model_access_check'for x in setup)==3
    assert all(x.get('generation_submitted')is False for x in setup if x['record_kind']=='non_generation_model_access_check')
    assert load('settings-summary.json')['restoration_completed']is True
    forbidden={
        'private conversation/share URL':r'https?://(?:chatgpt\.com/(?:c|s|share)/|grok\.com/c/)',
        'local path or capture link':r'/Users/|(?<!\w)(?:raw|screenshots)/[\w./-]+',
        'opaque provider identifier':r'\b(?:req|resp|ws|msg|rs)_[A-Za-z0-9_-]{12,}\b',
        'email address':r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b|mailto:',
        'credential':r'\bsk-[A-Za-z0-9_-]{16,}|Bearer [A-Za-z0-9._-]{16,}',
        'tracking/session/signed URL parameter':r'[?&](?:(?:a?utm_)\w+|X-Amz-[^=&#\s]+|X-Goog-[^=&#\s]+|roistat_visit|_ga|_bhlid|fbclid|gclid|ck_subscriber_id|sh_kit|fpr|via|client_id|session_id|_rsc|cluster|access_token|refresh_token|token|api_key|signature|credential)=',
        'non-English annotation':r'[\u3400-\u9fff]',
        'private field or stale index':r'"(?:request_id|response_id|call_id|conversation_url|share_url|automation_id|start_index|end_index|output_item_index|content_index)"\s*:',
    }
    files=[p for p in STAGE.rglob('*')if p.is_file()]
    assert not any(p.suffix.lower()in{'.png','.jpg','.jpeg','.har','.log','.command'}for p in files)
    assert not any(p.name in{'api_credentials.py','collect_api.py','capture-pad.html','Set API Key.command'}for p in files)
    for path in files:
        if path.suffix in{'.json','.html','.md','.txt'}:
            text=path.read_text()
            for label,pattern in forbidden.items():assert not re.search(pattern,text,re.I),(path.relative_to(ROOT),label)
    f=json.loads((STAGE/'findings.json').read_text())
    assert not f['validation_issues']and f['counts']['eligible_coded_bodies']==24
    assert f['counts']['historical_chatgpt_ui_submissions']==3
    for name,digest in f['input_sha256'].items():assert hashlib.sha256((DATA/name).read_bytes()).hexdigest()==digest,name
    assert f['review_analysis_code_sha256']==hashlib.sha256((ROOT/'scripts/analysis_extensions.py').read_bytes()).hexdigest()
    ext=f['review_analyses']; assert not ext['validation_issues']
    for pair_group in ext['within_vs_cross']:
        assert len(pair_group['within']['pairs'])==6 and len(pair_group['cross']['pairs'])==9
        if pair_group['platform']=='Grok':
            assert pair_group['within']['summary']['numeric_pairs']==6
            assert pair_group['cross']['summary']['numeric_pairs']==9
    api_m=next(x for x in ext['entity_lenses']['wording_contrasts']if x['platform']=='OpenAI API + web search'and x['intent']=='M')
    strict=api_m['views']['strict']['pooled_overlap']; family=api_m['views']['family']['pooled_overlap']
    assert (strict['intersection'],strict['union'])==(0,7)and(family['intersection'],family['union'])==(1,6)
    human=load('human-review.json')
    assert human['status']=='awaiting_independent_human_review'and human['human_completed_cases']==0
    assert len(human['cases'])==8 and not human['independent_human_validation_completed']
    audit=load('source-audit.json')
    assert audit['summary']['requested_source_URLs']==6 and not audit['all_claims_verified']
    pages={}
    for name in ['index.html','technical-appendix.html']:
        page=Page();document=(STAGE/name).read_text();page.feed(document);pages[name]=page
        assert page.language=='en'and len(page.ids)==len(set(page.ids))and all(page.details)
        assert 'These results do not represent ChatGPT web app performance.'in document
    assert len((STAGE/'index.html').read_bytes())<100_000,'Reader should remain concise; raw evidence belongs in appendix'
    assert len(pages['technical-appendix.html'].details)>300,'Full expanded evidence should remain available'
    for name,page in pages.items():
        for href in page.links:
            u=urlsplit(href)
            if u.scheme or u.netloc:
                assert u.scheme in{'https','http'};continue
            target=(STAGE/unquote(u.path)).resolve()if u.path else STAGE/name
            assert target.is_relative_to(ROOT),href
            if target.is_dir():target=target/'index.html'
            assert target.is_file(),href
            if u.fragment and target.parent==STAGE and target.name in pages:
                assert unquote(u.fragment)in pages[target.name].ids,href
    expected={str(p.relative_to(STAGE))for p in DATA.rglob('*')if p.is_file()}|{'findings.json'}
    with zipfile.ZipFile(STAGE/'public-data.zip')as z:
        assert z.testzip()is None and set(z.namelist())==expected
        for name in z.namelist():assert z.read(name)==(STAGE/name).read_bytes()
    print(json.dumps({'stage':3,'selected_answers':24,'prompt_submissions':27,'historical_UI_failures_or_partial':3,
                      'API_answers':12,'Grok_answers':12,'coding_records':24,'setup_records_not_answers':4,
                      'public_files':len(files),'expanded_appendix_sections':len(pages['technical-appendix.html'].details),
                      'reader_bytes':(STAGE/'index.html').stat().st_size,'report_links':sum(len(page.links)for page in pages.values()),
                      'privacy_and_data_checks':'passed'}))


if __name__=='__main__':main()
