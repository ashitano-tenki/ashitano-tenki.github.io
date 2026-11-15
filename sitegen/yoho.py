"""転機の天気予報（/yoho/）。国の統計から、転機の種類ごとに「いまの天気」を出す。

値は tools/fetch_yoho.py が毎朝 e-Stat と統計ダッシュボードから取り、data/yoho.json に保存している。
指標と天気の決め方は config/yoho.json。観測所の一覧・検索・データには混ぜない（掲載は民間のサービス・情報だけ、という決まりのため）。
"""
import json
import os

from sitegen.core import CONF, ROOT, TENKI_BY_NAME, load_json
from sitegen.parts import breadcrumb, e, emoji, page, write

__all__ = ["YOHO", "YOHO_LABEL", "build_yoho", "yoho_weather"]

YOHO = load_json("yoho.json") if os.path.exists(os.path.join(ROOT, "config", "yoho.json")) else {}
YOHO_LABEL = YOHO.get("name", "転機の天気予報")
YOHO_DATA = os.path.join(ROOT, "data", "yoho.json")

WEATHER = {  # 天気の札（雨も強い色にしない）
    "sunny": ("☀️", "晴れ"),
    "cloudy": ("☁️", "くもり"),
    "rainy": ("🌧️", "雨"),
}
ESTAT_CREDIT = "このサービスは、政府統計総合窓口(e-Stat)のAPI機能を使用していますが、サービスの内容は国によって保証されたものではありません。"
DASH_CREDIT = "このサービスは、統計ダッシュボードのAPI機能を使用していますが、サービスの内容は国によって保証されたものではありません。"


def load_data():
    if not os.path.exists(YOHO_DATA):
        return {}
    with open(YOHO_DATA, encoding="utf-8") as f:
        return json.load(f)


def prev_year(month):
    y, m = month.split("-")
    return "%d-%s" % (int(y) - 1, m)


def month_label(month):
    y, m = month.split("-")
    return "%s年%d月" % (y, int(m))


def date_label(iso):
    if not iso:
        return ""
    y, m, d = iso[:10].split("-")
    return "%s年%d月%d日" % (y, int(m), int(d))


def num(v, digits):
    if digits == 0:
        return "{:,}".format(int(round(v)))
    return ("{:,.%df}" % digits).format(v)


def yoho_weather(ind, rec):
    """指標1つの天気。値が足りなければ None。戻り値は (天気, 前年同月との差の文, 判定に使った差)"""
    series = rec.get("series") or {}
    latest = rec.get("latest")
    if not latest or latest not in series:
        return None
    rule, v = ind["rule"], series[latest]
    unit, digits = ind.get("unit", ""), ind.get("digits", 0)
    if rule["mode"] == "level":
        diff = v - rule["center"]
    else:
        base = series.get(prev_year(latest))
        if base is None or (rule["mode"] == "yoy_pct" and not base):
            return None
        diff = (v - base) / base * 100 if rule["mode"] == "yoy_pct" else v - base
    state = "sunny" if diff >= rule["sunny"] else "rainy" if diff <= rule["rainy"] else "cloudy"
    if rule["mode"] == "yoy_pct":
        change = "前の年の同じ月より%.1f%%%s" % (abs(diff), "多くなっています" if diff > 0 else "少なくなっています") if round(diff, 1) else "前の年の同じ月とほぼ同じです"
    elif rule["mode"] == "yoy_pt":
        change = "前の年の同じ月より%sポイント%s" % (num(abs(diff), digits), "高くなっています" if diff > 0 else "低くなっています") if round(diff, digits) else "前の年の同じ月と同じです"
    else:
        change = "目安の50より%sポイント%s" % (num(abs(diff), digits), "高くなっています" if diff > 0 else "低くなっています") if round(diff, digits) else "目安の50と同じです"
    return state, change, diff


def nice_ticks(lo, hi, n):
    """目盛り（きりのよい値で、lo〜hi をすべて含む）"""
    import math
    span = (hi - lo) or abs(hi) or 1
    step0 = span / n
    mag = 10 ** math.floor(math.log10(step0))
    step = next(f * mag for f in (1, 2, 2.5, 5, 10) if f * mag >= step0)
    v, top, out = math.floor(lo / step + 1e-9) * step, math.ceil(hi / step - 1e-9) * step, []
    while v <= top + 1e-9:
        out.append(round(v, 6))
        v += step
    return out


def tick_label(t, digits=0):
    return num(t, digits if t % 1 else 0)


def diff_text(ind, diff):
    """図に添える前の年との差の短い文字（例：−0.01ポイント、+1.0%）"""
    mode, digits = ind["rule"]["mode"], ind.get("digits", 0)
    if mode == "yoy_pct":
        r = round(diff, 1)
        return "±0.0%" if not r else ("+" if r > 0 else "−") + "%.1f%%" % abs(r)
    r = round(diff, digits)
    return "±0ポイント" if not r else ("+" if r > 0 else "−") + num(abs(r), digits) + "ポイント"


def text_w(s, size=11):
    """文字の幅の見積もり（viewBox の単位）。全角はほぼ1文字分、数字や記号は約0.58文字分"""
    return sum(size if ord(ch) > 0x2000 and ch != "−" else size * 0.58 for ch in s)


def place_diff(lines, labels, xc, yc, yp, label, W, H, B):
    """差の文字の置き場所を、線・年の札・点と重なりにくい順に選ぶ（2026-11-15 見本の案3）"""
    def hits(rect, segs):
        x0, y0, x1, y1 = rect
        n = 0
        for (ax, ay), (bx, by) in segs:
            k = max(1, int(max(abs(bx - ax), abs(by - ay))))
            for i in range(k + 1):
                px, py = ax + (bx - ax) * i / k, ay + (by - ay) * i / k
                if x0 <= px <= x1 and y0 <= py <= y1:
                    n += 1
        return n

    def overlap(a, b):
        return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])

    w = text_w(label)
    lo, hi, mid = min(yc, yp), max(yc, yp), (yc + yp) / 2
    cands = [("start", xc + 8, mid + 4), ("start", xc + 8, yp + 4), ("middle", xc, lo - 9), ("middle", xc, hi + 16),
             ("end", xc - 8, mid + 4), ("end", xc - 8, lo - 6), ("end", xc - 8, hi + 14)]
    segs, heavy = [], []
    for cls, pts in lines:
        (heavy if cls == "y0" else segs).extend(zip(pts, pts[1:]))
    boxes = [(x - 1, yy - 9, x + text_w(str(y)) + 1, yy + 2) for x, yy, y, cur in labels]
    dots = [(xc - 5, yc - 5, xc + 5, yc + 5), (xc - 4, yp - 4, xc + 4, yp + 4)]
    best = None
    for i, (anchor, x, base) in enumerate(cands):
        x0 = x if anchor == "start" else x - w if anchor == "end" else x - w / 2
        rect = (x0 - 1.5, base - 10.5, x0 + w + 1.5, base + 3.5)
        score = i * 0.5
        if rect[0] < 0 or rect[2] > W or rect[1] < 0 or rect[3] > H - B:
            score += 1000
        score += hits(rect, segs) + 4 * hits(rect, heavy)
        score += sum(40 for r in boxes if overlap(rect, r)) + sum(60 for r in dots if overlap(rect, r))
        if best is None or score < best[0]:
            best = (score, anchor, x, base)
    return best[1:]


def spark(series, latest, ind):
    """カードのグラフ（案A、2026-11-11 黒田さんが選んだ）。横軸を1月〜12月にして、年ごとの線を重ねる。
    今年は青い太線、前の年は濃いめの灰色、それより前は薄い灰色。前の年の同じ月と比べる天気の決め方が、そのまま見える。
    2026-11-15 の見本で採用した3つを足した：
    ・今年の線を path（pathLength="1"）にし、画面に入ったら一度だけ左から描く（案1のB。動きは site.js と style.css）
    ・前の年の同じ月の白い丸・青い点と結ぶ縦線・差の文字（案3。前の年と比べる指標だけ）
    ・なぞると月ごとの数字が吹き出しで出る（案2のB）。値を data-yoho に書き、縦線と点を隠して置く"""
    ly = int(latest[:4])
    years = [y for y in range(ly - 3, ly + 1) if any(k.startswith("%d-" % y) for k in series)]
    vals = [v for k, v in series.items() if int(k[:4]) in years and k <= latest]
    if len(years) < 2 or len(vals) < 6:
        return ""
    digits, unit = ind.get("digits", 0), ind.get("unit", "")
    ticks = nice_ticks(min(vals), max(vals), 3)
    lo, hi = ticks[0], ticks[-1]
    W, H, L, R, T, B = 300, 150, 36, 36, 8, 20
    X = lambda m: L + (m - 1) * (W - L - R) / 11
    Y = lambda v: T + (hi - v) / ((hi - lo) or 1) * (H - T - B)
    out = []
    for t in ticks:
        out.append('<line class="g" x1="%d" x2="%d" y1="%.1f" y2="%.1f"/><text x="%d" y="%.1f" text-anchor="end">%s</text>'
                   % (L, W - R, Y(t), Y(t), L - 6, Y(t) + 4, e(tick_label(t, digits))))
    for m in (1, 4, 7, 10, 12):
        out.append('<text x="%.1f" y="%d" text-anchor="middle">%d月</text>' % (X(m), H - 4, m))
    labels, lines, dot = [], [], None
    for y in years:
        pts = [(m, series["%d-%02d" % (y, m)], "%d-%02d" % (y, m)) for m in range(1, 13) if "%d-%02d" % (y, m) in series and "%d-%02d" % (y, m) <= latest]
        if not pts:
            continue
        cls = "y0" if y == ly else "y1" if y == ly - 1 else "y2"
        xy = [(X(m), Y(v)) for m, v, _ in pts]
        lines.append((cls, xy))
        if y == ly:
            out.append('<path class="y0 yoho-line" pathLength="1" d="M%s"/>' % " L".join("%.1f,%.1f" % p for p in xy))
        else:
            out.append('<polyline class="%s" points="%s"/>' % (cls, " ".join("%.1f,%.1f" % p for p in xy)))
        if y == ly:
            dot = xy[-1]
        labels.append([xy[-1][0] + 5, xy[-1][1] + 4, y, y == ly])
    labels.sort(key=lambda l: l[1])
    for i in range(1, len(labels)):
        if abs(labels[i][0] - labels[i - 1][0]) < 30 and labels[i][1] - labels[i - 1][1] < 12:
            labels[i][1] = labels[i - 1][1] + 12
    # 前の年の同じ月との差（目安の50と比べる指標には付けない）
    diff_svg = ""
    base = series.get(prev_year(latest))
    w = yoho_weather(ind, {"series": series, "latest": latest})
    if dot and base is not None and w and ind["rule"]["mode"] != "level":
        label = diff_text(ind, w[2])
        xc, yc = dot
        yp = Y(base)
        anchor, lx, lyy = place_diff(lines, labels, xc, yc, yp, label, W, H, B)
        if abs(yp - yc) > 7.5:  # 点どうしが近いときは線を引かない
            sgn = 1 if yp > yc else -1
            diff_svg += '<line class="yoho-link" x1="%.1f" x2="%.1f" y1="%.1f" y2="%.1f"/>' % (xc, xc, yc + sgn * 3.5, yp - sgn * 3)
        diff_svg += '<circle class="yoho-prev" cx="%.1f" cy="%.1f" r="3"/>' % (xc, yp)
        diff_text_svg = '<text class="yoho-diff" x="%.1f" y="%.1f" text-anchor="%s">%s</text>' % (lx, lyy, anchor, e(label))
    else:
        diff_text_svg = ""
    out.append(diff_svg)
    if dot:
        out.append('<circle class="dot yoho-end" cx="%.1f" cy="%.1f" r="3.5"/>' % dot)
    out.append(diff_text_svg)
    for x, yy, y, cur in labels:
        out.append('<text x="%.1f" y="%.1f"%s>%d</text>' % (x, yy, ' class="cur yoho-end"' if cur else "", y))
    # なぞったときの縦線と各年の点（ふだんは隠れている）
    cursor = ['<g class="yoho-cursor" aria-hidden="true"><line class="yoho-vline" x1="0" x2="0" y1="%d" y2="%d"/>' % (T - 4, H - B)]
    rows = []
    for y in reversed(years):
        cls = "y0" if y == ly else "y1" if y == ly - 1 else "y2"
        cursor.append('<circle class="yoho-pt %s" cx="0" cy="0" r="%s"/>' % (cls, "4" if cls == "y0" else "3"))
        pts = []
        for m in range(1, 13):
            k = "%d-%02d" % (y, m)
            v = series.get(k)
            pts.append(None if v is None or k > latest else [round(Y(v), 1), num(v, digits) + unit])
        rows.append({"year": y, "cls": cls, "pts": pts})
    cursor.append("</g>")
    data = {"w": W, "h": H, "b": B, "x": [round(X(m), 1) for m in range(1, 13)], "latest": int(latest[5:]), "years": rows}
    svg = '<svg viewBox="0 0 %d %d" role="img" aria-label="%sの年ごとの推移（%d年〜%d年）">%s%s</svg>' % (
        W, H, e(ind["label"]), years[0], ly, "".join(out), "".join(cursor))
    note = "。白い丸は前の年の同じ月" if diff_svg else ""
    return ('<figure class="yoho-years"><div class="yoho-plot" tabindex="0" role="group" aria-label="月ごとの数字を読む。左右の矢印キーで月を選べます" data-yoho="%s">%s'
            '<div class="yoho-tip" hidden></div></div><p class="yoho-live visually-hidden" aria-live="polite"></p>'
            '<figcaption>1月から12月までを年ごとに重ねています。青い太線が%d年%s。なぞると月ごとの数字が出ます</figcaption></figure>'
            % (e(json.dumps(data, ensure_ascii=False, separators=(",", ":"))), svg, ly, note))


def source_line(ind, rec):
    src = ind["source"]
    if src["api"] == "estat":
        url = "https://www.e-stat.go.jp/dbview?sid=%s" % (rec.get("table") or src["statsDataId"])
    else:
        url = ind.get("url", "https://dashboard.e-stat.go.jp/")
    return ('出典：<a href="%s" rel="noopener" target="_blank">%s（%s）</a>をもとに作成'
            % (e(url), e(ind["stat"]), e(ind["org"])))


def when_line(ind, rec):
    parts = ["%s分" % month_label(rec["latest"])]
    if rec.get("published"):
        parts.append("%s公表" % date_label(rec["published"]))
    else:
        seen = (rec.get("first_seen") or {}).get(rec["latest"])
        if seen:
            parts.append("%s取得" % date_label(seen))
    return "・".join(parts)


def card(ind, rec, tenki_name=None, card_id=""):
    w = yoho_weather(ind, rec)
    if not w:
        return ""
    state, change, _ = w
    icon, word = WEATHER[state]
    v = rec["series"][rec["latest"]]
    unit = ind.get("unit", "")
    value = "%s%s" % (num(v, ind.get("digits", 0)), unit)
    sentence = "%sは、%s。" % (ind["subject"], change)
    head = ""
    if tenki_name:
        t = TENKI_BY_NAME.get(tenki_name, {})
        head = '<h3 class="yoho-kind"><a href="/tenki/%s/">%s%s</a></h3>' % (e(t.get("slug", "")), emoji(t.get("emoji", "")), e(tenki_name)) if t.get("slug") \
            else '<h3 class="yoho-kind">%s</h3>' % e(tenki_name)
    return """<article class="yoho-card yoho-%s"%s>
  <div class="yoho-top">%s<p class="yoho-weather"><span class="yoho-icon" aria-hidden="true">%s</span><span class="yoho-word">%s</span></p></div>
  <p class="yoho-label">%s</p>
  <p class="yoho-value"><b>%s</b><span class="yoho-when">%s</span></p>
  <p class="yoho-sentence">%s</p>
  %s
  <p class="yoho-note">%s</p>
  <p class="yoho-source">%s</p>
</article>
""" % (state, (' id="%s" tabindex="-1"' % e(card_id)) if card_id else "", head, icon, word, e(ind["label"]), e(value), e(when_line(ind, rec)), e(sentence), spark(rec["series"], rec["latest"], ind),
       e(ind.get("notes", {}).get(state, "")), source_line(ind, rec))


def rule_text(ind):
    r = ind["rule"]
    if r["mode"] == "yoy_pct":
        return "%s：前の年の同じ月より%s%%以上多ければ晴れ、%s%%以上少なければ雨" % (ind["label"], num(r["sunny"], 0), num(abs(r["rainy"]), 0))
    if r["mode"] == "yoy_pt":
        return "%s：前の年の同じ月より%sポイント以上高ければ晴れ、%sポイント以上低ければ雨" % (ind["label"], r["sunny"], abs(r["rainy"]))
    return "%s：%sより%sポイント以上高ければ晴れ、%sポイント以上低ければ雨" % (ind["label"], r["center"], r["sunny"], abs(r["rainy"]))


def status_json(data, ctx):
    """指標ごとの取得の状況（Cowork の週次ふりかえりが読み、止まっている指標を知らせる）"""
    out = {"built": ctx["today"].isoformat(), "checked": data.get("checked", ""), "indicators": []}
    for ind in YOHO.get("indicators", []) + ([YOHO["mood"]] if YOHO.get("mood") else []):
        rec = data.get("indicators", {}).get(ind["key"], {})
        out["indicators"].append({"key": ind["key"], "label": ind["label"], "tenki": ind.get("tenki", ""),
                                  "latest": rec.get("latest", ""), "fetched": rec.get("fetched", ""),
                                  "published": rec.get("published", ""), "error": rec.get("error", "")})
    return out


def latest_json(data):
    out = {"checked": data.get("checked", ""), "indicators": []}
    for ind in YOHO.get("indicators", []) + ([YOHO["mood"]] if YOHO.get("mood") else []):
        rec = data.get("indicators", {}).get(ind["key"], {})
        w = yoho_weather(ind, rec)
        if not w:
            continue
        out["indicators"].append({"key": ind["key"], "tenki": ind.get("tenki", ""), "label": ind["label"], "unit": ind.get("unit", ""),
                                  "month": rec["latest"], "value": rec["series"][rec["latest"]], "weather": WEATHER[w[0]][1],
                                  "change": w[1], "stat": ind["stat"], "org": ind["org"]})
    return out


def strip(inds, recs, mood):
    """ページの上の、転機ごとの天気を1行に並べた帯（2026-11-15 見本の案4）。押すとそのカードへ移る（ページ内リンクと :target）"""
    tiles = []
    for ind, name, target, emo in [(i, i["tenki"], "yoho-" + TENKI_BY_NAME.get(i["tenki"], {}).get("slug", i["key"]),
                                    emoji(TENKI_BY_NAME.get(i["tenki"], {}).get("emoji", ""))) for i in inds] + \
            ([(mood, "全体の空気", "yoho-mood", "")] if mood else []):
        rec = recs.get(ind["key"], {})
        w = yoho_weather(ind, rec)
        if not w:
            continue
        icon, word = WEATHER[w[0]]
        tiles.append('<li><a class="yoho-tile yoho-%s" href="#%s"><span class="yoho-tile-kind">%s%s</span>'
                     '<span class="yoho-weather"><span class="yoho-icon" aria-hidden="true">%s</span><span class="yoho-word">%s</span></span>'
                     '<span class="yoho-tile-val"><b>%s%s</b><small>%d月分</small></span></a></li>'
                     % (w[0], target, emo, e(name), icon, word, e(num(rec["series"][rec["latest"]], ind.get("digits", 0))), e(ind.get("unit", "")),
                        int(rec["latest"][5:])))
    if not tiles:
        return ""
    return '<nav class="yoho-strip" aria-label="転機ごとの天気"><ul>%s</ul></nav>\n' % "".join(tiles)


def build_yoho(ctx):
    if not YOHO:
        return
    data = load_data()
    write("/yoho/status.json", json.dumps(status_json(data, ctx), ensure_ascii=False, indent=1) + "\n")
    write("/yoho/latest.json", json.dumps(latest_json(data), ensure_ascii=False, indent=1) + "\n")
    recs = data.get("indicators", {})
    cards = "".join(card(ind, recs.get(ind["key"], {}), ind["tenki"], "yoho-" + TENKI_BY_NAME.get(ind["tenki"], {}).get("slug", ind["key"]))
                    for ind in YOHO.get("indicators", []))
    later = "".join('<li>%s%s</li>' % (emoji(TENKI_BY_NAME.get(n, {}).get("emoji", "")), e(n)) for n in YOHO.get("later", []))
    mood = YOHO.get("mood")
    mood_html = ""
    strip_html = strip(YOHO.get("indicators", []), recs, mood)
    if mood and yoho_weather(mood, recs.get(mood["key"], {})):
        mood_html = """<section class="yoho-mood" id="yoho-mood" tabindex="-1" aria-labelledby="yoho-mood-h">
<h2 id="yoho-mood-h">全体の空気</h2>
<p class="yoho-mood-about">%s</p>
%s</section>
""" % (e(mood.get("about", "")), card(mood, recs[mood["key"]]))
    uses_estat = any(i["source"]["api"] == "estat" for i in YOHO.get("indicators", []) + ([mood] if mood else []))
    uses_dash = any(i["source"]["api"] == "dashboard" for i in YOHO.get("indicators", []) + ([mood] if mood else []))
    rules = "".join("<li>%s</li>" % e(rule_text(i)) for i in YOHO.get("indicators", []) + ([mood] if mood else []))
    body = """%s
<header class="page-head"><h1>%s</h1><p class="lead">%s</p></header>
%s<section class="yoho-grid-wrap" aria-labelledby="yoho-grid-h">
<h2 id="yoho-grid-h" class="visually-hidden">転機の種類ごとの天気</h2>
<div class="yoho-grid">
%s</div>
%s
</section>
%s
<section class="yoho-how" aria-labelledby="yoho-how-h">
<h2 id="yoho-how-h">どうやって天気を決めているか</h2>
<p>天気は、その転機のまわりで人や機会の動きが前の年より活発かどうかを表しています。よい・悪いの判定ではありません。季節による増え減りを避けるため、多くの指標は前の年の同じ月と比べています。</p>
<ul>%s</ul>
<p>そのあいだはくもりです。統計は国が公表したあと、毎朝確かめて新しい値に入れ替えます。公表の時期は統計ごとに違うため、カードによって何月分のデータかがずれることがあります。</p>
</section>
<section class="yoho-credit" aria-label="出典">
<p>各カードの数値は、出典に書いた統計をもとに作成したものです。前の年との差や天気は、観測所が計算しています。</p>
%s%s
</section>
""" % (breadcrumb([(YOHO_LABEL, None)]), e(YOHO_LABEL), e(YOHO.get("lead", "")), strip_html, cards,
       ('<div class="yoho-later"><p>%s</p><ul>%s</ul></div>' % (e(YOHO.get("later_note", "")), later)) if later else "",
       mood_html, rules,
       ('<p>%s</p>' % e(ESTAT_CREDIT)) if uses_estat else "", ('<p>%s</p>' % e(DASH_CREDIT)) if uses_dash else "")
    page("/yoho/", YOHO_LABEL, YOHO.get("lead", ""), body, ctx=ctx,
         extra_head='<link rel="alternate" type="application/json" href="/yoho/latest.json" title="%s（JSON）">\n' % e(YOHO_LABEL))
