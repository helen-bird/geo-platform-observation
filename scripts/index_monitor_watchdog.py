#!/usr/bin/env python3
"""Private Actions failure watchdog independent of monitor state persistence.

This script has no Google credential or Google API access. It uses official
Actions run history and private Issues only; it never writes monitoring state.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPOSITORY='helen-bird/geo-index-monitor'
WORKFLOW='GEO Lab — Google Index Monitor'
WORKFLOW_FILE='google-index-monitor.yml'
FAILURES={'failure','timed_out','cancelled'}
EVENTS={'schedule','workflow_dispatch'}


class WatchdogError(RuntimeError):
    def __init__(self,code,status=None):self.code,self.status=code,status;super().__init__(code)


def utc():return dt.datetime.now(dt.timezone.utc).isoformat()


def github(method,path,token,payload=None,*,opener=urlopen,sleep=time.sleep):
    if method not in{'GET','POST'}or not path.startswith('/')or path.startswith('//'):
        raise WatchdogError('INVALID_API_OPERATION')
    headers={'Accept':'application/vnd.github+json','Authorization':'Bearer '+token,'User-Agent':'GEO-Lab-Index-Monitor-Watchdog/1.0','X-GitHub-Api-Version':'2022-11-28'}
    body=None
    if payload is not None:headers['Content-Type']='application/json';body=json.dumps(payload).encode()
    context=ssl.create_default_context(cafile='/etc/ssl/cert.pem'if sys.platform=='darwin'else None)
    for attempt in range(1,(3 if method=='GET'else 1)+1):
        try:
            with opener(Request('https://api.github.com'+path,data=body,headers=headers,method=method),timeout=30,context=context)as response:
                raw=response.read(8_000_001)
                if len(raw)>8_000_000:raise WatchdogError('RESPONSE_TOO_LARGE')
                try:return json.loads(raw)
                except (ValueError,TypeError):raise WatchdogError('INVALID_API_RESPONSE',response.status)from None
        except HTTPError as exc:
            status=exc.code;retry=exc.headers.get('Retry-After','');rate=status==429 or(status==403 and exc.headers.get('X-RateLimit-Remaining')=='0');exc.close()
            if method=='GET'and attempt<3 and(rate or status in{500,502,503,504}):
                sleep(min(30,int(retry))if retry.isdigit()else 2**(attempt-1));continue
            raise WatchdogError('API_RATE_LIMIT'if rate else'API_HTTP_ERROR',status)from None
        except (URLError,TimeoutError,OSError):
            if method=='GET'and attempt<3:sleep(2**(attempt-1));continue
            raise WatchdogError('API_NETWORK_ERROR')from None


def approved_run(run,workflow_id):
    return (isinstance(run,dict)and type(run.get('id'))is int and run['id']>0
        and run.get('workflow_id')==workflow_id and run.get('name')==WORKFLOW
        and run.get('status')=='completed'and run.get('head_branch')=='main'
        and run.get('event')in EVENTS
        and isinstance(run.get('head_repository'),dict)
        and run['head_repository'].get('full_name')==REPOSITORY
        and run['head_repository'].get('private')is True)


def run_evidence(run):
    updated=run.get('updated_at')
    if not isinstance(updated,str)or not re.fullmatch(r'[0-9TZ:+.\-]{10,50}',updated):updated=None
    return {'id':run['id'],'run_attempt':run.get('run_attempt',1),'conclusion':run.get('conclusion'),'completed_run_updated_at':updated,'url':'https://github.com/'+REPOSITORY+'/actions/runs/'+str(run['id'])}


def history(token,workflow_id,*,client=github):
    found={};complete=False
    for page in range(1,11):
        response=client('GET','/repos/'+REPOSITORY+'/actions/workflows/'+str(workflow_id)+'/runs?branch=main&status=completed&per_page=100&page='+str(page),token)
        rows=response.get('workflow_runs')if isinstance(response,dict)else None
        if not isinstance(rows,list):raise WatchdogError('INVALID_RUN_HISTORY')
        for run in rows:
            if approved_run(run,workflow_id):found[run['id']]=run
        ordered=sorted(found.values(),key=lambda r:(r.get('run_number',r['id']),r['id']),reverse=True)
        if any(r.get('conclusion')=='success'for r in ordered):complete=True;break
        if len(rows)<100:complete=True;break
    return sorted(found.values(),key=lambda r:(r.get('run_number',r['id']),r['id']),reverse=True),complete


def incident(runs,complete,workflow_id):
    if len(runs)<2 or any(r.get('conclusion')not in FAILURES for r in runs[:2]):return None
    healthy=next((r for r in runs[2:]if r.get('conclusion')=='success'),None)
    if healthy is None and not complete:raise WatchdogError('RUN_HISTORY_INCOMPLETE')
    span=runs[:runs.index(healthy)]if healthy else runs
    chronological=list(reversed(span));first_eligible=None
    for prior,current in zip(chronological,chronological[1:]):
        if prior.get('conclusion')in FAILURES and current.get('conclusion')in FAILURES:
            first_eligible=current['id'];break
    if first_eligible is None:raise WatchdogError('INCONSISTENT_RUN_HISTORY')
    anchor=str(healthy['id'])+':'+str(healthy.get('run_attempt',1))if healthy else'no-success-in-complete-history'
    marker=hashlib.sha256(json.dumps([REPOSITORY,workflow_id,anchor],separators=(',',':')).encode()).hexdigest()[:32]
    return {'fingerprint':marker,'latest_two':[run_evidence(r)for r in runs[:2]],'prior_healthy':run_evidence(healthy)if healthy else None,'first_eligible_trigger_run':first_eligible}


def existing_issue(token,fingerprint,*,client=github):
    marker='<!-- geo-index-watchdog:'+fingerprint+' -->'
    for page in range(1,11):
        # Closed Issues also suppress repeats until a new healthy run resets
        # the incident identity. Closing an Issue is not a new failure event.
        issues=client('GET','/repos/'+REPOSITORY+'/issues?state=all&per_page=100&page='+str(page),token)
        if not isinstance(issues,list):raise WatchdogError('INVALID_ISSUE_HISTORY')
        for issue in issues:
            if marker in(issue.get('body')or''):
                return {'number':issue['number'],'url':'https://github.com/'+REPOSITORY+'/issues/'+str(issue['number'])}
        if len(issues)<100:return None
    raise WatchdogError('ISSUE_HISTORY_INCOMPLETE')


def issue_body(value,checked_at):
    body='<!-- geo-index-watchdog:'+value['fingerprint']+' -->\nTwo consecutive approved Google index-monitor workflow runs failed.\n\n'
    body+='| Run | Conclusion | Completed-run updated time |\n| --- | --- | --- |\n'
    for run in reversed(value['latest_two']):body+='| [Run '+str(run['id'])+']('+run['url']+') | '+str(run['conclusion'])+' | '+str(run['completed_run_updated_at']or'Not returned')+' |\n'
    prior=value['prior_healthy']
    body+='\nPrior successful run: '+('[Run '+str(prior['id'])+']('+prior['url']+'), completed-run updated time '+str(prior['completed_run_updated_at'])if prior else'none in the complete reviewed history')+'.\n'
    body+='\nChecked at: '+checked_at+'. Source: official GitHub Actions workflow-runs API. `updated_at` belongs to a completed run and is not presented as a separate exact completion timestamp.\n'
    body+='\nReview the linked runs, checkout/setup, private state validation and Git push permissions. This watchdog is independent of state persistence and has no Google credential. No page index state or AI recommendation effect is inferred.\n'
    return body


def inspect_event(event,repository,token,*,client=github,watchdog_attempt=1):
    result={'checked_at':utc(),'source':'official_github_actions_workflow_runs_api','google_queries_executed':False,'state_write_required':False,'issue_delivery':'NOT_REQUIRED'}
    if repository!=REPOSITORY:raise WatchdogError('UNAPPROVED_REPOSITORY')
    if not token:raise WatchdogError('GITHUB_AUTH_REQUIRED')
    metadata=client('GET','/repos/'+REPOSITORY,token)
    if metadata.get('private')is not True or metadata.get('full_name')!=REPOSITORY or metadata.get('has_pages')is not False:
        raise WatchdogError('PRIVATE_STORAGE_REQUIRED')
    trigger=event.get('workflow_run')if isinstance(event,dict)else None
    if not isinstance(trigger,dict)or trigger.get('name')!=WORKFLOW:return{**result,'status':'SKIPPED_OTHER_WORKFLOW'}
    trigger_id=trigger.get('id')
    if type(trigger_id)is not int or trigger_id<=0:raise WatchdogError('INVALID_TRIGGER_RUN')
    workflow=client('GET','/repos/'+REPOSITORY+'/actions/workflows/'+WORKFLOW_FILE,token)
    workflow_id=workflow.get('id')
    if type(workflow_id)is not int or workflow.get('name')!=WORKFLOW or workflow.get('path')!='.github/workflows/'+WORKFLOW_FILE:
        raise WatchdogError('UNAPPROVED_WORKFLOW')
    actual=client('GET','/repos/'+REPOSITORY+'/actions/runs/'+str(trigger_id),token)
    if not approved_run(actual,workflow_id):return{**result,'status':'SKIPPED_UNAPPROVED_RUN'}
    if actual.get('conclusion')not in FAILURES:return{**result,'status':'HEALTHY_OR_NON_FAILURE_TRIGGER'}
    runs,complete=history(token,workflow_id,client=client)
    value=incident(runs,complete,workflow_id)
    if value is None:return{**result,'status':'NO_CONSECUTIVE_FAILURES'}
    found=existing_issue(token,value['fingerprint'],client=client)
    if found:return{**result,'status':'ALREADY_NOTIFIED','issue_delivery':'CONFIRMED','issue':found,'incident':value}
    if trigger_id!=value['first_eligible_trigger_run']or watchdog_attempt!=1:
        # With no writable Git state, an absent Issue cannot prove an earlier
        # timed-out POST failed. A later callback/rerun must not blindly resend.
        return{**result,'status':'DELIVERY_UNCONFIRMED_REQUIRES_REVIEW','issue_delivery':'UNCONFIRMED','incident':value,'next_action':'Review the earliest eligible watchdog run and private Issues. Do not infer that an absent Issue proves a prior POST failed.'}
    payload={'title':'GEO index monitor: repeated workflow failures','body':issue_body(value,result['checked_at'])}
    try:
        issue=client('POST','/repos/'+REPOSITORY+'/issues',token,payload)
        if type(issue.get('number'))is not int:raise WatchdogError('INVALID_ISSUE_RESPONSE')
        return{**result,'status':'NOTIFIED','issue_delivery':'CONFIRMED','issue':{'number':issue['number'],'url':'https://github.com/'+REPOSITORY+'/issues/'+str(issue['number'])},'incident':value}
    except (WatchdogError,ValueError,TypeError,KeyError):
        return{**result,'status':'DELIVERY_UNCERTAIN_REQUIRES_REVIEW','issue_delivery':'UNCERTAIN','incident':value,'next_action':'Review this watchdog run and private Issues. POST was attempted once and is not automatically retried.'}


def main():
    try:
        path=Path(os.environ['GITHUB_EVENT_PATH']);event=json.loads(path.read_text())
        attempt=int(os.environ.get('GITHUB_RUN_ATTEMPT','1'))
        result=inspect_event(event,os.environ.get('GITHUB_REPOSITORY',''),os.environ.get('GITHUB_TOKEN',''),watchdog_attempt=attempt)
        print(json.dumps(result,ensure_ascii=True))
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            Path(os.environ['GITHUB_STEP_SUMMARY']).write_text('# GEO Lab index-monitor watchdog\n\n'+result['status']+'\n\nEvidence: official Actions run history. No Google query or index-state inference.\n\nIf delivery is uncertain, review the earliest eligible watchdog run and private Issues; do not blindly repeat it.\n')
        return 4 if result['issue_delivery']in{'UNCERTAIN','UNCONFIRMED'}else 0
    except Exception as exc:
        code=exc.code if isinstance(exc,WatchdogError)else'WATCHDOG_RUNTIME_FAILURE'
        print(json.dumps({'status':'WATCHDOG_FAILED','category':code,'http_status':getattr(exc,'status',None),'google_queries_executed':False,'next_action':'Review Actions and private Issue availability. No raw API error is logged.'}),file=sys.stderr)
        return 4


if __name__=='__main__':raise SystemExit(main())
