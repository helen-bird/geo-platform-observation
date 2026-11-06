#!/usr/bin/env python3
"""Private-repository runner, durable state and deduplicated safe Issue alerts.

Never submit ordinary pages to an indexing endpoint. Google calls here are
readonly: URL Inspection is delegated to index_monitor; Sitemaps uses GET only.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

PROPERTY = 'https://helen-bird.github.io/geo-platform-observation/'
SITEMAP = PROPERTY + 'sitemap.xml'
PRIVATE_REPOSITORY = 'helen-bird/geo-index-monitor'
PUBLIC_INVENTORY = 'https://raw.githubusercontent.com/helen-bird/geo-platform-observation/main/monitoring/google-index/urls.json'
SAFE_STATUS = {'MONITOR_COMPLETE','UNKNOWN','AUTH_REQUIRED','ERROR','INDEXED','NOT_INDEXED','DISCOVERED','CRAWLED','REMOVED','ADDED','MONITOR_FAILED','SITEMAP_ERROR','ALLOWED','BLOCKED'}
INCIDENT_KINDS = {'AUTH_REQUIRED','AUTH_FAILURE','API_AUTH_FAILURE','AUTHORIZATION_FAILED','CONSECUTIVE_FAILURES','CONSECUTIVE_MONITOR_FAILURES','SITEMAP_PROBLEM','SITEMAP_CHECK_ERROR','WORKFLOW_FAILURE','INDEXNOW_PROBLEM'}


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


class RunnerError(RuntimeError):
    def __init__(self, code, status=None):
        self.code, self.status = code, status
        super().__init__(code)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=True, indent=2) + '\n')
    temporary.replace(path)


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else default


def tls_context():
    # macOS local setup may need the maintained system CA bundle; runners use
    # Python's default verified trust store. Verification is never disabled.
    return ssl.create_default_context(cafile='/etc/ssl/cert.pem' if sys.platform == 'darwin' else None)


def request(url, *, method='GET', token=None, payload=None, opener=None, sleep=time.sleep, attempts=3):
    """Bounded GET retry; POST is a single attempt because delivery can be uncertain."""
    if method not in {'GET','POST'}:
        raise RunnerError('UNSUPPORTED_HTTP_METHOD')
    opener = opener or urlopen
    data = None if payload is None else json.dumps(payload).encode()
    headers = {'Accept':'application/json','User-Agent':'GEO-Lab-Google-Index-Monitor/1.0'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if payload is not None:
        headers['Content-Type'] = 'application/json'
    allowed_attempts = attempts if method == 'GET' else 1
    for attempt in range(1, allowed_attempts + 1):
        try:
            with opener(Request(url,data=data,headers=headers,method=method), timeout=30, context=tls_context()) as response:
                body = response.read(4_000_001)
                if len(body)>4_000_000:
                    raise RunnerError('RESPONSE_TOO_LARGE')
                return {'status':response.status,'body':body,'headers':dict(response.headers)}
        except HTTPError as exc:
            status = exc.code
            # Never include raw Google/GitHub error text in public logs/alerts.
            reasons=[]
            try:
                error=json.loads(exc.read(256_000)).get('error',{})
                if isinstance(error,dict):reasons=[e.get('reason')for e in error.get('errors',[])if isinstance(e,dict)]
            except (ValueError,TypeError,AttributeError):pass
            finally:exc.close()
            quota=status==429 or(status==403 and(bool(set(reasons)&{'rateLimitExceeded','userRateLimitExceeded','dailyLimitExceeded','quotaExceeded'})or exc.headers.get('X-RateLimit-Remaining')=='0'))
            if method=='GET' and (quota or status in {500,502,503,504}) and attempt<allowed_attempts:
                delay = min(30, 2 ** (attempt-1))
                retry = exc.headers.get('Retry-After','')
                if retry.isdigit(): delay=min(30,int(retry))
                sleep(delay)
                continue
            raise RunnerError('QUOTA_EXCEEDED'if quota else'AUTHENTICATION_FAILED'if status==401 else'PERMISSION_DENIED'if status==403 else'HTTP_ERROR', status) from None
        except (URLError,TimeoutError,OSError):
            if method=='GET' and attempt<allowed_attempts:
                sleep(min(8,2**(attempt-1)))
                continue
            raise RunnerError('NETWORK_ERROR') from None


def github_json(method, endpoint, token, payload=None, *, requester=request):
    if not endpoint.startswith('/') or endpoint.startswith('//'):
        raise RunnerError('INVALID_GITHUB_ENDPOINT')
    response = requester('https://api.github.com'+endpoint, method=method,token=token,payload=payload)
    try:
        return json.loads(response['body'])
    except (ValueError,TypeError):
        raise RunnerError('INVALID_GITHUB_RESPONSE',response.get('status')) from None


def verify_private_repository(repository, token, *, github=github_json):
    if repository != PRIVATE_REPOSITORY:
        raise RunnerError('UNAPPROVED_STORAGE_REPOSITORY')
    if not token:
        raise RunnerError('GITHUB_AUTH_REQUIRED')
    metadata = github('GET','/repos/'+repository,token)
    if metadata.get('private') is not True or metadata.get('full_name') != repository:
        raise RunnerError('PRIVATE_REPOSITORY_REQUIRED')
    if metadata.get('has_pages') is True:
        raise RunnerError('PRIVATE_STORAGE_MUST_NOT_ENABLE_PAGES')
    return metadata


def validate_inventory(value):
    if not isinstance(value,dict) or value.get('property',value.get('site_url',PROPERTY)) != PROPERTY:
        raise RunnerError('INVALID_INVENTORY_PROPERTY')
    entries=value.get('urls')
    if not isinstance(entries,list) or len(entries)>250:
        raise RunnerError('INVALID_INVENTORY_ENTRIES')
    known=set()
    for item in entries:
        if not isinstance(item,dict):raise RunnerError('INVALID_INVENTORY_ENTRY')
        url=item.get('url','');parsed=urlsplit(url)
        if not url.startswith(PROPERTY) or parsed.scheme!='https' or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise RunnerError('INVENTORY_URL_OUTSIDE_PROPERTY')
        if url in known:raise RunnerError('DUPLICATE_INVENTORY_URL')
        known.add(url)
        if not isinstance(item.get('monitor'),bool):raise RunnerError('INVENTORY_MONITOR_FLAG_REQUIRED')
    if not any(i['monitor'] for i in entries):raise RunnerError('EMPTY_MONITORING_INVENTORY')
    return value


def private_state_path(output, repository):
    root=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],text=True).strip()).resolve()
    state=Path(output).resolve()
    if state!=root/'state':raise RunnerError('STATE_PATH_MUST_BE_PRIVATE_REPOSITORY_STATE')
    remote=subprocess.check_output(['git','remote','get-url','origin'],cwd=root,text=True).strip().removesuffix('.git')
    if remote not in {'https://github.com/'+repository,'git@github.com:'+repository}:
        raise RunnerError('PRIVATE_REMOTE_MISMATCH')
    if state.is_symlink():raise RunnerError('UNSAFE_STATE_PATH')
    return root,state


def load_inventory(path, output, refresh, *, requester=request):
    if refresh:
        response=requester(PUBLIC_INVENTORY)
        try:value=json.loads(response['body'])
        except (ValueError,TypeError):raise RunnerError('INVALID_REMOTE_INVENTORY') from None
    else:value=read_json(path)
    validate_inventory(value)
    write_json(Path(output)/'inventory-used.json',{'loaded_at':utc_now(),'source':PUBLIC_INVENTORY if refresh else 'private checked-out canonical inventory','sha256':hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest(),'inventory':value})
    # Core receives only the reviewed manifest, never instructions or code from a URL.
    actual=Path(output)/'inventory-current.json';write_json(actual,value)
    return actual,value


def sitemap_observation(token, *, requester=request):
    observation={'checked_at':utc_now(),'property':PROPERTY,'sitemap_url':SITEMAP,'accessible':None,'processing_error':None,'google_status':'UNKNOWN','google_response':None}
    try:
        response=requester(SITEMAP)
        root=ET.fromstring(response['body'])
        observation['accessible']=response['status']==200 and root.tag=='{http://www.sitemaps.org/schemas/sitemap/0.9}urlset'
        if not observation['accessible']:observation['access_error']='INVALID_SITEMAP_XML'
    except RunnerError as exc:
        observation['accessible']=False if exc.status is not None else None
        observation['access_error']=exc.code;observation['access_http_status']=exc.status
    except ET.ParseError:
        observation['accessible']=False;observation['access_error']='INVALID_SITEMAP_XML'
    if not token:
        observation['google_status']='AUTH_REQUIRED'
        return observation
    url='https://www.googleapis.com/webmasters/v3/sites/'+quote(PROPERTY,safe='')+'/sitemaps/'+quote(SITEMAP,safe='')
    try:
        response=requester(url,token=token)
        raw=json.loads(response['body']);observation['google_response']=raw
        observation['google_status']='API_RETURNED'
        errors=raw.get('errors')
        if isinstance(errors,(int,str)) and str(errors).isdigit():observation['processing_error']=int(errors)>0
        # isPending or absent lastDownloaded are not inferred processing failures.
    except RunnerError as exc:
        observation['google_status']='QUOTA_EXCEEDED'if exc.code=='QUOTA_EXCEEDED'else'AUTH_REQUIRED'if exc.status in {401,403}else'NOT_SUBMITTED_OR_NOT_FOUND'if exc.status==404 else'API_ERROR'
        observation['api_error']={'category':exc.code,'http_status':exc.status}
    except (ValueError,TypeError):
        observation['google_status']='INVALID_API_RESPONSE'
    return observation


def safe_event(event, known_urls):
    engine=event.get('engine','google')
    if engine not in {'google','bing','openai-search','indexnow'}:raise RunnerError('INVALID_ALERT_ENGINE')
    url=event.get('url',PROPERTY)
    if url not in known_urls and url not in {PROPERTY,SITEMAP}:
        raise RunnerError('ALERT_URL_NOT_MONITORED')
    kind=str(event.get('type',event.get('event',event.get('kind','MONITOR_CHANGE')))).upper()
    if not re.fullmatch(r'[A-Z0-9_]{1,64}',kind):raise RunnerError('INVALID_ALERT_KIND')
    before=str(event.get('before_status',event.get('previous_status','UNKNOWN'))).upper()
    after=str(event.get('after_status',event.get('status','UNKNOWN'))).upper()
    if before not in SAFE_STATUS:before='UNKNOWN'
    if after not in SAFE_STATUS:after='UNKNOWN'
    checked=event.get('checked_at',utc_now())
    if not isinstance(checked,str)or not re.fullmatch(r'[0-9TZ:+.\-]{10,50}',checked):raise RunnerError('INVALID_ALERT_TIME')
    fingerprint=event.get('fingerprint')
    if not isinstance(fingerprint,str)or not re.fullmatch(r'[a-fA-F0-9]{16,64}',fingerprint):
        fingerprint=hashlib.sha256(json.dumps([engine,kind,url,before,after,checked],separators=(',',':')).encode()).hexdigest()
    # Deliberately replace arbitrary source/next_step text with controlled text.
    next_step=('Configure or renew the approved readonly Google OAuth authorization; then rerun this workflow.' if 'AUTH'in kind else
               'Check the public sitemap and its Search Console processing record; do not submit it repeatedly.' if 'SITEMAP'in kind else
               'Review the private snapshot and Search Console indexed view. URL Inspection is not a live test or indexing request.')
    source=('Google OAuth / official API authorization outcome'if'AUTH'in kind else
            'Anonymous HTTP/XML and official Search Console Sitemaps GET'if'SITEMAP'in kind else
            'Private GitHub Actions monitor run records'if'FAILURE'in kind else
            'Google URL Inspection API indexed-version response')
    if engine=='bing':
        source=('Bing authorization configuration; no index query is implied'if'AUTH'in kind else'Official Bing Webmaster REST observation; index membership is separate from crawl data')
        next_step=('Check or renew the selected owner-approved Bing authentication method; do not silently switch credential types.'if'AUTH'in kind else'Inspect the separate private Bing snapshot and official Bing URL Inspection Index card; do not infer ChatGPT indexing.')
        if kind=='BING_FIRST_COMPLETE_BATCH':
            source='Persisted GitHub Actions Bing snapshot: every planned canonical URL query, site access and Sitemap read succeeded; this is not an indexing verdict'
            next_step='@helen-bird The complete Bing query batch has passed. Review the private snapshot and history. Query success does not mean any URL is indexed or discoverable in ChatGPT.'
    elif engine=='openai-search':
        source='Public host-root robots and HTTP access observations; declared UA requests are simulation'
        next_step='Review effective host-root robots, page directives and access errors. Real OpenAI crawling remains UNKNOWN without trusted logs.'
    elif engine=='indexnow':
        source='Official IndexNow receipt and deployed public verification file'
        next_step='Review the private change ledger and verification file. Do not replay uncertain POSTs; receipt is not indexing.'
    return {'engine':engine,'type':kind,'url':url,'before_status':before,'after_status':after,'checked_at':checked,'source':source,'next_step':next_step,'fingerprint':fingerprint.lower()}


def issue_body(event):
    return ('<!-- geo-index-monitor:'+event['fingerprint']+' -->\n'
            'A recorded monitoring change needs review.\n\n'
            '| Field | Value |\n| --- | --- |\n'
            '| URL | '+event['url']+' |\n| Previous | '+event['before_status']+' |\n'
            '| Current | '+event['after_status']+' |\n| Checked at | '+event['checked_at']+' |\n'
            '| Source | '+event['source']+' |\n\n'+event['next_step']+'\n\n'
            'Detailed raw responses remain in this private repository. No claim about AI recommendations is made.\n')


def existing_issue(repository, token, fingerprint, *, github=github_json):
    marker='<!-- geo-index-monitor:'+fingerprint+' -->'
    for page in range(1,11):
        issues=github('GET','/repos/'+repository+'/issues?state=all&per_page=100&page='+str(page),token)
        if not isinstance(issues,list):raise RunnerError('INVALID_ISSUE_LIST')
        for issue in issues:
            if marker in (issue.get('body')or''):
                return {'number':issue['number'],'html_url':issue['html_url']}
        if len(issues)<100:return None
    # Do not risk duplicate delivery after a bounded but incomplete reconciliation.
    raise RunnerError('ISSUE_RECONCILIATION_LIMIT')


def _property_url(url):
    if not isinstance(url,str):return False
    parsed=urlsplit(url)
    return url.startswith(PROPERTY)and parsed.scheme=='https'and not(parsed.query or parsed.fragment or parsed.username or parsed.password)


def historical_monitored_urls(output):
    """Only previously recorded private monitoring evidence grants old URL access."""
    output=Path(output);known=set()
    history=output/'index-history.csv'
    if history.exists():
        with history.open(newline='')as stream:
            rows=csv.DictReader(stream)
            if {'snapshot_id','checked_at','url','status'}<=set(rows.fieldnames or []):
                known.update(row['url']for row in rows if row.get('snapshot_id')and row.get('checked_at')and _property_url(row.get('url')))
    sources=list((output/'snapshots').glob('*.json'))
    sources.extend(output/name for name in('latest-index-status.json','latest-successful-index-status.json'))
    for file in sources:
        if not file.exists():continue
        snapshot=read_json(file)
        if snapshot.get('property')!=PROPERTY or snapshot.get('source')!='official_url_inspection_api' or not snapshot.get('snapshot_id'):
            continue
        for row in snapshot.get('results',[]):
            if isinstance(row,dict)and _property_url(row.get('url')):known.add(row['url'])
    return known


def quarantine_alert(output, original, category):
    path=Path(output)/'alert-quarantine.json';saved=read_json(path,{'events':{}})
    digest=hashlib.sha256(json.dumps(original,sort_keys=True,default=lambda _:'unsupported').encode()).hexdigest()
    saved['events'].setdefault(digest,{'first_seen_at':utc_now(),'status':'QUARANTINED','reason':category,'event_sha256':digest,'next_action':'Review this private outbox event and its URL provenance. Other valid events continue.'})
    write_json(path,saved)


def possible_prior_delivery(entry):
    # Old ledger versions did not have this independent invariant. Treat their
    # ambiguous statuses conservatively; a GET failure cannot erase uncertainty.
    return entry.get('delivery_may_have_occurred',entry.get('status')in{'ATTEMPTING','UNCERTAIN','RECONCILIATION_BLOCKED','CONFIRMED'})is True


def deliver_alerts(events, output, repository, token, known_urls, *, github=github_json):
    path=Path(output)/'notification-ledger.json'
    ledger=read_json(path,{'events':{},'active_incidents':{}});delivered=[]
    permitted=set(known_urls)|historical_monitored_urls(output)
    for original in events:
        try:event=safe_event(original,permitted)
        except (RunnerError,TypeError,AttributeError)as exc:
            quarantine_alert(output,original,getattr(exc,'code','INVALID_ALERT_EVENT'));continue
        fingerprint=event['fingerprint'];kind=event['type']
        incident=kind+'|'+event['url']
        active=ledger['active_incidents'].get(incident)if kind in INCIDENT_KINDS else None
        if active and ledger['events'].get(active,{}).get('status')=='CONFIRMED':continue
        if active and ledger['events'].get(active,{}).get('status')in{'UNCERTAIN','ATTEMPTING','RECONCILIATION_BLOCKED'}:
            event=ledger['events'][active]['event'];fingerprint=active
        elif kind in INCIDENT_KINDS and not active and fingerprint not in ledger['events']:
            # A later renewed incident must be able to alert again after recovery.
            fingerprint=hashlib.sha256((fingerprint+'|'+event['checked_at']).encode()).hexdigest()
            event['fingerprint']=fingerprint
        old=ledger['events'].get(fingerprint,{})
        if old.get('status')=='CONFIRMED':continue
        possible=possible_prior_delivery(old)
        try:
            found=existing_issue(repository,token,fingerprint,github=github)
        except (RunnerError,KeyError,TypeError,ValueError)as exc:
            ledger['events'][fingerprint]={**old,'status':'RECONCILIATION_BLOCKED','event':event,'error_category':getattr(exc,'code','INVALID_RECONCILIATION_RESPONSE'),'delivery_may_have_occurred':possible};write_json(path,ledger);continue
        if found:
            ledger['events'][fingerprint]={**old,'status':'CONFIRMED','event':event,'issue':found,'reconciled':True,'delivery_may_have_occurred':True}
            if kind in INCIDENT_KINDS:ledger['active_incidents'][incident]=fingerprint
            write_json(path,ledger);continue
        if possible:
            # A missing reconciliation result does not prove that a prior POST failed.
            ledger['events'][fingerprint]={**old,'status':'UNCERTAIN','delivery_may_have_occurred':True,'next_action':'Owner review required; no blind fresh POST.'};write_json(path,ledger);continue
        ledger['events'][fingerprint]={'status':'ATTEMPTING','event':event,'attempted_at':utc_now(),'delivery_may_have_occurred':True}
        if kind in INCIDENT_KINDS:ledger['active_incidents'][incident]=fingerprint
        write_json(path,ledger)
        try:
            response=github('POST','/repos/'+repository+'/issues',token,{'title':'GEO index monitor: '+kind+' — '+urlsplit(event['url']).path[-80:],'body':issue_body(event)})
            issue={'number':response['number'],'html_url':response['html_url']}
            ledger['events'][fingerprint].update(status='CONFIRMED',issue=issue);delivered.append(issue)
        except (RunnerError,KeyError,TypeError) as exc:
            ledger['events'][fingerprint].update(status='UNCERTAIN',error_category=getattr(exc,'code','INVALID_ISSUE_RESPONSE'))
        write_json(path,ledger)
    return delivered


def clear_recovered_incidents(output, snapshot, sitemap):
    path=Path(output)/'notification-ledger.json';ledger=read_json(path,None)
    if ledger is None:return
    healthy=snapshot.get('run_complete')is True and snapshot.get('run_status')=='SUCCESS'
    for key in list(ledger['active_incidents']):
        kind=key.split('|',1)[0]
        if (healthy and kind in {'AUTH_REQUIRED','AUTH_FAILURE','API_AUTH_FAILURE','AUTHORIZATION_FAILED','CONSECUTIVE_FAILURES','CONSECUTIVE_MONITOR_FAILURES','WORKFLOW_FAILURE'})or(kind in {'SITEMAP_PROBLEM','SITEMAP_CHECK_ERROR'}and sitemap.get('accessible')is True and sitemap.get('processing_error')is False):
            ledger['active_incidents'].pop(key)
    write_json(path,ledger)


def merge_outbox(output, extra=()):
    """Carry undelivered transitions across advancement of successful snapshots."""
    output=Path(output);all_events=[]
    saved=read_json(output/'alert-outbox.json',{'events':[]});all_events.extend(saved.get('events',[]))
    previous=read_json(output/'latest-index-status.json',{})
    all_events.extend(previous.get('alerts',[]))
    latest=read_json(output/'alerts.json',[])
    all_events.extend(latest if isinstance(latest,list)else latest.get('alerts',[]))
    all_events.extend(extra)
    ledger=read_json(output/'notification-ledger.json',{'events':{}})
    pending_incidents=[v['event']for v in ledger['events'].values()if v.get('status')in{'ATTEMPTING','UNCERTAIN','RECONCILIATION_BLOCKED'}and v.get('event',{}).get('type')in INCIDENT_KINDS]
    by={}
    for event in all_events:
        if str(event.get('type',event.get('kind',''))).upper()in INCIDENT_KINDS:continue
        key=event.get('fingerprint')or hashlib.sha256(json.dumps(event,sort_keys=True).encode()).hexdigest()
        if ledger['events'].get(key,{}).get('status')=='CONFIRMED':continue
        by.setdefault(key,event)
    value={'events':list(by.values())};write_json(output/'alert-outbox.json',value)
    current_incidents=[e for e in extra if str(e.get('type',e.get('kind',''))).upper()in INCIDENT_KINDS]
    return value['events']+pending_incidents+current_incidents


def runtime_error_category(exc):
    if isinstance(exc,RunnerError)and re.fullmatch(r'[A-Z0-9_]{1,80}',exc.code):return exc.code
    if isinstance(exc,json.JSONDecodeError):return 'STATE_JSON_INVALID'
    if isinstance(exc,csv.Error):return 'STATE_CSV_INVALID'
    if isinstance(exc,OSError):return 'STATE_IO_ERROR'
    if isinstance(exc,ValueError):return 'MONITOR_VALIDATION_ERROR'
    if isinstance(exc,(KeyError,TypeError,AttributeError)):return 'MONITOR_STATE_OR_RESPONSE_INVALID'
    return 'INTERNAL_MONITOR_FAILURE'


def operator_failure(output, exc, context=None):
    path=Path(output)/'operator-state.json';context=context or{}
    try:
        prior=read_json(path,{'consecutive_failures':0});failures=prior.get('consecutive_failures',0)
        if type(failures)is not int or failures<0:raise ValueError('invalid failure counter')
    except (ValueError,TypeError,AttributeError):
        # Preserve the corrupt source; immutable local failure records provide a
        # conservative fallback count without copying raw exception/JSON text.
        failures=len(list((Path(output)/'operator-failures').glob('*.json')))
    attempted=context.get('api_requests_attempted',0)
    state={'checked_at':utc_now(),'consecutive_failures':failures+1,'category':runtime_error_category(exc),'http_status':getattr(exc,'status',None),'phase':context.get('phase','unknown'),'google_query_executed':None if attempted is None else attempted>0,'api_requests_attempted':attempted}
    write_json(path,state)
    stamp=re.sub(r'[^0-9]','',state['checked_at'])
    write_json(Path(output)/'operator-failures'/(stamp+'.json'),state)
    if state['consecutive_failures']>=2:
        return {'kind':'WORKFLOW_FAILURE','url':PROPERTY,'before_status':'UNKNOWN','after_status':'MONITOR_FAILED','checked_at':state['checked_at'],'fingerprint':hashlib.sha256(b'wrapper_consecutive_failure').hexdigest()[:24]}
    return None


def _run_verified(args, env, repository, github_token, output, context):
    context['phase']='pending_alert_state'
    merge_outbox(output)
    context['phase']='canonical_inventory'
    inventory_path,inventory=load_inventory(args.inventory,output,args.refresh_inventory)
    context['phase']='google_authorization'
    from google_search_console_auth import load_credentials_from_env,refresh_access_token,AuthError
    token=None;auth_error=None
    try:
        credentials=load_credentials_from_env();token=refresh_access_token(credentials)
    except AuthError as exc:
        auth_error={'category':getattr(exc,'code','AUTH_REQUIRED'),'http_status':getattr(exc,'status',None)}
    if token and env.get('GITHUB_ACTIONS')=='true':print('::add-mask::'+token)
    context['phase']='sitemap_observation'
    sitemap=sitemap_observation(token);write_json(output/'sitemap-status.json',sitemap)
    authorization={'checked_at':utc_now(),'status':'AUTH_REQUIRED'if auth_error else'AUTHORIZED','error':auth_error,'scope_required':'webmasters.readonly','meaning':'OAuth token refresh only; property access is checked separately by URL Inspection.'}
    # Keep previous failures even when the latest authorization recovers.
    previous_authorization=read_json(output/'authorization-status.json',{})
    for observation in (previous_authorization,authorization):
        if not observation:continue
        digest=hashlib.sha256(json.dumps(observation,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        history_path=output/'authorization-observations'/(digest+'.json')
        if not history_path.exists():write_json(history_path,observation)
    write_json(output/'authorization-status.json',authorization)
    from index_monitor import run_monitor
    context.update(phase='url_inspection_and_state',api_requests_attempted=None)
    snapshot=run_monitor(inventory_path,output,token_provider=lambda:token,sitemap_status=sitemap,private_runtime_verified=True)
    context.update(phase='notification_state',api_requests_attempted=snapshot.get('api_requests_attempted'))
    events=merge_outbox(output,snapshot.get('alerts',[]))
    known={i['url']for i in inventory['urls']if i['monitor']}
    delivered=deliver_alerts(events,output,repository,github_token,known)
    clear_recovered_incidents(output,snapshot,sitemap)
    if snapshot.get('run_complete')is True:write_json(output/'operator-state.json',{'consecutive_failures':0,'last_success_at':utc_now()})
    safe={'checked_at':snapshot.get('checked_at'),'run_status':snapshot.get('run_status'),'run_complete':snapshot.get('run_complete')is True,'counts':snapshot.get('counts',{}),'api_requests_attempted':snapshot.get('api_requests_attempted'),'new_private_issues':len(delivered),'state_storage':'private Git history; never GitHub Pages','google_indexing_request_sent':False}
    write_json(output/'safe-run-summary.json',safe)
    if env.get('GITHUB_STEP_SUMMARY'):
        Path(env['GITHUB_STEP_SUMMARY']).write_text('# GEO Lab — Google Index Monitor\n\nRun status: '+str(safe['run_status'])+'\n\n'+json.dumps(safe['counts'])+'\n\nThis is indexed-state monitoring, not a live URL test or indexing request. Detailed state remains private.\n')
    print(json.dumps(safe))
    return 0 if safe['run_status']=='SUCCESS'and safe['run_complete']else 2 if safe['run_status']=='AUTH_REQUIRED'else 3


def run(args):
    env=os.environ;repository=env.get('GITHUB_REPOSITORY','');github_token=env.get('GITHUB_TOKEN','')
    # These guards intentionally remain outside the state-writing handler.
    # A privacy/access failure must not create private data in an unsafe path.
    verify_private_repository(repository,github_token)
    _,output=private_state_path(args.output,repository)
    context={'phase':'state_directory','api_requests_attempted':0}
    try:
        output.mkdir(parents=True,exist_ok=True)
        return _run_verified(args,env,repository,github_token,output,context)
    except Exception as exc:
        category=runtime_error_category(exc);persisted=False;notification='NOT_REQUIRED'
        try:
            event=operator_failure(output,exc,context)
            write_json(output/'operator-failure.json',{'checked_at':utc_now(),'category':category,'phase':context['phase'],'api_requests_attempted':context['api_requests_attempted']})
            write_json(output/'safe-run-summary.json',{'checked_at':utc_now(),'run_status':'RUNTIME_FAILURE','run_complete':False,'error_category':category,'phase':context['phase'],'api_requests_attempted':context['api_requests_attempted'],'index_status_inferred':False})
            persisted=True
            if event:
                # Do not reread a corrupt outbox just to report that corruption.
                delivered=deliver_alerts([event],output,repository,github_token,{PROPERTY})
                notification='DELIVERED_OR_DEDUPLICATED'if delivered else'RECORDED_OR_RECONCILED'
        except Exception:
            # An unwritable private state or corrupt delivery ledger can prevent
            # reliable durable notification. Fail the job; do not send blind.
            notification='UNAVAILABLE_REQUIRES_WORKFLOW_REVIEW'
        print(json.dumps({'status':'RUNTIME_MONITOR_FAILURE','category':category,'phase':context['phase'],'api_requests_attempted':context['api_requests_attempted'],'failure_record_saved':persisted,'notification':notification}),file=sys.stderr)
        return 4


def persist(args):
    repository=os.environ.get('GITHUB_REPOSITORY','');token=os.environ.get('GITHUB_TOKEN','')
    verify_private_repository(repository,token)
    root,state=private_state_path(args.output,repository)
    if not state.exists():return 0
    deny=re.compile(r'"(?:access_token|refresh_token|client_secret|private_key|apiKey|api_key|bing_api_key|bing_oauth_credentials|microsoft_client_secret)"\s*:\s*"[^"\s]+"|[?&]api[Kk]ey=[^&\s]+|Bearer\s+[A-Za-z0-9._-]{16,}|\bsk-[A-Za-z0-9_-]{16,}')
    for file in state.rglob('*'):
        if file.is_symlink()or not file.resolve().is_relative_to(state):raise RunnerError('UNSAFE_STATE_PATH')
        if file.is_file():
            # The separately authorized one-time submission uses an empty local
            # flock file. It is not historical state and must never be staged.
            if file.name=='sitemap-submission.lock'and file.stat().st_size==0:
                continue
            if file.suffix not in {'.json','.csv','.md','.xml'}:raise RunnerError('UNEXPECTED_STATE_FILE')
            if file.suffix=='.xml':
                try:ET.parse(file)
                except ET.ParseError:raise RunnerError('INVALID_STATE_XML')from None
            if deny.search(file.read_text()):raise RunnerError('CREDENTIAL_LIKE_VALUE_IN_STATE')
    subprocess.run(['git','add','--','state',':(exclude)state/sitemap-submission.lock',':(exclude)state/**/sitemap-submission.lock'],cwd=root,check=True)
    staged=subprocess.check_output(['git','diff','--cached','--name-only'],cwd=root,text=True).splitlines()
    if any(not p.startswith('state/')for p in staged):raise RunnerError('UNRELATED_STAGED_CHANGES')
    if not staged:return 0
    subprocess.run(['git','-c','user.name=github-actions[bot]','-c','user.email=41898282+github-actions[bot]@users.noreply.github.com','commit','-m','Record private Google index monitoring snapshot'],cwd=root,check=True)
    # No forced push; one fresh rebase/push recovery is safe for concurrent refs.
    for attempt in range(2):
        subprocess.run(['git','fetch','origin','main'],cwd=root,check=True)
        subprocess.run(['git','rebase','origin/main'],cwd=root,check=True)
        result=subprocess.run(['git','push','origin','HEAD:main'],cwd=root)
        if result.returncode==0:return 0
    raise RunnerError('STATE_PUSH_FAILED')


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    monitor=sub.add_parser('run');monitor.add_argument('--output',required=True);monitor.add_argument('--inventory',default='monitoring/google-index/urls.json');monitor.add_argument('--refresh-inventory',action='store_true')
    save=sub.add_parser('persist');save.add_argument('--output',required=True)
    args=parser.parse_args()
    try:return run(args)if args.command=='run'else persist(args)
    except RunnerError as exc:
        print(json.dumps({'status':'CONFIGURATION_OR_MONITOR_FAILURE','category':exc.code,'http_status':exc.status}),file=sys.stderr);return 4
    except Exception:
        print(json.dumps({'status':'CONFIGURATION_OR_MONITOR_FAILURE','category':'UNVERIFIED_RUNTIME_FAILURE'}),file=sys.stderr);return 4


if __name__=='__main__':raise SystemExit(main())
