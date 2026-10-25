#!/usr/bin/env python3
"""共有画像（1200×630）を assets/og/ に作るスクリプト。
転機別ページ・掛け合わせページの画像と、セルフチェックの画像（全体用1枚と、結果の段階ごとの4枚）を作る。

Mac 専用（画像にするのに Mac の qlmanage を使う）。見出しの文面は config/tenki.json と check/check.js（段階のひとこと説明）から作るので、
それらの名前や文面を変えたときにだけ実行し直して、できた画像をリポジトリに入れる。

  python3 tools/make_og_images.py

見出しの書体 Zen Kaku Gothic New は、初回に tools/fonts/ へダウンロードする（リポジトリには入れない）。
"""
import base64
import os
import struct
import subprocess
import sys
import tempfile
import urllib.request
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402  見出しの文面を build.py と同じ作り方にするため

FONTS = os.path.join(ROOT, "tools", "fonts")
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/zenkakugothicnew/%s.ttf"
OUT = os.path.join(ROOT, "assets", "og")
STRONG = "、"
WEAK = "にのをたとではも"


def font_b64(name):
    os.makedirs(FONTS, exist_ok=True)
    path = os.path.join(FONTS, name + ".ttf")
    if not os.path.exists(path):
        urllib.request.urlretrieve(FONT_URL % name, path)
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def wrap(text, width):
    """行数がいちばん少なく、行の長さがそろう位置で折り返す。読点のあと、次に助詞のあとを優先する。"""
    n = len(text)
    def penalty(i):  # text[:i] と text[i:] の間で折り返すときの減点
        if i == n:
            return 0
        if text[i] in "、。ー" or text[i] in "ゃゅょっャュョッァィゥェォ":
            return 10 ** 6
        if text[i] in "もにのをはがとで":  # 助詞から始まる行にしない
            return 900
        if text[i - 1] in STRONG:
            return 0
        if text[i - 1] in WEAK:
            return 30
        return 400
    best = {0: (0, [])}
    for j in range(1, n + 1):
        for i in range(max(0, j - width), j):
            if i not in best:
                continue
            cost = best[i][0] + 1000 + penalty(j) + (0 if j == n else (width - (j - i)) ** 2)
            if j not in best or cost < best[j][0]:
                best[j] = (cost, best[i][1] + [text[i:j]])
    return best[n][1]


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg(kicker, title, fonts, antenna):
    size, width = 72, 13
    lines = wrap(title, width)
    if len(lines) > 3:
        size, width = 58, 16
        lines = wrap(title, width)
    elif len(lines) == 3:
        size = 64  # 3行のときは下の線と重ならないよう少し小さく
    line_h = int(size * 1.35)
    top = 170 + size + 24  # 見出しの1行目。上の英字と転機×段階の行に重ならないよう、上から順に並べる
    title_svg = "".join('<text x="104" y="%d" font-family="ZK" font-weight="900" font-size="%d" fill="#1a1d23">%s</text>'
                        % (top + i * line_h, size, esc(line)) for i, line in enumerate(lines))
    kicker_y = 160
    return """<svg xmlns="http://www.w3.org/2000/svg" width="750" height="393.75" viewBox="0 0 1200 630">
<style>
@font-face{{font-family:ZK;font-weight:900;src:url(data:font/ttf;base64,{black}) format("truetype");}}
@font-face{{font-family:ZK;font-weight:700;src:url(data:font/ttf;base64,{bold}) format("truetype");}}
</style>
<rect width="1200" height="630" fill="#fbfaf5"/>
<rect x="0" y="0" width="28" height="630" fill="#f5c518"/>
<text x="106" y="{kicker_y}" font-family="ZK" font-weight="700" font-size="34" fill="#1874b8">{kicker}</text>
{title}
<rect x="106" y="500" width="120" height="4" fill="#1a1d23"/>
<text x="106" y="560" font-family="ZK" font-weight="700" font-size="30" fill="#1a1d23">あしたの転機観測所</text>
<text x="400" y="560" font-family="Hiragino Sans" font-size="22" fill="#5e636b">ashitano-tenki.github.io</text>
<g transform="translate(1000 420) scale(1.25)">{antenna}</g>
</svg>""".format(black=fonts[0], bold=fonts[1], kicker_y=kicker_y, kicker=esc(kicker), title=title_svg, antenna=antenna)


def crop_top(png_path, out_path, height=630):
    """qlmanage が正方形で書き出すので、上の 1200×630 だけを切り出す。"""
    data = open(png_path, "rb").read()
    pos, idat = 8, b""
    while pos < len(data):
        n = struct.unpack(">I", data[pos:pos + 4])[0]
        kind, chunk = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if kind == b"IHDR":
            w, _, _, color = struct.unpack(">IIBB", chunk[:10])
        elif kind == b"IDAT":
            idat += chunk
    bpp = {6: 4, 2: 3}[color]
    stride = w * bpp
    raw = zlib.decompress(idat)
    rows, prev, i = [], bytearray(stride), 0
    for _ in range(height):
        f, line = raw[i], bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if f == 1:
                line[x] = (line[x] + a) & 255
            elif f == 2:
                line[x] = (line[x] + b) & 255
            elif f == 3:
                line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(b"\x00" + bytes(line))
        prev = line

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff)

    with open(out_path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, height, 8, color, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


def check_stage_texts():
    """セルフチェックの段階ごとのひとこと説明（check/check.js の STAGE_INFO の short）を読む。"""
    import re
    src = open(os.path.join(ROOT, "check", "check.js"), encoding="utf-8").read()
    return dict(re.findall(r'"(準備|遭遇|順応|安定)": \{\s*short: "([^"]+)"', src))


CHECK_HEAD = """<svg xmlns="http://www.w3.org/2000/svg" width="750" height="393.75" viewBox="0 0 1200 630">
<style>
@font-face{{font-family:ZK;font-weight:900;src:url(data:font/ttf;base64,{black}) format("truetype");}}
@font-face{{font-family:ZK;font-weight:700;src:url(data:font/ttf;base64,{bold}) format("truetype");}}
</style>
<rect width="1200" height="630" fill="#1a1d23"/>
<rect x="0" y="0" width="28" height="630" fill="#f5c518"/>
<text x="106" y="560" font-family="ZK" font-weight="700" font-size="30" fill="#fbfaf5">あしたの転機観測所</text>
<text x="400" y="560" font-family="Hiragino Sans" font-size="22" fill="#9aa0a8">ashitano-tenki.github.io</text>
<g transform="translate(1000 420) scale(1.25)">{antenna}</g>
"""


def svg_check_result(stage, short, fonts, antenna):
    """結果画面のヒーローと同じ、黒地に黄色の大きな段階名。"""
    return (CHECK_HEAD.format(black=fonts[0], bold=fonts[1], antenna=antenna) + """
<text x="106" y="168" font-family="ZK" font-weight="700" font-size="36" fill="#d6d9de">転機の段階セルフチェックの結果、いまは</text>
<text x="100" y="360" font-family="ZK" font-weight="900" font-size="190" fill="#f5c518">{stage}</text>
<text x="505" y="360" font-family="ZK" font-weight="700" font-size="40" fill="#d6d9de">の段階でした</text>
<text x="106" y="450" font-family="ZK" font-weight="700" font-size="34" fill="#9aa0a8">{short}</text>
</svg>""".format(stage=esc(stage), short=esc(short)))


def svg_check_general(fonts, antenna):
    stages = "".join('<text x="%d" y="400" font-family="ZK" font-weight="900" font-size="56" fill="%s">%s</text>'
                     % (106 + i * 190, "#f5c518" if i == 0 else "#fbfaf5", s) for i, s in enumerate(["準備", "遭遇", "順応", "安定"]))
    arrows = "".join('<text x="%d" y="396" font-family="Hiragino Sans" font-size="36" fill="#9aa0a8">→</text>' % (232 + i * 190)
                     for i in range(3))
    return (CHECK_HEAD.format(black=fonts[0], bold=fonts[1], antenna=antenna) + """
<text x="106" y="200" font-family="ZK" font-weight="900" font-size="68" fill="#fbfaf5">転機の段階セルフチェック</text>
<text x="106" y="270" font-family="ZK" font-weight="700" font-size="34" fill="#d6d9de">16の質問で、いまの段階と4つの資源をふりかえる</text>
{stages}{arrows}
</svg>""".format(stages=stages, arrows=arrows))


def antenna_svg():
    import re
    src = open(os.path.join(ROOT, "assets", "logo.svg"), encoding="utf-8").read()
    return re.search(r"<svg[^>]*>(.*)</svg>", src, re.S).group(1)


def main():
    fonts = (font_b64("ZenKakuGothicNew-Black"), font_b64("ZenKakuGothicNew-Bold"))
    antenna = antenna_svg()
    jobs = []
    for t in build.TENKI:
        jobs.append((t["slug"], "転機：%s" % t["name"], build.tenki_heading(t)))
        if t["past"]:
            for s in build.STAGES:
                jobs.append(("%s-%s" % (t["slug"], s["slug"]), "%s × %s" % (t["name"], s["name"]), build.combo_title(t, s)))
    pages = [(name, title, svg(kicker, title, fonts, antenna)) for name, kicker, title in jobs]
    # セルフチェック：全体用と、結果の段階ごと
    pages.append(("check", "転機の段階セルフチェック", svg_check_general(fonts, antenna)))
    texts = check_stage_texts()
    for st in build.STAGES:
        pages.append(("check-%s" % st["slug"], "いまは「%s」の段階" % st["name"],
                      svg_check_result(st["name"], texts[st["name"]], fonts, antenna)))
    os.makedirs(OUT, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for name, title, body in pages:
            src = os.path.join(tmp, name + ".svg")
            with open(src, "w", encoding="utf-8") as f:
                f.write(body)
            subprocess.run(["qlmanage", "-t", "-s", "1200", "-o", tmp, src], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            crop_top(src + ".png", os.path.join(OUT, name + ".png"))
            print("作成:", name, "／", title)


if __name__ == "__main__":
    main()
