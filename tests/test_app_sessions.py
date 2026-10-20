"""Claude 앱 기록(Code 탭 · Cowork)으로 찾는 세션을 가짜 앱 폴더로 확인한다. 실제 앱 기록은 읽지 않는다."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import board as B

NOW = time.time()


class AppSessionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='spyhop-app-')
        self.root = Path(self.tmp.name)
        self.app = self.root / 'Claude'
        self.home = self.root / 'home'
        self.env = patch.multiple(B, CLAUDE_APP_DIR=str(self.app))
        self.env.start()
        self.user = patch.dict(os.environ, {'HOME': str(self.home), 'USERPROFILE': str(self.home)})
        self.user.start()

    def tearDown(self):
        self.user.stop()
        self.env.stop()
        self.tmp.cleanup()

    def code(self, sid, cli, cwd, ago=60, archived=False, transcript=True):
        rec = self.app / 'claude-code-sessions' / 'acct' / 'org' / ('local_%s.json' % sid)
        rec.parent.mkdir(parents=True, exist_ok=True)
        rec.write_text(json.dumps({'sessionId': 'local_' + sid, 'cliSessionId': cli, 'cwd': cwd, 'isArchived': archived,
                                   'lastActivityAt': (NOW - ago) * 1000, 'title': 'T ' + sid}), encoding='utf-8')
        os.utime(rec, (NOW - ago, NOW - ago))
        if transcript:
            log = self.home / '.claude' / 'projects' / 'p' / (cli + '.jsonl')
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text('{}\n', encoding='utf-8')
        return rec

    def cowork(self, sid, cli, last_type, folders=(), audit_ago=5):
        org = self.app / 'local-agent-mode-sessions' / 'acct' / 'org'
        folder = org / sid[:8]
        (folder / 'outputs').mkdir(parents=True, exist_ok=True)
        rec = org / ('local_%s.json' % sid)
        rec.write_text(json.dumps({'sessionId': 'local_' + sid, 'cliSessionId': cli, 'cwd': str(folder / 'outputs'),
                                   'userSelectedFolders': list(folders), 'isArchived': False,
                                   'lastActivityAt': (NOW - 30) * 1000, 'title': 'Cowork ' + sid}), encoding='utf-8')
        log = folder / '.claude' / 'projects' / 'session' / (cli + '.jsonl')
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text('{}\n', encoding='utf-8')
        audit = folder / 'audit.jsonl'
        audit.write_text(json.dumps({'type': 'user'}) + '\n' + json.dumps({'type': last_type}) + '\n', encoding='utf-8')
        os.utime(audit, (NOW - audit_ago, NOW - audit_ago))
        return folder

    def test_recent_unarchived_code_tab_sessions_only(self):
        self.code('aaaa1111', 'cli-recent', '/w/automation')
        self.code('bbbb2222', 'cli-old', '/w/automation', ago=B.APP_RECENT + 60)
        self.code('cccc3333', 'cli-archived', '/w/automation', archived=True)
        self.code('dddd4444', 'cli-no-log', '/w/automation', transcript=False)
        found = B.app_sessions(now=NOW)
        self.assertEqual([s['cli'] for s in found], ['cli-recent'])
        self.assertEqual(found[0]['kind'], 'code')
        self.assertFalse(found[0]['busy'])  # 프로그램이 없는 Code 탭 세션은 일하는 중일 수 없다

    def test_running_sessions_are_not_listed_twice(self):
        self.code('aaaa1111', 'cli-live', '/w/automation')
        self.assertEqual(B.app_sessions(live_ids={'cli-live'}, now=NOW), [])

    def test_cowork_status_comes_from_audit(self):
        self.cowork('eeee5555-1', 'cli-working', 'assistant', folders=['/w/reports'])
        self.cowork('ffff6666-1', 'cli-done', 'result')
        self.cowork('9999aaaa-1', 'cli-stalled', 'assistant', audit_ago=B.COWORK_BUSY_QUIET + 60)
        found = {s['cli']: s for s in B.app_sessions(now=NOW)}
        self.assertEqual(set(found), {'cli-working', 'cli-done', 'cli-stalled'})
        self.assertTrue(found['cli-working']['busy'])
        self.assertFalse(found['cli-done']['busy'])
        self.assertFalse(found['cli-stalled']['busy'])
        self.assertEqual(found['cli-working']['cwd'], '/w/reports')  # 고른 폴더가 있으면 그 폴더 칸으로
        self.assertEqual(found['cli-done']['cwd'], '')
        self.assertTrue(found['cli-done']['log'].endswith('cli-done.jsonl'))

    def test_outside_terms_show_app_sessions_in_app_columns(self):
        self.code('aaaa1111', 'cli-code', '/w/automation')
        self.cowork('eeee5555-1', 'cli-cowork', 'result')
        with patch.object(B, 'agent_procs', return_value={}):
            terms, wts = B.outside_terms()
        cols = sorted(wts[t['worktreeId']]['displayName'] for t in terms)
        self.assertEqual(cols, ['Cowork', 'automation · Claude app'])
        for t in terms:
            self.assertTrue(t['handle'].startswith('proc_app_'))
            self.assertTrue(t['_proc']['log'])
            self.assertEqual(t['agent']['state'], 'done')

    def test_broken_records_are_skipped(self):
        bad = self.app / 'claude-code-sessions' / 'acct' / 'org' / 'local_bad.json'
        bad.parent.mkdir(parents=True)
        bad.write_text('{not json', encoding='utf-8')
        (bad.parent / 'local_list.json').write_text('[]', encoding='utf-8')
        self.code('aaaa1111', 'cli-ok', '/w/automation')
        self.assertEqual([s['cli'] for s in B.app_sessions(now=NOW)], ['cli-ok'])


if __name__ == '__main__':
    unittest.main()
