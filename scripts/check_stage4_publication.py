#!/usr/bin/env python3
"""Validate Stage 4's public evidence, redaction, reported metrics and offline links."""
from collections import Counter
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import unquote,urlsplit
import zipfile

ROOT=Path(__file__).resolve().parents[1]
STAGE=ROOT/'stages/04-creator-benchmark'
DATA=STAGE/'data'
read=lambda n:json.loads((DATA/n).read_text())
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def canonical(u):
 p=urlsplit(u);return(p.netloc.lower().removeprefix('www.'),p.path.rstrip('/'))
class Page(HTMLParser):
 def __init__(self):super().__init__();self.ids=[];self.links=[];self.details=[];self.language=None
 def handle_starttag(self,t,a):
  a=dict(a)
  if t=='html':self.language=a.get('lang')
  if 'id'in a:self.ids.append(a['id'])
  if t=='a'and'href'in a:self.links.append(a['href'])
  if t=='details':self.details.append('open'in a)

def main():
 protocol,runs,attempts,coding=[read(n+'.json') for n in ('protocol','runs','attempts','coding')]
 assert len(runs)==len(attempts)==18 and len(coding)==54
 assert len({r['id'] for r in runs})==18 and len({a['id']for a in attempts})==18
 assert set(Counter((r['platform'],r['prompt_id'])for r in runs).values())=={3}
 by={a['id']:a for a in attempts};ri={r['id']:r for r in runs};api=[a for a in attempts if a['interface']=='Responses API']
 assert len(api)==9 and len([a for a in attempts if a['platform']=='Grok'])==9
 for a in attempts:
  assert read(a['raw_file'])==a
  assert a['prompt']==protocol['prompts'][a['prompt_id']]
  assert a['status']=='completed' and a['body_complete'] is True and a['search_observed'] is True
  assert a['public_answer_characters']==len(a['answer_text'])
  if a['interface']=='Responses API':
   req=read(a['request_file']);resp=read(a['response_file'])
   assert req['input']==a['prompt'] and req['model']=='gpt-5.6-sol'and req['reasoning']['effort']=='medium'
   assert req['tool_choice']=='required'and req['tools'][0]['type']=='web_search'and req['tools'][0]['external_web_access']is True
   assert req['store']is False and req['max_tool_calls']==8 and req['max_output_tokens']==32768
   assert not {'instructions','conversation','previous_response_id','Authorization','api_key'}&req.keys()
   assert a['returned_model']=='gpt-5.6-sol'and a['returned_reasoning']['effort']=='medium'
   content=[c for item in resp['output']if item['type']=='message'for c in item['content']if c['type']=='output_text']
   assert '\n\n'.join(c['text']for c in content)==a['answer_text']
   urls=[ann['url']for c in content for ann in c.get('annotations',[])if ann['type']=='url_citation']
   assert urls==[x['url']for x in a['answer_links']]
  else:
   assert a['mode_label']=='Expert'and a['private']is True
   assert a['personalize_using_x']is False and a['personalize_using_history']is False
 for r in runs:
  a=by[r['selected_attempt_id']];assert r['attempt_ids']==[a['id']]
  assert {k:v for k,v in r.items()if k not in {'selected_attempt_id','attempt_ids'}}==a
 assert len({(c['run_id'],c['candidate_id'])for c in coding})==54
 for c in coding:
  assert c['run_id']in ri and c['candidate_id']in protocol['candidate_ids']
  for m in ('citation','mention','recommendation','person_mention','person_recommendation'):assert type(c[m]) is bool
  links={canonical(x['url'])for x in ri[c['run_id']]['answer_links']}
  for u in c['own_content_urls']+c['third_party_urls']:assert canonical(u)in links,(c['run_id'],u)
  assert c['citation']==bool(c['own_content_urls'])
 assert sum(c['citation']for c in coding)==10
 assert sum(c['mention']for c in coding)==sum(c['recommendation']for c in coding)==14
 assert all(not any(c[k]for k in ('citation','mention','recommendation'))for c in coding if ri[c['run_id']]['prompt_id']=='Q2')
 audit=read('audit/source-audit.json');assert len(audit['selected_pages'])==8
 assert Counter(p['candidate_id']for p in audit['selected_pages'])=={'artur-ferreira':3,'aleyda-solis':3,'kevin-indig':2}
 for p in audit['selected_pages']:
  for rid in p['run_ids']:
   c=next(x for x in coding if x['run_id']==rid and x['candidate_id']==p['candidate_id'])
   assert canonical(p['url'])in{canonical(u)for u in c['own_content_urls']}
 freeze=read('collection-freeze.json')
 for n,h in freeze['public_copy_sha256'].items():assert digest(DATA/n)==h
 reg=read('registration-manifest.json');assert reg['submitted_answers_at_registration']==0
 for n,h in reg['public_copy_sha256'].items():assert digest(DATA/n)==h
 assert read('settings-summary.json')['restoration_completed']is True
 assert read('setup-history.json')[0]['request_submitted']is False
 assert all(not i['new_submission']for i in protocol.get('capture_incidents',[]))
 f=json.loads((STAGE/'findings.json').read_text());assert not f['validation_issues']
 assert f['counts']['complete_selected_answers']==18 and f['counts']['candidate_answer_observations']==54
 assert f['counts']['strict_linked_own_citations']==10 and f['counts']['mentions']==f['counts']['recommendations']==14
 assert f['counts']['API_tool_cap_hits']==sum(x.get('tool_limit_reached')is True for x in api)==3
 for n,h in f['input_sha256'].items():assert digest(DATA/n)==h
 assert f['render_code_sha256']==digest(ROOT/'scripts/build_stage4_report_source.py')
 assert f['citation_sensitivity']['linked_or_explicit_plain_address_C']==5
 forbidden={
  'private conversation':r'https?://(?:chatgpt\.com/(?:c|s|share)/|grok\.com/(?:c|chat|share)/)',
  'local path':r'/Users/|(?<!\w)(?:raw|screenshots|evidence)/[\w./-]+',
  'provider ID':r'\b(?:resp|req|ws|msg|rs)_[A-Za-z0-9_-]{12,}\b',
  'email':r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b|mailto:',
  'credential':r'\bsk-[A-Za-z0-9_-]{16,}|Bearer [A-Za-z0-9._-]{16,}',
  'private field/index':r'"(?:request_id|response_id|call_id|conversation_url|share_url|automation_id|start_index|end_index|output_item_index|content_index|settings_restored_to)"\s*:',
  'original preference':r'ON/ON',
  'tracking/session/signature URL':r'[?&](?:(?:a?utm_)\w+|trk|ref|X-Amz-[^=&#\s]+|X-Goog-[^=&#\s]+|roistat_visit|_ga|_bhlid|fbclid|gclid|ck_subscriber_id|sh_kit|fpr|via|client_id|session_id|_rsc|cluster|access_token|refresh_token|token|api_key|signature|credential)=',
  'untranslated annotation':r'[\u3400-\u9fff]'}
 files=[p for p in STAGE.rglob('*')if p.is_file()]
 assert not any(p.suffix.lower()in{'.png','.jpg','.jpeg','.har','.log','.command'}for p in files)
 for path in files:
  if path.suffix in{'.json','.html','.md','.txt'}:
   text=path.read_text()
   for name,pat in forbidden.items():assert not re.search(pat,text,re.I),(path.relative_to(ROOT),name)
 pages={}
 for n in ('index.html','technical-appendix.html'):
  p=Page();doc=(STAGE/n).read_text();p.feed(doc);pages[n]=p
  assert p.language=='en'and len(p.ids)==len(set(p.ids))and all(p.details)
  assert 'data-report-series="v1"'in doc and 'id="report-version"'in doc
  assert 'OpenAI API'in doc and 'consumer ChatGPT Search'in doc
  assert 'recommended'in doc.lower() and 'Discoverable?'not in doc
  assert '3/9'in doc and 'tool'in doc
 for n,p in pages.items():
  for href in p.links:
   u=urlsplit(href)
   if u.scheme or u.netloc:assert u.scheme in{'http','https'};continue
   target=(STAGE/unquote(u.path)).resolve()if u.path else STAGE/n
   if target.is_dir():target=target/'index.html'
   assert target.is_relative_to(ROOT)and target.is_file(),(n,href)
   if u.fragment and target.parent==STAGE and target.name in pages:assert unquote(u.fragment)in pages[target.name].ids,(n,href)
 assert len(pages['technical-appendix.html'].details)>=36
 assert (STAGE/'index.html').stat().st_size<100_000
 expected={str(p.relative_to(STAGE))for p in DATA.rglob('*')if p.is_file()}|{'findings.json'}
 with zipfile.ZipFile(STAGE/'public-data.zip')as z:
  assert z.testzip()is None and set(z.namelist())==expected
  for n in z.namelist():assert z.read(n)==(STAGE/n).read_bytes()
 print(json.dumps({'stage':4,'selected_answers':18,'actual_submissions':18,'coding_rows':54,'API_requests':9,'API_response_copies':9,'audited_pages':8,'strict_C':10,'M':14,'R':14,'API_tool_cap_hits':3,'reader_bytes':(STAGE/'index.html').stat().st_size,'public_files':len(files),'privacy_evidence_archive_links':'passed'}))

if __name__=='__main__':main()
