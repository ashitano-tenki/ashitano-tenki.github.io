"""観測所の主なページ（トップ・転機から・転機×段階・紹介ページ・探す・観測レポート・観測所について・あとで見る・支援者の方へ・404）。"""
import datetime
import collections
import json
import os
import random
from urllib.parse import quote
from sitegen.core import BASE, COMMON, CONF, KINDS, KIND_BY_NAME, NOTES, NOTES_LABEL, OTHER, ROOT, STAGES, STAGE_BY_NAME, TENKI, TENKI_BY_NAME, by_kind, kinds_of, load_json, matches_tenki
from sitegen.parts import SAVE_ICON, SHARE_ICON, TENKI_AI, WEEKDAYS, ai_link, breadcrumb, card, e, emoji, image_credit, image_info, item_media, kind_emoji, kind_sections, kind_shelves, more_link, og_image, page, search_url, sm_shelf, tenki_url
from sitegen.notes import note_band, note_list, notes_for_tenki
from sitegen.voices import voice_band

__all__ = ["ANALYTICS_ABOUT", "CHECK_TEXT", "KIND_ACTION", "KIND_PHRASE", "SHOWN_WORDS", "ai_help_html", "build_404", "build_about", "build_combo", "build_guide", "build_home", "build_item", "build_report", "build_saved", "build_search", "build_tenki", "collection_ld", "combo_guide", "combo_lead", "combo_title", "common_section", "intro_html", "item_kind_phrase", "kind_tabs", "own_and_common", "own_section", "pick_box", "popular_words", "related_choices", "report_cards", "report_link", "stage_band", "start_words_html", "tenki_flow", "tenki_heading"]


# ---------------------------------------------------------------- ページ

def build_home(listed, ctx):
    new_items = sorted(ctx["new_items"], key=lambda it: (it["added"], -it["rank"]), reverse=True)
    # 入口の件数：大きな数字で出し、読み込むと0から数え上げる（site.js）。
    # 転機の件数は、その転機として載せているものだけ（どの転機にも役立つ「全般」の掲載は「全般」の件数に入れ、各転機には足さない）
    num = lambda n: '<b class="chip-num" data-count="%d">%d</b>' % (n, n)
    tenki_links = "".join(
        '<li><a href="%s">%s%s%s</a></li>' % (tenki_url(t), emoji(t.get("emoji", "")), e(t["name"]), num(sum(1 for it in listed if t["name"] in it["tenki"])))
        for t in TENKI if t["past"] and ctx["tenki_count"][t["name"]])
    common_t = next((t for t in TENKI if t["name"] == COMMON), None)
    if common_t and ctx["tenki_count"][COMMON]:
        tenki_links += '<li><a href="%s">全般%s</a></li>' % (tenki_url(common_t), num(ctx["tenki_count"][COMMON]))
    kind_links = "".join(
        '<li><a href="%s">%s%s%s</a></li>' % (e(search_url(kind=k)), kind_emoji(k), e(k), num(len(g)))
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
  <div class="hero-ruler" aria-hidden="true"></div>
  <p class="hero-count"><b data-count="{count}">{count}</b>件を掲載<span>毎日更新</span></p>
  <p class="lead">{lead}</p>
  {ai_check}
  <form class="search-box" action="/search/" method="get" role="search">
    <label for="home-q" class="visually-hidden">キーワード</label>
    <input id="home-q" type="search" name="q" placeholder="キーワードで探す（例：フリーランス、確定申告）">
    <button type="submit">探す</button>
  </form>
  <div class="start-help">
    <div class="start-words" data-shown="8" role="group" aria-label="検索の例">{popular}</div>
  </div>
</section>

<section class="entrances">
  <div class="entrance">
    <h2>{e_tenki}転機から探す</h2>
    <ul class="chips">{tenki_links}</ul>
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
""".format(e_tenki=emoji(CONF.get("entrance_emoji", {}).get("転機")), e_kind=emoji(CONF.get("entrance_emoji", {}).get("タイプ")), site=e(CONF["site_name"]), lead=e(CONF["lead"]), count=len(listed), tenki_links=tenki_links,
           ai_check='<p class="check-link">%s</p>' % ai_link(TENKI_AI, "転機AIに相談する", "home") if TENKI_AI else "",
           kind_links=kind_links, news=news,
           news_more=("観測レポートで今週の新着をすべて見る（%d件）" % len(new_items)) if len(new_items) > 6 else "観測レポートを見る",
           kinds=kind_shelves(listed, ctx),
           popular=start_words_html(popular_words(listed, ctx), "/search/?q="))
    website = {"@context": "https://schema.org", "@type": "WebSite", "name": CONF["site_name"], "url": BASE + "/",
               "description": CONF["description"], "inLanguage": "ja",
               "publisher": {"@type": "Person", "name": "黒田悠介", "jobTitle": "キャリア研究家",
                             "url": CONF.get("operator_url", BASE + "/about/"), "sameAs": [CONF["operator_url"]] if CONF.get("operator_url") else []},
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
        tn = notes_for_tenki(ctx["notes"], t["name"])
        if tn:
            main += '<section class="section note-section"><h2 class="section-title">%sについての%s</h2>%s</section>' % (e(t["name"]), NOTES_LABEL, note_list(tn, None, "note-list note-grid"))
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


def related_choices(item, listed, ctx, per=3, max_kinds=6):
    """紹介ページの下の「あわせて見たいもの」。同じ転機・段階の掲載を、手段（タイプ）ごとに選べる形で出す。
    いちばん左は同じタイプの「似た○○を比べる」、続けてほかのタイプをおすすめ順でいちばん上の掲載が上位のものから。
    JavaScript が使えるときはボタンで切り替え、使えないときは全部を見出し付きで並べる。"""
    pool = [o for o in listed if o["id"] != item["id"] and set(o["tenki"]) & set(item["tenki"]) and set(o["stages"]) & set(item["stages"])]
    if not pool:
        return ""
    pool.sort(key=lambda o: o["rank"])
    groups = collections.OrderedDict()
    for o in pool:
        groups.setdefault(o["kind"], []).append(o)
    tenki_param = next((t for t in item["tenki"] if t not in (COMMON, OTHER)), item["tenki"][0] if item["tenki"] else "")
    stage_param = item["stages"][0] if item["stages"] else ""
    panels = []  # (ボタンの文字, パネルの見出し, 掲載, 一覧へのリンク)
    if item["kind"] in groups:
        group = groups.pop(item["kind"])
        phrase = KIND_PHRASE.get(item["kind"], item["kind"])
        panels.append(("%s 似た%sを比べる" % (KIND_BY_NAME.get(item["kind"], {}).get("emoji", ""), phrase), "似た%s" % phrase, group,
                       search_url(tenki=tenki_param, stage=stage_param, kind=item["kind"])))
    for kind, group in list(groups.items())[:max_kinds]:
        panels.append(("%s %s" % (KIND_BY_NAME.get(kind, {}).get("emoji", ""), KIND_ACTION.get(kind, kind)), KIND_ACTION.get(kind, kind), group,
                       search_url(tenki=tenki_param, stage=stage_param, kind=kind)))
    where = "%s×%s" % (tenki_param, stage_param) if tenki_param and stage_param else (tenki_param or stage_param)
    tabs = "".join('<button type="button" aria-pressed="%s" data-panel="%d">%s</button>' % ("true" if i == 0 else "false", i, e(label.strip()))
                   for i, (label, _, _, _) in enumerate(panels))
    bodies = "".join(
        '<div class="related-panel" data-panel="%d"><h3 class="related-h">%s</h3>%s%s</div>'
        % (i, e(head), sm_shelf("".join(card(it, ctx["today"]) for it in group[:per]), min(per, len(group)), head),
           more_link(href, "%sの「%s」をすべて見る（%d件）" % (where, group[0]["kind"], len(group))) if len(group) > per else "")
        for i, (_, head, group, href) in enumerate(panels))
    tab_html = '<div class="kind-tabs related-tabs" role="group" aria-label="手段を選ぶ">%s</div>' % tabs if len(panels) > 1 else ""
    lead = "%sの時期に役立つものを、手段ごとに選べます。" % ("%sの%s" % (tenki_param, stage_param) if tenki_param and stage_param else where)
    return ('<section class="section related related-choices"><p class="related-kicker">あわせて見たいもの</p>'
            '<h2 class="related-title">次はどの手で進める？</h2><p class="related-lead">%s</p>%s%s</section>' % (e(lead), tab_html, bodies))


def pick_box(item, listed, ctx):
    """紹介ページの下の「ほかの情報をチェック」（2026-11-07 黒田さんが見本の案1を選んだ。コミュニティ図鑑の「ほかの事例をひく」と同じ形）。
    最初の1件はサイトを作るときに選んで書き込んでおく（掲載ごと・日ごとに変わる。開くたびに一覧を読まずに済む）。
    「もう1件めくる」を押すと、/search.json から掲載中の1件をランダムにめくる（site.js）。ボタンは JavaScript が使えるときだけ出す。"""
    others = [it for it in listed if it["id"] != item["id"]]
    if not others:
        return ""
    first = random.Random("%s-%s" % (item["id"], ctx["today"].isoformat())).choice(others)
    return ('<section class="pick-box" id="pick-box" data-id="%s" data-first="%s"><div class="pick-text">'
            '<h2><span aria-hidden="true">🎲</span>ほかの情報をチェック</h2>'
            '<p>観測所の全体からランダムに1件めくります。思いがけない情報に出会えるかもしれません。</p>'
            '<button type="button" class="pick-button" id="pick-button" data-goatcounter-click="pick" hidden>'
            '<span aria-hidden="true">🎲</span><span id="pick-label">もう1件めくる</span></button></div>'
            '<ul class="cards pick-card" id="pick-card" aria-live="polite">%s</ul></section>'
            % (e(item["id"]), e(first["id"]), card(first, ctx["today"])))


# 「あわせて見たいもの」のボタンの言葉（タイプごと）
KIND_ACTION = {"相談": "相談してみる", "仕事": "仕事を探す", "学習": "学んでみる", "内省": "自分を見つめる", "実務": "手続きを知る",
               "交流": "仲間と話す", "書籍": "本で考える", "媒体": "話を聞く", "調査": "データで知る"}


def build_item(item, listed, ctx):
    def links(names, lookup, make, labels=None):
        out = []
        for n in names:
            label = (labels or {}).get(n, n)
            out.append('<a href="%s">%s</a>' % (e(make(n)), e(label)) if n in lookup else e(label))
        return "、".join(out) or "―"

    similar_html = related_choices(item, listed, ctx) + pick_box(item, listed, ctx)

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
{note_band}{voice_band}{similar}
""".format(crumbs=crumbs, note_band=note_band(item, listed, ctx), voice_band=voice_band(item, ctx), title=e(item["title"]), similar=similar_html)
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
    if TENKI_AI:
        official += ('<p class="ai-consult">%s<span class="ai-note">Claudeにログインすると、AIが相談に乗ります（無料プランでも利用可）。</span></p>'
                     % ai_link("%s#%s" % (TENKI_AI, item["id"]), "この情報が自分に合うか、転機AIに相談する", "item/" + item["id"]))
    tenki_links = links(item["tenki"], TENKI_BY_NAME, lambda n: tenki_url(TENKI_BY_NAME[n]), {COMMON: "どの転機にも", OTHER: "そのほか"})
    stage_links = links(item["stages"], STAGE_BY_NAME, lambda n: search_url(stage=n))
    body = """
{crumbs}
<article class="detail">
  {hero}{credit}
  <h1>{title}</h1>
  <div class="detail-side">
  <div class="memo"><h2 class="visually-hidden">観測メモ</h2><p>{memo}</p></div>
  {official}
  <div class="helpful" data-id="{id}" data-title="{title}" hidden>
    <p class="helpful-q">この紹介は役に立ちましたか？</p>
    <div class="helpful-btns"><button type="button" class="button button-ghost" data-helpful="yes">👍 役に立った</button><button type="button" class="button button-ghost" data-helpful="no">👎 いまひとつ</button></div>
    <p class="helpful-thanks" hidden>ありがとうございます。観測所の見直しに使います。</p>
  </div>
  {report}
  </div>
  <dl class="facts">
    <div><dt>タイプ</dt><dd><a href="{kind_url}">{kind}</a></dd></div>
    <div><dt>転機</dt><dd>{tenki}</dd></div>
    <div><dt>段階</dt><dd>{stages}</dd></div>
    <div><dt>{provider_label}</dt><dd>{provider}</dd></div>
  </dl>
</article>
{note_band}{voice_band}{similar}
""".format(crumbs=crumbs, note_band=note_band(item, listed, ctx), voice_band=voice_band(item, ctx), kind_url=e(search_url(kind=item["kind"])), kind=e(item["kind"]), title=e(item["title"]),
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


SHOWN_WORDS = 8  # 「こんな言葉で探せます」に一度に出す数


def popular_words(listed, ctx):
    """「こんな言葉で探せます」の言葉（config/site.json の start_words。掲載データで件数を確かめて選んだ言葉と、実際に検索された言葉）。
    ページにはすべて書き出し、開くたびに site.js がランダムに8つを選んで出す。JavaScript が使えないときに出る最初の8つは、日付ごとに入れ替える。"""
    import random
    words = list(dict.fromkeys(CONF.get("start_words", [])))
    random.Random(ctx["today"].toordinal()).shuffle(words)
    return words


def start_words_html(words, href):
    """言葉のボタン。9つ目以降は隠しておき、site.js がランダムに入れ替える"""
    return "".join('<a class="start-word" href="%s%s"%s>%s</a>' % (href, e(quote(w)), " hidden" if i >= SHOWN_WORDS else "", e(w))
                   for i, w in enumerate(words))


def ai_help_html():
    """探すページの転機AIへの案内。結果が少ないとき（data-few の件数以下）は囲みで、多いときは一番下に1行で出す（search.js が切り替える）。"""
    if not TENKI_AI:
        return ""
    return ('<aside id="ai-help" class="ai-help" data-few="5" hidden>'
            '<p class="ai-help-title">うまく見つからないときは</p>'
            '<p class="ai-help-text">いまの状況を話すと、転機AIが合いそうな情報を一緒に探します。</p>'
            '%s</aside>'
            '<p id="ai-line" class="ai-line" hidden>%s</p>'
            % (ai_link(TENKI_AI, "転機AIに相談する", "search-few", "button button-ghost"),
               ai_link(TENKI_AI, "見つからないときは、転機AIに相談する", "search")))


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
    <div class="start-words" data-shown="8" role="group" aria-label="検索の例">{popular}</div>
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
        <div class="bar-count">
          <p id="result-count" aria-live="polite">読み込み中…</p>
          <div class="view-switch" role="group" aria-label="表示の切り替え"><button type="button" data-view="card" aria-pressed="true" title="カードで表示" aria-label="カードで表示"><svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><rect x="1.5" y="1.5" width="5.5" height="5.5" rx="1.2"/><rect x="9" y="1.5" width="5.5" height="5.5" rx="1.2"/><rect x="1.5" y="9" width="5.5" height="5.5" rx="1.2"/><rect x="9" y="9" width="5.5" height="5.5" rx="1.2"/></svg></button><button type="button" data-view="list" aria-pressed="false" title="一覧で表示" aria-label="一覧で表示"><svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><rect x="1.5" y="2" width="4" height="3.2" rx=".8"/><rect x="7" y="2.6" width="7.5" height="2" rx="1"/><rect x="1.5" y="6.4" width="4" height="3.2" rx=".8"/><rect x="7" y="7" width="7.5" height="2" rx="1"/><rect x="1.5" y="10.8" width="4" height="3.2" rx=".8"/><rect x="7" y="11.4" width="7.5" height="2" rx="1"/></svg></button></div>
        </div>
        <button type="button" class="bar-filter" id="bar-filter" aria-controls="filter-panel" aria-expanded="false">絞り込む</button>
        <div class="sort-field"><label for="sort">並び順</label><select id="sort" name="sort"><option value="">おすすめ順</option><option value="new">新着順</option></select></div>
      </div>
      <div id="active-chips" class="active-chips" hidden></div>
      <p id="syn-note" class="syn-note" hidden></p>
      <ul id="results" class="cards list-compact"></ul>
      <p class="more-wrap"><button type="button" id="more" class="button" hidden>もっと見る</button></p>
      {ai_help}
    </div>
  </div>
</form>
<noscript><p class="note">検索にはJavaScriptを使います。使えない場合は<a href="/tenki/">転機から探す</a>をご利用ください。</p></noscript>
<script>window.TENKI_PAGE_SIZE = {page_size}; window.TENKI_THIS_YEAR = {year}; window.TENKI_POPULAR = {popular_json};</script>
<script src="/assets/search.js?v={ver}" defer></script>
""".format(crumbs=breadcrumb([("探す", None)]), kinds=chip_group("kind", "タイプ", kinds_of(listed)),
           tenki=chip_group("tenki", "転機", [t["name"] for t in TENKI], {COMMON: "どの転機にも", OTHER: "そのほか"}),
           stages=chip_group("stage", "段階", [s["name"] for s in STAGES]),
           popular=start_words_html(words, "?q="),
           popular_json=json.dumps(words, ensure_ascii=False),
           ai_help=ai_help_html(), page_size=int(CONF["list_page_size"]), year=ctx["today"].year, ver=ctx["version"])
    page("/search/", "探す", "キャリアの転機に役立つサービスと情報を、転機・段階・タイプで絞り込み、キーワードで検索できます。", body, ctx=ctx)


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
<p>送っているのは、見たページ、どこから来たか（検索エンジンやSNSなど）、ブラウザや画面の大きさといった大まかな情報です。探すページで入力されたキーワードも送ります（入力の途中ではなく、手を止めたときの言葉だけ）。メールアドレスや電話番号、URLのような言葉は送りません。「こんな言葉で探せます」に出す言葉を選んだり、言い換え表を見直したり、掲載するものを探したりするのに使います。</p>
<p>紹介ページで「公式サイトを見る」「あとで見る」「共有」と、「この紹介は役に立ちましたか？」のボタンが押されたときは、どの掲載で押されたか（掲載のIDとタイトル）を数えます。役に立った掲載を知り、掲載するものや並び順を見直すのに使います。</p>
<p>転機AIへのリンクが押されたときは、どのページのリンクから移ったか（メニュー、トップ、探す、紹介ページのどれか。紹介ページなら掲載のID）を数えます。</p>
<p>「あしたの転機」のページから外のページ（note、Facebookグループ、Podcast など）へ移ったときは、移った先のサイト名だけを数えます。</p>
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
<p>広く知られた定番か、転機との近さ、情報の新しさ、無料で試せるかをもとに並べています。評価が近いものの中では、一覧を見やすくするため、公式ページの画像を表示できるものを先にしています。また、同じ転機や同じ提供元のものが続きすぎないように並べています。掲載依頼や広告で順番を変えることはありません。</p>

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

<h2 id="takedown">掲載されている方へ</h2>
<p>観測所は、公開されている情報をもとに、サービスや情報を紹介しています。内容の訂正や、掲載の取り下げをご希望の場合は、<a href="{contact}" rel="noopener" target="_blank">観測所へのご連絡</a>からお知らせください。紹介ページの「この情報の誤りを知らせる」からも開けます。</p>
<p>いただいたご連絡は、公式の情報と照らして確かめたうえで、訂正または取り下げを行います。画像だけを外すこともできます。取り下げた掲載は、サイトの毎日の更新で一覧と紹介ページから外れます。</p>

{analytics}
<h2>運営者</h2>
<div class="operator-card">
  <p class="operator-name"><strong>黒田悠介</strong><span>キャリア研究家</span></p>
  <p>これまでに1,000人以上のキャリア相談を受けてきました。著書に『ライフピボット』などがあります。この観測所のほか、転機について考えるnoteマガジンやコミュニティも運営しています。</p>
  <p>キャリアの転機についての相談（キャリア相談）も受けています。ご相談は、下のリンク集にある連絡先からお寄せください。</p>
  <p class="operator-link"><a class="button" href="{operator_url}" rel="noopener" target="_blank" data-goatcounter-click="contact-operator/about">黒田悠介のリンク集を見る</a><span>連絡先や、ほかの活動・発信をまとめています</span></p>
</div>

<h2>あしたの転機プロジェクトについて</h2>
<p>「あしたの転機プロジェクト」は、あしたやってくるかもしれない人生の転機について、これからの時代の働き方や生き方をテーマに考えていくプロジェクトです。この観測所はその一部として運営しています。コミュニティ、noteマガジン、イベントなどは、<a href="/project/">あしたの転機プロジェクトのページ</a>にまとめています。</p>
</article>
""".format(crumbs=breadcrumb([("観測所について", None)]), stage_dl=stage_dl,
           contact=e(CONF["contact_form_url"]),
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
