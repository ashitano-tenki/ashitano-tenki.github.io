#!/usr/bin/env python3
"""掲載先の公式ページからシェア用の画像（OGP画像）を取得し、縮小して images/items/ に保存するスクリプト。

  python3 tools/fetch_images.py

- 毎朝の「サイトを更新」で、サイトを作る前に動く。画像の縮小に Pillow を使う（ワークフローで入れる）。
- 取得するのは、まだ画像を確かめていない掲載・取得から30日たったもの・取れなかったもので7日たったものだけ。
  相手のサイトに負担をかけないよう、1回に確かめる数を MAX_PER_RUN までにし、同じドメインには間をあける。
- 本の表紙（URLのISBN、なければ書名から国立国会図書館サーチで引いたISBN）・Spotify・YouTube の動画は、ページを読まずに画像の場所を決める（derived_image_url）。取れなければページを読む。
- 自動の取得を断るページは、同じものを載せた別のページに読み替えて画像を探す（page_for_image。楽天市場の本→楽天ブックス）。
- 結果は data/images.json に書く（ID ごとに、状態・元の画像のURL・大きさ・確かめた日）。
- 画像は2つ、軽い WebP 形式で書き出す：{ID}.webp（紹介ページ用、幅960まで）と {ID}-s.webp（カードの上の画像用、幅600ほど）。
  `--resize-only` を付けると取得はせず、保存してある {ID}.webp からカード用の画像だけを作り直す（大きさを変えたとき用）。
- config/image_overrides.json に「ID: 画像のURL」を書いたものは、公式ページを読まずにそのURLの画像を使う
  （自動で取れない掲載に、黒田さんが手で見つけた画像を渡すとき。URLが変わったら次の回で取り直す）。
  「file:images/manual/R0019.png」のように書いたものは、リポジトリに置いた画像（黒田さんがアップロードしたキャプチャなど）を使う。
- config/site.json の image_exclude に書いたIDは取得せず、保存してある画像も消す（掲載先から申し出があったときなど）。
- 掲載が終わってCSVから消えたIDの画像も消す。スプレッドシートは変えない。
"""
import collections
import concurrent.futures
import csv
import datetime
import html
import io
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import unicodedata
import urllib.request

from PIL import Image, ImageChops, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402  CSVの取得と設定は build.py と同じものを使う

MANIFEST = os.path.join(ROOT, "data", "images.json")
OVERRIDES = os.path.join(ROOT, "config", "image_overrides.json")
IMG_DIR = os.path.join(ROOT, "images", "items")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0.0.0 Safari/537.36")
TIMEOUT = 15
WORKERS = 4
DOMAIN_GAP = 2.0
MAX_PER_RUN = int(os.environ.get("IMAGES_MAX", "60"))  # 1回に確かめる掲載の数（初回などは環境変数で増やせる）
REFRESH_DAYS = 30         # 取れた画像を取り直すまでの日数（画像の差し替えに追いつくため）
RETRY_DAYS = 7            # 取れなかったものを試し直すまでの日数
MAX_BYTES = 8_000_000     # これより大きい画像は使わない
SMALL_MIN_SIDE = 200      # 短い辺がこれより小さい画像は「小さい」として差し替えを頼む
LARGE_W = 960             # 紹介ページ用の幅
CARD_W, CARD_H = 600, 314  # カードの上の画像枠（1.91:1）を高精細の画面でも粗くなく埋められる大きさ
FRAME = 1.91              # カードと紹介ページの画像枠の縦横比
FILL_BELOW = 1.4          # これより縦に近い画像は、左右を足して枠いっぱいにする（build.py の image_info と同じ境目）
# 本の表紙とPodcastのカバーは、左右を足さずに枠の中に収める
COVER_HOSTS = ("kinokuniya.co.jp", "maruzenjunkudo.co.jp", "books.rakuten.co.jp", "item.rakuten.co.jp/book",
               "amazon.co.jp", "amzn.", "booklive.jp", "bookwalker.jp", "ebookjapan.", "diamond.co.jp/book",
               "kadokawa.co.jp/product", "books.bunshun.jp", "shopping.yahoo.co.jp", "netoff.co.jp", "bookoff.co.jp",
               "spotify.com", "podcasts.apple.com", "anchor.fm", "stand.fm", "voicy.jp")

_last = {}
_lock = threading.Lock()


def host_of(url):
    h = (urllib.parse.urlsplit(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def wait_for(host):
    while True:
        with _lock:
            now = time.monotonic()
            if now - _last.get(host, 0) >= DOMAIN_GAP:
                _last[host] = now
                return
        time.sleep(0.3)


def fetch(url, limit):
    wait_for(host_of(url))
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        return res.read(limit), res.geturl(), res.headers


def isbn10_from_13(isbn13):
    core = isbn13[3:12]
    check = (11 - sum((10 - i) * int(d) for i, d in enumerate(core)) % 11) % 11
    return core + ("X" if check == 10 else str(check))


def norm_title(t):
    return re.sub(r"[\s　・、。,.!！?？「」『』（）()［］\[\]〈〉<>:：/／\-－—―~〜]", "", unicodedata.normalize("NFKC", t or "")).lower()


def isbn_from_title(title):
    """本のURLにISBNがないとき（電子書籍のページなど）、国立国会図書館サーチの公開検索で書名からISBNを引く。
    国会図書館の書名は「本題 : 副題」の形で、掲載の書名と順番がちがうことがある。本題・副題のどれもが
    掲載の書名に含まれるものだけを使う（ちがう本の表紙を出さないため）。見つからなければ空文字。
    （2026年10月、紀伊國屋の電子書籍2冊で、黒田さんが書名で探して表紙を渡してくれたのを自動にしたもの）"""
    if not title:
        return ""
    body, _, _ = fetch("https://ndlsearch.ndl.go.jp/api/opensearch?cnt=5&title=" + urllib.parse.quote(title), 500_000)
    text = body.decode("utf-8", "replace")
    want = norm_title(title)
    for item in re.findall(r"<item>(.*?)</item>", text, re.S):
        t = re.search(r"<title>([^<]*)</title>", item)
        isbn = re.search(r'<dc:identifier xsi:type="dcndl:ISBN(?:13)?">([\dX-]+)</dc:identifier>', item)
        parts = [norm_title(x) for x in re.split(r"\s[:：]\s", html.unescape(t.group(1)))] if t else []
        parts = [x for x in parts if len(x) >= 2]
        if isbn and parts and want and all(x in want for x in parts) and len("".join(parts)) >= len(want) * 0.6:
            digits = isbn.group(1).replace("-", "")
            if len(digits) == 13 and digits.startswith("978"):
                return digits
    return ""


def kinokuniya_cover(isbn13):
    isbn10 = isbn10_from_13(isbn13)
    return "https://www.kinokuniya.co.jp/images/goods/ar2/web/imgdata2/large/%s/%s.jpg" % (isbn10[:5], isbn10)


def derived_image_url(page_url, kind="", title=""):
    """ページを読まなくても画像の場所がわかるものは、ここで画像のURLを決める。わからなければ空文字。
    - 本（タイプが「書籍」で、URLにISBN-13がある）：どの書店のページでも、紀伊國屋書店の表紙画像を使う。
      表紙画像はISBN-10から場所が決まる。書店のページの og:image は店のロゴのことが多いので、本は先にこちらを見る
      （2026年10月、丸善ジュンク堂の5冊が店のロゴになっていた）
    - Spotify の番組・エピソードなど：公式の oEmbed が返すカバー画像
    - YouTube の動画：動画のサムネイル（チャンネルのページは og:image があるので通常どおり）"""
    parts = urllib.parse.urlsplit(page_url)
    host = host_of(page_url)
    if kind == "書籍" or host == "kinokuniya.co.jp":
        m = re.search(r"(?<!\d)(978\d{10})(?!\d)", parts.path + "?" + parts.query)
        if m:
            return kinokuniya_cover(m.group(1))
    if kind == "書籍":
        isbn = isbn_from_title(title)  # URLにISBNがない本は、書名からISBNを引く
        if isbn:
            return kinokuniya_cover(isbn)
    if host == "open.spotify.com" and re.match(r"/(show|episode|album|playlist|track|artist)/", parts.path):
        body, _, _ = fetch("https://open.spotify.com/oembed?url=" + urllib.parse.quote(page_url, safe=""), 200_000)
        return json.loads(body.decode("utf-8")).get("thumbnail_url", "")
    if host in ("youtube.com", "m.youtube.com") and parts.path == "/watch":
        vid = urllib.parse.parse_qs(parts.query).get("v", [""])[0]
        if re.fullmatch(r"[\w-]{6,20}", vid):
            return "https://i.ytimg.com/vi/%s/hqdefault.jpg" % vid
    if host == "youtu.be" and re.fullmatch(r"/[\w-]{6,20}", parts.path):
        return "https://i.ytimg.com/vi/%s/hqdefault.jpg" % parts.path[1:]
    return ""


def page_for_image(page_url):
    """画像を探すときに読むページ。自動の取得を断るページは、同じものを載せた別のページに読み替える。
    - 楽天市場の本（item.rakuten.co.jp/book/番号）→ 楽天ブックス（books.rakuten.co.jp/rb/番号）。
      楽天市場は断るが、楽天ブックスは開けて、その本の表紙が og:image にある（2026年10月、R0169・R0170 で確認）"""
    parts = urllib.parse.urlsplit(page_url)
    m = re.fullmatch(r"/book/(\d+)/?", parts.path)
    if host_of(page_url) == "item.rakuten.co.jp" and m:
        return "https://books.rakuten.co.jp/rb/%s/" % m.group(1)
    return page_url


def og_image_url(page_url):
    """ページの og:image（なければ twitter:image）のURLを返す。見つからなければ空文字。
    YouTube のように og:image がページの後ろのほうにあるサイトもあるので、2MBまで読む。"""
    body, final, headers = fetch(page_url, 2_000_000)
    text = body.decode(headers.get_content_charset() or "utf-8", "replace")
    found = {}
    for tag in re.findall(r"<meta\b[^>]*>", text, re.I):
        key = re.search(r'(?:property|name)\s*=\s*["\']([^"\']+)["\']', tag, re.I)
        val = re.search(r'content\s*=\s*["\']([^"\']+)["\']', tag, re.I)
        if key and val:
            found.setdefault(key.group(1).lower(), html.unescape(val.group(1)).strip())
    src = found.get("og:image") or found.get("og:image:url") or found.get("og:image:secure_url") or found.get("twitter:image") or ""
    if not src:
        return ""
    src = urllib.parse.urljoin(final, src)
    return src if src.startswith(("http://", "https://")) else ""


def fills_frame(row):
    """左右を足して枠いっぱいにしてよい掲載か（本の表紙とPodcastのカバーは除く。image_fill は切り抜いて枠いっぱいにする掲載）。"""
    return (row.get("種類") != "書籍" and not any(h in row.get("URL", "") for h in COVER_HOSTS)
            and row.get("ID") not in build.CONF.get("image_fill", []))


def widen(im):
    """縦に近い画像の左右を足して 1.91:1 にする。左右の端の色がそろっていればその色で塗り（白地のロゴなど）、
    そろっていなければ同じ画像をぼかして背景に敷く（写真など）。元の画像は切らない。"""
    w, h = im.size
    nw = round(h * FRAME)
    # 左右の端（幅の2%）の画素のうち、いちばん多い色に近いものが9割以上なら「端の色がそろっている」とみなす
    px = list(im.crop((0, 0, max(1, w // 50), h)).getdata()) + list(im.crop((w - max(1, w // 50), 0, w, h)).getdata())
    base = tuple(sorted(p[i] for p in px)[len(px) // 2] for i in range(3))
    flat = sum(1 for p in px if max(abs(p[i] - base[i]) for i in range(3)) <= 24) >= len(px) * 0.9
    if flat:
        canvas = Image.new("RGB", (nw, h), base)
    else:
        scale = nw / w
        bg = im.resize((nw, round(h * scale)), Image.LANCZOS)
        top = (bg.height - h) // 2
        bg = bg.crop((0, top, nw, top + h)).filter(ImageFilter.GaussianBlur(max(8, h // 25)))
        canvas = Image.blend(bg, Image.new("RGB", (nw, h), (255, 255, 255)), 0.25)
    canvas.paste(im, ((nw - w) // 2, 0))
    return canvas


LOGO_MAX_AREA = 0.08      # 無地の背景で、中身（ロゴなど）がこの割合より小さい画像は寄って大きく見せる
LOGO_TARGET_W = 0.5       # 寄ったあと、中身が枠の幅に占める割合の目安
LOGO_MAX_ZOOM = 2.2       # 寄りすぎて粗くならないよう、拡大はここまで


def zoom_logo(im):
    """無地の背景の真ん中に小さなロゴがあるだけの画像は、ロゴに寄って 1.91:1 で切り出す。当てはまらなければそのまま返す。"""
    w, h = im.size
    if w / h < FILL_BELOW:
        return im
    edge = max(1, min(w, h) // 50)
    px = (list(im.crop((0, 0, w, edge)).getdata()) + list(im.crop((0, h - edge, w, h)).getdata())
          + list(im.crop((0, 0, edge, h)).getdata()) + list(im.crop((w - edge, 0, w, h)).getdata()))
    base = tuple(sorted(p[i] for p in px)[len(px) // 2] for i in range(3))
    if sum(1 for p in px if max(abs(p[i] - base[i]) for i in range(3)) <= 12) < len(px) * 0.97:
        return im  # 端の色がそろっていない（写真や模様）
    diff = ImageChops.difference(im, Image.new("RGB", im.size, base)).convert("L").point(lambda v: 255 if v > 28 else 0)
    box = diff.getbbox()
    if not box:
        return im
    bw, bh = box[2] - box[0], box[3] - box[1]
    if bw * bh > w * h * LOGO_MAX_AREA:
        return im
    # 幅で半分、または高さで3割を占めるまで寄る。ただし中身が枠からはみ出しそうなとき・切り出しが小さくなりすぎるとき（幅480px未満）は控える
    zoom = min(LOGO_MAX_ZOOM, max(LOGO_TARGET_W * w / bw, 0.3 * h / bh), 0.85 * w / bw, 0.8 * h / bh, w / 480)
    if zoom <= 1.15:
        return im
    cw = round(w / zoom)
    ch = round(cw / FRAME)
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    canvas = Image.new("RGB", (cw, ch), base)
    left, top = round(cx - cw / 2), round(cy - ch / 2)
    canvas.paste(im.crop((max(0, left), max(0, top), min(w, left + cw), min(h, top + ch))), (max(0, -left), max(0, -top)))
    return canvas


def save_images(item_id, data, fill=False):
    """画像を読み込み直して JPEG で2つ書き出す（元のファイルはそのまま使わない）。(幅, 高さ) を返す。"""
    im = Image.open(io.BytesIO(data))
    im.load()
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    else:
        im = im.convert("RGB")
    w, h = im.size
    if w < 80 or h < 80:
        raise ValueError("画像が小さすぎます")
    if not build.valid_id(item_id):
        raise ValueError("掲載IDに使えない文字があります")
    if fill and w / h < FILL_BELOW:
        im = widen(im)
        w, h = im.size
    if fill:
        im = zoom_logo(im)
        w, h = im.size
    large = im.copy()
    if w > LARGE_W:
        large = large.resize((LARGE_W, round(h * LARGE_W / w)), Image.LANCZOS)
    os.makedirs(IMG_DIR, exist_ok=True)
    large.save(os.path.join(IMG_DIR, item_id + ".webp"), "WEBP", quality=80, method=6)
    save_card(item_id, im)
    return large.size


def save_card(item_id, im):
    """カード用。横長は枠いっぱいに切り抜くので枠を覆う大きさに、正方形・縦長は枠の高さに収まる大きさにする。"""
    w, h = im.size
    scale = max(CARD_W / w, CARD_H / h) if w / h >= 1.6 else CARD_H / h
    small = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS) if scale < 1 else im.copy()
    small.save(os.path.join(IMG_DIR, item_id + "-s.webp"), "WEBP", quality=80, method=6)


def remove_files(item_id):
    if not build.valid_id(item_id):
        return
    for name in (item_id + ".webp", item_id + "-s.webp", item_id + ".jpg", item_id + "-s.jpg"):
        path = os.path.join(IMG_DIR, name)
        if os.path.exists(path):
            os.remove(path)


def check(row, today, override=""):
    """1件を確かめて、manifest に入れる記録を返す。override があれば公式ページを読まずにその画像を使う。"""
    rec = {"page": row["URL"], "checked": today.isoformat()}
    if override:
        rec["manual"] = True
    try:
        src, data = override, None
        if not src:
            # 決まった場所の画像（本の表紙など）を先に試し、取れなければふつうにページを読む
            # （ISBNがあっても紀伊國屋に表紙がない本もある）
            try:
                src = derived_image_url(row["URL"], row.get("種類", ""), row.get("タイトル", ""))
                if src:
                    data, _, _ = fetch(src, MAX_BYTES + 1)
                    Image.open(io.BytesIO(data)).verify()
            except Exception:
                src, data = "", None
        if not src:
            src = og_image_url(page_for_image(row["URL"]))
        if not src:
            remove_files(row["ID"])
            return dict(rec, status="none")
        if data is None and src.startswith("file:"):
            path = os.path.normpath(os.path.join(ROOT, src[5:]))
            if not path.startswith(os.path.join(ROOT, "images", "manual") + os.sep):
                raise ValueError("images/manual/ の外のファイルは使えません")
            with open(path, "rb") as f:
                data = f.read(MAX_BYTES + 1)
            rec["fsize"] = len(data)  # 同じファイル名で入れ替えたときに気づけるように
        elif data is None:
            data, _, _ = fetch(src, MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("画像が大きすぎます")
        w, h = save_images(row["ID"], data, fills_frame(row))
        return dict(rec, status="ok", src=src, w=w, h=h)
    except Exception as ex:  # 取れなかったときは前の画像を残す（一時的な失敗で消さない）
        return dict(rec, status="error", note=("%s: %s" % (type(ex).__name__, ex))[:120])


def norm_src(src):
    return re.sub(r"\?.*$", "", src.replace("http://", "https://", 1))


GENERIC_NAME = re.compile(r"(ogp|og[-_.]|ogimage|default|logo|share|common)", re.I)


def is_suspect(page, src):
    """サイト共通の画像かもしれないもの：トップ以外のページなのに、画像がサイトの浅い場所にある ogp・logo・default などの名前。
    （2026年10月、Business Insider の「キャリアインサイダー」がサイト全体の /images/ogp.png になっていた）"""
    page_path = urllib.parse.urlsplit(page).path
    if page_path in ("", "/") or not src or src.startswith("file:"):
        return False
    src_path = urllib.parse.urlsplit(src).path
    name = src_path.rsplit("/", 1)[-1]
    if not GENERIC_NAME.search(name):
        return False
    if "default" in name.lower():
        return True
    # 画像の場所や名前にページの部分（/soudan/ など）が入っていれば、そのページ用の画像とみなす
    words = [w for w in page_path.strip("/").split("/") if len(w) >= 3]
    if any(w.lower() in src_path.lower() for w in words):
        return False
    return src_path.count("/") <= 2


def mark_generic(manifest, keep):
    """取得し終えた記録を見直す。
    - ちがうページなのに同じ画像になっているものは、サイト共通の画像（店のロゴなど）とみなして使わない（status "generic"）。
      作業ページ「観測所の画像あつめ」で黒田さんに画像を頼む対象になる。
    - サイト共通の画像かもしれないものには suspect を付ける（画像は使い続け、作業ページで確かめてもらう）。
      config/site.json の image_keep に入れたIDは、確かめずみとして付けない。"""
    groups = collections.defaultdict(set)
    for item_id, rec in manifest.items():
        if rec.get("status") == "ok" and not rec.get("manual"):
            groups[norm_src(rec["src"])].add(item_id)
    for src, ids in groups.items():
        if len({manifest[i]["page"] for i in ids}) >= 2:
            for item_id in ids:
                remove_files(item_id)
                manifest[item_id] = {k: v for k, v in manifest[item_id].items() if k not in ("w", "h", "suspect")}
                manifest[item_id].update(status="generic", note="ほかの掲載と同じ画像（サイト共通の画像）")
    for item_id, rec in manifest.items():
        suspect = rec.get("status") == "ok" and not rec.get("manual") and item_id not in keep and is_suspect(rec.get("page", ""), rec.get("src", ""))
        if suspect:
            rec["suspect"] = True
        else:
            rec.pop("suspect", None)
        # 小さすぎる画像（短い辺が200px未満）は、大きく出すとぼやけるので、画像あつめで大きな画像を頼む
        # （w・h は縮小後の大きさ。幅960まで縮めた横長の帯（YouTube のバナーなど）は小さいとは見なさない）
        w, h = rec.get("w", 999), rec.get("h", 999)
        small = rec.get("status") == "ok" and item_id not in keep and w < 960 and min(w, h) < SMALL_MIN_SIDE
        if small:
            rec["small"] = True
        else:
            rec.pop("small", None)


def resize_only():
    for name in sorted(os.listdir(IMG_DIR)):
        if name.endswith(".webp") and not name.endswith("-s.webp"):
            with Image.open(os.path.join(IMG_DIR, name)) as im:
                save_card(name[:-5], im.convert("RGB"))
    print("カード用の画像を作り直しました")


def main():
    today = datetime.datetime.now(build.JST).date()
    manifest = {}
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as f:
            manifest = {k: v for k, v in json.load(f).items() if build.valid_id(k)}
    exclude = set(build.CONF.get("image_exclude", []))
    keep = set(build.CONF.get("image_keep", []))
    overrides = {}
    if os.path.exists(OVERRIDES):
        with open(OVERRIDES, encoding="utf-8") as f:
            overrides = {k: v.strip() for k, v in json.load(f).items() if isinstance(v, str) and v.strip().startswith(("http://", "https://", "file:images/manual/"))}

    reader = csv.DictReader(io.StringIO(build.fetch_csv(build.CONF["csv_url"])))
    rows, all_ids = [], set()
    for raw in reader:
        row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
        if not build.valid_id(row.get("ID")):  # サイト本体と同じIDのチェック（ファイル名に使うため）
            continue
        all_ids.add(row["ID"])
        if row.get("状態") in build.LISTED_STATES and row.get("URL", "").startswith(("http://", "https://")):
            rows.append(row)

    # 掲載が終わったもの・除外したものの画像を消す
    for item_id in list(manifest):
        if item_id not in all_ids or item_id in exclude:
            remove_files(item_id)
            del manifest[item_id]
    for name in os.listdir(IMG_DIR) if os.path.isdir(IMG_DIR) else []:
        item_id = name.split(".")[0].split("-")[0]
        if item_id not in manifest:
            os.remove(os.path.join(IMG_DIR, name))

    def due(row):
        rec = manifest.get(row["ID"])
        if row["ID"] in exclude:
            return False
        if not rec or rec.get("page") != row["URL"]:
            return True
        if row["ID"] in overrides and rec.get("src") != overrides[row["ID"]]:
            return True  # 手で渡した画像が新しく入った・変わった
        if row["ID"] in overrides and overrides[row["ID"]].startswith("file:"):
            path = os.path.join(ROOT, overrides[row["ID"]][5:])
            if os.path.exists(path) and rec.get("fsize") != os.path.getsize(path):
                return True  # 同じファイル名のまま画像を入れ替えた
        if rec.get("status") == "ok" and rec.get("w") and rec["w"] / rec["h"] < FILL_BELOW and fills_frame(row):
            return True  # 縦に近い画像を、左右を足して作り直す
        age = (today - datetime.date.fromisoformat(rec["checked"])).days
        return age >= (REFRESH_DAYS if rec["status"] == "ok" else RETRY_DAYS)

    todo = [r for r in rows if due(r)]
    todo.sort(key=lambda r: (r["ID"] not in overrides, r["ID"] in manifest, manifest.get(r["ID"], {}).get("checked", "")))  # 手で渡した画像と新しい掲載を先に
    todo = todo[:MAX_PER_RUN]

    by_host = collections.defaultdict(list)
    for r in todo:
        by_host[host_of(r["URL"])].append(r)
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for results in pool.map(lambda group: [(r["ID"], check(r, today, overrides.get(r["ID"], ""))) for r in group], by_host.values()):
            for item_id, rec in results:
                old = manifest.get(item_id, {})
                if rec["status"] == "error" and old.get("status") == "ok":
                    rec = dict(old, checked=rec["checked"], note=rec["note"])  # 前の画像を使い続ける
                manifest[item_id] = rec

    mark_generic(manifest, keep)
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(manifest.items())), f, ensure_ascii=False, indent=1)
        f.write("\n")
    counts = collections.Counter(manifest[r["ID"]]["status"] for r in rows if r["ID"] in manifest)
    suspects = sum(1 for r in rows if manifest.get(r["ID"], {}).get("suspect") or manifest.get(r["ID"], {}).get("small"))
    print("画像：今回確かめた %d件／掲載 %d件のうち 画像あり %d件（うち確認したいもの %d件）・画像なし %d件・サイト共通の画像 %d件・取得できず %d件・未確認 %d件"
          % (len(todo), len(rows), counts["ok"], suspects, counts["none"], counts["generic"], counts["error"], len(rows) - sum(counts.values())))


if __name__ == "__main__":
    resize_only() if "--resize-only" in sys.argv else main()
