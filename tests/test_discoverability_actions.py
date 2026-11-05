"""Isolated orchestration checks: no real credentials, network, Git or Issues."""
import copy
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import discoverability_actions as m

P=m.PROPERTY
U=P+'article.html'
V=P+'other.html'
W=P+'new.html'
T1='2026-11-05T08:00:00+00:00'
T2='2026-11-05T08:10:00+00:00'


def inventory():
    return {'site_url':P,'urls':[{'url':U,'category':'primary_content','indexing_desired':True}], 'excluded_urls':[]}


def bing_snapshot(*, when=T1, status='UNKNOWN', query='SUCCESS', complete=True, urls=(U,)):
    return {'engine':'bing','checked_at':when,'run_status':query,'run_complete':complete,
            'counts':{status:len(urls)},'results':[{'url':url,'checked_at':when,'index_status':status,
            'query_status':query,'last_crawl_time':None,'error':None}for url in urls]}


def openai_snapshot(*, when=T1, configuration='ALLOWED'):
    return {'engine':'openai-search','checked_at':when,'run_complete':True,'root_robots':{'http_status':404},
            'results':[{'url':U,'checked_at':when,'configuration_status':configuration,
            'openai_index_status':'UNKNOWN','public_access':{'error':None},'ua_simulation':{'error':None,'status':'FETCH_SUCCEEDED'},
            'real_crawl':{'status':'UNKNOWN','last_crawl_time':None}}]}


def receipt(**values):
    return {'status':'BASELINE_ONLY','post_performed':False,'url_count':0,'unresolved_delivery_count':0,'key_file_verified':True,**values}


class SnapshotPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def load(self,name):return json.loads((self.root/name).read_text())

    def test_failed_attempt_retained_without_replacing_success_or_baseline(self):
        success=m.persist_snapshot(self.root,bing_snapshot(status='INDEXED'),complete=True)
        original=(self.root/'latest-successful.json').read_bytes();baseline=(self.root/'baseline.json').read_bytes()
        failed=bing_snapshot(when=T2,query='AUTH_REQUIRED',complete=False)
        m.persist_snapshot(self.root,failed,complete=False)
        self.assertEqual((self.root/'latest-successful.json').read_bytes(),original)
        self.assertEqual((self.root/'baseline.json').read_bytes(),baseline)
        self.assertEqual(self.load('latest.json')['run_status'],'AUTH_REQUIRED')
        self.assertEqual(len(list((self.root/'snapshots').glob('*.json'))),2)
        self.assertEqual(self.load('latest-successful.json')['snapshot_id'],success['snapshot_id'])

    def test_initial_auth_required_baseline_never_backfilled_by_success(self):
        m.persist_snapshot(self.root,bing_snapshot(query='AUTH_REQUIRED',complete=False),complete=False)
        baseline=(self.root/'baseline.json').read_bytes()
        m.persist_snapshot(self.root,bing_snapshot(when=T2,complete=True),complete=True)
        self.assertEqual((self.root/'baseline.json').read_bytes(),baseline)
        self.assertEqual(self.load('baseline.json')['run_status'],'AUTH_REQUIRED')
        self.assertEqual(self.load('latest-successful.json')['run_status'],'SUCCESS')

    def test_inventory_added_and_removed_urls_are_in_all_persisted_snapshots(self):
        m.persist_snapshot(self.root,bing_snapshot(urls=(U,V)),complete=True)
        second=m.persist_snapshot(self.root,bing_snapshot(when=T2,urls=(V,W)),complete=True)
        for value in (second,self.load('latest.json'),self.load('latest-successful.json'),self.load('snapshots/'+second['snapshot_id']+'.json')):
            self.assertEqual(value.get('added_urls'),[W])
            self.assertEqual(value.get('removed_urls'),[U])

    def test_failed_inventory_does_not_change_successful_comparison(self):
        m.persist_snapshot(self.root,bing_snapshot(urls=(U,)),complete=True)
        before=(self.root/'comparison.json').read_bytes()
        m.persist_snapshot(self.root,bing_snapshot(when=T2,urls=(V,),complete=False,query='ERROR'),complete=False)
        self.assertEqual((self.root/'comparison.json').read_bytes(),before)

    def test_history_preserves_engine_query_status_and_unknown_membership(self):
        m.persist_snapshot(self.root,bing_snapshot(query='AUTH_REQUIRED',complete=False),complete=False)
        with (self.root/'history.csv').open(newline='')as stream:rows=list(csv.DictReader(stream))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['engine'],'bing')
        self.assertEqual(rows[0]['index_status'],'UNKNOWN')
        self.assertEqual(rows[0]['query_status'],'AUTH_REQUIRED')
        self.assertEqual(rows[0]['last_crawl_time'],'')

    def test_openai_history_never_converts_configuration_to_index_membership(self):
        m.persist_snapshot(self.root,openai_snapshot(configuration='ALLOWED'),complete=True)
        with (self.root/'history.csv').open(newline='')as stream:row=next(csv.DictReader(stream))
        self.assertEqual(row['engine'],'openai-search')
        self.assertEqual(row['configuration_status'],'ALLOWED')
        self.assertEqual(row['index_status'],'UNKNOWN')
        self.assertEqual(row['last_crawl_time'],'')

    def test_immutable_snapshot_collision_rejected_without_overwriting(self):
        m.google.write_json(self.root/'comparison.json',{'urls':{U:'UNKNOWN'},'checked_at':T1})
        snapshot=bing_snapshot();m.persist_snapshot(self.root,snapshot,complete=True)
        before=(self.root/'latest.json').read_bytes()
        with self.assertRaises(ValueError):m.persist_snapshot(self.root,snapshot,complete=True)
        self.assertEqual((self.root/'latest.json').read_bytes(),before)


class OrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def execute(self,**kwargs):
        values={'bing_probe':lambda:bing_snapshot(),'openai_probe':lambda:openai_snapshot(),'indexnow_runner':lambda:receipt()}
        values.update(kwargs)
        return m.execute(self.root,inventory(),{},**values)

    def test_bing_probe_exception_does_not_stop_other_dimensions(self):
        calls=[]
        def fail():raise RuntimeError('provider-private diagnostic must not leak')
        def openai():calls.append('openai');return openai_snapshot()
        def indexnow():calls.append('indexnow');return receipt()
        summary,errors=self.execute(bing_probe=fail,openai_probe=openai,indexnow_runner=indexnow)
        self.assertEqual(calls,['openai','indexnow'])
        self.assertIn('bing',errors)
        self.assertEqual(summary['openai_search']['configuration_allowed'],1)
        stored=json.loads((self.root/'bing/latest.json').read_text())
        self.assertEqual(stored['results'][0]['index_status'],'UNKNOWN')
        self.assertNotIn('provider-private',json.dumps(stored))
        self.assertFalse((self.root/'bing/latest-successful.json').exists())

    def test_explicit_bing_auth_required_stays_unknown_in_history_and_report(self):
        summary,errors=self.execute(bing_probe=lambda:bing_snapshot(query='AUTH_REQUIRED',complete=False))
        self.assertEqual(summary['bing']['query_status'],'AUTH_REQUIRED')
        self.assertEqual(summary['bing']['counts'],{'UNKNOWN':1})
        self.assertIn('bing',errors)
        with (self.root/'bing/history.csv').open(newline='')as stream:row=next(csv.DictReader(stream))
        self.assertEqual(row['index_status'],'UNKNOWN')
        self.assertEqual(row['query_status'],'AUTH_REQUIRED')

    def test_successful_bing_query_with_unknown_membership_is_not_false_failure(self):
        summary,errors=self.execute()
        self.assertEqual(errors,[])
        self.assertEqual(summary['bing']['counts'],{'UNKNOWN':1})
        self.assertTrue((self.root/'bing/latest-successful.json').is_file())
        self.assertFalse(summary['ai_answer_experiments_run'])

    def test_google_state_is_preserved_by_extension(self):
        original=b'{"checked_at":"2026-11-04T01:00:00Z","counts":{"INDEXED":1}}\n'
        (self.root/'latest-successful-index-status.json').write_bytes(original)
        summary,_=self.execute()
        self.assertEqual((self.root/'latest-successful-index-status.json').read_bytes(),original)
        self.assertEqual(summary['google']['counts'],{'INDEXED':1})

    def test_failed_indexnow_receipt_marks_dimension_incomplete_without_false_post(self):
        summary,errors=self.execute(indexnow_runner=lambda:receipt(status='ERROR',error='KEY_FILE_UNAVAILABLE'))
        self.assertIn('indexnow',errors)
        self.assertIs(summary['indexnow']['post_performed'],False)
        self.assertEqual(summary['indexnow']['url_count'],0)
        self.assertTrue((self.root/'bing/latest-successful.json').exists())
        self.assertTrue((self.root/'openai-search/latest-successful.json').exists())

    def test_prior_uncertain_delivery_remains_failure_even_without_new_changes(self):
        summary,errors=self.execute(indexnow_runner=lambda:receipt(status='NO_CHANGES',unresolved_delivery_count=1))
        self.assertIn('indexnow',errors)
        self.assertEqual(summary['indexnow']['unresolved_delivery_count'],1)
        self.assertFalse(summary['indexnow']['post_performed'])
        stored=json.loads((self.root/'indexnow/latest-receipt.json').read_text())
        self.assertEqual(stored['unresolved_delivery_count'],1)

    def test_key_verification_failure_is_not_a_successful_initialization(self):
        summary,errors=self.execute(indexnow_runner=lambda:receipt(key_file_verified=False))
        self.assertIn('indexnow',errors)
        self.assertFalse(summary['indexnow']['post_performed'])

    def test_exception_cannot_claim_whether_a_post_occurred(self):
        def fail():raise RuntimeError('error could have occurred after send')
        summary,errors=self.execute(indexnow_runner=fail)
        self.assertIn('indexnow',errors)
        self.assertIsNone(summary['indexnow']['post_performed'])
        self.assertIsNone(summary['indexnow']['url_count'])
        self.assertNotIn('error could',json.dumps(summary))

    def test_engine_notification_failure_does_not_stop_probes_or_receipt_persistence(self):
        calls=[]
        def bad_notification(folder,events,entries,value):calls.append(folder.name);raise OSError('notification failed')
        summary,errors=self.execute(notify=bad_notification)
        self.assertEqual(set(calls),{'bing','openai-search'})
        self.assertTrue((self.root/'indexnow/latest-receipt.json').is_file())
        self.assertEqual(summary['openai_search']['configuration_allowed'],1)
        self.assertEqual(set(errors),{'bing','openai-search'})
        failures=[json.loads(p.read_text())for p in (self.root/'discoverability/operator-failures').glob('*.json')]
        self.assertEqual({v['engine']for v in failures},{'bing','openai-search'})
        self.assertTrue(all('NOTIFICATION' in v['error']for v in failures))

    def test_indexnow_alert_failure_still_preserves_receipt_and_other_dimensions(self):
        def bad_notification(folder,events,entries,value):
            if folder.name=='indexnow':raise OSError('notification failed')
        summary,errors=self.execute(notify=bad_notification,indexnow_runner=lambda:receipt(status='UNCERTAIN',unresolved_delivery_count=1,post_performed=True,url_count=1))
        self.assertIn('indexnow',errors)
        self.assertTrue((self.root/'indexnow/latest-receipt.json').is_file())
        self.assertEqual(summary['indexnow']['status'],'UNCERTAIN')
        self.assertTrue((self.root/'openai-search/latest-successful.json').is_file())
        self.assertEqual(summary['indexnow']['notification_error'],'DELIVERY_OR_STATE_FAILURE')

    def test_pending_deployment_checks_are_incomplete_even_without_post(self):
        summary,errors=self.execute(indexnow_runner=lambda:receipt(status='NO_CHANGES',pending_count=1))
        self.assertIn('indexnow',errors)
        self.assertEqual(summary['indexnow']['pending_count'],1)
        self.assertFalse(summary['indexnow']['post_performed'])

    def test_bing_state_read_failure_does_not_stop_other_dimensions(self):
        original=m.google.read_json
        def read(path,default=None):
            if Path(path)==self.root/'bing/latest-successful.json':raise ValueError('corrupt prior Bing state')
            return original(path,default)
        with patch.object(m.google,'read_json',side_effect=read):summary,errors=self.execute()
        self.assertIn('bing',errors)
        self.assertEqual(summary['openai_search']['configuration_allowed'],1)
        self.assertTrue((self.root/'indexnow/latest-receipt.json').exists())

    def test_bing_persist_failure_does_not_stop_other_dimensions(self):
        original=m.persist_snapshot
        def persist(folder,snapshot,**kwargs):
            if Path(folder).name=='bing':raise OSError('storage failure')
            return original(folder,snapshot,**kwargs)
        with patch.object(m,'persist_snapshot',side_effect=persist):summary,errors=self.execute()
        self.assertIn('bing',errors)
        self.assertEqual(summary['openai_search']['configuration_allowed'],1)
        self.assertTrue((self.root/'indexnow/latest-receipt.json').exists())

    def test_healthy_indexnow_clears_only_prior_indexnow_incident(self):
        path=self.root/'indexnow/notification-ledger.json'
        m.google.write_json(path,{'active_incidents':{'INDEXNOW_PROBLEM|old':'old-id','OTHER_INCIDENT|x':'keep-id'}})
        self.execute()
        ledger=json.loads(path.read_text())
        self.assertEqual(ledger['active_incidents'],{'OTHER_INCIDENT|x':'keep-id'})


class ChangeEventTests(unittest.TestCase):
    def test_same_transition_in_later_episode_has_new_fingerprint(self):
        before=bing_snapshot(status='INDEXED');before['snapshot_id']='episode-a'
        after=bing_snapshot(when=T2,status='NOT_INDEXED')
        a=m.change_events(after,before)[0]
        later=copy.deepcopy(before);later['snapshot_id']='episode-b'
        b=m.change_events(after,later)[0]
        self.assertEqual(a['type'],'DEINDEXED')
        self.assertEqual(a['engine'],'bing')
        self.assertNotEqual(a['fingerprint'],b['fingerprint'])

    def test_auth_error_does_not_emit_false_deindex_event(self):
        before=bing_snapshot(status='INDEXED');before['snapshot_id']='good-snapshot'
        failure=bing_snapshot(when=T2,query='AUTH_REQUIRED',complete=False)
        events=m.change_events(failure,before)
        self.assertTrue(any(e['type']=='AUTH_REQUIRED'for e in events))
        self.assertFalse(any(e['type']=='DEINDEXED'for e in events))

    def test_engine_is_part_of_event_identity(self):
        before=bing_snapshot(status='INDEXED');before['snapshot_id']='same-prior'
        current=bing_snapshot(status='NOT_INDEXED')
        a=m.change_events(current,before)[0]
        current['engine']='google';b=m.change_events(current,before)[0]
        self.assertNotEqual(a['fingerprint'],b['fingerprint'])

    def test_openai_blocking_event_is_crawl_configuration_only(self):
        previous=openai_snapshot();previous['snapshot_id']='oai-prior'
        current=openai_snapshot(when=T2,configuration='BLOCKED')
        event=m.change_events(current,previous)[0]
        self.assertEqual(event['type'],'CRAWL_BLOCK')
        self.assertEqual(event['engine'],'openai-search')
        self.assertEqual(event['status'],'BLOCKED')


class SafeEngineEventTests(unittest.TestCase):
    def test_engine_and_controlled_provenance_survive_resanitization(self):
        for engine in ('bing','openai-search','indexnow'):
            event={'engine':engine,'type':'VISIBILITY_CHANGE','url':U,'before_status':'UNKNOWN','status':'ERROR','checked_at':T1,'source':'untrusted injected source','next_step':'untrusted action'}
            once=m.google.safe_event(event,{U});twice=m.google.safe_event(once,{U})
            self.assertEqual(twice['engine'],engine)
            self.assertEqual(twice['source'],once['source'])
            self.assertEqual(twice['next_step'],once['next_step'])
            self.assertEqual(twice['fingerprint'],once['fingerprint'])
            self.assertNotIn('untrusted',str(twice))
            self.assertNotIn('Search Console indexed view',twice['next_step'])

    def test_oai_configuration_statuses_survive_safe_event(self):
        event={'engine':'openai-search','type':'CRAWL_BLOCK','url':U,'before_status':'ALLOWED','status':'BLOCKED','checked_at':T1}
        safe=m.google.safe_event(m.google.safe_event(event,{U}),{U})
        self.assertEqual(safe['before_status'],'ALLOWED')
        self.assertEqual(safe['after_status'],'BLOCKED')
        self.assertIn('simulation',safe['source'])

    def test_unsupported_engine_rejected(self):
        with self.assertRaises(m.google.RunnerError)as caught:m.google.safe_event({'engine':'unapproved-vendor','url':U,'checked_at':T1},{U})
        self.assertEqual(caught.exception.code,'INVALID_ALERT_ENGINE')

    def test_identical_fallback_event_on_distinct_engines_gets_distinct_fingerprint(self):
        common={'type':'AUTH_REQUIRED','url':P,'before_status':'UNKNOWN','status':'AUTH_REQUIRED','checked_at':T1}
        a=m.google.safe_event(dict(common,engine='bing'),{U})
        b=m.google.safe_event(dict(common,engine='google'),{U})
        self.assertNotEqual(a['fingerprint'],b['fingerprint'])

if __name__=='__main__':unittest.main()
