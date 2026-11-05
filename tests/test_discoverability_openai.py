import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import unittest
from urllib.error import URLError
import discoverability_openai as m

P=m.PROPERTY

def inventory():
    return {'site_url':P,'urls':[{'url':P,'category':'primary_content','indexing_desired':True}], 'excluded_urls':[{'url':P+'evidence/a.html','indexing_desired':True},{'url':P+'monitoring/google-index/','indexing_desired':False}]}

def html(url=P, meta='', title='Research'):
    return ('<html><head><title>'+title+'</title><link rel="canonical" href="'+url+'">'+meta+'</head><body>Original evidence.</body></html>').encode()

class RobotsTests(unittest.TestCase):
    def test_longest_and_equal_allow_wins(self):
        text='User-agent: *\nDisallow: /\nAllow: /geo-platform-observation/\nDisallow: /geo-platform-observation/private\nAllow: /geo-platform-observation/private\n'
        self.assertEqual(m.robots_decision(text,P)['status'],'ALLOWED')
        self.assertEqual(m.robots_decision(text,P+'private')['status'],'ALLOWED')
    def test_wildcard_and_end_anchor(self):
        text='User-agent: *\nDisallow: /*.pdf$\n'
        self.assertEqual(m.robots_decision(text,P+'report.pdf')['status'],'DISALLOWED')
        self.assertEqual(m.robots_decision(text,P+'report.pdf?download=1')['status'],'ALLOWED')
    def test_specific_group_replaces_wildcard(self):
        text='User-agent: *\nDisallow: /\nUser-agent: OAI-SearchBot\nAllow: /\n'
        self.assertEqual(m.robots_decision(text,P)['status'],'ALLOWED')
    def test_repeated_specific_groups_combine(self):
        text='User-agent: OAI-SearchBot\nDisallow: /\nUser-agent: OAI-SearchBot\nAllow: /geo-platform-observation/\n'
        self.assertEqual(m.robots_decision(text,P)['status'],'ALLOWED')
    def test_empty_disallow_comments_and_case(self):
        text='User-Agent: oai-searchbot # crawler\nDisallow: # none\n'
        self.assertEqual(m.robots_decision(text,P)['status'],'ALLOWED')
    def test_percent_encoded_unreserved_and_reserved(self):
        text='User-agent: *\nDisallow: /geo-platform-observation/%61\n'
        self.assertEqual(m.robots_decision(text,P+'a')['status'],'DISALLOWED')
        self.assertNotEqual(m._octets('/a%2fb'),m._octets('/a/b'))
    def test_all_desired_canonicals_and_exclusions(self):
        self.assertEqual([r['url']for r in m.reviewed_urls(inventory())],[P,P+'evidence/a.html'])
    def test_reject_siblings_encoded_traversal_and_duplicates(self):
        for url in ['https://helen-bird.github.io/other/',P+'%2e%2e/other/',P+'%252e%252e/other/',P+'?x=1',P+'x#frag']:
            with self.assertRaises(m.ProbeError):m.validate_url(url)
        bad=inventory();bad['urls'].append(bad['urls'][0])
        with self.assertRaises(m.ProbeError):m.reviewed_urls(bad)

class ProbeTests(unittest.TestCase):
    def test_root_robots_and_simulation_never_real_crawl(self):
        calls=[]
        def req(method,url,headers,body,timeout):
            calls.append((url,headers['User-Agent']))
            return (404,{},b'')if url==m.ROBOTS_URL else (200,{'Content-Type':'text/html'},html(url))
        result=m.probe_openai(inventory(),requester=req,sleep=lambda _:None)
        self.assertEqual(calls[0][0],'https://helen-bird.github.io/robots.txt')
        self.assertEqual(len(calls),5)
        for row in result['results']:
            self.assertEqual(row['configuration_status'],'ALLOWED')
            self.assertEqual(row['ua_simulation']['status'],'FETCH_SUCCEEDED')
            self.assertEqual(row['real_crawl']['status'],'UNKNOWN')
            self.assertIsNone(row['real_crawl']['last_crawl_time'])
            self.assertEqual(row['openai_index_status'],'UNKNOWN')
    def test_robots_network_error_conservative_unknown(self):
        def req(method,url,headers,body,timeout):
            if url==m.ROBOTS_URL:raise URLError('private diagnostic not stored')
            return 200,{},html(url)
        row=m.probe_openai(inventory(),requester=req,sleep=lambda _:None)['results'][0]
        self.assertEqual(row['configuration_status'],'UNKNOWN')
        self.assertEqual(row['robots']['conservative_crawler_assumption'],'DISALLOWED')
    def test_robots_500_not_treated_as_missing_allow(self):
        def req(method,url,headers,body,timeout):return (503,{},b'')if url==m.ROBOTS_URL else (200,{},html(url))
        row=m.probe_openai(inventory(),requester=req,sleep=lambda _:None)['results'][0]
        self.assertEqual(row['robots']['status'],'UNKNOWN')
    def test_meta_and_generic_xrobots_noindex(self):
        for response in [{'http_status':200,'headers':{},'body':html(meta='<meta name="robots" content="noindex,follow">')},{'http_status':200,'headers':{'X-Robots-Tag':'noindex'},'body':html()}]:
            self.assertTrue(m.page_signals(response)['noindex'])
    def test_xrobots_other_agent_is_not_oai_block(self):
        self.assertFalse(m.page_signals({'headers':{'X-Robots-Tag':'googlebot: noindex, nofollow'},'body':html()})['noindex'])
        self.assertTrue(m.page_signals({'headers':{'X-Robots-Tag':'googlebot: nofollow, OAI-SearchBot: noindex'},'body':html()})['noindex'])
    def test_http_access_and_simulated_ua_denial_separate(self):
        def req(method,url,headers,body,timeout):
            if url==m.ROBOTS_URL:return 200,{},b'User-agent: *\nAllow: /'
            if headers['User-Agent']==m.OAI_UA:return 403,{},b'forbidden'
            return 200,{},html(url)
        row=m.probe_openai(inventory(),requester=req,sleep=lambda _:None)['results'][0]
        self.assertEqual(row['configuration_status'],'ALLOWED')
        self.assertEqual(row['ua_simulation']['status'],'HTTP_ACCESS_BLOCKED')
        self.assertEqual(row['real_crawl']['status'],'UNKNOWN')
    def test_html_200_interstitial_not_success_claim(self):
        def req(method,url,headers,body,timeout):
            if url==m.ROBOTS_URL:return 404,{},b''
            return 200,{},html(url,title='Just a moment...')
        row=m.probe_openai(inventory(),requester=req,sleep=lambda _:None)['results'][0]
        self.assertEqual(row['configuration_status'],'BLOCKED')
        self.assertEqual(row['ua_simulation']['status'],'INTERSTITIAL_OBSERVED')
    def test_get_retry_is_bounded_and_does_not_echo_error(self):
        calls=[]
        def req(*args):calls.append(1);raise URLError('secret-looking private error')
        result=m.get_url(P,requester=req,sleep=lambda _:None)
        self.assertEqual(len(calls),3);self.assertEqual(result['error'],'NETWORK_ERROR')
        self.assertNotIn('private',str(result))

if __name__=='__main__':unittest.main()
