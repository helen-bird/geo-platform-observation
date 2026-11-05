import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import copy
import hashlib
import json
import unittest
from urllib.error import URLError
import discoverability_indexnow as m

P=m.PROPERTY;U=P+'article.html';V=P+'new.html';KEY='test-only-fixture-key'
CFG={'host':'helen-bird.github.io','key':KEY,'keyLocation':P+KEY+'.txt'}
def inventory(urls=(U,)):
    return {'site_url':P,'urls':[{'url':u,'indexing_desired':True}for u in urls],'excluded_urls':[{'url':P+'privacy.html','indexing_desired':False}]}
def obs(url=U,body=b'initial',status=200):
    return {url:{'url':url,'http_status':status,'body_sha256':hashlib.sha256(body).hexdigest()if status==200 else None,'noindex':False,'canonical':[url],'possible_interstitial':False,'error':None,'content_type':'text/html'}}
def baseline():return m.plan_changes(inventory(),obs())['next_state']
def changed_plan():return m.plan_changes(inventory(),obs(body=b'new'),baseline())
def requester(events,status=200,error=False):
    def call(method,url,headers,body,timeout):
        events.append((method,url,body))
        if method=='GET':return 200,{},KEY.encode()
        if error:raise URLError('delivery outcome unknown')
        return status,{},b''
    return call

class PlannerTests(unittest.TestCase):
    def test_initial_baseline_does_not_notify_all(self):
        plan=m.plan_changes(inventory(),obs());self.assertTrue(plan['baseline_only']);self.assertEqual(plan['changes'],[])
    def test_no_change_no_notification(self):self.assertEqual(m.plan_changes(inventory(),obs(),baseline())['changes'],[])
    def test_real_added_and_updated(self):
        plan=m.plan_changes(inventory((U,V)),dict(obs(body=b'changed'),**obs(V)),baseline())
        self.assertEqual({c['kind']for c in plan['changes']},{'ADDED','UPDATED'})
    def test_bad_or_noindex_deployment_cannot_notify(self):
        for update in ({'http_status':503},{'noindex':True},{'canonical':[P]},{'possible_interstitial':True},{'error':'NETWORK_ERROR'}):
            values=obs(body=b'changed');values[U].update(update)
            plan=m.plan_changes(inventory(),values,baseline());self.assertEqual(plan['changes'],[]);self.assertTrue(plan['pending'])
    def test_deletion_requires_real_404_or_410(self):
        for status in (200,301,403,500):self.assertEqual(m.plan_changes(inventory(()),obs(status=status),baseline())['changes'],[])
        self.assertEqual(m.plan_changes(inventory(()),obs(status=410),baseline())['changes'][0]['kind'],'DELETED')
    def test_deleted_then_readded_url_is_real_addition(self):
        deleted=m.plan_changes(inventory(()),obs(status=404),baseline());state=deleted['next_state'];state['deliveries'][deleted['changes'][0]['change_id']]={'status':'RECEIVED'}
        restored=m.plan_changes(inventory(),obs(),state)
        self.assertEqual(len(restored['changes']),1);self.assertEqual(restored['changes'][0]['kind'],'ADDED')
    def test_excluded_support_page_never_notified(self):
        plan=m.plan_changes(inventory(),dict(obs(),**obs(P+'privacy.html')),baseline());self.assertEqual(plan['changes'],[])
    def test_initial_failed_fetch_later_success_is_baseline_not_new(self):
        first=m.plan_changes(inventory(),obs(status=503))
        second=m.plan_changes(inventory(),obs(),first['next_state']);self.assertEqual(second['changes'],[])
    def test_unattempted_outbox_survives_key_verification_failure(self):
        plan=changed_plan();saved=[]
        result=m.apply_notifications(plan,config=CFG,requester=lambda *args:(404,{},b''),persist=lambda s:saved.append(copy.deepcopy(s)))
        self.assertFalse(result['post_performed'])
        again=m.plan_changes(inventory(),obs(body=b'new'),saved[-1]);self.assertEqual(len(again['changes']),1)
    def test_return_to_old_content_creates_distinct_real_event(self):
        a=changed_plan();first_id=a['changes'][0]['change_id'];s=a['next_state'];s['deliveries'][first_id]={'status':'RECEIVED'}
        b=m.plan_changes(inventory(),obs(),s);s=b['next_state'];s['deliveries'][b['changes'][0]['change_id']]={'status':'RECEIVED'}
        c=m.plan_changes(inventory(),obs(body=b'new'),s);self.assertEqual(len(c['changes']),1);self.assertNotEqual(c['changes'][0]['change_id'],first_id)
    def test_only_deployed_content_hash_not_timestamp_changes(self):
        values=obs();values[U]['checked_at']='2099-01-01T00:00:00Z';self.assertEqual(m.plan_changes(inventory(),values,baseline())['changes'],[])
    def test_cosmetic_markup_change_does_not_notify(self):
        def observed(color,word='Finding',href='https://example.org/a'):
            body=('<html><head><style>body{color:'+color+'}</style><link rel="canonical" href="'+U+'"></head><body><p class="'+color+'">'+word+'</p><a href="'+href+'">Source</a></body></html>').encode()
            return m.observe_content(inventory(),requester=lambda *a:(200,{'Content-Type':'text/html'},body))
        old=observed('red');state=m.plan_changes(inventory(),old)['next_state'];new=observed('blue')
        self.assertNotEqual(old[U]['body_sha256'],new[U]['body_sha256'])
        self.assertEqual(m.plan_changes(inventory(),new,state)['changes'],[])
        self.assertEqual(len(m.plan_changes(inventory(),observed('red',word='New finding'),state)['changes']),1)
        self.assertEqual(len(m.plan_changes(inventory(),observed('red',href='https://example.org/b'),state)['changes']),1)
    def test_project_key_scope_and_fixed_endpoint(self):
        for values in [dict(CFG,keyLocation='https://helen-bird.github.io/'+KEY+'.txt'),dict(CFG,host='other.example'),dict(CFG,endpoint='https://other.example/indexnow')]:
            with self.assertRaises(m.IndexNowError):m.validate_config(values)

class DeliveryTests(unittest.TestCase):
    def test_baseline_persisted_without_post_or_key_request(self):
        events=[];result=m.apply_notifications(m.plan_changes(inventory(),obs()),config=CFG,requester=requester(events),persist=lambda s:None)
        self.assertEqual(result['status'],'BASELINE_ONLY');self.assertEqual(events,[])
    def test_200_and_202_have_distinct_receipts_no_index_claim(self):
        for code,expected in ((200,'RECEIVED'),(202,'KEY_VALIDATION_PENDING')):
            events=[];saved=[]
            def persist(s):saved.append(copy.deepcopy(s))
            result=m.apply_notifications(changed_plan(),config=CFG,requester=requester(events,code),persist=persist)
            self.assertEqual(result['status'],expected);self.assertEqual(result['engine_index_status'],'UNKNOWN')
            self.assertEqual(len([e for e in events if e[0]=='POST']),1)
            self.assertEqual(next(iter(saved[0]['deliveries'].values()))['status'],'UNCERTAIN')
            payload=json.loads(events[-1][2]);self.assertEqual(payload['keyLocation'],CFG['keyLocation']);self.assertEqual(payload['urlList'],[U])
    def test_uncertain_delivery_never_automatically_repeated(self):
        events=[];result=m.apply_notifications(changed_plan(),config=CFG,requester=requester(events,error=True),persist=lambda s:None)
        self.assertEqual(result['status'],'UNCERTAIN')
        plan=m.plan_changes(inventory(),obs(body=b'new'),result['state'])
        self.assertEqual(plan['changes'],[])
        self.assertEqual(len([e for e in events if e[0]=='POST']),1)
    def test_rejected_post_is_not_retried(self):
        events=[];result=m.apply_notifications(changed_plan(),config=CFG,requester=requester(events,429),persist=lambda s:None)
        self.assertEqual(result['status'],'REJECTED');self.assertEqual(len([e for e in events if e[0]=='POST']),1)
    def test_server_error_retains_uncertain_delivery(self):
        events=[];result=m.apply_notifications(changed_plan(),config=CFG,requester=requester(events,503),persist=lambda s:None)
        self.assertEqual(result['status'],'UNCERTAIN');self.assertEqual(len([e for e in events if e[0]=='POST']),1)
    def test_durable_intent_failure_prevents_post(self):
        events=[]
        def fail(s):raise OSError('disk full')
        with self.assertRaises(OSError):m.apply_notifications(changed_plan(),config=CFG,requester=requester(events),persist=fail)
        self.assertFalse(any(e[0]=='POST'for e in events))
    def test_missing_durable_store_is_rejected(self):
        with self.assertRaises(m.IndexNowError):m.apply_notifications(changed_plan(),config=CFG)
    def test_foreign_or_unreviewed_url_rejected_before_transmission(self):
        for url in ('https://example.com/',P+'unreviewed.html'):
            plan=changed_plan();plan['changes'][0]['url']=url;events=[]
            with self.assertRaises((m.IndexNowError,m.ProbeError)):m.apply_notifications(plan,config=CFG,requester=requester(events),persist=lambda s:None)
            self.assertEqual(events,[])
    def test_post_result_persist_failure_leaves_durable_uncertain(self):
        saves=[];events=[]
        def persist(s):
            if saves:raise OSError('post-send storage failed')
            saves.append(copy.deepcopy(s))
        with self.assertRaises(OSError):m.apply_notifications(changed_plan(),config=CFG,requester=requester(events),persist=persist)
        self.assertEqual(next(iter(saves[0]['deliveries'].values()))['status'],'UNCERTAIN')

if __name__=='__main__':unittest.main()
