"""観測ノートの下書きを、スマホでも見られる1枚のHTMLにする（黒田さんに見せる見本用）。

使い方：
  python3 build.py --drafts          # 下書きも含めて _site を作る
  python3 tools/note_preview.py <スラッグ> <出力先.html>

CSSと画像をページの中に埋め込み、サイト内のリンクは本番のURLに向けます。
"""
import base64
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "_site")
BASE = "https://ashitano-tenki.github.io"


def main(slug, out):
    src = os.path.join(SITE, "notes", slug, "index.html")
    with open(src, encoding="utf-8") as f:
        h = f.read()
    with open(os.path.join(SITE, "assets", "style.css"), encoding="utf-8") as f:
        css = f.read()
    h = re.sub(r'<link rel="stylesheet" href="/assets/style\.css[^>]*>', lambda m: "<style>" + css + "</style>", h)

    def img(m):
        path = os.path.join(SITE, m.group(1).split("?")[0].lstrip("/"))
        kind = "png" if path.endswith(".png") else "svg+xml" if path.endswith(".svg") else "webp"
        with open(path, "rb") as f:
            return 'src="data:image/%s;base64,%s"' % (kind, base64.b64encode(f.read()).decode())

    h = re.sub(r'src="(/(?:images|assets)/[^"]+)"', img, h)
    h = re.sub(r'<script src="/assets/[^"]+"></script>', "", h)
    h = re.sub(r"<script data-goatcounter[^>]*></script>", "", h)
    h = re.sub(r'<link rel="(icon|apple-touch-icon|alternate|canonical)"[^>]*>\n?', "", h)
    h = re.sub(r'href="/(?!/)', 'href="%s/' % BASE, h)
    h = h.replace("<body>", '<body><p style="margin:0;padding:10px 16px;background:#f5c518;color:#111;'
                  'font-size:14px;font-weight:700;text-align:center">観測ノートの見本（下書き・まだ公開していません）</p>', 1)
    with open(out, "w", encoding="utf-8") as f:
        f.write(h)
    print("書き出しました: %s（%d文字）" % (out, len(h)))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
