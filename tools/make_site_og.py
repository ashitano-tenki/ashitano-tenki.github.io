#!/usr/bin/env python3
"""サイト全体の共有画像 assets/ogp.png（1200×630）を作る。

載っているサービスの名前のカード（頭にサイトと同じ種類の絵）をレンガ積みに敷き詰め、まん中の白い箱に📡・サイト名・副題を置く。
2026-11-23 黒田さんが3案から案Aを選んだ（コミュニティ図鑑の共有画像と同じ形。件数は毎日変わるので入れない。
見本 https://claude.ai/artifact/FQqXgLxrqeVRxdFUt8N9np 。戻し先のタグ tenki-before-site-ogp-2026-11-23）。
ページの og:image には sitegen/parts.py が画像の中身から ?v= の版の印を付ける。

  python3 tools/make_site_og.py                         # assets/ogp.png を作り直す（作ったらリポジトリに入れる）
  python3 tools/make_site_og.py --note-cover 出力先.png  # 同じ形の note の見出し画像（1280×670）

Pillow が要る。書体の Noto Sans CJK は初回に tools/fonts/ へ取ってくる（リポジトリには入れない）。絵は tools/emoji/（Noto Emoji）。
"""
import csv
import os
import random
import re
import sys
import urllib.request

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "tools", "fonts")
EMOJI = os.path.join(ROOT, "tools", "emoji")
NOTO_URL = "https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/Japanese/%s"
SITE_OG = os.path.join(ROOT, "assets", "ogp.png")
NAME, SUB = "あしたの転機観測所", "キャリアの転機に役立つサービスと情報"
INK, INK2 = "#1a1d23", "#4a4f57"
# 種類の絵（config/site.json の kinds と同じ）
KIND_EMOJI = {"相談": "1f4ac", "仕事": "1f4bc", "学習": "1f393", "内省": "1fa9e", "実務": "1f9fe", "交流": "1f91d", "書籍": "1f4da", "媒体": "1f399", "調査": "1f4ca"}
# 並べる掲載（data/latest.csv に「確認済み」であるものだけを使う。名前が知られているものを選んだ）
SHELF = ("ビズリーチ|リクルートエージェント|ランサーズ|クラウドワークス|YOUTRUST|Wantedly|Schoo(スクー)|Udemy|ユーキャン|グロービス経営大学院|"
         "ストリートアカデミー(ストアカ)|ポジウィルキャリア|ココナラ|ミイダス|16Personalities|グッドポイント診断|freee開業|Misoca|クラウドサイン|"
         "ペライチ|フリーランス協会|yenta|二枚目の名刺|ADDress|SMOUT|日本仕事百貨|ビザスク|flier(フライヤー)|PIVOT CAREER|Green|LAPRAS|Forkwell|"
         "SHElikes(シーライクス)|DMM WEBCAMP|TechTrain|RUNTEQ|ミートキャリア|キャリドラ|ライフシフトラボ|coachee|タイムチケット|弁護士ドットコム|"
         "税理士ドットコム|バトンズ|Waris|複業クラウド|シューマツワーカー|ジョブメドレー|マイナビ看護師|greenz.jp|スタディング|アガルート|MENTA|"
         "仕事旅行|サービスグラント|Day One|議論メシ|人事図書館").split("|")
_fonts, _emoji = {}, {}


def font(kind, size):
    key = (kind, int(size))
    if key not in _fonts:
        name = {"bold": "NotoSansCJKjp-Bold.otf", "medium": "NotoSansCJKjp-Medium.otf"}[kind]
        path = os.path.join(FONTS, name)
        if not os.path.exists(path):
            os.makedirs(FONTS, exist_ok=True)
            print("書体をダウンロードします:", name)
            urllib.request.urlretrieve(NOTO_URL % name, path)
        _fonts[key] = ImageFont.truetype(path, int(size))
    return _fonts[key]


def emoji(cp, size):
    key = (cp, int(size))
    if key not in _emoji:
        _emoji[key] = Image.open(os.path.join(EMOJI, cp + ".png")).convert("RGBA").resize((int(size), int(size)), Image.LANCZOS)
    return _emoji[key]


def items():
    kinds = {}
    with open(os.path.join(ROOT, "data", "latest.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["状態"] == "確認済み":
                kinds.setdefault(r["タイトル"], r["種類"])
    out = [(re.sub(r"[（(].*?[）)]", "", n).strip(), kinds[n]) for n in SHELF if kinds.get(n) in KIND_EMOJI]
    random.Random(6).shuffle(out)
    return out


def make(w=1200, h=630, path=SITE_OG):
    s = w / 1200
    picks = items()
    img = Image.new("RGBA", (w, h), (238, 242, 246, 255))
    d = ImageDraw.Draw(img)
    f = font("bold", 22 * s)
    es, ch, gap = int(30 * s), int(66 * s), 13
    k = 0
    for r in range(int(h // (ch + gap)) + 2):
        x = -int(40 * s) - int(70 * s) * (r % 3)
        y = r * (ch + gap) - int(22 * s)
        while x < w:
            name, kind = picks[k % len(picks)]
            k += 1
            cw = int(d.textlength(name, font=f) + es + 46 * s)
            d.rounded_rectangle((x, y, x + cw, y + ch), radius=int(12 * s), fill="#ffffff", outline="#d6dee8", width=max(2, int(2 * s)))
            img.alpha_composite(emoji(KIND_EMOJI[kind], es), (int(x + 16 * s), int(y + 18 * s)))
            d.text((x + 26 * s + es, y + 42 * s), name, font=f, fill=INK2, anchor="ls")
            x += cw + gap
    # まん中の白い箱（ぼかした影つき）
    box = (int(188 * s), int(132 * s), w - int(188 * s), h - int(132 * s))
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((box[0] + 6 * s, box[1] + 12 * s, box[2] + 6 * s, box[3] + 12 * s), radius=int(30 * s), fill=(20, 40, 70, 60))
    veil = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(veil).rounded_rectangle(box, radius=int(30 * s), fill=(255, 255, 255, 250))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(18 * s)))
    img.alpha_composite(veil)
    d = ImageDraw.Draw(img)
    u = (box[3] - box[1]) / 366
    big = int(82 * u)
    img.alpha_composite(emoji("1f4e1", big), (int(w / 2 - big / 2), int(box[1] + 38 * u)))
    nf = font("bold", 86 * u)
    while d.textlength(NAME, font=nf) > (box[2] - box[0]) - 70 * u:
        nf = font("bold", nf.size - 2)
    d.text((w / 2, box[1] + 224 * u), NAME, font=nf, fill=INK, anchor="ms")
    d.text((w / 2, box[1] + 292 * u), SUB, font=font("medium", 32 * u), fill=INK2, anchor="ms")
    img.convert("RGB").save(path, optimize=True)
    print("作りました:", path)


if __name__ == "__main__":
    if "--note-cover" in sys.argv:
        make(1280, 670, sys.argv[sys.argv.index("--note-cover") + 1])
    else:
        make()
