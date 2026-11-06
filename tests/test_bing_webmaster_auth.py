"""Isolated Bing initial OAuth/Keychain/Secret tests; no live authorization."""
import ctypes
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlencode, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import bing_webmaster_auth as m

REDIRECT = 'http://127.0.0.1:54963/oauth2callback'


def credential(**changes):
    return {'type': 'authorized_user', 'client_id': 'fixture-client',
            'client_secret': 'fixture-secret', 'refresh_token': 'fixture-refresh',
            'scopes': [m.READ_SCOPE], 'token_uri': m.TOKEN_ENDPOINT,
            'scope_source': 'token_response', **changes}


def client(**changes):
    return {'client_id': 'fixture-client', 'client_secret': 'fixture-secret',
            'redirect_uri': REDIRECT, **changes}


class Transport:
    def __init__(self, value): self.value=value; self.calls=[]
    def __call__(self,*args):
        self.calls.append(args)
        if isinstance(self.value,Exception): raise self.value
        return self.value


def token_response(**changes):
    return 200, {}, {'access_token': 'fixture-access', 'refresh_token': 'fixture-refresh',
                     'token_type': 'Bearer', 'scope': 'Webmaster.read', **changes}


def invoke_handler(handler,path,host='127.0.0.1:54963'):
    instance=object.__new__(handler);instance.path=path;instance.headers={'Host':host}
    instance.wfile=io.BytesIO();statuses=[];headers=[]
    instance.send_response=statuses.append
    instance.send_header=lambda *args:headers.append(args)
    instance.end_headers=lambda:None
    instance.do_GET()
    return statuses,headers,instance.wfile.getvalue()


class ClientAndCallbackTests(unittest.TestCase):
    def test_fixed_exact_loopback_redirect_only(self):
        self.assertEqual(m.validate_redirect(REDIRECT),54963)
        for value in ('https://127.0.0.1:54963/oauth2callback',
                      'http://localhost:54963/oauth2callback','http://[::1]:54963/oauth2callback',
                      'http://127.0.0.1/oauth2callback','http://127.0.0.1:0/oauth2callback',
                      'http://127.0.0.1:80/oauth2callback','http://127.0.0.1:54963/other',
                      REDIRECT+'/',REDIRECT+'?q=1',REDIRECT+'#fragment',
                      'http://user:secret@127.0.0.1:54963/oauth2callback'):
            with self.assertRaises(m.BingAuthError):m.validate_redirect(value)

    def test_private_client_permissions_and_official_endpoints(self):
        with tempfile.TemporaryDirectory()as folder:
            path=Path(folder)/'client.json';path.write_text(json.dumps(client()));path.chmod(0o600)
            self.assertEqual(m.load_client(path),client())
            path.chmod(0o644)
            with self.assertRaisesRegex(m.BingAuthError,'PERMISSIONS'):m.load_client(path)
            path.chmod(0o600)
            for field in ('auth_uri','token_uri'):
                path.write_text(json.dumps(client(**{field:'https://collector.invalid/'})))
                with self.assertRaisesRegex(m.BingAuthError,'UNTRUSTED'):m.load_client(path)

    def test_missing_malformed_public_and_symlink_client_rejected(self):
        with self.assertRaisesRegex(m.BingAuthError,'PRIVATE_CLIENT_FILE'):m.load_client(m.ROOT/'anything.json')
        with tempfile.TemporaryDirectory()as folder:
            path=Path(folder)/'client.json';path.write_text('{private-secret');path.chmod(0o600)
            with self.assertRaises(m.BingAuthError)as caught:m.load_client(path)
            self.assertNotIn('private-secret',str(caught.exception))
            path.write_text(json.dumps({'client_id':'fixture'}))
            with self.assertRaisesRegex(m.BingAuthError,'INCOMPLETE'):m.load_client(path)
            link=Path(folder)/'link.json';link.symlink_to(path)
            with self.assertRaisesRegex(m.BingAuthError,'PRIVATE_CLIENT'):m.load_client(link)

    def test_state_is_mandatory_exact_single_and_not_optional_on_errors(self):
        state='strong-state-value'
        bad_queries=({'code':'private-code'}, {'code':'private-code','state':'wrong'},
                     {'code':'private-code','state':['strong-state-value','strong-state-value']},
                     {'error':'access_denied'}, {'code':'private-code','state':''})
        for values in bad_queries:
            result=m.callback_result('/oauth2callback?'+urlencode(values,doseq=True),state)
            self.assertFalse(result['ok']);self.assertNotIn('code',result)
            self.assertNotIn('private-code',json.dumps(result))
        result=m.callback_result('/oauth2callback?code=private-code&state='+state,state)
        self.assertTrue(result['ok']);self.assertEqual(result['code'],'private-code')

    def test_callback_path_duplicates_mixed_results_and_controls_are_rejected(self):
        state='state'
        for path in ('/wrong?code=private-code&state=state',
                     '//foreign/anything?code=private-code&state=state',
                     '/oauth2callback?code=a&code=b&state=state',
                     '/oauth2callback?code=a&error=denied&state=state',
                     '/oauth2callback?code=%0Avalue&state=state',
                     '/oauth2callback?code=a&state=state#fragment'):
            self.assertFalse(m.callback_result(path,state)['ok'])
        result=m.callback_result('/oauth2callback?error=provider-private-reason&state=state',state)
        self.assertEqual(result['error'],'OWNER_AUTHORIZATION_DECLINED')
        self.assertNotIn('provider-private',json.dumps(result))

    def test_handler_rejects_host_logs_nothing_and_never_echoes_code(self):
        outcome={};rejections=[];handler=m.callback_handler('state',54963,outcome,rejections)
        statuses,headers,body=invoke_handler(handler,'/oauth2callback?code=private-code&state=state','evil.invalid')
        self.assertEqual(statuses,[400]);self.assertEqual(outcome,{})
        self.assertEqual(rejections,['INVALID_CALLBACK_HOST'])
        statuses,headers,body=invoke_handler(handler,'/oauth2callback?code=private-code&state=state')
        self.assertEqual(statuses,[200]);self.assertEqual(outcome,{'code':'private-code'})
        self.assertNotIn(b'private-code',body)
        self.assertIn(('Cache-Control','no-store'),headers)
        self.assertIn(('Referrer-Policy','no-referrer'),headers)
        with patch('sys.stderr',new_callable=io.StringIO)as errors:
            handler.log_message(None,'private callback %s','private-code')
            self.assertEqual(errors.getvalue(),'')

    def test_consent_url_file_private_and_never_in_public_checkout(self):
        with tempfile.TemporaryDirectory()as folder:
            path=Path(folder)/'url.txt';path.write_text('old');path.chmod(0o644)
            self.assertEqual(m.write_consent_url(path,'https://official.invalid/?state=private-state'),path.resolve())
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertIn('private-state',path.read_text())
        with self.assertRaisesRegex(m.BingAuthError,'PRIVATE_CONSENT'):m.write_consent_url(m.ROOT/'consent.txt','url')


class ExchangeTests(unittest.TestCase):
    def test_code_exchange_is_single_official_post_without_credential_in_url(self):
        transport=Transport(token_response())
        value=m.exchange_code(client(),'fixture-code',requester=transport)
        method,url,headers,body,timeout=transport.calls[0]
        self.assertEqual((method,url),('POST',m.TOKEN_ENDPOINT))
        params=parse_qs(body.decode());self.assertEqual(params['grant_type'],['authorization_code'])
        self.assertEqual(params['redirect_uri'],[REDIRECT]);self.assertEqual(params['code'],['fixture-code'])
        self.assertNotIn('fixture-secret',url);self.assertNotIn('access_token',value)
        self.assertEqual(value['scopes'],[m.READ_SCOPE]);self.assertEqual(value['scope_source'],'token_response')

    def test_missing_response_scope_records_requested_unchanged_provenance(self):
        payload=token_response()[2];payload.pop('scope')
        result=m.exchange_code(client(),'code',requester=Transport((200,{},payload)))
        self.assertEqual(result['scope_source'],'requested_scope_unchanged_per_oauth_response')

    def test_broader_contradictory_missing_refresh_and_invalid_token_type_rejected(self):
        for payload in (token_response(scope='Webmaster.manage')[2],
                        token_response(scopes=['Webmaster.manage'])[2],
                        token_response(refresh_token=None)[2],token_response(token_type='Basic')[2]):
            with self.assertRaises(m.BingAuthError):m.exchange_code(client(),'code',requester=Transport((200,{},payload)))

    def test_network_and_http_errors_single_attempt_and_safe(self):
        for response in (URLError('private-code fixture-secret'),(400,{}, {'error_description':'private'}),
                         (429,{},{}),(503,{},{})):
            transport=Transport(response)
            with self.assertRaises(m.BingAuthError)as caught:m.exchange_code(client(),'private-code',requester=transport)
            self.assertEqual(len(transport.calls),1)
            self.assertNotIn('private-code',str(caught.exception));self.assertNotIn('fixture-secret',str(caught.exception))


class AuthorizationFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.client=self.root/'client.json';self.client.write_text(json.dumps(client()));self.client.chmod(0o600)
    def tearDown(self):self.temp.cleanup()

    def server_factory(self,announced,paths):
        owner=self
        class Server:
            def __init__(self,address,handler):self.address=address;self.handler=handler;self.closed=False;self.timeout=None;owner.server=self
            def handle_request(self):
                state=parse_qs(urlsplit(announced[0]).query)['state'][0]
                path=paths.pop(0)(state)
                invoke_handler(self.handler,path)
            def server_close(self):self.closed=True
        return Server

    def test_fixed_port_strong_state_readonly_and_no_invented_pkce(self):
        announced=[];transport=Transport(token_response());ticks=iter([0,0])
        result=m.authorize(self.client,announce=announced.append,
            server_factory=self.server_factory(announced,[lambda state:'/oauth2callback?'+urlencode({'code':'code','state':state})]),
            requester=transport,monotonic=lambda:next(ticks))
        values=parse_qs(urlsplit(announced[0]).query)
        self.assertEqual(self.server.address,('127.0.0.1',54963));self.assertTrue(self.server.closed)
        self.assertGreaterEqual(len(values['state'][0]),40)
        self.assertEqual(values['scope'],[m.READ_SCOPE]);self.assertEqual(values['redirect_uri'],[REDIRECT])
        self.assertNotIn('code_challenge',values);self.assertNotIn('client_secret',values)
        self.assertEqual(result['refresh_token'],'fixture-refresh')

    def test_invalid_state_then_valid_callback_can_complete_without_weakening(self):
        announced=[];transport=Transport(token_response());ticks=iter([0,0,0])
        result=m.authorize(self.client,announce=announced.append,
            server_factory=self.server_factory(announced,[lambda state:'/oauth2callback?code=evil&state=wrong',lambda state:'/oauth2callback?'+urlencode({'code':'good','state':state})]),
            requester=transport,monotonic=lambda:next(ticks))
        self.assertEqual(len(transport.calls),1)
        self.assertEqual(parse_qs(transport.calls[0][3].decode())['code'],['good'])

    def test_missing_provider_state_stops_without_exchange_and_closes_port(self):
        announced=[];transport=Transport(token_response());ticks=iter([0,0,2])
        with self.assertRaisesRegex(m.BingAuthError,'STATE_NOT_RETURNED'):
            m.authorize(self.client,timeout=1,announce=announced.append,
                server_factory=self.server_factory(announced,[lambda state:'/oauth2callback?code=private-code']),
                requester=transport,monotonic=lambda:next(ticks))
        self.assertFalse(transport.calls);self.assertTrue(self.server.closed)

    def test_owner_denial_with_valid_state_exchanges_nothing(self):
        announced=[];transport=Transport(token_response());ticks=iter([0,0])
        with self.assertRaisesRegex(m.BingAuthError,'OWNER_AUTHORIZATION_DECLINED'):
            m.authorize(self.client,announce=announced.append,
                server_factory=self.server_factory(announced,[lambda state:'/oauth2callback?'+urlencode({'error':'access_denied','state':state})]),
                requester=transport,monotonic=lambda:next(ticks))
        self.assertFalse(transport.calls)

    def test_private_destination_required_and_no_port_fallback(self):
        with self.assertRaisesRegex(m.BingAuthError,'DESTINATION_REQUIRED'):m.authorize(self.client)
        def unavailable(*args):raise OSError('private bind diagnostic')
        with self.assertRaisesRegex(m.BingAuthError,'PORT_UNAVAILABLE'):
            m.authorize(self.client,announce=lambda _:None,server_factory=unavailable)


class FakeKeychain:
    def __init__(self,found=-25300,value=None):
        self.found=found;self.calls=[];self.buffer=ctypes.create_string_buffer(value or b'{}')
    def SecKeychainFindGenericPassword(self,_,slen,service,alen,account,length,data,item):
        self.calls.append(('find',service,account))
        if self.found==0:
            if length is not None:length._obj.value=len(self.buffer.value)
            if data is not None:data._obj.value=ctypes.addressof(self.buffer)
            if item is not None:item._obj.value=7
        return self.found
    def SecKeychainAddGenericPassword(self,_,slen,service,alen,account,vlen,value,item):
        self.calls.append(('add',service,account,value));return 0
    def SecKeychainItemModifyAttributesAndData(self,item,_,vlen,value):
        self.calls.append(('modify',value));return 0
    def SecKeychainItemFreeContent(self,_,data):self.calls.append(('free',));return 0


class KeychainAndGitHubTests(unittest.TestCase):
    def test_native_keychain_add_and_update_use_separate_bing_identity(self):
        for found,expected in ((-25300,'add'),(0,'modify')):
            api=FakeKeychain(found=found);released=[]
            m.keychain_save(credential(),api_factory=lambda:api,releaser=lambda ref:released.append(ref.value))
            self.assertEqual(api.calls[0],('find',b'geo-lab-bing-webmaster',b'monitor-readonly'))
            self.assertEqual(api.calls[1][0],expected);self.assertEqual(len(released),1)

    def test_keychain_load_frees_native_buffer_and_validates_scope(self):
        api=FakeKeychain(found=0,value=json.dumps(credential()).encode())
        self.assertEqual(m.keychain_load(api_factory=lambda:api)['scopes'],[m.READ_SCOPE])
        self.assertEqual(api.calls[-1],('free',))
        api=FakeKeychain(found=0,value=b'{private malformed')
        with self.assertRaises(m.BingAuthError)as caught:m.keychain_load(api_factory=lambda:api)
        self.assertNotIn('private',str(caught.exception));self.assertEqual(api.calls[-1],('free',))
        with self.assertRaisesRegex(m.BingAuthError,'AUTH_REQUIRED'):m.keychain_load(api_factory=lambda:FakeKeychain())

    def test_invalid_scope_never_reaches_keychain(self):
        calls=[]
        with self.assertRaises(m.BingAuthError):m.keychain_save(credential(scopes=['Webmaster.manage']),api_factory=lambda:calls.append('called'))
        self.assertFalse(calls)

    def test_github_exact_private_repository_and_stdin_only(self):
        calls=[]
        def runner(argv,**kwargs):
            calls.append((argv,kwargs))
            body=json.dumps({'private':True,'has_pages':False,'full_name':m.REPOSITORY})if'api'in argv else''
            return subprocess.CompletedProcess(argv,0,body,'')
        result=m.install_github_secret(credentials=credential(),runner=runner)
        self.assertTrue(result['configured']);self.assertEqual(result['secret_name'],'BING_OAUTH_CREDENTIALS')
        self.assertEqual(len(calls),2)
        self.assertIn('fixture-refresh',calls[1][1]['input'])
        self.assertNotIn('fixture-refresh',' '.join(calls[1][0]));self.assertNotIn('--body',calls[1][0])
        self.assertNotIn('fixture-refresh',json.dumps(result))

    def test_public_wrong_repo_pages_or_failed_check_never_sets_secret(self):
        with self.assertRaisesRegex(m.BingAuthError,'UNAPPROVED'):
            m.install_github_secret('other/private',credentials=credential(),runner=lambda *a,**k:self.fail('runner called'))
        for metadata in ({'private':False,'has_pages':False,'full_name':m.REPOSITORY},
                         {'private':True,'has_pages':True,'full_name':m.REPOSITORY},
                         {'private':True,'has_pages':False,'full_name':'wrong/repo'}):
            calls=[]
            def runner(argv,**kwargs):calls.append(argv);return subprocess.CompletedProcess(argv,0,json.dumps(metadata),'')
            with self.assertRaises(m.BingAuthError):m.install_github_secret(credentials=credential(),runner=runner)
            self.assertEqual(len(calls),1)

    def test_safe_check_never_returns_access_or_refresh_values(self):
        transport=Transport((200,{}, {'access_token':'fixture-access','token_type':'Bearer'}))
        result=m.check_monitor_credential(credentials=credential(),requester=transport)
        self.assertEqual(result['status'],'TOKEN_REFRESH_SUCCEEDED')
        self.assertNotIn('fixture-access',json.dumps(result));self.assertNotIn('fixture-refresh',json.dumps(result))

    def test_cli_authorize_output_contains_no_url_state_code_or_credentials(self):
        def authorize(*args,**kwargs):kwargs['announce']('https://official.invalid/?state=private-state');return credential()
        with patch.object(m,'authorize',side_effect=authorize),patch.object(m,'keychain_save'),patch('sys.stdout',new_callable=io.StringIO)as output:
            status=m.main(['authorize','--client-file','/private/client.json','--url-file','/private/url.txt'])
        self.assertEqual(status,0)
        for secret in ('private-state','official.invalid','fixture-secret','fixture-refresh'):
            self.assertNotIn(secret,output.getvalue())
        self.assertIn('AUTHORIZED',output.getvalue())


if __name__=='__main__':unittest.main()
