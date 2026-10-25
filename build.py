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
import hashlib
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
NOTES = load_json("tenki_notes.json")  # 転機別・転機×段階のページに載せる解説文
TENKI = TENKI_CONF["tenki"]
STAGES = TENKI_CONF["stages"]
TENKI_BY_NAME = {t["name"]: t for t in TENKI}
STAGE_BY_NAME = {s["name"]: s for s in STAGES}
BASE = CONF["base_url"].rstrip("/")
KINDS = CONF["kinds"]  # 種類（タイプ）の一覧と表示順
KIND_BY_NAME = {k["name"]: k for k in KINDS}


def load_images():
    """掲載先のシェア用画像の記録（tools/fetch_images.py が書く data/images.json）。画像が取れたものだけを返す。"""
    path = os.path.join(ROOT, "data", "images.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    exclude = set(CONF.get("image_exclude", []))
    out = {}
    for item_id, rec in data.items():
        if (rec.get("status") == "ok" and item_id not in exclude
                and os.path.exists(os.path.join(ROOT, "images", "items", item_id + ".webp"))
                and os.path.exists(os.path.join(ROOT, "images", "items", item_id + "-s.webp"))):
            out[item_id] = rec
    return out


IMAGES = load_images()


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


def parse_month(value):
    """「2026/07」「2026/7」「2026-07」を (2026, 7) にする。読めなければ None。"""
    m = re.match(r"\s*(\d{4})\s*[/\-.年]\s*(\d{1,2})", unicodedata.normalize("NFKC", value or ""))
    if not m or not 1 <= int(m.group(2)) <= 12:
        return None
    return int(m.group(1)), int(m.group(2))


def fix_memo(text):
    """観測メモの言い回しを整える。「〜に向く。」は不自然なので「〜に向いている。」にする（スプレッドシートはそのまま）。"""
    return re.sub(r"に向く(?=。|$)", "に向いている", text or "")


def month_label(ym):
    return "%d年%d月" % ym if ym else ""


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
    items, seen, skipped = [], set(), []
    for raw in reader:
        row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
        item_id = row["ID"]
        if not item_id or not row["タイトル"] or not re.match(r"^[A-Za-z0-9_-]+$", item_id):
            continue
        if item_id in seen:
            continue
        seen.add(item_id)
        if row["種類"] not in KIND_BY_NAME:
            skipped.append("%s（%s）" % (item_id, row["種類"] or "種類なし"))
            continue
        items.append({
            "id": item_id,
            "title": row["タイトル"],
            "kind": row["種類"],
            "tenki": split_list(row["転機の種類"]),
            "stages": split_list(row["段階"]),
            "memo": fix_memo(row["観測メモ"]),
            "url": row["URL"] if re.match(r"^https?://", row["URL"]) else "",
            "provider": row["提供元・著者"],
            "observed": parse_date(row["最終観測日"]),
            "added": parse_date(row["追加日"]),
            "score": parse_score(row["観測スコア"]),
            "listed": row["状態"] in LISTED_STATES,
            "line": one_line(row["観測メモ"]),
            "published": parse_month(row.get("発表・更新時期", "")),
            # 向いている人（任意の列。「40代、女性」のように区切って書く。列がなければ空）。
            # 画面には出さず、キーワード検索の対象にだけ入れる（自分の属性が書かれていない人に疎外感を与えないため）
            "for": [x.strip() for x in re.split(r"[、,，/／]", row.get("向いている人", "")) if x.strip()],
        })
    if skipped:
        print("設定にない種類のため表示から外しました: %s" % "、".join(skipped))
    # 並び順（おすすめ順）は、掲載先の画像があるものを先に、そのなかで観測スコアの高い順。
    # スコアは並べ替えにだけ使い、出力には rank（順位）だけを残す。トップの棚・転機のページ・探すページなど、
    # rank を使う並びはすべてこの順になる（新着の一覧は追加日の新しい順で、同じ日のなかがこの順）
    items.sort(key=lambda it: (it["id"] not in IMAGES, -it["score"], -(it["added"] or datetime.date.min).toordinal(), it["id"]))
    for i, it in enumerate(items):
        it["rank"] = i + 1
    return items


def matches_tenki(item, name):
    if name in item["tenki"]:
        return True
    # 「共通」はどの転機にも役立つものなので、個別の転機にも含める
    return name not in (COMMON, OTHER) and COMMON in item["tenki"]


def kinds_of(items):
    """データに1件以上ある種類だけを、設定の順に返す（0件の種類は出さない）。"""
    present = {it["kind"] for it in items}
    return [k["name"] for k in KINDS if k["name"] in present]


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


def tag_list(item, kind=True):
    # 有料・無料は出さない（すっきりさせるため。カードにも紹介ページの表にも出さない）
    tags = ['<span class="tag tag-kind">%s</span>' % e(item["kind"])] if kind else []
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


SAVE_ICON = ('<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">'
             '<path d="M6 3h12v18l-6-4.5L6 21z" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>')


SHARE_ICON = ('<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M12 3v12M7 8l5-5 5 5M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6" '
              'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def save_button(item):
    return ('<button type="button" class="save-btn" data-save="%s" data-title="%s" aria-pressed="false" '
            'aria-label="「%s」をあとで見る" hidden>%s</button>' % (e(item["id"]), e(item["title"]), e(item["title"]), SAVE_ICON))


def card(item, today, kind=True, date=False):
    """カード1枚。kind=False はタイプのまとまりの中（タイプは見出しでわかる）、date=True は新着の一覧で使う。"""
    added = '<span class="card-date">%s</span>' % e(added_label(item["added"], today)) if date else ""
    # 読み上げではタイトルから聞こえるように、リンクの名前を「タイトル（転機｜段階）」にする
    return ('<li class="card"><a href="/item/%s/" aria-label="%s（%s）">%s<div class="card-body"><p class="card-when" title="%s">%s</p>'
            '<h3>%s</h3><p class="card-line">%s</p><div class="card-foot">%s%s</div></div></a>%s</li>'
            % (e(item["id"]), e(item["title"]), e(when_line(item)), item_media(item, "card-media", True), e(when_line(item)), e(when_line(item)), e(item["title"]),
               e(item["line"]), tag_list(item, kind), added, save_button(item)))


def cards(items, ctx, kind=True, date=False, cls=""):
    """cls="list-compact" は長い一覧用（スマホでは左に小さな画像の横長カードになる）。"""
    return '<ul class="cards%s">%s</ul>' % (" " + cls if cls else "", "".join(card(it, ctx["today"], kind, date) for it in items))


def sm_shelf(items_html, n, label, more_href="", more_label="", more_count=0, extra_cls=""):
    """パソコンではカードを並べ、スマホ（639px以下）では横にスワイプする棚になる一覧。"""
    more = ('<li class="card card-more sm-only"><a href="%s">%s<span>（%d件）</span></a></li>' % (e(more_href), e(more_label), more_count)) if more_href else ""
    return ('<div class="sm-shelf-block"><ul class="cards sm-shelf%s" tabindex="0" aria-label="%s">%s%s</ul>'
            '<div class="shelf-foot sm-only" aria-hidden="true"><span class="shelf-dots">%s</span></div></div>'
            % (" " + extra_cls if extra_cls else "", e(label), items_html, more, "".join("<i></i>" for _ in range(n))))


NAV = [("/search/", "探す"), ("/tenki/", "転機から"), ("/report/", "観測レポート"), ("/check/", "セルフチェック"), ("/saved/", "あとで見る")]


def nav_links(current=None):
    out = []
    for href, label in NAV:
        extra = '<span class="saved-count" id="saved-count"></span>' if href == "/saved/" else ""
        cur = ' aria-current="page"' if href == current else ""
        out.append('      <a href="%s"%s>%s%s</a>' % (href, cur, e(label), extra))
    return "\n".join(out)


_CRUMBS = []  # 直前に作ったパンくず。page() が構造化データ（BreadcrumbList）に使う


def breadcrumb(parts):
    _CRUMBS[:] = parts
    links = ['<a href="/">トップ</a>']
    for label, href in parts:
        links.append('<a href="%s">%s</a>' % (e(href), e(label)) if href else '<span>%s</span>' % e(label))
    return '<nav class="crumbs" aria-label="現在地">%s</nav>' % ' <span aria-hidden="true">›</span> '.join(links)


def og_image(name):
    """assets/og/ に専用の共有画像があればそれを、なければサイト共通の画像を使う。"""
    if name and os.path.exists(os.path.join(ROOT, "assets", "og", name + ".png")):
        return "/assets/og/%s.png" % name
    return "/assets/ogp.png"


def jsonld_tag(data):
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return '<script type="application/ld+json">%s</script>\n' % text


HEAD_SCRIPT = ('<script>document.documentElement.classList.add("js");'
               'try{if(localStorage.getItem("theme")==="dark")document.documentElement.setAttribute("data-theme","dark")}catch(e){}</script>\n')


def site_header(current=None):
    """全ページ共通のヘッダー（セルフチェックにも同じものを差し込む）。"""
    return """<a class="skip-link" href="#main">本文へ移動</a>
<header class="site-header">
  <div class="wrap header-inner">
    <a class="logo" href="/"><img class="logo-mark" src="/assets/logo.svg" alt="" width="24" height="24">{site}</a>
    <nav class="global-nav" id="global-nav" aria-label="サイト内">
{nav}
    </nav>
    <a class="header-saved-btn" href="/saved/" aria-label="あとで見る"><svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true"><path d="M6 3h12v18l-6-4.5L6 21z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg><span class="header-saved-count" id="saved-count-h" hidden></span></a>
    <a class="header-search-btn" id="header-search-btn" href="/search/" aria-label="キーワードで探す" aria-expanded="false" aria-controls="header-search"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M15.5 15.5 21 21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></a>
    <button type="button" class="menu-btn" id="menu-btn" aria-label="メニュー" aria-expanded="false" aria-controls="global-nav"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button>
  </div>
  <form class="header-search wrap" id="header-search" action="/search/" method="get" role="search" hidden>
    <label for="header-q" class="visually-hidden">キーワード</label>
    <input id="header-q" type="search" name="q" placeholder="キーワードで探す（例：フリーランス、確定申告）">
    <button type="submit">探す</button>
  </form>
</header>""".format(site=e(CONF["site_name"]), nav=nav_links(current))


def site_footer(ctx):
    """全ページ共通のフッターと、サイト全体の動き（site.js）。"""
    return """<footer class="site-footer">
  <div class="wrap">
    <div class="community">
      <p>この観測所は、黒田悠介が運営する「あしたの転機プロジェクト」の一部です。転機について考える記事はnoteマガジンで発信、転機を迎えている人同士の交流はFacebookグループで開催しています。</p>
      <p class="community-links">
        <a href="{note}" rel="noopener" target="_blank">noteマガジン「あしたの転機」</a>
        <a href="{fb}" rel="noopener" target="_blank">Facebookグループ「あしたの転機」</a>
      </p>
    </div>
    <div class="footer-bottom">
      <p class="footer-meta"><a href="/about/">観測所について</a>・<a href="/guide/">支援者の方へ</a>・<a href="/report/">観測レポート</a>・<a href="{contact}" rel="noopener" target="_blank">観測所へのご連絡</a>・最終更新 {updated}</p>
      <button type="button" class="theme-toggle" id="theme-toggle" aria-pressed="false">ダーク表示</button>
    </div>
  </div>
</footer>
<script src="/assets/site.js?v={ver}"></script>""".format(note=e(CONF["note_url"]), fb=e(CONF["facebook_url"]), contact=e(CONF["contact_form_url"]),
                         updated=fmt_date(ctx["today"]), ver=ctx["version"]) + analytics_tag(ctx)


def analytics_tag(ctx):
    """アクセス解析（GoatCounter）。Cookieを使わず、見たページと来た元だけを数える。サイト名が空なら何も入れない。"""
    code = CONF.get("goatcounter_code", "")
    if not code:
        return ""
    return ('\n<script data-goatcounter="https://%s.goatcounter.com/count" async src="/assets/count.js?v=%s"></script>'
            % (e(code), ctx["version"]))


def page(path, title, description, body, *, full_title=None, noindex=False, ctx, image=None, jsonld=None, lastmod=None):
    """1ページ分のHTMLを書き出す。path はサイト内のパス（例: /tenki/dokuritsu/）。"""
    site = CONF["site_name"]
    doc_title = full_title or ("%s｜%s" % (title, site))
    url = BASE + path
    robots = '<meta name="robots" content="noindex">\n' if noindex else ""
    structured = list(jsonld or [])
    if _CRUMBS:
        trail = [("トップ", "/")] + [(label, href or path) for label, href in _CRUMBS]
        structured.append({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": label, "item": BASE + href}
            for i, (label, href) in enumerate(trail)]})
        _CRUMBS[:] = []
    ld = "".join(jsonld_tag(d) for d in structured)
    gsv = CONF.get("google_site_verification", "")
    if gsv:
        robots += '<meta name="google-site-verification" content="%s">\n' % e(gsv)
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
<meta property="og:image" content="{base}{image}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{og_title}">
<meta property="og:locale" content="ja_JP">
<meta name="twitter:card" content="summary_large_image">
<link rel="alternate" type="application/rss+xml" title="{site} 観測レポート" href="/feed.xml">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/assets/favicon-32.png" type="image/png" sizes="32x32">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
{head_script}<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@700;900&display=swap">
<link rel="stylesheet" href="/assets/style.css?v={ver}">
{ld}</head>
<body>
{header}
<main class="wrap" id="main" tabindex="-1">
{body}
</main>
{footer}
</body>
</html>
""".format(doc_title=e(doc_title), desc=e(description), robots=robots, url=e(url),
           og_type="website" if path == "/" else "article", site=e(site),
           og_title=e(full_title or title), base=e(BASE), header=site_header(next((h for h, _ in NAV if path.startswith(h)), None)), footer=site_footer(ctx), head_script=HEAD_SCRIPT, image=e(image or "/assets/ogp.png"), ld=ld, ver=ctx["version"], body=body,
           note=e(CONF["note_url"]), fb=e(CONF["facebook_url"]), contact=e(CONF["contact_form_url"]),
           updated=fmt_date(ctx["today"]))
    write(path, html_text)
    if not noindex:
        ctx["sitemap"].append((url, lastmod or ctx["today"]))  # サイトマップの更新日（紹介ページは最終観測日、ほかは作った日）


def write(path, text):
    target = os.path.join(OUT, path.lstrip("/"))
    if path.endswith("/"):
        target = os.path.join(target, "index.html")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(text)


def more_link(href, label):
    return '<p class="more"><a href="%s">%s</a></p>' % (e(href), e(label))


def emoji(char):
    """見出しやボタンの頭に付ける絵文字。読み上げでは読まないようにする。"""
    return '<span class="emoji" aria-hidden="true">%s</span>' % e(char) if char else ""


def kind_emoji(kind):
    return emoji(KIND_BY_NAME.get(kind, {}).get("emoji", ""))


def image_info(item):
    """掲載先の画像があれば (URLの末尾の版, 収め方, 幅, 高さ) を返す。横長は枠いっぱいに切り抜き（wide）、
    正方形や縦長（本の表紙など）は枠の中に収める（fit）。"""
    rec = IMAGES.get(item["id"])
    if not rec:
        return None
    w, h = rec["w"], rec["h"]
    # URLの末尾の版は画像の中身から作る（差し替えた日にすぐ新しい画像が出るように）
    if "ver" not in rec:
        with open(os.path.join(ROOT, "images", "items", item["id"] + ".webp"), "rb") as f:
            rec["ver"] = hashlib.md5(f.read()).hexdigest()[:8]
    return rec["ver"], ("wide" if w / h >= 1.6 else "fit"), w, h


def item_media(item, cls, small):
    """カードの上の画像（small=True）か、紹介ページの大きな画像。画像がなければタイプの絵文字を同じ枠に出す。"""
    info = image_info(item)
    if not info:
        return '<div class="%s media-none" aria-hidden="true"><span>%s</span></div>' % (
            cls, e(KIND_BY_NAME.get(item["kind"], {}).get("emoji", "")))
    ver, fit, w, h = info
    if small:
        return ('<div class="%s media-%s" aria-hidden="true"><img src="/images/items/%s-s.webp?v=%s" alt="" loading="lazy" decoding="async"></div>'
                % (cls, fit, e(item["id"]), ver))
    return ('<div class="%s media-%s"><img src="/images/items/%s.webp?v=%s" alt="" width="%d" height="%d" fetchpriority="high"></div>'
            % (cls, fit, e(item["id"]), ver, w, h))


def kind_shelves(items, ctx):
    """トップの「タイプごとに見る」。タイプごとに、おすすめ順で最大8件を横にスワイプできる棚にする（自動では動かない）。"""
    n = CONF.get("shelf_size", 8)
    out = []
    for i, (kind, group) in enumerate(by_kind(items)):
        shown = group[:n]
        shelf_id = "shelf-%d" % i
        url = search_url(kind=kind)
        about = KIND_BY_NAME.get(kind, {}).get("about", "")
        more = ('<li class="card card-more"><a href="%s">%sをすべて見る<span>（%d件）</span></a></li>'
                % (e(url), e(kind), len(group))) if len(group) > len(shown) else ""
        out.append("""<section class="kind-block shelf-block">
  <div class="shelf-head">
    <div class="shelf-title"><h3>%s%s <span class="count">%d件</span></h3>%s</div>
    <div class="shelf-tools">
      <span class="shelf-arrows" hidden><button type="button" class="shelf-arrow" data-dir="-1" aria-controls="%s" aria-label="%sの前へ">←</button><button type="button" class="shelf-arrow" data-dir="1" aria-controls="%s" aria-label="%sの次へ">→</button></span>
      <a class="shelf-all" href="%s">すべて見る</a>
    </div>
  </div>
  <ul class="cards shelf" id="%s" tabindex="0" aria-label="%sの一覧（%d件中%d件を表示）">%s%s</ul>
  <div class="shelf-foot" aria-hidden="true"><span class="shelf-dots">%s</span></div>
</section>""" % (kind_emoji(kind), e(kind), len(group), '<p class="kind-about">%s</p>' % e(about) if about else "",
                 shelf_id, e(kind), shelf_id, e(kind), e(url),
                 shelf_id, e(kind), len(group), len(shown), "".join(card(it, ctx["today"], kind=False) for it in shown), more,
                 "".join("<i></i>" for _ in shown)))
    return "\n".join(out)


def kind_sections(items, params, ctx, heading_level=2):
    """種類ごとに上位数件を並べ、残りは一覧ページの該当条件へつなぐ。
    転機のページでは、その転機ならではの掲載を先に、「どの転機にも」の共通の掲載を後に並べる
    （共通の掲載は全体の4割あり、おすすめ順のままだと上位を占めてしまうため）。"""
    n = CONF["top_per_kind"]
    tenki = params.get("tenki", "")
    if tenki and tenki not in (COMMON, OTHER):
        items = sorted(items, key=lambda it: (COMMON in it["tenki"] and tenki not in it["tenki"], it["rank"]))
    out = []
    for kind, group in by_kind(items):
        h = "h%d" % heading_level
        sec = ['<section class="kind-block sm-box" data-kind="%s"><%s>%s%s <span class="count">%d件</span></%s>' % (e(kind), h, kind_emoji(kind), e(kind), len(group), h)]
        about = KIND_BY_NAME.get(kind, {}).get("about", "")
        if about:
            sec.append('<p class="kind-about">%s</p>' % e(about))
        # パソコンは上位 n 件、スマホは棚に shelf_size 件まで（残りは「すべて見る」カード）
        shown = group[:max(n, CONF.get("shelf_size", 8))]
        rest = len(group) > len(shown)
        sec.append(sm_shelf("".join(card(it, ctx["today"], kind=False) for it in shown), len(shown), "%sの一覧" % kind,
                            search_url(kind=kind, **params) if rest else "", "%sをすべて見る" % kind, len(group), extra_cls="lg-top%d" % n))
        if len(group) > n:
            sec.append(more_link(search_url(kind=kind, **params), "%sをもっと見る" % kind))
        sec.append("</section>")
        out.append("".join(sec))
    return "\n".join(out)


# ---------------------------------------------------------------- ページ

def build_home(listed, ctx):
    new_items = sorted(ctx["new_items"], key=lambda it: (it["added"], -it["rank"]), reverse=True)
    # 転機の入口：「転機から探す」のページと同じ絵文字を付け、件数は出さない（共通の掲載を含むと実態より大きく見えるため）。
    # 共通・その他は「どの転機にも役立つもの」1つにまとめる
    tenki_links = "".join(
        '<li><a href="%s">%s%s</a></li>' % (tenki_url(t), emoji(t.get("emoji", "")), e(t["name"]))
        for t in TENKI if t["past"] and ctx["tenki_count"][t["name"]])
    common_t = next((t for t in TENKI if t["name"] == COMMON), None)
    if common_t and ctx["tenki_count"][COMMON]:
        tenki_links += '<li><a href="%s">どの転機にも役立つもの</a></li>' % tenki_url(common_t)
    stage_links = "".join(
        '<li><a href="%s"><strong>%s</strong><span>%s</span></a></li>' % (e(search_url(stage=s["name"])), e(s["name"]), e(s["about"]))
        for s in STAGES)
    kind_links = "".join(
        '<li><a href="%s">%s%s</a></li>' % (e(search_url(kind=k)), kind_emoji(k), e(k))
        for k, g in by_kind(listed))
    if new_items:
        # 6件だけ見せ、続きは観測レポートへ（日付ごと・転機ごとに見られるため）。スマホでは横にスワイプする棚にする
        shown = new_items[:6]
        rest = len(new_items) > len(shown)
        news = sm_shelf("".join(card(it, ctx["today"], date=True) for it in shown), len(shown), "今週の新着",
                        "/report/" if rest else "", "観測レポートで今週の新着をすべて見る", len(new_items))
    else:
        news = '<p class="empty">この1週間に追加されたものはありません。</p>'
    body = """
<section class="hero">
  <h1>{site}</h1>
  <p class="lead">{lead}</p>
  <p class="check-link"><a href="/check/">転機の段階をセルフチェックする</a></p>
  <form class="search-box" action="/search/" method="get" role="search">
    <label for="home-q" class="visually-hidden">キーワード</label>
    <input id="home-q" type="search" name="q" placeholder="キーワードで探す（例：フリーランス、確定申告）">
    <button type="submit">探す</button>
  </form>
  <div class="start-help home-words">
    <p class="start-label">よく探される言葉</p>
    <div class="start-words">{popular}</div>
  </div>
</section>

<section class="entrances">
  <div class="entrance">
    <h2>{e_tenki}転機から探す</h2>
    <ul class="chips">{tenki_links}</ul>
  </div>
  <div class="entrance">
    <h2>{e_stage}今の段階から探す</h2>
    <ul class="stages">{stage_links}</ul>
  </div>
  <div class="entrance">
    <h2>{e_kind}タイプから探す</h2>
    <ul class="chips">{kind_links}</ul>
  </div>
</section>

<section class="section">
  <h2 class="section-title">今週の新着</h2>
  {news}
  <p class="more"><a href="/report/">{news_more}</a></p>
</section>

<section class="section">
  <h2 class="section-title">タイプごとに見る</h2>
  <p class="note">タイプごとに、おすすめ順で上位のものを紹介しています。並び順の考え方は<a href="/about/#order">観測所について</a>に書いています。</p>
  {kinds}
</section>
""".format(e_tenki=emoji(CONF.get("entrance_emoji", {}).get("転機")), e_stage=emoji(CONF.get("entrance_emoji", {}).get("段階")),
           e_kind=emoji(CONF.get("entrance_emoji", {}).get("タイプ")), site=e(CONF["site_name"]), lead=e(CONF["lead"]), tenki_links=tenki_links,
           stage_links=stage_links, kind_links=kind_links, news=news,
           news_more=("観測レポートで今週の新着をすべて見る（%d件）" % len(new_items)) if len(new_items) > 6 else "観測レポートを見る",
           kinds=kind_shelves(listed, ctx),
           popular="".join('<a class="start-word" href="/search/?q=%s">%s</a>' % (e(quote(w)), e(w)) for w in popular_words(listed, ctx)))
    website = {"@context": "https://schema.org", "@type": "WebSite", "name": CONF["site_name"], "url": BASE + "/",
               "description": CONF["description"], "inLanguage": "ja",
               "potentialAction": {"@type": "SearchAction", "target": BASE + "/search/?q={search_term_string}",
                                   "query-input": "required name=search_term_string"}}
    page("/", CONF["site_name"], CONF["description"], body, jsonld=[website],
         full_title="%s｜転機の種類と時期から探す、キャリアの転機に役立つサービス" % CONF["site_name"], ctx=ctx)


def intro_html(lead, note):
    """ページ冒頭の説明は1段落だけ。くわしい解説（config/tenki_notes.json）があればそれを、なければ短い説明を出す。"""
    if note:
        return '  <p class="page-note">%s</p>' % e(note)
    return '  <p class="lead">%s</p>' % e(lead)


def tenki_heading(t):
    if t["name"] == COMMON:
        return "どの転機にも役立つサービスと情報"
    if t["name"] == OTHER:
        return "そのほかの転機に役立つサービスと情報"
    return "%sに役立つサービスと情報" % t["name"]


def combo_title(t, s):
    return s["title"].format(name=t["name"], past=t["past"])


def combo_lead(t, s):
    return s["lead"].format(name=t["name"], past=t["past"])


CHECK_TEXT = load_json("check.json")  # セルフチェックと同じ「この時期によくあること」「次の一歩」を転機のページにも出す


def own_and_common(items, t):
    """その転機ならではの掲載と、どの転機にも役立つ共通の掲載に分ける。"""
    own = [it for it in items if t["name"] in it["tenki"]]
    common = [it for it in items if t["name"] not in it["tenki"]]
    return own, common


def stage_band(t, own, combo_names):
    """段階の帯：段階名・ひとこと・その転機ならではの件数。転機×段階のページがない段階や、0件の段階は押せない形で薄く出す。"""
    out = []
    for s in STAGES:
        n = sum(1 for it in own if s["name"] in it["stages"])
        inner = '<b>%s</b><span>%s</span><em>%d件</em>' % (e(s["name"]), e(s.get("short", "")), n)
        if n and s["name"] in combo_names:
            out.append('<li><a href="/tenki/%s/%s/" aria-label="%s（%d件）">%s</a></li>' % (t["slug"], s["slug"], e(combo_title(t, s)), n, inner))
        else:
            out.append('<li><span class="off">%s</span></li>' % inner)
    return '<ul class="stage-band" aria-label="%sの段階">%s</ul>' % (e(t["name"]), "".join(out))


def kind_tabs(items):
    """タイプの切り替えボタン（JavaScript が使えるときだけ出る）。タイプが3つ以上あるときだけ置く。"""
    kinds = [k for k, g in by_kind(items)]
    if len(kinds) < 3:
        return ""
    return ('<div class="kind-tabs" role="group" aria-label="タイプで絞る"><button type="button" aria-pressed="true" data-kind="">すべて</button>%s</div>'
            % "".join('<button type="button" aria-pressed="false" data-kind="%s">%s</button>' % (e(k), e(k)) for k in kinds))


def own_section(t, own, params, ctx, heading, level):
    """その転機ならではの掲載：タイプの切り替えボタンと、タイプごとの欄。"""
    h = "h%d" % level
    return ('<section class="section own-section"><%s class="section-title">%s</%s>%s<div class="kind-area">%s</div></section>'
            % (h, e(heading), h, kind_tabs(own), kind_sections(own, params, ctx, heading_level=level + 1)))


def common_section(common, ctx, more_params, level):
    """どの転機にも役立つ共通の掲載は、おすすめ順の上位6件だけを1つの棚にまとめ、残りは一覧へ。"""
    if not common:
        return ""
    h = "h%d" % level
    shown = sorted(common, key=lambda it: it["rank"])[:6]
    return ('<section class="section common-section"><%s class="section-title">どの転機にも役立つもの</%s>'
            '<p class="note">どの転機を迎えた人にも役立つサービスと情報です。</p>%s%s</section>'
            % (h, h, sm_shelf("".join(card(it, ctx["today"]) for it in shown), len(shown), "どの転機にも役立つもの"),
               more_link(search_url(**more_params), "どの転機にも役立つものをすべて見る（%d件）" % len(common))))


def tenki_flow(t, own, combo_names):
    """転機の流れ：準備→遭遇→順応→安定と、段階ごとの「この時期によくあること」（セルフチェックと同じ文章）。"""
    texts = CHECK_TEXT["combos"].get(t["name"], {})
    cells = []
    for i, s in enumerate(STAGES):
        common = (texts.get(s["name"]) or {}).get("common") or []
        n = sum(1 for it in own if s["name"] in it["stages"])
        link = ('<a href="/tenki/%s/%s/">%sの段階で役立つもの</a>' % (t["slug"], s["slug"], e(s["name"]))
                if n and s["name"] in combo_names else "")
        cells.append('<li><p class="flow-head"><span class="flow-no">%d</span><b>%s</b><span class="flow-short">%s</span></p>%s%s</li>'
                     % (i + 1, e(s["name"]), e(s.get("short", "")), "".join('<p class="flow-text">%s</p>' % e(c) for c in common[:1]), link))
    return ('<section class="section tenki-flow"><h2 class="section-title">%sの流れ</h2><ol class="flow">%s</ol></section>'
            % (e(t["name"]), "".join(cells)))


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
        combo_names = {s["name"] for s, sub in combos}
        own, common = own_and_common(items, t)
        heading = tenki_heading(t)
        if t["past"]:
            main = (tenki_flow(t, own, combo_names)
                    + own_section(t, own, {"tenki": t["name"]}, ctx, "%sならではのサービスと情報" % t["name"], 2)
                    + common_section(common, ctx, {"tenki": COMMON}, 2))
        else:
            main = '<section class="section">%s%s%s</section>' % (kind_tabs(items), '<div class="kind-area">%s</div>' % kind_sections(items, {"tenki": t["name"]}, ctx, heading_level=2),
                                                                  more_link(search_url(tenki=t["name"]), "%sの掲載情報をすべて見る" % t["name"]))
        body = """
{crumbs}
<header class="page-head">
  <h1>{heading}</h1>
{intro}
</header>
{main}
""".format(crumbs=breadcrumb([("転機から探す", "/tenki/"), (t["name"], None)]), heading=e(heading),
           intro=intro_html(t["about"], NOTES.get("tenki", {}).get(t["name"], "")), main=main)
        page(tenki_url(t), heading, t["about"], body, ctx=ctx, image=og_image(t["slug"]),
             jsonld=[collection_ld(heading, t["about"], tenki_url(t), items)])
        index_rows.append((t, items, own, combo_names))

    cards, extra = [], []
    for t, items, own, combo_names in index_rows:
        if not t["past"]:
            extra.append('<li><a href="%s">%s</a></li>' % (tenki_url(t), e(tenki_heading(t).replace("サービスと情報", "もの"))))
            continue
        cards.append('<li class="tenki-card"><a class="tenki-name" href="%s">%s%s</a><p>%s</p>%s</li>'
                     % (tenki_url(t), emoji(t.get("emoji", "")), e(t["name"]), e(t["about"]), stage_band(t, own, combo_names)))
    body = """
{crumbs}
<header class="page-head">
  <h1>転機から探す</h1>
  <p class="lead">転職、独立、起業など、迎えている転機を選んでください。段階を押すと、その時期に役立つものに絞って見られます。</p>
</header>
<ul class="tenki-cards">{cards}</ul>
<ul class="chips tenki-extra">{extra}</ul>
<section class="lost-box">
  <h2>どの転機か、まだはっきりしない人へ</h2>
  <p>何かを変えたいけれど、どの転機かはまだ決まっていない。そんなときは、いまの段階を確かめるところから始めてみてください。</p>
  <p class="lost-link"><a href="/check/">セルフチェックで、いまの段階を確かめる</a></p>
</section>
""".format(crumbs=breadcrumb([("転機から探す", None)]), cards="".join(cards), extra="".join(extra))
    page("/tenki/", "転機から探す", "転職、独立、起業、副業、退職・休職、定年、学び直し。迎えている転機から、役立つサービスと情報を探せます。", body, ctx=ctx)


def collection_ld(name, description, path, items):
    return {"@context": "https://schema.org", "@type": "CollectionPage", "name": name, "description": description,
            "url": BASE + path, "inLanguage": "ja",
            "mainEntity": {"@type": "ItemList", "numberOfItems": len(items), "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "url": "%s/item/%s/" % (BASE, it["id"]), "name": it["title"]}
                for i, it in enumerate(items[:50])]}}


def combo_guide(t, s):
    """転機×段階のページの「この時期によくあること」と「次の一歩」（セルフチェックの結果と同じ文章）。"""
    text = CHECK_TEXT["combos"].get(t["name"], {}).get(s["name"])
    if not text:
        return ""
    return """<section class="combo-guide">
  <div><h2>この時期によくあること</h2><ul>%s</ul></div>
  <div><h2>次の一歩</h2><ol>%s</ol></div>
  <p class="combo-check"><a href="/check/">自分の段階をセルフチェックで確かめる</a></p>
</section>""" % ("".join("<li>%s</li>" % e(x) for x in text["common"]), "".join("<li>%s</li>" % e(x) for x in text["steps"]))


def build_combo(t, s, items, ctx):
    title = combo_title(t, s)
    own, common = own_and_common(items, t)
    body = """
{crumbs}
<header class="page-head">
  <h1>{title}</h1>
{intro}
</header>
{guide}
{own}
{common}
""".format(crumbs=breadcrumb([("転機から探す", "/tenki/"), (t["name"], tenki_url(t)), (s["name"], None)]),
           title=e(title),
           intro=intro_html(combo_lead(t, s), NOTES.get("combos", {}).get(t["name"], {}).get(s["name"], "")),
           guide=combo_guide(t, s),
           own=own_section(t, own, {"tenki": t["name"], "stage": s["name"]}, ctx, "%s×%sのサービスと情報" % (t["name"], s["name"]), 2) if own else "",
           common=common_section(common, ctx, {"tenki": COMMON, "stage": s["name"]}, 2))
    path = "/tenki/%s/%s/" % (t["slug"], s["slug"])
    page(path, title, combo_lead(t, s), body, ctx=ctx, image=og_image("%s-%s" % (t["slug"], s["slug"])),
         jsonld=[collection_ld(title, combo_lead(t, s), path, items)])


def similar_items(item, listed, limit=3):
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


def next_stage(item):
    """その掲載情報の段階のうち、いちばん後ろの段階の次。安定の次は、次の転機の準備。"""
    order = [s["name"] for s in STAGES]
    idx = [order.index(st) for st in item["stages"] if st in order]
    if not idx:
        return None
    last = max(idx)
    if last == len(order) - 1:
        return order[0], True
    return order[last + 1], False


def report_link(item):
    url = CONF.get("report_form_url", "")
    if not url:
        return '<p class="report">情報の誤りに気づいたときのお知らせフォームは準備中です。</p>'
    href = url.replace("{id}", quote(item["id"])).replace("{title}", quote(item["title"]))
    return '<p class="report"><a href="%s" rel="noopener" target="_blank">この情報の誤りを知らせる</a></p>' % e(href)


KIND_PHRASE = {"相談": "相談先", "仕事": "仕事サービス", "学習": "学びの場", "内省": "自己分析サービス", "実務": "実務サービス",
               "交流": "コミュニティ", "書籍": "本", "媒体": "メディア", "調査": "調査レポート"}


def item_kind_phrase(item):
    """ページの題名に添える言葉。例：「転職の仕事サービス」「キャリアの転機に役立つ本」"""
    kind = KIND_PHRASE.get(item["kind"], item["kind"])
    tenki = next((t for t in item["tenki"] if t not in (COMMON, OTHER)), "")
    return "%sの%s" % (tenki, kind) if tenki else "キャリアの転機に役立つ%s" % kind


def related_section(panels):
    """紹介ページの下の関連。1つならそのまま、2つなら切り替えボタン（JavaScript が使えないときは両方並べる）。"""
    if not panels:
        return ""
    if len(panels) == 1:
        return '<section class="section related"><h2 class="section-title">%sで役立つもの</h2>%s</section>' % (e(panels[0][0]), panels[0][1])
    tabs = "".join('<button type="button" aria-pressed="%s" data-panel="%d">%s</button>' % ("true" if i == 0 else "false", i, e(name)) for i, (name, _) in enumerate(panels))
    bodies = "".join('<div class="related-panel" data-panel="%d"><h3 class="related-h">%sで役立つもの</h3>%s</div>' % (i, e(name), html) for i, (name, html) in enumerate(panels))
    return ('<section class="section related"><h2 class="section-title">あわせて見たいもの</h2>'
            '<div class="kind-tabs related-tabs" role="group" aria-label="関連の切り替え">%s</div>%s</section>' % (tabs, bodies))


def build_item(item, listed, ctx):
    def links(names, lookup, make):
        out = []
        for n in names:
            out.append('<a href="%s">%s</a>' % (e(make(n)), e(n)) if n in lookup else e(n))
        return "、".join(out) or "―"

    similar = similar_items(item, listed)
    panels = []  # 下の関連：（ボタンの名前, 中身）。2つあるときは切り替えボタンで1つの区切りにまとめる
    if similar:
        panels.append(("同じ転機・段階", sm_shelf("".join(card(it, ctx["today"]) for it in similar), len(similar), "同じ転機・段階で役立つもの")))

    nxt = next_stage(item)
    if item["listed"] and nxt:
        stage, following = nxt
        picks = [o for o in listed if o["id"] != item["id"] and stage in o["stages"]
                 and any(matches_tenki(o, t) for t in item["tenki"])][:3]
        if picks:
            heading = ("次の転機の準備に役立つもの" if following else "次の段階（%s）で役立つもの" % stage)
            tenki_param = next((t for t in item["tenki"] if t not in (COMMON, OTHER)), "")
            panels.append(("次の転機の準備" if following else "次の段階（%s）" % stage,
                           sm_shelf("".join(card(it, ctx["today"]) for it in picks), len(picks), heading)
                           + more_link(search_url(tenki=tenki_param, stage=stage),
                                       "%s×%sで役立つものをすべて見る" % (tenki_param, stage) if tenki_param
                                       else "%sで役立つものをすべて見る" % stage)))
    similar_html = related_section(panels)

    # パンくずは、その掲載のいちばん目の転機のページを通る（どの転機にもの掲載は「どの転機にも」）
    main = next((TENKI_BY_NAME[t] for t in item["tenki"] if t in TENKI_BY_NAME), None)
    crumbs = breadcrumb([("転機から探す", "/tenki/")]
                        + ([("どの転機にも" if main["name"] == COMMON else main["name"], tenki_url(main))] if main else [])
                        + [(item["title"], None)])
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

    # リンクの文言は種類ごと（調査は「レポートを読む」、書籍は「購入ページを見る」など。config/site.json の kinds）
    link_label = KIND_BY_NAME.get(item["kind"], {}).get("link", "公式サイトを見る")
    official_link = ('<a class="button" href="%s" rel="noopener" target="_blank" data-goatcounter-click="official/%s" data-goatcounter-title="%s">%s</a>'
                     % (e(item["url"]), e(item["id"]), e(item["title"]), e(link_label))) if item["url"] else ""
    official = ('<p class="official">%s<button type="button" class="button button-ghost save-wide" data-save="%s" '
                'data-title="%s" aria-pressed="false" hidden>%s<span>あとで見る</span></button>'
                '<button type="button" class="button button-ghost share-btn" data-share-title="%s" hidden>%s<span>共有</span></button></p>'
                % (official_link, e(item["id"]), e(item["title"]), SAVE_ICON, e(item["title"] + "｜" + CONF["site_name"]), SHARE_ICON))
    tenki_links = links(item["tenki"], TENKI_BY_NAME, lambda n: tenki_url(TENKI_BY_NAME[n]))
    stage_links = links(item["stages"], STAGE_BY_NAME, lambda n: search_url(stage=n))
    body = """
{crumbs}
<article class="detail">
  {hero}{credit}
  <h1>{title}</h1>
  <div class="detail-side">
  <div class="memo"><h2 class="visually-hidden">観測メモ</h2><p>{memo}</p></div>
  {official}
  </div>
  <dl class="facts">
    <div><dt>タイプ</dt><dd><a href="{kind_url}">{kind}</a></dd></div>
    <div><dt>転機</dt><dd>{tenki}</dd></div>
    <div><dt>段階</dt><dd>{stages}</dd></div>
    <div><dt>{provider_label}</dt><dd>{provider}</dd></div>
  </dl>
  <div class="helpful" data-id="{id}" data-title="{title}" hidden>
    <p class="helpful-q">この紹介は役に立ちましたか？</p>
    <div class="helpful-btns"><button type="button" class="button button-ghost" data-helpful="yes">👍 役に立った</button><button type="button" class="button button-ghost" data-helpful="no">👎 いまひとつ</button></div>
    <p class="helpful-thanks" hidden>ありがとうございます。観測所の見直しに使います。</p>
  </div>
  {report}
</article>
{similar}
""".format(crumbs=crumbs, kind_url=e(search_url(kind=item["kind"])), kind=e(item["kind"]), title=e(item["title"]),
           memo=e(item["memo"]), id=e(item["id"]),
           hero=item_media(item, "detail-hero", False), credit=image_credit(item), official=official, tenki=tenki_links, stages=stage_links,
           provider=e(item["provider"] or "―"), report=report_link(item),
           provider_label={"調査": "発表元", "書籍": "著者・出版社"}.get(item["kind"], "提供元"),
           similar=similar_html)
    desc = item["memo"][:110] or "%sの紹介ページです。" % item["title"]
    ld_type = {"書籍": "Book", "調査": "Report"}.get(item["kind"], "Service")
    about = {"@type": ld_type, "name": item["title"], "description": item["memo"]}
    if ld_type == "Service":
        about["category"] = item["kind"]
    if item["url"]:
        about["url"] = item["url"]
    if item["provider"]:
        key = {"Book": "author", "Report": "publisher"}.get(ld_type, "provider")
        about[key] = {"@type": "Organization" if ld_type != "Book" else "Person", "name": item["provider"]}
    if ld_type == "Report" and item["published"]:
        about["datePublished"] = "%04d-%02d" % item["published"]
    webpage = {"@context": "https://schema.org", "@type": "WebPage", "name": item["title"], "description": desc,
               "url": "%s/item/%s/" % (BASE, item["id"]), "inLanguage": "ja", "about": about}
    if item["observed"]:
        webpage["dateModified"] = item["observed"].isoformat()
    # 共有画像：tools/make_item_og.py が作った掲載ごとの画像があればそれを、なければ観測所共通の画像
    og = "/images/og/%s.png" % item["id"] if os.path.exists(os.path.join(ROOT, "og-items", item["id"] + ".png")) else None
    info = image_info(item)
    if info:  # 構造化データにも画像（掲載先の画像）を入れる
        about["image"] = "%s/images/items/%s.webp" % (BASE, item["id"])
    page("/item/%s/" % item["id"], item["title"], desc, body, ctx=ctx, jsonld=[webpage], image=og, lastmod=item["observed"],
         full_title="%s（%s）｜%s" % (item["title"], item_kind_phrase(item), CONF["site_name"]))


def popular_words(listed, ctx, k=8):
    """「よく探される言葉」：言い換え表の各グループの代表の言葉と、向いている人の言葉のうち、掲載が3件以上あるもの（タイプの名前と「無料」は除く）。
    毎日の更新で、日付に合わせて k 個を選び直す。"""
    groups = [g for g in load_json("synonyms.json").get("groups", []) if isinstance(g, list) and g]
    # タイプの名前（ボタンで選べる）と、サイトで出していない費用の言葉は外す
    skip = {k["name"] for k in KINDS} | {"無料"}
    pool = [w for w in dict.fromkeys([g[0] for g in groups] + CONF.get("audience", [])) if w not in skip]
    texts = [normalize(" ".join([it["title"], it["memo"], it["provider"], it["kind"], " ".join(it["for"])])) for it in listed]
    pool = [w for w in pool if sum(1 for t in texts if normalize(w) in t) >= 3]
    if len(pool) <= k:
        return pool
    # 日付を種にして選ぶので、同じ日のうちは何度作り直しても同じ言葉になる
    import random
    return random.Random(ctx["today"].toordinal()).sample(pool, k)


def build_search(listed, ctx):
    words = popular_words(listed, ctx)

    def chip_group(name, label, values, labels=None):
        """条件のボタン（ラジオボタンを押しやすい形にしたもの）。件数は search.js が入れる"""
        labels = labels or {}
        opts = [("", "すべて")] + [(v, labels.get(v, v)) for v in values]
        return ('<fieldset class="chip-group"><legend>%s</legend><div class="fchips">%s</div></fieldset>'
                % (e(label), "".join('<label class="fchip"><input type="radio" name="%s" value="%s"%s><span>%s<i></i></span></label>'
                                     % (name, e(v), " checked" if not v else "", e(t)) for v, t in opts)))
    body = """
{crumbs}
<header class="page-head page-head-tight">
  <h1>探す</h1>
</header>
<form id="filters" class="filters" action="/search/" method="get" role="search">
  <div class="search-q">
    <label for="q" class="visually-hidden">キーワード</label>
    <input id="q" type="search" name="q" placeholder="キーワードで探す（例：フリーランス、確定申告）" autocomplete="off" aria-autocomplete="list" aria-controls="suggest">
    <ul id="suggest" class="suggest" role="listbox" aria-label="候補" hidden></ul>
  </div>
  <div id="start-help" class="start-help">
    <p class="start-label">よく探される言葉</p>
    <div class="start-words">{popular}</div>
  </div>
  <div class="search-layout">
    <div class="filter-col">
      <button type="button" id="filter-toggle" class="filter-toggle" aria-expanded="false" aria-controls="filter-panel">絞り込む<span id="filter-count"></span></button>
      <div id="filter-panel" class="filter-panel">
        {tenki}
        {stages}
        {kinds}
        <noscript><button type="submit">この条件で探す</button></noscript>
      </div>
    </div>
    <div class="result-col">
      <div class="result-bar">
        <p id="result-count" aria-live="polite">読み込み中…</p>
        <button type="button" class="bar-filter" id="bar-filter" aria-controls="filter-panel" aria-expanded="false">絞り込む</button>
        <div class="view-switch" role="group" aria-label="表示の切り替え"><button type="button" data-view="card" aria-pressed="true">カード</button><button type="button" data-view="list" aria-pressed="false">一覧</button></div>
        <div class="sort-field"><label for="sort">並び順</label><select id="sort" name="sort"><option value="">おすすめ順</option><option value="new">新着順</option></select><a class="sort-help" href="/about/#order">並び順の考え方</a></div>
      </div>
      <div id="active-chips" class="active-chips" hidden></div>
      <p id="syn-note" class="syn-note" hidden></p>
      <ul id="results" class="cards list-compact"></ul>
      <p class="more-wrap"><button type="button" id="more" class="button" hidden>もっと見る</button></p>
    </div>
  </div>
</form>
<noscript><p class="note">検索にはJavaScriptを使います。使えない場合は<a href="/tenki/">転機から探す</a>をご利用ください。</p></noscript>
<script>window.TENKI_PAGE_SIZE = {page_size}; window.TENKI_THIS_YEAR = {year}; window.TENKI_POPULAR = {popular_json};</script>
<script src="/assets/search.js?v={ver}" defer></script>
""".format(crumbs=breadcrumb([("探す", None)]), kinds=chip_group("kind", "タイプ", kinds_of(listed)),
           tenki=chip_group("tenki", "転機", [t["name"] for t in TENKI], {COMMON: "どの転機にも", OTHER: "そのほか"}),
           stages=chip_group("stage", "段階", [s["name"] for s in STAGES]),
           popular="".join('<a class="start-word" href="?q=%s">%s</a>' % (e(quote(w)), e(w)) for w in words),
           popular_json=json.dumps(words, ensure_ascii=False),
           page_size=int(CONF["list_page_size"]), year=ctx["today"].year, ver=ctx["version"])
    page("/search/", "探す", "キャリアの転機に役立つサービスと情報を、転機・段階・タイプで絞り込み、キーワードで検索できます。", body, ctx=ctx)


WEEKDAYS = "月火水木金土日"


def report_cards(items, ctx):
    """観測レポートのカード。転機で絞れるように、カードに転機の名前を持たせる（どの転機にもの掲載は「共通」）。"""
    out = []
    for it in items:
        html = card(it, ctx["today"], date=True)
        out.append(html.replace('<li class="card"', '<li class="card" data-tenki="%s"' % e(" ".join(it["tenki"])), 1))
    return '<ul class="cards list-compact">%s</ul>' % "".join(out)


def build_report(listed, ctx):
    weeks = {}
    for it in listed:
        if not it["added"]:
            continue
        start = it["added"] - datetime.timedelta(days=it["added"].weekday())
        weeks.setdefault(start, []).append(it)
    this_week = ctx["today"] - datetime.timedelta(days=ctx["today"].weekday())
    sections = []
    for start in sorted(weeks, reverse=True):
        end = start + datetime.timedelta(days=6)
        group = weeks[start]
        label = {this_week: "今週", this_week - datetime.timedelta(days=7): "先週"}.get(start, "")
        dates = "%d年%d月%d日〜%d月%d日" % (start.year, start.month, start.day, end.month, end.day) if not label else "%d月%d日〜%d月%d日" % (start.month, start.day, end.month, end.day)
        heading = ('<b>%s</b>%s' % (label, e(dates))) if label else e(dates)
        # 週の中を日付ごとに区切る。各日は最初の6件を見せ、残りは「この日の残りを見る」で開く
        days = []
        for d in sorted({it["added"] for it in group}, reverse=True):
            day_items = sorted([it for it in group if it["added"] == d], key=lambda it: it["rank"])
            first, rest = day_items[:6], day_items[6:]
            more = ('<details class="week-more"><summary>この日の残り <span class="rest-n">%d</span>件を見る</summary>%s</details>'
                    % (len(rest), report_cards(rest, ctx))) if rest else ""
            days.append('<section class="report-day"><h3>%d月%d日（%s）<span class="count"><span class="day-n">%d</span>件</span></h3>%s%s</section>'
                        % (d.month, d.day, WEEKDAYS[d.weekday()], len(day_items), report_cards(first, ctx), more))
        sections.append('<section class="week" id="w%s"><h2>%s <span class="count"><span class="week-n">%d</span>件</span></h2>%s</section>'
                        % (start.strftime("%Y%m%d"), heading, len(group), "".join(days)))
    tabs = ('<div class="kind-tabs report-tabs" role="group" aria-label="転機で絞る"><button type="button" aria-pressed="true" data-tenki="">すべて</button>%s</div>'
            % "".join('<button type="button" aria-pressed="false" data-tenki="%s">%s</button>' % (e(t["name"]), e(t["name"])) for t in TENKI if t["past"]))
    body = """
{crumbs}
<header class="page-head">
  <h1>観測レポート</h1>
  <p class="lead">観測所に新しく加わったサービスと情報を、週ごとにまとめています。</p>
</header>
{tabs}
<p class="report-empty" id="report-empty" hidden>この転機の新着は、まだありません。</p>
{sections}
<p class="rss-note"><a href="/feed.xml">新着をRSSで受け取る</a>（ニュースリーダーに登録すると、新しく加わった掲載が届きます）</p>
""".format(crumbs=breadcrumb([("観測レポート", None)]), tabs=tabs if sections else "",
           sections="\n".join(sections) or '<p class="empty">まだ記録がありません。</p>')
    page("/report/", "観測レポート", "あしたの転機観測所に新しく加わったサービスと情報を、週ごとにまとめています。", body, ctx=ctx)


ANALYTICS_ABOUT = """<h2 id="analytics">アクセス解析について</h2>
<p>観測所をよりよくするために、アクセス解析の GoatCounter（goatcounter.com）を使っています。Cookie は使わず、閲覧した人を特定する情報も集めません。</p>
<p>送っているのは、見たページ、どこから来たか（検索エンジンやSNSなど）、ブラウザや画面の大きさといった大まかな情報です。探すページで何も見つからなかったときは、そのとき入力されたキーワードも送ります。言い換え表を見直したり、掲載するものを探したりするのに使います。</p>
<p>紹介ページで「公式サイトを見る」「あとで見る」「共有」と、「この紹介は役に立ちましたか？」のボタンが押されたときは、どの掲載で押されたか（掲載のIDとタイトル）を数えます。役に立った掲載を知り、掲載するものや並び順を見直すのに使います。</p>
<p>転機の段階セルフチェックは、始めた回数、最後まで答えた回数と結果の段階、結果に出たおすすめが押された回数だけを数えます。一つひとつの回答や、4つの資源のバランス、相談メモの中身は送りません。</p>
"""


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
<p>キャリアコンサルタントや人事など、相談に乗る立場の方に向けた使い方は、<a href="/guide/">キャリア支援者の方へ</a>にまとめています。</p>

<h2>掲載の基準</h2>
<p>掲載しているのは、民間の企業や団体、個人が提供しているサービスと情報だけです。国や自治体の制度、公的な窓口は載せていません。</p>
<p>提供が終わったものや掲載を終えたものは、一覧と検索から外します。外部から紹介ページへのリンクが切れないように、紹介ページだけは残し、掲載を終えたことを表示します。</p>

<h2 id="order">並び順の考え方</h2>
<p>特定の人や時期に特化しているか、運営の実績、無料で試せるか、情報の新しさをもとに並べています。一覧を見やすくするため、公式ページの画像を表示できるものを先に並べています。掲載依頼や広告で順番を変えることはありません。</p>

<h2>情報の集め方と点検</h2>
<p>掲載情報は、AIが公開されている情報をもとに集め、内容を確かめてから載せています。載せたあともAIが定期的に点検しています。</p>
<p>料金や内容は変わることがあります。利用する前に、公式サイトで最新の情報を確かめてください。</p>

<h2 id="images">掲載している画像について</h2>
<p>紹介ページと一覧の画像は、各サービスが公式サイトでシェア用に公開している画像や、出版社・書店が公開している書影です。どんなサービス・本かがわかりやすいように、紹介ページへのリンクと一緒に縮小して表示しています。</p>
<p>掲載先の方で、画像を外したい・差し替えたい場合は、<a href="{contact}" rel="noopener" target="_blank">観測所へのご連絡</a>からお知らせください。確認のうえ対応します。</p>

<h2 id="contact">観測所へのご連絡</h2>
<p>掲載情報の誤りのお知らせや、掲載してほしいサービス・情報のご提案は、<a href="{contact}" rel="noopener" target="_blank">観測所へのご連絡</a>のフォームから受け付けています。</p>
<ul>
  <li>ご提案いただいたものも、ほかの掲載情報と同じ基準で確かめてから掲載するかどうかを決めます。掲載をお約束するものではありません。</li>
  <li>ご提案によって並び順が変わることはありません。</li>
  <li>掲載料をいただく掲載や、広告としての掲載は行っていません。</li>
  <li>個別のご返信はしていません。</li>
</ul>

{analytics}
<h2>運営者</h2>
<p>運営は黒田悠介です。キャリア研究家として、これまでに1,000人以上のキャリア相談を受けてきました。著書に『ライフピボット』などがあります。</p>
<p>ほかの活動や発信は、<a href="{operator_url}" rel="noopener" target="_blank">黒田悠介のリンク集（Linktree）</a>にまとめています。</p>

<h2>あしたの転機について</h2>
<p>「あしたの転機」は、キャリアの転機について考え、転機を迎えている人どうしがつながるための場です。この観測所はその一部として運営しています。</p>
<ul>
  <li><a href="{note}" rel="noopener" target="_blank">noteマガジン「あしたの転機」</a>：転機について考える記事を載せています。</li>
  <li><a href="{fb}" rel="noopener" target="_blank">Facebookグループ「あしたの転機」</a>：同じように転機を迎えている人と交流できます。</li>
</ul>
</article>
""".format(crumbs=breadcrumb([("観測所について", None)]), stage_dl=stage_dl,
           note=e(CONF["note_url"]), fb=e(CONF["facebook_url"]), contact=e(CONF["contact_form_url"]),
           analytics=ANALYTICS_ABOUT if CONF.get("goatcounter_code") else "", operator_url=e(CONF.get("operator_url", "")))
    page("/about/", "観測所について", "あしたの転機観測所の目的、掲載の基準、並び順の考え方、情報の集め方と運営者について。", body, ctx=ctx)


def build_saved(ctx):
    body = """
{crumbs}
<header class="page-head">
  <h1>あとで見る</h1>
  <p class="lead">カードや紹介ページの<span class="save-inline">{icon}</span>ボタンで残したものです。</p>
  <p class="note">このブラウザの中だけに保存しています。ほかの端末やブラウザとは共有されず、観測所に送られることもありません。</p>
</header>
<div class="saved-bar">
<p id="saved-status" class="saved-status" aria-live="polite">読み込み中…</p>
<p class="saved-actions"><button type="button" id="saved-import" class="button" hidden>自分の「あとで見る」に入れる</button><button type="button" id="saved-share" class="button button-ghost share-list" hidden>このリストを送る</button></p>
</div>
<p id="saved-share-note" class="note saved-note" aria-live="polite"></p>
<ul id="saved-list" class="cards list-compact"></ul>
<div id="saved-empty" class="saved-empty" hidden>
  <p>まずは次のところから、気になるものを探してみてください。</p>
  <ul class="saved-empty-links">
    <li><a href="/tenki/"><b>転機から探す</b><span>転職・独立・副業など、迎えている転機から</span></a></li>
    <li><a href="/search/"><b>キーワードで探す</b><span>キーワードや段階・タイプで絞り込んで</span></a></li>
    <li><a href="/check/"><b>セルフチェックする</b><span>いまの段階をふりかえって、合いそうなものを見つける</span></a></li>
  </ul>
</div>
<p class="more-wrap"><button type="button" id="saved-clear" class="link-button" hidden>すべて外す</button></p>
<noscript><p class="note">この機能にはJavaScriptを使います。</p></noscript>
""".format(crumbs=breadcrumb([("あとで見る", None)]), icon=SAVE_ICON)
    page("/saved/", "あとで見る", "あとで見るために残したサービスと情報の一覧です。", body, noindex=True, ctx=ctx)


def build_guide(listed, ctx):
    """キャリア支援者（キャリアコンサルタント・人事・コーチなど）向けの使い方。"""
    body = """
{crumbs}
<article class="prose">
<h1>キャリア支援者の方へ</h1>
<p>キャリアコンサルタント、人事、コーチ、学校の先生など、転機を迎えた人を支える方に向けた、観測所の使い方です。相談の場で、相談者に合いそうなサービスや情報を一緒に探したり、あとで見てもらうためにまとめて送ったりできます。</p>

<h2>相談者の転機と時期から絞り込む</h2>
<p>観測所の掲載は、転機の種類（転職・独立・起業・副業・退職や休職・定年・学び直し）と、その転機のどの時期か（準備・遭遇・順応・安定）で整理しています。</p>
<ul>
<li><a href="/tenki/">転機から探す</a>で転機を選ぶと、時期ごとのページに進めます。</li>
<li><a href="/search/">探す</a>では、転機・段階・タイプ（相談・仕事・学習など）を組み合わせて絞り込めます。絞り込んだ状態のページのURLを、そのまま相談者に送ることもできます。</li>
</ul>

<h2>候補をリストにして送る</h2>
<p>気になる掲載のカードや紹介ページで「あとで見る」を押すと、<a href="/saved/">あとで見る</a>にたまります。たまったら「このリストを送る」で、リストのURLを相談者に送れます。</p>
<p>受け取った人がURLを開くと、同じリストが表示され、「自分の『あとで見る』に入れる」で取り込めます。リストはそれぞれのブラウザの中にだけ保存され、観測所に送られることはありません。</p>

<h2>いまの段階を一緒にふりかえる</h2>
<p><a href="/check/">転機の段階セルフチェック</a>は、16の質問で、転機のどの段階にいるかと、転機を乗り切る4つの資源（状況・自分・支え・戦略）のバランスをふりかえるものです。結果には、転機と段階に合わせた次の一歩と、観測所からのおすすめが出ます。最後の「相談メモ」は、コピーや印刷をして相談の場で使えます。相談の入口や、面談の前の宿題として使えます。回答や結果は送信されません。</p>

<h2>紹介するときに知っておいてほしいこと</h2>
<ul>
<li>掲載しているのは、民間の企業・団体・個人が提供しているサービスと情報です。国や自治体の制度、公的な窓口は載せていません。</li>
<li>掲載料をいただく掲載や、広告としての掲載はしていません。並び順の考え方は<a href="/about/#order">観測所について</a>に書いています。</li>
<li>掲載情報はAIが集めて確かめ、定期的に点検していますが、料金や内容は変わることがあります。利用する前に、公式サイトで最新の情報を確かめるよう伝えてください。</li>
<li>掲載情報の誤りに気づいたときや、紹介したいサービスがあるときは、<a href="{contact}" rel="noopener" target="_blank">観測所へのご連絡</a>からお知らせください。</li>
</ul>
</article>
""".format(crumbs=breadcrumb([("支援者の方へ", None)]), contact=e(CONF["contact_form_url"]))
    page("/guide/", "キャリア支援者の方へ", "キャリアコンサルタント・人事・コーチなど、転機を迎えた人を支える方に向けた、あしたの転機観測所の使い方です。", body, ctx=ctx)


def build_404(ctx):
    body = """
<header class="page-head">
  <h1>ページが見つかりません</h1>
  <p class="lead">お探しのページは移動したか、削除された可能性があります。</p>
</header>
<form class="search-box" action="/search/" method="get" role="search">
  <label for="nf-q" class="visually-hidden">キーワード</label>
  <input id="nf-q" type="search" name="q" placeholder="キーワードで探す（例：フリーランス、確定申告）">
  <button type="submit">探す</button>
</form>
<section class="section">
  <h2 class="section-title">転機から探す</h2>
  <ul class="chips">{tenki}</ul>
</section>
<section class="section">
  <h2 class="section-title">タイプから探す</h2>
  <ul class="chips">{kinds}</ul>
</section>
<p class="more"><a href="/">トップへ戻る</a></p>
""".format(tenki="".join('<li><a href="%s">%s</a></li>' % (e(tenki_url(t)), e(t["name"])) for t in TENKI),
           kinds="".join('<li><a href="%s">%s%s</a></li>' % (e(search_url(kind=k["name"])), kind_emoji(k["name"]), e(k["name"])) for k in KINDS))
    page("/404.html", "ページが見つかりません", CONF["description"], body, noindex=True, ctx=ctx)


# ---------------------------------------------------------------- 出力

def normalize(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    # ひらがなをカタカナにそろえる（「ふりーらんす」でも見つかるように）
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in s)


def image_credit(item):
    """紹介ページの画像の下の出典。本は出版社・書店の書影、それ以外は公式サイトの画像。画像がなければ何も出さない。"""
    if not image_info(item):
        return ""
    text = "書影：出版社・書店の公開画像より" if item["kind"] == "書籍" else "画像：公式サイトより"
    return '<p class="hero-credit">%s</p>' % text


def image_ref(item):
    """JSで描くカード（探す・あとで見る・セルフチェック）用。カードの上の画像のURLと収め方。画像がなければタイプの絵文字。"""
    info = image_info(item)
    if not info:
        return {"emoji": KIND_BY_NAME.get(item["kind"], {}).get("emoji", "")}
    return {"src": "/images/items/%s-s.webp?v=%s" % (item["id"], info[0]), "fit": info[1]}


def reading(text):
    """漢字の読み（カタカナ）。ひらがなだけでも探せるように検索用のデータに入れる。
    pykakasi が入っているとき（毎朝の更新では入れる）だけ作り、なければ空文字（ひらがな検索はできないが、ほかは変わらない）。"""
    global _KAKASI
    if _KAKASI is None:
        try:
            import pykakasi
            _KAKASI = pykakasi.kakasi()
        except ImportError:
            _KAKASI = False
    if not _KAKASI or not text:
        return ""
    return normalize("".join(part["kana"] for part in _KAKASI.convert(text)))


_KAKASI = None


def build_search_json(listed, ctx):
    synonyms = load_json("synonyms.json").get("groups", [])
    data = {
        "items": [{
            "id": it["id"], "title": it["title"], "line": it["line"], "kind": it["kind"],
            "tenki": it["tenki"], "stages": it["stages"],
            "added": it["added"].isoformat() if it["added"] else "",
            "rank": it["rank"], "new": it["id"] in ctx["new_ids"], "img": image_ref(it),
            "text": normalize(" ".join([it["title"], it["memo"], it["provider"], it["kind"], " ".join(it["for"]),
                                        " ".join(it["tenki"]), " ".join(it["stages"])]))
                    + " " + reading(" ".join([it["title"], it["memo"], it["provider"], it["kind"], " ".join(it["tenki"])])),
        } for it in listed],
        # 言い換え表。読みは「どのグループに当たるか」の判定にだけ使う（「ふくぎょう」でも 副業・兼業 などが一緒に見つかるように）。
        # 読みで本文を探すと、同じ読みの別の言葉（障害と生涯）まで見つかるため、本文を探すのは words だけ
        "synonyms": [{"words": sorted({normalize(w) for w in g if w.strip()}),
                      "readings": sorted({reading(w) for w in g if w.strip()} - {""})} for g in synonyms if isinstance(g, list)],
    }
    # 入力中の候補（言い換え表の言葉のうち、掲載に1件以上あるもの）。読みを添えて、ひらがなでも候補に出す
    texts = [i["text"] for i in data["items"]]
    words = list(dict.fromkeys(w.strip() for g in synonyms if isinstance(g, list) for w in g if w.strip()))
    data["suggest"] = [{"w": w, "r": reading(w)} for w in words if any(normalize(w) in t for t in texts)]
    write("/search.json", json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def build_check(listed, ctx):
    """転機の段階セルフチェック（check/index.html）と、結果画面のおすすめに使う picks.json を書き出す。"""
    with open(os.path.join(ROOT, "check", "index.html"), encoding="utf-8") as f:
        text = f.read()
    # ほかのページとまったく同じヘッダー・フッターを差し込む（観測所の style.css と site.js も読み込む）
    for mark in ("<!--SITE_HEAD-->", "<!--SITE_HEADER-->", "<!--SITE_FOOTER-->"):
        assert mark in text, mark
    head = (HEAD_SCRIPT + '<link rel="alternate" type="application/rss+xml" title="%s 観測レポート" href="/feed.xml">\n'
            '<link rel="stylesheet" href="/assets/style.css?v=%s">' % (e(CONF["site_name"]), ctx["version"]))
    # 質問と結果の文章（config/check.json）と、動きの JavaScript（check/check.js）をページに埋め込む
    with open(os.path.join(ROOT, "check", "check.js"), encoding="utf-8") as f:
        js = f.read()
    data = json.dumps(load_json("check.json"), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    text = (text.replace("<!--SITE_HEAD-->", head)
                .replace("<!--SITE_HEADER-->", site_header("/check/"))
                .replace("<!--SITE_FOOTER-->", site_footer(ctx))
                .replace("/*CHECK_DATA*/null", data)
                .replace("/*CHECK_JS*/", js))
    write("/check/", text)
    ctx["sitemap"].append((BASE + "/check/", ctx["today"]))
    data = {"items": [{
        "id": it["id"], "title": it["title"], "type": it["kind"], "tenki": it["tenki"], "stage": it["stages"],
        "memo": it["memo"], "url": it["url"], "rank": it["rank"],
        "page": "/item/%s/" % it["id"], "img": image_ref(it),
    } for it in listed]}
    write("/check/picks.json", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    # 結果ごとのシェア用ページ（/check/sogu/ など）。SNSには段階ごとの画像を見せ、開いた人はセルフチェックへ移る
    for st in STAGES:
        title = "いまは「%s」の段階でした｜転機の段階セルフチェック" % st["name"]
        desc = "16の質問で、キャリアの転機のどの段階（準備・遭遇・順応・安定）にいるかと、転機を乗り切る4つの資源のバランスをふりかえるセルフチェック。"
        write("/check/%s/" % st["slug"], """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta name="robots" content="noindex">
<link rel="canonical" href="{base}/check/">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{site}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{base}/check/{slug}/">
<meta property="og:image" content="{base}/assets/og/check-{slug}.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:locale" content="ja_JP">
<meta name="twitter:card" content="summary_large_image">
<meta http-equiv="refresh" content="0; url=/check/">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
</head>
<body>
<p><a href="/check/">転機の段階セルフチェックへ</a></p>
<script>location.replace("/check/");</script>
</body>
</html>
""".format(title=e(title), desc=e(desc), base=e(BASE), site=e(CONF["site_name"]), slug=st["slug"]))


def feed_image(item):
    """RSSの各記事に、カードと同じ画像を付ける（RSSリーダーで画像が出る）。"""
    info = image_info(item)
    if not info:
        return ""
    path = os.path.join(ROOT, "images", "items", item["id"] + "-s.webp")
    return '<enclosure url="%s/images/items/%s-s.webp?v=%s" type="image/webp" length="%d"/>' % (BASE, item["id"], info[0], os.path.getsize(path))


def build_feed(listed, ctx):
    """観測レポートのRSS。追加日の新しい順に最大50件。"""
    from email.utils import format_datetime
    items = sorted([it for it in listed if it["added"]], key=lambda it: (it["added"], -it["rank"]), reverse=True)[:50]
    def pub(d):
        return format_datetime(datetime.datetime(d.year, d.month, d.day, 5, 0, tzinfo=JST))
    entries = "".join(
        "<item><title>%s</title><link>%s/item/%s/</link><guid isPermaLink=\"true\">%s/item/%s/</guid>"
        "<description>%s</description><category>%s</category><pubDate>%s</pubDate>%s</item>"
        % (e(it["title"]), BASE, it["id"], BASE, it["id"], e("%s｜%s" % (when_line(it), it["memo"])), e(it["kind"]), pub(it["added"]), feed_image(it))
        for it in items)
    write("/feed.xml", '''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>%s 観測レポート</title><link>%s/report/</link>
<description>観測所に新しく加わったサービスと情報</description><language>ja</language>%s</channel></rss>
''' % (e(CONF["site_name"]), BASE, entries))


def build_meta_files(ctx):
    urls = "".join("<url><loc>%s</loc><lastmod>%s</lastmod></url>" % (e(u), d.isoformat()) for u, d in ctx["sitemap"])
    write("/sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>\n' % urls)
    write("/robots.txt", "User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % BASE)
    write("/.nojekyll", "")
    # 毎週のリンク点検の結果（tools/check_links.py が data/linkcheck.json に書く）を、サイトのトップと同じ場所に置く
    linkcheck = os.path.join(ROOT, "data", "linkcheck.json")
    if os.path.exists(linkcheck):
        shutil.copyfile(linkcheck, os.path.join(OUT, "linkcheck.json"))


def assets_version():
    """assets/ の中身から作る短い印。中身が変わると印が変わり、ブラウザが古い見た目や動きを使い続けないようにする。"""
    h = hashlib.sha1()
    folder = os.path.join(ROOT, "assets")
    for dirpath, dirnames, filenames in sorted(os.walk(folder)):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            with open(full, "rb") as f:
                h.update(os.path.relpath(full, folder).encode("utf-8") + f.read())
    return h.hexdigest()[:10]


def save_snapshot(text):
    """読み込んだCSVを data/latest.csv に残す（毎日の記録で、何がいつ変わったかの履歴になる）。
    リポジトリは公開されているので、画面に出さない「観測スコア」の列は外して残す。"""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return
    drop = [i for i, h in enumerate(rows[0]) if h.strip() == "観測スコア"]
    with open(os.path.join(ROOT, "data", "latest.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        for r in rows:
            w.writerow([v for i, v in enumerate(r) if i not in drop])


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
    ap.add_argument("--save-data", action="store_true",
                    help="読み込んだCSVを data/latest.csv に残す（毎日の自動更新で使い、変更の履歴にする）")
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
        "version": assets_version(),
        "sitemap": [],
        "new_items": new_items,
        "new_ids": {it["id"] for it in new_items},
        "tenki_count": {t["name"]: sum(1 for it in listed if matches_tenki(it, t["name"])) for t in TENKI},
    }

    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(os.path.join(ROOT, "assets"), os.path.join(OUT, "assets"))
    # 紹介ページごとの共有画像（tools/make_item_og.py が og-items/ に作る。なければ作らない）
    og_dir = os.path.join(ROOT, "og-items")
    if os.path.isdir(og_dir):
        shutil.copytree(og_dir, os.path.join(OUT, "images", "og"))
    # 掲載先の画像（画像が取れて、除外していないものだけ）
    os.makedirs(os.path.join(OUT, "images", "items"))
    for item_id in IMAGES:
        for name in (item_id + ".webp", item_id + "-s.webp"):
            shutil.copy2(os.path.join(ROOT, "images", "items", name), os.path.join(OUT, "images", "items", name))

    build_home(listed, ctx)
    build_search(listed, ctx)
    build_tenki(listed, ctx)
    for it in items:
        build_item(it, listed, ctx)
    build_report(listed, ctx)
    build_about(listed, ctx)
    build_404(ctx)
    build_saved(ctx)
    build_guide(listed, ctx)
    build_check(listed, ctx)
    build_search_json(listed, ctx)
    build_feed(listed, ctx)
    build_meta_files(ctx)

    meta = {"built": today.isoformat(), "total": len(items), "listed": len(listed)}
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    with open(os.path.join(ROOT, "data", "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")
    if args.save_data:
        save_snapshot(text)
    print("作成しました: 全%d件（掲載中%d件、今週の新着%d件、ページ%d枚）"
          % (len(items), len(listed), len(new_items), len(ctx["sitemap"])))


if __name__ == "__main__":
    try:
        main()
    except BuildError as ex:
        print("中止: %s" % ex, file=sys.stderr)
        sys.exit(1)
