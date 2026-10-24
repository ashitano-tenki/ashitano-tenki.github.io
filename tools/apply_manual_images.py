"""作業ページ「観測所の画像あつめ」の入力を観測所に取り込む（Claude Code が手元で使う。Pillow が必要）。

  python tools/apply_manual_images.py 作業フォルダ アセットのフォルダ

- 作業フォルダの entries.json（{ID: {image, asset, skip}}）を読み、画像を images/manual/{ID}.jpg に保存して
  config/image_overrides.json に "file:images/manual/{ID}.jpg" を書く。skip は config/site.json の image_exclude へ。
- アップロード画像は、作業ページのアセットを取り出したフォルダ（ファイル名がアセットIDで始まる）から読む。
- 結果は作業フォルダの results.json（作業ページに書き戻す result・resultFor・resultNote）。
- このあと tools/fetch_images.py を動かすと、紹介ページ用・カード用の画像ができる。"""
import json, os, sys, io, re, urllib.request
from PIL import Image
site = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S, assets_dir = sys.argv[1], sys.argv[2]
entries = json.load(open(S + "/entries.json", encoding="utf-8"))
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
ov_path = site + "/config/image_overrides.json"
overrides = json.load(open(ov_path, encoding="utf-8"))
conf_path = site + "/config/site.json"
conf_text = open(conf_path, encoding="utf-8").read()
conf = json.loads(conf_text)
exclude = list(conf.get("image_exclude", []))
os.makedirs(site + "/images/manual", exist_ok=True)
results = {}
for i, en in sorted(entries.items()):
    try:
        if en.get("skip"):
            if i not in exclude: exclude.append(i)
            overrides.pop(i, None)
            results[i] = {"result": "skip", "resultFor": "skip"}
            continue
        if i in exclude: exclude.remove(i)
        if en.get("asset"):
            key = "asset:" + en["asset"]
            fn = [f for f in os.listdir(assets_dir) if f.startswith(en["asset"])][0]
            data = open(os.path.join(assets_dir, fn), "rb").read()
        else:
            key = en["image"]
            if key.lower().split("?")[0].endswith(".svg"):
                raise ValueError("SVG形式の画像は使えません。キャプチャをアップロードするか、PNG・JPEGのURLを入れてください")
            req = urllib.request.Request(key, headers={"User-Agent": UA, "Referer": key})
            data = urllib.request.urlopen(req, timeout=20).read(15_000_000)
        im = Image.open(io.BytesIO(data)); im.load()
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA"); bg = Image.new("RGB", im.size, (255, 255, 255)); bg.paste(im, mask=im.split()[-1]); im = bg
        else:
            im = im.convert("RGB")
        w, h = im.size
        if min(w, h) < 120:
            raise ValueError("画像が小さすぎます（%d×%d）。もっと大きな画像かキャプチャを入れてください" % (w, h))
        if w > 1600:
            im = im.resize((1600, round(h * 1600 / w)), Image.LANCZOS)
        im.save(site + "/images/manual/%s.jpg" % i, "JPEG", quality=85, optimize=True, progressive=True)
        overrides[i] = "file:images/manual/%s.jpg" % i
        results[i] = {"result": "ok", "resultFor": key, "size": "%dx%d" % (w, h)}
    except Exception as ex:
        msg = str(ex) if isinstance(ex, ValueError) else "この画像は取得できませんでした（%s）。別のURLかキャプチャを試してください" % type(ex).__name__
        results[i] = {"result": "failed", "resultFor": en.get("image") if not en.get("asset") else "asset:" + en["asset"], "resultNote": msg}
json.dump(dict(sorted(overrides.items())), open(ov_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
conf_text = re.sub(r'"image_exclude": \[[^\]]*\]', '"image_exclude": ' + json.dumps(sorted(exclude)), conf_text)
json.loads(conf_text); open(conf_path, "w", encoding="utf-8").write(conf_text)
json.dump(results, open(S + "/results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
from collections import Counter
print(Counter(r["result"] for r in results.values()))
for k, r in results.items():
    if r["result"] == "failed": print(k, r["resultNote"])
    elif r["result"] == "ok" and min(map(int, r["size"].split("x"))) < 300: print(k, "small", r["size"])
