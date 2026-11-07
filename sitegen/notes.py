"""観測ノート（/notes/）。原稿は notes/<スラッグ>.md。"""
import datetime
import json
import os
import re
import sys
from sitegen.core import BASE, CONF, KIND_BY_NAME, NOTES_DIR, NOTES_LABEL, TENKI_BY_NAME, parse_date, split_list
from sitegen.parts import breadcrumb, e, fmt_date, item_media, kind_emoji, og_image, page, tenki_url, write

__all__ = ["build_notes", "load_notes", "note_band", "note_blocks", "note_data", "note_emoji", "note_html", "note_inline", "note_list", "note_meta_line", "note_pick", "note_plain", "note_strip", "note_url", "notes_for_item", "notes_for_tenki", "parse_note_file", "write_notes_json"]


def parse_note_file(path):
    with open(path, encoding="utf-8") as f:
        text = f.read().replace("\r\n", "\n")
    meta, body = {}, text
    if text.startswith("---\n"):
        head, _, body = text[4:].partition("\n---\n")
        for line in head.split("\n"):
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
    slug = os.path.splitext(os.path.basename(path))[0]
    return {"slug": slug, "title": meta.get("title", slug), "description": meta.get("description", ""),
            "tenki": split_list(meta.get("tenki", "")), "stage": meta.get("stage", ""),
            "published": parse_date(meta.get("published", "")), "updated": parse_date(meta.get("updated", "")),
            "draft": meta.get("draft", "").lower() in ("true", "yes", "1"), "body": body,
            "ids": re.findall(r"^:::item\s+(\S+)", body, re.M)}


def load_notes(listed, with_drafts):
    """公開する観測ノート（新しい順）。掲載を終えた・見つからない掲載を差し込んでいたら知らせる。"""
    if not os.path.isdir(NOTES_DIR):
        return []
    ids = {it["id"] for it in listed}
    notes = []
    for name in sorted(os.listdir(NOTES_DIR)):
        if not name.endswith(".md") or name.startswith("_"):
            continue
        n = parse_note_file(os.path.join(NOTES_DIR, name))
        if n["draft"] and not with_drafts:
            continue
        if not n["published"] and not n["draft"]:
            print("注意: 観測ノート %s に published（公開日）がないので公開しません" % name, file=sys.stderr)
            continue
        for i in n["ids"]:
            if i not in ids:
                print("注意: 観測ノート %s の掲載 %s は掲載中ではないので、記事から外して表示します" % (name, i), file=sys.stderr)
        notes.append(n)
    notes.sort(key=lambda n: (n["published"] or datetime.date.max), reverse=True)
    return notes


def note_url(n):
    return "/notes/%s/" % n["slug"]


def note_inline(text):
    """1行ぶんの文字をHTMLにする（リンクと強調だけ）。"""
    out, pos = [], 0
    for m in re.finditer(r"\[([^\]]+)\]\(([^)\s]+)\)|\*\*(.+?)\*\*", text):
        out.append(e(text[pos:m.start()]))
        if m.group(1):
            href = m.group(2)
            ext = href.startswith("http")
            out.append('<a href="%s"%s>%s</a>' % (e(href), ' rel="noopener" target="_blank"' if ext else "", e(m.group(1))))
        else:
            out.append("<strong>%s</strong>" % e(m.group(3)))
        pos = m.end()
    out.append(e(text[pos:]))
    return "".join(out)


def note_blocks(text):
    """段落・見出し・箇条書きをHTMLにする。"""
    html_out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [l for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        if lines[0].startswith("### "):
            html_out.append("<h3>%s</h3>" % note_inline(lines[0][4:].strip()))
            lines = lines[1:]
        elif lines[0].startswith("## "):
            title = lines[0][3:].strip()
            html_out.append("<h2>%s</h2>" % note_inline(title))
            lines = lines[1:]
        if not lines:
            continue
        if all(l.startswith("- ") for l in lines):
            html_out.append("<ul>%s</ul>" % "".join("<li>%s</li>" % note_inline(l[2:].strip()) for l in lines))
        else:
            html_out.append("<p>%s</p>" % "<br>".join(note_inline(l.strip()) for l in lines))
    return "".join(html_out)


def note_pick(item, comment_html, num=0):
    link_label = KIND_BY_NAME.get(item["kind"], {}).get("link", "公式サイトを見る")
    official = ('<a href="%s" rel="noopener" target="_blank">%s</a>' % (e(item["url"]), e(link_label))) if item["url"] else ""
    return ('<section class="note-pick" id="pick-%s"><span class="note-pick-num" aria-hidden="true">%02d</span><a class="note-pick-head linkcard" href="/item/%s/">%s<span class="note-pick-body">'
            '<span class="note-pick-kind">%s %s</span><span class="note-pick-title">%s</span><span class="note-pick-line">%s</span></span></a>'
            '%s<p class="note-pick-links"><a href="/item/%s/">紹介ページを見る</a>%s</p></section>'
            % (e(item["id"]), num, e(item["id"]), item_media(item, "note-pick-media", True), kind_emoji(item["kind"]), e(item["kind"]), e(item["title"]), e(item["line"]),
               '<div class="note-pick-comment"><p class="note-pick-who">黒田のひとこと</p>%s</div>' % comment_html if comment_html else "",
               e(item["id"]), "・" + official if official else ""))


def note_html(n, by_id):
    """本文全体。:::item のかたまりは掲載のカードにする。"""
    parts = re.split(r"^:::item\s+(\S+)\s*\n(.*?)^:::\s*$", n["body"], flags=re.M | re.S)
    out = [note_blocks(parts[0])]
    num = 0
    for i in range(1, len(parts), 3):
        item = by_id.get(parts[i])
        if item:
            num += 1
            out.append(note_pick(item, note_blocks(parts[i + 1]), num))
        out.append(note_blocks(parts[i + 2]))
    return "".join(out)


def note_meta_line(n):
    bits = []
    if n["published"]:
        bits.append('<time datetime="%s">%s</time>公開' % (n["published"].isoformat(), fmt_date(n["published"])))
    if n["updated"] and n["updated"] != n["published"]:
        bits.append('<time datetime="%s">%s</time>更新' % (n["updated"].isoformat(), fmt_date(n["updated"])))
    return "・".join(bits)


def note_emoji(n):
    t = next((TENKI_BY_NAME[t] for t in n["tenki"] if t in TENKI_BY_NAME), None)
    return t.get("emoji", "") if t else ""


def note_list(notes, by_id=None, cls="note-list"):
    """記事のカード。上に記事ごとの共有画像、下に題名と説明、紹介している数。"""
    def li(n):
        count = len([i for i in n["ids"] if by_id is None or i in by_id])
        meta = "・".join(x for x in [e("・".join(n["tenki"])), "%d件を紹介" % count if count else "", fmt_date(n["published"]) if n["published"] else ""] if x)
        return ('<li><a href="%s"><span class="note-card-img"><img src="%s" alt="" loading="lazy" width="1200" height="630"></span>'
                '<span class="note-card-body"><span class="note-list-title">%s</span><span class="note-list-desc">%s</span>'
                '<span class="note-card-meta">%s</span></span></a></li>'
                % (e(note_url(n)), e(og_image("note-" + n["slug"])), e(n["title"]), e(n["description"]), meta))
    return '<ul class="%s">%s</ul>' % (cls, "".join(li(n) for n in notes))


def note_strip(n, by_id):
    """記事の頭に置く「この記事で紹介するもの」。小さな画像を並べ、押すとその紹介へ移る。"""
    items = [by_id[i] for i in n["ids"] if i in by_id]
    if not items:
        return ""
    return ('<nav class="note-strip" aria-label="この記事で紹介するもの"><p class="note-strip-head">この記事で紹介する<b>%d</b>件</p><ol>%s</ol></nav>'
            % (len(items), "".join('<li><a href="#pick-%s" title="%s">%s<span>%s</span></a></li>'
                                   % (e(it["id"]), e(it["title"]), item_media(it, "note-strip-media", True), e(it["title"])) for it in items)))


def note_band(item, listed, ctx):
    """紹介ページの枠の下に置く帯。この掲載を紹介した観測ノートを、シェア画像と紹介している掲載の画像で見せる。"""
    notes = notes_for_item(ctx["notes"], item["id"])
    if not notes:
        return ""
    by_id = ctx.get("_listed_by_id")
    if by_id is None:
        by_id = ctx["_listed_by_id"] = {it["id"]: it for it in listed}
    out = []
    for n in notes:
        items = [by_id[i] for i in n["ids"] if i in by_id]
        thumbs = "".join('<li%s><a href="/item/%s/" title="%s"%s>%s<span class="visually-hidden">%s</span></a></li>'
                         % (' class="is-here"' if it["id"] == item["id"] else "", e(it["id"]), e(it["title"]),
                            ' aria-current="page"' if it["id"] == item["id"] else "", item_media(it, "note-band-media", True), e(it["title"]))
                         for it in items)
        out.append('<section class="note-band"><a class="note-band-img" href="%s" tabindex="-1" aria-hidden="true">'
                   '<img src="%s" alt="" width="1200" height="630" loading="lazy"></a><div class="note-band-body">'
                   '<p class="note-band-kicker">この掲載が出てくる%s</p><h2 class="note-band-title"><a href="%s">%s</a></h2>'
                   '<p class="note-band-lead">%s</p>%s<a class="note-band-btn" href="%s">記事を読む</a></div></section>'
                   % (e(note_url(n)), e(og_image("note-" + n["slug"])), NOTES_LABEL, e(note_url(n)), e(n["title"]), e(n["description"]),
                      '<ol class="note-band-items">%s</ol><p class="note-band-cap">記事で紹介している%d件（枠がこのページ）</p>' % (thumbs, len(items)) if items else "",
                      e(note_url(n))))
    return "\n".join(out) + "\n"


def notes_for_tenki(notes, name):
    return [n for n in notes if name in n["tenki"]]


def notes_for_item(notes, item_id):
    return [n for n in notes if item_id in n["ids"]]


def build_notes(notes, listed, ctx):
    if not notes:
        return
    by_id = {it["id"]: it for it in listed}
    operator = CONF.get("operator_url", "")
    for n in notes:
        tenki_links = "、".join('<a href="%s">%s</a>' % (e(tenki_url(TENKI_BY_NAME[t])), e(t)) for t in n["tenki"] if t in TENKI_BY_NAME)
        others = [o for o in notes if o is not n and set(o["tenki"]) & set(n["tenki"])][:4]
        more = ""
        if others:
            more += '<h2>ほかの観測ノート</h2>' + note_list(others, by_id)
        body = """
{crumbs}
<header class="note-hero">
  <span class="note-hero-emoji" aria-hidden="true">{emoji}</span>
  <p class="note-kicker">{label}{tenki}</p>
  <h1>{title}</h1>
  <p class="note-by">文：<a href="{operator}" rel="noopener" target="_blank">黒田悠介</a>（キャリア研究家）<span class="note-date">{date}</span></p>
</header>
<article class="prose note">
{strip}
{main}
<div class="note-end">
  <p>掲載しているサービスや本の内容は変わることがあります。使う前に、公式サイトで最新の情報を確かめてください。</p>
  {tenki_more}
</div>
{more}
</article>
""".format(crumbs=breadcrumb([(NOTES_LABEL, "/notes/"), (n["title"], None)]), label=e(NOTES_LABEL),
           tenki="｜" + "・".join(e(t) for t in n["tenki"]) if n["tenki"] else "",
           # 「。」と「、」のところで区切り、言葉の途中で折り返さないようにする
           title="".join("<span>%s</span>" % e(x) for x in re.findall(r"[^。、]+[。、]?", n["title"])),
           operator=e(operator), date=note_meta_line(n), main=note_html(n, by_id), emoji=note_emoji(n), strip=note_strip(n, by_id),
           tenki_more='<p>%sのサービスと情報は、%sのページにまとめています。</p>' % ("・".join(e(t) for t in n["tenki"]), tenki_links) if tenki_links else "",
           more=more)
        ld = {"@context": "https://schema.org", "@type": "Article", "headline": n["title"], "description": n["description"],
              "inLanguage": "ja", "url": BASE + note_url(n),
              "author": {"@type": "Person", "name": "黒田悠介", "jobTitle": "キャリア研究家", "url": operator},
              "publisher": {"@type": "Organization", "name": CONF["site_name"], "url": BASE + "/"}}
        if n["published"]:
            ld["datePublished"] = n["published"].isoformat()
        ld["dateModified"] = (n["updated"] or n["published"] or ctx["today"]).isoformat()
        page(note_url(n), n["title"], n["description"], body, ctx=ctx, noindex=n["draft"], jsonld=[ld],
             image=og_image("note-" + n["slug"]), lastmod=n["updated"] or n["published"])
    public = [n for n in notes if not n["draft"]]
    if public:
        body = """
{crumbs}
<header class="note-hero note-hero-index">
  <span class="note-hero-emoji" aria-hidden="true">📓</span>
  <h1>{label}</h1>
  <p class="note-hero-lead"><span>転機ごとのよくある迷いと、</span><span>そのときに役立つサービスや本を、</span><span>キャリア研究家の黒田悠介が</span><span>まとめた記事です。</span></p>
  <p class="note-hero-count"><b>{count}</b>本の記事</p>
</header>
<section class="section">{list}</section>
""".format(crumbs=breadcrumb([(NOTES_LABEL, None)]), label=e(NOTES_LABEL), list=note_list(public, by_id, "note-list note-grid"), count=len(public))
        page("/notes/", NOTES_LABEL, "転機ごとのよくある迷いと、そのときに役立つサービスや本を、キャリア研究家の黒田悠介がまとめた記事です。", body, ctx=ctx,
             extra_head='<link rel="alternate" type="application/json" href="/notes/index.json" title="%s（JSON）">\n' % e(NOTES_LABEL))
    write_notes_json(public, by_id, ctx)


def note_plain(text):
    """ノートの1行を、リンクと強調の記号を外した文字にする。"""
    text = re.sub(r"\[([^\]]+)\]\([^)\s]+\)", r"\1", text)
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text).strip()


def note_data(n, by_id):
    """転機AIなどが読む、ノート1本分のデータ（notes/index.json の1件）。本文と同じ元のファイルから作る。"""
    sections, items, worries, next_steps, related = [], [], [], [], []
    heading, buf = "", []

    def flush():
        text = "\n".join(buf).strip()
        if heading or text:
            sections.append({"heading": heading, "text": text})

    lines = n["body"].replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^:::item\s+(\S+)", line)
        if m:
            words = []
            i += 1
            while i < len(lines) and lines[i].strip() != ":::":
                if lines[i].strip():
                    words.append(note_plain(lines[i]))
                i += 1
            it = by_id.get(m.group(1), {})
            items.append({"id": m.group(1), "title": it.get("title", ""), "kind": it.get("kind", ""),
                          "url": "%s/item/%s/" % (BASE, m.group(1)), "section": heading, "hitokoto": "\n".join(words)})
            i += 1
            continue
        if line.startswith("## "):
            flush()
            heading, buf = note_plain(line[3:]), []
        elif line.startswith("### "):
            buf.append(note_plain(line[4:]))
        else:
            if "迷い" in heading and line.startswith("- "):
                worries.append(note_plain(line[2:]))
            if heading == "次の一歩":
                if line.startswith("- "):
                    next_steps.append(note_plain(line[2:]))
                elif line.strip():
                    next_steps.extend(x + "。" for x in re.split(r"。", note_plain(line)) if x.strip())
                related.extend(BASE + h if h.startswith("/") else h for h in re.findall(r"\]\(([^)\s]+)\)", line))
            buf.append("・" + note_plain(line[2:]) if line.startswith("- ") else note_plain(line))
        i += 1
    flush()
    for sec in sections:
        sec["text"] = re.sub(r"\n{3,}", "\n\n", sec["text"]).strip()
    return {"slug": n["slug"], "url": BASE + note_url(n), "title": n["title"],
            "date": n["published"].isoformat() if n["published"] else "",
            "updated": (n["updated"] or n["published"]).isoformat() if (n["updated"] or n["published"]) else "",
            "author": "黒田悠介", "tenki": n["tenki"], "dankai": split_list(n["stage"]), "lead": n["description"],
            "image": "%s/assets/og/note-%s.png" % (BASE, n["slug"]),
            "worries": worries, "sections": sections, "items": items, "next_steps": next_steps, "related": related}


def write_notes_json(public, by_id, ctx):
    """公開している観測ノートの中身をまとめた /notes/index.json（転機AIが読む）。下書きは入れない。"""
    data = {"updated": ctx["today"].isoformat(), "count": len(public), "notes": [note_data(n, by_id) for n in public]}
    write("/notes/index.json", json.dumps(data, ensure_ascii=False, indent=1) + "\n")
