"""ページの部品（ヘッダー・フッター・カード・画像・パンくず・page() と write() など）と、検索用の文字の整え方。"""
import hashlib
import html
import json
import os
import re
import unicodedata
from urllib.parse import quote, urlencode
from sitegen.core import BASE, COMMON, CONF, IMAGES, KIND_BY_NAME, NOTES_LABEL, OTHER, OUT, ROOT, VOICES_LABEL, by_kind

__all__ = ["EMOJI_RE", "emoji_name", "emoji_file", "emoji_img", "emoji_images", "prepare_emoji", "HEAD_SCRIPT", "NAV", "SAVE_ICON", "SHARE_ICON", "TENKI_AI", "WEEKDAYS", "_CRUMBS", "_KAKASI", "added_label", "ai_link", "analytics_tag", "breadcrumb", "card", "cards", "e", "emoji", "fmt_date", "image_credit", "image_info", "image_ref", "item_media", "jsonld_tag", "kind_emoji", "kind_sections", "kind_shelves", "more_link", "nav_links", "normalize", "og_image", "page", "reading", "save_button", "search_url", "site_footer", "site_header", "sm_shelf", "tag_list", "tenki_url", "when_line", "write"]


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


# 観測レポートはフッターから、あとで見るはヘッダーのしおりの絵から開く
# セルフチェック（/check/）は 2026-11-06 にメニューから外した（ページは残す。トップやほかのページからのリンクはそのまま）
NAV = [("/search/", "探す"), ("/tenki/", "転機から"), ("/notes/", "観測ノート"), ("/voices/", "転機の声")]


def nav_links(current=None):
    out = []
    for href, label in NAV:
        if href == "/voices/":
            label = VOICES_LABEL
        cur = ' aria-current="page"' if href == current else ""
        out.append('      <a href="%s"%s>%s</a>' % (href, cur, e(label)))
        if href == "/voices/" and TENKI_AI:  # 転機AIは観測所の外なので、サイト内の項目（転機の声まで）のあとに置く
            out.append('      ' + ai_link(TENKI_AI, "転機AIに相談", "nav"))
    return "\n".join(out)


TENKI_AI = CONF.get("tenki_ai_url", "")


def ai_link(href, label, where, cls=""):
    """転機AI（観測所の外、Claude のアーティファクト）へのリンク。新しいタブで開き（↗ の印は style.css が付ける）、どこから移ったかを数える。"""
    return ('<a%s href="%s" target="_blank" rel="noopener" data-goatcounter-click="tenki-ai/%s" data-goatcounter-title="転機AI（%s）">%s'
            '<span class="visually-hidden">（新しいタブで開く）</span></a>'
            % (' class="%s"' % cls if cls else "", e(href), e(where), e(where), e(label)))


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
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
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
    <a class="header-saved-btn" href="/saved/" aria-label="あとで見る" title="あとで見る"{saved_cur}><svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true"><path d="M6 3h12v18l-6-4.5L6 21z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg><span class="header-saved-count" id="saved-count-h" hidden></span></a>
    <a class="header-search-btn" id="header-search-btn" href="/search/" aria-label="キーワードで探す" aria-expanded="false" aria-controls="header-search"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M15.5 15.5 21 21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></a>
    <button type="button" class="menu-btn" id="menu-btn" aria-label="メニュー" aria-expanded="false" aria-controls="global-nav"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button>
  </div>
  <form class="header-search wrap" id="header-search" action="/search/" method="get" role="search" hidden>
    <label for="header-q" class="visually-hidden">キーワード</label>
    <input id="header-q" type="search" name="q" placeholder="キーワードで探す（例：フリーランス、確定申告）">
    <button type="submit">探す</button>
  </form>
</header>""".format(site=e(CONF["site_name"]), nav=nav_links(current), saved_cur=' aria-current="page"' if current == "/saved/" else "")


def site_footer(ctx):
    """全ページ共通のフッターと、サイト全体の動き（site.js）。"""
    return """<footer class="site-footer">
  <div class="wrap">
    <div class="community">
      <p>この観測所は、<a href="{operator}" rel="noopener" target="_blank">黒田悠介</a>が運営する「<a href="/project/">あしたの転機プロジェクト</a>」の一部です。転機について考えるnoteマガジン、語り合うイベントやコミュニティなどを、プロジェクトのページにまとめています。</p>
      <p>運営者のほかのサイト：<a href="https://community-zukan.github.io/" rel="noopener" target="_blank" data-goatcounter-click="sister/zukan">コミュニティ図鑑</a></p>
    </div>
    <div class="footer-bottom">
      <p class="footer-meta"><a href="/about/">観測所について</a>・<a href="/guide/">支援者の方へ</a>・<a href="/report/">観測レポート</a>{notes}・<a href="{contact}" rel="noopener" target="_blank">観測所へのご連絡</a>・最終更新 {updated}</p>
      <button type="button" class="theme-toggle" id="theme-toggle" aria-pressed="false">ダーク表示</button>
    </div>
  </div>
</footer>
<script src="/assets/site.js?v={ver}"></script>""".format(contact=e(CONF["contact_form_url"]), operator=e(CONF.get("operator_url", "")),
                         updated=fmt_date(ctx["today"]), ver=ctx["version"],
                         notes='・<a href="/notes/">%s</a>' % NOTES_LABEL if any(not n["draft"] for n in ctx.get("notes", [])) else "") + analytics_tag(ctx)


def analytics_tag(ctx):
    """アクセス解析（GoatCounter）。Cookieを使わず、見たページと来た元だけを数える。サイト名が空なら何も入れない。"""
    code = CONF.get("goatcounter_code", "")
    if not code:
        return ""
    return ('\n<script data-goatcounter="https://%s.goatcounter.com/count" async src="/assets/count.js?v=%s"></script>'
            % (e(code), ctx["version"]))


def page(path, title, description, body, *, full_title=None, noindex=False, ctx, image=None, jsonld=None, lastmod=None, extra_head=""):
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
{extra_head}<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
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
           og_title=e(full_title or title), base=e(BASE), header=site_header(next((h for h in [h for h, _ in NAV] + ["/saved/"] if path.startswith(h)), None)), footer=site_footer(ctx), head_script=HEAD_SCRIPT, image=e(image or "/assets/ogp.png"), ld=ld, ver=ctx["version"], body=body,
           contact=e(CONF["contact_form_url"]),
           updated=fmt_date(ctx["today"]), extra_head=extra_head)
    write(path, html_text)
    if not noindex:
        ctx["sitemap"].append((url, lastmod or ctx["today"]))  # サイトマップの更新日（紹介ページは最終観測日、ほかは作った日）


def write(path, text):
    target = os.path.join(OUT, path.lstrip("/"))
    if path.endswith("/"):
        target = os.path.join(target, "index.html")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if target.endswith(".html"):
        text = emoji_images(text)
    with open(target, "w", encoding="utf-8") as f:
        f.write(text)


def more_link(href, label):
    return '<p class="more"><a href="%s">%s</a></p>' % (e(href), e(label))


# 絵文字は、どの端末でも Google の Noto Color Emoji の絵（Apache License 2.0）にそろえる。
# 書体（Google Fonts）で配ると iPhone の Safari では空白になる（Safari が読めない形式で届く。2026-11-08）ので、
# コミュニティ図鑑と同じく、Noto の SVG 画像を assets/emoji/ に置き、ページの文字の絵文字を <img> に置き換える。
# U+1F000 以降はそのまま。それより前の記号（♪ ☆ など）は、ふつうの文字として使うことも多いので、
# 絵文字として書いたもの（直後に U+FE0F がある）と、もともと絵文字で表示される少数（✨ など）だけを絵にする（2026-11-08 図鑑のセッションの指摘）。
_EMOJI_ONE = "(?:[\U0001F000-\U0001FAFF]|[\u2300-\u23FF\u2600-\u27BF\u2B00-\u2BFF]\uFE0F|[\u2728\u2705\u274C\u2B50\u23F0\u231B\u2615\u26A1\u2753\u2757])\uFE0F?"
EMOJI_RE = re.compile("[\U0001F1E6-\U0001F1FF]{2}|%s(?:\u200D%s|\u200D[\u2640\u2642\u2695\u2696\u2708\u2764]\uFE0F?)*" % (_EMOJI_ONE, _EMOJI_ONE))
EMOJI_DIR = os.path.join(ROOT, "assets", "emoji")
# noto-emoji の版を固定する（2026-11-08 時点の main。2D の絵）
NOTO_SVG = "https://raw.githubusercontent.com/googlefonts/noto-emoji/99701e07d3d1fe1bdbcdb14964547f0fd592966f/2D/svg/emoji_u%s.svg"
_EMOJI_OK = {}


def emoji_name(seq):
    """Noto の画像のファイル名（異体字セレクタ U+FE0F を除いた符号位置を _ でつなぐ）。"""
    return "_".join("%04x" % ord(c) for c in seq if c != "\ufe0f")


def emoji_file(seq):
    """その絵文字の画像が assets/emoji/ にあるか。なければ noto-emoji から取ってくる。取れなければ文字のまま出す。"""
    name = emoji_name(seq)
    if name not in _EMOJI_OK:
        path = os.path.join(EMOJI_DIR, name + ".svg")
        if not os.path.exists(path):
            import urllib.request
            try:
                with urllib.request.urlopen(NOTO_SVG % name, timeout=20) as r:
                    data = r.read()
                os.makedirs(EMOJI_DIR, exist_ok=True)
                with open(path, "wb") as f:
                    f.write(data)
            except Exception as err:
                print("注意: 絵文字 %s（%s）の画像を取れなかったので、文字のまま出します: %s" % (seq, name, err))
        _EMOJI_OK[name] = os.path.exists(path)
    return name if _EMOJI_OK[name] else None


def emoji_img(seq):
    name = emoji_file(seq)
    if not name:
        return seq
    return '<img class="emo" src="/assets/emoji/%s.svg" alt="%s" draggable="false">' % (name, seq)


_EMOJI_SKIP = ("script", "style", "title", "textarea")


def emoji_images(text):
    """HTML の文字の部分（タグの中や script・style・title を除く）の絵文字を、Noto の画像に置き換える。"""
    out, skip = [], None
    for part in re.split(r"(<[^>]*>)", text):
        if part.startswith("<"):
            m = re.match(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)", part)
            if m:
                tag = m.group(2).lower()
                if skip and m.group(1) and tag == skip:
                    skip = None
                elif not skip and not m.group(1) and tag in _EMOJI_SKIP:
                    skip = tag
            out.append(part)
        elif skip or not part:
            out.append(part)
        else:
            out.append(EMOJI_RE.sub(lambda m: emoji_img(m.group(0)), part))
    return "".join(out)


def prepare_emoji():
    """ページの作り方・動き（JS が出す絵文字も）・設定・観測ノートの原稿にある絵文字の画像を、先にそろえておく。"""
    for folder, exts in (("sitegen", ".py"), ("assets", ".js"), ("check", ".js"), ("config", ".json"), ("notes", ".md")):
        base = os.path.join(ROOT, folder)
        for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
            if name.endswith(exts):
                with open(os.path.join(base, name), encoding="utf-8") as f:
                    for seq in EMOJI_RE.findall(f.read()):
                        emoji_file(seq)


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
    # 1.4:1 より横長なら、上下が少し切れても枠いっぱいに出す（左右の空白を作らない）。image_fill は個別に枠いっぱいにする掲載
    wide = w / h >= 1.4 or item["id"] in CONF.get("image_fill", [])
    return rec["ver"], ("wide" if wide else "fit"), w, h


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


WEEKDAYS = "月火水木金土日"


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
