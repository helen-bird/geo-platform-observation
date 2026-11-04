#!/usr/bin/env python3
"""One-time official Search Console sitemap submission with a private ledger.

This tool never requests ordinary-page indexing or executes a live URL test.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request
import xml.etree.ElementTree as ET

from google_search_console_auth import AuthError, _opener, keychain_delete, load_credentials, refresh_access_token, utc

PROPERTY = 'https://helen-bird.github.io/geo-platform-observation/'
SITEMAP = PROPERTY+'sitemap.xml'
ROOT = Path(__file__).resolve().parents[1]


class SitemapError(RuntimeError):
    def __init__(self, code, status=None, raw=None, attempts=None, uncertain=False):
        self.code,self.status,self.raw,self.attempts,self.uncertain = code,status,raw,attempts or [],uncertain
        super().__init__(code)


def endpoint(site=PROPERTY, sitemap=SITEMAP):
    if site != PROPERTY or sitemap != SITEMAP: raise SitemapError('UNEXPECTED_PROPERTY_OR_SITEMAP')
    return 'https://www.googleapis.com/webmasters/v3/sites/'+quote(site,safe='')+'/sitemaps/'+quote(sitemap,safe='')


def baseline_guard(path):
    try: content=Path(path).read_bytes();baseline=json.loads(content)
    except (OSError,ValueError):raise SitemapError('BASELINE_REQUIRED')from None
    prop=baseline.get('property')or baseline.get('property_url')or baseline.get('site_url')
    stamp=baseline.get('captured_at')or baseline.get('checked_at')or baseline.get('created_at')
    if prop != PROPERTY or not isinstance(stamp,str):raise SitemapError('BASELINE_PROVENANCE_REQUIRED')
    try:created=datetime.datetime.fromisoformat(stamp.replace('Z','+00:00'))
    except ValueError:raise SitemapError('INVALID_BASELINE_TIME')from None
    if created.tzinfo is None or created>datetime.datetime.now(datetime.timezone.utc):raise SitemapError('INVALID_BASELINE_TIME')
    return {'sha256':hashlib.sha256(content).hexdigest(),'captured_at':stamp,'property':PROPERTY}


def _write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temporary=path.with_name(path.name+'.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w')as stream:json.dump(data,stream,ensure_ascii=False,indent=2);stream.write('\n')
    os.replace(temporary,path)


def private_state_dir(path):
    result=Path(path).expanduser().resolve()
    if result==ROOT or result.is_relative_to(ROOT):raise SitemapError('PRIVATE_STATE_OUTSIDE_PUBLIC_REPOSITORY_REQUIRED')
    result.mkdir(parents=True,exist_ok=True,mode=0o700)
    return result


def inspect_public_sitemap(*, opener=None):
    opener=_opener()if opener is None else opener
    try:
        with opener.open(Request(SITEMAP,headers={'User-Agent':'GEO-Lab-Sitemap-Verification/1.0'}),timeout=30)as response:
            body=response.read(2_000_001);status=response.status
        if status!=200 or len(body)>2_000_000:raise SitemapError('PUBLIC_SITEMAP_NOT_READABLE',status)
        root=ET.fromstring(body)
    except (HTTPError,URLError,TimeoutError,OSError,ET.ParseError):raise SitemapError('PUBLIC_SITEMAP_NOT_READABLE')from None
    namespace='{http://www.sitemaps.org/schemas/sitemap/0.9}'
    if root.tag!=namespace+'urlset':raise SitemapError('INVALID_SITEMAP_XML')
    urls=[node.findtext(namespace+'loc')for node in root.findall(namespace+'url')]
    if not urls or len(urls)!=len(set(urls)):raise SitemapError('INVALID_SITEMAP_URLS')
    if any(not u or not u.startswith(PROPERTY)or urlsplit(u).query or urlsplit(u).fragment for u in urls):raise SitemapError('INVALID_SITEMAP_URLS')
    return {'checked_at':utc(),'url':SITEMAP,'http_status':200,'sha256':hashlib.sha256(body).hexdigest(),'url_count':len(urls)}


def _api_request(method,access_token,*,opener=None,sleep=time.sleep):
    opener=_opener()if opener is None else opener;attempts=[]
    for retry in range(3):
        when=utc()
        try:
            request=Request(endpoint(),method=method,headers={'Authorization':'Bearer '+access_token,'Accept':'application/json'})
            with opener.open(request,timeout=30)as response:
                status=response.status;data=response.read(2_000_001)
            payload=json.loads(data)if data else{}
            attempts.append({'method':method,'checked_at':when,'http_status':status})
            if not isinstance(payload,dict):raise SitemapError('INVALID_API_RESPONSE',status,attempts=attempts)
            return payload,status,attempts
        except HTTPError as error:
            try:raw=json.loads(error.read(200_000))
            except(ValueError,OSError):raw={}
            finally:error.close()
            reasons=[x.get('reason')for x in raw.get('error',{}).get('errors',[])]if isinstance(raw,dict)and isinstance(raw.get('error'),dict)else[]
            quota=error.code==429 or(error.code==403 and any(x in('rateLimitExceeded','userRateLimitExceeded','quotaExceeded')for x in reasons))
            attempts.append({'method':method,'checked_at':when,'http_status':error.code,'quota_error':quota})
            retriable=quota or(method=='GET'and 500<=error.code<600)
            if retriable and retry<2:
                value=error.headers.get('Retry-After','');delay=min(float(value),30)if re.fullmatch(r'\d+(?:\.\d+)?',value)else 2**(retry+1);sleep(delay);continue
            code='AUTH_REQUIRED'if error.code==401 else('QUOTA_ERROR'if quota else('PERMISSION_DENIED'if error.code==403 else'API_HTTP_ERROR'))
            raise SitemapError(code,error.code,raw,attempts,uncertain=method=='PUT'and error.code>=500)from None
        except(URLError,TimeoutError,OSError):
            attempts.append({'method':method,'checked_at':when,'error':'NETWORK_ERROR'})
            if method=='GET'and retry<2:sleep(2**(retry+1));continue
            raise SitemapError('API_NETWORK_ERROR',attempts=attempts,uncertain=method=='PUT')from None
        except(ValueError,UnicodeError):raise SitemapError('INVALID_API_RESPONSE',attempts=attempts,uncertain=method=='PUT')from None
    raise SitemapError('API_HTTP_ERROR',attempts=attempts)


def processing_state(raw):
    if not isinstance(raw,dict):return'UNKNOWN'
    try:errors=int(raw.get('errors',0))
    except(ValueError,TypeError):errors=0
    if errors>0:return'PROCESSING_ERROR'
    if raw.get('isPending')is True:return'PENDING'
    if raw.get('lastDownloaded')and raw.get('isPending')is False:return'READ_REPORTED'
    return'UNKNOWN'


def _observe(state,access_token,*,opener=None,sleep=time.sleep):
    try:
        raw,status,attempts=_api_request('GET',access_token,opener=opener,sleep=sleep)
        result={'source':'search_console_sitemaps_api','checked_at':utc(),'property':PROPERTY,'sitemap_url':SITEMAP,'api_status':status,'processing_state':processing_state(raw),'raw_response':raw,'attempts':attempts}
    except SitemapError as error:
        result={'source':'search_console_sitemaps_api','checked_at':utc(),'property':PROPERTY,'sitemap_url':SITEMAP,'api_status':error.status,'error':error.code,'raw_response':error.raw,'attempts':error.attempts,'processing_state':'UNKNOWN'}
    name='sitemap-observations/'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json';_write(state/name,result)
    return result


def manage_sitemap(*,baseline,state_dir,action='status',access_token=None,opener=None,sleep=time.sleep,public_validator=inspect_public_sitemap):
    provenance=baseline_guard(baseline);state=private_state_dir(state_dir);ledger_path=state/'sitemap-submission.json'
    if action not in('submit','status'):raise SitemapError('INVALID_ACTION')
    lockfile=state/'sitemap-submission.lock'
    with lockfile.open('a')as lock:
        os.chmod(lockfile,0o600);fcntl.flock(lock,fcntl.LOCK_EX)
        if ledger_path.exists():
            try:ledger=json.loads(ledger_path.read_text())
            except(ValueError,OSError):raise SitemapError('INVALID_SUBMISSION_LEDGER')from None
        else:ledger={'property':PROPERTY,'sitemap_url':SITEMAP,'baseline':provenance,'submission_status':'NOT_SUBMITTED','events':[]}
        if ledger.get('property')!=PROPERTY or ledger.get('sitemap_url')!=SITEMAP:raise SitemapError('INVALID_SUBMISSION_LEDGER')
        # Completed submissions never trigger another PUT on a later run.
        completed=ledger['submission_status']in('SUBMITTED','ALREADY_REGISTERED','RECONCILED_PRESENT')
        if access_token is None:
            mode='monitor'if action=='status'or completed else'sitemap'
            access_token=refresh_access_token(load_credentials(mode))
        if action=='status'or completed:
            observation=_observe(state,access_token,opener=opener,sleep=sleep);ledger['latest_observation']=observation;_write(ledger_path,ledger)
            return {'submission_status':ledger['submission_status'],'put_performed':False,'observation':observation}
        # Existing registration alone does not prove that the newly deployed
        # feed was submitted. Perform one explicitly authorized PUT for this
        # setup unless our own ledger already confirms completion.
        observation=_observe(state,access_token,opener=opener,sleep=sleep)
        if observation.get('api_status')not in(200,404):
            ledger['latest_observation']=observation;_write(ledger_path,ledger)
            return {'submission_status':ledger['submission_status'],'put_performed':False,'observation':observation,'error':observation.get('error','API_STATUS_UNKNOWN')}
        # An uncertain previous delivery is never blindly repeated, even if the
        # processing resource has not become visible yet.
        if ledger['submission_status']in('PENDING','UNCERTAIN'):
            if observation.get('api_status')==200 and ledger.get('resource_existed_before_submit')is False:
                ledger.update(submission_status='RECONCILED_PRESENT',latest_observation=observation)
                ledger['events'].append({'event':'RESOURCE_PRESENT_AFTER_UNCERTAIN_DELIVERY','at':utc(),'api_status':200})
                _write(ledger_path,ledger)
                return {'submission_status':'RECONCILED_PRESENT','put_performed':False,'observation':observation,'put_response_confirmed':False}
            ledger['latest_observation']=observation;_write(ledger_path,ledger)
            return {'submission_status':'UNCERTAIN','put_performed':False,'error':'REVIEW_UNCERTAIN_DELIVERY_BEFORE_RESUBMISSION','observation':observation}
        public=public_validator();requested_at=utc();ledger.update(submission_status='PENDING',public_sitemap=public,request_started_at=requested_at,resource_existed_before_submit=observation.get('api_status')==200,pre_submission_observation=observation)
        ledger['events'].append({'event':'SUBMISSION_STARTED','at':requested_at});_write(ledger_path,ledger)
        try:
            raw,status,attempts=_api_request('PUT',access_token,opener=opener,sleep=sleep)
            ledger.update(submission_status='SUBMITTED',submitted_at=requested_at,response_received_at=utc(),api_response_status=status,api_response=raw,submission_attempts=attempts)
            ledger['events'].append({'event':'SUBMISSION_ACCEPTED','at':utc(),'api_status':status});_write(ledger_path,ledger)
        except SitemapError as error:
            ledger.update(submission_status='UNCERTAIN'if error.uncertain else'FAILED',submission_error=error.code,api_response_status=error.status,api_response=error.raw,submission_attempts=error.attempts)
            ledger['events'].append({'event':'SUBMISSION_UNCERTAIN'if error.uncertain else'SUBMISSION_FAILED','at':utc(),'api_status':error.status,'error':error.code});_write(ledger_path,ledger)
            return {'submission_status':ledger['submission_status'],'put_performed':True,'error':error.code,'api_status':error.status}
        observation=_observe(state,access_token,opener=opener,sleep=sleep);ledger['latest_observation']=observation;_write(ledger_path,ledger)
        return {'submission_status':'SUBMITTED','put_performed':True,'api_status':status,'observation':observation,'submitted_at':requested_at}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--baseline',required=True);parser.add_argument('--state-dir',required=True);parser.add_argument('--action',choices=('submit','status'),default='status');args=parser.parse_args(argv)
    try:
        result=manage_sitemap(baseline=args.baseline,state_dir=args.state_dir,action=args.action)
        # The full API response and referring/private metadata remain in the
        # private state directory; terminal output is a safe operation summary.
        safe={k:v for k,v in result.items()if k!='observation'}
        if result.get('observation'):safe['google_processing_state']=result['observation']['processing_state'];safe['status_api_http']=result['observation'].get('api_status')
        if result.get('submission_status')=='SUBMITTED'and result.get('put_performed'):
            try:keychain_delete('sitemap');safe['one_time_local_credential_removed']=True
            except AuthError:safe['one_time_local_credential_removed']=False
        print(json.dumps(safe))
        return 2 if safe.get('error')or safe.get('status_api_http',200)not in(200,404)else 0
    except(AuthError,SitemapError)as error:
        print(json.dumps({'submission_status':'AUTH_REQUIRED'if isinstance(error,AuthError)else'NOT_SUBMITTED','error':error.code,'api_status':error.status}))
        return 2


if __name__=='__main__':raise SystemExit(main())
