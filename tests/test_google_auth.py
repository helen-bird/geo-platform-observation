"""Isolated Google OAuth/Sitemaps safety checks; no real account or network use."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.error import HTTPError, URLError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import google_search_console_auth as auth
import google_sitemap_submit as sitemap


def credential(scope=auth.READONLY_SCOPE):
    return {'type':'authorized_user','client_id':'fixture-client','client_secret':'fixture-client-secret','refresh_token':'fixture-refresh-value','token_uri':auth.TOKEN_URI,'scopes':[scope]}


class Response:
    def __init__(self,payload=None,status=200):self.payload=payload;self.status=status
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,*args):return b''if self.payload is None else json.dumps(self.payload).encode()


class Opener:
    def __init__(self,results):self.results=list(results);self.requests=[]
    def open(self,request,**kwargs):
        self.requests.append(request)
        result=self.results.pop(0)
        if isinstance(result,Exception):raise result
        return result


def http_error(status,payload=None):
    return HTTPError(sitemap.endpoint(),status,'Fixture error',{},io.BytesIO(json.dumps(payload or{}).encode()))


class AuthTests(unittest.TestCase):
    def test_monitor_rejects_broader_or_unspecified_scopes(self):
        self.assertEqual(auth.load_credentials_from_env({'GOOGLE_OAUTH_CREDENTIALS':json.dumps(credential())})['scopes'],[auth.READONLY_SCOPE])
        for scopes in([auth.WRITE_SCOPE],[auth.READONLY_SCOPE,auth.WRITE_SCOPE],[]):
            data=credential();data['scopes']=scopes
            with self.assertRaises(auth.AuthError):auth.validate_credentials(data,'monitor')

    def test_no_arbitrary_token_endpoint_or_service_account(self):
        data=credential();data['token_uri']='https://example.invalid/token'
        with self.assertRaisesRegex(auth.AuthError,'UNTRUSTED'):auth.refresh_access_token(data)
        data=credential();data['type']='service_account'
        with self.assertRaisesRegex(auth.AuthError,'UNSUPPORTED'):auth.validate_credentials(data)

    def test_current_downloaded_desktop_client_legacy_auth_uri_is_safe(self):
        with tempfile.TemporaryDirectory()as folder:
            p=Path(folder)/'client.json';p.write_text(json.dumps({'installed':{'client_id':'fixture','client_secret':'fixture-secret','auth_uri':'https://accounts.google.com/o/oauth2/auth','token_uri':auth.TOKEN_URI}}))
            self.assertEqual(auth.load_desktop_client(p)['client_id'],'fixture')
            p.write_text(json.dumps({'installed':{'client_id':'fixture','client_secret':'fixture-secret','auth_uri':'https://example.invalid/auth'}}))
            with self.assertRaisesRegex(auth.AuthError,'UNTRUSTED'):auth.load_desktop_client(p)

    def test_safe_credential_defaults_are_normalized(self):
        data=credential();data.pop('type');data.pop('token_uri')
        normalized=auth.validate_credentials(data);self.assertEqual(normalized['type'],'authorized_user');self.assertEqual(normalized['token_uri'],auth.TOKEN_URI)

    def test_refresh_uses_post_and_checks_actual_returned_scope(self):
        opener=Opener([Response({'access_token':'fixture-access','scope':auth.READONLY_SCOPE,'token_type':'Bearer'})])
        self.assertEqual(auth.refresh_access_token(credential(),opener=opener),'fixture-access')
        req=opener.requests[0];self.assertEqual(req.full_url,auth.TOKEN_URI);self.assertEqual(req.method,'POST');self.assertNotIn('fixture-refresh-value',req.full_url)
        opener=Opener([Response({'access_token':'fixture-access','scope':auth.WRITE_SCOPE})])
        with self.assertRaisesRegex(auth.AuthError,'GRANTED_SCOPE_CHANGED'):auth.refresh_access_token(credential(),opener=opener)

    def test_refresh_retry_is_bounded_and_does_not_leak_provider_description(self):
        opener=Opener([http_error(503),http_error(503),http_error(400,{'error':'invalid_grant','error_description':'fixture-refresh-value private'})]);delays=[]
        with self.assertRaises(auth.AuthError)as caught:auth.refresh_access_token(credential(),opener=opener,sleep=delays.append)
        self.assertEqual(caught.exception.code,'AUTH_EXPIRED');self.assertNotIn('fixture-refresh-value',str(caught.exception));self.assertEqual(delays,[2,4]);self.assertEqual(len(opener.requests),3)

    def test_github_secret_private_repo_and_stdin_only(self):
        calls=[]
        def runner(argv,**kwargs):
            calls.append((argv,kwargs));return subprocess.CompletedProcess(argv,0,'true\n'if'api'in argv else'','')
        result=auth.install_github_secret('example/private-monitor',credentials=credential(),runner=runner)
        self.assertTrue(result['configured']);self.assertEqual(len(calls),2)
        self.assertIn('fixture-refresh-value',calls[1][1]['input']);self.assertNotIn('fixture-refresh-value',' '.join(calls[1][0]))
        def public_runner(argv,**kwargs):return subprocess.CompletedProcess(argv,0,'false\n','')
        with self.assertRaisesRegex(auth.AuthError,'PRIVATE_MONITOR'):auth.install_github_secret('example/public',credentials=credential(),runner=public_runner)


class SitemapTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name);self.baseline=self.root/'baseline.json';self.baseline.write_text(json.dumps({'property':sitemap.PROPERTY,'captured_at':'2026-11-04T00:00:00+00:00'}));self.state=self.root/'state'
    def tearDown(self):self.temporary.cleanup()
    def manage(self,opener,action='submit'):
        return sitemap.manage_sitemap(baseline=self.baseline,state_dir=self.state,action=action,access_token='fixture-access',opener=opener,sleep=lambda _:None,public_validator=lambda:{'http_status':200,'sha256':'fixture','url_count':9})

    def test_baseline_is_mandatory_and_future_or_wrong_property_rejected(self):
        with self.assertRaises(sitemap.SitemapError):sitemap.baseline_guard(self.root/'missing.json')
        self.baseline.write_text(json.dumps({'property':sitemap.PROPERTY,'captured_at':'2999-01-01T00:00:00+00:00'}))
        with self.assertRaisesRegex(sitemap.SitemapError,'INVALID_BASELINE_TIME'):sitemap.baseline_guard(self.baseline)
        with self.assertRaisesRegex(sitemap.SitemapError,'UNEXPECTED'):sitemap.endpoint(site='https://example.invalid/')

    def test_submit_once_then_status_get_only(self):
        opener=Opener([http_error(404),Response(None),Response({'isPending':True})])
        result=self.manage(opener);self.assertEqual(result['submission_status'],'SUBMITTED');self.assertEqual([x.method for x in opener.requests],['GET','PUT','GET'])
        opener2=Opener([Response({'isPending':False,'lastDownloaded':'2026-11-04T01:00:00Z','errors':'0'})])
        result=self.manage(opener2);self.assertFalse(result['put_performed']);self.assertEqual(result['observation']['processing_state'],'READ_REPORTED');self.assertEqual([x.method for x in opener2.requests],['GET'])

    def test_preexisting_registration_does_not_skip_requested_updated_feed_submission(self):
        opener=Opener([Response({'isPending':False}),Response(None),Response({'isPending':True})]);result=self.manage(opener)
        self.assertEqual(result['submission_status'],'SUBMITTED');self.assertTrue(result['put_performed']);self.assertEqual([x.method for x in opener.requests],['GET','PUT','GET'])
        second=Opener([Response({'isPending':True})]);result=self.manage(second)
        self.assertFalse(result['put_performed']);self.assertEqual([x.method for x in second.requests],['GET'])

    def test_preexisting_resource_cannot_prove_an_uncertain_refresh_put_succeeded(self):
        opener=Opener([Response({'isPending':False}),URLError('fixture-network-failure')]);result=self.manage(opener)
        self.assertEqual(result['submission_status'],'UNCERTAIN')
        later=Opener([Response({'isPending':False})]);result=self.manage(later)
        self.assertEqual(result['submission_status'],'UNCERTAIN');self.assertFalse(result['put_performed']);self.assertEqual([x.method for x in later.requests],['GET'])

    def test_unknown_put_delivery_is_not_blindly_retried(self):
        opener=Opener([http_error(404),URLError('fixture-network-failure')]);result=self.manage(opener)
        self.assertEqual(result['submission_status'],'UNCERTAIN');self.assertEqual([x.method for x in opener.requests],['GET','PUT'])
        result=self.manage(Opener([http_error(404)]));self.assertFalse(result['put_performed']);self.assertEqual(result['submission_status'],'UNCERTAIN')
        result=self.manage(Opener([Response({'isPending':True})]));self.assertEqual(result['submission_status'],'RECONCILED_PRESENT');self.assertFalse(result['put_performed'])

    def test_permission_failure_cannot_submit_and_error_does_not_leave_private_dir(self):
        opener=Opener([http_error(403,{'error':{'errors':[{'reason':'insufficientPermissions'}]}})]);result=self.manage(opener)
        self.assertFalse(result['put_performed']);self.assertEqual(result['error'],'PERMISSION_DENIED');self.assertEqual([x.method for x in opener.requests],['GET'])
        with self.assertRaisesRegex(sitemap.SitemapError,'PRIVATE_STATE'):sitemap.private_state_dir(sitemap.ROOT/'private-state')

    def test_processing_evidence_and_auth_get_failure(self):
        self.assertEqual(sitemap.processing_state({'errors':'1','lastDownloaded':'2026-11-04T01:00:00Z'}),'PROCESSING_ERROR')
        self.assertEqual(sitemap.processing_state({'isPending':True}),'PENDING')
        self.assertEqual(sitemap.processing_state({}),'UNKNOWN')
        opener=Opener([http_error(401)]);result=self.manage(opener,'status');self.assertEqual(result['observation']['error'],'AUTH_REQUIRED');self.assertEqual(len(opener.requests),1)


if __name__=='__main__':unittest.main()
