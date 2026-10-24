#!/usr/bin/env python3
"""掲載先の公式ページからシェア用の画像（OGP画像）を取得し、縮小して images/items/ に保存するスクリプト。

  python3 tools/fetch_images.py

- 毎朝の「サイトを更新」で、サイトを作る前に動く。画像の縮小に Pillow を使う（ワークフローで入れる）。
- 取得するのは、まだ画像を確かめていない掲載・取得から30日たったもの・取れなかったもので7日たったものだけ。
  相手のサイトに負担をかけないよう、1回に確かめる数を MAX_PER_RUN までにし、同じドメインには間をあける。
- 結果は data/images.json に書く（ID ごとに、状態・元の画像のURL・大きさ・確かめた日）。
- 画像は2つ書き出す：{ID}.jpg（紹介ページ用、幅960まで）と {ID}-s.jpg（カードの上の画像用、幅600ほど）。
  `--resize-only` を付けると取得はせず、保存してある {ID}.jpg からカード用の画像だけを作り直す（大きさを変えたとき用）。
- config/image_overrides.json に「ID: 画像のURL」を書いたものは、公式ページを読まずにそのURLの画像を使う
  （自動で取れない掲載に、黒田さんが手で見つけた画像を渡すとき。URLが変わったら次の回で取り直す）。
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
import urllib.request

from PIL import Image

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
LARGE_W = 960             # 紹介ページ用の幅
CARD_W, CARD_H = 600, 314  # カードの上の画像枠（1.91:1）を高精細の画面でも粗くなく埋められる大きさ

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


def og_image_url(page_url):
    """ページの og:image（なければ twitter:image）のURLを返す。見つからなければ空文字。"""
    body, final, headers = fetch(page_url, 600_000)
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


def save_images(item_id, data):
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
    large = im.copy()
    if w > LARGE_W:
        large = large.resize((LARGE_W, round(h * LARGE_W / w)), Image.LANCZOS)
    os.makedirs(IMG_DIR, exist_ok=True)
    large.save(os.path.join(IMG_DIR, item_id + ".jpg"), "JPEG", quality=78, optimize=True, progressive=True)
    save_card(item_id, im)
    return large.size


def save_card(item_id, im):
    """カード用。横長は枠いっぱいに切り抜くので枠を覆う大きさに、正方形・縦長は枠の高さに収まる大きさにする。"""
    w, h = im.size
    scale = max(CARD_W / w, CARD_H / h) if w / h >= 1.6 else CARD_H / h
    small = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS) if scale < 1 else im.copy()
    small.save(os.path.join(IMG_DIR, item_id + "-s.jpg"), "JPEG", quality=78, optimize=True)


def remove_files(item_id):
    for name in (item_id + ".jpg", item_id + "-s.jpg"):
        path = os.path.join(IMG_DIR, name)
        if os.path.exists(path):
            os.remove(path)


def check(row, today, override=""):
    """1件を確かめて、manifest に入れる記録を返す。override があれば公式ページを読まずにその画像を使う。"""
    rec = {"page": row["URL"], "checked": today.isoformat()}
    if override:
        rec["manual"] = True
    try:
        src = override or og_image_url(row["URL"])
        if not src:
            remove_files(row["ID"])
            return dict(rec, status="none")
        data, _, _ = fetch(src, MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("画像が大きすぎます")
        w, h = save_images(row["ID"], data)
        return dict(rec, status="ok", src=src, w=w, h=h)
    except Exception as ex:  # 取れなかったときは前の画像を残す（一時的な失敗で消さない）
        return dict(rec, status="error", note=("%s: %s" % (type(ex).__name__, ex))[:120])


def resize_only():
    for name in sorted(os.listdir(IMG_DIR)):
        if name.endswith(".jpg") and not name.endswith("-s.jpg"):
            with Image.open(os.path.join(IMG_DIR, name)) as im:
                save_card(name[:-4], im.convert("RGB"))
    print("カード用の画像を作り直しました")


def main():
    today = datetime.datetime.now(build.JST).date()
    manifest = {}
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as f:
            manifest = json.load(f)
    exclude = set(build.CONF.get("image_exclude", []))
    overrides = {}
    if os.path.exists(OVERRIDES):
        with open(OVERRIDES, encoding="utf-8") as f:
            overrides = {k: v.strip() for k, v in json.load(f).items() if isinstance(v, str) and v.strip().startswith(("http://", "https://"))}

    reader = csv.DictReader(io.StringIO(build.fetch_csv(build.CONF["csv_url"])))
    rows, all_ids = [], set()
    for raw in reader:
        row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
        if not row.get("ID"):
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

    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(manifest.items())), f, ensure_ascii=False, indent=1)
        f.write("\n")
    counts = collections.Counter(manifest[r["ID"]]["status"] for r in rows if r["ID"] in manifest)
    print("画像：今回確かめた %d件／掲載 %d件のうち 画像あり %d件・画像なし %d件・取得できず %d件・未確認 %d件"
          % (len(todo), len(rows), counts["ok"], counts["none"], counts["error"], len(rows) - sum(counts.values())))


if __name__ == "__main__":
    resize_only() if "--resize-only" in sys.argv else main()
