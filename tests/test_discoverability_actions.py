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

class RenderedReportHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.folder=self.root/'discoverability';self.folder.mkdir()
    def tearDown(self):self.temp.cleanup()
    def generate(self, bing=None, **receipt_values):
        with patch.object(m,'now',return_value=T2):
            return m.report(self.root,inventory(),bing or bing_snapshot(),openai_snapshot(),receipt(**receipt_values))

    def test_successful_feed_report_does_not_claim_registration_unconfirmed(self):
        bing=bing_snapshot()
        bing['sitemap_observation']={'checked_at':T1,'query_status':'SUCCESS','query_success':True,'registered':True,'processing_status':'Success'}
        summary=self.generate(bing)
        text=(self.folder/'report.zh-CN.md').read_text()
        self.assertIn('registered=True',text)
        self.assertNotIn('\u7f3a\u6388\u6743\u65f6\u5c1a\u672a\u786e\u8ba4\u6ce8\u518c',text)
        self.assertIn('API \u67e5\u8be2\u4e0e\u4eba\u5de5\u5bfc\u5165\u8bc1\u636e\u5206\u5f00\u8bb0\u5f55',text)
        self.assertTrue((self.folder/summary['report_snapshot']).is_file())

    def test_legacy_snapshot_environment_not_inferred_from_report_process(self):
        with patch.dict(m.os.environ,{'GITHUB_ACTIONS':'true'},clear=True):
            summary=self.generate()
        self.assertEqual(summary['bing']['execution_environment'],'UNKNOWN')
        self.assertEqual(summary['bing']['weekly_automation_evidence'],'NOT_ESTABLISHED_BY_THIS_SNAPSHOT')
        self.assertIn('UNKNOWN',(self.folder/'report.zh-CN.md').read_text())

    def test_local_oneoff_report_cannot_establish_weekly_actions_success(self):
        bing=bing_snapshot();bing['execution_environment']='owner_macOS_oneoff'
        summary=self.generate(bing)
        self.assertEqual(summary['bing']['execution_environment'],'owner_macOS_oneoff')
        self.assertEqual(summary['bing']['weekly_automation_evidence'],'NOT_ESTABLISHED_BY_THIS_SNAPSHOT')
        text=(self.folder/'report.zh-CN.md').read_text()
        self.assertIn('owner_macOS_oneoff',text)
        self.assertIn('\u672c\u673a\u4e00\u6b21\u6027\u57fa\u7ebf\u4e0d\u4ee3\u8868 GitHub \u6bcf\u5468\u76d1\u6d4b\u5df2\u6210\u529f',text)
        self.assertIn('\u90e8\u5206\u5931\u8d25\u8bb0\u5f55\u7ee7\u7eed\u5355\u72ec\u4fdd\u7559',text)

    def test_quota_partial_report_keeps_skipped_slots_and_first_stop_reason(self):
        bing=bing_snapshot(query='QUOTA_EXCEEDED',complete=False,urls=(U,V,W))
        bing.update({'queries_succeeded':1,'urls_not_queried_after_block':1,'request_interval_seconds':5,
                     'batch_stop':{'operation':'GetUrlInfo','query_status':'QUOTA_EXCEEDED','error':{'category':'QUOTA_EXCEEDED','http_status':400,'provider_error_code':5},'raw_response':{'ErrorCode':5,'Message':'ThrottleHost'},'checked_at':T1}})
        summary=self.generate(bing)
        self.assertFalse(summary['bing']['run_complete'])
        self.assertEqual(summary['bing']['queries_succeeded'],1)
        self.assertEqual(summary['bing']['planned_url_count'],3)
        self.assertEqual(summary['bing']['urls_not_queried_after_block'],1)
        self.assertEqual(summary['bing']['batch_stop']['error']['provider_error_code'],5)
        self.assertNotIn('raw_response',summary['bing']['batch_stop'])
        text=(self.folder/'report.zh-CN.md').read_text()
        self.assertIn('1 / 3',text)
        self.assertIn('\u5f53\u524d\u6279\u6b21\u5df2\u505c\u6b62',text)
        self.assertIn('Retry-After',text)

    def test_preexisting_manual_appendices_and_generated_reports_are_preserved(self):
        previous='Historical report\n\nOwner-confirmed import and failed OAuth notes.\n'
        (self.folder/'report.zh-CN.md').write_text(previous)
        first=self.generate()
        first_path=self.folder/first['report_snapshot'];first_bytes=first_path.read_bytes()
        second=self.generate(status='NO_CHANGES')
        self.assertEqual(first_path.read_bytes(),first_bytes)
        reports=list((self.folder/'report-snapshots').glob('*.zh-CN.md'))
        self.assertEqual(len(reports),3)
        preserved=next(path for path in reports if path.name.startswith('preserved-at-'))
        self.assertEqual(preserved.read_text(),previous)
        metadata=json.loads(preserved.with_name(preserved.name.replace('.zh-CN.md','.json')).read_text())
        self.assertEqual(metadata['preserved_at'],T2)
        self.assertIsNone(metadata['original_generation_time'])
        self.generate(status='NO_CHANGES')
        self.assertEqual(len(list((self.folder/'report-snapshots').glob('*.zh-CN.md'))),3)
        self.assertEqual((self.folder/'report.zh-CN.md').read_bytes(),(self.folder/second['report_snapshot']).read_bytes())

    def test_immutable_metadata_collision_fails_without_overwriting(self):
        summary={'checked_at':T2,'counts':{'UNKNOWN':1}}
        m.persist_report(self.folder,'Exact report',summary)
        original={p.name:p.read_bytes()for p in(self.folder/'report-snapshots').iterdir()}
        with self.assertRaisesRegex(ValueError,'REPORT_SNAPSHOT_ALREADY_EXISTS'):
            m.persist_report(self.folder,'Exact report',dict(summary,counts={'UNKNOWN':2}))
        self.assertEqual({p.name:p.read_bytes()for p in(self.folder/'report-snapshots').iterdir()},original)
        self.assertEqual((self.folder/'report.zh-CN.md').read_text(),'Exact report')


class BingAuthenticationSelectionTests(unittest.TestCase):
    def probe(self, env, response=None):
        from urllib.parse import urlsplit
        from discoverability_bing import BingClient
        calls=[];clients=[]
        def transport(method,url,headers,body,timeout):
            calls.append((method,url,headers,body))
            operation=urlsplit(url).path.rsplit('/',1)[-1]
            payload=({'d':[{'Url':P},{'Url':'https://private.example/'}]} if operation=='GetUserSites'
                     else {'d':[{'Url':P+'sitemap.xml','Status':'Success'}]} if operation=='GetFeeds'
                     else {'d':{'Url':U,'LastCrawledDate':'2026-11-06T08:00:00Z'}})
            return response or (200,{},payload)
        def construct(*args,**kwargs):
            client=BingClient(*args,**kwargs,requester=transport,sleep=lambda _:None)
            clients.append(client);return client
        with patch.dict(m.os.environ,env,clear=True),patch.object(m,'BingClient',side_effect=construct),patch.object(m,'refresh_bing_oauth',return_value='synthetic-oauth')as refresh:
            result=m.bing_monitor_probe([{'url':U}])
        return result,calls,clients,refresh

    def test_probe_records_actual_collection_environment(self):
        for env,expected in (({'BING_AUTH_METHOD':'api_key','BING_API_KEY':'synthetic-key'},'local_process'),
                             ({'BING_AUTH_METHOD':'api_key','BING_API_KEY':'synthetic-key','GITHUB_ACTIONS':'true'},'github_actions')):
            with self.subTest(expected=expected),patch('builtins.print'):
                result,*_=self.probe(env)
            self.assertEqual(result['execution_environment'],expected)

    def test_default_oauth_ignores_present_api_key(self):
        result,calls,clients,refresh=self.probe({'BING_API_KEY':'synthetic-broader-key'})
        refresh.assert_called_once_with()
        self.assertEqual(result['configured_authentication_method'],'oauth')
        self.assertEqual(result['authentication']['method'],'oauth_bearer')
        self.assertTrue(all('apikey='not in call[1] for call in calls))

    def test_explicit_api_key_only_reads_fixed_geo_and_filters_other_sites(self):
        from urllib.parse import urlsplit,parse_qs
        key='synthetic-bing-key'
        result,calls,clients,refresh=self.probe({'BING_AUTH_METHOD':'api_key','BING_API_KEY':key})
        refresh.assert_not_called()
        self.assertEqual(result['run_status'],'SUCCESS_WITH_UNKNOWN_MEMBERSHIP')
        self.assertEqual(result['configured_authentication_method'],'api_key')
        self.assertFalse(result['authentication']['readonly_scoped'])
        self.assertFalse(result['program_access']['write_enabled'])
        self.assertEqual({urlsplit(call[1]).path.rsplit('/',1)[-1]for call in calls},{'GetUserSites','GetUrlInfo','GetFeeds'})
        for method,url,headers,body in calls:
            self.assertEqual(method,'GET');self.assertIsNone(body)
            self.assertEqual(urlsplit(url).netloc,'ssl.bing.com')
            query=parse_qs(urlsplit(url).query)
            self.assertEqual(query['apikey'],[key])
            if 'siteUrl'in query:self.assertEqual(query['siteUrl'],[P])
            if 'url'in query:self.assertEqual(query['url'],[U])
        self.assertNotIn('private.example',json.dumps(result))
        self.assertNotIn(key,json.dumps(result))
        self.assertTrue(all(client.allow_write is False for client in clients))
        count=len(calls)
        self.assertEqual(clients[-1].submit_feed()['error']['category'],'WRITE_AUTHORIZATION_REQUIRED')
        self.assertEqual(len(calls),count)

    def test_missing_selected_api_key_does_not_fall_back_to_oauth(self):
        result,calls,clients,refresh=self.probe({'BING_AUTH_METHOD':'api_key','BING_OAUTH_CREDENTIALS':'present-but-unselected'})
        refresh.assert_not_called();self.assertEqual(calls,[])
        self.assertEqual(result['run_status'],'AUTH_REQUIRED')
        self.assertEqual(result['authorization_error']['category'],'AUTH_REQUIRED')

    def test_invalid_api_key_is_safe_and_never_used(self):
        secret='synthetic-secret\n::injected'
        result,calls,clients,refresh=self.probe({'BING_AUTH_METHOD':'api_key','BING_API_KEY':secret})
        refresh.assert_not_called();self.assertEqual(calls,[])
        self.assertEqual(result['authorization_error']['category'],'INVALID_API_KEY_SECRET')
        self.assertNotIn('synthetic-secret',json.dumps(result))

    def test_invalid_auth_mode_is_safe_and_never_falls_back(self):
        result,calls,clients,refresh=self.probe({'BING_AUTH_METHOD':'private-untrusted-value','BING_API_KEY':'synthetic-key'})
        refresh.assert_not_called();self.assertEqual(calls,[])
        self.assertEqual(result['configured_authentication_method'],'INVALID')
        self.assertEqual(result['authorization_error']['category'],'UNSUPPORTED_BING_AUTH_METHOD')
        self.assertNotIn('private-untrusted-value',json.dumps(result))

    def test_rejected_api_key_never_exposes_provider_text_or_falls_back(self):
        key='synthetic-rejected-key'
        result,calls,clients,refresh=self.probe({'BING_AUTH_METHOD':'api_key','BING_API_KEY':key},response=(403,{}, {'ErrorMessage':key,'apiKey':key}))
        refresh.assert_not_called()
        self.assertFalse(result['run_complete'])
        self.assertNotIn(key,json.dumps(result))
        self.assertTrue(all(row['index_status']=='UNKNOWN'for row in result['results']))

    def test_foreign_url_is_rejected_before_any_api_request(self):
        from discoverability_bing import BingClient
        calls=[]
        def construct(*args,**kwargs):
            return BingClient(*args,**kwargs,requester=lambda *args:calls.append(args))
        with patch.dict(m.os.environ,{'BING_AUTH_METHOD':'api_key','BING_API_KEY':'synthetic-key'},clear=True),patch.object(m,'BingClient',side_effect=construct):
            with self.assertRaisesRegex(ValueError,'URL_OUTSIDE_APPROVED_PROPERTY'):
                m.bing_monitor_probe([{'url':'https://other.example/'}])
        self.assertEqual(calls,[])


if __name__=='__main__':unittest.main()
