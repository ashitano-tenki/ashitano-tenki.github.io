"""転機の声（/voices/）。"""
import csv
import collections
import io
import json
import os
import re
import sys
from sitegen.core import BuildError, ROOT, TENKI, VOICES, VOICES_LABEL, fetch_csv, month_label, parse_month, split_list, valid_id
from sitegen.parts import breadcrumb, e, emoji, normalize, page, reading, write

__all__ = ["VOICES_JSON_LINK", "VOICES_SNAPSHOT", "VOICES_TEXT", "VOICE_COLUMNS", "build_voices", "parse_voices", "voice_band", "voice_card", "voice_month", "voice_stats", "voices_for_item", "voices_text", "write_voices_json"]
VOICES_SNAPSHOT = os.path.join(ROOT, "data", "voices.csv")  # 前回読めた中身（読めなかった日はこれを使う）
VOICES_TEXT = {}  # main() で読んだCSVの文字列（--save-data のとき data/voices.csv に残す）
VOICE_COLUMNS = ["ID", "タイトル", "語り手", "転機の前", "転機の後", "転機の種類", "段階", "きっかけ", "年代",
                 "発信元の区分", "要約", "URL", "掲載媒体", "公開日", "観測所ID", "キーワード"]


def voices_text(path=None):
    """転機の声のCSVの文字列。手元のファイルを指定したときはそれを、なければネットから。読めなければ前回の中身、それもなければ空。"""
    if path:
        with open(path, encoding="utf-8-sig") as f:
            return f.read()
    url = VOICES.get("csv_url", "")
    if url:
        try:
            text = fetch_csv(url)
            if text.lstrip().startswith("<"):
                raise BuildError("CSVの代わりにHTMLが返ってきました")
            VOICES_TEXT["text"] = text
            return text
        except BuildError as ex:
            print("注意: 転機の声のCSVを読めませんでした（前回の中身を使います）: %s" % ex, file=sys.stderr)
    if os.path.exists(VOICES_SNAPSHOT):
        with open(VOICES_SNAPSHOT, encoding="utf-8") as f:
            return f.read()
    return ""


def parse_voices(text):
    """公開用タブの行を記事の一覧にする。列が足りないときは、サイト全体を止めずに0件として扱う。新しい公開日の順に並べる。"""
    reader = csv.DictReader(io.StringIO(text or ""))
    header = [h.strip() for h in (reader.fieldnames or [])]
    missing = [c for c in VOICE_COLUMNS if c not in header]
    if text.strip() and missing:
        print("注意: 転機の声のCSVに必要な列がありません（0件として作ります）: %s" % "、".join(missing), file=sys.stderr)
        return []
    out, seen = [], set()
    for raw in reader:
        row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
        vid, url = row.get("ID", ""), row.get("URL", "")
        if not valid_id(vid) or vid in seen or not row.get("タイトル") or not re.match(r"^https?://", url):
            continue
        seen.add(vid)
        out.append({
            "id": vid, "title": row["タイトル"], "who": row["語り手"], "before": row["転機の前"], "after": row["転機の後"],
            "tenki": split_list(row["転機の種類"]), "stages": split_list(row["段階"]), "triggers": split_list(row["きっかけ"]),
            "age": row["年代"] or "不明", "age_raw": row["年代"], "job": row.get("職種", ""), "industry": row.get("業界", ""),
            "source": row["発信元の区分"], "summary": row["要約"], "url": url,
            "media": row["掲載媒体"], "month": parse_month(row["公開日"]),
            "items": [x for x in split_list(row["観測所ID"]) if valid_id(x)],
            # キーワード（観測所の「向いている人」と同じ言葉）は検索にだけ使い、画面には出さない
            "keywords": split_list(row["キーワード"]),
        })
    out.sort(key=lambda v: (v["month"] or (0, 0), v["id"]), reverse=True)
    return out


def voice_month(v):
    return month_label(v["month"]) if v["month"] else ""


def voice_card(v, by_id):
    """転機の声の記事カード（「いま」が見出しの雑誌風）。上半分に転機の種類・年代・前・転機の後（見出し）・語り手、
    下半分にきっかけ・あらすじ・記事へのリンク。段階・発信元の注記・この話に出てくるものは出さない（2026-11-06 黒田さんの判断。
    絞り込みと検索には残る）。data-* は voices.js の絞り込み・並び替えに使う。"""
    tenki_emoji = {t["name"]: t.get("emoji", "") for t in TENKI}
    trig_emoji = VOICES.get("trigger_emoji", {})
    # 札（転機の種類・年代・きっかけ）は押すとその条件で絞り込む（voices.js）
    tag = lambda cls, f, val, label: ('<button type="button" class="%s" data-f="%s" data-v="%s" title="「%s」で絞り込む">%s</button>'
                                      % (cls, f, e(val), e(val), label))
    badges = "".join(tag("vc-tenki", "tenki", t, emoji(tenki_emoji.get(t, "")) + e(t)) for t in v["tenki"])
    if v["age"] != "不明":
        badges += tag("vc-age", "age", v["age"], e(v["age"]))
    big = next((tenki_emoji[t] for t in v["tenki"] if tenki_emoji.get(t)), "")
    icon = '<span class="vc-icon" aria-hidden="true">%s</span>' % e(big) if big else ""
    # 「前」のラベルは付けない（見出しの矢印で前後が分かるため。2026-11-06 黒田さんの判断）。読み上げでは「転機の前：」と読む
    before = '<p class="vc-from"><span class="visually-hidden">転機の前：</span>%s</p>' % e(v["before"]) if v["before"] else ""
    after = '<span class="vc-after-arrow" aria-hidden="true">→</span>%s' % e(v["after"] or v["title"])  # 見出し（h3）の中身。p で包まない（余白が付くため）
    trig = ('<p class="vc-trig"><span class="visually-hidden">きっかけ：</span>%s</p>'
            % "".join(tag("vc-chip", "trigger", t, emoji(trig_emoji.get(t, "")) + e(t)) for t in v["triggers"])) if v["triggers"] else ""
    # あらすじは吹き出しで、カードの上に重ねて開く（カードの形を変えない。2026-11-06 黒田さんの判断）。開け閉めは voices.js
    summary = ('<details class="vc-more"><summary>あらすじを読む</summary><div class="vc-bubble">'
               '<span class="vc-bubble-head">あらすじ<button type="button" class="vc-bubble-x" aria-label="あらすじを閉じる">×</button></span>'
               '<p>%s</p></div></details>' % e(v["summary"])) if v["summary"] else ""
    meta = "・".join(x for x in [e(v["media"]), e(voice_month(v))] if x)
    raw = " ".join([v["title"], v["who"], v["before"], v["after"], v["summary"], v["media"]] + v["keywords"])
    text = normalize(raw) + " " + reading(raw)  # 読み（ひらがなでも探せるように。pykakasi があるときだけ）
    data = {"tenki": v["tenki"], "stage": v["stages"], "trigger": v["triggers"], "age": [v["age"]], "source": [v["source"]], "item": v["items"]}
    attrs = "".join(' data-%s="%s"' % (k, e("|".join(vals))) for k, vals in data.items())
    return ('<li class="voice" data-id="%s"%s data-month="%s" data-text="%s"><article class="voice-card">'
            '<div class="vc-top">%s<div class="vc-head">%s</div>%s<h3 class="vc-headline">%s</h3><p class="vc-who" title="%s">%s</p></div>'
            '<div class="vc-body">%s%s<div class="vc-foot"><p class="vc-meta">%s</p>'
            '<a class="vc-title" href="%s" target="_blank" rel="noopener">%s<span class="visually-hidden">（新しいタブで開く）</span></a>'
            '<a class="vc-go" href="%s" target="_blank" rel="noopener">記事を読む<span class="visually-hidden">（新しいタブで開く）</span></a></div></div>'
            '</article></li>'
            % (e(v["id"]), attrs, "%04d-%02d" % v["month"] if v["month"] else "", e(text),
               icon, badges, before, after, e(v["who"]), e(v["who"]), trig, summary, meta, e(v["url"]), e(v["title"]), e(v["url"])))


def voice_stats(voices):
    """数字で見る：転機の種類・段階・年代ごとの件数を、横向きの棒で。1件の記事が複数の転機に入るので、合計は件数より多くなる。"""
    def group(title, names, counter, note=""):
        top = max([counter.get(n, 0) for n in names] + [1])
        rows = "".join('<li><span class="vs-name">%s</span><span class="vs-bar" aria-hidden="true"><i style="width:%.1f%%"></i></span><span class="vs-num">%d件</span></li>'
                       % (e(n), 100.0 * counter.get(n, 0) / top, counter.get(n, 0)) for n in names if counter.get(n, 0) or n != "不明")
        return '<div class="vs-group"><h3>%s</h3>%s<ul class="vs-rows">%s</ul></div>' % (e(title), '<p class="vs-note">%s</p>' % e(note) if note else "", rows)
    tenki = collections.Counter(t for v in voices for t in v["tenki"])
    stages = collections.Counter(s for v in voices for s in v["stages"])
    ages = collections.Counter(v["age"] for v in voices)
    return ('<section class="voice-stats" aria-labelledby="vs-h"><h2 class="section-title" id="vs-h">数字で見る</h2>'
            '<p class="vs-total">確認して載せている記事 <b>%d</b>件</p><div class="vs-grid">%s%s%s</div></section>'
            % (len(voices), group("転機の種類", VOICES.get("tenki", []), tenki, "1つの記事に2つ以上の転機があるときは、それぞれに数えます。"),
               group("段階", VOICES.get("stages", []), stages, "語られている段階をすべて数えます。"),
               group("年代", VOICES.get("ages", []), ages, "転機を迎えたときの年代です。")))


def write_voices_json(voices, ctx):
    """転機の声の中身をまとめた /voices/index.json（転機AIが読む）。/voices/ と同じ記事を同じ順（公開日の新しい順）で入れる。
    値が空のときもキーは残す（文字は空文字、一覧は空の配列）。items は観測所に紹介ページがあるIDだけ。"""
    ids = ctx.get("item_ids", set())
    data = {"updated": ctx["today"].isoformat(), "count": len(voices), "voices": [{
        "id": v["id"], "title": v["title"], "speaker": v["who"], "before": v["before"], "after": v["after"],
        "tenki": v["tenki"], "dankai": v["stages"], "trigger": v["triggers"], "age": v["age_raw"],
        "job": v["job"], "industry": v["industry"], "source": v["source"], "summary": v["summary"], "url": v["url"],
        "media": v["media"], "published": "%04d-%02d" % v["month"] if v["month"] else "",
        "items": [i for i in v["items"] if i in ids], "keywords": v["keywords"]} for v in voices]}
    write("/voices/index.json", json.dumps(data, ensure_ascii=False, indent=1) + "\n")


VOICES_JSON_LINK = '<link rel="alternate" type="application/json" href="/voices/index.json" title="%s（JSON）">\n' % e(VOICES_LABEL)


def build_voices(voices, listed, ctx):
    by_id = {it["id"]: it for it in listed}
    write_voices_json(voices, ctx)

    def chip_group(name, label, values, counter, emojis=None):
        """emojis があれば、ボタンの頭に絵文字を付ける（転機の種類はトップページと同じ絵文字）"""
        values = [v for v in values if counter.get(v)]
        if not values:
            return ""
        emojis = emojis or {}
        opts = [("", "すべて")] + [(v, v) for v in values]
        return ('<fieldset class="chip-group"><legend>%s</legend><div class="fchips">%s</div></fieldset>'
                % (e(label), "".join('<label class="fchip"><input type="radio" name="%s" value="%s"%s><span>%s%s<i></i></span></label>'
                                     % (name, e(v), " checked" if not v else "", emoji(emojis.get(v, "")), e(t)) for v, t in opts)))
    head = ('%s\n<header class="page-head"><h1>%s</h1><p class="lead">%s</p></header>\n'
            % (breadcrumb([(VOICES_LABEL, None)]), e(VOICES_LABEL), e(VOICES.get("lead", ""))))
    if not voices:
        body = head + '<p class="voices-empty">%s</p>\n' % e(VOICES.get("empty", "準備中です。"))
        page("/voices/", VOICES_LABEL, VOICES.get("lead", ""), body, ctx=ctx, noindex=True, extra_head=VOICES_JSON_LINK)
        return
    count = lambda key: collections.Counter(x for v in voices for x in (v[key] if isinstance(v[key], list) else [v[key]]))
    filters = "".join([
        chip_group("tenki", "転機の種類", VOICES.get("tenki", []), count("tenki"), {t["name"]: t.get("emoji", "") for t in TENKI}),
        chip_group("stage", "段階", VOICES.get("stages", []), count("stages")),
        chip_group("trigger", "きっかけ", VOICES.get("triggers", []), count("triggers")),
        chip_group("age", "年代", VOICES.get("ages", []), count("age")),
        chip_group("source", "発信元", VOICES.get("sources", []), count("source")),
    ])
    body = head + """<form id="vfilters" class="filters voices-filters" action="/voices/" method="get" role="search">
  <div class="search-q">
    <label for="vq" class="visually-hidden">キーワード</label>
    <input id="vq" type="search" name="q" placeholder="キーワードで探す（例：育児、エンジニア、地方）" autocomplete="off">
  </div>
  <div class="search-layout">
    <div class="filter-col">
      <button type="button" id="filter-toggle" class="filter-toggle" aria-expanded="false" aria-controls="filter-panel">絞り込む<span id="filter-count"></span></button>
      <div id="filter-panel" class="filter-panel">
        {filters}
      </div>
    </div>
    <div class="result-col">
      <h2 class="visually-hidden">記事の一覧</h2>
      <div class="result-bar">
        <p id="result-count" aria-live="polite">{n}件</p>
        <button type="button" class="bar-filter" id="bar-filter" aria-controls="filter-panel" aria-expanded="false">絞り込む</button>
        <div class="sort-field"><label for="sort">並び順</label><select id="sort" name="sort"><option value="">公開日の新しい順</option><option value="old">公開日の古い順</option></select></div>
      </div>
      <div id="active-chips" class="active-chips" hidden></div>
      <ol id="voices" class="voice-list">{cards}</ol>
      <p class="more-wrap"><button type="button" id="more" class="button" hidden>もっと見る</button></p>
    </div>
  </div>
</form>
{stats}
<script>window.TENKI_PAGE_SIZE = {page_size};</script>
<script src="/assets/voices.js?v={ver}" defer></script>
""".format(filters=filters, n=len(voices), cards="".join(voice_card(v, by_id) for v in voices), stats=voice_stats(voices),
           page_size=int(VOICES.get("page_size", 8)), ver=ctx["version"])
    page("/voices/", VOICES_LABEL, VOICES.get("lead", ""), body, ctx=ctx, extra_head=VOICES_JSON_LINK)


def voices_for_item(voices, item_id):
    return [v for v in voices if item_id in v["items"]]


def voice_band(item, ctx):
    """紹介ページの「この情報が出てくる転機の声」。記事のタイトル（記事へ）と語り手を最大5件。0件なら何も出さない。"""
    hits = voices_for_item(ctx.get("voices", []), item["id"])
    if not hits:
        return ""
    limit = int(VOICES.get("item_max", 5))
    lis = "".join('<li><a href="%s" target="_blank" rel="noopener">%s<span class="visually-hidden">（新しいタブで開く）</span></a>'
                  '<span class="voice-band-who">%s</span></li>'
                  % (e(v["url"]), e(v["title"]), e("・".join(x for x in [v["who"], v["media"]] if x))) for v in hits[:limit])
    more = ('<a href="/voices/?item=%s">%sの一覧で見る（%d件）</a>' % (e(item["id"]), e(VOICES_LABEL), len(hits))) if len(hits) > limit \
        else '<a href="/voices/">%sをもっと見る</a>' % e(VOICES_LABEL)
    return ('<section class="voice-band"><h2 class="voice-band-title">この情報が出てくる%s</h2>'
            '<p class="voice-band-lead">この掲載が話に出てくるインタビュー記事です。記事は各サイトで開きます。</p>'
            '<ul class="voice-band-list">%s</ul><p class="voice-band-more">%s</p></section>\n' % (e(VOICES_LABEL), lis, more))
