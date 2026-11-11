"""Test offline cho phần bonus: chọn tools/prompt, giới hạn retry 429, chờ Retry-After."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent import run_agent, SYSTEM_PROMPT, BONUS_RULES, MAX_RATE_LIMIT_ATTEMPTS
from bonus.test_agent import ScriptedProvider, call, final
from bonus.tools import BonusTools
from status_tools import StatusTools


class PromptSelectionTests(unittest.TestCase):
    def test_bonus_tools_get_bonus_prompt_and_rules(self):
        p = ScriptedProvider([final()])
        run_agent('x', p, BonusTools())
        system = p.histories[0][0]['content']
        self.assertIn('DigitalOcean', system)
        self.assertIn(BONUS_RULES, system)

    def test_main_tools_keep_main_prompt_and_schemas(self):
        p = ScriptedProvider([final()])
        run_agent('x', p, StatusTools())
        self.assertEqual(p.histories[0][0]['content'], SYSTEM_PROMPT)
        self.assertEqual({s['function']['name'] for s in p.schemas[0]}, {'get_status', 'get_incident_details'})


class RateLimitTests(unittest.TestCase):
    def _run_vercel(self, scenario, n):
        responses = [call(f'c{i}', 'get_vercel_status', {}) for i in range(n)] + [final('Vercel: chưa biết')]
        p = ScriptedProvider(responses)
        return run_agent('x', p, BonusTools(scenario=scenario), max_steps=n + 2), p

    def test_retry_is_capped_when_429_persists(self):
        result, p = self._run_vercel('rate_limit_always', 5)
        executed = [t for t in result['trace'] if t['event'] == 'tool']
        blocked = [t for t in result['trace'] if t['event'] == 'retry_blocked']
        self.assertEqual(len(executed), MAX_RATE_LIMIT_ATTEMPTS)
        self.assertEqual(len(blocked), 5 - MAX_RATE_LIMIT_ATTEMPTS)
        self.assertEqual(json.loads(p.histories[-1][-1]['content'])['error'], 'RETRY_LIMIT_REACHED')
        self.assertEqual(result['status'], 'completed')

    def test_success_resets_counter(self):
        result, _ = self._run_vercel('rate_limit_once', 4)
        self.assertFalse([t for t in result['trace'] if t['event'] == 'retry_blocked'])
        self.assertEqual(len([t for t in result['trace'] if t['event'] == 'tool']), 4)

    def test_other_provider_not_blocked(self):
        responses = [call(f'v{i}', 'get_vercel_status', {}) for i in range(3)] + [call('g', 'get_github_status', {}), final()]
        result = run_agent('x', ScriptedProvider(responses), BonusTools(scenario='rate_limit_always'), max_steps=6)
        self.assertIn('get_github_status', [t.get('name') for t in result['trace'] if t['event'] == 'tool'])

    def test_retry_after_is_waited_but_capped(self):
        class Tools:
            schemas, system_prompt = [], 'p'
            def execute(self, name, args):
                return {'ok': False, 'error': 'RATE_LIMITED', 'retry_after': '120'}
        with patch('agent.time.sleep') as sleep:
            run_agent('x', ScriptedProvider([call('a', 'get_vercel_status', {}), final()]), Tools(), max_steps=3)
        sleep.assert_called_once_with(5)

    def test_zero_retry_after_does_not_sleep(self):
        with patch('agent.time.sleep') as sleep:
            self._run_vercel('rate_limit_once', 2)
        sleep.assert_not_called()


class RetryNudgeTests(unittest.TestCase):
    def test_nudge_when_model_answers_after_single_429(self):
        p = ScriptedProvider([call('a', 'get_vercel_status', {}), final('Vercel lỗi'), call('b', 'get_vercel_status', {}), final('Vercel ổn')])
        result = run_agent('x', p, BonusTools(scenario='rate_limit_once'), max_steps=6)
        self.assertTrue([t for t in result['trace'] if t['event'] == 'retry_nudge'])
        self.assertEqual(len([t for t in result['trace'] if t['event'] == 'tool']), 2)
        self.assertEqual(result['answer'], 'Vercel ổn')

    def test_no_nudge_after_limit_reached(self):
        responses = [call(f'c{i}', 'get_vercel_status', {}) for i in range(3)] + [final('Vercel: chưa biết')]
        result = run_agent('x', ScriptedProvider(responses), BonusTools(scenario='rate_limit_always'), max_steps=6)
        self.assertFalse([t for t in result['trace'] if t['event'] == 'retry_nudge'])

    def test_nudges_are_bounded(self):
        responses = [call('a', 'get_vercel_status', {})] + [final('bỏ cuộc')] * 6
        result = run_agent('x', ScriptedProvider(responses), BonusTools(scenario='rate_limit_always'), max_steps=10)
        self.assertLessEqual(len([t for t in result['trace'] if t['event'] == 'retry_nudge']), 3)
        self.assertEqual(result['status'], 'completed')


class PaginationTests(unittest.TestCase):
    def test_next_offset_page_can_be_requested(self):
        t = BonusTools()
        first = t.execute('get_incident_details', {'provider': 'vercel', 'incident_id': 'sps6n39gm4sg', 'limit': 3})
        self.assertTrue(first['ok'])
        self.assertIsNotNone(first['next_offset'])
        p = ScriptedProvider([call('a', 'get_incident_details', {'provider': 'vercel', 'incident_id': 'sps6n39gm4sg', 'limit': 3}),
                              call('b', 'get_incident_details', {'provider': 'vercel', 'incident_id': 'sps6n39gm4sg', 'offset': first['next_offset'], 'limit': 3}),
                              final('Nguồn: ' + first['url'])])
        result = run_agent('x', p, t, max_steps=5)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len({x['step'] for x in result['trace'] if x['event'] == 'tool'}), 2)


if __name__ == '__main__':
    unittest.main()
