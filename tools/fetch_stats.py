#!/usr/bin/env python3
"""GoatCounter の数字を読み、週次ふりかえり用の data/stats.json を書くスクリプト（毎週月曜の自動実行で使う）。

  GOATCOUNTER_API_KEY=… python3 tools/fetch_stats.py

- 期間は日本時間の日付で区切る。「直近7日」は昨日までの7日間、「前の7日」はその前の7日間。
- 入れるもの：訪問数、上位20ページ、探すページの検索語の上位20（結果あり search/〇〇 と 0件 search-zero/〇〇）、
  「役に立った／いまひとつ」の数、/project/ の訪問数、そのほかのクリックの記録（公式サイト・転機AI など）の合計。
- 個人を特定できる情報（IPアドレス・参照元のURLなど）は入れない。GoatCounter もそれらを返さない。
- GoatCounter は「訪問数」（同じ人の同じページは1日1回）で数える。ページビューの数は持っていない。
- API キーがないときは何も書かずに終わる（終了コード0）。
"""
import datetime
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "stats.json")
API = "https://yusukekuroda.goatcounter.com/api/v0"
JST = datetime.timezone(datetime.timedelta(hours=9))
TOP = 20


def get(path, key, **params):
    url = API + path + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                return json.load(res)
        except urllib.error.HTTPError as ex:
            if ex.code == 429 and attempt < 3:  # 呼びすぎ。少し待って試し直す
                time.sleep(5 * (attempt + 1))
                continue
            raise


def iso(d):
    """日本時間のその日の0時を、UTC の時刻の文字列にする（GoatCounter は1時間単位）。"""
    return datetime.datetime(d.year, d.month, d.day, tzinfo=JST).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def all_hits(key, start, end):
    """期間中のすべてのページ・イベントと、その訪問数。100件ずつ読む。"""
    hits, seen = [], []
    while True:
        params = {"start": start, "end": end, "limit": 100}
        if seen:
            params["exclude_paths"] = ",".join(str(i) for i in seen)
        data = get("/stats/hits", key, **params)
        page = data.get("hits") or []
        hits += page
        seen += [h["path_id"] for h in page]
        if not data.get("more") or not page:
            return hits
        time.sleep(1)


def summarize(key, first, last):
    """first〜last（日本時間の日付、両端を含む）の数字。"""
    start, end = iso(first), iso(last + datetime.timedelta(days=1))
    total = get("/stats/total", key, start=start, end=end)
    hits = all_hits(key, start, end)
    pages = sorted((h for h in hits if not h.get("event")), key=lambda h: -h["count"])
    events = [h for h in hits if h.get("event")]

    def ev(prefix):
        rows = sorted((h for h in events if h["path"].startswith(prefix)), key=lambda h: -h["count"])
        return rows

    def words(prefix):
        return [{"word": h["path"][len(prefix):], "count": h["count"]} for h in ev(prefix)[:TOP]]

    def helpful(kind):
        rows = ev("helpful/%s/" % kind)
        return {"total": sum(h["count"] for h in rows),
                "items": [{"id": h["path"].rsplit("/", 1)[-1], "count": h["count"]} for h in rows[:10]]}

    def path_count(path):
        return sum(h["count"] for h in pages if h["path"].rstrip("/") == path.rstrip("/"))

    clicks = {}
    for name, prefix in [("公式サイトを見る", "official/"), ("転機AIへの入口", "tenki-ai/"), ("あとで見る", "save/"),
                         ("共有", "share/"), ("セルフチェックのおすすめ", "check-pick/"),
                         ("セルフチェックを始めた", "check-start"), ("セルフチェックを終えた", "check-done/")]:
        clicks[name] = sum(h["count"] for h in ev(prefix))
    return {
        "start": first.isoformat(), "end": last.isoformat(),
        "visits": total.get("total", 0) - total.get("total_events", 0) if total.get("total_events") is not None else total.get("total", 0),
        "visits_including_events": total.get("total", 0),
        "top_pages": [{"path": h["path"], "title": h.get("title", ""), "count": h["count"]} for h in pages[:TOP]],
        "search_words": words("search/"),
        "search_zero_words": words("search-zero/"),
        "helpful_yes": helpful("yes"),
        "helpful_no": helpful("no"),
        "project_visits": path_count("/project/"),
        "clicks": clicks,
    }


def main():
    key = os.environ.get("GOATCOUNTER_API_KEY", "").strip()
    if not key:
        print("GOATCOUNTER_API_KEY がないので、stats.json は作りませんでした")
        return
    today = datetime.datetime.now(JST).date()
    last = today - datetime.timedelta(days=1)
    week = summarize(key, last - datetime.timedelta(days=6), last)
    prev = summarize(key, last - datetime.timedelta(days=13), last - datetime.timedelta(days=7))
    data = {"updated": datetime.datetime.now(JST).replace(microsecond=0).isoformat(),
            "note": "GoatCounter の訪問数（同じ人の同じページは1日1回）。期間は日本時間の日付で、両端を含む。",
            "this_week": week, "previous_week": prev}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("stats.json：%s〜%s 訪問 %d（前の7日 %d）" % (week["start"], week["end"], week["visits"], prev["visits"]))


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as ex:
        print("GoatCounter の API でエラーになりました（%s）。キーの権限（Read statistics）を確かめてください" % ex.code, file=sys.stderr)
        sys.exit(1)
