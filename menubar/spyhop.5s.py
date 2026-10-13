#!/usr/bin/env python3
# <swiftbar.title>세션 보드</swiftbar.title>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideLastUpdated>true</swiftbar.hideLastUpdated>
# <swiftbar.hideDisappear>true</swiftbar.hideDisappear>
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
"""메뉴바 항목: 오르카 세션 요약을 보여주고, 누르면 그 창으로 이동한다.
board.py 감시가 꺼져 있으면 Claude·Codex 가 떠 있을 때 다시 켠다."""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
BOARD = os.path.join(os.path.dirname(HERE), 'board.py')
STATE = '/tmp/progress-board/state.json'
PIDFILE = '/tmp/progress-board/watch.pid'
ORCA = '/usr/local/bin/orca'


def watcher_alive():
    try:
        with open(PIDFILE) as f:
            os.kill(int(f.read().split()[0]), 0)  # "pid 코드경로"
        return True
    except (OSError, ValueError, IndexError):
        return False


def agents_running():
    # Claude Code 는 프로세스 이름이 버전 번호(예: 2.1.286)로 보인다
    out = subprocess.run(['ps', '-axo', 'comm='], capture_output=True, text=True).stdout.split()
    return any(c in ('codex', 'claude') or c.replace('.', '').isdigit() and c.count('.') == 2 for c in out)


def ensure_watcher():
    if not watcher_alive() and agents_running():
        os.makedirs('/tmp/progress-board', exist_ok=True)
        subprocess.Popen(['/usr/bin/python3', BOARD, '--ensure'], stdout=subprocess.DEVNULL,
                         stderr=open('/tmp/progress-board/watch.log', 'a'), start_new_session=True)


def server_up():
    import socket
    try:
        socket.create_connection(('127.0.0.1', 47613), timeout=0.3).close()
        return True
    except OSError:
        return False


def waited(sec):
    sec = max(0, int(time.time() - sec))
    return 'now' if sec < 60 else '%dm' % (sec // 60) if sec < 3600 else '%dh' % (sec // 3600)


def q(x):
    # 따옴표로 감싸는 값 안의 따옴표는 바꾼다
    return x.replace('"', "'")


def clean(x):
    return (x or '').replace('|', '/').replace('\n', ' ')


STEP_MARK = {'done': '✅', 'now': '🟠', 'blocked': '❗', 'left': '⚪'}
STEP_ICON = {'done': ('checkmark.circle.fill', '#22a06b'), 'now': ('circle.inset.filled', '#e2a300'),
             'blocked': ('exclamationmark.circle.fill', '#e2483d'), 'left': ('circle.dotted', '#8590a2')}
ORCA_ICON = 'iVBORw0KGgoAAAANSUhEUgAAACgAAAAoCAYAAACM/rhtAAAABmJLR0QA/wD/AP+gvaeTAAAC2UlEQVRYhc3YT2hUVxTH8c8kVmMa0JJYLLQESgMitQtdSBZCi4JBV7pqcddF6aJCFq1dSEEUW3Ehgi78A9JNli7qSrA1olgrItWFpaEhokRRaG3in6opzXRxJ8ljOu/vzBv6gzPMm3n3nO+7f86593Vqn7pRwT9tjBmrTgzhGG5gBtWaPcZFfIW32g22Ap/jdgQoyV7iIJaUDdaPU7WAWcDq7QpeKwNsEb7E84JgUbuEV1oJ14fRFoBFbW+r4Pox3mK4qjASTS+cNzFRAtycHW4GrhvXS4Sr4ncsLgr4bclwc/ZBEbhtbQD7Hl9jd164btwtGe6hhTSzKS/gnpLhqjgXibc0D9wyTLUB8Ehd3I75jxTtrEHG6TI+xWp0CTuW17FdSORZNVZ3nak+d4ifexcwmNK+gn0x7eut3lemsrclxtlpoQ5nUUV67pzx33lXyeJ8pIGzKfl3HmmA13L6Q+jiPxs4O5nTTxeepAB+E9c4aZFswPIGv/+WE3ArelLuORv3RxLg+zG/96YEq/e/K+WeR/gxh895jWo8HDdlnMD4IsZH1E4UgeuQPG8+zuDjI+EElwa4sQjgQIrTv/GJcHqr16s4hNkMcL9KGY24XLYm5QEW4TiG8R1+EarNu/hQcuWJ6mgNNLd2Kb/2PhR6O1Fxq7i/yFPl1AE8K9r4jHJ7b0JI4KmK68Gsc6ioPsOLZhyUeTAaaQZsTmMlwU3INjqp+9R7JQFmPWvM7wEa5cE+5czBp/ghEmMVVgpn4Jd4ICTuP4TNxRQLWXwQO7AZ7yQE+avm4AGmcwJO19qlxRgX3h+exE9wVbHhuiW8C0wKNiBsGG4VjHG1UvvSrO4L5e5R7bpXOES90azjKGBV6NKz+Bl3hHnTI1SWtcJr3fWyb7fqVSjGkFD0k4YqqgHh9cSk7EM1if05YwxjqGhPEHLVOmE/9x7etrD6p4WcdxPnhcQ/20Ss/6/+BaOJWhj9+/K/AAAAAElFTkSuQmCC'  # 스파이홉 범고래 (메뉴바 색에 맞춰 칠해지는 템플릿 이미지)
SWITCH = 'bash=%s param1=terminal param2=switch param3=--terminal param4=%%s terminal=false' % ORCA


def main():
    ensure_watcher()
    try:
        with open(STATE, encoding='utf-8') as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = {'at': 0, 'sessions': []}
    stale = time.time() - state.get('at', 0) > 120
    ss = [] if stale else state['sessions']
    wait = [s for s in ss if s['status'] == 'wait']
    busy = [s for s in ss if s['status'] == 'busy']

    # 메뉴바: 칸반 모양 단색 아이콘 + 내 차례 수. 누르면 보드 패널(웹뷰)이 뜬다
    icon = 'rectangle.split.3x1.fill' if wait else 'rectangle.split.3x1'
    text = str(len(wait)) if wait else ('' if not ss else '·%d' % len(busy))
    if server_up():
        print('%s | templateImage=%s width=20 height=20 href=http://127.0.0.1:47613/panel webview=true webvieww=380 webviewh=560' % (text, ORCA_ICON))
        return
    print('%s | templateImage=%s width=20 height=20' % (text, ORCA_ICON))
    print('---')
    print('My turn %d · Working %d | size=13' % (len(wait), len(busy)))

    ws = None
    for s in ss:
        if s['ws'] != ws:
            ws = s['ws']
            print('---')
            print('📁  %s | size=12' % clean(ws))
        mark = '🔴' if s['status'] == 'wait' else '🔵'
        progress = '%d/%d' % (s['done'], s['total']) if s['total'] else '—'
        when = waited(s['since']) + (' waiting' if s['status'] == 'wait' else '')
        title = clean(s['title'])
        if len(title) > 30:
            title = title[:29] + '…'
        print('%s  %s    %s · %s | tooltip="%s"' % (mark, title, progress, when, q(clean(s.get('summary'))[:200] or title)))
        # 옆으로 펼치는 메뉴: 요약 → 단계 → 모델 → 이동
        if s.get('summary'):
            print('--%s | size=11 length=60 tooltip="%s"' % (clean(s['summary']), q(clean(s['summary']))))
            print('-----')
        for st in s.get('steps') or []:
            print('--%s  %s | size=13' % (STEP_MARK.get(st['state'], '⚪'), clean(st['label'])))
        print('-----')
        if s.get('model'):
            print('--🧠  %s | size=12' % clean(s['model']))
        print('--↗  Go to session | %s' % (SWITCH % s['handle']))

    print('---')
    print('🗂  Open board | bash=/usr/bin/open param1=/tmp/progress-board/index.html terminal=false')
    if stale:
        print('💤 Watcher off · starts automatically when Claude/Codex runs | size=11')


if __name__ == '__main__':
    main()
