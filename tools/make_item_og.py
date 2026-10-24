#!/usr/bin/env python3
"""紹介ページごとの共有画像（1200×630）を og-items/{ID}.png に作るスクリプト。

  python3 tools/make_item_og.py

- 毎朝の「サイトを更新」で、サイトを作る前に動く（Pillow を使う）。できた画像は build.py が /images/og/{ID}.png として公開し、
  紹介ページの og:image にする。画像がなければ観測所共通の共有画像のまま。
- 載せるのはタイプ・転機・段階とタイトル。掲載先の画像は使わない（観測所のページだとわかるように）。
  見た目は転機のページの共有画像（tools/make_og_images.py）とそろえる：生成りの地、左に黄色の帯、空色の小見出し、黒の見出し、右下にアンテナ。
- 見出しの書体 Zen Kaku Gothic New は tools/fonts/ にダウンロードする（リポジトリには入れない）。
- og-items/ はリポジトリに入れない（毎回作り直す）。
"""
import csv
import io
import os
import sys
import urllib.request

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402  CSVの取得と、掲載の読み取りは build.py と同じものを使う

FONTS = os.path.join(ROOT, "tools", "fonts")
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/zenkakugothicnew/%s.ttf"
OUT = os.path.join(ROOT, "og-items")
ANTENNA = os.path.join(ROOT, "tools", "og_antenna.png")
W, H = 1200, 630
BASE, INK, SKY, SUB, YELLOW = "#fbfaf5", "#1a1d23", "#1874b8", "#5e636b", "#f5c518"
LEFT, RIGHT = 106, 1200 - 96
NO_START = "、。，．・ー）」』】！？ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮ"  # 行の頭に来ないようにする文字
NO_END = "（「『【"  # 行の終わりに来ないようにする文字


def font(name, size):
    os.makedirs(FONTS, exist_ok=True)
    path = os.path.join(FONTS, name + ".ttf")
    if not os.path.exists(path):
        urllib.request.urlretrieve(FONT_URL % name, path)
    return ImageFont.truetype(path, size)


def wrap(text, fnt, width):
    """幅に収まるように折り返す。行頭・行末の禁則を少しだけ守る。"""
    lines, line = [], ""
    for ch in text:
        if fnt.getlength(line + ch) <= width or not line:
            line += ch
            continue
        if ch in NO_START and len(line) > 1:  # 前の行の最後の1文字を次の行に送る
            lines.append(line[:-1])
            line = line[-1] + ch
        elif line[-1] in NO_END and len(line) > 1:
            lines.append(line[:-1])
            line = line[-1] + ch
        else:
            lines.append(line)
            line = ch
    if line:
        lines.append(line)
    return lines


def title_lines(title):
    """大きい字から試して、3行に収まる大きさを選ぶ。収まらなければ最後の行を「…」で切る。"""
    for size in (76, 68, 60, 54):
        fnt = font("ZenKakuGothicNew-Black", size)
        lines = wrap(title, fnt, RIGHT - LEFT)
        if len(lines) <= 3:
            return fnt, size, lines
    lines = lines[:3]
    while fnt.getlength(lines[2] + "…") > RIGHT - LEFT and lines[2]:
        lines[2] = lines[2][:-1]
    lines[2] += "…"
    return fnt, size, lines


def kicker(item):
    tenki = "どの転機にも" if build.COMMON in item["tenki"] else "・".join(item["tenki"])
    return "｜".join(x for x in [item["kind"], tenki, "・".join(item["stages"])] if x)


def make(item, antenna):
    im = Image.new("RGB", (W, H), BASE)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 27, H), fill=YELLOW)
    small = font("ZenKakuGothicNew-Bold", 32)
    k = kicker(item)
    while small.getlength(k) > RIGHT - LEFT and len(k) > 4:
        k = k[:-2] + "…"
    d.text((LEFT, 78), k, font=small, fill=SKY)
    title = item["title"].replace("―", "ー").replace("—", "ー")  # 書体にない長いダッシュは長音に
    fnt, size, lines = title_lines(title)
    y = 150
    for line in lines:
        d.text((LEFT, y), line, font=fnt, fill=INK)
        y += int(size * 1.32)
    d.rectangle((LEFT, 500, LEFT + 120, 503), fill=INK)
    d.text((LEFT, 528), "あしたの転機観測所", font=font("ZenKakuGothicNew-Bold", 30), fill=INK)
    d.text((LEFT + 300, 535), "ashitano-tenki.github.io", font=font("ZenKakuGothicNew-Bold", 22), fill=SUB)
    if antenna:
        im.paste(antenna, (1000, 415))
    im.save(os.path.join(OUT, item["id"] + ".png"), optimize=True)


def main():
    items = build.parse_rows(build.fetch_csv(build.CONF["csv_url"]))
    listed = [it for it in items if it["listed"]]
    os.makedirs(OUT, exist_ok=True)
    keep = set()
    antenna = Image.open(ANTENNA).convert("RGB") if os.path.exists(ANTENNA) else None
    for it in listed:
        make(it, antenna)
        keep.add(it["id"] + ".png")
    for name in os.listdir(OUT):  # 掲載が終わったものの画像は消す
        if name not in keep:
            os.remove(os.path.join(OUT, name))
    print("紹介ページの共有画像を作りました: %d件" % len(listed))


if __name__ == "__main__":
    main()
