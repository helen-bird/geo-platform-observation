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

def full_bing_batch(snapshot):
    """A persisted GitHub query success is distinct from index membership."""
    rows=snapshot.get('results',[]);planned=snapshot.get('planned_urls',[])
    urls=[r.get('url')for r in rows]
    return (snapshot.get('engine')=='bing'and snapshot.get('execution_environment')=='github_actions'
            and bool(snapshot.get('snapshot_id'))and snapshot.get('run_complete')is True
            and snapshot.get('url_queries_complete')is True and bool(planned)
            and len(planned)==len(set(planned))and len(urls)==len(set(urls))
            and set(urls)==set(planned)and snapshot.get('queries_succeeded')==len(planned)
            and snapshot.get('site_access_observation',{}).get('query_status')=='SUCCESS'
            and snapshot.get('sitemap_observation',{}).get('query_success')is True
            and all(r.get('query_success')is True and r.get('query_status')=='SUCCESS'
                    and bool(r.get('api_attempts'))for r in rows))

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

def persist_report(folder, text, summary):
    """Archive every rendered report, including older manual progress notes.

    A preserved pre-existing report has an observation/preservation time only;
    its original generation time is unknown, rather than backfilled.
    """
    folder=Path(folder);history=folder/'report-snapshots';history.mkdir(parents=True,exist_ok=True)
    def immutable(path, content):
        try:
            with path.open('x')as stream:stream.write(content)
        except FileExistsError:
            if path.read_text()!=content:raise ValueError('REPORT_SNAPSHOT_ALREADY_EXISTS')
    current=folder/'report.zh-CN.md'
    if current.exists():
        previous=current.read_text();digest=hashlib.sha256(previous.encode()).hexdigest()
        if previous!=text and not any(history.glob('*-'+digest+'.zh-CN.md')):
            preserved_at=now();stamp=preserved_at.replace(':','').replace('+','_')
            prefix='preserved-at-'+stamp+'-'+digest
            immutable(history/(prefix+'.zh-CN.md'),previous)
            immutable(history/(prefix+'.json'),json.dumps({'source':'existing_report_before_replacement','preserved_at':preserved_at,'original_generation_time':None,'sha256':digest},sort_keys=True,indent=2)+'\n')
    digest=hashlib.sha256(text.encode()).hexdigest();stamp=summary['checked_at'].replace(':','').replace('+','_')
    prefix=stamp+'-'+digest
    immutable(history/(prefix+'.zh-CN.md'),text)
    immutable(history/(prefix+'.json'),json.dumps({'source':'generated_monitor_report','checked_at':summary['checked_at'],'sha256':digest,'summary':summary},sort_keys=True,indent=2)+'\n')
    current.write_text(text)
    return str(Path('report-snapshots')/(prefix+'.zh-CN.md'))

def report(output, inventory, bing, openai, receipt):
    google_snapshot=google.read_json(output/'latest-successful-index-status.json',{})
    google_sitemap=google.read_json(output/'sitemap-status.json',{})
    google_count=len(google_snapshot['results'])if isinstance(google_snapshot.get('results'),list)else sum(v for v in google_snapshot.get('counts',{}).values()if type(v)is int and v>=0)
    rows=openai.get('results',[]);allowed=sum(r.get('configuration_status')=='ALLOWED'for r in rows);blocked=sum(r.get('configuration_status')=='BLOCKED'for r in rows);sim=sum(r.get('ua_simulation',{}).get('status')=='FETCH_SUCCEEDED'for r in rows)
    summary={'checked_at':now(),'google':{'checked_at':google_snapshot.get('checked_at'),'counts':google_snapshot.get('counts',{}),'source':'official_url_inspection_api','scope':'recorded important canonical pages','recorded_url_count':google_count},'bing':{'checked_at':bing['checked_at'],'counts':bing.get('counts',{'UNKNOWN':len(bing['results'])}),'query_status':bing.get('run_status'),'scope':'all reviewed indexing_desired canonicals','membership':'UNKNOWN unless explicit independent official evidence','authentication_method':bing.get('configured_authentication_method',bing.get('authentication',{}).get('method')),'credential_readonly_scoped':bing.get('authentication',{}).get('readonly_scoped'),'program_write_enabled':False,'execution_environment':bing.get('execution_environment','UNKNOWN'),'weekly_automation_evidence':'CURRENT_SNAPSHOT_IS_GITHUB_ACTIONS'if bing.get('execution_environment')=='github_actions'else'NOT_ESTABLISHED_BY_THIS_SNAPSHOT'},'openai_search':{'checked_at':openai['checked_at'],'configuration_allowed':allowed,'configuration_blocked':blocked,'configuration_unknown':len(rows)-allowed-blocked,'ua_simulation_succeeded':sim,'real_crawl':'UNKNOWN','openai_index':'UNKNOWN'},'indexnow':{k:v for k,v in receipt.items()if k!='state'},'ai_answer_experiments_run':False}
    summary['bing'].update({'full_batch_passed':full_bing_batch(bing),'run_complete':bing.get('run_complete'),'planned_url_count':len(bing['results']),'queries_succeeded':bing.get('queries_succeeded'),'urls_not_queried_after_block':bing.get('urls_not_queried_after_block'),'request_interval_seconds':bing.get('request_interval_seconds'),'batch_stop':{key:bing.get('batch_stop',{}).get(key)for key in ('operation','query_status','error','checked_at')}if bing.get('batch_stop')else None})
    summary['google_sitemap']={'checked_at':google_sitemap.get('checked_at'),'query_status':google_sitemap.get('google_status','UNKNOWN'),'isPending':google_sitemap.get('google_response',{}).get('isPending'),'lastDownloaded':google_sitemap.get('google_response',{}).get('lastDownloaded')}
    summary['bing_sitemap']={k:bing.get('sitemap_observation',{}).get(k)for k in('checked_at','query_status','registered','processing_status','submitted_time','last_crawl_time')}
    folder=output/'discoverability'
    bing_setup='Bing \u53ea\u8bfb API \u67e5\u8be2\u5df2\u5b8c\u6210\uff1b\u7d22\u5f15\u6210\u5458\u5224\u5b9a\u4ecd\u9700\u4fdd\u7559\u4e0a\u8ff0\u9650\u5236\u3002'if bing.get('run_complete')else'Bing API \u67e5\u8be2\u672a\u5168\u90e8\u5b8c\u6210\uff1b\u8bf7\u68c0\u67e5\u6240\u9009\u6388\u6743\u65b9\u5f0f\u548c\u5b9e\u9645\u9519\u8bef\u3002API Key \u4e3a\u8d26\u53f7\u7ea7\u51ed\u8bc1\uff0c\u53ea\u6709\u7a0b\u5e8f\u8c03\u7528\u88ab\u9650\u5236\u4e3a GEO \u53ea\u8bfb\uff1b\u4e0d\u80fd\u5c06\u5176\u79f0\u4e3a\u53ea\u8bfb\u6388\u6743\u3002'
    text=f'''# GEO Lab #05 \u2014 \u591a\u5f15\u64ce\u53d1\u73b0\u8def\u5f84\u76d1\u6d4b\n\n\u66f4\u65b0\u65f6\u95f4\uff1a{summary['checked_at']}\uff08UTC\uff09\u3002\u539f Google \u57fa\u7ebf\u4e0e\u5386\u53f2\u5747\u4fdd\u7559\u3002\n\n| \u7ef4\u5ea6 | \u8303\u56f4 | \u5b9e\u9645\u89c2\u5bdf | \u4e0d\u80fd\u636e\u6b64\u5224\u65ad |\n| --- | --- | --- | --- |\n| Google Indexing | {google_count} \u4e2a\u5df2\u8bb0\u5f55\u7684\u91cd\u8981\u89c4\u8303\u9875\u9762 | {json.dumps(summary['google']['counts'])}\uff1b\u5feb\u7167 {summary['google']['checked_at']} | ChatGPT \u6216 Bing \u662f\u5426\u6536\u5f55 |\n| Bing Indexing | {len(bing['results'])} \u4e2a\u5e0c\u671b\u88ab\u7d22\u5f15\u7684\u89c4\u8303\u9875\u9762 | \u67e5\u8be2\u72b6\u6001 {bing.get('run_status')}\uff1b\u7d22\u5f15\u6210\u5458\u72b6\u6001 UNKNOWN | GetUrlInfo \u7684 IsPage\u3001\u6293\u53d6\u65f6\u95f4\u3001HTTP 200 \u5747\u4e0d\u8db3\u4ee5\u8bc1\u660e\u5df2\u6536\u5f55 |\n| OpenAI Search Crawl Eligibility | {len(rows)} \u4e2a\u89c4\u8303\u9875\u9762 | \u914d\u7f6e\u5141\u8bb8 {allowed}\u3001\u963b\u6b62 {blocked}\u3001\u672a\u77e5 {len(rows)-allowed-blocked}\uff1b\u58f0\u660e UA \u6a21\u62df\u6210\u529f {sim} | \u771f\u5b9e OpenAI \u722c\u866b\u8bbf\u95ee\u3001OpenAI \u7d22\u5f15\u4e0e ChatGPT \u63a8\u8350\u5747 UNKNOWN |\n\n## \u5df2\u81ea\u52a8\u6267\u884c\n\n- Google \u539f\u6709\u6d41\u7a0b\u4fdd\u7559\uff1bBing \u4e0e OpenAI \u4f7f\u7528\u72ec\u7acb\u5feb\u7167\u3001\u5386\u53f2 CSV\u3001\u6210\u529f\u6307\u9488\u548c\u9519\u8bef\u8bb0\u5f55\u3002\n- \u540c\u4e00 Sitemap URL \u5206\u5f15\u64ce\u4fdd\u5b58\u6ce8\u518c\u3001\u5904\u7406\u548c\u8bfb\u53d6\u8bc1\u636e\u3002Google \u539f\u59cb API \u63d0\u4ea4\u4e0e\u540e\u7eed\u4eba\u5de5\u7ea0\u6b63\u6027\u91cd\u63d0\u5206\u522b\u7559\u5b58\uff1b\u4f8b\u884c\u76d1\u6d4b\u4e0d\u91cd\u590d\u63d0\u4ea4\u3002\n- IndexNow \u4f7f\u7528\u5f53\u524d\u9879\u76ee\u76ee\u5f55\u4e0b\u7684\u516c\u5f00\u9a8c\u8bc1 key \u6587\u4ef6\uff0c\u5e76\u5728\u901a\u77e5\u4e2d\u660e\u786e keyLocation\u3002\u521d\u59cb\u5316\u4ec5\u5efa\u7acb\u5185\u5bb9\u57fa\u7ebf\uff1b\u4e4b\u540e\u53ea\u901a\u77e5\u7ecf\u8fc7\u5b9e\u9645\u90e8\u7f72\u6838\u9a8c\u7684\u65b0\u589e\u3001\u5b9e\u8d28\u5185\u5bb9\u66f4\u65b0\u6216\u5220\u9664\u3002\n- IndexNow \u672c\u8f6e\u72b6\u6001\uff1a{receipt.get('status','UNKNOWN')}\uff0c\u5b9e\u9645 POST\uff1a{receipt.get('post_performed',False)}\uff0c\u901a\u77e5 URL \u6570\uff1a{receipt.get('url_count',0)}\u3002\u63a5\u53d7\u901a\u77e5\u4e0d\u4ee3\u8868\u5df2\u6293\u53d6\u6216\u6536\u5f55\u3002\n- \u6bcf\u5468\u4e00\u5317\u4eac\u65f6\u95f4 10:17 \u5728\u539f\u79c1\u6709\u4ed3\u5e93\u8fd0\u884c\uff0c\u652f\u6301\u624b\u52a8\u89e6\u53d1\uff1bGitHub \u53ef\u80fd\u5ef6\u8fdf\u3002\n- \u4e3b\u673a\u6839\u7ea7 robots\uff1a{openai.get('root_robots',{}).get('http_status','UNKNOWN')}\uff1b\u9879\u76ee\u8def\u5f84\u4e0b robots.txt \u4e0d\u4f5c\u4e3a\u6709\u6548\u6839\u7ea7\u89c4\u5219\u3002\n\n## Sitemap \u72ec\u7acb\u72b6\u6001\n\n- \u5171\u540c URL\uff1ahttps://helen-bird.github.io/geo-platform-observation/sitemap.xml\n- Google\uff1a\u67e5\u8be2\u72b6\u6001 {summary['google_sitemap']['query_status']}\uff0cisPending={summary['google_sitemap']['isPending']}\uff0clastDownloaded={summary['google_sitemap']['lastDownloaded']}\u3002\u539f\u63d0\u4ea4\u63a5\u53d7\u8bb0\u5f55\u4fdd\u6301\u4e0d\u53d8\u3002\n- Bing\uff1a\u67e5\u8be2\u72b6\u6001 {summary['bing_sitemap']['query_status']}\uff0cregistered={summary['bing_sitemap']['registered']}\uff0c\u5904\u7406\u72b6\u6001 {summary['bing_sitemap']['processing_status']}\u3002API \u67e5\u8be2\u4e0e\u4eba\u5de5\u5bfc\u5165\u8bc1\u636e\u5206\u5f00\u8bb0\u5f55\uff1b\u7f3a\u5c11 API \u6388\u6743\u4e0d\u80fd\u636e\u6b64\u63a8\u65ad Sitemap \u672a\u6ce8\u518c\u3002\n- IndexNow \u8fdc\u7aef\u6240\u6709\u6743\u9a8c\u8bc1\uff1a{receipt.get('remote_engine_key_validation','UNKNOWN')}\u3002\u516c\u5f00 key \u6587\u4ef6\u53ef\u8bfb\u4e0d\u7b49\u4e8e\u670d\u52a1\u5668\u5df2\u5b8c\u6210\u9a8c\u8bc1\uff1b\u771f\u5b9e\u901a\u77e5\u7684\u63a5\u6536\u4e0e\u9a8c\u8bc1\u8fdb\u5ea6\u4ee5\u72ec\u7acb\u56de\u6267\u4e3a\u51c6\uff0cHTTP 202 \u4ecd\u8868\u793a key \u9a8c\u8bc1\u7b49\u5f85\u3002\n\n## \u5269\u4f59\u6388\u6743\u4e0e\u8bc1\u636e\u7f3a\u53e3\n\n- Bing \u5b9e\u9645\u67e5\u8be2\u72b6\u6001\u4e3a {bing.get('run_status')}\u3002\u7f3a\u6388\u6743\u65f6\uff0c\u7d22\u5f15\u72b6\u6001\u4e3a UNKNOWN\uff0c\u4e0d\u63a8\u65ad\u672a\u6536\u5f55\u3002{bing_setup}\n- Bing GetUrlInfo \u5f53\u524d\u5b98\u65b9\u5b57\u6bb5\u6ca1\u6709\u660e\u786e\u7d22\u5f15\u6210\u5458\u5224\u5b9a\uff1b\u5b8c\u6574\u63a5\u53e3\u67e5\u8be2\u6210\u529f\u540e\u4ecd\u9700\u4fdd\u7559 UNKNOWN\uff0c\u5fc5\u8981\u65f6\u901a\u8fc7 Bing \u5b98\u65b9 URL Inspection \u7684 Index \u5361\u53e6\u5b58\u4eba\u5de5\u89c2\u5bdf\u3002Live URL \u4e0d\u80fd\u66ff\u4ee3\u7d22\u5f15\u7248\u672c\u3002\n- GitHub Pages \u672a\u63d0\u4f9b\u672c\u9879\u76ee\u53ef\u53d6\u5f97\u7684\u9010\u8bf7\u6c42\u53ef\u4fe1\u722c\u866b\u65e5\u5fd7\uff1b\u771f\u5b9e OAI-SearchBot \u6293\u53d6\u72b6\u6001\u548c\u65f6\u95f4 UNKNOWN\u3002\u6a21\u62df UA \u8bf7\u6c42\u6765\u81ea\u76d1\u6d4b\u73af\u5883\uff0c\u4e0d\u662f OpenAI \u5b98\u65b9 IP\u3002\n- \u672a\u8fd0\u884c ChatGPT/Grok \u56de\u7b54\u5b9e\u9a8c\u3002Google/Bing \u6536\u5f55\u53d8\u5316\u4e0d\u80fd\u89e3\u91ca\u4e3a ChatGPT \u5df2\u6536\u5f55\u6216\u63a8\u8350\u63d0\u9ad8\u3002\n\n## \u65b9\u6cd5\u4e0e\u53d8\u66f4\u8bb0\u5f55\n\nGoogle \u51bb\u7ed3\u57fa\u7ebf\u4e0d\u56de\u586b\uff1b\u6bcf\u9879\u65b0\u89c2\u5bdf\u3001Sitemap \u6ce8\u518c\u3001IndexNow \u521d\u59cb\u5316/\u901a\u77e5\u548c\u914d\u7f6e\u90e8\u7f72\u5206\u522b\u8bb0\u5f55\u65f6\u95f4\u3002\u539f\u59cb\u51bb\u7ed3\u57fa\u7ebf\u8986\u76d6 10 \u4e2a\u91cd\u8981\u9875\u9762\uff1b\u65b0\u589e\u9875\u9762\u6309\u5bf9\u5e94\u6e05\u5355\u53ca\u771f\u5b9e\u68c0\u67e5\u65f6\u95f4\u5355\u5217\uff0c\u4e0d\u56de\u586b\u65e7\u57fa\u7ebf\u3002Bing/OpenAI/IndexNow \u7684\u5f53\u524d\u8303\u56f4\u4ee5\u8be5\u6b21\u5b9e\u9645\u4f7f\u7528\u7684\u516c\u5f00\u6e05\u5355 indexing_desired \u4e3a\u51c6\uff1bnoindex \u8bf4\u660e\u9875\u3001\u9a8c\u8bc1\u53ca\u9519\u8bef\u6587\u4ef6\u6392\u9664\u3002\u539f\u59cb\u54cd\u5e94\u4e0e\u72b6\u6001\u4ec5\u5728\u79c1\u6709\u4ed3\u5e93\u6301\u4e45\u4fdd\u5b58\uff1b\u7ecf\u8fc7\u5ba1\u67e5\u7684\u4ee3\u7801\u4e0e\u516c\u5f00\u9a8c\u8bc1\u6587\u4ef6\u4f4d\u4e8e\u516c\u5f00\u4ed3\u5e93\u3002\n'''
    auth_note='Bing API \u51ed\u8bc1\u65b9\u5f0f\uff1a{method}\uff1b\u51ed\u8bc1\u672c\u8eab\u53ea\u8bfb\u8303\u56f4\uff1a{scoped}\uff1b\u7a0b\u5e8f\u5199\u5165\u6743\u9650\uff1a\u5173\u95ed\u3002API Key \u662f\u8d26\u53f7\u7ea7\u51ed\u8bc1\uff0c\u7a0b\u5e8f\u53ea\u8bfb\u53d6 GEO\uff0c\u5e76\u4e0d\u7f29\u5c0f\u51ed\u8bc1\u672c\u8eab\u7684\u6743\u9650\u3002'
    # Keep source ASCII for publication; rendered operational report is Chinese.
    auth_note=auth_note.format(method=summary['bing']['authentication_method'],scoped=summary['bing']['credential_readonly_scoped'])
    text+='\nBing \u672c\u6b21\u89c2\u5bdf\u7684\u6267\u884c\u73af\u5883\uff1a'+str(summary['bing']['execution_environment'])+'\n'
    if summary['bing']['execution_environment']=='owner_macOS_oneoff':
        text+='\n> \u672c\u673a\u4e00\u6b21\u6027\u57fa\u7ebf\u4e0d\u4ee3\u8868 GitHub \u6bcf\u5468\u76d1\u6d4b\u5df2\u6210\u529f\uff1b\u6b64\u524d GitHub \u8fd0\u884c\u7684\u90e8\u5206\u5931\u8d25\u8bb0\u5f55\u7ee7\u7eed\u5355\u72ec\u4fdd\u7559\uff0c\u4e0d\u80fd\u88ab\u672c\u673a\u6210\u529f\u7ed3\u679c\u8986\u76d6\u6216\u6539\u5199\u3002\n'
    elif summary['bing']['execution_environment']=='UNKNOWN':
        text+='\n> \u6b64\u5feb\u7167\u6ca1\u6709\u8bb0\u5f55\u6267\u884c\u73af\u5883\uff0c\u4fdd\u6301 UNKNOWN\uff1b\u4e0d\u6309\u5f53\u524d\u751f\u6210\u62a5\u544a\u7684\u73af\u5883\u56de\u586b\uff0c\u4e5f\u4e0d\u80fd\u636e\u6b64\u786e\u8ba4 GitHub \u6bcf\u5468\u76d1\u6d4b\u6210\u529f\u3002\n'
    text+='\n'+auth_note+'\n'
    text+='\nBing \u5b9e\u9645\u6210\u529f\u67e5\u8be2 URL \u6570\uff1a{success} / {planned}\uff1b\u56e0\u5148\u524d\u9650\u6d41\u6216\u6388\u6743\u963b\u65ad\u800c\u672a\u67e5\u8be2\uff1a{skipped}\uff1b\u5b9e\u9645\u8bf7\u6c42\u95f4\u9694\uff1a{pace} \u79d2\u3002\u672a\u67e5\u8be2\u4f4d\u7f6e\u4ecd\u4fdd\u7559 UNKNOWN \u548c\u96f6\u6b21\u8bf7\u6c42\uff0c\u4e0d\u5192\u5145 API \u67e5\u8be2\u7ed3\u679c\u3002\n'.format(success=summary['bing']['queries_succeeded'],planned=summary['bing']['planned_url_count'],skipped=summary['bing']['urls_not_queried_after_block'],pace=summary['bing']['request_interval_seconds'])
    if summary['bing']['batch_stop']:
        text+='\n> Bing \u5df2\u51fa\u73b0\u9650\u6d41\u3001\u6388\u6743\uff0f\u6743\u9650\u963b\u65ad\uff0c\u6216\u9700\u8981\u5ef6\u540e\u91cd\u8bd5\u7684\u670d\u52a1\u7aef\u7b49\u5f85\u8981\u6c42\uff1b\u5f53\u524d\u6279\u6b21\u5df2\u505c\u6b62\uff0c\u4e0d\u7ee7\u7eed\u9010 URL \u8bf7\u6c42\u3001\u4e0d\u81ea\u52a8\u6362\u51ed\u8bc1\u6216\u73af\u5883\u3002\u9996\u6b21\u963b\u65ad\u8bc1\u636e\u5355\u72ec\u4fdd\u5b58\uff1b\u82e5\u6ca1\u6709 Retry-After\uff0c\u4e0d\u63a8\u65ad\u6062\u590d\u65f6\u95f4\u3002\n'
    if receipt.get('run_scope')=='indexnow_only_notification':
        summary['monitor_scope']='indexnow_only_notification';summary['other_dimensions_rechecked']=False
        for dimension in ('google','bing','openai_search'):summary[dimension]['carried_forward_from_previous_observation']=True
        text+='\n> \u672c\u6b21\u4ec5\u68c0\u67e5\u771f\u5b9e\u5185\u5bb9\u53d8\u66f4\u5e76\u901a\u77e5 IndexNow\u3002Google\u3001Bing \u548c OpenAI \u6cbf\u7528\u65e2\u6709\u89c2\u5bdf\u53ca\u539f\u68c0\u67e5\u65f6\u95f4\uff0c\u6ca1\u6709\u67e5\u8be2\u5b83\u4eec\uff1b\u901a\u77e5\u63a5\u6536\u4e0d\u7b49\u4e8e\u6293\u53d6\u6216\u6536\u5f55\u3002\n'
    elif bing.get('run_scope')=='bing_only_recheck':
        summary['monitor_scope']='bing_only_recheck';summary['other_dimensions_rechecked']=False
        summary['indexnow']['carried_forward_from_previous_observation']=True
        text+='\n> \u672c\u6b21\u4ec5\u8865\u67e5 Bing\u3002\u4e0a\u65b9 Google\u3001OpenAI \u548c IndexNow \u4e3a\u6cbf\u7528\u7684\u5386\u53f2\u89c2\u5bdf\uff0c\u5404\u81ea\u4fdd\u7559\u539f\u68c0\u67e5\u65f6\u95f4\uff1b\u672c\u6b21\u6ca1\u6709\u5bf9\u5b83\u4eec\u6267\u884c\u65b0\u7684\u5b9e\u65f6\u68c0\u67e5\u6216\u63d0\u4ea4\u3002\n'
    summary['report_snapshot']=persist_report(folder,text,summary)
    google.write_json(folder/'latest-summary.json',summary)
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

def bing_monitor_probe(entries, *, request_interval=5):
    """Select one approved credential source; never silently fall back.

    API keys are account-wide, not readonly-scoped. This runner always creates
    a no-write client with fixed-property read methods; response filtering in
    inspect_urls omits unrelated sites returned by GetUserSites.
    """
    mode=os.environ.get('BING_AUTH_METHOD','oauth')
    error=None;client=BingClient(allow_write=False,request_interval=request_interval)
    try:
        if mode=='api_key':
            key=os.environ.get('BING_API_KEY')
            if not isinstance(key,str) or not key.strip():raise BingAuthError('AUTH_REQUIRED')
            if len(key)>4096 or key!=key.strip() or any(ord(c)<32 or ord(c)==127 for c in key):
                raise BingAuthError('INVALID_API_KEY_SECRET')
            if os.environ.get('GITHUB_ACTIONS')=='true':print('::add-mask::'+key.replace('%','%25'))
            client=BingClient(api_key=key,allow_write=False,request_interval=request_interval)
        elif mode=='oauth':
            access=refresh_bing_oauth()
            if access and os.environ.get('GITHUB_ACTIONS')=='true':print('::add-mask::'+access)
            client=BingClient(access_token=access,allow_write=False,request_interval=request_interval)
        else:raise BingAuthError('UNSUPPORTED_BING_AUTH_METHOD')
    except BingAuthError as exc:error={'category':exc.code,'http_status':exc.status}
    snapshot=inspect_urls(entries,client=client)
    snapshot['planned_urls']=[entry['url']for entry in entries]
    snapshot['github_run_id']=os.environ.get('GITHUB_RUN_ID')if os.environ.get('GITHUB_ACTIONS')=='true'else None
    snapshot['github_run_attempt']=os.environ.get('GITHUB_RUN_ATTEMPT')if os.environ.get('GITHUB_ACTIONS')=='true'else None
    snapshot['execution_environment']='github_actions'if os.environ.get('GITHUB_ACTIONS')=='true'else'local_process'
    snapshot['configured_authentication_method']=mode if mode in {'oauth','api_key'} else 'INVALID'
    snapshot['program_access']={'property':PROPERTY,'allowed_api_operations':['GetUserSites','GetUrlInfo','GetFeeds'],'write_enabled':False,'unrelated_sites_persisted':False}
    if error:snapshot['authorization_error']=error
    return snapshot

def execute_bing_only(output, inventory, *, bing_probe, notify=None):
    """Read Bing only; carry other engines' prior observations without probing."""
    entries=reviewed_urls(inventory);folder=output/'bing'
    previous=google.read_json(folder/'latest-successful.json',{})
    try:value=bing_probe()
    except Exception as exc:value=safe_failure('bing',entries,getattr(exc,'code','UNEXPECTED_PROBE_FAILURE'))
    value['run_scope']='bing_only_recheck';complete=value.get('run_complete')is True
    value=persist_snapshot(folder,value,complete=complete)
    events=change_events(value,previous);errors=[]if complete else['bing']
    if notify:
        try:notify(folder,events,entries,value)
        except Exception:
            errors.append('bing-notification')
            google.write_json(output/'discoverability'/'operator-failures'/(snapshot_id({'checked_at':now(),'error':'BING_NOTIFICATION_FAILURE'})+'.json'),{'checked_at':now(),'error':'BING_NOTIFICATION_FAILURE','raw_error_omitted':True})
    openai=google.read_json(output/'openai-search'/'latest.json',{'checked_at':None,'results':[]})
    receipt=google.read_json(output/'indexnow'/'latest-receipt.json',{'status':'UNKNOWN','post_performed':False,'url_count':0})
    summary=report(output,inventory,value,openai,receipt)
    result={'checked_at':now(),'scope':'bing_only_recheck','snapshot_id':value['snapshot_id'],
            'planned_url_count':len(entries),'full_batch_passed':full_bing_batch(value),
            'errors':errors,'other_dimensions_rechecked':False,'indexing_requested':False}
    google.write_json(folder/'recheck-receipts'/(value['snapshot_id']+'.json'),result)
    return summary,errors

def bing_completion_event(snapshot):
    if not full_bing_batch(snapshot):raise ValueError('COMPLETE_BING_EVIDENCE_REQUIRED')
    kind='BING_FIRST_COMPLETE_BATCH'
    return {'engine':'bing','type':kind,'url':PROPERTY,'before_status':'UNKNOWN',
            'status':'MONITOR_COMPLETE','checked_at':snapshot['checked_at'],
            'fingerprint':hashlib.sha256(json.dumps(['bing',kind,PROPERTY],separators=(',',':')).encode()).hexdigest()}

def notify_bing_completion(output, repository, token, *, event=None,
                           client=google.github_json, runner=subprocess.run,
                           deliver=google.deliver_alerts):
    """Notify only after official run success and a committed matching snapshot."""
    if repository!=google.PRIVATE_REPOSITORY or not token:raise ValueError('APPROVED_PRIVATE_REPOSITORY_REQUIRED')
    if event is None:event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    trigger=event.get('workflow_run',{});run_id=trigger.get('id')
    names={'GEO Lab \u2014 Multi-Engine Discoverability Monitor':'google-index-monitor.yml',
           'GEO Lab \u2014 Bing Index Recheck':'bing-index-recheck.yml'}
    name=trigger.get('name')
    if name not in names or type(run_id)is not int or run_id<=0:
        raise ValueError('UNAPPROVED_COMPLETION_TRIGGER')
    workflow=client('GET','/repos/'+repository+'/actions/workflows/'+names[name],token)
    actual=client('GET','/repos/'+repository+'/actions/runs/'+str(run_id),token)
    if (actual.get('id')!=run_id or type(workflow.get('id'))is not int or workflow.get('name')!=name
        or actual.get('status')!='completed'or actual.get('conclusion')!='success'
        or actual.get('name')!=name or actual.get('workflow_id')!=workflow.get('id')
        or workflow.get('path')!='.github/workflows/'+names[name]
        or actual.get('head_branch')!='main'or actual.get('event')not in{'schedule','workflow_dispatch'}
        or actual.get('head_repository',{}).get('full_name')!=repository
        or actual.get('head_repository',{}).get('private')is not True):
        return {'status':'NO_APPROVED_SUCCESSFUL_RUN','notification_created':False}
    folder=output/'bing';candidates=[]
    for evidence in (folder/'snapshots').glob('*.json'):
        value=google.read_json(evidence,{})
        if (str(value.get('github_run_id'))==str(run_id)
            and str(value.get('github_run_attempt'))==str(actual.get('run_attempt',1))
            and full_bing_batch(value)):candidates.append((evidence,value))
    if not candidates:return {'status':'NO_COMPLETE_BING_BATCH','notification_created':False}
    if len(candidates)!=1:raise ValueError('AMBIGUOUS_BING_COMPLETION_EVIDENCE')
    evidence,value=candidates[0]
    relative=str(evidence.resolve().relative_to(Path.cwd()))
    for command in [['git','ls-files','--error-unmatch','--',relative],['git','diff','--exit-code','HEAD','--',relative]]:
        if runner(command,capture_output=True,text=True).returncode:
            raise ValueError('BING_COMPLETION_EVIDENCE_NOT_COMMITTED')
    completion=bing_completion_event(value)
    pending=google.merge_outbox(folder,[completion])
    selected=[item for item in pending if item.get('type')=='BING_FIRST_COMPLETE_BATCH']
    delivered=deliver(selected,folder,repository,token,{PROPERTY})
    ledger=google.read_json(folder/'notification-ledger.json',{})
    confirmed=ledger.get('events',{}).get(completion['fingerprint'],{}).get('status')=='CONFIRMED'
    return {'status':'COMPLETE_BING_BATCH_NOTIFICATION_RECONCILED'if confirmed else'BING_NOTIFICATION_UNCONFIRMED','snapshot_id':value['snapshot_id'],
            'successful_workflow_run':run_id,'notification_created':bool(delivered),'notification_confirmed':confirmed,'index_membership_claimed':False}

def run_indexnow(output, inventory, config):
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

def execute_indexnow_only(output, inventory, *, indexnow_runner, notify=None):
    """Notify verified real content changes; never probe other search engines."""
    entries=reviewed_urls(inventory);errors=[]
    try:receipt=indexnow_runner()
    except Exception as exc:receipt={'status':'ERROR','error':getattr(exc,'code','UNEXPECTED_INDEXNOW_FAILURE'),'post_performed':None,'url_count':None}
    receipt['run_scope']='indexnow_only_notification'
    failed=(receipt.get('status')not in{'BASELINE_ONLY','NO_CHANGES','ALREADY_ATTEMPTED','RECEIVED','KEY_VALIDATION_PENDING'}or receipt.get('unresolved_delivery_count',0)or receipt.get('pending_count',0)or receipt.get('key_file_verified')is False)
    if failed:
        errors.append('indexnow')
        if notify:
            event={'engine':'indexnow','type':'INDEXNOW_PROBLEM','url':PROPERTY,'before_status':'UNKNOWN','status':'ERROR','checked_at':now()}
            event['fingerprint']=hashlib.sha256(json.dumps(['indexnow',receipt.get('status'),receipt.get('unresolved_delivery_count',0),receipt.get('key_file_verified')],sort_keys=True).encode()).hexdigest()
            try:notify(output/'indexnow',[event],entries,{'run_complete':False})
            except Exception:receipt['notification_error']='DELIVERY_OR_STATE_FAILURE';errors.append('indexnow-notification')
    google.write_json(output/'indexnow/latest-receipt.json',receipt)
    bing=google.read_json(output/'bing/latest.json',safe_failure('bing',entries,'NO_PRIOR_OBSERVATION'))
    openai=google.read_json(output/'openai-search/latest.json',{'checked_at':None,'results':[]})
    summary=report(output,inventory,bing,openai,receipt)
    return summary,errors

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',default='state');scope=parser.add_mutually_exclusive_group();scope.add_argument('--bing-only',action='store_true');scope.add_argument('--indexnow-only',action='store_true');scope.add_argument('--notify-bing-complete',action='store_true');parser.add_argument('--bing-request-interval',type=int,choices=range(5,61),default=5);args=parser.parse_args()
    repository=os.environ.get('GITHUB_REPOSITORY','');token=os.environ.get('GITHUB_TOKEN','')
    google.verify_private_repository(repository,token);_,output=google.private_state_path(args.output,repository)
    if args.notify_bing_complete:
        result=notify_bing_completion(output,repository,token)
        print(json.dumps(result));return 4 if result.get('notification_confirmed')is False else 0
    inputs={}
    try:inventory=json.loads(google.request(google.PUBLIC_INVENTORY)['body']);inputs['inventory_source']=google.PUBLIC_INVENTORY
    except Exception:
        inventory=json.loads(Path('monitoring/google-index/urls.json').read_text());inputs['inventory_source']='CHECKED_OUT_FALLBACK_REMOTE_REFRESH_FAILED'
    google.validate_inventory(inventory);entries=reviewed_urls(inventory)
    def notify(folder,events,entries,value):
        pending=google.merge_outbox(folder,events)
        google.deliver_alerts(pending,folder,repository,token,{r['url']for r in entries})
        google.clear_recovered_incidents(folder,{'run_complete':value.get('run_complete',False),'run_status':'SUCCESS'},{'accessible':True,'processing_error':False}if value.get('sitemap_observation',{}).get('query_success')and not events else {})
    if args.bing_only:
        google.write_json(output/'discoverability'/'inventory.json',{'loaded_at':now(),**inputs,'inventory':inventory})
        summary,errors=execute_bing_only(output,inventory,bing_probe=lambda:bing_monitor_probe(entries,request_interval=args.bing_request_interval),notify=notify)
        print(json.dumps({'bing_only_status':'PARTIAL_FAILURE'if errors else'SUCCESS','incomplete_dimensions':errors,'private_state_saved':True,'other_dimensions_rechecked':False,'full_batch_passed':summary['bing']['full_batch_passed']}))
        return 3 if errors else 0
    try:config=validate_config(json.loads(google.request(CONFIG_URL)['body']));inputs['config_source']=CONFIG_URL
    except Exception:
        config=validate_config(json.loads(Path('monitoring/discoverability/indexnow.json').read_text()));inputs['config_source']='CHECKED_OUT_FALLBACK_REMOTE_REFRESH_FAILED'
    google.write_json(output/'discoverability'/'inventory.json',{'loaded_at':now(),**inputs,'inventory':inventory});google.write_json(output/'indexnow'/'config-used.json',config)
    def bing_probe():return bing_monitor_probe(entries,request_interval=args.bing_request_interval)
    def indexnow_runner():return run_indexnow(output,inventory,config)
    if args.indexnow_only:
        summary,errors=execute_indexnow_only(output,inventory,indexnow_runner=indexnow_runner,notify=notify)
        print(json.dumps({'indexnow_only_status':'PARTIAL_FAILURE'if errors else'SUCCESS','incomplete_dimensions':errors,'private_state_saved':True,'other_dimensions_rechecked':False,'post_performed':summary['indexnow'].get('post_performed',False)}))
        return 3 if errors else 0
    _,errors=execute(output,inventory,config,bing_probe=bing_probe,openai_probe=lambda:probe_openai(inventory),indexnow_runner=indexnow_runner,notify=notify)
    print(json.dumps({'multi_engine_status':'PARTIAL_FAILURE'if errors else'SUCCESS','incomplete_dimensions':errors,'private_state_saved':True,'ai_answer_experiments_run':False}))
    return 3 if errors else 0

if __name__=='__main__':raise SystemExit(main())
