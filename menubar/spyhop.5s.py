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
ORCA_ICON = 'iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAACPElEQVR4nOyXy0tXQRTHv1kZZgVGWoRFuCmiIAh6Eu2iRUS0qIja9aJ/oFW0a9eytQtBUBBd6MadCIoioiAKLgQfKD4QX/gG/R7mXLwMM797594f/DYe+PCb15n7nTl3ztxfGUpsZSixHQs4ieLYDfKSvCI1ZJ8sp3E8hex2nnwmX8k9R38veUMWCk1yAtnsMWkllxPGDZAnZM83IEsI3pMOmB1Isqtkigz6BoTugMS5HWHC+8lDFEGArHicXEG4VZEVV0fIMfyT8eEi+ravM+0OXCQzpELrszAvoWzvJHlOfsN9qt6qX6Nr4rTH8Evs4W3kI9mK9XfBvOl/Lb9FFfrdN3FaAZ9i5W/WwyPbdrR16e8OcgiQo3RXy7swq3LZO0dbt/56s2Kal/BFrFwOcxRtk4z4yNEe7cAqcgi4Y9WbyU9SR66TX6Te4ddHhrWcKwQ3rbrkg//Jbvihv7LIXeQQUIdwayBDWr5F1nwD04TgHMJsEyYskUkI15FDwBmE2T8yZwnw7kCaEIQK6LTq1+DOG6kFXECYDVn1mkKDkwRUIuzCmicbVlsVcgioQJiNOuavRICASzApVV6cWoTHfwImSUX+Z0m1tkkCW7Idouu4XAe8hv+KPoDJbjKuW+vRHM9gPtUeJPi3wNyke7YAWemaCpH02UTGtE8+Jj7g6EJKskL+khElJPu2AOiA0/B/QD6FWaVMVm31zetDhR6P/32YO2Ek3pj1s1yOVq2Wp+G/ohMtq4CiWcn/Gx4CAAD//15abGcAAAAGSURBVAMAyOxd/B59GW0AAAAASUVORK5CYII='  # 스파이홉 범고래 (메뉴바 색에 맞춰 칠해지는 템플릿 이미지)
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
