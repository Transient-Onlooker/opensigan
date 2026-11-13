import json
import unittest
from unittest.mock import patch

from backend.app import dispatch_request, _rate_clients
from backend.cache import Cache


class PublicApiTests(unittest.TestCase):
    def setUp(self):
        _rate_clients.clear()

    def test_cors_restricts_origins_and_options_does_not_use_limit(self):
        with patch.dict('os.environ', {'ALLOWED_ORIGIN': 'https://example.test'}):
            for _ in range(65):
                status, headers, _ = dispatch_request('OPTIONS', '/api/v1/schools', '', client='x', request_origin='https://evil.test')
                self.assertEqual(status, 204)
                self.assertNotIn('Access-Control-Allow-Origin', headers)
            _, headers, _ = dispatch_request('OPTIONS', '/api/v1/schools', '', request_origin='https://example.test')
            self.assertEqual(headers['Access-Control-Allow-Origin'], 'https://example.test')

    def test_rate_limit_and_error_contract(self):
        for _ in range(60):
            status, _, _ = dispatch_request('GET', '/api/v1/schools', '', client='client')
            self.assertEqual(status, 400)
        status, headers, body = dispatch_request('GET', '/api/v1/schools', '', client='client')
        self.assertEqual(status, 429)
        self.assertGreater(int(headers['Retry-After']), 0)
        self.assertEqual(json.loads(body)['code'], 'rate_limited')
        self.assertEqual(dispatch_request('GET', '/api/v1/status', '', client='client')[0], 200)

    def test_timetable_cache_state_and_disabled_history(self):
        result = {'schoolId': '1:Example', 'weekStart': '2026-11-09', 'records': [], 'stale': False}
        with patch('backend.app.validate_timetable_week'), patch('backend.app.fetch_timetable', return_value=result) as fetch, patch.dict('os.environ', {'OPENCIGAN_HISTORY_DB': ''}):
            cache = Cache()
            query = 'school=1%3AExample&week=2026-11-09'
            first = json.loads(dispatch_request('GET', '/api/v1/timetable', query, cache)[2])
            second = json.loads(dispatch_request('GET', '/api/v1/timetable', query, cache)[2])
            self.assertEqual((first['cacheStatus'], second['cacheStatus']), ('miss', 'hit'))
            fetch.assert_called_once()
            status, _, body = dispatch_request('GET', '/api/v1/timetable/history', query)
            self.assertEqual((status, json.loads(body)['code']), (503, 'history_disabled'))

    def test_history_records_only_successful_fresh_fetches(self):
        from unittest.mock import Mock
        response = {'schoolId': '1:Example', 'weekStart': '2026-11-09', 'records': [],
                    'fetchedAt': '2026-11-09T00:00:00+00:00', 'stale': False}
        store = Mock()
        with patch('backend.app.validate_timetable_week'), patch('backend.app._history_store', return_value=store), \
                patch('backend.app.fetch_timetable', side_effect=[response, RuntimeError('unavailable')]):
            cache = Cache(ttl=0, retry_delay=60)
            query = 'school=1%3AExample&week=2026-11-09'
            first = json.loads(dispatch_request('GET', '/api/v1/timetable', query, cache)[2])
            second = json.loads(dispatch_request('GET', '/api/v1/timetable', query, cache)[2])
            self.assertEqual((first['cacheStatus'], second['cacheStatus']), ('miss', 'stale'))
            store.observe.assert_called_once()

    def test_history_endpoint_with_synthetic_data(self):
        import tempfile
        from pathlib import Path
        from backend.history import HistoryStore
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'history.sqlite')
            store = HistoryStore(path)
            record = {'grade': 1, 'class': 2, 'date': '2026-11-09', 'period': 1, 'subject': 'Math', 'teacher': 'A'}
            store.observe('1:Example', '2026-11-09', [record])
            store.observe('1:Example', '2026-11-09', [{**record, 'subject': 'Art'}])
            with patch.dict('os.environ', {'OPENCIGAN_HISTORY_DB': path}):
                status, _, body = dispatch_request('GET', '/api/v1/timetable/history', 'school=1%3AExample&week=2026-11-09')
                self.assertEqual(status, 200)
                change = json.loads(body)['changes'][0]
                self.assertEqual((change['before']['subject'], change['after']['subject']), ('Math', 'Art'))


if __name__ == '__main__':
    unittest.main()
