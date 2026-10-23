#!/usr/bin/env python3
"""掲載中のURLが開けるかを確かめ、結果を data/linkcheck.json に書くスクリプト（毎週の自動点検で使う）。

  python3 tools/check_links.py [report.md]

- 対象：公開用CSVのうち「状態」が「確認済み」「要更新」の行の「URL」列。
- 結果は 正常／移転／拒否／要確認 の4つに分ける。linkcheck.json の items には「正常」以外だけを入れる。
- 「要確認」があったときは、Issue 用の report.md も書く（引数で指定したとき）。
- スプレッドシートやサイトの掲載は変えない。直すかどうかは、データ側の定期実行が判断する。
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
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
           "Accept-Language": "ja,en-US;q=0.8,en;q=0.6"}
TIMEOUT = 15          # 1件あたりの待ち時間（秒）
WORKERS = 4           # 同時に確かめるドメインの数（相手に負担をかけないよう少なめ）
DOMAIN_GAP = 2.0      # 同じドメインに続けてアクセスするときの間隔（秒）
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
            rows.append(row)

    def run(batch):
        """ドメインごとにまとめ、ドメイン単位で並べて確かめる（同じドメインは順番に、間をあけて）。"""
        by_host = collections.defaultdict(list)
        for row in batch:
            by_host[host_of(row["URL"])].append(row)
        out = {}
        def work(group):
            return [(row["ID"], check_once(row["URL"])) for row in group]
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for results in pool.map(work, by_host.values()):
                out.update(dict(results))
        return out

    results = run(rows)
    retry = [row for row in rows if results[row["ID"]][4]]
    if retry:  # 応答がない・サーバーの不具合だったものは、時間をおいてもう1回
        time.sleep(RETRY_WAIT)
        results.update(run(retry))

    summary = {"正常": 0, "移転": 0, "拒否": 0, "要確認": 0}
    items = []
    for row in rows:
        status, code, final, note, _ = results[row["ID"]]
        summary[status] += 1
        if status != "正常":
            items.append({"id": row["ID"], "title": row["タイトル"], "url": row["URL"], "status": status,
                          "http_status": code, "final_url": final, "note": note})
    order = {"要確認": 0, "移転": 1, "拒否": 2}
    items.sort(key=lambda it: (order[it["status"]], it["id"]))
    data = {"checked_at": datetime.datetime.now(build.JST).replace(microsecond=0).isoformat(),
            "summary": summary, "items": items}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("点検 %d件：%s" % (len(rows), "、".join("%s %d" % kv for kv in summary.items())))

    need = [it for it in items if it["status"] == "要確認"]
    if report_path and need:
        lines = ["掲載中のURLを %s に自動で開いて確かめました（%d件）。" % (build.fmt_date(datetime.datetime.now(build.JST).date()), len(rows)),
                 "結果：" + "、".join("%s %d件" % kv for kv in summary.items()),
                 "くわしい結果は %s/linkcheck.json でも見られます。サイトの掲載は自動では変えていません。" % build.BASE, "",
                 "## 要確認（ブラウザで開いて確かめてください）", "",
                 "自動の点検は GitHub のサーバーから開くため、ブラウザでは見られるのに「見つかりません」と出るサイトもあります。", "",
                 "| ID | タイトル | URL | 内容 |", "|---|---|---|---|"]
        lines += ["| %s | %s | %s | %s |" % (it["id"], it["title"], it["url"], it["note"]) for it in need]
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
