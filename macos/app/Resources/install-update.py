#!/usr/bin/python3
"""앱 종료 뒤 설치하고 다시 연다. 사용자 세션과 보드 데이터는 건드리지 않는다."""
import argparse
import fcntl
import json
import os
import plistlib
import shutil
import subprocess
import sys
import time
import tempfile
from pathlib import Path


def run(args, timeout=180):
    return subprocess.run(args, check=True, stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          timeout=timeout)


def validate(app, version):
    with (app / 'Contents/Info.plist').open('rb') as stream:
        info = plistlib.load(stream)
    if (info.get('CFBundleIdentifier') != 'io.github.leeleelee3264.spyhop'
            or info.get('CFBundleShortVersionString') != version
            or info.get('CFBundleExecutable') != 'Spyhop'
            or not os.access(app / 'Contents/MacOS/Spyhop', os.X_OK)):
        raise ValueError('Invalid update bundle')
    run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(app)])


def replace(app, staged, version):
    """같은 파일시스템에 먼저 복사한 뒤 이름을 바꾼다. 실패 시 이전 앱을 복원한다."""
    import uuid
    suffix = str(uuid.uuid4())
    incoming = app.with_name('.Spyhop-update-' + suffix + '.app')
    backup = app.with_name('.Spyhop-backup-' + suffix + '.app')
    moved = False
    try:
        run(['/usr/bin/ditto', str(staged), str(incoming)])
        validate(incoming, version)
        app.rename(backup)
        moved = True
        incoming.rename(app)
        run(['/usr/bin/open', '-n', str(app)], timeout=30)
    except Exception:
        if moved:
            if app.exists():
                shutil.rmtree(app)
            backup.rename(app)
        raise
    finally:
        if incoming.exists():
            shutil.rmtree(incoming)
    # 새 앱을 여는 데 성공한 뒤에만 백업을 지운다.
    shutil.rmtree(backup, ignore_errors=True)


def install(args):
    app = Path(args.app)
    # 앱이 정상 종료할 때까지 기다리고, 끝나지 않으면 현재 앱을 유지한다.
    deadline = time.monotonic() + 60
    while True:
        try:
            os.kill(args.pid, 0)
        except ProcessLookupError:
            break
        if time.monotonic() >= deadline:
            raise TimeoutError('Spyhop did not quit')
        time.sleep(.1)
    # 준비하는 동안 다른 업데이트가 먼저 적용됐으면 덮어쓰지 않는다.
    validate(app, args.from_version)
    if args.brew:
        env = dict(os.environ, HOMEBREW_NO_AUTO_UPDATE='1', HOMEBREW_NO_ENV_HINTS='1')
        subprocess.run([args.brew, 'upgrade', '--cask', 'leeleelee3264/tap/spyhop'],
                       check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=600, env=env)
        validate(app, args.version)
        run(['/usr/bin/open', '-n', str(app)], timeout=30)
    else:
        validate(Path(args.staged), args.version)
        replace(app, Path(args.staged), args.version)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--app', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--from-version', required=True)
    parser.add_argument('--result', required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--brew')
    mode.add_argument('--staged')
    args = parser.parse_args()
    result = Path(args.result)
    result.parent.mkdir(parents=True, exist_ok=True)
    # 여러 앱 사본이 동시에 교체하는 것을 막는다.
    with (result.parent / 'update.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 1
        try:
            install(args)
        except Exception:
            # 내부 경로와 명령 출력을 UI에 그대로 내보내지 않는다.
            temp = result.with_suffix('.tmp')
            temp.write_text(json.dumps({'error': 'The update could not be completed. Please try again. If you use Homebrew, run brew upgrade --cask spyhop.'}))
            temp.replace(result)
            if Path(args.app).exists():
                try:
                    run(['/usr/bin/open', '-n', args.app], timeout=30)
                except Exception:
                    pass
            return 1
        finally:
            # 실행 중인 파일을 지워도 파이썬은 이미 읽은 코드를 마저 실행한다.
            work = Path(__file__).resolve().parent
            if work.name.startswith('spyhop-update-') and work.parent == Path(tempfile.gettempdir()).resolve():
                shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
