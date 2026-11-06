"""Synthetic Bing transport and ledger behavior; not live Bing evidence."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

spec = importlib.util.spec_from_file_location('discoverability_bing', Path(__file__).resolve().parents[1]/'scripts/discoverability_bing.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
STAMP = '2026-11-05T08:00:00+00:00'


def setUpModule():
    global no_real_sleep
    no_real_sleep = patch.object(m.time, 'sleep', lambda _: None)
    no_real_sleep.start()


def tearDownModule():
    no_real_sleep.stop()


class Transport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers, body))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def ok(value):
    return 200, {}, {'d': value}


def feed(**values):
    return {'Url': m.SITEMAP, 'Status': 'Success', 'Submitted': '/Date(1793865600000+0800)/',
            'LastCrawled': '/Date(1793865600000+0800)/', **values}


class ClassificationTests(unittest.TestCase):
    def test_is_page_and_http_do_not_establish_index_membership(self):
        for value in (True, False):
            result = m.classify_url_info({'d': {'IsPage': value, 'HttpStatus': 200,
                'DocumentSize': 100, 'IsIndexed': True}})
            self.assertEqual(result['index_status'], 'UNKNOWN')
            self.assertEqual(result['lifecycle'], 'UNKNOWN')

    def test_dates_keep_raw_values_and_do_not_double_apply_offset(self):
        raw = '/Date(1793865600000+0800)/'
        result = m.classify_url_info({'d': {'DiscoveryDate': raw, 'LastCrawledDate': raw}})
        self.assertEqual(result['last_crawl_time'], '2026-11-05T08:00:00+00:00')
        self.assertEqual(result['raw_last_crawled_date'], raw)
        self.assertEqual(result['lifecycle'], 'CRAWLED')
        self.assertEqual(result['index_status'], 'UNKNOWN')

    def test_missing_default_and_naive_dates_remain_unknown(self):
        for value in (None, '', '/Date(-62135596800000)/', '/Date(0)/',
                      '0001-01-01T00:00:00Z', '2026-11-05T08:00:00', 'garbage'):
            self.assertIsNone(m.normalize_bing_date(value))
        result = m.classify_url_info({'d': {'DiscoveryDate': '2026-11-04T00:00:00Z'}})
        self.assertEqual(result['lifecycle'], 'DISCOVERED')
        self.assertEqual(result['index_status'], 'UNKNOWN')

    def test_out_of_property_alias_and_traversal_rejected(self):
        for url in ('https://example.org/', m.PROPERTY+'index.html', m.PROPERTY+'%2e%2e/private',
                    m.PROPERTY+'?x=1', m.PROPERTY+'#section', 'https://helen-bird.github.io/other/'):
            with self.assertRaises(ValueError):
                m.canonical_guard(url)
        with self.assertRaises(ValueError):
            m.inspect_urls([m.PROPERTY, m.PROPERTY])


class ClientTests(unittest.TestCase):
    def test_absent_auth_records_all_seventy_unknown_without_calls(self):
        transport = Transport([])
        entries = [m.PROPERTY] + [m.PROPERTY+'evidence/'+str(i)+'.html' for i in range(69)]
        result = m.inspect_urls(entries, m.BingClient(requester=transport), STAMP)
        self.assertEqual(len(result['results']), 70)
        self.assertEqual(result['counts'], {'INDEXED': 0, 'NOT_INDEXED': 0, 'UNKNOWN': 70})
        self.assertEqual(result['api_requests_attempted'], 0)
        self.assertTrue(all(r['query_status'] == 'AUTH_REQUIRED' for r in result['results']))
        self.assertFalse(transport.calls)

    def test_oauth_readonly_header_and_fixed_query_scope(self):
        transport = Transport([ok({'IsPage': True})])
        result = m.BingClient('synthetic-token', requester=transport).get_url_info(m.PROPERTY)
        self.assertTrue(result['ok'])
        method, url, headers, body = transport.calls[0]
        self.assertEqual(urlsplit(url).netloc, 'www.bing.com')
        self.assertEqual(headers['Authorization'], 'Bearer synthetic-token')
        self.assertEqual(parse_qs(urlsplit(url).query)['siteUrl'], [m.PROPERTY])
        self.assertNotIn('apikey', url)
        self.assertIsNone(body)

    def test_api_key_not_called_readonly_and_no_secret_in_returned_records(self):
        secret = 'synthetic-api-secret'
        transport = Transport([ok({'Url': m.PROPERTY, 'apiKey': secret, 'echo': secret})])
        client = m.BingClient(api_key=secret, requester=transport)
        result = client.get_url_info(m.PROPERTY)
        self.assertFalse(client.authentication['readonly_scoped'])
        self.assertNotIn(secret, json.dumps(result))
        self.assertEqual(urlsplit(transport.calls[0][1]).netloc, 'ssl.bing.com')
        self.assertEqual(parse_qs(urlsplit(transport.calls[0][1]).query)['apikey'], [secret])

    def test_401_and_403_are_distinct_and_not_retried(self):
        for status, category in ((401, 'AUTH_REQUIRED'), (403, 'PERMISSION_DENIED')):
            transport = Transport([(status, {}, {'error': 'private-value'})])
            result = m.BingClient('token', requester=transport).get_user_sites()
            self.assertEqual(result['query_status'], category)
            self.assertEqual(len(transport.calls), 1)
            self.assertEqual(result['raw_response'], {'error': 'private-value'})

    def test_terminal_http_fault_preserves_diagnostics_with_credentials_removed(self):
        secret='synthetic/key+secret'
        payload={'ErrorCode':42,'ErrorMessage':'Unknown URL; credential '+secret,
                 'apiKey':secret,'nested':{'client_secret':'never-retain',
                 'request':'https://ssl.bing.com/api?siteUrl=geo&apiKey='+secret+'&url=answer',
                 'first':'https://ssl.bing.com/api?apikey='+secret+'&url=answer',
                 'only':'https://ssl.bing.com/api?apikey='+secret,
                 'adjacent':'https://ssl.bing.com/api?apikey='+secret+'&apiKey='+secret+'&url=answer',
                 'encoded':'synthetic%2Fkey%2Bsecret'}}
        transport=Transport([(400,{},payload)])
        result=m.BingClient(api_key=secret,requester=transport).get_url_info(m.PROPERTY)
        self.assertFalse(result['ok']);self.assertEqual(result['query_status'],'ERROR')
        self.assertEqual(result['error'],{'category':'HTTP_ERROR','http_status':400,'provider_error_code':42})
        self.assertEqual(result['raw_response']['ErrorCode'],42)
        self.assertIn('Unknown URL',result['raw_response']['ErrorMessage'])
        self.assertEqual(result['raw_response']['nested']['request'],'https://ssl.bing.com/api?siteUrl=geo&url=answer')
        self.assertEqual(result['raw_response']['nested']['first'],'https://ssl.bing.com/api?url=answer')
        self.assertEqual(result['raw_response']['nested']['only'],'https://ssl.bing.com/api')
        self.assertEqual(result['raw_response']['nested']['adjacent'],'https://ssl.bing.com/api?url=answer')
        serialized=json.dumps(result)
        for forbidden in (secret,'never-retain','synthetic%2Fkey%2Bsecret','apiKey=','apikey='):
            self.assertNotIn(forbidden,serialized)
        self.assertEqual(len(transport.calls),1)

    def test_api_fault_with_success_http_remains_error_and_retains_safe_body(self):
        secret='synthetic-bearer-token'
        payload={'d':{'ErrorCode':7,'ErrorMessage':'URL unavailable; '+secret,
                      'Authorization':'Bearer '+secret,'url':'https://example.test/?access_token='+secret}}
        result=m.BingClient(secret,requester=Transport([(200,{},payload)])).get_url_info(m.PROPERTY)
        self.assertFalse(result['ok']);self.assertEqual(result['query_status'],'ERROR')
        self.assertEqual(result['error']['category'],'API_FAULT')
        self.assertEqual(result['raw_response']['d']['ErrorCode'],7)
        self.assertNotIn(secret,json.dumps(result))
        self.assertNotIn('Authorization',result['raw_response']['d'])
        self.assertNotIn('access_token=',json.dumps(result))
        self.assertNotIn('payload',result)

    def test_failed_url_body_never_becomes_index_or_crawl_evidence(self):
        payload={'d':{'ErrorCode':9,'ErrorMessage':'not available','IsPage':True,'LastCrawledDate':STAMP}}
        transport=Transport([ok([{'Url':m.PROPERTY}]),(400,{},payload),ok([])])
        snapshot=m.inspect_urls([m.PROPERTY],m.BingClient(api_key='synthetic-key',requester=transport),STAMP)
        row=snapshot['results'][0]
        self.assertEqual(row['raw_response'],payload)
        self.assertEqual(row['query_status'],'ERROR')
        self.assertEqual(row['index_status'],'UNKNOWN')
        self.assertEqual(row['lifecycle'],'UNKNOWN')
        self.assertIsNone(row['last_crawl_time'])
        self.assertFalse(snapshot['run_complete'])
        self.assertEqual(snapshot['run_status'],'PARTIAL_FAILURE')

    def test_429_stops_without_immediate_retry_and_preserves_retry_after(self):
        sleeps = []
        transport = Transport([(429, {'Retry-After': '9999'}, {})])
        client=m.BingClient('token', requester=transport, sleep=sleeps.append)
        result = client.get_feeds()
        self.assertEqual(result['query_status'], 'QUOTA_EXCEEDED')
        self.assertEqual(result['error']['retry_after'],'9999')
        self.assertEqual(sleeps, [])
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(client.get_url_info(m.PROPERTY)['query_status'],'NOT_QUERIED_QUOTA_BLOCKED')
        self.assertEqual(len(transport.calls),1)

    def test_provider_throttle_stops_batch_but_preserves_all_seventy_slots(self):
        for code in (4,5):
            with self.subTest(code=code):
                payload={'ErrorCode':code,'Message':'ERROR!!! '+('ThrottleUser'if code==4 else'ThrottleHost')}
                transport=Transport([ok([{'Url':m.PROPERTY}]),ok({'IsPage':True}),(400,{},payload)])
                sleeps=[]
                client=m.BingClient(api_key='synthetic-key',requester=transport,sleep=sleeps.append)
                urls=[m.PROPERTY]+[m.PROPERTY+'evidence/'+str(i)+'.html'for i in range(69)]
                result=m.inspect_urls(urls,client,STAMP)
                self.assertEqual(len(result['results']),70)
                self.assertEqual(result['queries_succeeded'],1)
                self.assertEqual(result['api_requests_attempted'],3)
                self.assertEqual(result['urls_not_queried_after_block'],68)
                self.assertEqual(result['batch_stop']['raw_response'],payload)
                self.assertEqual(result['batch_stop']['operation'],'GetUrlInfo')
                self.assertEqual(result['run_status'],'QUOTA_EXCEEDED')
                self.assertFalse(result['run_complete'])
                self.assertEqual(result['counts'],{'INDEXED':0,'NOT_INDEXED':0,'UNKNOWN':70})
                self.assertEqual(result['results'][1]['query_status'],'QUOTA_EXCEEDED')
                for row in result['results'][2:]:
                    self.assertEqual(row['query_status'],'NOT_QUERIED_QUOTA_BLOCKED')
                    self.assertEqual(row['api_attempts'],[])
                    self.assertFalse(row['query_success'])
                    self.assertIsNone(row['raw_response'])
                self.assertEqual(result['sitemap_observation']['query_status'],'NOT_QUERIED_QUOTA_BLOCKED')
                self.assertEqual(sleeps,[5,5])
                self.assertEqual(len(transport.calls),3)
                self.assertNotIn('retry_after',result['batch_stop']['error'])

    def test_get_user_sites_throttle_prevents_all_url_and_feed_requests(self):
        payload={'ErrorCode':5,'Message':'ERROR!!! ThrottleHost'}
        transport=Transport([(200,{},payload)])
        snapshot=m.inspect_urls([m.PROPERTY,m.PROPERTY+'evidence/answer.html'],m.BingClient(api_key='synthetic-key',requester=transport),STAMP)
        self.assertEqual(snapshot['run_status'],'QUOTA_EXCEEDED')
        self.assertEqual(snapshot['api_requests_attempted'],1)
        self.assertEqual(snapshot['batch_stop']['operation'],'GetUserSites')
        self.assertEqual(snapshot['batch_stop']['raw_response'],payload)
        self.assertEqual(snapshot['urls_not_queried_after_block'],2)
        self.assertEqual(snapshot['sitemap_observation']['attempts'],[])
        self.assertEqual(len(transport.calls),1)

    def test_get_feeds_throttle_remains_failed_and_records_actual_final_response(self):
        payload={'ErrorCode':4,'Message':'ERROR!!! ThrottleUser'}
        transport=Transport([ok([{'Url':m.PROPERTY}]),ok({}),(400,{'Retry-After':'120'},payload)])
        snapshot=m.inspect_urls([m.PROPERTY],m.BingClient(api_key='synthetic-key',requester=transport),STAMP)
        self.assertEqual(snapshot['run_status'],'QUOTA_EXCEEDED')
        self.assertFalse(snapshot['run_complete'])
        self.assertEqual(snapshot['queries_succeeded'],1)
        self.assertEqual(snapshot['batch_stop']['operation'],'GetFeeds')
        self.assertEqual(snapshot['batch_stop']['error']['retry_after'],'120')
        self.assertEqual(snapshot['sitemap_observation']['raw_response'],payload)
        self.assertEqual(len(transport.calls),3)

    def test_official_auth_and_permission_fault_codes_stop_duplicate_requests(self):
        for code,status in ((3,'AUTH_REQUIRED'),(6,'PERMISSION_DENIED'),(13,'PERMISSION_DENIED'),(14,'PERMISSION_DENIED')):
            with self.subTest(code=code):
                payload={'ErrorCode':code,'Message':'provider fault'}
                transport=Transport([(400,{},payload)])
                snapshot=m.inspect_urls([m.PROPERTY,m.PROPERTY+'evidence/answer.html'],m.BingClient(api_key='synthetic-key',requester=transport),STAMP)
                self.assertEqual(snapshot['batch_stop']['query_status'],status)
                self.assertEqual(snapshot['run_status'],'AUTH_REQUIRED'if code==3 else'PARTIAL_FAILURE')
                self.assertEqual(snapshot['api_requests_attempted'],1)
                self.assertTrue(all(row['query_status']=='NOT_QUERIED_AUTH_BLOCKED'for row in snapshot['results']))
                self.assertEqual(len(transport.calls),1)

    def test_unknown_error_two_is_not_retried_or_reclassified(self):
        payload={'ErrorCode':2,'Message':'ERROR!!! UnknownError'}
        transport=Transport([ok([{'Url':m.PROPERTY}]),(400,{},payload),ok({}),ok([])])
        snapshot=m.inspect_urls([m.PROPERTY,m.PROPERTY+'evidence/answer.html'],m.BingClient(api_key='synthetic-key',requester=transport),STAMP)
        self.assertEqual(snapshot['results'][0]['query_status'],'ERROR')
        self.assertEqual(snapshot['results'][0]['raw_response'],payload)
        self.assertEqual(len(snapshot['results'][0]['api_attempts']),1)
        self.assertIsNone(snapshot['batch_stop'])
        self.assertEqual(snapshot['run_status'],'PARTIAL_FAILURE')
        self.assertEqual(len(transport.calls),4)

    def test_serial_pacing_applies_to_all_actual_requests_and_cannot_be_disabled(self):
        sleeps=[]
        client=m.BingClient(api_key='synthetic-key',requester=Transport([ok([{'Url':m.PROPERTY}]),ok({}),ok([])]),sleep=sleeps.append)
        snapshot=m.inspect_urls([m.PROPERTY],client,STAMP)
        self.assertEqual(sleeps,[5,5])
        self.assertEqual(snapshot['request_interval_seconds'],5)
        for interval in (0,1,4.9,61,True,'5',float('nan')):
            with self.assertRaisesRegex(ValueError,'BING_REQUEST_INTERVAL'):
                m.BingClient(api_key='synthetic-key',request_interval=interval)

    def test_long_or_date_server_retry_after_defers_remaining_batch_without_early_retry(self):
        for retry in ('120','Fri, 06 Nov 2026 18:00:00 GMT'):
            with self.subTest(retry=retry):
                sleeps=[]
                transport=Transport([ok([{'Url':m.PROPERTY}]),(503,{'Retry-After':retry},{'message':'busy'})])
                snapshot=m.inspect_urls([m.PROPERTY,m.PROPERTY+'evidence/answer.html'],m.BingClient(api_key='synthetic-key',requester=transport,sleep=sleeps.append),STAMP)
                self.assertEqual(len(transport.calls),2)
                self.assertEqual(sleeps,[5])
                self.assertEqual(snapshot['batch_stop']['error']['category'],'SERVER_ERROR')
                self.assertEqual(snapshot['batch_stop']['error']['retry_after'],retry)
                self.assertTrue(snapshot['batch_stop']['error']['retry_deferred'])
                self.assertEqual(snapshot['results'][1]['query_status'],'NOT_QUERIED_RETRY_DEFERRED')
                self.assertEqual(snapshot['results'][1]['api_attempts'],[])
                self.assertEqual(snapshot['sitemap_observation']['attempts'],[])
                self.assertEqual(snapshot['run_status'],'PARTIAL_FAILURE')

    def test_lowercase_retry_after_is_honored_without_early_or_later_host_request(self):
        sleeps=[]
        transport=Transport([ok([{'Url':m.PROPERTY}]),(503,{'retry-after':'120'},{'message':'busy'})])
        snapshot=m.inspect_urls([m.PROPERTY,m.PROPERTY+'evidence/answer.html'],m.BingClient(api_key='synthetic-key',requester=transport,sleep=sleeps.append),STAMP)
        self.assertEqual(len(transport.calls),2)
        self.assertEqual(sleeps,[5])
        self.assertEqual(snapshot['batch_stop']['error']['retry_after'],'120')
        self.assertTrue(snapshot['batch_stop']['error']['retry_deferred'])
        self.assertEqual(snapshot['results'][1]['query_status'],'NOT_QUERIED_RETRY_DEFERRED')
        self.assertEqual(snapshot['sitemap_observation']['attempts'],[])
        self.assertFalse(snapshot['run_complete'])

    def test_unknown_error_two_is_not_retried_even_with_server_http_status(self):
        payload={'ErrorCode':2,'Message':'ERROR!!! UnknownError'}
        transport=Transport([(503,{},payload)])
        result=m.BingClient(api_key='synthetic-key',requester=transport).get_url_info(m.PROPERTY)
        self.assertEqual(result['query_status'],'ERROR')
        self.assertEqual(result['error']['category'],'API_FAULT')
        self.assertEqual(result['raw_response'],payload)
        self.assertEqual(len(transport.calls),1)

    def test_transient_server_and_network_retry_without_raw_error(self):
        transport = Transport([URLError('private-token-in-url'), (503, {}, {}), ok([])])
        result = m.BingClient('token', requester=transport, sleep=lambda _: None).get_user_sites()
        self.assertTrue(result['ok'])
        self.assertEqual(len(transport.calls), 3)
        self.assertNotIn('private-token-in-url', json.dumps(result))

    def test_invalid_json_api_fault_and_missing_url_fields_are_errors(self):
        for payload in ({'_invalid_json': True}, {'d': {'ErrorCode': 5, 'ErrorMessage': 'private'}}, {'d': None}):
            transport = Transport([(200, {}, payload)])
            result = m.BingClient('token', requester=transport).get_url_info(m.PROPERTY)
            self.assertFalse(result['ok'])
            self.assertEqual(result['raw_response'], payload)

    def test_read_observations_are_separate_and_never_submit(self):
        transport = Transport([ok([{'Url': m.PROPERTY}]), ok({'IsPage': True, 'LastCrawledDate': STAMP}), ok([feed()])])
        result = m.inspect_urls([{'url': m.PROPERTY}], m.BingClient('token', requester=transport), STAMP)
        self.assertTrue(result['run_complete'])
        self.assertEqual(result['counts']['UNKNOWN'], 1)
        self.assertEqual(result['api_requests_attempted'], 3)
        self.assertTrue(result['sitemap_observation']['registered'])
        self.assertEqual(result['sitemap_observation']['last_crawl_time'], STAMP)
        self.assertTrue(all(call[0] == 'GET' for call in transport.calls))

    def test_duplicate_feed_rows_still_prove_registration(self):
        client = m.BingClient('token', requester=Transport([ok([feed(), feed()])]))
        result = m.sitemap_observation(client, STAMP)
        self.assertTrue(result['registered'])
        self.assertEqual(result['matching_feed_count'], 2)

    def test_absent_feed_and_failed_get_have_distinct_unknowns(self):
        for response, registered, status in ((ok([]), False, 'NOT_RETURNED'), ((403, {}, {}), None, 'UNKNOWN')):
            result = m.sitemap_observation(m.BingClient('token', requester=Transport([response])))
            self.assertIs(result['registered'], registered)
            self.assertEqual(result['registration_status'], status)

    def test_user_sites_observation_keeps_only_exact_property_and_matching_fields(self):
        matching = {'Url': m.PROPERTY, 'IsVerified': True, 'Permission': 'Owner'}
        private = {'Url': 'https://unrelated-private.example/', 'AccountMetadata': 'not-for-monitor'}
        for payload in ({'d': [matching, private], 'AccountMetadata': 'top-level-private'}, [matching, private]):
            transport = Transport([(200, {}, payload), ok({'IsPage': True}), ok([])])
            snapshot = m.inspect_urls([m.PROPERTY], m.BingClient('token', requester=transport), STAMP)
            observation = snapshot['site_access_observation']
            self.assertTrue(observation['filtered'])
            self.assertEqual(observation['matching_site_count'], 1)
            self.assertEqual(m.unwrap(observation['raw_response']), [matching])
            serialized = json.dumps(snapshot)
            self.assertNotIn('unrelated-private', serialized)
            self.assertNotIn('not-for-monitor', serialized)
            self.assertNotIn('top-level-private', serialized)

    def test_user_sites_filter_does_not_treat_parent_or_other_project_as_exact_property(self):
        transport = Transport([ok([{'Url': 'https://helen-bird.github.io/'},
                                  {'Url': 'https://helen-bird.github.io/other/'}]),
                               ok({'IsPage': False}), ok([])])
        snapshot = m.inspect_urls([m.PROPERTY], m.BingClient('token', requester=transport), STAMP)
        observation = snapshot['site_access_observation']
        self.assertEqual(observation['matching_site_count'], 0)
        self.assertEqual(observation['raw_response'], {'d': []})
        self.assertNotIn('https://helen-bird.github.io/other/', json.dumps(snapshot))

    def test_unexpected_scopes_and_multiple_credentials_rejected(self):
        with self.assertRaises(ValueError):
            m.BingClient('token', api_key='key')
        with self.assertRaises(ValueError):
            m.BingClient('token', scope='unrelated.scope')


class SubmissionTests(unittest.TestCase):
    def test_existing_imported_feed_never_posted_even_readonly(self):
        with tempfile.TemporaryDirectory() as folder:
            transport = Transport([ok([feed()]), ok([feed()])])
            client = m.BingClient('token', requester=transport)
            ledger = Path(folder)/'bing.json'
            for _ in range(2):
                result = m.submit_sitemap_once(client, ledger, checked_at=STAMP)
                self.assertEqual(result['submission_status'], 'ALREADY_REGISTERED')
            self.assertTrue(all(call[0] == 'GET' for call in transport.calls))

    def test_single_post_accepted_then_later_calls_are_get_only(self):
        with tempfile.TemporaryDirectory() as folder:
            transport = Transport([ok([]), ok(None), ok([feed()]), ok([feed()])])
            client = m.BingClient('token', scope=m.MANAGE_SCOPE, allow_write=True, requester=transport)
            ledger = Path(folder)/'bing.json'
            result = m.submit_sitemap_once(client, ledger, checked_at=STAMP)
            self.assertEqual(result['submission_status'], 'SUBMITTED')
            m.submit_sitemap_once(client, ledger, checked_at=STAMP)
            posts = [c for c in transport.calls if c[0] == 'POST']
            self.assertEqual(len(posts), 1)
            self.assertEqual(json.loads(posts[0][3]), {'siteUrl': m.PROPERTY, 'feedUrl': m.SITEMAP})
            self.assertEqual(ledger.stat().st_mode & 0o777, 0o600)

    def test_readonly_grant_cannot_submit_missing_feed(self):
        with tempfile.TemporaryDirectory() as folder:
            transport = Transport([ok([])])
            result = m.submit_sitemap_once(m.BingClient('token', allow_write=True, requester=transport), Path(folder)/'bing.json')
            self.assertEqual(result['submission_status'], 'WRITE_AUTHORIZATION_REQUIRED')
            self.assertEqual(len(transport.calls), 1)

    def test_post_timeout_and_empty_later_get_never_enable_repost(self):
        with tempfile.TemporaryDirectory() as folder:
            transport = Transport([ok([]), URLError('sensitive'), ok([])])
            client = m.BingClient('token', scope=m.MANAGE_SCOPE, allow_write=True, requester=transport)
            ledger = Path(folder)/'bing.json'
            self.assertEqual(m.submit_sitemap_once(client, ledger)['submission_status'], 'UNCERTAIN')
            self.assertEqual(m.submit_sitemap_once(client, ledger)['submission_status'], 'UNCERTAIN')
            self.assertEqual(sum(c[0] == 'POST' for c in transport.calls), 1)
            self.assertNotIn('sensitive', ledger.read_text())

    def test_started_attempt_reconciles_registration_without_attributing_cause(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = Path(folder)/'bing.json'
            ledger.write_text(json.dumps({'engine': 'bing', 'property': m.PROPERTY, 'sitemap_url': m.SITEMAP, 'events': [], 'submission_status': 'ATTEMPT_STARTED'}))
            transport = Transport([ok([feed()])])
            result = m.submit_sitemap_once(m.BingClient('token', requester=transport), ledger)
            self.assertEqual(result['submission_status'], 'REGISTERED_AFTER_UNCERTAIN_ATTEMPT')
            self.assertEqual(len(transport.calls), 1)

    def test_missing_authorization_never_submits_or_infers_indexing(self):
        with tempfile.TemporaryDirectory() as folder:
            result = m.submit_sitemap_once(m.BingClient(), Path(folder)/'bing.json')
            self.assertEqual(result['submission_status'], 'AUTH_REQUIRED')
            self.assertFalse(result['latest_observation']['query_success'])

    def test_public_or_symlink_ledger_rejected(self):
        with self.assertRaises(ValueError):
            m.submit_sitemap_once(m.BingClient(), m.ROOT/'forbidden-bing-ledger.json')
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'original.json'; target.write_text('{}')
            link = Path(folder)/'link.json'; link.symlink_to(target)
            with self.assertRaises(ValueError):
                m.submit_sitemap_once(m.BingClient(), link)
            self.assertEqual(target.read_text(), '{}')

    def test_corrupt_ledger_preserved_and_no_request(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'bing.json'; path.write_text('{broken')
            transport = Transport([])
            with self.assertRaises(ValueError):
                m.submit_sitemap_once(m.BingClient('token', requester=transport), path)
            self.assertEqual(path.read_text(), '{broken')
            self.assertFalse(transport.calls)


def credentials(**changes):
    return {'type': 'authorized_user', 'client_id': 'synthetic-client',
            'client_secret': 'synthetic-client-secret', 'refresh_token': 'synthetic-refresh',
            'scopes': [m.READ_SCOPE], **changes}


class OAuthRefreshTests(unittest.TestCase):
    def test_refresh_uses_official_post_body_and_returns_only_access_token(self):
        transport = Transport([(200, {}, {'access_token': 'ephemeral-access', 'token_type': 'Bearer'})])
        self.assertEqual(m.refresh_bing_oauth(credentials(), requester=transport), 'ephemeral-access')
        method, url, headers, body = transport.calls[0]
        self.assertEqual((method, url), ('POST', m.TOKEN_ENDPOINT))
        values = parse_qs(body.decode())
        self.assertEqual(values['grant_type'], ['refresh_token'])
        self.assertEqual(values['client_secret'], ['synthetic-client-secret'])
        self.assertNotIn('synthetic', url)
        self.assertEqual(headers['Content-Type'], 'application/x-www-form-urlencoded')

    def test_case_insensitive_exact_readonly_scope_and_same_refresh_are_accepted(self):
        grant = credentials(scopes=['webmaster.read'])
        transport = Transport([(200, {}, {'access_token': 'ephemeral', 'token_type': 'bearer',
                            'scope': 'WEBMASTER.READ', 'refresh_token': grant['refresh_token']})])
        self.assertEqual(m.refresh_bing_oauth(grant, requester=transport), 'ephemeral')

    def test_scope_string_and_env_json_are_supported_without_file_access(self):
        grant = credentials(); grant.pop('scopes'); grant['scope'] = 'Webmaster.read'
        with patch.dict(m.os.environ, {'BING_OAUTH_CREDENTIALS': json.dumps(grant)}, clear=True):
            transport = Transport([(200, {}, {'access_token': 'ephemeral', 'token_type': 'Bearer'})])
            self.assertEqual(m.refresh_bing_oauth(requester=transport), 'ephemeral')
        self.assertEqual(m.load_bing_oauth_from_env({'BING_OAUTH_CREDENTIALS': json.dumps(grant)}), grant)

    def test_absent_corrupt_env_and_non_authorized_user_are_safe_errors(self):
        for value, code in ((None, 'AUTH_REQUIRED'), ('{private-secret', 'INVALID_OAUTH_SECRET_JSON'),
                            ('[]', 'AUTHORIZED_USER_CREDENTIAL_REQUIRED')):
            with self.assertRaises(m.BingAuthError) as caught:
                m.load_bing_oauth_from_env({} if value is None else {'BING_OAUTH_CREDENTIALS': value})
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn('private-secret', str(caught.exception))

    def test_manage_extra_unspecified_and_conflicting_scopes_rejected_before_network(self):
        for grant in (credentials(scopes=['Webmaster.manage']), credentials(scopes=[]),
                      credentials(scopes=['Webmaster.read', 'unrelated']),
                      credentials(scope='Webmaster.manage')):
            transport = Transport([])
            with self.assertRaises(m.BingAuthError) as caught:
                m.refresh_bing_oauth(grant, requester=transport)
            self.assertEqual(caught.exception.code, 'EXACT_READONLY_SCOPE_REQUIRED')
            self.assertFalse(transport.calls)

    def test_foreign_token_uri_or_missing_secret_rejected_before_network(self):
        for grant in (credentials(token_uri='https://example.org/collect'), credentials(client_secret='')):
            transport = Transport([])
            with self.assertRaises(m.BingAuthError):
                m.refresh_bing_oauth(grant, requester=transport)
            self.assertFalse(transport.calls)

    def test_network_uncertainty_is_not_retried_and_error_contains_no_provider_text(self):
        transport = Transport([URLError('synthetic-refresh private-data')])
        with self.assertRaises(m.BingAuthError) as caught:
            m.refresh_bing_oauth(credentials(), requester=transport)
        self.assertEqual(caught.exception.code, 'TOKEN_REQUEST_UNCERTAIN_NO_RETRY')
        self.assertEqual(len(transport.calls), 1)
        self.assertNotIn('private-data', str(caught.exception))

    def test_429_server_and_invalid_grant_have_distinct_safe_categories_without_retry(self):
        for status, payload, code in ((429, {}, 'TOKEN_QUOTA_EXCEEDED'),
                 (503, {}, 'TOKEN_SERVER_ERROR_NO_RETRY'),
                 (400, {'error': 'invalid_grant', 'error_description': 'private'}, 'AUTH_EXPIRED'),
                 (403, {}, 'TOKEN_AUTH_REJECTED')):
            transport = Transport([(status, {}, payload)])
            with self.assertRaises(m.BingAuthError) as caught:
                m.refresh_bing_oauth(credentials(), requester=transport)
            self.assertEqual(caught.exception.code, code)
            self.assertEqual(len(transport.calls), 1)
            self.assertNotIn('private', str(caught.exception))

    def test_returned_manage_or_extra_scope_cannot_produce_access_token(self):
        for scope in ('Webmaster.manage', 'Webmaster.read unrelated', [], ''):
            transport = Transport([(200, {}, {'access_token': 'private-access', 'token_type': 'Bearer', 'scope': scope})])
            with self.assertRaises(m.BingAuthError) as caught:
                m.refresh_bing_oauth(credentials(), requester=transport)
            self.assertEqual(caught.exception.code, 'GRANTED_SCOPE_CHANGED')
            self.assertNotIn('private-access', str(caught.exception))

    def test_rotated_refresh_requires_secure_update_never_returns_new_secret(self):
        transport = Transport([(200, {}, {'access_token': 'private-access', 'token_type': 'Bearer',
                                        'refresh_token': 'new-private-refresh'})])
        with self.assertRaises(m.BingAuthError) as caught:
            m.refresh_bing_oauth(credentials(), requester=transport)
        self.assertEqual(caught.exception.code, 'ROTATION_REQUIRES_SECURE_SECRET_UPDATE')
        self.assertNotIn('private', str(caught.exception))
        self.assertEqual(len(transport.calls), 1)

    def test_invalid_token_type_missing_access_or_non_json_fail_safely(self):
        for payload in ({'_invalid_json': True}, None, {}, {'access_token': 'access', 'token_type': 'Basic'}):
            transport = Transport([(200, {}, payload)])
            with self.assertRaises(m.BingAuthError) as caught:
                m.refresh_bing_oauth(credentials(), requester=transport)
            self.assertEqual(caught.exception.code, 'INVALID_TOKEN_RESPONSE')


if __name__ == '__main__':
    unittest.main()
