#!/usr/bin/env python3
"""共有画像（1200×630）を assets/og/ に作るスクリプト。
転機別ページ・掛け合わせページの画像と、セルフチェックの画像（全体用1枚と、結果の段階ごとの4枚）を作る。

Mac 専用（画像にするのに Mac の qlmanage を使う。観測ノートの画像は Mac の Google Chrome で書き出す）。見出しの文面は config/tenki.json と check/check.js（段階のひとこと説明）から作るので、
それらの名前や文面を変えたときにだけ実行し直して、できた画像をリポジトリに入れる。

  python3 tools/make_og_images.py
  python3 tools/make_og_images.py --notes   # 観測ノートの共有画像だけを作る（記事を足したり題名を変えたりしたとき）

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


CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# 観測ノートの共有画像の重ねる画像の位置（左, 上, 傾き, 幅）。2026-11-20 黒田さんが見本の案B「中身を見せる」を選んだ
NOTE_CARDS = [(690, 70, -7, 300), (860, 150, 5, 300), (720, 300, 3, 300), (900, 340, -5, 260)]


def split_title(title):
    """題名を「。」（または「？」）の前（大きく出す）と後ろ（小さく出す）に分ける"""
    for mark in ("。", "？"):
        if mark in title:
            head, rest = title.split(mark, 1)
            return head + ("？" if mark == "？" else ""), rest
    return title, ""


def data_uri(path, mime):
    with open(path, "rb") as f:
        return "data:%s;base64,%s" % (mime, base64.b64encode(f.read()).decode())


def two_lines(text):
    """題名を2行に分ける。「、」のあと、次に助詞のあと（次がひらがなのときは言葉の途中なので切らない。「たら」のあとは切る）を選び、なるべく真ん中に近いところで切る"""
    n, best = len(text), None
    for i in range(2, n - 1):
        prev, nxt = text[i - 1], text[i]
        if prev in "、・":
            score = 0
        elif text[i - 2:i] == "たら" or (prev in "のをにはでとがもへ" and not ("\u3041" <= nxt <= "\u309f")):
            score = 1
        else:
            score = 6
        cost = score * 10 + abs(i - n / 2)
        if best is None or cost < best[0]:
            best = (cost, i)
    i = best[1] if best else n // 2
    return [text[:i], text[i:]]


def html_note(note):
    """観測ノートの共有画像（案B「中身を見せる」）。黄色の地の左に題名、右に記事で紹介している本やサービスの画像を4枚まで重ねる。
    画像がない記事は、題名を横いっぱいに使う。題名は「。」の前を1行に収まる大きさで大きく、後ろを小さく出す。"""
    head, rest = split_title(note["title"])
    imgs = [i for i in note.get("ids", []) if i in build.IMAGES and os.path.exists(os.path.join(ROOT, "images", "items", i + ".webp"))][:4]
    text_w = 560 if imgs else 1040  # 右の画像（左端 690px、傾きで少し左へはみ出す）にかからない幅
    n = max(len(head), 1)
    if text_w // n >= 44:  # 1行に収まるなら1行で大きく
        size, per = min(62, text_w // n), n
    else:  # 2行に分ける（折り返しは言葉の切れ目で）
        lines = two_lines(head)
        per = max(len(l) for l in lines)
        size = min(58, text_w // per)
    head_html = "<br>".join(esc(l) for l in (wrap(head, per) if per == n else two_lines(head)))
    rest_html = "<br>".join(esc(l) for l in (two_lines(rest) if len(rest) > text_w // 30 else [rest]))
    cards = "".join(
        '<div style="position:absolute;left:%dpx;top:%dpx;width:%dpx;height:%dpx;transform:rotate(%ddeg);'
        'background:#fff url(%s) center/cover;border-radius:10px;box-shadow:0 10px 30px rgba(26,29,35,.25);border:6px solid #fff"></div>'
        % (x, y, w, int(w * 0.62), r, data_uri(os.path.join(ROOT, "images", "items", i + ".webp"), "image/webp"))
        for (x, y, r, w), i in zip(NOTE_CARDS, imgs))
    names = [t for t in note["tenki"] if t in build.TENKI_BY_NAME]
    emo = ""
    if names and build.TENKI_BY_NAME[names[0]].get("emoji"):
        name = build.emoji_file(build.TENKI_BY_NAME[names[0]]["emoji"])
        if name:
            emo = '<img src="%s" style="width:34px;height:34px">' % data_uri(os.path.join(ROOT, "assets", "emoji", name + ".svg"), "image/svg+xml")
    label = "観測ノート" + ("｜" + "・".join(names) if names else "")
    count = len(note.get("ids", []))
    font = "file://" + FONTS
    return """<!doctype html><meta charset=utf-8><style>
@font-face{{font-family:ZK;font-weight:500;src:url({font}/ZenKakuGothicNew-Medium.ttf)}}
@font-face{{font-family:ZK;font-weight:700;src:url({font}/ZenKakuGothicNew-Bold.ttf)}}
@font-face{{font-family:ZK;font-weight:900;src:url({font}/ZenKakuGothicNew-Black.ttf)}}
html,body{{margin:0;width:1200px;height:630px;overflow:hidden}}
</style>
<div style="position:relative;width:1200px;height:630px;background:#f5c518;color:#1a1d23;font-family:ZK,sans-serif;overflow:hidden">
{cards}
<div style="position:absolute;left:80px;top:80px;width:{text_w}px">
 <div style="display:inline-flex;align-items:center;gap:10px;background:#1a1d23;color:#f5c518;font-weight:700;font-size:26px;padding:8px 18px;border-radius:8px">{emo}{label}</div>
 <div style="margin-top:40px;font-weight:900;font-size:{size}px;line-height:1.28">{head}</div>
 <div style="margin-top:20px;font-weight:500;font-size:30px;line-height:1.5">{rest}</div></div>
<div style="position:absolute;left:80px;bottom:60px;font-size:26px;font-weight:700">{count_text}あしたの転機観測所</div>
</div>""".format(font=font, cards=cards, text_w=text_w, emo=emo, label=esc(label), size=size, head=head_html, rest=rest_html,
                 count_text=("本・サービス %d件　｜　" % count) if count else "")


def render_html(pages):
    """HTML の共有画像を Chrome（画面なし）で 1200×630 の PNG にする"""
    os.makedirs(OUT, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for name, title, body in pages:
            src = os.path.join(tmp, name + ".html")
            with open(src, "w", encoding="utf-8") as f:
                f.write(body)
            subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", "--allow-file-access-from-files", "--window-size=1200,630",
                            "--virtual-time-budget=3000", "--screenshot=" + os.path.join(OUT, name + ".png"), "file://" + src],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("作成:", name, "／", title)


def render(pages):
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


def main_notes():
    """観測ノートの共有画像（assets/og/note-<スラッグ>.png）を、下書きも含めて全記事ぶん作り直す（案B、Chrome で書き出す）。"""
    for name in ("ZenKakuGothicNew-Medium", "ZenKakuGothicNew-Bold", "ZenKakuGothicNew-Black"):
        font_b64(name)  # なければ tools/fonts/ へダウンロードしておく
    pages = []
    for name in sorted(os.listdir(build.NOTES_DIR)):
        if name.endswith(".md") and not name.startswith("_"):
            n = build.parse_note_file(os.path.join(build.NOTES_DIR, name))
            pages.append(("note-" + n["slug"], n["title"], html_note(n)))
    render_html(pages)


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
    if "--notes" in sys.argv:
        main_notes()  # python3 tools/make_og_images.py --notes
    else:
        main()
