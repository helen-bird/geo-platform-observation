#!/usr/bin/env python3
"""Build Stage 4 offline from public-only evidence, without paid calls or private paths."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import zipfile
import build_stage4_report_source as renderer
from report_series import finish_page

ROOT=Path(__file__).resolve().parents[1]
STAGE=ROOT/'stages/04-creator-benchmark'
DATA=STAGE/'data'
SITE='https://helen-bird.github.io/geo-platform-observation/stages/04-creator-benchmark/'
read=lambda n:json.loads((DATA/n).read_text())
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
 runs=read('runs.json');coding=read('coding.json');audit=read('audit/source-audit.json');protocol=read('protocol.json')
 assert len(runs)==18 and len(coding)==54 and len(audit['selected_pages'])==8
 indexed={(x['run_id'],x['candidate_id']):x for x in coding}
 metrics=('citation','mention','recommendation','person_mention','person_recommendation')
 def counts(selected,cid):return {'answers':len(selected),**{m:sum(indexed[r['id'],cid][m] is True for r in selected) for m in metrics}}
 by_question=[{'prompt_id':q,'platform':env,'candidate_id':cid,**counts([r for r in runs if r['prompt_id']==q and r['platform']==env],cid)} for q in ('Q1','Q2','Q3') for env in ('OpenAI API + web search','Grok') for cid in protocol['candidate_ids']]
 pooled=[{'platform':env,'candidate_id':cid,**counts([r for r in runs if r['platform']==env],cid)} for env in ('OpenAI API + web search','Grok') for cid in protocol['candidate_ids']]
 findings={'edition':'Redacted public edition','condition_notice':'OpenAI API + web search, not consumer ChatGPT Search. These results do not represent ChatGPT web app performance.',
  'counts':{'complete_selected_answers':18,'actual_submissions':len(read('attempts.json')),'candidate_answer_observations':54,'actual_own_byline_audit_pages':8,'strict_linked_own_citations':sum(x['citation'] is True for x in coding),'mentions':sum(x['mention'] is True for x in coding),'recommendations':sum(x['recommendation'] is True for x in coding),'API_tool_cap_hits':sum(r.get('tool_limit_reached') is True for r in runs)},
  'by_question':by_question,'all_question_pooled_secondary':pooled,
  'citation_sensitivity':{'candidate_id':'artur-ferreira','platform':'Grok','strict_linked_own_C':3,'linked_or_explicit_plain_address_C':5,'denominator':9,'primary_rule_unchanged':True},
  'estimated_api_usd':protocol['api_collection']['estimated_spend_usd'],'billing_reconciled':False,
  'validation_issues':[], 'input_sha256':{str(p.relative_to(DATA)):digest(p) for p in sorted(DATA.rglob('*')) if p.is_file()},
  'render_code_sha256':digest(Path(renderer.__file__)),'coding_method':'Assistant observational judgments; no independent human double coding or underlying-study replication.',
  'interpretation':'Counts describe this historically selected candidate set, prompt bank, environments and date. They do not prove a causal GEO tactic, long-term recommendation probability or business effect.'}
 (STAGE/'findings.json').write_text(json.dumps(findings,ensure_ascii=True,indent=2)+'\n')
 renderer.build(DATA,STAGE)
 notice=('<blockquote><p><strong>Redacted public edition.</strong> All 18 original answers, real submissions and assistant coding are available below. Private account UI, original preference values, conversations and service identifiers remain local. Necessary source-URL tracking removal is documented.</p>'
  '<p><a href="public-data.zip">Download Stage 4 public data</a> · <a href="data/README.md">Data guide</a> · <a href="data/publication-notes.json">Publication scope</a> · <a href="data/review-response.md">Peer-review decisions</a></p></blockquote>')
 for name,kind in (('report.html','reader'),('technical-appendix.html','appendix')):
  path=STAGE/name;doc=path.read_text()
  doc=doc.replace('href="report.html','href="index.html')
  doc=doc.replace('Local learning record','Public learning record')
  doc=re.sub(r'<div class="experiment-series">.*?</div>','',doc,count=1,flags=re.S)
  doc=doc.replace('</main>',notice+'</main>',1)
  doc=doc.replace('</head>','<link rel="canonical" href="'+SITE+('technical-appendix.html' if kind=='appendix' else '')+'"><meta name="description" content="GEO Lab 04 compares creator and content-asset recommendations in 18 OpenAI API web-search and Grok Expert answers, with an eight-page source audit. No causal GEO claim."></head>',1)
  doc=finish_page(doc,4,kind=kind)
  (STAGE/('index.html' if kind=='reader' else name)).write_text(doc)
 # report.html is a temporary renderer output; keep one canonical reader path.
 (STAGE/'report.html').unlink()
 with zipfile.ZipFile(STAGE/'public-data.zip','w',zipfile.ZIP_DEFLATED) as archive:
  for path in sorted([p for p in DATA.rglob('*') if p.is_file()]+[STAGE/'findings.json']):
   name=str(path.relative_to(STAGE));info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16;archive.writestr(info,path.read_bytes())
 print(json.dumps({'stage':4,**findings['counts'],'reader_bytes':(STAGE/'index.html').stat().st_size}))

if __name__=='__main__':main()
