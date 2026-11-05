#!/usr/bin/env python3
"""Private weekly Bing/OpenAI/IndexNow extension; Google state stays independent."""
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import subprocess

import index_monitor_actions as google
from discoverability_openai import PROPERTY, reviewed_urls, probe_openai, get_url
from discoverability_bing import BingClient, BingAuthError, refresh_bing_oauth, inspect_urls
from discoverability_indexnow import observe_content, plan_changes, apply_notifications, validate_config

CONFIG_URL = PROPERTY + 'monitoring/discoverability/indexnow.json'

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()

def snapshot_id(value):
    return value['checked_at'].replace(':','').replace('+','_') + '-' + hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()[:12]

def persist_snapshot(folder, snapshot, *, complete):
    """Every attempt is immutable; failed attempts never replace success pointers."""
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    previous=google.read_json(folder/'comparison.json',{'urls':{}})['urls']
    current={r['url']:r.get('configuration_status',r.get('index_status','UNKNOWN'))for r in snapshot.get('results',[])}
    snapshot={**snapshot,'added_urls':sorted(set(current)-set(previous)),'removed_urls':sorted(set(previous)-set(current))}
    ident=snapshot_id(snapshot);snapshot={**snapshot,'snapshot_id':ident}
    destination=folder/'snapshots'/(ident+'.json')
    if destination.exists(): raise ValueError('SNAPSHOT_ALREADY_EXISTS')
    google.write_json(destination,snapshot);google.write_json(folder/'latest.json',snapshot)
    if not(folder/'baseline.json').exists():google.write_json(folder/'baseline.json',snapshot)
    if complete:google.write_json(folder/'latest-successful.json',snapshot)
    history=folder/'history.csv';old=history.read_text()if history.exists()else''
    fields=['snapshot_id','engine','checked_at','url','index_status','configuration_status','query_status','last_crawl_time','status_changed','error']
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=fields)
    if not old:writer.writeheader()
    for row in snapshot.get('results',[]):
        url=row['url'];status=row.get('configuration_status',row.get('index_status','UNKNOWN'));current[url]=status
        writer.writerow({'snapshot_id':ident,'engine':snapshot.get('engine'),'checked_at':row.get('checked_at',snapshot['checked_at']),'url':url,'index_status':row.get('index_status',row.get('openai_index_status','UNKNOWN')),'configuration_status':row.get('configuration_status',''),'query_status':row.get('query_status',''),'last_crawl_time':row.get('last_crawl_time')or'', 'status_changed':url in previous and previous[url]!=status,'error':json.dumps(row.get('error'))if row.get('error')else''})
    history.write_text(old+stream.getvalue())
    if complete:google.write_json(folder/'comparison.json',{'urls':current,'checked_at':snapshot['checked_at']})
    return snapshot

def safe_failure(engine, entries, category):
    return {'engine':engine,'checked_at':now(),'run_status':'ERROR','run_complete':False,'error':category,'results':[{'url':r['url'],'index_status':'UNKNOWN','configuration_status':'UNKNOWN','query_status':'ERROR','error':category}for r in entries]}

def change_events(current, previous):
    events=[];engine=current['engine'];prior={r['url']:r for r in(previous or{}).get('results',[])}
    if current.get('run_status')=='AUTH_REQUIRED':
        events.append({'engine':engine,'type':'AUTH_REQUIRED','url':PROPERTY,'before_status':'UNKNOWN','status':'AUTH_REQUIRED','checked_at':current['checked_at']})
    for row in current.get('results',[]):
        old=prior.get(row['url']);before=(old or{}).get('configuration_status',(old or{}).get('index_status','UNKNOWN'));after=row.get('configuration_status',row.get('index_status','UNKNOWN'))
        kind='FIRST_INDEXED'if after=='INDEXED'and before!='INDEXED'else'DEINDEXED'if before=='INDEXED'and after=='NOT_INDEXED'else'CRAWL_BLOCK'if after=='BLOCKED'and before!='BLOCKED'else'VISIBILITY_CHANGE'if old and before!=after else None
        if kind:events.append({'engine':engine,'type':kind,'url':row['url'],'before_status':before,'status':after,'checked_at':row.get('checked_at',current['checked_at'])})
    feed=current.get('sitemap_observation',{})
    if feed.get('query_success')and str(feed.get('processing_status','')).lower()in{'failed','error','invalid'}:
        events.append({'engine':engine,'type':'SITEMAP_PROBLEM','url':PROPERTY+'sitemap.xml','before_status':'UNKNOWN','status':'ERROR','checked_at':current['checked_at']})
    for event in events:event['fingerprint']=hashlib.sha256(json.dumps([engine,event['type'],event['url'],event['before_status'],event['status'],(previous or{}).get('snapshot_id')],separators=(',',':')).encode()).hexdigest()
    return events

def report(output, inventory, bing, openai, receipt):
    google_snapshot=google.read_json(output/'latest-successful-index-status.json',{})
    rows=openai.get('results',[]);allowed=sum(r.get('configuration_status')=='ALLOWED'for r in rows);blocked=sum(r.get('configuration_status')=='BLOCKED'for r in rows);sim=sum(r.get('ua_simulation',{}).get('status')=='FETCH_SUCCEEDED'for r in rows)
    summary={'checked_at':now(),'google':{'checked_at':google_snapshot.get('checked_at'),'counts':google_snapshot.get('counts',{}),'source':'official_url_inspection_api','scope':'existing ten important pages'},'bing':{'checked_at':bing['checked_at'],'counts':bing.get('counts',{'UNKNOWN':len(bing['results'])}),'query_status':bing.get('run_status'),'scope':'all reviewed indexing_desired canonicals','membership':'UNKNOWN unless explicit independent official evidence'},'openai_search':{'checked_at':openai['checked_at'],'configuration_allowed':allowed,'configuration_blocked':blocked,'configuration_unknown':len(rows)-allowed-blocked,'ua_simulation_succeeded':sim,'real_crawl':'UNKNOWN','openai_index':'UNKNOWN'},'indexnow':{k:v for k,v in receipt.items()if k!='state'},'ai_answer_experiments_run':False}
    folder=output/'discoverability';google.write_json(folder/'latest-summary.json',summary)
    bing_setup='Bing \u53ea\u8bfb API \u67e5\u8be2\u5df2\u5b8c\u6210\uff1b\u7d22\u5f15\u6210\u5458\u5224\u5b9a\u4ecd\u9700\u4fdd\u7559\u4e0a\u8ff0\u9650\u5236\u3002'if bing.get('run_complete')else'\u9700\u5728 Bing \u5b8c\u6210\u7f51\u7ad9\u9a8c\u8bc1\u53ca\u5b98\u65b9\u53ea\u8bfb API \u6388\u6743\uff1b\u4f18\u5148\u4f7f\u7528\u5df2\u6709 GSC \u5c5e\u6027\u5bfc\u5165\uff0c\u5e76\u68c0\u67e5 Sitemap \u662f\u5426\u968f\u5bfc\u5165\u6ce8\u518c\u3002'
    text=f'''# GEO Lab #05 \u2014 \u591a\u5f15\u64ce\u53d1\u73b0\u8def\u5f84\u76d1\u6d4b\n\n\u66f4\u65b0\u65f6\u95f4\uff1a{summary['checked_at']}\uff08UTC\uff09\u3002\u539f Google \u57fa\u7ebf\u4e0e\u5386\u53f2\u5747\u4fdd\u7559\u3002\n\n| \u7ef4\u5ea6 | \u8303\u56f4 | \u5b9e\u9645\u89c2\u5bdf | \u4e0d\u80fd\u636e\u6b64\u5224\u65ad |\n| --- | --- | --- | --- |\n| Google Indexing | \u539f\u6709 10 \u4e2a\u91cd\u8981\u89c4\u8303\u9875\u9762 | {json.dumps(summary['google']['counts'])}\uff1b\u5feb\u7167 {summary['google']['checked_at']} | ChatGPT \u6216 Bing \u662f\u5426\u6536\u5f55 |\n| Bing Indexing | {len(bing['results'])} \u4e2a\u5e0c\u671b\u88ab\u7d22\u5f15\u7684\u89c4\u8303\u9875\u9762 | \u67e5\u8be2\u72b6\u6001 {bing.get('run_status')}\uff1b\u7d22\u5f15\u6210\u5458\u72b6\u6001 UNKNOWN | GetUrlInfo \u7684 IsPage\u3001\u6293\u53d6\u65f6\u95f4\u3001HTTP 200 \u5747\u4e0d\u8db3\u4ee5\u8bc1\u660e\u5df2\u6536\u5f55 |\n| OpenAI Search Crawl Eligibility | {len(rows)} \u4e2a\u89c4\u8303\u9875\u9762 | \u914d\u7f6e\u5141\u8bb8 {allowed}\u3001\u963b\u6b62 {blocked}\u3001\u672a\u77e5 {len(rows)-allowed-blocked}\uff1b\u58f0\u660e UA \u6a21\u62df\u6210\u529f {sim} | \u771f\u5b9e OpenAI \u722c\u866b\u8bbf\u95ee\u3001OpenAI \u7d22\u5f15\u4e0e ChatGPT \u63a8\u8350\u5747 UNKNOWN |\n\n## \u5df2\u81ea\u52a8\u6267\u884c\n\n- Google \u539f\u6709\u6d41\u7a0b\u4fdd\u7559\uff1bBing \u4e0e OpenAI \u4f7f\u7528\u72ec\u7acb\u5feb\u7167\u3001\u5386\u53f2 CSV\u3001\u6210\u529f\u6307\u9488\u548c\u9519\u8bef\u8bb0\u5f55\u3002\n- \u540c\u4e00 Sitemap URL \u5206\u5f15\u64ce\u4fdd\u5b58\u6ce8\u518c\u3001\u5904\u7406\u548c\u8bfb\u53d6\u8bc1\u636e\u3002Google \u539f\u5148\u4ec5\u4e00\u6b21\u63d0\u4ea4\uff0c\u4e0d\u91cd\u590d\u6267\u884c\u3002\n- IndexNow \u4f7f\u7528\u5f53\u524d\u9879\u76ee\u76ee\u5f55\u4e0b\u7684\u516c\u5f00\u9a8c\u8bc1 key \u6587\u4ef6\uff0c\u5e76\u5728\u901a\u77e5\u4e2d\u660e\u786e keyLocation\u3002\u521d\u59cb\u5316\u4ec5\u5efa\u7acb\u5185\u5bb9\u57fa\u7ebf\uff1b\u4e4b\u540e\u53ea\u901a\u77e5\u7ecf\u8fc7\u5b9e\u9645\u90e8\u7f72\u6838\u9a8c\u7684\u65b0\u589e\u3001\u5b9e\u8d28\u5185\u5bb9\u66f4\u65b0\u6216\u5220\u9664\u3002\n- IndexNow \u672c\u8f6e\u72b6\u6001\uff1a{receipt.get('status','UNKNOWN')}\uff0c\u5b9e\u9645 POST\uff1a{receipt.get('post_performed',False)}\uff0c\u901a\u77e5 URL \u6570\uff1a{receipt.get('url_count',0)}\u3002\u63a5\u53d7\u901a\u77e5\u4e0d\u4ee3\u8868\u5df2\u6293\u53d6\u6216\u6536\u5f55\u3002\n- \u6bcf\u5468\u4e00\u5317\u4eac\u65f6\u95f4 10:17 \u5728\u539f\u79c1\u6709\u4ed3\u5e93\u8fd0\u884c\uff0c\u652f\u6301\u624b\u52a8\u89e6\u53d1\uff1bGitHub \u53ef\u80fd\u5ef6\u8fdf\u3002\n- \u4e3b\u673a\u6839\u7ea7 robots\uff1a{openai.get('root_robots',{}).get('http_status','UNKNOWN')}\uff1b\u9879\u76ee\u8def\u5f84\u4e0b robots.txt \u4e0d\u4f5c\u4e3a\u6709\u6548\u6839\u7ea7\u89c4\u5219\u3002\n\n## \u5269\u4f59\u6388\u6743\u4e0e\u8bc1\u636e\u7f3a\u53e3\n\n- Bing \u5b9e\u9645\u67e5\u8be2\u72b6\u6001\u4e3a {bing.get('run_status')}\u3002\u7f3a\u6388\u6743\u65f6\uff0c\u7d22\u5f15\u72b6\u6001\u4e3a UNKNOWN\uff0c\u4e0d\u63a8\u65ad\u672a\u6536\u5f55\u3002{bing_setup}\n- Bing GetUrlInfo \u5f53\u524d\u5b98\u65b9\u5b57\u6bb5\u6ca1\u6709\u660e\u786e\u7d22\u5f15\u6210\u5458\u5224\u5b9a\uff1b\u5b8c\u6574\u63a5\u53e3\u67e5\u8be2\u6210\u529f\u540e\u4ecd\u9700\u4fdd\u7559 UNKNOWN\uff0c\u5fc5\u8981\u65f6\u901a\u8fc7 Bing \u5b98\u65b9 URL Inspection \u7684 Index \u5361\u53e6\u5b58\u4eba\u5de5\u89c2\u5bdf\u3002Live URL \u4e0d\u80fd\u66ff\u4ee3\u7d22\u5f15\u7248\u672c\u3002\n- GitHub Pages \u672a\u63d0\u4f9b\u672c\u9879\u76ee\u53ef\u53d6\u5f97\u7684\u9010\u8bf7\u6c42\u53ef\u4fe1\u722c\u866b\u65e5\u5fd7\uff1b\u771f\u5b9e OAI-SearchBot \u6293\u53d6\u72b6\u6001\u548c\u65f6\u95f4 UNKNOWN\u3002\u6a21\u62df UA \u8bf7\u6c42\u6765\u81ea\u76d1\u6d4b\u73af\u5883\uff0c\u4e0d\u662f OpenAI \u5b98\u65b9 IP\u3002\n- \u672a\u8fd0\u884c ChatGPT/Grok \u56de\u7b54\u5b9e\u9a8c\u3002Google/Bing \u6536\u5f55\u53d8\u5316\u4e0d\u80fd\u89e3\u91ca\u4e3a ChatGPT \u5df2\u6536\u5f55\u6216\u63a8\u8350\u63d0\u9ad8\u3002\n\n## \u65b9\u6cd5\u4e0e\u53d8\u66f4\u8bb0\u5f55\n\nGoogle \u51bb\u7ed3\u57fa\u7ebf\u4e0d\u56de\u586b\uff1b\u6bcf\u9879\u65b0\u89c2\u5bdf\u3001Sitemap \u6ce8\u518c\u3001IndexNow \u521d\u59cb\u5316/\u901a\u77e5\u548c\u914d\u7f6e\u90e8\u7f72\u5206\u522b\u8bb0\u5f55\u65f6\u95f4\u3002\u539f\u89c4\u8303\u6e05\u5355 10 \u4e2a\u91cd\u8981\u9875\u9762\u4e4b\u5916\u7684 60 \u4e2a\u5355\u6761\u56de\u7b54\u6863\u6848\uff0c\u6309\u516c\u5f00\u6e05\u5355 indexing_desired \u7eb3\u5165 Bing/OpenAI/IndexNow\uff1b\u4e24\u4efd noindex OAuth \u8bf4\u660e\u9875\u4e0e\u9a8c\u8bc1\u3001\u9519\u8bef\u6587\u4ef6\u6392\u9664\u3002\u539f\u59cb\u54cd\u5e94\u4e0e\u72b6\u6001\u4ec5\u5728\u79c1\u6709\u4ed3\u5e93\u6301\u4e45\u4fdd\u5b58\uff1b\u7ecf\u8fc7\u5ba1\u67e5\u7684\u4ee3\u7801\u4e0e\u516c\u5f00\u9a8c\u8bc1\u6587\u4ef6\u4f4d\u4e8e\u516c\u5f00\u4ed3\u5e93\u3002\n'''
    (folder/'report.zh-CN.md').write_text(text)
    return summary

def execute(output, inventory, config, *, bing_probe=None, openai_probe=None, indexnow_runner=None, notify=None):
    entries=reviewed_urls(inventory);results={};run_errors=[]
    for engine,probe in [('bing',bing_probe),('openai-search',openai_probe)]:
        folder=output/engine;value=None
        try:
            previous=google.read_json(folder/'latest-successful.json',{})
            try:value=probe()
            except Exception as exc:value=safe_failure(engine,entries,getattr(exc,'code','UNEXPECTED_PROBE_FAILURE'))
            complete=value.get('run_complete',bool(value.get('results'))and all(r.get('configuration_status')in{'ALLOWED','BLOCKED'}and r.get('public_access',{}).get('error')is None and r.get('ua_simulation',{}).get('error')is None for r in value.get('results',[])))
            if not complete:run_errors.append(engine)
            value['engine']=engine;value['run_complete']=complete
            value.setdefault('run_status','SUCCESS'if complete else'PARTIAL_FAILURE')
            value=persist_snapshot(folder,value,complete=complete);results[engine]=value
            events=change_events(value,previous)
            if notify:notify(folder,events,entries,value)
        except Exception as exc:
            if engine not in run_errors:run_errors.append(engine)
            failure={'engine':engine,'checked_at':now(),'error':getattr(exc,'code','ENGINE_STATE_OR_NOTIFICATION_FAILURE'),'raw_error_omitted':True}
            google.write_json(output/'discoverability'/'operator-failures'/(snapshot_id(failure)+'.json'),failure)
            results.setdefault(engine,value or safe_failure(engine,entries,failure['error']))
    try:receipt=indexnow_runner()
    except Exception as exc:receipt={'status':'ERROR','error':getattr(exc,'code','UNEXPECTED_INDEXNOW_FAILURE'),'post_performed':None,'url_count':None};run_errors.append('indexnow')
    if (receipt.get('status')not in{'BASELINE_ONLY','NO_CHANGES','ALREADY_ATTEMPTED','RECEIVED','KEY_VALIDATION_PENDING'}or receipt.get('unresolved_delivery_count',0)or receipt.get('pending_count',0)or receipt.get('key_file_verified')is False)and'indexnow'not in run_errors:run_errors.append('indexnow')
    if 'indexnow'in run_errors and notify:
        event={'engine':'indexnow','type':'INDEXNOW_PROBLEM','url':PROPERTY,'before_status':'UNKNOWN','status':'ERROR','checked_at':now()}
        event['fingerprint']=hashlib.sha256(json.dumps(['indexnow',receipt.get('status'),receipt.get('unresolved_delivery_count',0),receipt.get('key_file_verified')],sort_keys=True).encode()).hexdigest()
        try:notify(output/'indexnow',[event],entries,{'run_complete':False})
        except Exception:receipt['notification_error']='DELIVERY_OR_STATE_FAILURE'
    elif 'indexnow'not in run_errors:
        ledger_path=output/'indexnow'/'notification-ledger.json'
        ledger=google.read_json(ledger_path,None)
        if ledger:
            ledger['active_incidents']={k:v for k,v in ledger.get('active_incidents',{}).items()if not k.startswith('INDEXNOW_PROBLEM|')}
            google.write_json(ledger_path,ledger)
    google.write_json(output/'indexnow'/'latest-receipt.json',receipt)
    summary=report(output,inventory,results['bing'],results['openai-search'],receipt)
    return summary,run_errors

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',default='state');args=parser.parse_args()
    repository=os.environ.get('GITHUB_REPOSITORY','');token=os.environ.get('GITHUB_TOKEN','')
    google.verify_private_repository(repository,token);_,output=google.private_state_path(args.output,repository)
    inputs={}
    try:inventory=json.loads(google.request(google.PUBLIC_INVENTORY)['body']);inputs['inventory_source']=google.PUBLIC_INVENTORY
    except Exception:
        inventory=json.loads(Path('monitoring/google-index/urls.json').read_text());inputs['inventory_source']='CHECKED_OUT_FALLBACK_REMOTE_REFRESH_FAILED'
    google.validate_inventory(inventory);entries=reviewed_urls(inventory)
    try:config=validate_config(json.loads(google.request(CONFIG_URL)['body']));inputs['config_source']=CONFIG_URL
    except Exception:
        config=validate_config(json.loads(Path('monitoring/discoverability/indexnow.json').read_text()));inputs['config_source']='CHECKED_OUT_FALLBACK_REMOTE_REFRESH_FAILED'
    google.write_json(output/'discoverability'/'inventory.json',{'loaded_at':now(),**inputs,'inventory':inventory});google.write_json(output/'indexnow'/'config-used.json',config)
    def bing_probe():
        error=None;access=None
        try:access=refresh_bing_oauth()
        except BingAuthError as exc:error={'category':exc.code,'http_status':exc.status}
        if access and os.environ.get('GITHUB_ACTIONS')=='true':print('::add-mask::'+access)
        snapshot=inspect_urls(entries,client=BingClient(access_token=access))
        if error:snapshot['authorization_error']=error
        return snapshot
    def indexnow_runner():
        path=output/'indexnow'/'change-ledger.json';old=google.read_json(path,None)
        observations=observe_content(inventory,removed_urls=(old or{}).get('observed',{}));plan=plan_changes(inventory,observations,previous_state=old,config=config)
        google.write_json(output/'indexnow'/'observations'/ (snapshot_id({'checked_at':now(),'observations':observations})+'.json'),observations)
        def durable_ledger(state):
            google.write_json(path,state)
            # Push intent before POST so runner loss cannot erase uncertainty.
            subprocess.run(['git','add','--',str(path)],check=True)
            names=subprocess.check_output(['git','diff','--cached','--name-only'],text=True).splitlines()
            if any(name!='state/indexnow/change-ledger.json'for name in names):raise ValueError('UNRELATED_STAGED_CHANGES')
            if names:
                subprocess.run(['git','-c','user.name=github-actions[bot]','-c','user.email=41898282+github-actions[bot]@users.noreply.github.com','commit','-m','Persist private IndexNow change ledger'],check=True)
                subprocess.run(['git','push','origin','HEAD:main'],check=True)
        receipt=apply_notifications(plan,config=config,persist=durable_ledger)
        ledger=receipt.pop('state',{})
        receipt['unresolved_delivery_count']=sum(d.get('status')in{'UNCERTAIN','REJECTED'}for d in ledger.get('deliveries',{}).values())
        receipt['pending_count']=len(plan.get('pending',[]))
        receipt['pending']=plan.get('pending',[])
        receipt['verified_observation_count']=len(ledger.get('observed',{}))
        key_check=get_url(config['keyLocation'])
        receipt['key_file_verified']=key_check['http_status']==200 and key_check['body'].decode('utf-8','replace').strip()==config['key']
        receipt['key_verification_observed_at']=now()
        receipt['remote_engine_key_validation']='KEY_VALIDATION_PENDING'if receipt.get('status')=='KEY_VALIDATION_PENDING'else'RECEIPT_ACCEPTED'if receipt.get('status')=='RECEIVED'else'UNKNOWN_NO_NOTIFICATION_PERFORMED'
        google.write_json(output/'indexnow'/'receipts'/(snapshot_id({'checked_at':now(),'receipt':receipt})+'.json'),receipt)
        return receipt
    def notify(folder,events,entries,value):
        pending=google.merge_outbox(folder,events);google.deliver_alerts(pending,folder,repository,token,{r['url']for r in entries})
        google.clear_recovered_incidents(folder,{'run_complete':value.get('run_complete',False),'run_status':'SUCCESS'},{'accessible':True,'processing_error':False}if value.get('sitemap_observation',{}).get('query_success')and not events else {})
    _,errors=execute(output,inventory,config,bing_probe=bing_probe,openai_probe=lambda:probe_openai(inventory),indexnow_runner=indexnow_runner,notify=notify)
    print(json.dumps({'multi_engine_status':'PARTIAL_FAILURE'if errors else'SUCCESS','incomplete_dimensions':errors,'private_state_saved':True,'ai_answer_experiments_run':False}))
    return 3 if errors else 0

if __name__=='__main__':raise SystemExit(main())
