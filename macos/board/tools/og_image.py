#!/usr/bin/env python3
"""링크 미리보기(og:image)용 docs/og.png 를 만든다. 보드 그림은 demo_screens 가 찍은 최신 화면을 쓴다.

  python3 tools/demo_screens.py && python3 tools/og_image.py

og.png 는 디스코드·X·슬랙에 링크를 붙일 때 가장 먼저 보이는 한 장이라, 보드 화면이 바뀌면 같이 다시 만든다.
헤드리스 크롬 레이아웃에 맡기면 보드 아래쪽이 잘려서, 치수를 직접 계산해 Pillow 로 합성한다.
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import demo_screens as D

DOCS = os.path.join(D.ROOT, '..', '..', 'docs')
BOARD = os.path.join(DOCS, 'screenshots', 'board.png')
OUT = os.path.join(DOCS, 'og.png')

W, H = 1200, 630
SS = 2                      # 2배로 그린 뒤 줄여서 글자를 또렷하게
BG = (246, 247, 249)
INK = (25, 31, 40)
SUB = (78, 89, 104)
TITLE = 'Spyhop'
TAGLINE = 'Every AI coding session on one board, each with its own progress'

FONT = '/System/Library/Fonts/SFNS.ttf'
FALLBACK = '/System/Library/Fonts/Helvetica.ttc'
TOP, GAP, SIDE, BOTTOM, RADIUS = 46, 26, 60, 26, 14


def font(size):
    try:
        return ImageFont.truetype(FONT, size * SS)
    except OSError:
        return ImageFont.truetype(FALLBACK, size * SS)


def centered(draw, y, text, f, fill):
    x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=f)
    draw.text(((W * SS - (x1 - x0)) / 2 - x0, y), text, font=f, fill=fill)
    return y1 - y0


def rounded(img, radius):
    mask = Image.new('L', img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.size[0] - 1, img.size[1] - 1), radius, fill=255)
    out = Image.new('RGBA', img.size)
    out.paste(img, (0, 0), mask)
    return out


def main():
    if not os.path.exists(BOARD):
        raise SystemExit('먼저 tools/demo_screens.py 로 board.png 를 만드세요: ' + BOARD)
    board = Image.open(BOARD).convert('RGB')
    bw, bh = board.size

    title_f, tag_f = font(56), font(21)
    head = TOP + 62 + 14 + 28 + GAP          # 제목 + 부제 + 사이 여백
    avail_h = H - head - BOTTOM
    card_w = W - SIDE * 2
    if card_w * bh / bw > avail_h:           # 높이가 모자라면 폭을 줄여 보드 전체가 들어가게 한다
        card_w = int(avail_h * bw / bh)
    card_h = math.ceil(card_w * bh / bw)

    im = Image.new('RGB', (W * SS, H * SS), BG)
    d = ImageDraw.Draw(im)
    centered(d, TOP * SS, TITLE, title_f, INK)
    centered(d, (TOP + 62 + 14) * SS, TAGLINE, tag_f, SUB)

    shot = rounded(board.resize((card_w * SS, card_h * SS), Image.LANCZOS), RADIUS * SS)
    cx, cy = (W - card_w) // 2 * SS, head * SS
    shadow = Image.new('RGBA', im.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (cx, cy + 6 * SS, cx + card_w * SS, cy + (card_h + 6) * SS), RADIUS * SS, fill=(16, 24, 40, 38))
    im.paste(Image.alpha_composite(im.convert('RGBA'), shadow.filter(ImageFilter.GaussianBlur(9 * SS))).convert('RGB'), (0, 0))
    im.paste(shot, (cx, cy), shot)

    im.resize((W, H), Image.LANCZOS).save(OUT, 'PNG', optimize=True)
    print('wrote %s  (보드 %dx%d -> 카드 %dx%d)' % (OUT, bw, bh, card_w, card_h))


if __name__ == '__main__':
    main()
