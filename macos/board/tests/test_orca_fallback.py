"""오르카 CLI 를 못 찾거나 창 목록을 못 받아도 오르카 안 세션이 보드에서 사라지지 않는다."""
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import board as B


def orca_agent(**extra):
    a = {'pid': 42, 'kind': 'claude', 'tty': 'ttys003', 'start': 1000, 'cwd': '/w/api', 'busy': False,
         'orca_pane_key': 'tab1:leaf1', 'term_program': 'Orca', 'log': None}
    a.update(extra)
    return a


class OrcaPaneFallbackTest(unittest.TestCase):
    def terms(self, listed):
        with patch.dict(B.LIST_CACHE, {'list': {'terminals': listed}}, clear=True), \
                patch.object(B, 'agent_procs', return_value={42: orca_agent()}):
            return B.outside_terms()

    def test_orca_pane_is_left_to_orca_when_the_list_came_back(self):
        out, wts = self.terms([{'handle': 'term_1'}])
        self.assertEqual((out, wts), ([], {}))

    def test_orca_pane_becomes_a_card_when_the_list_is_empty(self):
        out, wts = self.terms([])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['handle'], 'proc_42')
        self.assertEqual(wts[out[0]['worktreeId']]['displayName'], 'api · Orca')
        self.assertEqual(out[0]['agent'], {'state': 'done'})

    def test_orca_pane_becomes_a_card_before_any_list(self):
        with patch.dict(B.LIST_CACHE, {}, clear=True), patch.object(B, 'agent_procs', return_value={42: orca_agent()}):
            out, _ = B.outside_terms()
        self.assertEqual([t['handle'] for t in out], ['proc_42'])


class FindOrcaBinTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def exe(self, folder):
        os.makedirs(folder, exist_ok=True)
        p = os.path.join(folder, 'orca')
        Path(p).write_text('#!/bin/sh\n')
        os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR)
        return p

    def test_app_bundle_cli_is_on_the_search_list(self):
        self.assertIn('/Applications/Orca.app/Contents/Resources/bin', B.EXTRA_PATH)

    def test_falls_back_to_the_app_bundle_when_path_has_no_orca(self):
        bundled = self.exe(os.path.join(self.tmp.name, 'Orca.app/Contents/Resources/bin'))
        with patch.dict(os.environ, {'PATH': '/usr/bin:/bin'}), patch.object(B, 'EXTRA_PATH', [os.path.dirname(bundled)]):
            self.assertEqual(B.find_bin('orca'), bundled)

    def test_orca_runs_the_path_it_found(self):
        bundled = self.exe(os.path.join(self.tmp.name, 'Orca.app/Contents/Resources/bin'))
        reply = SimpleNamespace(stdout='{"result": {"terminals": []}}')
        with patch.dict(os.environ, {'PATH': '/usr/bin:/bin'}), patch.object(B, 'EXTRA_PATH', [os.path.dirname(bundled)]), \
                patch.object(B.subprocess, 'run', return_value=reply) as run:
            B.orca('terminal', 'list')
        self.assertEqual(run.call_args[0][0][0], bundled)

    def test_path_still_wins_over_the_app_bundle(self):
        registered = self.exe(os.path.join(self.tmp.name, 'bin'))
        bundled = self.exe(os.path.join(self.tmp.name, 'Orca.app/Contents/Resources/bin'))
        with patch.dict(os.environ, {'PATH': os.path.dirname(registered)}), patch.object(B, 'EXTRA_PATH', [os.path.dirname(bundled)]):
            self.assertEqual(B.find_bin('orca'), registered)


class FolderWorkspaceTest(unittest.TestCase):
    PS = {'worktrees': [
        {'worktreeId': 'folder:a', 'repo': 'workspace', 'path': '/w', 'displayName': 'gig', 'agents': [{'paneKey': 't1:l1'}]},
        {'worktreeId': 'repo1::/w/api', 'repo': 'api', 'path': '/w/api', 'displayName': 'from ps', 'agents': []},
    ]}

    def setUp(self):
        self.addCleanup(B.PS_WORKTREES.clear)

    def test_ps_names_fill_folder_workspaces(self):
        with patch.object(B, 'orca', return_value=self.PS):
            agents = B.orca_agents()
        self.assertEqual(list(agents), ['t1:l1'])
        wts = B.add_folder_worktrees({})
        self.assertEqual(wts['folder:a']['displayName'], 'gig')
        self.assertTrue(wts['folder:a']['psOnly'])

    def test_git_workspace_from_list_is_kept(self):
        with patch.object(B, 'orca', return_value=self.PS):
            B.orca_agents()
        listed = {'id': 'repo1::/w/api', 'displayName': 'api', 'path': '/w/api', 'isArchived': False}
        wts = B.add_folder_worktrees({'repo1::/w/api': listed})
        self.assertIs(wts['repo1::/w/api'], listed)

    def test_failed_ps_keeps_the_last_names(self):
        with patch.object(B, 'orca', return_value=self.PS):
            B.orca_agents()
        with patch.object(B, 'orca', side_effect=OSError('orca gone')):
            self.assertEqual(B.orca_agents(), {})
        self.assertIn('folder:a', B.PS_WORKTREES)


if __name__ == '__main__':
    unittest.main()
