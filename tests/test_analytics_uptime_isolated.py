"""Exercise production uptime logic without a Frappe test site or database."""
import ast
import math
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

class UptimeTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / 'press/api/analytics.py'
        node = next(n for n in ast.parse(source.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'get_uptime')
        self.now = datetime(2026, 10, 16, 10, tzinfo=timezone.utc)
        fixed = self.now
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed
        self.request = Mock(return_value=SimpleNamespace(json=lambda: {'data': {'result': []}}))
        scope = {'datetime': Clock, 'datetime_timezone': timezone, 'math': math,
                 'frappe': SimpleNamespace(db=SimpleNamespace(get_single_value=lambda *args: 'monitor'), _dict=dict),
                 'get_decrypted_password': lambda *args: 'unused',
                 'requests': SimpleNamespace(get=self.request),
                 'convert_utc_to_timezone': lambda value, zone: value}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), scope)
        self.uptime = scope['get_uptime']

    def test_future_end_is_clamped_and_requested_start_is_not_expanded(self):
        start = self.now - timedelta(minutes=7)
        self.uptime('site', 'UTC', start, self.now + timedelta(minutes=20), 60)
        query = self.request.call_args.kwargs['params']
        self.assertEqual(query['start'], start.timestamp())
        self.assertEqual(query['end'], self.now.timestamp())
        self.assertNotIn('vector(0)', query['query'])

    def test_missing_monitoring_returns_no_outage_points(self):
        self.assertEqual(self.uptime('site', 'UTC', self.now-timedelta(hours=1), self.now, 60), [])

    def test_empty_or_reversed_window_does_not_query(self):
        for start in [self.now, self.now + timedelta(hours=1)]:
            self.assertEqual(self.uptime('site', 'UTC', start, self.now, 60), [])
        self.request.assert_not_called()

    def test_real_failure_is_retained_but_future_and_nonfinite_points_are_not(self):
        values = [[self.now.timestamp()-60, '0'], [self.now.timestamp(), '1'],
                  [self.now.timestamp()+60, '0'], [self.now.timestamp()-120, 'NaN']]
        self.request.return_value.json = lambda: {'data': {'result': [{'values': values}]}}
        rows = self.uptime('site', 'UTC', self.now-timedelta(minutes=5), self.now, 60)
        self.assertEqual([r['value'] for r in rows], [0.0, 1.0])

if __name__ == '__main__':
    unittest.main()
