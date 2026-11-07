#!/usr/bin/env python3
"""作ったサイト（_site）を点検するスクリプト（毎朝の自動更新で、公開の前に使う）。

  python3 tools/check_site.py [report.md]

- 確かめること：サイト内のリンク・画像・読み込むファイルの行き先があるか、ページに title と h1 が1つずつあるか、
  見出しの段が飛んでいないか（h2 の次がいきなり h4 など）、画像に alt があるか、同じ id が1ページに2つないか。
- 外のサイトは開かない（それは毎週のリンク点検の担当）。
- 問題があれば report.md を書く（引数で指定したとき）。公開は止めない。終了コードはいつも0。
"""
import collections
import html.parser
import os
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "_site")
MAX_SHOW = 30  # 種類ごとに報告に載せる例の数


class Page(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.refs, self.headings, self.ids, self.no_alt = [], [], [], 0
        self.titles = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self.titles += 1
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.headings.append(int(tag[1]))
        if a.get("id"):
            self.ids.append(a["id"])
        if tag == "a" and a.get("href"):
            self.refs.append(a["href"])
        if tag in ("img", "script", "source") and a.get("src"):
            self.refs.append(a["src"])
        if tag == "link" and a.get("href") and a.get("rel") in ("stylesheet", "icon", "apple-touch-icon", "manifest", "alternate", "preload"):
            self.refs.append(a["href"])
        if tag == "img" and "alt" not in a:
            self.no_alt += 1


def target(page_path, ref):
    """サイト内の参照なら、_site の中のファイルの場所を返す。外や対象外は None。"""
    u = urllib.parse.urlsplit(ref)
    if u.scheme or u.netloc or ref.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        if u.netloc == "ashitano-tenki.github.io":
            u = urllib.parse.urlsplit(u.path)
        else:
            return None
    path = urllib.parse.unquote(u.path)
    if not path:
        return None
    if not path.startswith("/"):
        path = "/" + os.path.relpath(os.path.join(os.path.dirname(page_path), path), SITE).replace(os.sep, "/")
    full = os.path.normpath(os.path.join(SITE, path.lstrip("/")))
    if path.endswith("/") or os.path.isdir(full):
        full = os.path.join(full, "index.html")
    return full


def main():
    report_path = sys.argv[1] if len(sys.argv) > 1 else None
    problems = collections.defaultdict(list)
    pages = 0
    for dirpath, _, files in os.walk(SITE):
        for name in files:
            if not name.endswith(".html"):
                continue
            path = os.path.join(dirpath, name)
            rel = "/" + os.path.relpath(path, SITE).replace(os.sep, "/").replace("index.html", "")
            pages += 1
            p = Page()
            with open(path, encoding="utf-8") as f:
                p.feed(f.read())
            for ref in dict.fromkeys(p.refs):
                t = target(path, ref)
                if t and not os.path.exists(t):
                    problems["行き先のないサイト内リンク・画像"].append("%s → %s" % (rel, ref))
            if p.titles != 1:
                problems["title が1つでないページ"].append("%s（%d個）" % (rel, p.titles))
            h1 = p.headings.count(1)
            # セルフチェック（/check/）は見出しをスクリプトで書き出すので、h1 の数は数えない
            if h1 != 1 and name != "404.html" and not rel.startswith("/check/"):
                problems["h1 が1つでないページ"].append("%s（%d個）" % (rel, h1))
            for a, b in zip(p.headings, p.headings[1:]):
                if b > a + 1:
                    problems["見出しの段が飛んでいるページ"].append("%s（h%d の次が h%d）" % (rel, a, b))
                    break
            dup = [i for i, n in collections.Counter(p.ids).items() if n > 1]
            if dup:
                problems["同じ id が2つ以上あるページ"].append("%s（%s）" % (rel, "、".join(dup[:5])))
            if p.no_alt:
                problems["alt のない画像があるページ"].append("%s（%d枚）" % (rel, p.no_alt))

    total = sum(len(v) for v in problems.values())
    print("サイトの点検：%dページ、問題 %d件" % (pages, total) + "".join("\n  %s %d件" % (k, len(v)) for k, v in problems.items()))
    if report_path and total:
        lines = ["毎朝の自動更新で、作ったサイト（%dページ）を点検しました。問題が %d件ありました。サイトの公開は止めていません。" % (pages, total), ""]
        for kind, rows in problems.items():
            lines += ["## %s（%d件）" % (kind, len(rows)), ""]
            lines += ["- " + r for r in rows[:MAX_SHOW]]
            if len(rows) > MAX_SHOW:
                lines.append("- ほか %d件" % (len(rows) - MAX_SHOW))
            lines.append("")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


if __name__ == "__main__":
    main()
