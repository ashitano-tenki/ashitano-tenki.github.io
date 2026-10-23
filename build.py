#!/usr/bin/env python3
"""あしたの転機観測所のサイトを作るスクリプト。

公開用CSVを読み込み、_site/ に静的なHTMLを書き出す。
Python の標準ライブラリだけで動く。

  python3 build.py                 # CSVをネットから取得して作る
  python3 build.py --csv data.csv  # 手元のCSVから作る
  python3 build.py --allow-decrease  # 件数が大きく減っても公開を止めない
"""
import argparse
import csv
import datetime
import html
import io
import json
import os
import re
import shutil
import sys
import unicodedata
import urllib.request
from urllib.parse import quote, urlencode

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "_site")
JST = datetime.timezone(datetime.timedelta(hours=9))

REQUIRED_COLUMNS = ["ID", "タイトル", "種類", "転機の種類", "段階", "観測メモ", "URL",
                    "提供元・著者", "費用", "最終観測日", "追加日", "観測スコア", "状態"]
LISTED_STATES = {"確認済み", "要更新"}
COST_ORDER = ["無料", "一部無料", "有料"]
COMMON = "共通"
OTHER = "その他"


class BuildError(Exception):
    pass


def load_json(name):
    with open(os.path.join(ROOT, "config", name), encoding="utf-8") as f:
        return json.load(f)


CONF = load_json("site.json")
TENKI_CONF = load_json("tenki.json")
TENKI = TENKI_CONF["tenki"]
STAGES = TENKI_CONF["stages"]
TENKI_BY_NAME = {t["name"]: t for t in TENKI}
STAGE_BY_NAME = {s["name"]: s for s in STAGES}
BASE = CONF["base_url"].rstrip("/")


# ---------------------------------------------------------------- データ

def fetch_csv(url):
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tenki-kansoku-build"})
            with urllib.request.urlopen(req, timeout=60) as res:
                return res.read().decode("utf-8-sig")
        except Exception as ex:  # 通信の一時的な失敗に備えて3回まで試す
            last = ex
    raise BuildError("CSVを取得できませんでした: %s" % last)


def split_list(value):
    return [v.strip() for v in re.split(r"[、,，/／]", value or "") if v.strip()]


def parse_date(value):
    value = (value or "").strip()
    m = re.match(r"(\d{4})[/\-.年](\d{1,2})[/\-.月](\d{1,2})", value)
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def parse_score(value):
    try:
        return float(unicodedata.normalize("NFKC", value or "").strip())
    except ValueError:
        return 0.0


def one_line(memo, limit=60):
    memo = (memo or "").strip()
    first = memo.split("。")[0]
    first = first + "。" if first and first != memo else first
    if len(first) > limit:
        first = first[:limit - 1] + "…"
    return first


def parse_rows(text):
    if text.lstrip().startswith("<"):
        raise BuildError("CSVの代わりにHTMLが返ってきました。公開設定を確認してください。")
    reader = csv.DictReader(io.StringIO(text))
    header = [h.strip() for h in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise BuildError("CSVに必要な列がありません: %s" % "、".join(missing))
    items, seen = [], set()
    for raw in reader:
        row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
        item_id = row["ID"]
        if not item_id or not row["タイトル"] or not re.match(r"^[A-Za-z0-9_-]+$", item_id):
            continue
        if item_id in seen:
            continue
        seen.add(item_id)
        items.append({
            "id": item_id,
            "title": row["タイトル"],
            "kind": row["種類"] or OTHER,
            "tenki": split_list(row["転機の種類"]),
            "stages": split_list(row["段階"]),
            "memo": row["観測メモ"],
            "url": row["URL"] if re.match(r"^https?://", row["URL"]) else "",
            "provider": row["提供元・著者"],
            "cost": row["費用"],
            "observed": parse_date(row["最終観測日"]),
            "added": parse_date(row["追加日"]),
            "score": parse_score(row["観測スコア"]),
            "listed": row["状態"] in LISTED_STATES,
            "line": one_line(row["観測メモ"]),
        })
    # 並び順は観測スコアの高い順。スコアは並べ替えにだけ使い、出力には rank（順位）だけを残す
    items.sort(key=lambda it: (-it["score"], -(it["added"] or datetime.date.min).toordinal(), it["id"]))
    for i, it in enumerate(items):
        it["rank"] = i + 1
    return items


def matches_tenki(item, name):
    if name in item["tenki"]:
        return True
    # 「共通」はどの転機にも役立つものなので、個別の転機にも含める
    return name not in (COMMON, OTHER) and COMMON in item["tenki"]


def kinds_of(items):
    order = CONF.get("kind_order", [])
    found = sorted({it["kind"] for it in items},
                   key=lambda k: (order.index(k) if k in order else len(order), k))
    return found


def by_kind(items):
    groups = {}
    for it in items:
        groups.setdefault(it["kind"], []).append(it)
    return [(k, groups[k]) for k in kinds_of(items)]


# ---------------------------------------------------------------- HTML部品

def e(s):
    return html.escape(str(s), quote=True)


def search_url(**params):
    params = {k: v for k, v in params.items() if v}
    return "/search/" + ("?" + urlencode(params) if params else "")


def fmt_date(d):
    return "%d年%d月%d日" % (d.year, d.month, d.day) if d else "不明"


def tenki_url(t):
    return "/tenki/%s/" % t["slug"]


def tag_list(item):
    tags = ['<span class="tag tag-kind">%s</span>' % e(item["kind"])]
    if item["cost"]:
        tags.append('<span class="tag tag-cost">%s</span>' % e(item["cost"]))
    return '<div class="tags">%s</div>' % "".join(tags)


def when_line(item):
    """カードの「誰の・いつの」一行。例：起業、独立｜準備"""
    tenki = "どの転機にも" if COMMON in item["tenki"] else "、".join(item["tenki"])
    return "｜".join(x for x in [tenki, "、".join(item["stages"])] if x)


def added_label(d, today):
    if not d:
        return ""
    if d.year == today.year:
        return "%d月%d日に追加" % (d.month, d.day)
    return "%d年%d月%d日に追加" % (d.year, d.month, d.day)


def card(item, today):
    return ('<li class="card"><a href="/item/%s/"><p class="card-when">%s</p><h3>%s</h3><p class="card-line">%s</p>'
            '<div class="card-foot">%s<span class="card-date">%s</span></div></a></li>'
            % (e(item["id"]), e(when_line(item)), e(item["title"]), e(item["line"]), tag_list(item),
               e(added_label(item["added"], today))))


def cards(items, ctx):
    return '<ul class="cards">%s</ul>' % "".join(card(it, ctx["today"]) for it in items)


def breadcrumb(parts):
    links = ['<a href="/">トップ</a>']
    for label, href in parts:
        links.append('<a href="%s">%s</a>' % (e(href), e(label)) if href else '<span>%s</span>' % e(label))
    return '<nav class="crumbs" aria-label="現在地">%s</nav>' % ' <span aria-hidden="true">›</span> '.join(links)


def page(path, title, description, body, *, full_title=None, noindex=False, ctx):
    """1ページ分のHTMLを書き出す。path はサイト内のパス（例: /tenki/dokuritsu/）。"""
    site = CONF["site_name"]
    doc_title = full_title or ("%s｜%s" % (title, site))
    url = BASE + path
    robots = '<meta name="robots" content="noindex">\n' if noindex else ""
    html_text = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{doc_title}</title>
<meta name="description" content="{desc}">
{robots}<link rel="canonical" href="{url}">
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="{site}">
<meta property="og:title" content="{og_title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{base}/assets/ogp.png">
<meta property="og:locale" content="ja_JP">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/assets/favicon-32.png" type="image/png" sizes="32x32">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<script>try{{if(localStorage.getItem("theme")==="dark")document.documentElement.setAttribute("data-theme","dark")}}catch(e){{}}</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700&family=Zen+Kaku+Gothic+New:wght@700;900&display=swap">
<link rel="stylesheet" href="/assets/style.css?v={ver}">
</head>
<body>
<header class="site-header">
  <div class="wrap header-inner">
    <a class="logo" href="/"><img class="logo-mark" src="/assets/logo.svg" alt="" width="24" height="24">{site}</a>
    <nav class="global-nav" aria-label="サイト内">
      <a href="/search/">探す</a>
      <a href="/tenki/">転機から</a>
      <a href="/check/">セルフチェック</a>
      <a href="/report/">観測レポート</a>
    </nav>
    <button type="button" class="theme-toggle" id="theme-toggle" aria-pressed="false">ダーク表示</button>
  </div>
</header>
<main class="wrap">
{body}
</main>
<footer class="site-footer">
  <div class="wrap">
    <p class="ai-note">掲載情報はAIが収集・確認し、定期的に点検しています。</p>
    <div class="community">
      <p>この観測所は、黒田悠介が運営する「あしたの転機」の一部です。転機について考える記事はnoteマガジン「あしたの転機」で、同じように転機を迎えている人との交流はFacebookグループ「あしたの転機」で続けています。</p>
      <p class="community-links">
        <a href="{note}" rel="noopener" target="_blank">noteマガジン「あしたの転機」</a>
        <a href="{fb}" rel="noopener" target="_blank">Facebookグループ「あしたの転機」</a>
      </p>
    </div>
    <p class="contact">掲載情報の誤りのお知らせや掲載のご提案は、<a href="{contact}" rel="noopener" target="_blank">観測所へのご連絡</a>のフォームからお送りください。</p>
    <p class="footer-meta"><a href="/about/">観測所について</a>・<a href="/report/">観測レポート</a>・最終更新 {updated}</p>
  </div>
</footer>
<script src="/assets/theme.js?v={ver}"></script>
</body>
</html>
""".format(doc_title=e(doc_title), desc=e(description), robots=robots, url=e(url),
           og_type="website" if path == "/" else "article", site=e(site),
           og_title=e(full_title or title), base=e(BASE), ver=ctx["version"], body=body,
           note=e(CONF["note_url"]), fb=e(CONF["facebook_url"]), contact=e(CONF["contact_form_url"]),
           updated=fmt_date(ctx["today"]))
    write(path, html_text)
    if not noindex:
        ctx["sitemap"].append(url)


def write(path, text):
    target = os.path.join(OUT, path.lstrip("/"))
    if path.endswith("/"):
        target = os.path.join(target, "index.html")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(text)


def more_link(href, label):
    return '<p class="more"><a href="%s">%s</a></p>' % (e(href), e(label))


def kind_sections(items, params, ctx, heading_level=2):
    """種類ごとに上位数件を並べ、残りは一覧ページの該当条件へつなぐ。"""
    n = CONF["top_per_kind"]
    out = []
    for kind, group in by_kind(items):
        h = "h%d" % heading_level
        sec = ['<section class="kind-block"><%s>%s <span class="count">%d件</span></%s>' % (h, e(kind), len(group), h)]
        sec.append(cards(group[:n], ctx))
        if len(group) > n:
            sec.append(more_link(search_url(kind=kind, **params), "%sをもっと見る（全%d件）" % (kind, len(group))))
        sec.append("</section>")
        out.append("".join(sec))
    return "\n".join(out)


# ---------------------------------------------------------------- ページ

def build_home(listed, ctx):
    new_items = sorted(ctx["new_items"], key=lambda it: (it["added"], -it["rank"]), reverse=True)
    tenki_links = "".join(
        '<li><a href="%s">%s<span class="count">%d</span></a></li>' % (tenki_url(t), e(t["name"]), ctx["tenki_count"][t["name"]])
        for t in TENKI if ctx["tenki_count"][t["name"]])
    stage_links = "".join(
        '<li><a href="%s"><strong>%s</strong><span>%s</span></a></li>' % (e(search_url(stage=s["name"])), e(s["name"]), e(s["about"]))
        for s in STAGES)
    kind_links = "".join(
        '<li><a href="%s">%s<span class="count">%d</span></a></li>' % (e(search_url(kind=k)), e(k), len(g))
        for k, g in by_kind(listed))
    if new_items:
        news = cards(new_items[:12], ctx)
        if len(new_items) > 12:
            news += more_link(search_url(sort="new"), "今週の新着をすべて見る（%d件）" % len(new_items))
    else:
        news = '<p class="empty">この1週間に追加されたものはありません。</p>'
    body = """
<section class="hero">
  <p class="label">Observatory for career transitions</p>
  <h1>{site}</h1>
  <p class="lead">{lead}</p>
  <p class="check-link"><a href="/check/">いまの段階をチェックする</a><span>（18の質問で、転機のどの段階にいるかをふりかえる）</span></p>
  <form class="search-box" action="/search/" method="get" role="search">
    <label for="home-q" class="visually-hidden">キーワード</label>
    <input id="home-q" type="search" name="q" placeholder="キーワードで探す（例：フリーランス、確定申告）">
    <button type="submit">探す</button>
  </form>
  <p class="hero-meta">掲載中 {total}件・毎朝更新</p>
</section>

<section class="entrances">
  <div class="entrance">
    <h2>転機から探す</h2>
    <ul class="chips">{tenki_links}</ul>
  </div>
  <div class="entrance">
    <h2>今の段階から探す</h2>
    <ul class="stages">{stage_links}</ul>
  </div>
  <div class="entrance">
    <h2>タイプから探す</h2>
    <p class="note">相談・仕事・学習など、サービスのタイプで探せます。</p>
    <ul class="chips">{kind_links}</ul>
  </div>
</section>

<section class="section">
  <p class="label">New this week</p>
  <h2 class="section-title">今週の新着</h2>
  {news}
  <p class="more"><a href="/report/">週ごとの観測レポートを見る</a></p>
</section>

<section class="section">
  <p class="label">By category</p>
  <h2 class="section-title">タイプごとに見る</h2>
  <p class="note">タイプごとに、観測所の並び順で上位のものを紹介しています。並び順の考え方は<a href="/about/#order">観測所について</a>に書いています。</p>
  {kinds}
</section>
""".format(site=e(CONF["site_name"]), lead=e(CONF["lead"]), total=len(listed), tenki_links=tenki_links,
           stage_links=stage_links, kind_links=kind_links, news=news,
           kinds=kind_sections(listed, {}, ctx, heading_level=3))
    page("/", CONF["site_name"], CONF["description"], body,
         full_title="%s｜転機の種類と時期から探す、キャリアの転機に役立つサービス" % CONF["site_name"], ctx=ctx)


def combo_title(t, s):
    return s["title"].format(name=t["name"], past=t["past"])


def combo_lead(t, s):
    return s["lead"].format(name=t["name"], past=t["past"])


def build_tenki(listed, ctx):
    index_rows = []
    for t in TENKI:
        items = [it for it in listed if matches_tenki(it, t["name"])]
        if not items:
            continue
        combos = []
        if t["past"]:
            for s in STAGES:
                sub = [it for it in items if s["name"] in it["stages"]]
                if len(sub) >= CONF["min_combo_items"]:
                    combos.append((s, sub))
                    build_combo(t, s, sub, ctx)
        stage_nav = ""
        if combos:
            stage_nav = '<nav class="stage-nav" aria-label="段階で絞る"><h2>段階から探す</h2><ul>%s</ul></nav>' % "".join(
                '<li><a href="/tenki/%s/%s/"><strong>%s</strong><span>%s</span></a></li>'
                % (t["slug"], s["slug"], e(s["name"]), e(combo_title(t, s))) for s, sub in combos)
        common_note = ""
        if t["name"] not in (COMMON, OTHER):
            common_note = '<p class="note">どの転機にも役立つもの（共通）も含めています。</p>'
        heading = "%sに役立つサービスと情報" % t["name"] if t["name"] not in (COMMON, OTHER) else (
            "どの転機にも役立つサービスと情報" if t["name"] == COMMON else "そのほかの転機に役立つサービスと情報")
        body = """
{crumbs}
<header class="page-head">
  <h1>{heading}</h1>
  <p class="lead">{about}</p>
  <p class="page-meta">掲載中 {n}件</p>
</header>
{stage_nav}
<section class="section">
  <h2 class="section-title">タイプごとに見る</h2>
  {common_note}
  {kinds}
  {more}
</section>
""".format(crumbs=breadcrumb([("転機から探す", "/tenki/"), (t["name"], None)]), heading=e(heading), about=e(t["about"]),
           n=len(items), stage_nav=stage_nav, common_note=common_note,
           kinds=kind_sections(items, {"tenki": t["name"]}, ctx, heading_level=3),
           more=more_link(search_url(tenki=t["name"]), "%sの掲載情報をすべて見る" % t["name"]))
        page(tenki_url(t), heading, t["about"], body, ctx=ctx)
        index_rows.append((t, items, combos))

    rows = []
    for t, items, combos in index_rows:
        combo_html = ""
        if combos:
            combo_html = "<ul class=\"sub-links\">%s</ul>" % "".join(
                '<li><a href="/tenki/%s/%s/">%s</a></li>' % (t["slug"], s["slug"], e(combo_title(t, s))) for s, sub in combos)
        rows.append('<li class="tenki-row"><a class="tenki-name" href="%s">%s <span class="count">%d件</span></a><p>%s</p>%s</li>'
                    % (tenki_url(t), e(t["name"]), len(items), e(t["about"]), combo_html))
    stage_dl = "".join("<div><dt>%s</dt><dd>%s</dd></div>" % (e(s["name"]), e(s["about"])) for s in STAGES)
    body = """
{crumbs}
<header class="page-head">
  <h1>転機から探す</h1>
  <p class="lead">転職、独立、起業など、迎えている転機を選んでください。転機ごとのページでは、段階に分けて探すこともできます。</p>
</header>
<ul class="tenki-list">{rows}</ul>
<section class="section">
  <h2 class="section-title">段階について</h2>
  <p class="note">観測所では、転機の時期を4つの段階に分けています。</p>
  <dl class="stage-dl">{stage_dl}</dl>
</section>
""".format(crumbs=breadcrumb([("転機から探す", None)]), rows="".join(rows), stage_dl=stage_dl)
    page("/tenki/", "転機から探す", "転職、独立、起業、副業、退職・休職、定年、学び直し。迎えている転機から、役立つサービスと情報を探せます。", body, ctx=ctx)


def build_combo(t, s, items, ctx):
    title = combo_title(t, s)
    body = """
{crumbs}
<header class="page-head">
  <p class="kicker">{tenki} × {stage}</p>
  <h1>{title}</h1>
  <p class="lead">{lead}</p>
  <p class="page-meta">掲載中 {n}件</p>
</header>
<section class="section">
  {kinds}
  {more}
</section>
""".format(crumbs=breadcrumb([("転機から探す", "/tenki/"), (t["name"], tenki_url(t)), (s["name"], None)]),
           tenki=e(t["name"]), stage=e(s["name"]), title=e(title), lead=e(combo_lead(t, s)), n=len(items),
           kinds=kind_sections(items, {"tenki": t["name"], "stage": s["name"]}, ctx, heading_level=2),
           more=more_link(search_url(tenki=t["name"], stage=s["name"]), "この条件の掲載情報をすべて見る"))
    page("/tenki/%s/%s/" % (t["slug"], s["slug"]), title, combo_lead(t, s), body, ctx=ctx)


def similar_items(item, listed, limit=4):
    def score(other):
        tenki = len(set(item["tenki"]) & set(other["tenki"]))
        stage = len(set(item["stages"]) & set(other["stages"]))
        return tenki, stage
    pool = []
    for o in listed:
        if o["id"] == item["id"]:
            continue
        tenki, stage = score(o)
        if tenki and stage:
            pool.append((0, -(tenki * 2 + stage), o["rank"], o))
        elif tenki:
            pool.append((1, -tenki, o["rank"], o))
    pool.sort(key=lambda x: x[:3])
    return [p[3] for p in pool[:limit]]


def report_link(item):
    url = CONF.get("report_form_url", "")
    if not url:
        return '<p class="report">情報の誤りに気づいたときのお知らせフォームは準備中です。</p>'
    href = url.replace("{id}", quote(item["id"])).replace("{title}", quote(item["title"]))
    return '<p class="report"><a href="%s" rel="noopener" target="_blank">この情報の誤りを知らせる</a>（フォームが開きます）</p>' % e(href)


def build_item(item, listed, ctx):
    def links(names, lookup, make):
        out = []
        for n in names:
            out.append('<a href="%s">%s</a>' % (e(make(n)), e(n)) if n in lookup else e(n))
        return "、".join(out) or "―"

    similar = similar_items(item, listed)
    similar_html = ""
    if similar:
        similar_html = '<section class="section"><h2 class="section-title">同じ転機・段階で役立つもの</h2>%s</section>' % cards(similar, ctx)

    crumbs = breadcrumb([("探す", "/search/"), (item["title"], None)])
    if not item["listed"]:
        body = """
{crumbs}
<article class="detail ended">
  <h1>{title}</h1>
  <p class="ended-note">このサービスは提供を終了したか、掲載を終えました。</p>
  <p class="note">ほかのサービスは<a href="/search/">一覧ページ</a>から探せます。</p>
</article>
{similar}
""".format(crumbs=crumbs, title=e(item["title"]), similar=similar_html)
        page("/item/%s/" % item["id"], item["title"], "このサービスは提供を終了したか、掲載を終えました。", body, noindex=True, ctx=ctx)
        return

    official = ('<p class="official"><a class="button" href="%s" rel="noopener" target="_blank">公式サイトを見る</a></p>'
                % e(item["url"])) if item["url"] else ""
    tenki_links = links(item["tenki"], TENKI_BY_NAME, lambda n: tenki_url(TENKI_BY_NAME[n]))
    stage_links = links(item["stages"], STAGE_BY_NAME, lambda n: search_url(stage=n))
    body = """
{crumbs}
<article class="detail">
  <p class="kicker"><a href="{kind_url}">{kind}</a></p>
  <h1>{title}</h1>
  <div class="memo"><h2 class="visually-hidden">観測メモ</h2><p>{memo}</p></div>
  {official}
  <dl class="facts">
    <div><dt>タイプ</dt><dd><a href="{kind_url}">{kind}</a></dd></div>
    <div><dt>転機</dt><dd>{tenki}</dd></div>
    <div><dt>段階</dt><dd>{stages}</dd></div>
    <div><dt>費用</dt><dd>{cost}</dd></div>
    <div><dt>提供元</dt><dd>{provider}</dd></div>
    <div><dt>最終観測日</dt><dd>{observed}</dd></div>
  </dl>
  <p class="note">料金や内容は変わることがあります。利用する前に公式サイトで確かめてください。</p>
  {report}
</article>
{similar}
""".format(crumbs=crumbs, kind_url=e(search_url(kind=item["kind"])), kind=e(item["kind"]), title=e(item["title"]),
           memo=e(item["memo"]), official=official, tenki=tenki_links, stages=stage_links, cost=e(item["cost"] or "―"),
           provider=e(item["provider"] or "―"), observed=fmt_date(item["observed"]), report=report_link(item),
           similar=similar_html)
    desc = item["memo"][:110] or "%sの紹介ページです。" % item["title"]
    page("/item/%s/" % item["id"], item["title"], desc, body, ctx=ctx)


def build_search(listed, ctx):
    def options(values):
        return "".join('<option value="%s">%s</option>' % (e(v), e(v)) for v in values)
    costs = [c for c in COST_ORDER if any(it["cost"] == c for it in listed)]
    costs += sorted({it["cost"] for it in listed if it["cost"] and it["cost"] not in COST_ORDER})
    body = """
{crumbs}
<header class="page-head page-head-tight">
  <h1>探す</h1>
</header>
<form id="filters" class="filters" action="/search/" method="get" role="search">
  <div class="search-q">
    <label for="q" class="visually-hidden">キーワード</label>
    <input id="q" type="search" name="q" placeholder="キーワードで探す（例：フリーランス、確定申告）">
  </div>
  <div class="search-layout">
    <div class="filter-col">
      <button type="button" id="filter-toggle" class="filter-toggle" aria-expanded="false" aria-controls="filter-panel">絞り込む<span id="filter-count"></span></button>
      <div id="filter-panel" class="filter-panel">
        <div class="field"><label for="kind">タイプ</label><select id="kind" name="kind"><option value="">すべて</option>{kinds}</select></div>
        <div class="field"><label for="tenki">転機</label><select id="tenki" name="tenki"><option value="">すべて</option>{tenki}</select></div>
        <div class="field"><label for="stage">段階</label><select id="stage" name="stage"><option value="">すべて</option>{stages}</select></div>
        <div class="field"><label for="cost">費用</label><select id="cost" name="cost"><option value="">すべて</option>{costs}</select></div>
        <p class="note filter-note">条件はURLに残るので、そのまま共有できます。</p>
        <noscript><button type="submit">この条件で探す</button></noscript>
      </div>
    </div>
    <div class="result-col">
      <div class="result-bar">
        <p id="result-count" aria-live="polite">読み込み中…</p>
        <div class="sort-field"><label for="sort">並び順</label><select id="sort" name="sort"><option value="">観測所の並び順</option><option value="new">新着順</option></select></div>
      </div>
      <div id="active-chips" class="active-chips" hidden></div>
      <ul id="results" class="cards"></ul>
      <p class="more-wrap"><button type="button" id="more" class="button" hidden>もっと見る</button></p>
    </div>
  </div>
</form>
<noscript><p class="note">検索にはJavaScriptを使います。使えない場合は<a href="/tenki/">転機から探す</a>をご利用ください。</p></noscript>
<script>window.TENKI_PAGE_SIZE = {page_size}; window.TENKI_THIS_YEAR = {year};</script>
<script src="/assets/search.js?v={ver}" defer></script>
""".format(crumbs=breadcrumb([("探す", None)]), kinds=options(kinds_of(listed)),
           tenki=options([t["name"] for t in TENKI]), stages=options([s["name"] for s in STAGES]),
           costs=options(costs), page_size=int(CONF["list_page_size"]), year=ctx["today"].year, ver=ctx["version"])
    page("/search/", "探す", "キャリアの転機に役立つサービスと情報を、タイプ・転機・段階・費用で絞り込み、キーワードで検索できます。", body, ctx=ctx)


def build_report(listed, ctx):
    weeks = {}
    for it in listed:
        if not it["added"]:
            continue
        start = it["added"] - datetime.timedelta(days=it["added"].weekday())
        weeks.setdefault(start, []).append(it)
    sections = []
    for start in sorted(weeks, reverse=True):
        end = start + datetime.timedelta(days=6)
        group = sorted(weeks[start], key=lambda it: (it["added"], -it["rank"]), reverse=True)
        heading = "%d年%d月%d日〜%d月%d日" % (start.year, start.month, start.day, end.month, end.day)
        sections.append('<section class="week" id="w%s"><h2>%s <span class="count">%d件</span></h2>%s</section>'
                        % (start.strftime("%Y%m%d"), e(heading), len(group), cards(group, ctx)))
    body = """
{crumbs}
<header class="page-head">
  <h1>観測レポート</h1>
  <p class="lead">観測所に新しく加わったサービスと情報を、週ごとにまとめています（週は月曜日から日曜日まで）。</p>
</header>
{sections}
""".format(crumbs=breadcrumb([("観測レポート", None)]),
           sections="\n".join(sections) or '<p class="empty">まだ記録がありません。</p>')
    page("/report/", "観測レポート", "あしたの転機観測所に新しく加わったサービスと情報を、週ごとにまとめています。", body, ctx=ctx)


def build_about(listed, ctx):
    stage_dl = "".join("<div><dt>%s</dt><dd>%s</dd></div>" % (e(s["name"]), e(s["about"])) for s in STAGES)
    body = """
{crumbs}
<article class="prose">
<h1>観測所について</h1>

<h2>この観測所の目的</h2>
<p>あしたの転機観測所は、転職、独立、起業、副業など、キャリアの転機を迎えた人が、その時期に使えるサービスや情報を探せるようにしたサイトです。</p>
<p>同じ転機でも、考え始めた時期と、迎えた直後と、慣れてきた時期とでは、必要なものが変わります。そこで、転機の種類と、今どの段階にいるかの二つから探せるようにしています。</p>
<dl class="stage-dl">{stage_dl}</dl>

<h2>掲載の基準</h2>
<p>掲載しているのは、民間の企業や団体、個人が提供しているサービスと情報だけです。国や自治体の制度、公的な窓口は載せていません。</p>
<p>提供が終わったものや掲載を終えたものは、一覧と検索から外します。外部から紹介ページへのリンクが切れないように、紹介ページだけは残し、掲載を終えたことを表示します。</p>

<h2 id="order">並び順の考え方</h2>
<p>特定の人や時期に特化しているか、運営の実績、無料で試せるか、情報の新しさをもとに並べています。掲載依頼や広告で順番を変えることはありません。</p>

<h2>情報の集め方と点検</h2>
<p>掲載情報は、AIが公開されている情報をもとに集め、内容を確かめてから載せています。載せたあともAIが定期的に点検し、内容を確かめた日を「最終観測日」として表示しています。</p>
<p>料金や内容は変わることがあります。利用する前に、公式サイトで最新の情報を確かめてください。</p>

<h2 id="contact">観測所へのご連絡</h2>
<p>掲載情報の誤りのお知らせや、掲載してほしいサービス・情報のご提案は、<a href="{contact}" rel="noopener" target="_blank">観測所へのご連絡</a>のフォームから受け付けています。</p>
<ul>
  <li>ご提案いただいたものも、ほかの掲載情報と同じ基準で確かめてから掲載するかどうかを決めます。掲載をお約束するものではありません。</li>
  <li>ご提案によって並び順が変わることはありません。</li>
  <li>掲載料をいただく掲載や、広告としての掲載は行っていません。</li>
  <li>個別のご返信はしていません。</li>
</ul>

<h2>運営者</h2>
<p>運営は黒田悠介です。キャリア研究家として、これまでに1,000人以上のキャリア相談を受けてきました。著書に『ライフピボット』などがあります。</p>

<h2>あしたの転機について</h2>
<p>「あしたの転機」は、キャリアの転機について考え、転機を迎えている人どうしがつながるための場です。この観測所はその一部として運営しています。</p>
<ul>
  <li><a href="{note}" rel="noopener" target="_blank">noteマガジン「あしたの転機」</a>：転機について考える記事を載せています。</li>
  <li><a href="{fb}" rel="noopener" target="_blank">Facebookグループ「あしたの転機」</a>：同じように転機を迎えている人と交流できます。</li>
</ul>
</article>
""".format(crumbs=breadcrumb([("観測所について", None)]), stage_dl=stage_dl,
           note=e(CONF["note_url"]), fb=e(CONF["facebook_url"]), contact=e(CONF["contact_form_url"]))
    page("/about/", "観測所について", "あしたの転機観測所の目的、掲載の基準、並び順の考え方、情報の集め方と運営者について。", body, ctx=ctx)


def build_404(ctx):
    body = """
<header class="page-head">
  <h1>ページが見つかりません</h1>
  <p class="lead">お探しのページは移動したか、削除された可能性があります。</p>
</header>
<p><a class="button" href="/">トップへ戻る</a> <a class="button button-ghost" href="/search/">一覧から探す</a></p>
"""
    page("/404.html", "ページが見つかりません", CONF["description"], body, noindex=True, ctx=ctx)


# ---------------------------------------------------------------- 出力

def normalize(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    # ひらがなをカタカナにそろえる（「ふりーらんす」でも見つかるように）
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in s)


def build_search_json(listed, ctx):
    synonyms = load_json("synonyms.json").get("groups", [])
    data = {
        "items": [{
            "id": it["id"], "title": it["title"], "line": it["line"], "kind": it["kind"],
            "tenki": it["tenki"], "stages": it["stages"], "cost": it["cost"],
            "added": it["added"].isoformat() if it["added"] else "",
            "rank": it["rank"], "new": it["id"] in ctx["new_ids"],
            "text": normalize(" ".join([it["title"], it["memo"], it["provider"], it["kind"],
                                        " ".join(it["tenki"]), " ".join(it["stages"])])),
        } for it in listed],
        "synonyms": [[normalize(w) for w in g if w.strip()] for g in synonyms if isinstance(g, list)],
    }
    write("/search.json", json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def build_check(listed, ctx):
    """転機の段階セルフチェック（check/index.html）と、結果画面のおすすめに使う picks.json を書き出す。"""
    with open(os.path.join(ROOT, "check", "index.html"), encoding="utf-8") as f:
        write("/check/", f.read())
    ctx["sitemap"].append(BASE + "/check/")
    data = {"items": [{
        "id": it["id"], "title": it["title"], "type": it["kind"], "tenki": it["tenki"], "stage": it["stages"],
        "memo": it["memo"], "url": it["url"], "cost": it["cost"], "rank": it["rank"],
        "page": "/item/%s/" % it["id"],
    } for it in listed]}
    write("/check/picks.json", json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def build_meta_files(ctx):
    urls = "".join("<url><loc>%s</loc></url>" % e(u) for u in ctx["sitemap"])
    write("/sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>\n' % urls)
    write("/robots.txt", "User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % BASE)
    write("/.nojekyll", "")


def check_counts(items, listed, allow_decrease):
    """データの一時的な不具合でサイトが空になるのを防ぐ。"""
    if not listed:
        raise BuildError("掲載中の件数が0件です。公開を中止します。")
    meta_path = os.path.join(ROOT, "data", "meta.json")
    if os.path.exists(meta_path) and not allow_decrease:
        with open(meta_path, encoding="utf-8") as f:
            prev = json.load(f).get("listed", 0)
        if prev and len(listed) < prev * CONF["min_ratio_to_previous"]:
            raise BuildError("掲載中の件数が前回の%d件から%d件に減りました。データの不具合の可能性があるため公開を中止します。"
                             % (prev, len(listed)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="手元のCSVファイルを使う")
    ap.add_argument("--allow-decrease", action="store_true", help="件数が大きく減っても公開する")
    ap.add_argument("--today", help="今日の日付（確認用。例: 2026-10-22）")
    args = ap.parse_args()

    if args.csv:
        with open(args.csv, encoding="utf-8-sig") as f:
            text = f.read()
    else:
        text = fetch_csv(CONF["csv_url"])
    items = parse_rows(text)
    listed = [it for it in items if it["listed"]]
    check_counts(items, listed, args.allow_decrease)

    today = (datetime.date.fromisoformat(args.today) if args.today
             else datetime.datetime.now(JST).date())
    since = today - datetime.timedelta(days=CONF["new_days"] - 1)
    new_items = [it for it in listed if it["added"] and since <= it["added"] <= today]
    ctx = {
        "today": today,
        "version": today.strftime("%Y%m%d"),
        "sitemap": [],
        "new_items": new_items,
        "new_ids": {it["id"] for it in new_items},
        "tenki_count": {t["name"]: sum(1 for it in listed if matches_tenki(it, t["name"])) for t in TENKI},
    }

    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(os.path.join(ROOT, "assets"), os.path.join(OUT, "assets"))

    build_home(listed, ctx)
    build_search(listed, ctx)
    build_tenki(listed, ctx)
    for it in items:
        build_item(it, listed, ctx)
    build_report(listed, ctx)
    build_about(listed, ctx)
    build_404(ctx)
    build_check(listed, ctx)
    build_search_json(listed, ctx)
    build_meta_files(ctx)

    meta = {"built": today.isoformat(), "total": len(items), "listed": len(listed)}
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    with open(os.path.join(ROOT, "data", "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("作成しました: 全%d件（掲載中%d件、今週の新着%d件、ページ%d枚）"
          % (len(items), len(listed), len(new_items), len(ctx["sitemap"])))


if __name__ == "__main__":
    try:
        main()
    except BuildError as ex:
        print("中止: %s" % ex, file=sys.stderr)
        sys.exit(1)
