"""소개 페이지를 만든다. 원본은 src.html, 그림·영상은 assets/ (shots.py·frames.py 로 데모 데이터에서 다시 찍는다).
  python3 site/build.py  →  docs/index.html (GitHub Pages)"""
import base64, os, re
os.chdir(os.path.dirname(os.path.abspath(__file__)))
s = open('src.html', encoding='utf-8').read()
def emb(m):
    n = m.group(1)
    if n.endswith('.mp4') or n.endswith('.webp'):
        return 'data:%s;base64,' % ('video/mp4' if n.endswith('.mp4') else 'image/webp') + base64.b64encode(open('assets/' + n, 'rb').read()).decode()
    return 'data:image/png;base64,' + base64.b64encode(open('assets/%s.png' % n, 'rb').read()).decode()
s = re.sub(r'\{\{([a-z.0-9-]+)\}\}', emb, s)
open('../docs/index.html', 'w', encoding='utf-8').write(s)
print('ok', len(s))
