"""격리된 앱 폴더에서 교체, 실패 복구, Cask 분기를 검사한다."""
import argparse
import importlib.util
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'Resources/install-update.py'
spec = importlib.util.spec_from_file_location('installer', SOURCE)
I = importlib.util.module_from_spec(spec)
spec.loader.exec_module(I)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='spyhop-installer-test-')
        self.root = Path(self.tmp.name)
        self.app = self.bundle('installed/Spyhop.app', '2.0.0')
        self.staged = self.bundle('staged/Spyhop.app', '2.1.0')
        self.commands = []
        self.ready_check = patch.object(I, 'wait_ready')
        self.ready_check.start()

    def tearDown(self):
        self.ready_check.stop()
        self.tmp.cleanup()

    def bundle(self, name, version, identifier='io.github.leeleelee3264.spyhop'):
        app = self.root / name
        (app / 'Contents/MacOS').mkdir(parents=True)
        (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({
            'CFBundleIdentifier': identifier, 'CFBundleShortVersionString': version,
            'CFBundleExecutable': 'Spyhop',
        }))
        exe = app / 'Contents/MacOS/Spyhop'
        exe.write_text('#!/bin/sh\nexit 0\n')
        exe.chmod(0o755)
        return app

    def run_command(self, args, **kwargs):
        self.commands.append(args)
        if args[0] == '/usr/bin/ditto':
            shutil.copytree(args[1], args[2])

    def version(self):
        return plistlib.loads((self.app / 'Contents/Info.plist').read_bytes())['CFBundleShortVersionString']

    def test_replace_and_reopen_preserves_settings(self):
        settings = self.root / 'settings.json'
        settings.write_text('{"theme":"dark"}')
        with patch.object(I, 'run', side_effect=self.run_command):
            I.replace(self.app, self.staged, '2.1.0')
        self.assertEqual(self.version(), '2.1.0')
        self.assertEqual(settings.read_text(), '{"theme":"dark"}')
        self.assertEqual(self.commands[-1][:3], ['/usr/bin/open', '-n', str(self.app)])
        self.assertEqual(self.commands[-1][3:5], ['--args', '--update-token'])
        self.assertEqual(list(self.app.parent.glob('.Spyhop-*')), [])

    def test_bad_signature_keeps_original(self):
        def command(args, **kwargs):
            if args[0] == '/usr/bin/codesign':
                raise subprocess.CalledProcessError(1, args)
            self.run_command(args, **kwargs)
        with patch.object(I, 'run', side_effect=command):
            with self.assertRaises(subprocess.CalledProcessError):
                I.replace(self.app, self.staged, '2.1.0')
        self.assertEqual(self.version(), '2.0.0')
        self.assertFalse(any(c[0] == '/usr/bin/open' for c in self.commands))

    def test_open_failure_restores_original(self):
        def command(args, **kwargs):
            if args[0] == '/usr/bin/open':
                raise subprocess.CalledProcessError(1, args)
            self.run_command(args, **kwargs)
        with patch.object(I, 'run', side_effect=command):
            with self.assertRaises(subprocess.CalledProcessError):
                I.replace(self.app, self.staged, '2.1.0')
        self.assertEqual(self.version(), '2.0.0')
        self.assertEqual(list(self.app.parent.glob('.Spyhop-*')), [])

    def test_unhealthy_launch_restores_original(self):
        with patch.object(I, 'run', side_effect=self.run_command), \
                patch.object(I, 'wait_ready', side_effect=TimeoutError), patch.object(I, 'stop_attempt') as stop:
            with self.assertRaises(TimeoutError):
                I.replace(self.app, self.staged, '2.1.0')
        self.assertEqual(self.version(), '2.0.0')
        stop.assert_called_once()

    def test_ready_ack_requires_matching_token_version_and_app(self):
        self.ready_check.stop()
        ready = self.root / 'update-ready.json'
        record = {'token': 'expected', 'version': '2.1.0', 'app': str(self.app), 'pid': os.getpid()}
        for key, value in [('token', 'stale'), ('version', '2.0.0'), ('app', '/another/app')]:
            ready.write_text(json.dumps(dict(record, **{key: value})))
            with patch.object(I.time, 'sleep'), self.assertRaises(TimeoutError):
                I.wait_ready(ready, 'expected', self.app, '2.1.0', timeout=.005)
        ready.write_text(json.dumps(record))
        I.wait_ready(ready, 'expected', self.app, '2.1.0', timeout=3)
        self.assertFalse(ready.exists())
        self.ready_check.start()

    def test_invalid_id_and_wrong_version_rejected(self):
        bad = self.bundle('other.app', '2.1.0', 'another.app')
        with patch.object(I, 'run', side_effect=self.run_command):
            for app, version in [(bad, '2.1.0'), (self.staged, '2.2.0')]:
                with self.assertRaises(ValueError):
                    I.validate(app, version)

    def test_wait_for_quit_before_touching_app(self):
        args = argparse.Namespace(app=str(self.app), pid=123, version='2.1.0',
                                  from_version='2.0.0', brew=None, staged=str(self.staged))
        with patch.object(I.os, 'kill', side_effect=[None, ProcessLookupError]), \
                patch.object(I.time, 'sleep') as sleep, \
                patch.object(I, 'run', side_effect=self.run_command):
            I.install(args)
        sleep.assert_called_once_with(.1)
        self.assertEqual(self.version(), '2.1.0')

    def test_refuses_concurrent_version_change(self):
        args = argparse.Namespace(app=str(self.app), pid=123, version='2.1.0',
                                  from_version='1.9.0', brew=None, staged=str(self.staged))
        with patch.object(I.os, 'kill', side_effect=ProcessLookupError), \
                patch.object(I, 'run', side_effect=self.run_command):
            with self.assertRaises(ValueError):
                I.install(args)
        self.assertEqual(self.version(), '2.0.0')

    def test_brew_upgrade_runs_after_quit_and_reopens(self):
        args = argparse.Namespace(app=str(self.app), pid=123, version='2.1.0',
                                  from_version='2.0.0', brew='/example/brew', staged=None)
        def brew(command, **kwargs):
            self.assertEqual(command, ['/example/brew', 'upgrade', '--cask', 'leeleelee3264/tap/spyhop'])
            shutil.rmtree(self.app)
            shutil.copytree(self.staged, self.app)
        with patch.object(I.os, 'kill', side_effect=ProcessLookupError), \
                patch.object(I.subprocess, 'run', side_effect=brew), \
                patch.object(I, 'run', side_effect=self.run_command):
            I.install(args)
        self.assertEqual(self.version(), '2.1.0')
        self.assertEqual(self.commands[-1][:3], ['/usr/bin/open', '-n', str(self.app)])

    def test_brew_failure_after_removal_restores_original(self):
        args = argparse.Namespace(app=str(self.app), pid=123, version='2.1.0',
                                  from_version='2.0.0', brew='/example/brew', staged=None)
        def failed_brew(command, **kwargs):
            shutil.rmtree(self.app)
            raise subprocess.CalledProcessError(1, command)
        with patch.object(I.os, 'kill', side_effect=ProcessLookupError), \
                patch.object(I.subprocess, 'run', side_effect=failed_brew), \
                patch.object(I, 'run', side_effect=self.run_command):
            with self.assertRaises(subprocess.CalledProcessError):
                I.install(args)
        self.assertEqual(self.version(), '2.0.0')

    def test_brew_unhealthy_launch_restores_original(self):
        args = argparse.Namespace(app=str(self.app), pid=123, version='2.1.0',
                                  from_version='2.0.0', brew='/example/brew', staged=None, reinstall=True)
        def reinstall(command, **kwargs):
            self.assertEqual(command[1], 'reinstall')
            shutil.rmtree(self.app)
            shutil.copytree(self.staged, self.app)
        with patch.object(I.os, 'kill', side_effect=ProcessLookupError), \
                patch.object(I.subprocess, 'run', side_effect=reinstall), \
                patch.object(I, 'run', side_effect=self.run_command), \
                patch.object(I, 'wait_ready', side_effect=TimeoutError), patch.object(I, 'stop_attempt'):
            with self.assertRaises(TimeoutError):
                I.install(args)
        self.assertEqual(self.version(), '2.0.0')

    @unittest.skipUnless(os.environ.get('SPYHOP_TEST_APP'), 'Set SPYHOP_TEST_APP to a signed test bundle')
    def test_real_signed_bundle_copy_and_verify(self):
        # 실제 ditto/codesign을 실행하되 open은 가짜 실행기로 대체한다.
        source = Path(os.environ['SPYHOP_TEST_APP'])
        version = plistlib.loads((source / 'Contents/Info.plist').read_bytes())['CFBundleShortVersionString']
        real_run = I.run
        def command(args, **kwargs):
            if args[0] != '/usr/bin/open':
                return real_run(args, **kwargs)
            self.commands.append(args)
        with patch.object(I, 'run', side_effect=command):
            I.replace(self.app, source, version)
        self.assertEqual(self.version(), version)
        I.validate(self.app, version)

    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc') and os.environ.get('SPYHOP_LIVE_UPDATE_TEST') == '1',
                         'Set SPYHOP_LIVE_UPDATE_TEST=1 on macOS for the launch test')
    def test_real_helper_quits_replaces_and_launches_new_app(self):
        marker = self.root / 'launched-version'
        source = self.root / 'main.swift'
        source.write_text('import Foundation\n'
                          'let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as! String\n'
                          'try version.write(toFile: ' + json.dumps(str(marker)) + ', atomically: true, encoding: .utf8)\n'
                          'let args = CommandLine.arguments\nlet token = args[args.firstIndex(of: "--update-token")! + 1]\n'
                          'let ready: [String: Any] = ["token": token, "pid": ProcessInfo.processInfo.processIdentifier, "version": version, "app": Bundle.main.bundleURL.resolvingSymlinksInPath().path]\n'
                          'try JSONSerialization.data(withJSONObject: ready).write(to: URL(fileURLWithPath: '
                          + json.dumps(str(self.root / 'update-ready.json')) + '))\nThread.sleep(forTimeInterval: 3)\n')
        subprocess.run(['swiftc', str(source), '-o', str(self.staged / 'Contents/MacOS/Spyhop')],
                       check=True, capture_output=True)
        for app in (self.app, self.staged):
            subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(app)],
                           check=True, capture_output=True)
        work = Path(tempfile.mkdtemp(prefix='spyhop-update-'))
        helper = work / 'install.py'
        shutil.copy2(SOURCE, helper)
        result = self.root / 'result.json'
        old = subprocess.Popen(['/bin/sleep', '60'])
        installer = subprocess.Popen(['/usr/bin/python3', str(helper), '--pid', str(old.pid),
                                      '--app', str(self.app), '--version', '2.1.0', '--from-version', '2.0.0',
                                      '--staged', str(self.staged), '--result', str(result)])
        try:
            time.sleep(.3)
            self.assertEqual(self.version(), '2.0.0')
            self.assertFalse(marker.exists())
            old.terminate()
            old.wait(timeout=5)
            self.assertEqual(installer.wait(timeout=30), 0)
            deadline = time.monotonic() + 10
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(.1)
            self.assertEqual(marker.read_text(), '2.1.0')
            self.assertEqual(self.version(), '2.1.0')
            self.assertFalse(result.exists())
            self.assertFalse(work.exists())
        finally:
            if old.poll() is None:
                old.terminate(); old.wait(timeout=5)
            if installer.poll() is None:
                installer.terminate(); installer.wait(timeout=5)
            shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
