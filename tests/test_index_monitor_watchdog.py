"""Synthetic official-run/Issue responses; no GitHub or Google network writes."""
import io
from pathlib import Path
import sys
import unittest
from urllib.error import URLError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import index_monitor_watchdog as m


def run(identifier,conclusion='failure',**changes):
    record={'id':identifier,'run_number':identifier,'run_attempt':1,'workflow_id':7,'name':m.WORKFLOW,'status':'completed','conclusion':conclusion,'head_branch':'main','event':'schedule','head_repository':{'full_name':m.REPOSITORY,'private':True},'updated_at':'2026-11-09T02:20:00Z'}
    record.update(changes);return record


class Client:
    def __init__(self,runs,issues=None,private=True,post_timeout=False):
        self.runs=runs;self.issues=issues or[];self.private=private;self.post_timeout=post_timeout;self.calls=[]
    def __call__(self,method,path,token,payload=None):
        self.calls.append((method,path,payload))
        if path=='/repos/'+m.REPOSITORY:return{'full_name':m.REPOSITORY,'private':self.private,'has_pages':False}
        if path.endswith('/actions/workflows/'+m.WORKFLOW_FILE):return{'id':7,'name':m.WORKFLOW,'path':'.github/workflows/'+m.WORKFLOW_FILE}
        if '/actions/runs/'in path:return next(r for r in self.runs if r['id']==int(path.rsplit('/',1)[1]))
        if '/actions/workflows/7/runs?'in path:return{'workflow_runs':self.runs}
        if '/issues?'in path:return self.issues
        if path.endswith('/issues')and method=='POST':
            if self.post_timeout:raise m.WatchdogError('API_NETWORK_ERROR')
            return{'number':42}
        raise AssertionError('Unexpected request '+path)
    def posts(self):return [c for c in self.calls if c[0]=='POST']


def invoke(client,identifier=2,**kwargs):
    return m.inspect_event({'workflow_run':{'id':identifier,'name':m.WORKFLOW}},m.REPOSITORY,'fake',client=client,**kwargs)


class WatchdogTests(unittest.TestCase):
    def test_two_failures_create_one_safe_private_issue(self):
        client=Client([run(2),run(1)]);result=invoke(client)
        self.assertEqual(result['status'],'NOTIFIED');self.assertEqual(len(client.posts()),1)
        self.assertFalse(result['google_queries_executed']);self.assertFalse(result['state_write_required'])
        body=client.posts()[0][2]['body'];self.assertIn('official GitHub Actions',body);self.assertIn('/actions/runs/1',body);self.assertIn('/actions/runs/2',body)

    def test_success_breaks_consecutive_failures(self):
        client=Client([run(3),run(2,'success'),run(1)])
        self.assertEqual(invoke(client,3)['status'],'NO_CONSECUTIVE_FAILURES');self.assertFalse(client.posts())

    def test_unknown_conclusion_not_inferred_failure(self):
        client=Client([run(2),run(1,None)])
        self.assertEqual(invoke(client)['status'],'NO_CONSECUTIVE_FAILURES');self.assertFalse(client.posts())

    def test_timed_out_and_cancelled_are_recorded_failures(self):
        client=Client([run(2,'timed_out'),run(1,'cancelled')])
        self.assertEqual(invoke(client)['status'],'NOTIFIED')

    def test_existing_open_issue_deduplicates_unchanged_failures(self):
        runs=[run(3),run(2),run(1)];value=m.incident(runs,True,7)
        issue={'number':4,'state':'open','body':'<!-- geo-index-watchdog:'+value['fingerprint']+' -->'}
        client=Client(runs,[issue]);result=invoke(client,3)
        self.assertEqual(result['status'],'ALREADY_NOTIFIED');self.assertFalse(client.posts())

    def test_closed_issue_does_not_repeat_before_new_healthy_run(self):
        runs=[run(2),run(1)];value=m.incident(runs,True,7)
        client=Client(runs,[{'number':4,'state':'closed','body':'<!-- geo-index-watchdog:'+value['fingerprint']+' -->'}])
        self.assertEqual(invoke(client)['status'],'ALREADY_NOTIFIED');self.assertFalse(client.posts())

    def test_later_callback_without_issue_does_not_blindly_post(self):
        client=Client([run(3),run(2),run(1)])
        result=invoke(client,3);self.assertEqual(result['status'],'DELIVERY_UNCONFIRMED_REQUIRES_REVIEW');self.assertFalse(client.posts())

    def test_rerun_of_eligible_callback_does_not_blindly_post(self):
        client=Client([run(2),run(1)])
        self.assertEqual(invoke(client,watchdog_attempt=2)['status'],'DELIVERY_UNCONFIRMED_REQUIRES_REVIEW');self.assertFalse(client.posts())

    def test_post_timeout_attempted_only_once(self):
        client=Client([run(2),run(1)],post_timeout=True);result=invoke(client)
        self.assertEqual(result['status'],'DELIVERY_UNCERTAIN_REQUIRES_REVIEW');self.assertEqual(len(client.posts()),1)

    def test_remote_success_after_timeout_reconciles_on_later_callback(self):
        first=Client([run(2),run(1)],post_timeout=True);result=invoke(first)
        marker=result['incident']['fingerprint'];issue={'number':10,'state':'open','body':'<!-- geo-index-watchdog:'+marker+' -->'}
        later=Client([run(3),run(2),run(1)],[issue])
        self.assertEqual(invoke(later,3)['status'],'ALREADY_NOTIFIED');self.assertFalse(later.posts());self.assertEqual(len(first.posts()),1)

    def test_healthy_completion_starts_a_new_incident_identity(self):
        prior=m.incident([run(2),run(1)],True,7)
        current=Client([run(5),run(4),run(3,'success'),run(2),run(1)])
        result=invoke(current,5);self.assertEqual(result['status'],'NOTIFIED');self.assertNotEqual(result['incident']['fingerprint'],prior['fingerprint']);self.assertEqual(result['incident']['prior_healthy']['id'],3)

    def test_public_repository_denied_before_history_or_post(self):
        client=Client([run(2),run(1)],private=False)
        with self.assertRaises(m.WatchdogError)as error:invoke(client)
        self.assertEqual(error.exception.code,'PRIVATE_STORAGE_REQUIRED');self.assertEqual(len(client.calls),1)

    def test_other_workflow_is_skipped_and_watchdog_cannot_loop(self):
        client=Client([run(2),run(1)])
        result=m.inspect_event({'workflow_run':{'id':2,'name':'GEO Lab — Google Index Monitor Watchdog'}},m.REPOSITORY,'fake',client=client)
        self.assertEqual(result['status'],'SKIPPED_OTHER_WORKFLOW');self.assertEqual(len(client.calls),1)

    def test_wrong_branch_or_head_repository_or_pr_event_skipped(self):
        variants=[{'head_branch':'feature'},{'event':'pull_request'},{'head_repository':{'full_name':'other/fork','private':True}}]
        for changes in variants:
            client=Client([run(2,**changes),run(1)])
            self.assertEqual(invoke(client)['status'],'SKIPPED_UNAPPROVED_RUN');self.assertFalse(client.posts())

    def test_get_bounded_retry_and_post_single_attempt(self):
        calls=[]
        def opener(req,**kwargs):calls.append(req.get_method());raise URLError('must not log private raw text')
        with self.assertRaises(m.WatchdogError)as error:m.github('POST','/repos/'+m.REPOSITORY+'/issues','fake',{},opener=opener,sleep=lambda _:self.fail('No POST retry'))
        self.assertEqual(calls,['POST']);self.assertNotIn('private raw',str(error.exception))
        calls.clear()
        with self.assertRaises(m.WatchdogError):m.github('GET','/repos/'+m.REPOSITORY,'fake',opener=opener,sleep=lambda _:None)
        self.assertEqual(calls,['GET']*3)

    def test_no_google_credential_or_endpoint_in_workflow_execution(self):
        client=Client([run(2),run(1)]);invoke(client)
        self.assertTrue(all(path.startswith('/repos/'+m.REPOSITORY)for _,path,_ in client.calls))
        template=(Path(__file__).resolve().parents[1]/'templates/google-index-monitor-watchdog.yml').read_text()
        self.assertNotIn('GOOGLE_',template);self.assertIn('contents: read',template);self.assertIn('actions: read',template);self.assertIn('issues: write',template);self.assertNotIn('contents: write',template);self.assertIn('ref: main',template)


if __name__=='__main__':unittest.main()
