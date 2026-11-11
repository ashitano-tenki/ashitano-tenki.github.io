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


def spark(series, latest, ind):
    """カードのグラフ（案A、2026-11-11 黒田さんが選んだ）。横軸を1月〜12月にして、年ごとの線を重ねる。
    今年は青い太線、前の年は濃いめの灰色、それより前は薄い灰色。前の年の同じ月と比べる天気の決め方が、そのまま見える。"""
    ly = int(latest[:4])
    years = [y for y in range(ly - 3, ly + 1) if any(k.startswith("%d-" % y) for k in series)]
    vals = [v for k, v in series.items() if int(k[:4]) in years and k <= latest]
    if len(years) < 2 or len(vals) < 6:
        return ""
    digits = ind.get("digits", 0)
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
    labels = []
    for y in years:
        pts = [(m, series["%d-%02d" % (y, m)], "%d-%02d" % (y, m)) for m in range(1, 13) if "%d-%02d" % (y, m) in series and "%d-%02d" % (y, m) <= latest]
        if not pts:
            continue
        cls = "y0" if y == ly else "y1" if y == ly - 1 else "y2"
        out.append('<polyline class="%s" points="%s"/>' % (cls, " ".join("%.1f,%.1f" % (X(m), Y(v)) for m, v, _ in pts)))
        m, v, _ = pts[-1]
        if y == ly:
            out.append('<circle class="dot" cx="%.1f" cy="%.1f" r="3.5"/>' % (X(m), Y(v)))
        labels.append([X(m) + 5, Y(v) + 4, y, y == ly])
    labels.sort(key=lambda l: l[1])
    for i in range(1, len(labels)):
        if abs(labels[i][0] - labels[i - 1][0]) < 30 and labels[i][1] - labels[i - 1][1] < 12:
            labels[i][1] = labels[i - 1][1] + 12
    for x, yy, y, cur in labels:
        out.append('<text x="%.1f" y="%.1f"%s>%d</text>' % (x, yy, ' class="cur"' if cur else "", y))
    return ('<figure class="yoho-years"><svg viewBox="0 0 %d %d" role="img" aria-label="%sの年ごとの推移（%d年〜%d年）">%s</svg>'
            '<figcaption>1月から12月までを年ごとに重ねています。青い太線が%d年</figcaption></figure>'
            % (W, H, e(ind["label"]), years[0], ly, "".join(out), ly))


def yoy_avg3(ind, rec):
    """前の年の同じ月と比べた増減（%）を、直近3か月で平均した値（案Cの1枚に使う）"""
    s = rec.get("series") or {}
    g = {k: (v - s[prev_year(k)]) / s[prev_year(k)] * 100 for k, v in s.items() if s.get(prev_year(k))}
    ks = sorted(g)
    return {ks[i]: sum(g[ks[j]] for j in (i, i - 1, i - 2)) / 3 for i in range(2, len(ks))}


def overview(recs):
    """ページの最初に置く1枚（案C、2026-11-11 黒田さんが選んだ）。5つの転機の「前の年との差」を同じ目盛りで重ねる。
    月ごとのぶれ（とくに起業）に引っぱられないよう、直近3か月で平均する。色だけに頼らないよう、線の端に転機の名前を付ける。"""
    lines = []
    for i, ind in enumerate(YOHO.get("indicators", [])):
        g = yoy_avg3(ind, recs.get(ind["key"], {}))
        if g:
            lines.append((ind, g, "s%d" % (i + 1)))
    if not lines:
        return ""
    ks = sorted({k for _, g, _ in lines for k in g})[-24:]
    vals = [g[k] for _, g, _ in lines for k in ks if k in g] + [5, -5]
    ticks = nice_ticks(min(vals), max(vals), 6)
    lo, hi = ticks[0], ticks[-1]
    W, H, L, R, T, B = 960, 360, 56, 120, 12, 30
    X = lambda i: L + i * (W - L - R) / (len(ks) - 1)
    Y = lambda v: T + (hi - v) / (hi - lo) * (H - T - B)
    sun = min(r["rule"]["sunny"] for r in [l[0] for l in lines] if r["rule"]["mode"] == "yoy_pct")
    rain = max(r["rule"]["rainy"] for r in [l[0] for l in lines] if r["rule"]["mode"] == "yoy_pct")
    out = ['<rect class="sun" x="%d" y="%.1f" width="%d" height="%.1f"/>' % (L, Y(hi), W - L - R, Y(sun) - Y(hi)),
           '<rect class="rain" x="%d" y="%.1f" width="%d" height="%.1f"/>' % (L, Y(rain), W - L - R, Y(lo) - Y(rain)),
           '<text x="%d" y="%.1f">晴れの目安（＋%s%%より上）</text>' % (L + 8, Y(hi) + 16, num(sun, 0)),
           '<text x="%d" y="%.1f">雨の目安（−%s%%より下）</text>' % (L + 8, Y(lo) - 8, num(abs(rain), 0))]
    for t in ticks:
        out.append('<line class="%s" x1="%d" x2="%d" y1="%.1f" y2="%.1f"/><text x="%d" y="%.1f" text-anchor="end">%s%s%%</text>'
                   % ("zero" if t == 0 else "g", L, W - R, Y(t), Y(t), L - 6, Y(t) + 4, "+" if t > 0 else "", tick_label(t)))
    for i, k in enumerate(ks):
        if i == 0 or k.endswith("-01"):
            out.append('<text x="%.1f" y="%d" text-anchor="middle">%s</text>' % (X(i), H - 6, month_label(k)))
    ends = []
    for ind, g, cls in lines:
        pts = [(i, g[k], k) for i, k in enumerate(ks) if k in g]
        out.append('<polyline class="%s" points="%s"/>' % (cls, " ".join("%.1f,%.1f" % (X(i), Y(v)) for i, v, _ in pts)))
        i, v, _ = pts[-1]
        out.append('<circle class="dot %s" cx="%.1f" cy="%.1f" r="3.5"/>' % (cls, X(i), Y(v)))
        ends.append([Y(v) + 4, ind["tenki"], cls])
    ends.sort()
    for i in range(1, len(ends)):
        if ends[i][0] - ends[i - 1][0] < 18:
            ends[i][0] = ends[i - 1][0] + 18
    for yy, name, cls in ends:
        out.append('<text class="end %s" x="%d" y="%.1f">%s</text>' % (cls, W - R + 10, yy, e(name)))
    legend = "".join('<li><i class="%s"></i>%s：%s</li>' % (cls, e(ind["tenki"]), e(ind["label"].replace("（季節調整値）", ""))) for ind, _, cls in lines)
    return """<section class="yoho-overview" aria-labelledby="yoho-overview-h">
<h2 id="yoho-overview-h">転機ごとの動きを重ねて見る</h2>
<div class="yoho-overview-scroll"><svg viewBox="0 0 %d %d" role="img" aria-label="5つの転機の前の年との差（%s〜%s）">%s</svg></div>
<p class="yoho-scroll-hint">いちばん新しい月を表示しています。左へずらすと前の月を見られます。</p>
<script>document.querySelectorAll(".yoho-overview-scroll").forEach(function (el) { el.scrollLeft = el.scrollWidth; });</script>
<ul class="yoho-legend">%s</ul>
<p class="yoho-overview-cap">%s〜%s。どれも前の年の同じ月と比べた増減（%%）を、月ごとのぶれをならすため直近3か月で平均しています。有効求人倍率も、倍率の増減を%%に直しています。</p>
</section>
""" % (W, H, month_label(ks[0]), month_label(ks[-1]), "".join(out), legend, month_label(ks[0]), month_label(ks[-1]))


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


def card(ind, rec, tenki_name=None):
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
    return """<article class="yoho-card yoho-%s">
  <div class="yoho-top">%s<p class="yoho-weather"><span class="yoho-icon" aria-hidden="true">%s</span><span class="yoho-word">%s</span></p></div>
  <p class="yoho-label">%s</p>
  <p class="yoho-value"><b>%s</b><span class="yoho-when">%s</span></p>
  <p class="yoho-sentence">%s</p>
  %s
  <p class="yoho-note">%s</p>
  <p class="yoho-source">%s</p>
</article>
""" % (state, head, icon, word, e(ind["label"]), e(value), e(when_line(ind, rec)), e(sentence), spark(rec["series"], rec["latest"], ind),
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


def build_yoho(ctx):
    if not YOHO:
        return
    data = load_data()
    write("/yoho/status.json", json.dumps(status_json(data, ctx), ensure_ascii=False, indent=1) + "\n")
    write("/yoho/latest.json", json.dumps(latest_json(data), ensure_ascii=False, indent=1) + "\n")
    recs = data.get("indicators", {})
    cards = "".join(card(ind, recs.get(ind["key"], {}), ind["tenki"]) for ind in YOHO.get("indicators", []))
    later = "".join('<li>%s%s</li>' % (emoji(TENKI_BY_NAME.get(n, {}).get("emoji", "")), e(n)) for n in YOHO.get("later", []))
    mood = YOHO.get("mood")
    mood_html = ""
    if mood and yoho_weather(mood, recs.get(mood["key"], {})):
        mood_html = """<section class="yoho-mood" aria-labelledby="yoho-mood-h">
<h2 id="yoho-mood-h">全体の空気</h2>
<p class="yoho-mood-about">%s</p>
%s</section>
""" % (e(mood.get("about", "")), card(mood, recs[mood["key"]]))
    uses_estat = any(i["source"]["api"] == "estat" for i in YOHO.get("indicators", []) + ([mood] if mood else []))
    uses_dash = any(i["source"]["api"] == "dashboard" for i in YOHO.get("indicators", []) + ([mood] if mood else []))
    rules = "".join("<li>%s</li>" % e(rule_text(i)) for i in YOHO.get("indicators", []) + ([mood] if mood else []))
    body = """%s
<header class="page-head"><h1>%s</h1><p class="lead">%s</p></header>
%s
<section class="yoho-grid-wrap" aria-labelledby="yoho-grid-h">
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
""" % (breadcrumb([(YOHO_LABEL, None)]), e(YOHO_LABEL), e(YOHO.get("lead", "")), overview(recs), cards,
       ('<div class="yoho-later"><p>%s</p><ul>%s</ul></div>' % (e(YOHO.get("later_note", "")), later)) if later else "",
       mood_html, rules,
       ('<p>%s</p>' % e(ESTAT_CREDIT)) if uses_estat else "", ('<p>%s</p>' % e(DASH_CREDIT)) if uses_dash else "")
    page("/yoho/", YOHO_LABEL, YOHO.get("lead", ""), body, ctx=ctx,
         extra_head='<link rel="alternate" type="application/json" href="/yoho/latest.json" title="%s（JSON）">\n' % e(YOHO_LABEL))
