"""감시 재시작이 다른 프로세스를 끝내지 않는지 실제 자식 프로세스로 확인한다."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import board as B


class WatcherIdentityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='spyhop-identity-')
        self.root = Path(self.tmp.name)
        self.script = self.root / 'board.py'
        self.script.write_text('import time\ntime.sleep(60)\n')
        self.pidfile = self.root / 'watch.pid'
        self.processes = []
        self.paths = patch.multiple(B, PIDFILE=str(self.pidfile), UPDATE_FILE=str(self.root / 'update.json'))
        self.paths.start()

    def tearDown(self):
        for p in self.processes:
            if p.poll() is None:
                p.terminate()
            p.wait(timeout=5)
        self.paths.stop()
        self.tmp.cleanup()

    def start(self, argv=None):
        p = subprocess.Popen(argv or [sys.executable, str(self.script), '--watch'])
        self.processes.append(p)
        self.pidfile.write_text('%d %s' % (p.pid, self.script))
        for _ in range(100):
            record = B.watcher_record()
            if record:
                return p, record
            time.sleep(.01)
        return p, None

    def test_live_legacy_board_is_recognized(self):
        p, record = self.start()
        self.assertIsNotNone(record)
        self.assertEqual(record[0], p.pid)
        self.assertTrue(B.watching())

    def test_matching_birth_is_recognized_but_reused_birth_is_not(self):
        p, record = self.start()
        self.assertIsNotNone(record)
        self.pidfile.write_text('%d %s %s' % (p.pid, self.script, record[2]))
        self.assertTrue(B.watching())
        self.pidfile.write_text('%d %s %s' % (p.pid, self.script, record[2] - 1))
        B.stop_if_outdated()
        self.assertFalse(B.watching())
        self.assertIsNone(p.poll())

    def test_board_started_through_symlink_is_recognized(self):
        alias = self.root / 'alias.py'
        alias.symlink_to(self.script)
        _, record = self.start([sys.executable, str(alias), '--watch'])
        self.assertIsNotNone(record)

    def test_unrelated_live_pid_is_not_signalled(self):
        p = subprocess.Popen(['/bin/sleep', '60'])
        self.processes.append(p)
        self.pidfile.write_text('%d %s' % (p.pid, self.script))
        self.assertFalse(B.watching())
        B.stop_if_outdated()
        self.assertIsNone(p.poll())

    def test_python_without_watch_argument_is_not_signalled(self):
        p, _ = self.start([sys.executable, str(self.script)])
        B.stop_if_outdated()
        self.assertFalse(B.watching())
        self.assertIsNone(p.poll())

    def test_real_old_board_is_stopped(self):
        p, record = self.start()
        self.assertIsNotNone(record)
        threading.Thread(target=p.wait, daemon=True).start()
        B.stop_if_outdated()
        self.assertEqual(p.wait(timeout=5), -15)

    def test_missing_and_invalid_records_are_ignored(self):
        self.assertFalse(B.watching())
        for value in ('', 'not-a-pid', '-1 /fake/board.py', '1 /fake/board.py bad'):
            self.pidfile.write_text(value)
            B.stop_if_outdated()
            self.assertFalse(B.watching(), value)


if __name__ == '__main__':
    unittest.main()
