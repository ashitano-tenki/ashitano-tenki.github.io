"""「あしたの転機」のページ（/project/）。"""
import csv
import datetime
import email.utils
import hashlib
import io
import os
import re
import sys
import urllib.request
from sitegen.core import BuildError, CONF, JST, OUT, ROOT, fetch_csv
from sitegen.parts import WEEKDAYS, breadcrumb, e, fmt_date, page

__all__ = ["PROJECT_INTRO", "PROJECT_SNAPSHOT", "PROJECT_TEXT", "build_project", "event_when", "parse_when", "project_rows", "project_thumb", "read_feed"]


# ---------------------------------------------------------------- あしたの転機（運営元のプロジェクトのページ）
# 観測所の一覧・検索・絞り込み・並び順には入れない。中身はスプレッドシートの「あしたの転機」タブ（config/site.json の project_csv_url）。

# ページの冒頭の紹介文。直したいときはここを書き換える
PROJECT_INTRO = ("「あしたの転機プロジェクト」は、あしたやってくるかもしれない人生の転機について、"
                 "これからの時代の働き方や生き方をテーマに考えていくプロジェクトです。")
PROJECT_SNAPSHOT = os.path.join(ROOT, "data", "project.csv")  # 前回読めた中身（読めなかった日はこれを使う）
PROJECT_TEXT = {}  # main() で読んだCSVの文字列（--save-data のとき data/project.csv に残す）


def project_rows():
    """「あしたの転機」タブの行。「表示しない」の行は除く。読めなければ前回の中身を使う。"""
    text = ""
    url = CONF.get("project_csv_url", "")
    if url:
        try:
            text = fetch_csv(url)
            PROJECT_TEXT["text"] = text
        except BuildError as ex:
            print("注意: あしたの転機のCSVを読めませんでした（前回の中身を使います）: %s" % ex, file=sys.stderr)
    if not text and os.path.exists(PROJECT_SNAPSHOT):
        with open(PROJECT_SNAPSHOT, encoding="utf-8") as f:
            text = f.read()
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        r = {k.strip(): (v or "").strip() for k, v in r.items() if k}
        if r.get("区分") and r.get("タイトル") and r.get("表示") != "表示しない":
            rows.append(r)
    return rows


def read_feed(url, limit):
    """RSSから新しい順に limit 件（タイトル・リンク・公開日・画像）。読めなければ空。"""
    import xml.etree.ElementTree as ET
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "tenki-kansoku-build"})
        with urllib.request.urlopen(req, timeout=30) as res:
            root = ET.fromstring(res.read())
    except Exception as ex:  # フィードが読めない日は、リンクだけを出す
        print("注意: フィードを読めませんでした: %s (%s)" % (url, ex), file=sys.stderr)
        return []
    out = []
    for it in root.iter("item"):
        title, link = (it.findtext("title") or "").strip(), (it.findtext("link") or "").strip()
        if not title or not link.startswith("https://"):
            continue
        date = None
        try:
            # 「+0900」も「GMT」も読めるように（PodcastのRSSは GMT で書かれている）
            date = email.utils.parsedate_to_datetime((it.findtext("pubDate") or "").strip()).astimezone(JST).date()
        except (TypeError, ValueError):
            pass
        thumb = (it.findtext("{http://search.yahoo.com/mrss/}thumbnail") or "").strip()
        out.append({"title": title, "link": link, "date": date, "thumb": thumb})
        if len(out) >= limit:
            break
    return out


def project_thumb(url):
    """記事の画像を観測所の中に取り込む（見る人の端末から外のサイトへ読みに行かないように）。取り込めなければ空。"""
    if not url.startswith("https://"):
        return ""
    url = re.sub(r"([?&])width=\d+", r"\1width=480", url)
    name = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "tenki-kansoku-build"})
        with urllib.request.urlopen(req, timeout=30) as res:
            kind, data = res.headers.get("Content-Type", ""), res.read(3_000_000)
    except Exception:
        return ""
    ext = {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}.get(kind.split(";")[0].strip(), ".jpg")
    path = "/images/project/%s%s" % (name, ext)
    os.makedirs(os.path.join(OUT, "images", "project"), exist_ok=True)
    with open(os.path.join(OUT, path.lstrip("/")), "wb") as f:
        f.write(data)
    return path


def parse_when(value):
    try:
        return datetime.datetime.strptime(value, "%Y/%m/%d %H:%M").replace(tzinfo=JST)
    except ValueError:
        return None


def event_when(start, end):
    """「11月6日（木）19:30〜21:30」の形。日をまたぐときは終わりの日付も書く。"""
    s = "%d月%d日（%s）%s" % (start.month, start.day, WEEKDAYS[start.weekday()], start.strftime("%H:%M"))
    if end:
        s += "〜" + (end.strftime("%H:%M") if end.date() == start.date()
                    else "%d月%d日 %s" % (end.month, end.day, end.strftime("%H:%M")))
    return s


def build_project(ctx):
    rows = project_rows()
    by = {}
    for r in rows:
        by.setdefault(r["区分"], []).append(r)
    ext = lambda href, label, cls="": '<a%s href="%s" rel="noopener" target="_blank">%s</a>' % (' class="%s"' % cls if cls else "", e(href), e(label))
    blocks = []

    # コミュニティ（いちばん上に置く）
    for r in by.get("コミュニティ", []):
        blocks.append('<section class="pj-block"><h2 class="section-title">コミュニティ</h2>'
                      '<p class="pj-lead">転機を迎えている人どうしで、%sで交流しています。</p><p class="pj-more">%s</p></section>'
                      % (e(r["タイトル"]), ext(r["URL"], "Facebookグループを見る") if r.get("URL") else ""))

    # note：マガジンへのリンクと、フィードの新しい記事3件
    for r in by.get("note", []):
        posts = read_feed(r["フィードURL"], 3) if r.get("フィードURL") and r.get("表示") == "表示する" else []
        items = []
        for p in posts:
            img = project_thumb(p["thumb"])
            items.append('<li><a class="pj-post linkcard" href="%s" rel="noopener" target="_blank">%s<span class="pj-post-body"><span class="pj-post-title">%s</span>%s</span></a></li>'
                         % (e(p["link"]), '<img src="%s" alt="" loading="lazy" width="240" height="126">' % img if img else '<span class="pj-post-noimg" aria-hidden="true"></span>',
                            e(p["title"]), '<span class="pj-date">%s</span>' % fmt_date(p["date"]) if p["date"] else ""))
        blocks.append('<section class="pj-block"><h2 class="section-title">noteマガジン</h2>'
                      '<p class="pj-lead">転機について考える記事を、noteマガジン「%s」で発信しています。</p>%s<p class="pj-more">%s</p></section>'
                      % (e(r["タイトル"].replace("（noteマガジン）", "")), '<ul class="pj-posts">%s</ul>' % "".join(items) if items else "",
                         ext(r["URL"], "noteマガジンを見る") if r.get("URL") else ""))

    # Podcast：準備中のあいだは「準備中」とだけ出す。表示するにしたら番組へのリンクと最新回3件
    for r in by.get("Podcast", []):
        if r.get("表示") == "準備中" or not r.get("URL"):
            body = '<p class="pj-lead">番組「%s」<span class="pj-soon">準備中</span></p>' % e(r["タイトル"])
        else:
            eps = read_feed(r["フィードURL"], 3) if r.get("フィードURL") else []
            body = '<p class="pj-lead">番組「%s」%s</p>' % (e(r["タイトル"]), "：" + e(r["説明"]) if r.get("説明") else "")
            if eps:
                body += '<ul class="pj-list">%s</ul>' % "".join(
                    '<li>%s%s</li>' % (ext(p["link"], p["title"]), '<span class="pj-date">%s</span>' % fmt_date(p["date"]) if p["date"] else "") for p in eps)
            body += '<p class="pj-more">%s</p>' % ext(r["URL"], "番組を聴く")
        blocks.append('<section class="pj-block"><h2 class="section-title">Podcast</h2>%s</section>' % body)

    # イベント：日時のない行はPeatixのグループページ。日時のある行は、これからのもの（近い順）と過去のもの（新しい順に5件）に分ける
    ev = by.get("イベント", [])
    if ev:
        now = datetime.datetime.now(JST)
        groups = [r for r in ev if not parse_when(r.get("開始日時", ""))]
        dated = [(parse_when(r["開始日時"]), parse_when(r.get("終了日時", "")), r) for r in ev if parse_when(r.get("開始日時", ""))]
        upcoming = sorted([d for d in dated if (d[1] or d[0]) >= now], key=lambda d: d[0])
        past = sorted([d for d in dated if (d[1] or d[0]) < now], key=lambda d: d[0], reverse=True)[:5]

        def event_li(d, soon):
            s, en, r = d
            meta = " ・ ".join(x for x in [e(r.get("場所", "")), e(r.get("価格", ""))] if x)
            return ('<li class="pj-event%s"><p class="pj-event-when">%s</p><p class="pj-event-title">%s</p>%s%s</li>'
                    % ("" if soon else " is-past", event_when(s, en), ext(r["URL"], r["タイトル"]) if r.get("URL") else e(r["タイトル"]),
                       '<p class="pj-event-meta">%s</p>' % meta if meta else "",
                       '<p class="pj-event-desc">%s</p>' % e(r["説明"]) if soon and r.get("説明") else ""))
        body = ""
        if upcoming:
            body += '<h3 class="pj-sub">これからのイベント</h3><ul class="pj-events">%s</ul>' % "".join(event_li(d, True) for d in upcoming)
        if past:
            body += '<h3 class="pj-sub">過去のイベント</h3><ul class="pj-events">%s</ul>' % "".join(event_li(d, False) for d in past)
        more = "".join('<p class="pj-more">%s</p>' % ext(r["URL"], "Peatixでイベントの一覧を見る") for r in groups if r.get("URL"))
        blocks.append('<section class="pj-block"><h2 class="section-title">イベント</h2>'
                      '<p class="pj-lead">転機をテーマに語り合うイベントを開いています。申し込みはPeatixから受け付けています。</p>%s%s</section>' % (body, more))

    # グッズ：価格のない行はショップ、価格のある行は商品
    gd = by.get("グッズ", [])
    if gd:
        shops = [r for r in gd if not r.get("価格")]
        goods = [r for r in gd if r.get("価格")]
        body = '<ul class="pj-goods">%s</ul>' % "".join(
            '<li>%s<span class="pj-price">%s</span></li>' % (ext(r["URL"], r["タイトル"]) if r.get("URL") else e(r["タイトル"]), e(r["価格"])) for r in goods) if goods else ""
        more = "".join('<p class="pj-more">%s</p>' % ext(r["URL"], "ショップを見る") for r in shops if r.get("URL"))
        blocks.append('<section class="pj-block"><h2 class="section-title">グッズ</h2>'
                      '<p class="pj-lead">あしたの転機のオフィシャルグッズを、Tシャツトリニティで販売しています。</p>%s%s</section>' % (body, more))

    body = """
{crumbs}
<header class="page-head">
  <h1>あしたの転機プロジェクト</h1>
  <p class="lead">{intro}</p>
  <p class="pj-owner"><span>主宰：<strong>黒田悠介</strong>（キャリア研究家）</span><a href="{operator}" rel="noopener" target="_blank">活動や発信のリンク集</a></p>
</header>
{blocks}
""".format(crumbs=breadcrumb([("あしたの転機プロジェクト", None)]), intro=e(PROJECT_INTRO), blocks="\n".join(blocks),
           operator=e(CONF.get("operator_url", "")))
    page("/project/", "あしたの転機プロジェクト", "この観測所を運営する「あしたの転機プロジェクト」のコミュニティ、noteマガジン、Podcast、イベント、グッズ。", body, ctx=ctx)
