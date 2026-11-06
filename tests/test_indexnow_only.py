"""IndexNow-only acceptance path; synthetic transports, no live requests."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import discoverability_actions as m
from discoverability_indexnow import apply_notifications,plan_changes
P=m.PROPERTY
CFG={'host':'helen-bird.github.io','key':'public-test-key','keyLocation':P+'public-test-key.txt','endpoint':'https://api.indexnow.org/indexnow'}
URL=P+'learning-hub/'
INV={'site_url':P,'urls':[{'url':URL,'category':'primary_content','indexing_desired':True}],'excluded_urls':[]}
def observed(digest):return {URL:{'url':URL,'http_status':200,'error':None,'noindex':False,'canonical':[URL],'possible_interstitial':False,'body_sha256':digest*64,'content_sha256':digest*64,'content_type':'text/html'}}

class IndexNowOnlyTests(unittest.TestCase):
    def test_only_indexnow_runs_and_other_engine_dates_and_bytes_remain(self):
        with tempfile.TemporaryDirectory()as folder:
            out=Path(folder)
            bing={'engine':'bing','checked_at':'2026-11-06T09:26:00Z','results':[],'run_complete':False,'run_scope':'bing_only_recheck'}
            openai={'checked_at':'2026-11-06T08:41:00Z','results':[]}
            m.google.write_json(out/'bing/latest.json',bing);m.google.write_json(out/'openai-search/latest.json',openai)
            files={p:p.read_bytes()for p in[out/'bing/latest.json',out/'openai-search/latest.json']}
            with patch.object(m,'bing_monitor_probe',side_effect=AssertionError('No Bing query')),patch.object(m,'probe_openai',side_effect=AssertionError('No OpenAI query')):
                summary,errors=m.execute_indexnow_only(out,INV,indexnow_runner=lambda:{'status':'KEY_VALIDATION_PENDING','post_performed':True,'url_count':1,'remote_engine_key_validation':'KEY_VALIDATION_PENDING'})
            self.assertEqual(errors,[]);self.assertEqual(summary['monitor_scope'],'indexnow_only_notification')
            self.assertEqual(summary['bing']['checked_at'],bing['checked_at']);self.assertEqual(summary['openai_search']['checked_at'],openai['checked_at'])
            self.assertEqual(summary['indexnow']['remote_engine_key_validation'],'KEY_VALIDATION_PENDING')
            for p,data in files.items():self.assertEqual(p.read_bytes(),data)
    def test_failed_receipt_preserved_and_alerted_without_invented_success(self):
        with tempfile.TemporaryDirectory()as folder:
            out=Path(folder);events=[]
            summary,errors=m.execute_indexnow_only(out,INV,indexnow_runner=lambda:{'status':'UNCERTAIN','post_performed':True,'url_count':1,'unresolved_delivery_count':1},notify=lambda f,e,*args:events.extend(e))
            self.assertEqual(errors,['indexnow']);self.assertEqual(events[0]['engine'],'indexnow')
            self.assertEqual(json.loads((out/'indexnow/latest-receipt.json').read_text())['status'],'UNCERTAIN')
    def test_exception_is_recorded_without_provider_text(self):
        with tempfile.TemporaryDirectory()as folder:
            def fail():raise RuntimeError('secret-provider-text')
            summary,errors=m.execute_indexnow_only(Path(folder),INV,indexnow_runner=fail)
            self.assertEqual(errors,['indexnow']);self.assertNotIn('secret-provider-text',json.dumps(summary))
    def test_push_precedes_post_and_uncertain_change_is_never_replayed(self):
        with tempfile.TemporaryDirectory()as folder:
            out=Path(folder);old=plan_changes(INV,observed('a'))['next_state'];m.google.write_json(out/'indexnow/change-ledger.json',old)
            events=[];posts=[]
            def runner(args,**kwargs):events.append(args[1]);return SimpleNamespace(returncode=0)
            def transport(method,url,headers,body,timeout):
                if method=='GET':return 200,{},b'public-test-key'
                self.assertEqual(events[-1],'push');posts.append(json.loads(body));raise TimeoutError('uncertain')
            def apply(plan,**kwargs):return apply_notifications(plan,requester=transport,**kwargs)
            with patch.object(m,'observe_content',return_value=observed('b')),patch.object(m,'apply_notifications',side_effect=apply),patch.object(m,'get_url',return_value={'http_status':200,'body':b'public-test-key'}),patch.object(m.subprocess,'run',side_effect=runner),patch.object(m.subprocess,'check_output',return_value='state/indexnow/change-ledger.json\n'):
                first=m.run_indexnow(out,INV,CFG);second=m.run_indexnow(out,INV,CFG)
            self.assertEqual(len(posts),1);self.assertEqual(posts[0]['urlList'],[URL]);self.assertEqual(posts[0]['keyLocation'],CFG['keyLocation'])
            self.assertEqual(first['status'],'UNCERTAIN');self.assertEqual(second['unresolved_delivery_count'],1)
    def test_failed_durable_push_never_transmits(self):
        with tempfile.TemporaryDirectory()as folder:
            out=Path(folder);m.google.write_json(out/'indexnow/change-ledger.json',plan_changes(INV,observed('a'))['next_state'])
            posts=[]
            def runner(args,**kwargs):
                if args[1]=='push':raise RuntimeError('push failed')
                return SimpleNamespace(returncode=0)
            def transport(method,url,*args):
                if method=='GET':return 200,{},b'public-test-key'
                posts.append(url);return 200,{},b''
            def apply(plan,**kwargs):return apply_notifications(plan,requester=transport,**kwargs)
            with patch.object(m,'observe_content',return_value=observed('b')),patch.object(m,'apply_notifications',side_effect=apply),patch.object(m.subprocess,'run',side_effect=runner),patch.object(m.subprocess,'check_output',return_value='state/indexnow/change-ledger.json\n'):
                with self.assertRaises(RuntimeError):m.run_indexnow(out,INV,CFG)
            self.assertEqual(posts,[])
    def test_no_change_does_not_post(self):
        with tempfile.TemporaryDirectory()as folder:
            out=Path(folder);m.google.write_json(out/'indexnow/change-ledger.json',plan_changes(INV,observed('a'))['next_state'])
            with patch.object(m,'observe_content',return_value=observed('a')),patch.object(m,'get_url',return_value={'http_status':200,'body':b'public-test-key'}),patch.object(m.subprocess,'run',return_value=SimpleNamespace(returncode=0)),patch.object(m.subprocess,'check_output',return_value=''),patch.object(m,'apply_notifications',wraps=m.apply_notifications)as send:
                receipt=m.run_indexnow(out,INV,CFG)
            self.assertEqual(receipt['status'],'NO_CHANGES');self.assertFalse(receipt['post_performed'])
    def test_later_new_page_failed_deployment_is_not_mistaken_for_initial_baseline(self):
        state=plan_changes(INV,observed('a'))['next_state']
        new_url=P+'new-real-report/'
        expanded=copy.deepcopy(INV);expanded['urls'].append({'url':new_url,'category':'primary_content','indexing_desired':True})
        failed=plan_changes(expanded,observed('a'),previous_state=state)
        self.assertEqual(failed['changes'],[])
        live=observed('a');live[new_url]={**observed('b')[URL],'url':new_url,'canonical':[new_url]}
        recovered=plan_changes(expanded,live,previous_state=failed['next_state'])
        self.assertEqual([(c['url'],c['kind'])for c in recovered['changes']],[(new_url,'ADDED')])
    def test_failed_initial_baseline_page_does_not_trigger_retroactive_notification(self):
        failed=plan_changes(INV,{})
        recovered=plan_changes(INV,observed('a'),previous_state=failed['next_state'])
        self.assertEqual(recovered['changes'],[])
    def test_google_scope_comes_from_saved_rows_or_counts_not_new_manifest(self):
        for rows in [True,False]:
            with tempfile.TemporaryDirectory()as folder:
                out=Path(folder);saved={'checked_at':'2026-11-06T08:40:00Z','counts':{'INDEXED':5,'NOT_INDEXED':5}}
                if rows:saved['results']=[{'url':P+'old-'+str(i)}for i in range(10)]
                m.google.write_json(out/'latest-successful-index-status.json',saved)
                expanded=copy.deepcopy(INV);expanded['urls']=[{'url':P+'new-'+str(i),'category':'primary_content','indexing_desired':True}for i in range(12)]
                summary,errors=m.execute_indexnow_only(out,expanded,indexnow_runner=lambda:{'status':'NO_CHANGES','post_performed':False,'url_count':0})
                self.assertEqual(summary['google']['recorded_url_count'],10)
                self.assertEqual(summary['google']['checked_at'],saved['checked_at'])
    def test_manual_workflow_has_no_search_credentials_or_repeat_schedule(self):
        root=Path(__file__).resolve().parents[1];path=root/'templates/indexnow-change-notify.yml'
        if not path.exists():path=root/'.github/workflows/indexnow-change-notify.yml'
        text=path.read_text()
        self.assertIn('workflow_dispatch:',text);self.assertIn('--indexnow-only',text)
        self.assertNotIn('schedule:',text);self.assertNotIn('BING_API_KEY',text);self.assertNotIn('GOOGLE_OAUTH_CREDENTIALS',text)
        self.assertIn('if: always()',text)
if __name__=='__main__':unittest.main()
