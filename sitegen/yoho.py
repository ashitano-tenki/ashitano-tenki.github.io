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


def spark(series, latest, months=36):
    """小さな推移グラフ（過去3年分）。読み上げでは読まない（値と前年との差は文で出している）"""
    keys = [k for k in sorted(series) if k <= latest][-months:]
    if len(keys) < 6:
        return ""
    vals = [series[k] for k in keys]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    w, h, pad = 240, 48, 4
    pts = ["%.1f,%.1f" % (pad + i * (w - 2 * pad) / (len(vals) - 1), h - pad - (v - lo) / span * (h - 2 * pad)) for i, v in enumerate(vals)]
    lx, ly = pts[-1].split(",")
    py = prev_year(latest)
    mark = ""
    if py in keys:
        i = keys.index(py)
        px, pyy = pts[i].split(",")
        mark = '<circle class="yoho-spark-prev" cx="%s" cy="%s" r="3"/>' % (px, pyy)
    return ('<figure class="yoho-spark"><svg viewBox="0 0 %d %d" preserveAspectRatio="none" aria-hidden="true" focusable="false">'
            '<polyline points="%s"/>%s<circle class="yoho-spark-last" cx="%s" cy="%s" r="3.5"/></svg>'
            '<figcaption>%s〜%s。白い丸が前の年の同じ月</figcaption></figure>'
            % (w, h, " ".join(pts), mark, lx, ly, month_label(keys[0]), month_label(keys[-1])))


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
""" % (state, head, icon, word, e(ind["label"]), e(value), e(when_line(ind, rec)), e(sentence), spark(rec["series"], rec["latest"]),
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
""" % (breadcrumb([(YOHO_LABEL, None)]), e(YOHO_LABEL), e(YOHO.get("lead", "")), cards,
       ('<div class="yoho-later"><p>%s</p><ul>%s</ul></div>' % (e(YOHO.get("later_note", "")), later)) if later else "",
       mood_html, rules,
       ('<p>%s</p>' % e(ESTAT_CREDIT)) if uses_estat else "", ('<p>%s</p>' % e(DASH_CREDIT)) if uses_dash else "")
    page("/yoho/", YOHO_LABEL, YOHO.get("lead", ""), body, ctx=ctx,
         extra_head='<link rel="alternate" type="application/json" href="/yoho/latest.json" title="%s（JSON）">\n' % e(YOHO_LABEL))
