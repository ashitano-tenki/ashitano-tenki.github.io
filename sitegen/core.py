"""設定の読み込み、共通の定数、スプレッドシートのCSVの読み込みと掲載データの組み立て。"""
import csv
import datetime
import io
import json
import os
import re
import unicodedata
import urllib.request

__all__ = ["SPREAD_SHIFT", "score_band", "SPREAD_MAX", "spread_keys", "spread_line", "spread_order", "BASE", "BuildError", "COMMON", "CONF", "COST_ORDER", "IMAGES", "JST", "KINDS", "KIND_BY_NAME", "LISTED_STATES", "NOTES", "NOTES_DIR", "NOTES_LABEL", "OTHER", "OUT", "REQUIRED_COLUMNS", "ROOT", "STAGES", "STAGE_BY_NAME", "TENKI", "TENKI_BY_NAME", "TENKI_CONF", "VOICES", "VOICES_LABEL", "by_kind", "fetch_csv", "fix_memo", "kinds_of", "load_images", "load_json", "matches_tenki", "month_label", "one_line", "parse_date", "parse_month", "parse_rows", "parse_score", "split_list", "valid_id"]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # リポジトリの一番上（build.py のある場所）
OUT = os.path.join(ROOT, "_site")
JST = datetime.timezone(datetime.timedelta(hours=9))

REQUIRED_COLUMNS = ["ID", "タイトル", "種類", "転機の種類", "段階", "観測メモ", "URL",
                    "提供元・著者", "費用", "最終観測日", "追加日", "観測スコア", "状態"]
LISTED_STATES = {"確認済み", "要更新"}


def valid_id(item_id):
    """掲載IDとして使える文字だけか（ページや画像のファイル名に使うので、英数字・ハイフン・下線だけにする）。"""
    return bool(re.fullmatch(r"[A-Za-z0-9_-]+", item_id or ""))
COST_ORDER = ["無料", "一部無料", "有料"]
COMMON = "共通"
OTHER = "その他"


class BuildError(Exception):
    pass


def load_json(name):
    with open(os.path.join(ROOT, "config", name), encoding="utf-8") as f:
        return json.load(f)


CONF = load_json("site.json")
TENKI_CONF = load_json("tenki.json")
NOTES = load_json("tenki_notes.json")  # 転機別・転機×段階のページに載せる解説文
TENKI = TENKI_CONF["tenki"]
STAGES = TENKI_CONF["stages"]
TENKI_BY_NAME = {t["name"]: t for t in TENKI}
STAGE_BY_NAME = {s["name"]: s for s in STAGES}
BASE = CONF["base_url"].rstrip("/")
KINDS = CONF["kinds"]  # 種類（タイプ）の一覧と表示順
KIND_BY_NAME = {k["name"]: k for k in KINDS}


def load_images():
    """掲載先のシェア用画像の記録（tools/fetch_images.py が書く data/images.json）。画像が取れたものだけを返す。"""
    path = os.path.join(ROOT, "data", "images.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    exclude = set(CONF.get("image_exclude", []))
    out = {}
    for item_id, rec in data.items():
        if (valid_id(item_id) and rec.get("status") == "ok" and item_id not in exclude
                and os.path.exists(os.path.join(ROOT, "images", "items", item_id + ".webp"))
                and os.path.exists(os.path.join(ROOT, "images", "items", item_id + "-s.webp"))):
            out[item_id] = rec
    return out


IMAGES = load_images()


# ---------------------------------------------------------------- データ

def fetch_csv(url):
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tenki-kansoku-build"})
            with urllib.request.urlopen(req, timeout=60) as res:
                return res.read().decode("utf-8-sig")
        except Exception as ex:  # 通信の一時的な失敗に備えて3回まで試す
            last = ex
    raise BuildError("CSVを取得できませんでした: %s" % last)


def split_list(value):
    return [v.strip() for v in re.split(r"[、,，/／]", value or "") if v.strip()]


def parse_date(value):
    value = (value or "").strip()
    m = re.match(r"(\d{4})[/\-.年](\d{1,2})[/\-.月](\d{1,2})", value)
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def parse_month(value):
    """「2026/07」「2026/7」「2026-07」を (2026, 7) にする。読めなければ None。"""
    m = re.match(r"\s*(\d{4})\s*[/\-.年]\s*(\d{1,2})", unicodedata.normalize("NFKC", value or ""))
    if not m or not 1 <= int(m.group(2)) <= 12:
        return None
    return int(m.group(1)), int(m.group(2))


def fix_memo(text):
    """観測メモの言い回しを整える。「〜に向く。」は不自然なので「〜に向いている。」にする（スプレッドシートはそのまま）。"""
    return re.sub(r"に向く(?=。|$)", "に向いている", text or "")


def month_label(ym):
    return "%d年%d月" % ym if ym else ""


def parse_score(value):
    try:
        return float(unicodedata.normalize("NFKC", value or "").strip())
    except ValueError:
        return 0.0


def one_line(memo, limit=60):
    memo = (memo or "").strip()
    first = memo.split("。")[0]
    first = first + "。" if first and first != memo else first
    if len(first) > limit:
        first = first[:limit - 1] + "…"
    return first


def parse_rows(text):
    if text.lstrip().startswith("<"):
        raise BuildError("CSVの代わりにHTMLが返ってきました。公開設定を確認してください。")
    reader = csv.DictReader(io.StringIO(text))
    header = [h.strip() for h in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise BuildError("CSVに必要な列がありません: %s" % "、".join(missing))
    items, seen, skipped = [], set(), []
    for raw in reader:
        row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
        item_id = row["ID"]
        if not valid_id(item_id) or not row["タイトル"]:
            continue
        if item_id in seen:
            continue
        seen.add(item_id)
        if row["種類"] not in KIND_BY_NAME:
            skipped.append("%s（%s）" % (item_id, row["種類"] or "種類なし"))
            continue
        items.append({
            "id": item_id,
            "title": row["タイトル"],
            "kind": row["種類"],
            "tenki": split_list(row["転機の種類"]),
            "stages": split_list(row["段階"]),
            "memo": fix_memo(row["観測メモ"]),
            "url": row["URL"] if re.match(r"^https?://", row["URL"]) else "",
            "provider": row["提供元・著者"],
            "observed": parse_date(row["最終観測日"]),
            "added": parse_date(row["追加日"]),
            "score": parse_score(row["観測スコア"]),
            "listed": row["状態"] in LISTED_STATES,
            "line": one_line(row["観測メモ"]),
            "published": parse_month(row.get("発表・更新時期", "")),
            # 向いている人（任意の列。「40代、女性」のように区切って書く。列がなければ空）。
            # 画面には出さず、キーワード検索の対象にだけ入れる（自分の属性が書かれていない人に疎外感を与えないため）
            "for": [x.strip() for x in re.split(r"[、,，/／]", row.get("向いている人", "")) if x.strip()],
        })
    if skipped:
        print("設定にない種類のため表示から外しました: %s" % "、".join(skipped))
    # 並び順（おすすめ順）は、観測スコアを5点刻みの帯（95〜100、90〜94 …）に分け、帯の高い順 → 同じ帯の中で画像ありを先 →
    # 観測スコアの高い順（2026-11-07 黒田さんの決定。画像があるだけで点数の低いものが先頭に来ないように）。そのうえで spread_order で、
    # 同じ主な転機・同じ提供元が3件続かないように並べ直す。スコアは並べ替えにだけ使い、出力には rank（順位）だけを残す。
    items.sort(key=lambda it: (-score_band(it["score"]), it["id"] not in IMAGES, -it["score"],
                               -(it["added"] or datetime.date.min).toordinal(), it["id"]))
    # score_rank は並べ直す前の順（キーワード検索の並びに使う。検索では同じ転機・提供元を散らさない）
    for i, it in enumerate(items):
        it["score_rank"] = i + 1
    # rank（一覧の並び）は、同じ転機・同じ提供元が上位で続かないように並べ直したもの（spread_order）
    shown = [it for it in items if it["listed"]]
    order = spread_order(shown) + [it for it in items if not it["listed"]]
    for i, it in enumerate(order):
        it["rank"] = i + 1
    items.sort(key=lambda it: it["rank"])
    return items


def score_band(score):
    """観測スコアの5点刻みの帯。95〜100 は同じ帯（19）、90〜94 は 18 …。"""
    return min(int(score // 5), 19)


SPREAD_MAX = 2    # 同じ「主な転機」・同じ「提供元・著者」が続いてよい数
SPREAD_SHIFT = 3  # 並べ直しで後ろに回すのは、元の位置から最大でこの数まで


def spread_keys(it):
    """並べ直しで比べる2つ：主な転機（転機の種類の最初の語）と提供元・著者。"""
    return (it["tenki"][0] if it["tenki"] else "", it["provider"].strip())


def spread_line(items):
    """1本の並びを、上から順に、直前の2件と同じ主な転機・同じ提供元が3件目にならないものを先に出す形に並べ直す
    （2026-11-07 データ側の依頼。本の上位が定年ばかりになっていたため）。
    後ろに回すのは元の位置から SPREAD_SHIFT 個下まで。それを超えそうなものは、条件に合わなくてもそこで出す。
    前に出すのも元の位置から SPREAD_SHIFT 個上まで（実務のように同じ転機が多い種類で、点数の低いものが遠くから上がってこないように）。
    条件に合うものがなければ、残りのいちばん上をそのまま出す。"""
    rest, out = list(enumerate(items)), []
    while rest:
        pos = len(out)
        def ok(it):
            if pos < SPREAD_MAX:
                return True
            keys = spread_keys(it)
            for k in range(2):
                if keys[k] and all(spread_keys(o)[k] == keys[k] for o in out[-SPREAD_MAX:]):
                    return False
            return True
        if rest[0][0] + SPREAD_SHIFT <= pos:  # これ以上は後ろに回せない
            hit = rest[0]
        else:
            # 前に出すのも、元の位置から SPREAD_SHIFT 個上まで（点数の大きく違うものが入れ替わらないように）
            hit = next((r for r in rest if r[0] <= pos + SPREAD_SHIFT and ok(r[1])), rest[0])
        out.append(hit[1])
        rest.remove(hit)
    return out


def spread_order(items):
    """一覧の並び。種類（タイプ）ごとに spread_line で並べ直し、その種類がもとの並びで占めていた位置に入れ直す。
    こうすると、種類ごとの一覧（棚・タイプのページ）でも、全部を混ぜた一覧でも、それぞれの種類の中は並べ直した順になる。"""
    queues = {}
    for kind in dict.fromkeys(it["kind"] for it in items):
        queues[kind] = spread_line([it for it in items if it["kind"] == kind])
    return [queues[it["kind"]].pop(0) for it in items]


def matches_tenki(item, name):
    if name in item["tenki"]:
        return True
    # 「共通」はどの転機にも役立つものなので、個別の転機にも含める
    return name not in (COMMON, OTHER) and COMMON in item["tenki"]


def kinds_of(items):
    """データに1件以上ある種類だけを、設定の順に返す（0件の種類は出さない）。"""
    present = {it["kind"] for it in items}
    return [k["name"] for k in KINDS if k["name"] in present]


def by_kind(items):
    groups = {}
    for it in items:
        groups.setdefault(it["kind"], []).append(it)
    return [(k, groups[k]) for k in kinds_of(items)]


# ---------------------------------------------------------------- 観測ノート（転機ごとのまとめ記事）
# 原稿は notes/<スラッグ>.md。先頭の --- で囲んだ部分に題名などを書き、本文は次の書き方だけを使う。
#   ## 見出し / ### 小見出し / 空行で段落 / 「- 」で箇条書き / [文字](URL) でリンク / **強調**
#   :::item R0123   ← 掲載を1件差し込む（名前・画像・リンクはデータから自動で入る）
#   黒田さんのひとこと（次の ::: までの段落）
#   :::
# draft: true の原稿は公開しない（--drafts を付けたときだけ、検索に出ない形で作る）。
NOTES_DIR = os.path.join(ROOT, "notes")
NOTES_LABEL = "観測ノート"


# ---------------------------------------------------------------- 転機の声

# 「転機の声」のページ（/voices/）。転機を経験した人のインタビュー記事を、別のスプレッドシートの「公開用」タブから読む。
# 観測所の一覧・検索・並び順には混ぜない（search.json にも入れない）。記事の本文・写真は載せず、タイトル・リンク・分類・要約だけを出す
VOICES = CONF.get("voices", {})
VOICES_LABEL = VOICES.get("name", "転機の声")
