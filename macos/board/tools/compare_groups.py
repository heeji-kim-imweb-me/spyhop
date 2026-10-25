#!/usr/bin/env python3
"""AI 주제 묶기를 한 장으로 보여 주는 비교 그림(docs/screenshots/ai-groups-compare.png).

  python3 tools/demo_screens.py && python3 tools/compare_groups.py

board.png 와 ai-groups.png 는 따로 보면 거의 똑같이 생겨서 "AI 가 주제별로 다시 묶었다"는 게 드러나지 않는다.
같은 세션들을 위아래로 붙이고 설명을 달아 차이가 보이게 한다.
"""
import os

from PIL import Image, ImageDraw, ImageFont

import demo_screens as D

SHOTS = os.path.join(D.ROOT, '..', '..', 'docs', 'screenshots')
OUT = os.path.join(SHOTS, 'ai-groups-compare.png')

W, SS = 1200, 2
BG = (246, 247, 249)
INK = (25, 31, 40)
SUB = (78, 89, 104)
SIDE, TOP, GAP, BOTTOM, RADIUS = 50, 34, 34, 40, 12
PANELS = [('board.png', 'Group by folder', 'One column per worktree or folder'),
          ('ai-groups.png', 'Group by AI topic', 'The same sessions, re-grouped by what they are actually about')]

FONT = '/System/Library/Fonts/SFNS.ttf'
FALLBACK = '/System/Library/Fonts/Helvetica.ttc'


def font(size):
    try:
        return ImageFont.truetype(FONT, size * SS)
    except OSError:
        return ImageFont.truetype(FALLBACK, size * SS)


def rounded(img, radius):
    mask = Image.new('L', img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.size[0] - 1, img.size[1] - 1), radius, fill=255)
    out = Image.new('RGBA', img.size)
    out.paste(img, (0, 0), mask)
    return out


def main():
    card_w = W - SIDE * 2
    shots = []
    for name, _, _ in PANELS:
        p = os.path.join(SHOTS, name)
        if not os.path.exists(p):
            raise SystemExit('먼저 tools/demo_screens.py 를 돌리세요: ' + p)
        im = Image.open(p).convert('RGB')
        shots.append(im.resize((card_w * SS, round(card_w * SS * im.height / im.width)), Image.LANCZOS))

    h_f, s_f = font(20), font(14)
    head = 26 + 8 + 20 + 14                       # 제목 + 설명 + 그림까지의 여백
    total = TOP + sum(head + s.height // SS + GAP for s in shots) - GAP + BOTTOM
    im = Image.new('RGB', (W * SS, total * SS), BG)
    d = ImageDraw.Draw(im)

    y = TOP
    for (name, title, note), shot in zip(PANELS, shots):
        d.text((SIDE * SS, y * SS), title, font=h_f, fill=INK)
        d.text((SIDE * SS, (y + 26) * SS), note, font=s_f, fill=SUB)
        card = rounded(shot, RADIUS * SS)
        im.paste(card, (SIDE * SS, (y + head) * SS), card)
        y += head + shot.height // SS + GAP

    im.resize((W, total), Image.LANCZOS).save(OUT, 'PNG', optimize=True)
    print('wrote %s %dx%d' % (OUT, W, total))


if __name__ == '__main__':
    main()
