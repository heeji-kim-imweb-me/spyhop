"""카드를 끌어 다른 칸으로 옮기는 장면을 프레임으로 찍어 영상으로 만든다 (데모 데이터)."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.expanduser('~/workspace/personal/spyhop/tools'))
import demo_screens as D  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FR = os.path.join(HERE, 'frames')
os.makedirs(FR, exist_ok=True)
_patch = D.patch


def patch(mode):
    _patch(mode)
    D.B.cached_summary = lambda log: D.B.summarize(log)


D.patch = patch
D.patch('orca')
D.B.build()
base = open(D.B.OUT, encoding='utf-8').read().replace('location.reload()', '0')

CSS = ('*{transition:none!important;animation:none!important}.sea .orca{display:none!important}'
       '.card.moving:after{background-position:var(--bp,0) 0,0 0!important}#toast{transition:none!important}')
# t(0~1) 에 맞춰 장면을 그린다. 실제 보드 코드의 끌기 함수를 그대로 쓰고, 위치만 시간에 맞춰 정한다
JS = r"""
function ease(x){return x<.5?4*x*x*x:1-Math.pow(-2*x+2,3)/2}
function lerp(a,b,k){return a+(b-a)*k}
var T=__T__,c=document.querySelector('main .card'),cols=document.querySelectorAll('main .col'),to=cols[2];
var r0=c.getBoundingClientRect(),tr=to.getBoundingClientRect();
var gx=tr.left+20,gy=tr.top+60;
if(T>=0.1&&T<0.6){var k=ease(Math.min(1,(T-0.1)/0.45));
  startDrag(c,{clientX:r0.left+40,clientY:r0.top+20});
  drag.float.style.transform='translate('+lerp(r0.left,gx,k)+'px,'+lerp(r0.top,gy,k)+'px) rotate('+(1.5*Math.min(1,k*4))+'deg) scale('+(1+0.03*Math.min(1,k*4))+')';
  if(k>0.55)to.classList.add('drop')}
if(T>=0.6){var more=to.querySelector('.more');to.insertBefore(c,more.nextSibling);recount();
  var r1=c.getBoundingClientRect(),k2=ease(Math.min(1,(T-0.6)/0.08));
  c.style.transform='translate('+lerp(gx-r1.left,0,k2)+'px,'+lerp(gy-r1.top,0,k2)+'px)';
  if(T<0.95){c.classList.add('moving');c.style.setProperty('--bp',(-60+((T-0.6)/0.35*4%1)*220)+'%')}
  if(T>=0.64){var e=document.getElementById('toast');e.textContent='Moved to infra · still working in ~/payments-api';e.className='on'}}
"""


def frame(i, t):
    page = os.path.join(D.TMP, 'f.html')
    s = base.replace('</head>', '<style>%s</style></head>' % CSS)
    s = s.replace('</body>', '<script>setTimeout(function(){%s},200)</script></body>' % JS.replace('__T__', '%.4f' % t))
    open(page, 'w', encoding='utf-8').write(s)
    out = os.path.join(FR, 'f%03d.png' % i)
    subprocess.run([D.CHROME, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--window-size=1280,560',
                    '--force-device-scale-factor=1', '--virtual-time-budget=800', '--screenshot=' + out,
                    'file://' + page + '#x'], capture_output=True)


N = 60  # 4초 · 15fps
for i in range(N):
    frame(i, i / (N - 1))
print('frames', N)
