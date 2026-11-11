"""「転機の天気予報」（/yoho/）に使う国の統計を取って、data/yoho.json に保存する。

毎朝の「サイトを更新」で、サイトを作る前に動く。指標は config/yoho.json に書く。
- e-Stat の API はアプリケーションID（GitHub の Secrets の ESTAT_APP_ID）を使う。IDはファイルにもページにも書かない。
- 統計ダッシュボードの API は登録なしで使える。
- 取れなかった指標や、値の形がおかしい指標は、前回の値をそのまま残す（ページを壊さない）。
  指標ごとの結果（最後に取れた日・データの年月・エラー）は status に書き、ページを作るときに /yoho/status.json として公開する。
- 統計表が作り直されて statsDataId が変わったときは、statsCode と表の題名で探し直して使う（見つけた ID も保存する）。

使い方：python3 tools/fetch_yoho.py
"""
import datetime
import json
import os
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF = os.path.join(ROOT, "config", "yoho.json")
DATA = os.path.join(ROOT, "data", "yoho.json")
ESTAT = "https://api.e-stat.go.jp/rest/3.0/app/json/"
DASH = "https://dashboard.e-stat.go.jp/api/1.0/Json/getData"
YEARS = 4  # 何年前から取るか（前年同月比と、小さな推移グラフに使う）
JST = datetime.timezone(datetime.timedelta(hours=9))


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ashitano-tenki-yoho"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def estat(api, app_id, **params):
    params["appId"] = app_id
    return get_json(ESTAT + api + "?" + urllib.parse.urlencode(params))


def text(x):
    return x.get("$", "") if isinstance(x, dict) else (x or "")


def find_table(src, app_id):
    """statsCode と題名で、いまの統計表の ID を探し直す（いちばん新しく公開されたもの）"""
    d = estat("getStatsList", app_id, statsCode=src["statsCode"], searchWord=src["title"][:20], limit=50)["GET_STATS_LIST"]
    tables = d.get("DATALIST_INF", {}).get("TABLE_INF", [])
    tables = tables if isinstance(tables, list) else [tables]
    hits = [t for t in tables if text(t.get("TITLE")).strip() == src["title"].strip()]
    hits.sort(key=lambda t: t.get("OPEN_DATE", ""), reverse=True)
    return hits[0]["@id"] if hits else None


def month_key(code):
    """e-Stat の時間コード（2026000909）や統計ダッシュボードの時間（20260900）を 2026-09 にする"""
    code = str(code)
    if len(code) == 10:
        return "%s-%s" % (code[:4], code[8:10])
    return "%s-%s" % (code[:4], code[4:6])


def fetch_estat(src, app_id):
    since = datetime.date.today().year - YEARS
    params = dict(src.get("params", {}), statsDataId=src["statsDataId"], cdTimeFrom="%d000101" % since)

    def get(sid):
        params["statsDataId"] = sid
        return estat("getStatsData", app_id, **params)["GET_STATS_DATA"]

    d = get(src["statsDataId"])
    found = None
    if str(d["RESULT"]["STATUS"]) not in ("0", "1") or not d.get("STATISTICAL_DATA", {}).get("DATA_INF"):
        found = find_table(src, app_id)
        if found and found != src["statsDataId"]:
            d = get(found)
    if str(d["RESULT"]["STATUS"]) != "0":
        raise RuntimeError("e-Stat：%s" % d["RESULT"].get("ERROR_MSG", ""))
    sd = d["STATISTICAL_DATA"]
    values = sd["DATA_INF"]["VALUE"]
    values = values if isinstance(values, list) else [values]
    series = {}
    for v in values:
        try:
            series[month_key(v["@time"])] = float(v["$"])
        except (KeyError, ValueError):
            continue  # 「-」や「…」（値なし）は飛ばす
    table = sd.get("TABLE_INF", {})
    return series, {"published": str(table.get("OPEN_DATE", "")), "table": found or src["statsDataId"]}


def fetch_dashboard(src):
    since = datetime.date.today().year - YEARS
    url = DASH + "?" + urllib.parse.urlencode({"IndicatorCode": src["indicator"], "RegionCode": "00000", "Cycle": 1,
                                               "IsSeasonalAdjustment": src.get("seasonal", 1), "TimeFrom": "%d0100" % since})
    d = get_json(url)["GET_STATS"]
    if str(d["RESULT"]["status"]) != "0":
        raise RuntimeError("統計ダッシュボード：%s" % d["RESULT"].get("errorMsg", ""))
    objs = d["STATISTICAL_DATA"]["DATA_INF"]["DATA_OBJ"]
    series = {}
    for o in objs if isinstance(objs, list) else [objs]:
        v = o["VALUE"]
        try:
            series[month_key(v["@time"])] = float(v["$"])
        except (KeyError, ValueError):
            continue
    return series, {}


def check(series):
    """値の形を確かめる（少なすぎる・前年同月がない・極端に飛んでいる値は使わない）"""
    if len(series) < 13:
        raise RuntimeError("値が%d か月分しかありません" % len(series))
    last = max(series)
    y, m = last.split("-")
    if "%d-%s" % (int(y) - 1, m) not in series:
        raise RuntimeError("%s の前年同月の値がありません" % last)
    if any(v < 0 for v in series.values()):
        raise RuntimeError("負の値があります")


def main():
    conf = json.load(open(CONF, encoding="utf-8"))
    old = json.load(open(DATA, encoding="utf-8")) if os.path.exists(DATA) else {}
    app_id = os.environ.get("ESTAT_APP_ID", "").strip()
    now = datetime.datetime.now(JST).replace(microsecond=0).isoformat()
    today = now[:10]
    out = {"checked": now, "indicators": {}}
    changed = False
    for ind in conf["indicators"] + ([conf["mood"]] if conf.get("mood") else []):
        key, src = ind["key"], ind["source"]
        prev = old.get("indicators", {}).get(key, {})
        rec = dict(prev)
        try:
            if src["api"] == "estat":
                if not app_id:
                    raise RuntimeError("ESTAT_APP_ID がありません")
                series, extra = fetch_estat(src, app_id)
            else:
                series, extra = fetch_dashboard(src)
            check(series)
            latest = max(series)
            new = dict(sorted(series.items())) != prev.get("series")
            changed = changed or new or bool(prev.get("error"))
            first_seen = prev.get("first_seen", {})
            if latest not in first_seen:
                first_seen = dict(first_seen, **{latest: today})
            rec.update({"series": dict(sorted(series.items())), "latest": latest, "fetched": today if new else prev.get("fetched", today), "error": "",
                        "first_seen": {k: v for k, v in first_seen.items() if k >= min(series)}}, **extra)
            print("%s：%s まで %d か月分" % (ind["label"], latest, len(series)))
        except Exception as ex:  # 取れなくても、前回の値を残して次の指標へ
            changed = changed or not prev.get("error")
            rec["error"] = "%s（%s）" % (str(ex)[:200], today)
            print("%s：取得できませんでした（%s）。前回の値を使います" % (ind["label"], ex), file=sys.stderr)
        out["indicators"][key] = rec
    if not changed and old.get("indicators"):
        # 新しい値もエラーの出入りもないときは書かない（毎日の記録が無駄に増えないように）。
        # fetched は「新しい値を最後に取れた日」、checked は「最後に見に行った日時」（ページを作るときに status.json に入れる）
        print("新しい値はありませんでした")
        return
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")


if __name__ == "__main__":
    main()
