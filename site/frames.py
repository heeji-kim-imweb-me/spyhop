"""세션 옮기기 영상: 기다리는 세션을 On hold 칸에 잠시 두고, 미뤄 둔 세션을 원래 칸으로 꺼낸다 (데모 데이터).
  python3 site/frames.py  →  assets/move.mp4 (컴퓨터), assets/m-move.mp4 (휴대폰)"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'macos', 'board', 'tools'))
import demo_screens as D  # noqa: E402

tag = subprocess.run(['git', '-C', HERE, 'describe', '--tags', '--abbrev=0'], capture_output=True, text=True).stdout.strip()
if tag:
    D.B.VERSION = tag.lstrip('v')
# 칸 순서는 정렬(Newest)을 따르므로 몇 분 전인지로 payments-api → On hold → web-app → infra 순서를 만든다
D.WORKTREES[:] = [('w1', 'payments-api', 1), ('w4', 'On hold', 2), ('w2', 'web-app', 3), ('w3', 'infra', 4)]
S = [list(s) for s in D.SESSIONS]
S[4][0], S[4][3] = 'w4', 7    # Shrink staging EKS node pool: 미뤄 둔 세션
S[5][3] = 30
D.SESSIONS[:] = [tuple(s) for s in S]
D.patch('orca')
D.B.outside_terms = lambda: ([], {})   # 오르카 밖 세션은 옮길 수 없으니 영상에서 뺀다
D.B.build()
base = open(D.B.OUT, encoding='utf-8').read().replace('location.reload()', '0').replace(
    "fetch('http://127.0.0.1:47613/gen'", "(function(){return new Promise(function(){})})(''")

CSS = ('*{transition:none!important;animation:none!important}.sea .orca{display:none!important}'
       '.card.moving:after{background-position:var(--bp,0) 0,0 0!important}#toast{transition:none!important}')
# T(0~1) 에 맞춰 장면을 처음부터 다시 그린다. 실제 보드의 끌기 함수를 쓰고 위치만 시간에 맞춘다
JS = r"""
function ease(x){return x<.5?4*x*x*x:1-Math.pow(-2*x+2,3)/2}
function lerp(a,b,k){return a+(b-a)*k}
function card(t){return document.querySelector('main .card[data-title="'+t+'"]')}
function col(n){return document.querySelector('main .col[data-name="'+n+'"]')}
function put(c,to){to.insertBefore(c,to.querySelector('.more').nextSibling);recount()}
function say(t){var e=document.getElementById('toast');e.textContent=t;e.className='on'}
var T=__T__;
var M=[{t:'Refund webhook signature check',to:'On hold',a:.06,b:.30,end:.46,msg:'Moved to On hold · still working in ~/payments-api'},
       {t:'Shrink staging EKS node pool',to:'infra',a:.56,b:.78,end:.94,msg:'Moved to infra'}];
M.forEach(function(m){
  var c=card(m.t),to=col(m.to);if(!c||!to||T<m.a)return;
  if(T>=m.end){put(c,to);if(m===M[M.length-1])say(m.msg);return}   // 끝난 이동은 놓인 상태로
  var r0=c.getBoundingClientRect(),tr=to.getBoundingClientRect(),gx=tr.left+20,gy=tr.top+60;
  if(T<m.b){var k=ease((T-m.a)/(m.b-m.a));
    startDrag(c,{clientX:r0.left+40,clientY:r0.top+20},{x:r0.left+40,y:r0.top+20});
    drag.float.style.transform='translate('+lerp(r0.left,gx,k)+'px,'+lerp(r0.top,gy,k)+'px) rotate('+(1.5*Math.min(1,k*4))+'deg) scale('+(1+0.03*Math.min(1,k*4))+')';
    if(k>0.55)to.classList.add('drop');return}
  put(c,to);var r1=c.getBoundingClientRect(),k2=ease(Math.min(1,(T-m.b)/0.06));
  c.style.transform='translate('+lerp(gx-r1.left,0,k2)+'px,'+lerp(gy-r1.top,0,k2)+'px)';
  if(T<m.end){c.classList.add('moving');c.style.setProperty('--bp',(-60+((T-m.b)/(m.end-m.b)*3%1)*220)+'%')}
  if(T>=m.b+.02)say(m.msg)});
"""


def shoot(w, h, scale, n):
    """장면을 n 장으로 찍어 프레임 png 경로들을 돌려준다."""
    tmp = tempfile.mkdtemp(prefix='spyhop-frames-')
    paths = []
    for i in range(n):
        page = os.path.join(tmp, 'f.html')
        s = base.replace('</head>', '<style>%s</style></head>' % CSS)
        s = s.replace('</body>', '<script>setTimeout(function(){%s},200)</script></body>' % JS.replace('__T__', '%.4f' % (i / (n - 1))))
        open(page, 'w', encoding='utf-8').write(s)
        url = 'file://' + page + '#x'
        if w < 900:  # 좁은 창은 iframe 에 담아 찍는다 (헤드리스 크롬이 좁은 창을 넓게 그림)
            fr = os.path.join(tmp, 'frame.html')
            open(fr, 'w').write('<html><body style="margin:0"><iframe src="%s" style="width:%dpx;height:%dpx;border:0;display:block">'
                                '</iframe></body></html>' % (url, w, h))
            url = 'file://' + fr
        out = os.path.join(tmp, 'f%03d.png' % i)
        subprocess.run([D.CHROME, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--window-size=%d,%d' % (w, h),
                        '--force-device-scale-factor=%s' % scale, '--virtual-time-budget=800',
                        '--screenshot=' + out, url], capture_output=True)
        paths.append(out)
    return tmp, paths


def render(name, w, h, scale, n, out):
    tmp, paths = shoot(w, h, scale, n)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', '15', '-i', os.path.join(tmp, 'f%03d.png'),
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '30', '-preset', 'slow', '-movflags', '+faststart',
                    '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2', os.path.join(HERE, 'assets', out)], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print('wrote', out)


def render_gif(w, h, scale, n, out, width=960, fps=15, colors=128):
    """ffmpeg 없이 GIF 로 만든다. 디스코드·이슈 본문처럼 mp4 를 못 붙이는 곳에 쓴다.

    프레임마다 팔레트를 따로 만들면 Pillow 가 프레임 간 차이를 못 줄여 파일이 몇 배로 커진다.
    전체 프레임을 한 장으로 이어 붙여 공용 팔레트를 만든 뒤 그 팔레트로 양자화한다.
    """
    from PIL import Image
    tmp, paths = shoot(w, h, scale, n)
    raw = []
    for p in paths:
        im = Image.open(p).convert('RGB')
        if im.width != width:
            im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        raw.append(im)
    step = max(1, len(raw) // 12)                      # 팔레트 표본: 프레임 12장 정도면 충분
    sample = raw[::step]
    strip = Image.new('RGB', (raw[0].width, raw[0].height * len(sample)))
    for i, im in enumerate(sample):
        strip.paste(im, (0, i * raw[0].height))
    pal = strip.quantize(colors=colors, method=Image.MEDIANCUT)
    frames = [im.quantize(palette=pal, dither=Image.NONE) for im in raw]
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=round(1000 / fps), loop=0, optimize=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print('wrote %s (%d프레임 · %.1f초 · %dKB)' % (out, len(frames), len(frames) / fps, os.path.getsize(out) // 1024))


if __name__ == '__main__':
    import sys
    N = 90  # 6초 · 15fps
    if '--gif' in sys.argv:
        # 홍보용 GIF: docs/screenshots/move.gif
        render_gif(1280, 560, 1, 60, os.path.join(HERE, '..', 'docs', 'screenshots', 'move.gif'), width=960, fps=15)
    else:
        render('desktop', 1280, 560, 1, N, 'move.mp4')
        render('phone', 600, 812, 1.2, N, 'm-move.mp4')
