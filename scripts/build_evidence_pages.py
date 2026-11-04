#!/usr/bin/env python3
"""Build small, immutable-text response views from the existing redacted datasets."""
from collections import Counter
from html import escape
import hashlib
import json
from pathlib import Path
import posixpath
import re

ROOT = Path(__file__).resolve().parents[1]
SITE = 'https://helen-bird.github.io/geo-platform-observation/'
OUT = ROOT/'evidence'
STAGES = {
    1: ('data', '', 12, 'AI Recommendations'),
    2: ('stages/02-post-discovery/data', 'stages/02-post-discovery/', 6, 'Content Discovery'),
    3: ('stages/03-question-sensitivity/data', 'stages/03-question-sensitivity/', 24, 'Prompt Sensitivity'),
    4: ('stages/04-creator-benchmark/data', 'stages/04-creator-benchmark/', 18, 'Creator Benchmark'),
}
CSS = '''
:root{--ink:#182b36;--muted:#4f6873;--line:#dce5e9;--accent:#176a76;--soft:#eaf4f4}*{box-sizing:border-box}html{scroll-padding-top:20px;scrollbar-color:#7b9da5 #edf3f5}body{margin:0;color:var(--ink);background:white;font:16px/1.65 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}::selection{background:#b8dedf;color:#12383f}a{color:var(--accent);text-underline-offset:3px;overflow-wrap:anywhere}a:hover{text-decoration-thickness:2px}:focus-visible{outline:3px solid var(--accent);outline-offset:4px}.layout{display:grid;grid-template-columns:235px minmax(0,1fr);min-height:100vh}nav{position:sticky;top:0;height:100vh;overflow:auto;background:#17343d;color:#edf7f7;padding:30px 22px}nav strong{display:block;font-size:19px;line-height:1.35;margin-bottom:18px}nav a{display:block;color:#e0eeee;text-decoration:none;padding:8px 0;font-size:14px}nav p{font-size:12px;color:#bed4db}main{min-width:0;max-width:1260px;padding:44px 5vw 80px}h1{font-size:clamp(29px,3vw,40px);line-height:1.2;letter-spacing:-.03em;margin:0 0 22px;max-width:28ch;overflow-wrap:anywhere}h2{font-size:25px;line-height:1.3;margin:36px 0 12px}h3{font-size:19px;line-height:1.4;margin:28px 0 10px}h1,h2,h3{text-wrap:balance}p,li,blockquote{max-width:72ch}p{margin:10px 0}blockquote{border-left:1px solid #7bafb5;background:var(--soft);margin:18px 0;padding:12px 17px;color:#385560;font-size:14px}blockquote p:first-child{margin-top:0}blockquote p:last-child{margin-bottom:0}.answer,.prompt{white-space:pre-wrap;overflow-wrap:anywhere;max-width:72ch;font:inherit;tab-size:4;margin:14px 0}.record-meta{font-size:14px;max-width:75ch}.record-meta dt{font-weight:700;margin-top:12px}.record-meta dd{margin:2px 0 10px;overflow-wrap:anywhere}.record{border-top:1px solid var(--line);padding:22px 0}.record h3{margin:0 0 8px}.record p{font-size:14px}.source-role,.provenance{font-size:14px;color:var(--muted)}.sources{padding-left:24px;max-width:75ch}.sources li{padding:5px 0;overflow-wrap:anywhere}.sources .source-role{display:block}.links{display:flex;flex-wrap:wrap;gap:8px 22px;margin:18px 0}.footer{font-size:13px;color:var(--muted);border-top:1px solid var(--line);padding-top:20px;margin-top:34px}.skip{position:absolute;left:12px;top:-80px;background:white;padding:10px;z-index:5}.skip:focus{top:12px}
@media(max-width:950px){.layout{grid-template-columns:190px minmax(0,1fr)}nav{padding:25px 17px}main{padding:30px}}
@media(max-width:650px){.layout{display:block}nav{position:static;height:auto;padding:18px 20px}nav strong{margin-bottom:10px;font-size:18px}.nav-links{display:flex;flex-wrap:wrap;gap:3px 18px}nav a{font-size:12px;padding:5px 0}nav p{margin:5px 0}main{padding:28px 20px 54px}h1{font-size:29px}h2{font-size:24px}.links{gap:9px 18px}.record-meta{font-size:13px}}
@media print{nav{display:none}.layout{display:block}main{max-width:none;padding:0}a{color:inherit}}
'''


def read(path): return json.loads((ROOT/path).read_text())
def digest(text): return hashlib.sha256(text.encode('utf-8')).hexdigest()
def pretty(value): return value if isinstance(value, str) else json.dumps(value, ensure_ascii=True, indent=2)
def href(path, target):
    try:
        from site_metadata import canonical_path
        target=canonical_path(target or 'index.html')
    except ImportError:
        if target.endswith('index.html'):target=target[:-len('index.html')]
    relative=posixpath.relpath(target or '.',posixpath.dirname(path))
    return relative+'/' if not target or target.endswith('/') else relative
def link(path, target, text): return '<a href="'+escape(href(path,target),quote=True)+'">'+escape(text)+'</a>'


def shell(title, description, path, nav, body, stage=None):
    doc='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(title)+'</title><meta name="description" content="'+escape(description,quote=True)+'"><link rel="canonical" href="'+SITE+path+'"><style>'+CSS+'</style></head><body><a class="skip" href="#main">Skip to evidence</a><div class="layout"><nav aria-label="Evidence contents"><strong>GEO Learning Log</strong><div class="nav-links">'+nav+'</div><p>Selected original responses.<br>Complete archives remain available.</p></nav><main id="main"><h1>'+escape(title)+'</h1>'+body+'<p class="footer">Curated and published by Helen Bird. Original responses were generated by the recorded AI platform; their claims are not independently verified by this archive.</p></main></div></body></html>'
    # Existing response captures contain a few non-English UI badges. Numeric
    # references preserve exact extracted text without rewriting the response.
    doc=re.sub(r'[\u3400-\u9fff]',lambda m:'&#'+str(ord(m.group()))+';',doc)
    try:
        from site_metadata import finalize_page
    except ImportError:
        return doc
    return finalize_page(doc,path,kind='evidence' if stage else 'evidence-index',stage=stage)


def entries():
    found=[]
    for stage,(data,report,count,label) in STAGES.items():
        runs=read(data+'/runs.json');assert len(runs)==count
        for r in runs:
            identifier=r['id'];assert re.fullmatch(r'[A-Za-z0-9_-]+',identifier)
            raw=r['raw_file'] if stage==1 else data+'/'+r['raw_file']
            original=read(raw)
            assert r['answer_text']==original['answer_text'] and r['prompt']==original['prompt'],identifier
            found.append({'stage':stage,'label':label,'record':r,'raw':raw,'report':report,'data':data,'path':f'evidence/stage-{stage:02d}/{identifier}.html'})
    assert len(found)==60
    return found


def model(r): return r.get('returned_model') or r.get('model_label') or 'Not recorded'
def submitted(r): return r.get('submitted_at') or r.get('started_at') or r.get('date_local') or 'Not recorded'
def query(r): return r.get('prompt_id') or r.get('question_id') or r.get('condition') or 'Not recorded'
def search(r):
    if r.get('search_observed') is True: return 'Actual search activity observed; exact controls and evidence remain in the raw record.'
    if r.get('search_observed') is False: return 'Search activity not established in this record.'
    return str(r.get('search_status','Search observation not recorded'))


def source_groups(r):
    result=[]
    for key,label in [('answer_links','Recorded answer-body links'),('sources','Recorded sources, with original attribution roles'),('cited_sources','Additional recorded cited sources'),('explicit_body_urls','Explicit plain-text body URLs'),('retrieval_sources','Retrieval-only / source-panel inventory')]:
        if r.get(key):result.append((key,label,r[key]))
    return result


def render_sources(r):
    groups=source_groups(r)
    if not groups:return '<p>No source URL was captured for this selected response. This does not establish that no search occurred.</p>'
    body='<blockquote><p>These are the source roles recorded in the public dataset. A retrieval or source-panel item is not automatically an answer-body citation. A URL supplied in the prompt and repeated by an answer does not prove content access. No destination has been repaired or independently validated here.</p></blockquote>'
    for key,label,items in groups:
        body+='<section><h3>'+escape(label)+' ('+str(len(items))+')</h3><ul class="sources">'
        for item in items:
            item={'url':item,'kind':'Explicit plain-text address, not an inline citation'} if isinstance(item,str) else item
            url=item.get('url','');name=item.get('title')or item.get('text')or url or 'No URL recorded';kind=item.get('kind')or('Retrieval/source-panel entry'if key=='retrieval_sources'else'Attribution not specified in this item')
            if url.startswith(('https://','http://')):body+='<li><a href="'+escape(url,quote=True)+'">'+escape(name)+'</a><span class="source-role">'+escape(kind)+' · '+escape(item.get('domain')or url.split('/')[2])+'</span></li>'
            else:body+='<li>'+escape(pretty(item))+'</li>'
        body+='</ul></section>'
    return body


def render_record(e):
    r=e['record'];path=e['path'];stage=e['stage'];record_id=r['id'];question=query(r)
    nav=link(path,'evidence/index.html','All selected responses')+link(path,e['report'],'Lab report')+link(path,e['report']+'technical-appendix.html','Full technical appendix')+link(path,'learning-hub/','Learning Hub')+'<a href="#conditions">Recorded conditions</a><a href="#prompt">Original prompt</a><a href="#answer">Original answer</a><a href="#sources">Recorded sources</a><a href="#provenance">Evidence and qualifications</a>'
    body='<p>This page presents one selected response from GEO Lab #'+f'{stage:02d}'+'. It adds a smaller reading and citation entry point; it does not replace the full archive or collect a new answer.</p>'
    if stage in(3,4):body+='<blockquote><p>The OpenAI arm uses the Responses API with web search and does not represent consumer ChatGPT Search. Grok records identify their actual consumer-interface mode and available model label.</p></blockquote>'
    if stage==2:body+='<blockquote><p>This lab includes a user-supplied manual replacement and recovered responses. Read the raw record and complete appendix for the conditions and capture qualifications; selected answer completeness does not establish successful discovery.</p></blockquote>'
    complete='Selected complete public answer; capture and independent verification limits are preserved below.' if stage==1 else ('Recorded body complete' if r.get('body_complete') is True else 'Body completeness not established')
    pairs=[('Record ID',record_id),('Platform',r['platform']),('Question / condition',question),('Repeat',str(r.get('repeat','Single selected planned position'))),('Model label',model(r)),('Visible mode',r.get('mode_label','Not independently recorded')),('Reasoning',r.get('reasoning_effort','See model/mode evidence in the raw record')),('Submitted / first recorded time',submitted(r)),('Completeness',complete),('Search',search(r))]
    body+='<section id="conditions"><h2>Recorded conditions</h2><dl class="record-meta">'+''.join('<dt>'+escape(k)+'</dt><dd>'+escape(str(v))+'</dd>'for k,v in pairs)+'</dl></section>'
    body+='<section id="prompt"><h2>Original prompt</h2><pre class="prompt" id="original-prompt">'+escape(r['prompt'])+'</pre><blockquote><p>The agreed prompt is reproduced exactly. Any recorded difference in the actual submitted text or search UI is retained in the raw record and full appendix.</p></blockquote></section>'
    body+='<section id="answer"><h2>Original answer</h2><pre class="answer" id="original-answer">'+escape(r['answer_text'])+'</pre></section>'
    body+='<section id="sources"><h2>Recorded sources</h2>'+render_sources(r)+'</section>'
    body+='<section id="provenance"><h2>Evidence and qualifications</h2><div class="links">'+link(path,e['raw'],'Read original public JSON')+link(path,e['report']+'technical-appendix.html','Read complete evidence and failures')+link(path,e['report']+'public-data.zip','Download public dataset')+'</div>'
    body+='<blockquote><p>This is the existing redacted public record. It has not been rewritten for this page. Earlier privacy edits and collection qualifications continue to apply. Editorial text is English; a few original captures retain non-English UI badges or source-panel date labels. An answer’s empirical claims are platform output, not verified findings of this archive.</p></blockquote>'
    for key,label in [('capture_method','Capture method'),('capture_provenance','Capture provenance'),('search_evidence','Search evidence'),('notes','Record notes'),('body_review','Body review'),('answer_privacy_edits','Existing public-text privacy policy')]:
        if r.get(key):body+='<h3>'+escape(label)+'</h3><p class="provenance">'+escape(pretty(r[key])).replace('\n','<br>')+'</p>'
    body+='<p class="provenance">Prompt SHA-256: '+digest(r['prompt'])+'<br>Answer SHA-256: '+digest(r['answer_text'])+'</p></section>'
    title=f'GEO Lab #{stage:02d} · {record_id} · Original response'
    description=f'Original {r["platform"]} response for GEO Lab {stage:02d}, question {question}, record {record_id}, with exact prompt, recorded conditions, source roles and public evidence.'
    return shell(title,description,path,nav,body,stage)


def render_index(all_entries):
    path='evidence/index.html';nav=link(path,'learning-hub/','Learning Hub')+''.join('<a href="#stage-'+str(s)+'">GEO Lab #'+f'{s:02d}'+'</a>'for s in STAGES)
    body='<p>Read the 60 selected original responses individually, then return to each lab’s full evidence archive for all submissions, failures, coding and limitations.</p><blockquote><p>These smaller pages preserve the existing redacted prompt and answer text exactly. They introduce no new responses or empirical conclusions. Helen Bird curates the research record; the responses are AI-generated. Separate answer links, retrieval inventory and plain-text addresses retain their recorded roles.</p><p>Labs #03 and #04 use OpenAI Responses API + web search, which does not represent consumer ChatGPT Search. Model, timing and capture differences in earlier labs remain documented.</p></blockquote>'
    for stage,(data,report,count,label) in STAGES.items():
        body+='<section id="stage-'+str(stage)+'"><h2>GEO Lab #'+f'{stage:02d}'+' · '+escape(label)+'</h2><div class="links">'+link(path,report,'Read lab report')+link(path,report+'technical-appendix.html','Read full evidence archive')+link(path,report+'public-data.zip','Download public data')+'</div>'
        for e in all_entries:
            if e['stage']!=stage:continue
            r=e['record'];body+='<article class="record"><h3>'+link(path,e['path'],r['id'])+'</h3><p>'+escape(r['platform'])+' · '+escape(str(query(r)))+' · '+escape(model(r))+'<br>Submitted / first recorded: '+escape(submitted(r))+'</p><p>'+escape(r['prompt'])+'</p><p class="source-role">Selected public response; full capture and completeness qualifications are available on the response page and in the archive.</p></article>'
        body+='</section>'
    body+='<p>'+link(path,'evidence/manifest.json','Response paths and exact-text hashes')+'</p>'
    return shell('GEO Lab · Original response index','An index of 60 selected original GEO Lab responses, with exact prompt and answer text, source attribution roles, model conditions and links to complete public archives.',path,nav,body)


def main():
    all_entries=entries();OUT.mkdir(exist_ok=True);expected={'index.html','manifest.json'};manifest=[]
    for e in all_entries:
        r=e['record'];destination=ROOT/e['path'];destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(render_record(e));expected.add(str(destination.relative_to(OUT)))
        manifest.append({'stage':e['stage'],'record_id':r['id'],'path':e['path'],'raw_record':e['raw'],'source_dataset':e['data']+'/runs.json','prompt_sha256':digest(r['prompt']),'answer_sha256':digest(r['answer_text']),'prompt_characters':len(r['prompt']),'answer_characters':len(r['answer_text']),'source_roles':{key:len(items)for key,label,items in source_groups(r)}})
    (OUT/'index.html').write_text(render_index(all_entries))
    (OUT/'manifest.json').write_text(json.dumps({'scope':'Selected original redacted responses only; full archives retain all submissions, failures, coding and limits. No new model calls.','curator':'Helen Bird','counts':dict(sorted(Counter(e['stage']for e in all_entries).items())),'responses':manifest},ensure_ascii=True,indent=2)+'\n')
    unexpected=[str(p.relative_to(OUT))for p in OUT.rglob('*')if p.is_file()and str(p.relative_to(OUT))not in expected]
    assert not unexpected,('Unexpected files in generated evidence directory',unexpected)
    print(json.dumps({'selected_response_pages':len(all_entries),'index':'evidence/index.html','stage_counts':dict(Counter(e['stage']for e in all_entries)),'data_modified':False,'model_calls':0}))


if __name__=='__main__':main()
