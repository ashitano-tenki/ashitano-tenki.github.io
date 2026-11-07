#!/usr/bin/env python3
"""掲載中のURLが開けるかを確かめ、結果を data/linkcheck.json に書くスクリプト（毎週の自動点検で使う）。

  python3 tools/check_links.py [report.md]

- 対象：公開用CSVのうち「状態」が「確認済み」「要更新」の行の「URL」列と、転機の声の公開用CSV（確認済みの記事だけが並ぶ）の「URL」列。
- 結果の各行の kind で区別する（観測所の掲載は「観測所」、転機の声の記事は「声」）。summary は観測所の掲載だけ、voices_summary は転機の声だけの件数。
- 結果は 正常／移転／拒否／要確認 の4つに分ける。linkcheck.json の items には「正常」以外だけを入れる。
- 「要確認」があったときは、Issue 用の report.md も書く（引数で指定したとき）。
- スプレッドシートやサイトの掲載は変えない。直すかどうかは、データ側の定期実行が判断する。
- 1回ですべてを開かない（掲載が増えて30分の時間切れで止まったため）。毎回確かめるのは、
  まだ一度も確かめていないもの・前回「正常」以外だったもの・残りのうち確かめた日が古いもの（全体の4分の1）。
  4週で全体を一巡する。確かめた日と結果は data/linkcheck_seen.json に残す。
- 時間の上限（BUDGET 秒）を過ぎたら新しく開くのをやめ、そこまでの結果を保存する。残りは次回に回る。
- 同じサイトが続けて3回応答しなければ、そのサイトの残りは開かずに「拒否」（自動の点検に応答しないサイト）とする。
- linkcheck.json の items と summary は、今回確かめていないものも含めた「最後に確かめた結果」。
"""
import collections
import concurrent.futures
import csv
import datetime
import io
import json
import os
import socket
import ssl
import sys
import threading
import time
import http.cookiejar
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402  CSVの取得と設定は build.py と同じものを使う

OUT = os.path.join(ROOT, "data", "linkcheck.json")
SEEN = os.path.join(ROOT, "data", "linkcheck_seen.json")  # 掲載ごとの、最後に確かめた日・URL・結果
BUDGET = int(os.environ.get("LINKCHECK_BUDGET", "1200"))  # 新しく開くのをやめるまでの秒数（試し直しは含まない）
RETRY_BUDGET = 300                                       # 試し直しに使ってよい秒数
ROTATION = 4                                             # 何週で全体を一巡するか
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
           "Accept-Language": "ja,en-US;q=0.8,en;q=0.6"}
TIMEOUT = 12          # 1件あたりの待ち時間（秒）
WORKERS = 4           # 同時に確かめるドメインの数（相手に負担をかけないよう少なめ）
DOMAIN_GAP = 2.0      # 同じドメインに続けてアクセスするときの間隔（秒）
GIVE_UP = 3           # 同じサイトが続けてこの回数応答しなければ、そのサイトの残りは開かない
NO_ANSWER = ("拒否", None, "", "自動の点検に応答しないサイトです（ブラウザでは開けることが多い）", False)
RETRY_WAIT = 60       # 失敗したものを試し直すまでの待ち時間（秒）
REFUSED = {401, 403, 405, 406, 429, 451, 999}  # 自動アクセスを断るときによく返る番号

_last_access = {}
_lock = threading.Lock()


def host_of(url):
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def wait_for_domain(host):
    """同じドメインへの連続アクセスに間をあける。"""
    while True:
        with _lock:
            last = _last_access.get(host, 0)
            now = time.monotonic()
            if now - last >= DOMAIN_GAP:
                _last_access[host] = now
                return
        time.sleep(DOMAIN_GAP - (now - last))


class Redirects(urllib.request.HTTPRedirectHandler):
    """308（恒久的な転送）もたどる。"""
    def http_error_308(self, req, fp, code, msg, headers):
        return self.http_error_302(req, fp, 307, msg, headers)

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, 307 if code == 308 else code, msg, headers, newurl)
        if new is not None and req.get_method() == "HEAD":
            new.method = "HEAD"
        return new


def request(url, method):
    """(HTTPの番号, 最終的なURL) を返す。つながらないときは例外。転送はたどり、Cookie を使う転送にも対応する。"""
    wait_for_domain(host_of(url))
    opener = urllib.request.build_opener(Redirects, urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
                                         urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    req = urllib.request.Request(url, headers=HEADERS, method=method)
    with opener.open(req, timeout=TIMEOUT) as res:
        if method == "GET":
            res.read(4096)
        return res.status, res.geturl()


def check_once(url):
    """1回確かめる。HEAD で失敗したら GET で試し直す。(status, http_status, final_url, note, retryable) を返す。"""
    code, final, note = None, "", ""
    for method in ("HEAD", "GET"):
        try:
            code, final = request(url, method)
            break
        except urllib.error.HTTPError as ex:
            code, final, note = ex.code, "", ""
            if method == "HEAD":
                continue  # HEAD を受け付けないサイトがあるので GET で試し直す
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, ssl.SSLError) as ex:
            reason = getattr(ex, "reason", ex)
            if isinstance(reason, socket.gaierror):
                return "要確認", None, "", "ドメインが見つかりません", False
            if method == "HEAD":
                continue
            if isinstance(reason, (socket.timeout, TimeoutError)) or isinstance(ex, (socket.timeout, TimeoutError)):
                return "要確認", None, "", "応答がありません", True
            return "要確認", None, "", "つながりません（%s）" % reason, True
        except Exception as ex:  # 予想外の失敗も結果に残す
            if method == "HEAD":
                continue
            return "要確認", None, "", "確認できませんでした（%s）" % ex, True
    if code is None:
        return "要確認", None, "", "応答がありません", True
    if 200 <= code < 300:
        if final and host_of(final) != host_of(url):
            return "移転", code, final, "開き先のドメインが変わっています", False
        return "正常", code, "", "", False
    if code in REFUSED:
        return "拒否", code, "", "自動アクセスを断られました（壊れているとは限りません）", False
    if code in (404, 410):
        return "要確認", code, "", "ページが見つかりません", False
    if code >= 500:
        return "要確認", code, "", "サーバーの不具合", True
    return "要確認", code, "", "想定外の応答です", False


def main():
    report_path = sys.argv[1] if len(sys.argv) > 1 else None
    reader = csv.DictReader(io.StringIO(build.fetch_csv(build.CONF["csv_url"])))
    rows = []
    for raw in reader:
        row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
        if row.get("状態") in build.LISTED_STATES and row.get("URL", "").startswith(("http://", "https://")):
            row["_kind"] = "観測所"
            rows.append(row)
    # 転機の声の記事（公開用タブに出ている行はすべて確認済み）。読めなければ観測所の掲載だけを確かめる
    try:
        voice_text = build.fetch_csv(build.VOICES["csv_url"]) if build.VOICES.get("csv_url") else ""
    except build.BuildError as ex:
        print("注意: 転機の声のCSVを読めませんでした: %s" % ex, file=sys.stderr)
        voice_text = ""
    for v in build.parse_voices(voice_text):
        rows.append({"ID": v["id"], "タイトル": v["title"], "URL": v["url"], "_kind": "声"})

    try:
        with open(SEEN, encoding="utf-8") as f:
            seen = json.load(f)
    except (OSError, ValueError):
        seen = {}
    key = lambda row: row["_kind"] + ":" + row["ID"]
    rows = list({key(r): r for r in rows}.values())  # 同じIDが2行あっても1回だけ

    # 今回確かめるもの：一度も確かめていない・URLが変わった・前回「正常」以外 は必ず。残りは確かめた日が古い順に全体の4分の1
    must, rest = [], []
    for row in rows:
        old = seen.get(key(row))
        (must if not old or old.get("url") != row["URL"] or old.get("status") != "正常" else rest).append(row)
    rest.sort(key=lambda r: (seen[key(r)].get("date", ""), r["ID"]))
    quota = -(-len(rows) // ROTATION)  # 全体の4分の1（切り上げ）
    todo = must + rest[:quota]

    def run(batch, budget):
        """ドメインごとにまとめ、ドメイン単位で並べて確かめる（同じドメインは順番に、間をあけて）。時間を過ぎたら開くのをやめる。"""
        deadline = time.monotonic() + budget
        by_host = collections.defaultdict(list)
        for row in batch:
            by_host[host_of(row["URL"])].append(row)
        out = {}
        def work(group):
            # 同じサイトが続けて GIVE_UP 回応答しなければ、そのサイトは自動の点検を受け付けないとみなし、
            # 残りは開かずに「拒否」として記録する（紀伊國屋書店など。ブラウザでは開けることが多い）
            done, silent = [], 0
            for row in group:
                if silent >= GIVE_UP:
                    done.append((key(row), NO_ANSWER))
                    continue
                if time.monotonic() > deadline:
                    break
                result = check_once(row["URL"])
                silent = silent + 1 if result[3] in ("応答がありません",) else 0
                done.append((key(row), result))
            if silent >= GIVE_UP:  # 応答しなかった分も、試し直さずに「拒否」にそろえる
                done = [(k, NO_ANSWER if r[3] == "応答がありません" else r) for k, r in done]
            return done
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for results in pool.map(work, by_host.values()):
                out.update(dict(results))
        return out

    started = time.monotonic()
    results = run(todo, BUDGET)
    retry = [row for row in todo if key(row) in results and results[key(row)][4]]
    if retry:  # 応答がない・サーバーの不具合だったものは、時間をおいてもう1回
        time.sleep(RETRY_WAIT)
        results.update(run(retry, RETRY_BUDGET))
    today = datetime.datetime.now(build.JST).date().isoformat()
    for row in todo:
        if key(row) in results:
            status, code, final, note, _ = results[key(row)]
            seen[key(row)] = {"date": today, "url": row["URL"], "status": status, "http_status": code, "final_url": final, "note": note}
    listed = {key(r) for r in rows}
    seen = {k: v for k, v in sorted(seen.items()) if k in listed}  # 掲載から外れたものは忘れる
    with open(SEEN, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=0)
        f.write("\n")

    summary = {"正常": 0, "移転": 0, "拒否": 0, "要確認": 0}
    voices_summary = dict.fromkeys(summary, 0)
    items, unchecked = [], 0
    for row in rows:
        rec = seen.get(key(row))
        if not rec or rec.get("url") != row["URL"]:
            unchecked += 1
            continue
        (voices_summary if row["_kind"] == "声" else summary)[rec["status"]] += 1
        if rec["status"] != "正常":
            items.append({"id": row["ID"], "kind": row["_kind"], "title": row["タイトル"], "url": row["URL"], "status": rec["status"],
                          "http_status": rec.get("http_status"), "final_url": rec.get("final_url", ""), "note": rec.get("note", ""),
                          "checked": rec["date"]})
    order = {"要確認": 0, "移転": 1, "拒否": 2}
    items.sort(key=lambda it: (order[it["status"]], it["id"]))
    data = {"checked_at": datetime.datetime.now(build.JST).replace(microsecond=0).isoformat(),
            "summary": summary, "voices_summary": voices_summary,
            "this_run": {"checked": sum(1 for r in todo if key(r) in results), "planned": len(todo),
                         "minutes": round((time.monotonic() - started) / 60, 1)},
            "unchecked": unchecked, "items": items}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("点検：今回 %d件（予定 %d件、%.1f分）、まだ一度も確かめていないもの %d件。最後に確かめた結果：観測所 %s／転機の声 %s"
          % (data["this_run"]["checked"], len(todo), data["this_run"]["minutes"], unchecked,
             "、".join("%s %d" % kv for kv in summary.items()), "、".join("%s %d" % kv for kv in voices_summary.items())))

    need = [it for it in items if it["status"] == "要確認"]
    if report_path and need:
        lines = ["掲載中のURLを %s に自動で開いて確かめました（今回 %d件。残りは週ごとに順番に確かめます）。" % (build.fmt_date(datetime.datetime.now(build.JST).date()), data["this_run"]["checked"]),
                 "結果（観測所の掲載）：" + "、".join("%s %d件" % kv for kv in summary.items()),
                 "結果（転機の声の記事）：" + "、".join("%s %d件" % kv for kv in voices_summary.items()),
                 "くわしい結果は %s/linkcheck.json でも見られます。サイトの掲載は自動では変えていません。" % build.BASE, "",
                 "## 要確認（ブラウザで開いて確かめてください）", "",
                 "自動の点検は GitHub のサーバーから開くため、ブラウザでは見られるのに「見つかりません」と出るサイトもあります。", "",
                 "| 種類 | ID | タイトル | URL | 内容 | 確かめた日 |", "|---|---|---|---|---|---|"]
        lines += ["| %s | %s | %s | %s | %s | %s |" % (it["kind"], it["id"], it["title"], it["url"], it["note"], it["checked"]) for it in need]
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
