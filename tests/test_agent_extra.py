"""Test bổ sung cho các nhánh lỗi của agent loop (offline, dùng provider giả)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent import run_agent, SYSTEM_PROMPT
from status_tools import StatusTools
from test_lab import FakeProvider, tool_call, final


class RaisingProvider:
    def complete(self, messages, schemas):
        raise RuntimeError('Provider trả HTTP 500')


class RaisingTools:
    def execute(self, name, args):
        raise TimeoutError('quá thời gian')


class ErrorPathTests(unittest.TestCase):
    def test_provider_error_is_error_not_crash(self):
        result = run_agent('x', RaisingProvider(), StatusTools())
        self.assertEqual(result['status'], 'error')
        self.assertTrue(any(t['event'] == 'provider_error' for t in result['trace']))

    def test_tool_exception_becomes_observation(self):
        fake = FakeProvider([tool_call('t1', 'get_status', '{"provider":"github"}'), final('Không đủ dữ liệu')])
        result = run_agent('x', fake, RaisingTools())
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(json.loads(fake.histories[1][-1]['content'])['error'], 'TimeoutError')

    def test_abnormal_finish_is_error(self):
        odd = final('lọc nội dung')
        odd['finish'] = 'content_filter'
        self.assertEqual(run_agent('x', FakeProvider([odd]), StatusTools())['status'], 'error')

    def test_non_object_arguments_rejected(self):
        fake = FakeProvider([tool_call('t2', 'get_status', '[1,2]'), final()])
        result = run_agent('x', fake, StatusTools())
        self.assertEqual(json.loads(fake.histories[1][-1]['content'])['error'], 'INVALID_ARGUMENTS')

    def test_usage_recorded_per_model_call(self):
        fake = FakeProvider([tool_call('t3', 'get_status', '{"provider":"github"}'), final()])
        self.assertEqual(len(run_agent('x', fake, StatusTools())['usage']), 2)

    def test_prompt_tells_model_to_follow_linked_incident(self):
        self.assertIn('get_incident_details', SYSTEM_PROMPT)
        self.assertIn('incidents/<id>', SYSTEM_PROMPT)


if __name__ == '__main__':
    unittest.main()
