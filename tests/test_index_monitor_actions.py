"""Simulated wrapper/notification checks; these are not live Google inspections."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import index_monitor_actions as m


class Response:
    def __init__(self,body,status=200):self.body=body;self.status=status;self.headers={}
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,*args):return self.body


def event(kind='FIRST_INDEXED',at='2026-11-09T02:18:00+00:00',fingerprint='a'*24):
    return {'kind':kind,'url':m.PROPERTY,'before_status':'NOT_INDEXED','after_status':'INDEXED'if kind=='FIRST_INDEXED'else'AUTH_REQUIRED','checked_at':at,'fingerprint':fingerprint,'next_step':'untrusted private text','raw_response':{'secret':'must not copy'}}


class WrapperTests(unittest.TestCase):
    def test_private_repository_required_before_use(self):
        with self.assertRaises(m.RunnerError)as error:
            m.verify_private_repository(m.PRIVATE_REPOSITORY,'fake',github=lambda *a:{'private':False,'full_name':m.PRIVATE_REPOSITORY})
        self.assertEqual(error.exception.code,'PRIVATE_REPOSITORY_REQUIRED')

    def test_wrong_private_repo_rejected(self):
        with self.assertRaises(m.RunnerError):m.verify_private_repository('someone/other','fake',github=lambda *a:self.fail('No request allowed'))

    def test_pages_private_repo_rejected(self):
        with self.assertRaises(m.RunnerError):m.verify_private_repository(m.PRIVATE_REPOSITORY,'fake',github=lambda *a:{'private':True,'full_name':m.PRIVATE_REPOSITORY,'has_pages':True})

    def test_inventory_property_query_and_duplicates(self):
        valid={'site_url':m.PROPERTY,'urls':[{'url':m.PROPERTY,'monitor':True}]}
        self.assertEqual(m.validate_inventory(valid),valid)
        for url in ('https://example.com/',m.PROPERTY+'?token=secret',m.PROPERTY+'#a'):
            with self.assertRaises(m.RunnerError):m.validate_inventory({'urls':[{'url':url,'monitor':True}]})
        with self.assertRaises(m.RunnerError):m.validate_inventory({'urls':valid['urls']*2})

    def test_safe_event_omits_raw_details_and_untrusted_advice(self):
        safe=m.safe_event(event(),{m.PROPERTY})
        self.assertNotIn('raw_response',safe)
        self.assertNotIn('untrusted',json.dumps(safe))
        self.assertEqual(safe['fingerprint'],'a'*24)
        with self.assertRaises(m.RunnerError):m.safe_event({**event(),'url':'https://other.example/private'},{m.PROPERTY})

    def test_sitemap_support_alert_allowed(self):
        safe=m.safe_event({**event('SITEMAP_PROBLEM'),'url':m.SITEMAP,'after_status':'SITEMAP_ERROR'},{m.PROPERTY})
        self.assertEqual(safe['after_status'],'SITEMAP_ERROR')

    def test_get_retries_are_bounded(self):
        calls=[];delays=[]
        def opener(req,**kwargs):
            calls.append(req.get_method())
            raise HTTPError(req.full_url,429,'no raw log',{'Retry-After':'100'},None)
        with self.assertRaises(m.RunnerError)as error:m.request('https://api.github.com/example',opener=opener,sleep=delays.append)
        self.assertEqual(calls,['GET']*3);self.assertEqual(delays,[30,30]);self.assertEqual(error.exception.status,429)

    def test_post_uncertainty_never_blindly_retries(self):
        calls=[]
        def opener(req,**kwargs):calls.append(req.get_method());raise URLError('private network diagnostic')
        with self.assertRaises(m.RunnerError)as error:m.request('https://api.github.com/example',method='POST',payload={},opener=opener,sleep=lambda _:self.fail('No POST retry'))
        self.assertEqual(calls,['POST']);self.assertNotIn('private',str(error.exception))

    def test_google_403_quota_not_authorization_failure(self):
        calls=[]
        def opener(req,**kwargs):
            calls.append(req.get_method())
            raise HTTPError(req.full_url,403,'private error',{},io.BytesIO(b'{"error":{"errors":[{"reason":"quotaExceeded"}]}}'))
        with self.assertRaises(m.RunnerError)as error:m.request('https://www.googleapis.com/example',opener=opener,sleep=lambda _:None)
        self.assertEqual(error.exception.code,'QUOTA_EXCEEDED');self.assertEqual(len(calls),3)

    def test_google_403_permission_not_retried(self):
        calls=[]
        def opener(req,**kwargs):
            calls.append(req.get_method());raise HTTPError(req.full_url,403,'private error',{},io.BytesIO(b'{"error":{"errors":[{"reason":"forbidden"}]}}'))
        with self.assertRaises(m.RunnerError)as error:m.request('https://www.googleapis.com/example',opener=opener,sleep=lambda _:self.fail('No permission retry'))
        self.assertEqual(error.exception.code,'PERMISSION_DENIED');self.assertEqual(len(calls),1)

    def test_issue_confirmation_deduplicates(self):
        with tempfile.TemporaryDirectory()as folder:
            calls=[]
            def github(method,endpoint,token,payload=None):
                calls.append(method)
                return []if method=='GET'else{'number':1,'html_url':'https://github.com/'+m.PRIVATE_REPOSITORY+'/issues/1'}
            m.deliver_alerts([event()],folder,m.PRIVATE_REPOSITORY,'fake',{m.PROPERTY},github=github)
            m.deliver_alerts([event()],folder,m.PRIVATE_REPOSITORY,'fake',{m.PROPERTY},github=github)
            self.assertEqual(calls,['GET','POST'])

    def test_uncertain_issue_reconciles_without_post_again(self):
        with tempfile.TemporaryDirectory()as folder:
            calls=[]
            def uncertain(method,endpoint,token,payload=None):
                calls.append(method)
                if method=='POST':raise m.RunnerError('NETWORK_ERROR')
                return []
            m.deliver_alerts([event()],folder,m.PRIVATE_REPOSITORY,'fake',{m.PROPERTY},github=uncertain)
            m.deliver_alerts([event()],folder,m.PRIVATE_REPOSITORY,'fake',{m.PROPERTY},github=uncertain)
            self.assertEqual(calls,['GET','POST','GET'])
            ledger=m.read_json(Path(folder)/'notification-ledger.json');self.assertEqual(ledger['events']['a'*24]['status'],'UNCERTAIN')

    def test_sustained_auth_incident_and_new_episode(self):
        with tempfile.TemporaryDirectory()as folder:
            calls=[]
            def github(method,endpoint,token,payload=None):
                calls.append(method);return []if method=='GET'else{'number':len(calls),'html_url':'https://github.com/'+m.PRIVATE_REPOSITORY+'/issues/1'}
            one=event('AUTHORIZATION_FAILED');two=event('AUTHORIZATION_FAILED','2026-11-16T02:18:00+00:00')
            m.deliver_alerts([one],folder,m.PRIVATE_REPOSITORY,'fake',{m.PROPERTY},github=github)
            m.deliver_alerts([two],folder,m.PRIVATE_REPOSITORY,'fake',{m.PROPERTY},github=github)
            self.assertEqual(calls.count('POST'),1)
            m.clear_recovered_incidents(folder,{'run_complete':True,'run_status':'SUCCESS'},{})
            m.deliver_alerts([two],folder,m.PRIVATE_REPOSITORY,'fake',{m.PROPERTY},github=github)
            self.assertEqual(calls.count('POST'),2)

    def test_uncertain_auth_incident_is_reconciled(self):
        with tempfile.TemporaryDirectory()as folder:
            one=event('AUTHORIZATION_FAILED');calls=[]
            def github(method,endpoint,token,payload=None):
                calls.append(method)
                if method=='POST':raise m.RunnerError('NETWORK_ERROR')
                return []
            m.deliver_alerts([one],folder,m.PRIVATE_REPOSITORY,'fake',{m.PROPERTY},github=github)
            m.deliver_alerts([one],folder,m.PRIVATE_REPOSITORY,'fake',{m.PROPERTY},github=github)
            self.assertEqual(calls,['GET','POST','GET'])

    def test_pending_transition_survives_core_advance(self):
        with tempfile.TemporaryDirectory()as folder:
            m.write_json(Path(folder)/'latest-index-status.json',{'alerts':[event()]})
            before=m.merge_outbox(folder);self.assertEqual(len(before),1)
            m.write_json(Path(folder)/'latest-index-status.json',{'alerts':[]})
            self.assertEqual(m.merge_outbox(folder)[0]['fingerprint'],'a'*24)

    def test_confirmed_transition_pruned_from_pending_outbox(self):
        with tempfile.TemporaryDirectory()as folder:
            m.write_json(Path(folder)/'alert-outbox.json',{'events':[event()]})
            m.write_json(Path(folder)/'notification-ledger.json',{'events':{'a'*24:{'status':'CONFIRMED'}},'active_incidents':{}})
            self.assertEqual(m.merge_outbox(folder),[])

    def test_sitemap_get_only_does_not_infer_pending_failure(self):
        urls=[]
        def requester(url,**kwargs):
            urls.append((url,kwargs))
            body=b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>'if url==m.SITEMAP else json.dumps({'isPending':True}).encode()
            return {'status':200,'body':body,'headers':{}}
        result=m.sitemap_observation('fake',requester=requester)
        self.assertTrue(result['accessible']);self.assertIsNone(result['processing_error']);self.assertEqual(len(urls),2)
        self.assertTrue(all(c.get('method','GET')=='GET'for _,c in urls))

    def test_sitemap_errors_from_actual_api_field(self):
        def requester(url,**kwargs):return {'status':200,'body':b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>'if url==m.SITEMAP else b'{"errors":"2"}','headers':{}}
        self.assertTrue(m.sitemap_observation('fake',requester=requester)['processing_error'])

    def test_missing_auth_is_real_failure_with_private_records(self):
        with tempfile.TemporaryDirectory()as folder:
            state=Path(folder)/'state';source=Path(folder)/'urls.json';source.write_text(json.dumps({'site_url':m.PROPERTY,'urls':[{'url':m.PROPERTY,'monitor':True}]}))
            args=argparse.Namespace(output=str(state),inventory=str(source),refresh_inventory=False)
            with patch.dict(os.environ,{'GITHUB_REPOSITORY':m.PRIVATE_REPOSITORY,'GITHUB_TOKEN':'fake'},clear=True),patch.object(m,'verify_private_repository'),patch.object(m,'private_state_path',return_value=(Path(folder),state)),patch.object(m,'sitemap_observation',return_value={'accessible':True,'processing_error':None,'google_status':'AUTH_REQUIRED'}),patch.object(m,'deliver_alerts',return_value=[]),contextlib.redirect_stdout(io.StringIO())as printed:
                code=m.run(args)
            self.assertEqual(code,2);latest=m.read_json(state/'latest-index-status.json');self.assertEqual(latest['results'][0]['status'],'AUTH_REQUIRED');self.assertFalse(latest['run_complete']);self.assertFalse((state/'latest-successful-index-status.json').exists());self.assertNotIn('fake',printed.getvalue())

    def test_empty_submission_lock_not_staged(self):
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder).resolve();state=root/'state';(state/'sitemap').mkdir(parents=True);(state/'sitemap/sitemap-submission.lock').write_bytes(b'');(state/'snapshot.json').write_text('{"status":"AUTH_REQUIRED"}')
            with patch.dict(os.environ,{'GITHUB_REPOSITORY':m.PRIVATE_REPOSITORY,'GITHUB_TOKEN':'fake'},clear=True),patch.object(m,'verify_private_repository'),patch.object(m,'private_state_path',return_value=(root,state)),patch.object(m.subprocess,'check_output',return_value='state/snapshot.json\n'),patch.object(m.subprocess,'run',return_value=SimpleNamespace(returncode=0))as calls:
                self.assertEqual(m.persist(argparse.Namespace(output=str(state))),0)
            add=calls.call_args_list[0].args[0];self.assertIn(':(exclude)state/**/sitemap-submission.lock',add)

    def test_nonempty_submission_lock_rejected(self):
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder).resolve();state=root/'state';state.mkdir();(state/'sitemap-submission.lock').write_text('unexpected sensitive payload')
            with patch.dict(os.environ,{'GITHUB_REPOSITORY':m.PRIVATE_REPOSITORY,'GITHUB_TOKEN':'fake'},clear=True),patch.object(m,'verify_private_repository'),patch.object(m,'private_state_path',return_value=(root,state)),self.assertRaises(m.RunnerError)as error:
                m.persist(argparse.Namespace(output=str(state)))
            self.assertEqual(error.exception.code,'UNEXPECTED_STATE_FILE')

    def test_post_timeout_then_reconciliation_error_cannot_enable_second_post(self):
        with tempfile.TemporaryDirectory()as folder:
            calls=[];phase=[1]
            def github(method,endpoint,token,payload=None):
                calls.append(method)
                if method=='POST':raise m.RunnerError('NETWORK_ERROR')
                if phase[0]==2:raise m.RunnerError('HTTP_ERROR',503)
                return []
            for n in(1,2,3):
                phase[0]=n;m.deliver_alerts([event()],folder,m.PRIVATE_REPOSITORY,'fake',{m.PROPERTY},github=github)
            ledger=m.read_json(Path(folder)/'notification-ledger.json')['events']['a'*24]
            self.assertEqual(calls.count('POST'),1);self.assertTrue(ledger['delivery_may_have_occurred']);self.assertEqual(ledger['status'],'UNCERTAIN')

    def test_active_uncertain_incident_reconciles_after_get_failure(self):
        with tempfile.TemporaryDirectory()as folder:
            calls=[];phase=[1]
            def github(method,endpoint,token,payload=None):
                calls.append(method)
                if method=='POST':raise m.RunnerError('NETWORK_ERROR')
                if phase[0]==2:raise m.RunnerError('NETWORK_ERROR')
                return []
            for n in(1,2,3):
                phase[0]=n;m.deliver_alerts([event('AUTHORIZATION_FAILED')],folder,m.PRIVATE_REPOSITORY,'fake',{m.PROPERTY},github=github)
            self.assertEqual(calls,['GET','POST','GET','GET'])
            ledger=m.read_json(Path(folder)/'notification-ledger.json');self.assertTrue(next(iter(ledger['events'].values()))['delivery_may_have_occurred'])

    def test_first_get_failure_without_post_can_later_deliver(self):
        with tempfile.TemporaryDirectory()as folder:
            calls=[];phase=[1]
            def github(method,endpoint,token,payload=None):
                calls.append(method)
                if phase[0]==1:raise m.RunnerError('NETWORK_ERROR')
                return []if method=='GET'else{'number':1,'html_url':'https://github.com/'+m.PRIVATE_REPOSITORY+'/issues/1'}
            m.deliver_alerts([event()],folder,m.PRIVATE_REPOSITORY,'fake',{m.PROPERTY},github=github)
            self.assertFalse(m.read_json(Path(folder)/'notification-ledger.json')['events']['a'*24]['delivery_may_have_occurred'])
            phase[0]=2;m.deliver_alerts([event()],folder,m.PRIVATE_REPOSITORY,'fake',{m.PROPERTY},github=github)
            self.assertEqual(calls,['GET','GET','POST'])

    def test_removed_url_pending_alert_uses_private_history_provenance(self):
        with tempfile.TemporaryDirectory()as folder:
            old=m.PROPERTY+'old-report/';new=m.PROPERTY+'new-report/';unknown=m.PROPERTY+'never-monitored/'
            (Path(folder)/'index-history.csv').write_text('snapshot_id,checked_at,url,status\nprior,2026-11-04T10:00:00+00:00,'+old+',INDEXED\n')
            sent=[]
            def github(method,endpoint,token,payload=None):
                if method=='GET':return []
                sent.append(payload['body']);return{'number':len(sent),'html_url':'https://github.com/'+m.PRIVATE_REPOSITORY+'/issues/1'}
            events=[{**event(),'url':old},{**event(fingerprint='b'*24),'url':unknown},{**event(fingerprint='c'*24),'url':new}]
            m.deliver_alerts(events,folder,m.PRIVATE_REPOSITORY,'fake',{new},github=github)
            self.assertEqual(len(sent),2);self.assertIn(old,sent[0]);self.assertIn(new,sent[1]);self.assertEqual(len(m.read_json(Path(folder)/'alert-quarantine.json')['events']),1)

    def test_snapshot_provenance_allows_removed_url_but_not_arbitrary_project_url(self):
        with tempfile.TemporaryDirectory()as folder:
            old=m.PROPERTY+'archived/';snapshot={'property':m.PROPERTY,'source':'official_url_inspection_api','snapshot_id':'old-snapshot','results':[{'url':old,'status':'INDEXED'}]}
            m.write_json(Path(folder)/'snapshots/old.json',snapshot)
            self.assertEqual(m.historical_monitored_urls(folder),{old})

    def test_runtime_core_validation_failures_count_and_alert_on_second(self):
        import index_monitor
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder).resolve();state=root/'state';source=root/'urls.json';source.write_text(json.dumps({'site_url':m.PROPERTY,'urls':[{'url':m.PROPERTY,'monitor':True}]}));args=argparse.Namespace(output=str(state),inventory=str(source),refresh_inventory=False)
            with patch.dict(os.environ,{'GITHUB_REPOSITORY':m.PRIVATE_REPOSITORY,'GITHUB_TOKEN':'fake'},clear=True),patch.object(m,'verify_private_repository'),patch.object(m,'private_state_path',return_value=(root,state)),patch.object(m,'sitemap_observation',return_value={'accessible':True,'processing_error':None}),patch.object(index_monitor,'run_monitor',side_effect=ValueError('private-sensitive-value')),patch.object(m,'deliver_alerts',return_value=[])as alerts,contextlib.redirect_stderr(io.StringIO())as errors:
                self.assertEqual(m.run(args),4);self.assertEqual(m.run(args),4)
            record=m.read_json(state/'operator-state.json');self.assertEqual(record['consecutive_failures'],2);self.assertEqual(record['category'],'MONITOR_VALIDATION_ERROR');self.assertIsNone(record['api_requests_attempted']);self.assertIsNone(record['google_query_executed']);self.assertEqual(alerts.call_count,1);self.assertEqual(alerts.call_args.args[0][0]['kind'],'WORKFLOW_FAILURE');self.assertNotIn('private-sensitive-value',errors.getvalue());self.assertFalse(m.read_json(state/'safe-run-summary.json')['run_complete'])

    def test_corrupt_outbox_runtime_failure_is_safe_and_counted(self):
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder).resolve();state=root/'state';state.mkdir();(state/'alert-outbox.json').write_text('{"private": "sensitive-do-not-print"')
            args=argparse.Namespace(output=str(state),inventory=str(root/'unused.json'),refresh_inventory=False)
            with patch.dict(os.environ,{'GITHUB_REPOSITORY':m.PRIVATE_REPOSITORY,'GITHUB_TOKEN':'fake'},clear=True),patch.object(m,'verify_private_repository'),patch.object(m,'private_state_path',return_value=(root,state)),patch.object(m,'deliver_alerts',return_value=[])as alerts,contextlib.redirect_stderr(io.StringIO())as errors:
                self.assertEqual(m.run(args),4);self.assertEqual(m.run(args),4)
            self.assertEqual(m.read_json(state/'operator-state.json')['category'],'STATE_JSON_INVALID');self.assertEqual(alerts.call_count,1);self.assertNotIn('sensitive-do-not-print',errors.getvalue());self.assertEqual(len(list((state/'operator-failures').glob('*.json'))),2)

    def test_privacy_guard_failure_never_writes_failure_state(self):
        with tempfile.TemporaryDirectory()as folder:
            state=Path(folder)/'state';args=argparse.Namespace(output=str(state),inventory='unused',refresh_inventory=False)
            with patch.object(m,'verify_private_repository',side_effect=m.RunnerError('PRIVATE_REPOSITORY_REQUIRED')),patch.object(m,'operator_failure')as recorded,self.assertRaises(m.RunnerError):m.run(args)
            self.assertFalse(state.exists());recorded.assert_not_called()


if __name__=='__main__':unittest.main()
