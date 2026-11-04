"""Behavior tests use synthetic API responses; they are not real Google evidence."""
import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1]/'scripts/index_monitor.py'
spec = importlib.util.spec_from_file_location('index_monitor', MODULE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def payload(**fields):
    return {'inspectionResult': {'indexStatusResult': fields}}


class ClassificationTests(unittest.TestCase):
    def test_absence_and_unspecified_remain_unknown(self):
        for data in ({}, {'verdict': 'VERDICT_UNSPECIFIED'}, {'pageFetchState': 'SUCCESSFUL'}, {'indexingState': 'INDEXING_ALLOWED'}):
            self.assertEqual(m.classify_result(payload(**data))['status'], 'UNKNOWN')

    def test_explicit_coverage_and_positive_evidence(self):
        cases = [
            ({'coverageState': 'Discovered - currently not indexed'}, 'DISCOVERED'),
            ({'coverageState': 'Crawled - currently not indexed'}, 'CRAWLED'),
            ({'coverageState': 'URL is unknown to Google'}, 'NOT_INDEXED'),
            ({'verdict': 'PASS', 'googleCanonical': m.PROPERTY}, 'INDEXED'),
            ({'verdict': 'PASS', 'coverageState': 'Submitted and indexed'}, 'INDEXED'),
            ({'verdict': 'FAIL'}, 'UNKNOWN'),
            ({'indexingState': 'BLOCKED_BY_META_TAG'}, 'NOT_INDEXED'),
        ]
        for fields, expected in cases:
            with self.subTest(fields=fields):
                self.assertEqual(m.classify_result(payload(**fields))['status'], expected)

    def test_crawl_evidence_does_not_prove_indexed(self):
        p = payload(lastCrawlTime='2026-11-04T00:00:00Z')
        result = m.classify_result(p)
        self.assertEqual(result['lifecycle'], 'CRAWLED')
        self.assertEqual(result['status'], 'UNKNOWN')
        self.assertEqual(m.classify_result(payload(lastCrawlTime='nonsense'))['lifecycle'], 'UNKNOWN')

    def test_canonical_and_robots_alert_evidence(self):
        r = m.classify_result(payload(robotsTxtState='DISALLOWED', googleCanonical=m.PROPERTY+'other/'), m.PROPERTY)
        self.assertEqual(r['status'], 'NOT_INDEXED')
        self.assertEqual(r['blockers'], ['GOOGLE_CANONICAL_DIFFERS', 'ROBOTS_BLOCKED'])

    def test_indexed_page_can_have_a_new_crawl_block(self):
        r = m.classify_result(payload(verdict='PASS', googleCanonical=m.PROPERTY,
            robotsTxtState='DISALLOWED'), m.PROPERTY)
        self.assertEqual(r['status'], 'INDEXED')
        self.assertIn('ROBOTS_BLOCKED', r['blockers'])

    def test_conflicting_and_different_canonical_evidence_not_false_indexed(self):
        r = m.classify_result(payload(verdict='PASS',
            coverageState='Crawled - currently not indexed', googleCanonical=m.PROPERTY), m.PROPERTY)
        self.assertEqual(r['status'], 'UNKNOWN')
        self.assertIn('CONFLICTING_INDEX_EVIDENCE', r['blockers'])
        r = m.classify_result(payload(verdict='PASS', googleCanonical=m.PROPERTY+'other/'), m.PROPERTY)
        self.assertEqual(r['status'], 'UNKNOWN')


class ClientTests(unittest.TestCase):
    def test_401_and_permission_403_not_retried(self):
        for code in (401, 403):
            calls = []
            def request(*args):
                calls.append(args)
                return code, {}, {'error': {'message': 'private error detail'}}
            result = m.InspectionClient(lambda: 'private-token', request).inspect(m.PROPERTY)
            self.assertFalse(result['ok'])
            self.assertEqual(len(calls), 1)
            self.assertNotIn('private-token', json.dumps(result))

    def test_429_retry_is_bounded_and_retry_after_clamped(self):
        calls, waits = [], []
        def request(*args):
            calls.append(args)
            return 429, {'Retry-After': '900'}, {}
        result = m.InspectionClient(lambda: 'token', request, waits.append).inspect(m.PROPERTY)
        self.assertEqual(len(calls), 3)
        self.assertEqual(waits, [30, 30])
        self.assertEqual(result['error']['category'], 'RATE_LIMITED')

    def test_transient_error_then_success(self):
        values = [(503, {}, {}), (200, {}, payload(verdict='PASS', googleCanonical=m.PROPERTY))]
        client = m.InspectionClient(lambda: 'token', lambda *args: values.pop(0), sleep=lambda _: None)
        self.assertTrue(client.inspect(m.PROPERTY)['ok'])

    def test_absent_auth_never_makes_request(self):
        def fail(*args):
            self.fail('No request should happen without auth')
        result = m.InspectionClient(lambda: None, fail).inspect(m.PROPERTY)
        self.assertEqual(result['error'], {'category': 'AUTH_REQUIRED', 'attempts': 0})

    def test_quota_is_distinct_from_permission(self):
        category, retry = m.error_category(403, {'error': {'status': 'RESOURCE_EXHAUSTED'}})
        self.assertEqual(category, 'QUOTA_EXCEEDED')
        self.assertFalse(retry)
        category, retry = m.error_category(403, {'error': {'details': [{'reason': 'RATE_LIMIT_EXCEEDED'}]}})
        self.assertEqual(category, 'RATE_LIMITED')
        self.assertTrue(retry)


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.inventory = self.root/'inventory.json'
        self.inventory.write_text(json.dumps({'property': m.PROPERTY, 'urls': [
            {'url': m.PROPERTY, 'category': 'primary_content', 'monitor': True},
            {'url': m.PROPERTY+'learning-hub/', 'category': 'primary_content', 'monitor': True}]}))
        self.output = self.root/'private'

    def tearDown(self):
        self.temp.cleanup()

    def run_with(self, request, **kwargs):
        return m.run_monitor(self.inventory, self.output, lambda: 'token', requester=request,
            sleep=lambda _: None, now=dt.datetime(2026, 11, 4, tzinfo=dt.timezone.utc), **kwargs)

    def test_partial_does_not_replace_previous_success(self):
        def indexed(method, url, headers, body, timeout):
            target = json.loads(body)['inspectionUrl']
            return 200, {}, payload(verdict='PASS', googleCanonical=target)
        first = self.run_with(indexed)
        baseline_bytes = (self.output/'latest-successful-index-status.json').read_bytes()
        def partial(method, url, headers, body, timeout):
            target = json.loads(body)['inspectionUrl']
            return (200, {}, payload(coverageState='Crawled - currently not indexed')) if target == m.PROPERTY else (401, {}, {})
        second = self.run_with(partial)
        self.assertEqual(second['run_status'], 'AUTH_REQUIRED')
        self.assertEqual((self.output/'latest-successful-index-status.json').read_bytes(), baseline_bytes)
        self.assertEqual(second['previous_successful_snapshot_id'], first['snapshot_id'])
        self.assertEqual(len(list((self.output/'snapshots').glob('*.json'))), 2)
        kinds = {a['kind'] for a in second['alerts']}
        self.assertIn('INDEX_LOST', kinds)
        self.assertIn('AUTHORIZATION_FAILED', kinds)

    def test_snapshot_is_immutable_and_safe_alerts_exclude_raw_fields(self):
        def response(*args):
            return 200, {}, payload(verdict='PASS', googleCanonical=m.PROPERTY,
                referringUrls=['https://private.example/ref'], sitemap=[m.PROPERTY+'sitemap.xml'])
        first = self.run_with(response)
        snapshot = self.output/'snapshots'/(first['snapshot_id']+'.json')
        original = snapshot.read_bytes()
        self.run_with(response)
        self.assertEqual(snapshot.read_bytes(), original)
        self.assertNotIn('referringUrls', (self.output/'alerts.json').read_text())
        self.assertNotIn('private.example', (self.output/'alerts.json').read_text())
        self.assertEqual(len((self.output/'index-history.csv').read_text().splitlines()), 5)

    def test_new_and_removed_urls_and_changes(self):
        self.run_with(lambda *args: (200, {}, payload(coverageState='URL is unknown to Google')))
        self.inventory.write_text(json.dumps({'urls': [
            {'url': m.PROPERTY, 'monitor': True},
            {'url': m.PROPERTY+'new/', 'monitor': True}]}))
        second = self.run_with(lambda *args: (200, {}, payload(coverageState='Discovered - currently not indexed')))
        self.assertEqual(second['added_urls'], [m.PROPERTY+'new/'])
        self.assertEqual(second['removed_urls'], [m.PROPERTY+'learning-hub/'])
        self.assertTrue(all(r['status_changed'] for r in second['results']))

    def test_baseline_file_not_modified(self):
        baseline = self.output/'baseline-index-status.json'
        self.output.mkdir();baseline.write_text('{"source":"manual_historical"}')
        self.run_with(lambda *args: (200, {}, payload(verdict='VERDICT_UNSPECIFIED')))
        self.assertEqual(baseline.read_text(), '{"source":"manual_historical"}')

    def test_public_output_directory_rejected(self):
        with self.assertRaises(ValueError):
            m.run_monitor(self.inventory, m.PUBLIC_ROOT/'monitoring/private', lambda: 'token')

    def test_private_runtime_requires_visibility_proof_and_approved_remote(self):
        target = m.PUBLIC_ROOT/'state'
        with patch.object(m.subprocess, 'check_output', return_value='https://github.com/helen-bird/geo-index-monitor.git\n'):
            with self.assertRaises(ValueError):
                m._guard_private_output(target, False)
            m._guard_private_output(target, True)
        with patch.object(m.subprocess, 'check_output', return_value='https://github.com/helen-bird/geo-platform-observation.git\n'):
            with self.assertRaises(ValueError):
                m._guard_private_output(target, True)

    def test_transition_fingerprints_allow_distinct_reindexing_episodes(self):
        current = [{'url': m.PROPERTY, 'status': 'INDEXED', 'query_success': True, 'blockers': []}]
        old = {'snapshot_id': 'old-1', 'results': [{'url': m.PROPERTY, 'status': 'NOT_INDEXED'}]}
        first = m.compare(old, current, '2026-11-04T00:00:00Z')[0][0]
        second = m.compare(old, current, '2026-11-04T01:00:00Z')[0][0]
        self.assertEqual(first['fingerprint'], second['fingerprint'])
        old['snapshot_id'] = 'later-separate-episode'
        third = m.compare(old, current, '2026-11-05T00:00:00Z')[0][0]
        self.assertNotEqual(first['fingerprint'], third['fingerprint'])

    def test_corrupt_state_is_not_overwritten(self):
        self.output.mkdir();p=self.output/'monitor-state.json';p.write_text('{broken')
        with self.assertRaises(json.JSONDecodeError):
            self.run_with(lambda *args: (200, {}, payload(verdict='PASS')))
        self.assertEqual(p.read_text(), '{broken')

    def test_alias_and_encoded_traversal_rejected(self):
        for url in (m.PROPERTY+'index.html', m.PROPERTY+'%2e%2e/private/'):
            self.inventory.write_text(json.dumps({'urls': [{'url': url, 'monitor': True}]}))
            with self.assertRaises(ValueError):
                m.load_inventory(self.inventory)


if __name__ == '__main__':
    unittest.main()
