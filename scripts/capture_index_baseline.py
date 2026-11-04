#!/usr/bin/env python3
"""Capture an immutable pre-submission baseline without inferring Google index state."""
import argparse,csv,datetime,hashlib,json,re,shutil,ssl,subprocess,time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.parse import urljoin,urlsplit
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
SITE='https://helen-bird.github.io/geo-platform-observation/'
FIRST='2026-11-04'
class Page(HTMLParser):
    def __init__(self):super().__init__();self.canonical=[];self.robots=[];self.title='';self.intitle=False
    def handle_starttag(self,t,a):
        a=dict(a)
        if t=='link'and'canonical'in a.get('rel','').split():self.canonical.append(a.get('href'))
        if t=='meta'and a.get('name','').lower()in('robots','googlebot'):self.robots.append(a.get('content',''))
        if t=='title':self.intitle=True
    def handle_endtag(self,t):
        if t=='title':self.intitle=False
    def handle_data(self,s):
        if self.intitle:self.title+=s
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def dump(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--inventory-output',type=Path);args=ap.parse_args();out=args.output.resolve()
    if out.is_relative_to(ROOT):raise SystemExit('Private baseline must stay outside the public website repository')
    if(out/'baseline-index-status.json').exists():raise SystemExit('Immutable baseline already exists; never backfill later checks')
    out.mkdir(parents=True,exist_ok=True);started=now();head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();tracked=[n for n in subprocess.check_output(['git','ls-files','-z'],cwd=ROOT,text=True).split('\0')if n];html=[n for n in tracked if n.endswith('.html')]
    primary={'index.html','learning-hub/index.html','stages/02-post-discovery/index.html','stages/03-question-sensitivity/index.html','stages/04-creator-benchmark/index.html','evidence/index.html'}
    candidates=[]
    for name in html:
        page=Page();page.feed((ROOT/name).read_text());canonical=page.canonical[0]if len(page.canonical)==1 else None
        category='primary_content'if name in primary else('technical_appendix'if name.endswith('technical-appendix.html')else'excluded')
        monitor=category!='excluded';reason='Original research and learning navigation'if category=='primary_content'else('Unique original answers, methods, failures and source provenance; useful independent evidence'if category=='technical_appendix'else('Supplemental individual response archive; crawlable but outside the initial editorial monitoring scope'if name.startswith('evidence/')else'Error template or site-ownership verification, not search-result content'))
        noindex=any('noindex'in r.lower()for r in page.robots)
        url=canonical or SITE+name
        assert url.startswith(SITE)and urlsplit(url).scheme=='https'
        candidates.append({'url':url,'source_file':name,'title':page.title,'canonical':canonical,'canonical_count':len(page.canonical),'category':category,'monitor':monitor,'sitemap_include':monitor,'indexing_desired':monitor or name.startswith('evidence/'),'noindex_in_source':noindex,'decision_reason':reason})
    assert len({c['url']for c in candidates})==len(candidates),'Aliases must not duplicate content'
    monitored=[c for c in candidates if c['monitor']];assert len(monitored)==10
    http=[];ctx=ssl.create_default_context(cafile='/etc/ssl/cert.pem');max_requests=160;request_count=0
    for c in candidates:
        url=c['url'];attempts=[]
        for attempt in(1,2):
            assert request_count<max_requests;request_count+=1;time.sleep(0.35)
            r={'url':url,'checked_at':now(),'attempt':attempt,'method':'GET','cookies_sent':False,'authorization_sent':False}
            try:
                req=Request(url,headers={'User-Agent':'GEO-Lab-Index-Baseline/1.0'})
                try:response=urlopen(req,context=ctx,timeout=25)
                except HTTPError as e:response=e
                with response:body=response.read();r.update(http_status=response.status,final_url=response.url,content_type=response.headers.get('Content-Type'),x_robots_tag=response.headers.get('X-Robots-Tag',''),sha256=hashlib.sha256(body).hexdigest())
                if r['http_status']==200:
                    page=Page();page.feed(body.decode('utf-8',errors='replace'));r.update(live_canonical=page.canonical,live_meta_robots=page.robots,live_title=page.title,matches_tracked_file=body==(ROOT/c['source_file']).read_bytes());r['noindex_observed']='noindex'in(r['x_robots_tag']+' '+' '.join(page.robots)).lower()
                attempts.append(r);break
            except(URLError,OSError,TimeoutError)as e:
                r.update(error=type(e).__name__+': '+str(e));attempts.append(r)
        http.append({'url':url,'source_file':c['source_file'],'attempts':attempts,'final':attempts[-1]});dump(out/'http-baseline.json',http)
    by={r['url']:r['final']for r in http}
    for c in monitored:
        r=by[c['url']];assert r.get('http_status')==200 and r.get('live_canonical')==[c['url']]and not r.get('noindex_observed')and r.get('matches_tracked_file'),c['url']
    checked=now();fields=('verdict','coverageState','indexingState','pageFetchState','robotsTxtState','lastCrawlTime','googleCanonical','userCanonical','sitemap','referringUrls')
    rows=[{'url':c['url'],'category':c['category'],'status':'AUTH_REQUIRED','index_status':'UNKNOWN','source':'not_queried_auth_required','checked_at':checked,'api_request_performed':False,'raw_api_response':None,**{k:None for k in fields},'error':{'category':'AUTH_REQUIRED','reason':'No authorized URL Inspection call performed by this technical baseline collector; any account-access diagnostic is retained separately in private evidence.'}}for c in monitored]
    manual=json.loads((out/'manual-historical-evidence.json').read_text())if(out/'manual-historical-evidence.json').exists()else None
    baseline={'property':SITE,'captured_at':checked,'started_at':started,'git_commit':head,'source':'pre-submission technical observations plus explicitly unavailable API index data','api_scope_required':'https://www.googleapis.com/auth/webmasters.readonly','sitemap_submission_performed_before_capture':False,'website_changes_performed_before_capture':False,'existing_sitemap_note':'Nine-URL sitemap was already deployed in prior technical-maintenance task; this capture precedes the new submission/monitoring setup.','urls':rows,'technical_inventory':candidates,'manual_historical_evidence':manual,'API_counts':{'urls':len(rows),'INDEXED':0,'NOT_INDEXED':0,'UNKNOWN_OR_AUTH_REQUIRED':len(rows)},'request_count':request_count,'method_limits':'HTTP200 and canonical/noindex checks do not establish Google indexing. Two owner-reported manual observations remain separate and are not API fields.'}
    dump(out/'baseline-index-status.json',baseline)
    headers=['url','category','status','index_status','source','checked_at','api_request_performed']+list(fields)
    with(out/'baseline-index-status.csv').open('w',newline='')as f:
        w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows({k:r.get(k)for k in headers}for r in rows)
    summary=f'''# Google\u7d22\u5f15\u72b6\u6001\u57fa\u7ebf\n\n\u91c7\u96c6\u65f6\u95f4：{checked}；\u6e90\u63d0\u4ea4：`{head}`。\u5171\u53d1\u73b0{len(candidates)}\u4e2a\u72ec\u7acbHTML\u5185\u5bb9/\u7279\u6b8a\u6587\u4ef6，\u89c4\u8303\u53bb\u91cd\u540e\u76d1\u6d4b{len(monitored)}\u4e2a\u91cd\u8981\u5165\u53e3（6\u4e2aprimary_content\u542b\u8bc1\u636e\u7d22\u5f15，4\u4e2atechnical_appendix）；60\u4e2a\u5355\u6761\u56de\u7b54\u8f85\u52a9\u6863\u6848\u548c2\u4e2a\u7279\u6b8a\u6587\u4ef6\u4e0d\u7eb3\u5165\u521d\u59cb\u76d1\u6d4b，\u4e0d\u7ed9\u5b83\u4eec\u6dfb\u52a0noindex。\n\n\u5f53\u524dURLInspectionAPI\u57fa\u7ebf：\u5df2\u786e\u8ba4INDEXED0，\u5df2\u786e\u8ba4NOT_INDEXED0，UNKNOWN/AUTH_REQUIRED{len(rows)}。\u6ca1\u6709URLInspection\u54cd\u5e94；\u4e0d\u80fd\u628a403\u5c5e\u6027\u6388\u6743\u5931\u8d25\u89e3\u91ca\u4e3a\u672a\u7d22\u5f15。\n\n\u7528\u6237\u53e6\u884c\u62a5\u544a：2026-11-04\u9996\u9875\u548cLearningHub\u672a\u7d22\u5f15、\u5b9e\u65f6\u7f51\u5740\u6d4b\u8bd5\u901a\u8fc7、\u5c1a\u672a\u8bf7\u6c42\u7d22\u5f15；\u6765\u6e90manual_search_console_inspection，\u5177\u4f53\u68c0\u67e5\u65f6\u95f4\u672a\u77e5。\u8fd9\u4e24\u9879\u4fdd\u7559\u4e3a\u72ec\u7acb\u5386\u53f2\u8bc1\u636e，\u4e0d\u5192\u5145API\u6216\u672c\u6b21\u5b9e\u65f6\u68c0\u67e5。\n\n\u6240\u670910\u4e2a\u91cd\u8981\u89c4\u8303URL\u672c\u8f6e\u533f\u540dGET200、canonical\u81ea\u6307、\u672a\u89c2\u5bdf\u5230noindex、\u4e0e\u4ed3\u5e93\u6587\u4ef6\u5b57\u8282\u4e00\u81f4。HTTP\u4e0e\u7d22\u5f15\u72b6\u6001\u4e25\u683c\u5206\u5f00。\u5df2\u67099URLSitemap\u6765\u81ea\u6b64\u524d\u6280\u672f\u4fee\u590d，\u5f53\u524d\u57fa\u7ebf\u5728\u672c\u8f6e\u66f4\u6539Sitemap\u548c\u63d0\u4ea4Google\u524d\u4fdd\u5b58；\u672a\u56de\u586b\u5c06\u6765\u6570\u636e。\n\n\u540e\u7eed\u6388\u6743\u540e\u521b\u5efa\u65b0\u7684\u65f6\u95f4\u6233\u5feb\u7167，\u4e0d\u4fee\u6539\u672c\u57fa\u7ebf。\u5b8c\u6574HTTP\u4e0e\u5206\u7c7b\u89c1http-baseline.json；API\u5b57\u6bb5\u5747\u4fdd\u7559null\u4ee5\u8868\u793a\u672a\u53d6\u5f97，\u975e\u5426\u5b9a\u72b6\u6001。\n''';(out/'baseline-summary.md').write_text(summary)
    inventory={'schema_version':1,'site_url':SITE,'source_repository':'helen-bird/geo-platform-observation','generated_from_commit':head,'inventory_policy':'Ten important editorial/navigation/appendix routes; supplemental original-answer archives remain crawlable outside the initial monitor. Verification/error assets excluded. No Google index data in this public file.','urls':[{k:c[k]for k in('url','category','monitor','sitemap_include','indexing_desired','source_file','decision_reason')}for c in monitored],'excluded_urls':[{k:c[k]for k in('url','category','monitor','indexing_desired','source_file','decision_reason')}for c in candidates if not c['monitor']]}
    dump(out/'canonical-url-inventory.json',inventory)
    if args.inventory_output:dump(args.inventory_output,inventory)
    checklist=[]
    for priority,c in enumerate([c for c in monitored if c['category']=='primary_content'and c['source_file']!='evidence/index.html'],1):
        history=next((x for x in(manual or{}).get('observations',[])if x['url']==c['url']),None)
        checklist.append({'URL':c['url'],'current_index_status':'UNKNOWN — API AUTH_REQUIRED','recommend_request':'VERIFY_CURRENT_STATUS_FIRST','request_priority':'P'+str(priority),'manual_request_time':'','google_interface_result':'','notes':('Owner reported NOT_INDEXED with passing live test on2026-11-04; timeunknown. 'if history else'')+'In verified property: URL inspection -> check current index state. If indexed, skip. If not indexed, Request indexing once; record actual time/result. No request submitted by automation.'})
    with(out/'manual-indexing-requests.csv').open('w',newline='')as f:
        w=csv.DictWriter(f,fieldnames=list(checklist[0]));w.writeheader();w.writerows(checklist)
    dump(out/'baseline-freeze.json',{'frozen_at':now(),'scope':'Pre-submission baseline and owner history; never overwrite or backfill later API checks','sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in out.iterdir()if p.is_file()and p.name!='baseline-freeze.json'}})
    print(json.dumps({'baseline_saved':True,'important_urls':len(monitored),'all_discovered_HTML_files':len(candidates),'actual_HTTP_requests':request_count,'API_inspections_performed':0,'index_state':'AUTH_REQUIRED','manual_owner_observations_separate':2}))

if __name__=='__main__':main()
