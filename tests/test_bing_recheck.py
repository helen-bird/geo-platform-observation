"""Isolated recheck, completion provenance and notification tests; no live calls."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import discoverability_actions as m

P=m.PROPERTY
T='2026-11-07T02:20:00+00:00'
NAME='GEO Lab \u2014 Bing Index Recheck'
REPO='helen-bird/geo-index-monitor'


def snapshot(count=3):
    urls=[P+'page-'+str(i)+'.html'for i in range(count)]
    return {'engine':'bing','checked_at':T,'snapshot_id':'fixture-proof','execution_environment':'github_actions',
            'github_run_id':'123','github_run_attempt':'1','planned_urls':urls,'run_complete':True,
            'url_queries_complete':True,'queries_succeeded':count,'counts':{'UNKNOWN':count},
            'site_access_observation':{'query_status':'SUCCESS'},'sitemap_observation':{'query_success':True},
            'results':[{'url':url,'query_success':True,'query_status':'SUCCESS','index_status':'UNKNOWN','api_attempts':[{'http_status':200}]}for url in urls]}


def inventory():
    return {'site_url':P,'urls':[{'url':url,'category':'primary_content','indexing_desired':True}for url in snapshot()['planned_urls']],'excluded_urls':[]}


class FullPassTests(unittest.TestCase):
    def test_all_unknown_membership_can_be_a_complete_query_batch(self):
        self.assertTrue(m.full_bing_batch(snapshot(70)))
    def test_skipped_missing_duplicate_or_local_results_never_pass(self):
        for change in [lambda x:x.update(execution_environment='owner_macOS_oneoff'),
                       lambda x:x.update(run_complete=False),lambda x:x.update(snapshot_id=None),
                       lambda x:x['results'].pop(),lambda x:x['results'].append(x['results'][0]),
                       lambda x:x['results'][0].update(query_success=False),
                       lambda x:x['results'][0].update(api_attempts=[]),
                       lambda x:x['sitemap_observation'].update(query_success=False),
                       lambda x:x['site_access_observation'].update(query_status='ERROR')]:
            value=snapshot();change(value);self.assertFalse(m.full_bing_batch(value))
    def test_stable_event_dedupes_later_success_and_failure_recovery(self):
        first=snapshot();later=snapshot();later.update(checked_at='2026-11-09T02:20:00+00:00',github_run_id='456',snapshot_id='later')
        a,b=m.bing_completion_event(first),m.bing_completion_event(later)
        self.assertEqual(a['fingerprint'],b['fingerprint'])
        self.assertFalse(any(e['type']=='BING_FIRST_COMPLETE_BATCH'for e in m.change_events(first,{})))
    def test_controlled_completion_message_mentions_owner_not_indexed(self):
        event=m.google.safe_event(m.bing_completion_event(snapshot()),{P})
        self.assertEqual(event['after_status'],'MONITOR_COMPLETE')
        self.assertIn('@helen-bird',event['next_step'])
        self.assertIn('does not mean any URL is indexed',event['next_step'])
    def test_bing_auth_message_does_not_request_a_different_credential_type(self):
        event=m.google.safe_event({'engine':'bing','type':'AUTH_REQUIRED','url':P,'checked_at':T},{P})
        self.assertIn('selected owner-approved',event['next_step'])
        self.assertNotIn('readonly OAuth',event['next_step'])


class CompletionCallbackTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.old=Path.cwd();os.chdir(self.root)
        self.output=self.root/'state';self.path=self.output/'bing/snapshots/fixture-proof.json';self.path.parent.mkdir(parents=True)
        self.value=snapshot();self.path.write_text(json.dumps(self.value))
        self.actual={'id':123,'workflow_id':7,'name':NAME,'status':'completed','conclusion':'success','head_branch':'main','event':'workflow_dispatch','run_attempt':1,'head_repository':{'full_name':REPO,'private':True}}
        self.calls=[];self.git=[];self.posts=[]
    def tearDown(self):os.chdir(self.old);self.temp.cleanup()
    def client(self,method,path,token):
        self.calls.append((method,path))
        return {'id':7,'name':NAME,'path':'.github/workflows/bing-index-recheck.yml'}if '/workflows/'in path else self.actual
    def runner(self,args,**kwargs):self.git.append(args);return SimpleNamespace(returncode=0)
    def deliver(self,events,folder,repo,token,known):
        self.posts.extend(events)
        m.google.write_json(folder/'notification-ledger.json',{'events':{e['fingerprint']:{'status':'CONFIRMED'}for e in events}})
        return [{'number':99}]if events else[]
    def run_check(self,**kwargs):
        return m.notify_bing_completion(self.output,REPO,'fake',event={'workflow_run':{'id':123,'name':NAME}},client=self.client,runner=self.runner,deliver=kwargs.pop('deliver',self.deliver),**kwargs)
    def test_completed_success_bound_to_committed_snapshot_notifies(self):
        result=self.run_check();self.assertTrue(result['notification_confirmed']);self.assertEqual(len(self.posts),1);self.assertEqual(len(self.git),2)
        self.assertEqual(self.posts[0]['type'],'BING_FIRST_COMPLETE_BATCH')
    def test_failed_in_progress_or_wrong_source_run_never_notifies(self):
        for field,value in [('conclusion','failure'),('status','in_progress'),('head_branch','feature'),('id',999),('workflow_id',9)]:
            original=self.actual[field];self.actual[field]=value
            result=self.run_check();self.assertEqual(result['status'],'NO_APPROVED_SUCCESSFUL_RUN');self.assertFalse(self.posts)
            self.actual[field]=original
    def test_snapshot_from_other_run_attempt_or_missing_planned_url_never_notifies(self):
        for change in [lambda x:x.update(github_run_id='456'),lambda x:x.update(github_run_attempt='2'),lambda x:x['results'].pop()]:
            value=snapshot();change(value);self.path.write_text(json.dumps(value))
            self.assertEqual(self.run_check()['status'],'NO_COMPLETE_BING_BATCH');self.assertFalse(self.posts)
    def test_uncommitted_snapshot_is_blocked_before_delivery(self):
        with self.assertRaises(ValueError):
            m.notify_bing_completion(self.output,REPO,'fake',event={'workflow_run':{'id':123,'name':NAME}},client=self.client,runner=lambda *a,**k:SimpleNamespace(returncode=1),deliver=self.deliver)
        self.assertFalse(self.posts)
    def test_uncertain_delivery_is_not_reported_as_confirmed(self):
        result=self.run_check(deliver=lambda *a:[]);self.assertFalse(result['notification_confirmed']);self.assertEqual(result['status'],'BING_NOTIFICATION_UNCONFIRMED')


class BingOnlyTests(unittest.TestCase):
    def test_only_bing_is_probed_and_other_snapshot_dates_are_preserved(self):
        with tempfile.TemporaryDirectory()as folder:
            out=Path(folder);old={'checked_at':'2026-11-06T08:41:00+00:00','results':[]}
            m.google.write_json(out/'openai-search/latest.json',old)
            m.google.write_json(out/'indexnow/latest-receipt.json',{'status':'NO_CHANGES','post_performed':False,'url_count':0})
            before=(out/'openai-search/latest.json').read_bytes()
            with patch.object(m,'probe_openai',side_effect=AssertionError('No OpenAI query')),patch.object(m,'apply_notifications',side_effect=AssertionError('No IndexNow notification')):
                summary,errors=m.execute_bing_only(out,inventory(),bing_probe=snapshot)
            self.assertEqual(errors,[]);self.assertEqual((out/'openai-search/latest.json').read_bytes(),before)
            self.assertEqual(summary['openai_search']['checked_at'],old['checked_at'])
            self.assertFalse(summary['other_dimensions_rechecked'])
            self.assertEqual(len(list((out/'bing/recheck-receipts').glob('*.json'))),1)
    def test_quota_failure_keeps_all_slots_and_historical_success_pointer(self):
        with tempfile.TemporaryDirectory()as folder:
            out=Path(folder);prior=m.persist_snapshot(out/'bing',snapshot(),complete=True);old=(out/'bing/latest-successful.json').read_bytes()
            failed=snapshot();failed.update(checked_at='2026-11-08T02:20:00+00:00',run_complete=False,url_queries_complete=False,queries_succeeded=0,run_status='QUOTA_EXCEEDED')
            for row in failed['results']:row.update(query_success=False,query_status='NOT_QUERIED_QUOTA_BLOCKED',api_attempts=[])
            _,errors=m.execute_bing_only(out,inventory(),bing_probe=lambda:failed)
            self.assertEqual(errors,['bing']);self.assertEqual((out/'bing/latest-successful.json').read_bytes(),old)
            self.assertEqual(len(json.loads((out/'bing/latest.json').read_text())['results']),3)
            self.assertEqual(len(list((out/'bing/snapshots').glob('*.json'))),2)
    def test_explicit_recheck_interval_is_passed_to_readonly_client(self):
        with patch.dict(os.environ,{'BING_AUTH_METHOD':'api_key','BING_API_KEY':'fixture-key'},clear=True),patch.object(m,'BingClient')as cls,patch.object(m,'inspect_urls',return_value={})as inspect:
            value=m.bing_monitor_probe([{'url':P}],request_interval=10)
        self.assertEqual(cls.call_args.kwargs,{'api_key':'fixture-key','allow_write':False,'request_interval':10})
        self.assertEqual(value['planned_urls'],[P]);self.assertIsNone(value['github_run_id'])
    def test_manual_workflow_is_guarded_and_does_not_change_weekly_cadence(self):
        root=Path(__file__).resolve().parents[1];base=root/'templates'if(root/'templates').exists()else root/'.github/workflows';manual=(base/'bing-index-recheck.yml').read_text();completion=(base/'bing-index-completion.yml').read_text()
        self.assertNotIn('schedule:',manual);self.assertIn('--bing-only --bing-request-interval 10',manual)
        self.assertIn("steps.checkout.outcome == 'success'",manual);self.assertIn('if: always()',manual)
        self.assertIn("workflow_run.conclusion == 'success'",completion)
        self.assertNotIn('BING_API_KEY',completion)
        self.assertIn("17 2 * * 1",(base/'google-index-monitor.yml').read_text())


if __name__=='__main__':unittest.main()
