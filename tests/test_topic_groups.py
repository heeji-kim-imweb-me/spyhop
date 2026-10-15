"""주제 배정과 빈 칸 유지 회귀 시험. 외부 모델과 실제 세션은 사용하지 않는다."""
import copy
import json
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
import board as B
import demo_screens as D


class ImmediateThread:
    def __init__(self, target, **kwargs):
        self.target = target

    def start(self):
        self.target()


class Columns(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.names = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'section' and attrs.get('class') == 'col':
            self.names.append(attrs['data-name'])


class TopicGroupsTest(unittest.TestCase):
    def setUp(self):
        self.saved = dict(vars(B))
        self.tmp = tempfile.TemporaryDirectory(prefix='spyhop-topics-')
        self.root = Path(self.tmp.name)
        for name, filename in [('BASE', ''), ('GROUPS_FILE', 'groups.json'),
                               ('MOVED_FILE', 'moved.json'), ('TRACE', 'trace.json'),
                               ('CONFIG', 'config.json')]:
            setattr(B, name, str(self.root / filename))
        self.groups = {'groups': ['First', 'Middle', 'Last'], 'assign': {
            'old': {'g': 'Middle', 'manual': False},
            'manual': {'g': 'First', 'manual': True}}}
        B.save_groups(self.groups)
        B._GROUPING = {'busy': False, 'at': 0}

    def tearDown(self):
        vars(B).update(self.saved)
        self.tmp.cleanup()

    def test_only_new_session_is_classified_and_empty_groups_are_candidates(self):
        with patch.object(B.threading, 'Thread', ImmediateThread), patch.object(
                B, 'llm', return_value='{"assign":{"s1":"Last"}}') as model:
            B.assign_groups([('old', 'Changed title', 'Changed topic'),
                             ('manual', 'Manual title', 'New summary'),
                             ('new', 'New session', 'New topic')])
        prompt = model.call_args.args[1]
        self.assertIn('Last', prompt)
        self.assertNotIn('Changed title', prompt)
        self.assertNotIn('Manual title', prompt)
        current = B.load_groups()
        for key in ('old', 'manual'):
            self.assertEqual(current['assign'][key], self.groups['assign'][key])
        self.assertEqual(current['assign']['new']['g'], 'Last')
        self.assertEqual(current['groups'], self.groups['groups'])

    def test_assigned_session_never_calls_model_again(self):
        with patch.object(B, 'llm') as model:
            for _ in range(3):
                B.assign_groups([('old', 'Different title', 'Different summary')])
        model.assert_not_called()

    def test_manual_move_during_model_call_wins(self):
        def answer(*args):
            current = B.load_groups()
            current['assign']['new'] = {'g': 'First', 'manual': True}
            B.save_groups(current)
            return '{"assign":{"s1":"Last"}}'
        with patch.object(B.threading, 'Thread', ImmediateThread), patch.object(B, 'llm', answer):
            B.assign_groups([('new', 'New session', 'Topic')])
        self.assertEqual(B.load_groups()['assign']['new'], {'g': 'First', 'manual': True})

    def test_model_failure_preserves_existing_data(self):
        with patch.object(B.threading, 'Thread', ImmediateThread), patch.object(
                B, 'llm', side_effect=RuntimeError('offline')):
            B.assign_groups([('new', 'New session', 'Topic')])
        self.assertEqual(B.load_groups(), self.groups)
        self.assertFalse(B._GROUPING['busy'])

    def test_empty_columns_and_order_survive_session_disappearance(self):
        group_of = B.group_of
        D.patch('ai')
        B.group_of = group_of
        B.load_groups = lambda: copy.deepcopy(self.groups)
        B.OUT = str(self.root / 'board.html')
        B.STATE = str(self.root / 'state.json')
        for i in range(len(D.SESSIONS) + 1):
            self.groups['assign'][str(Path(D.TMP) / ('session-%d.jsonl' % i))] = {
                'g': 'Middle', 'manual': False}
        B.build()
        self.assertEqual(Columns(Path(B.OUT).read_text()).names, self.groups['groups'])
        B.orca = lambda *args: {'worktrees': [], 'terminals': []}
        B.outside_terms = lambda: ([], {})
        B.build()
        self.assertEqual(Columns(Path(B.OUT).read_text()).names, self.groups['groups'])
        self.assertEqual(json.loads(Path(B.STATE).read_text())['sessions'], [])

    def test_snapshot_does_not_reload_changed_assignment(self):
        snapshot = B.load_groups()
        current = B.load_groups()
        current['assign']['old']['g'] = 'Last'
        B.save_groups(current)
        self.assertEqual(B.group_of('old', snapshot), 'Middle')
        self.assertEqual(B.group_of('old'), 'Last')


if __name__ == '__main__':
    unittest.main()
