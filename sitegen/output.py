"""検索用データ・セルフチェック・RSS・サイトマップなど、ページ以外の書き出しと、公開前の件数チェック。"""
import csv
import datetime
import hashlib
import io
import json
import os
import shutil
from sitegen.core import BASE, BuildError, CONF, JST, OUT, ROOT, STAGES, load_json
from sitegen.parts import HEAD_SCRIPT, e, image_info, image_ref, normalize, reading, site_footer, site_header, when_line, write

__all__ = ["assets_version", "build_check", "build_feed", "build_meta_files", "build_search_json", "check_counts", "feed_image", "save_snapshot", "write_items_json"]


def write_items_json(listed, ctx):
    """掲載中の一覧をまとめた /items.json（転機AIが読む）。おすすめ順（rank の小さい順）で入れる。
    観測スコアと料金は入れない（サイトに出していないため）。並べ替えには rank を使う。値が空のときもキーは残す。"""
    data = {"updated": ctx["today"].isoformat(), "count": len(listed), "items": [{
        "id": it["id"], "title": it["title"], "kind": it["kind"], "tenki": it["tenki"], "stages": it["stages"],
        "memo": it["memo"], "url": it["url"], "provider": it["provider"], "for": it["for"],
        "added": it["added"].isoformat() if it["added"] else "", "rank": it["rank"],
        "page": "%s/item/%s/" % (BASE, it["id"])} for it in sorted(listed, key=lambda it: it["rank"])]}
    write("/items.json", json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")


def build_search_json(listed, ctx):
    synonyms = load_json("synonyms.json").get("groups", [])
    data = {
        "items": [{
            "id": it["id"], "title": it["title"], "line": it["line"], "kind": it["kind"],
            "tenki": it["tenki"], "stages": it["stages"],
            "added": it["added"].isoformat() if it["added"] else "",
            "rank": it["rank"], "img": image_ref(it),
        } for it in listed],
        # 言い換え表。読みは「どのグループに当たるか」の判定にだけ使う（「ふくぎょう」でも 副業・兼業 などが一緒に見つかるように）。
        # 読みで本文を探すと、同じ読みの別の言葉（障害と生涯）まで見つかるため、本文を探すのは words だけ
        "synonyms": [{"words": sorted({normalize(w) for w in g if w.strip()}),
                      "readings": sorted({reading(w) for w in g if w.strip()} - {""})} for g in synonyms if isinstance(g, list)],
    }
    # キーワード検索に使う文字（説明の全文と読み）は、データの4分の3を占めるので別のファイル /search-text.json に分ける。
    # 探すページは search.json だけで一覧を先に出し、キーワードで探すときだけ search-text.json を待つ（探せる言葉や結果は変わらない）
    text_by_id = {it["id"]: normalize(" ".join([it["title"], it["memo"], it["provider"], it["kind"], " ".join(it["for"]),
                                                 " ".join(it["tenki"]), " ".join(it["stages"])]))
                             + " " + reading(" ".join([it["title"], it["memo"], it["provider"], it["kind"], " ".join(it["tenki"])])) for it in listed}
    write("/search-text.json", json.dumps({"text": text_by_id}, ensure_ascii=False, separators=(",", ":")))
    # 入力中の候補（言い換え表の言葉のうち、掲載に1件以上あるもの）。読みを添えて、ひらがなでも候補に出す
    texts = list(text_by_id.values())
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
    # AI の学習用のクローラーだけを断る（2026-11-06 黒田さんの判断。コミュニティ図鑑と同じ）。検索用（OAI-SearchBot・Claude-SearchBot・PerplexityBot など）と
    # ふつうの検索エンジンは通す。AI の検索の答えに観測所が出典として出る道は残すため。robots.txt はお願いで、守らない相手は止められない
    AI_TRAINING = ["GPTBot", "ClaudeBot", "anthropic-ai", "Google-Extended", "CCBot", "Applebot-Extended", "Meta-ExternalAgent", "Bytespider", "cohere-training-data-crawler"]
    blocks = "".join("User-agent: %s\nDisallow: /\n\n" % b for b in AI_TRAINING)
    write("/robots.txt", "%sUser-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % (blocks, BASE))
    write("/.nojekyll", "")
    # 毎週のリンク点検の結果（tools/check_links.py が data/linkcheck.json に書く）を、サイトのトップと同じ場所に置く
    linkcheck = os.path.join(ROOT, "data", "linkcheck.json")
    if os.path.exists(linkcheck):
        shutil.copyfile(linkcheck, os.path.join(OUT, "linkcheck.json"))
    # 週次の数字（tools/fetch_stats.py が毎週月曜に data/stats.json に書く。週次ふりかえりが読む）
    stats = os.path.join(ROOT, "data", "stats.json")
    if os.path.exists(stats):
        shutil.copyfile(stats, os.path.join(OUT, "stats.json"))


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
