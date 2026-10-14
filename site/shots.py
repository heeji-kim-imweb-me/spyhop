"""share 페이지용 스크린샷: 레포의 데모 데이터로 그린 화면 + 끌기·서랍·진행 막대·범고래 장면."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.expanduser('~/workspace/personal/spyhop/tools'))
import demo_screens as D  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'img')
os.makedirs(OUT, exist_ok=True)
D.OUTDIR = OUT
D.WORKTREES.append(('w4', 'docs-site', 4))  # 세션 없는 워크스페이스 → 서랍에 나온다
_patch = D.patch


def patch(mode):
    _patch(mode)
    D.B.cached_summary = lambda log: D.B.summarize(log)


D.patch = patch


def shot(html, name, w, h, hash_='#x', css='', js=''):
    page = os.path.join(D.TMP, name + '.html')
    s = open(html, encoding='utf-8').read().replace('location.reload()', '0').replace("fetch('http://127.0.0.1:47613/gen'", "(function(){return new Promise(function(){})})(''")
    s = s.replace('</head>', '<style>%s</style></head>' % css)
    if js:
        s = s.replace('</body>', '<script>setTimeout(function(){%s},300)</script></body>' % js)
    open(page, 'w', encoding='utf-8').write(s)
    out = os.path.join(OUT, name + '.png')
    subprocess.run([D.CHROME, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--window-size=%d,%d' % (w, h),
                    '--force-device-scale-factor=2', '--virtual-time-budget=3500', '--screenshot=' + out,
                    'file://' + page + hash_], capture_output=True)
    print('wrote', out)


FROZEN = '.orca{animation:none!important;transform:translateY(45%)!important}*{transition:none!important}.modal *,.card,.slot{animation:none!important}'
D.patch('orca')
D.B.build()
board = D.B.OUT
shot(board, 'board', 1280, 600, css=FROZEN)
first = open(board, encoding='utf-8').read().split('class="modal ', 1)[1].split('id="', 1)[1].split('"', 1)[0]
shot(board, 'detail', 1280, 680, hash_='#' + first, css=FROZEN)
shot(board, 'settings', 1280, 980, hash_='#settings', css=FROZEN + '#mcpu,#mmem{visibility:hidden}')
# 화면이 좁으면 카드가 진행 막대로 줄어든다
shot(board, 'bars', 1280, 400, css=FROZEN)
# 끄는 중: 손을 따라오는 카드 + 세션 없는 워크스페이스 서랍
drag_js = ("var c=document.querySelectorAll('main .card')[0],r=c.getBoundingClientRect();"
           "startDrag(c,{clientX:r.left+40,clientY:r.top+20},{x:r.left+40,y:r.top+20});drawerAt(20);"
           "setTimeout(function(){var s=document.querySelector('.drawer .slot');if(!s)return;s.classList.add('drop');var q=s.getBoundingClientRect();"
           "drag.float.style.transform='translate('+(q.left+120)+'px,'+(q.top+34)+'px) rotate(2deg) scale(1.03)'},600);")
shot(board, 'drag', 1280, 600, css=FROZEN, js=drag_js)
# 놓은 직후: 카드는 바로 새 칸에, 아래 막대로 '옮기는 중'
move_js = ("var c=document.querySelectorAll('main .card')[1],cols=document.querySelectorAll('main .col');"
           "var to=cols[cols.length-1];to.insertBefore(c,to.querySelector('.more').nextSibling);recount();c.classList.add('moving');"
           "toast('Moved to infra · still working in ~/payments-api');document.getElementById('toast').className='on';"
           "toast=function(){};")
shot(board, 'moving', 1280, 600, css=FROZEN + '#toast{opacity:1!important}', js=move_js)
# 일을 끝낸 세션 카드 위로 범고래가 고개를 내민다
peek_js = "peek();"
shot(board, 'peek', 1280, 600, css=FROZEN, js=peek_js)
D.patch('ai')
D.B.build()
shot(D.B.OUT, 'ai-groups', 1280, 600, css=FROZEN)
