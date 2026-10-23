#!/usr/bin/env python3
"""掲載中の公式サイトのURLを開き、つながらないものを報告するスクリプト（毎週の自動点検で使う）。

  python3 tools/check_links.py report.md

問題が見つかったときは report.md に報告を書き、終了コード 0 で終える。
問題がなければ report.md は作らない。スプレッドシートやサイトは変えない。
"""
import concurrent.futures
import datetime
import os
import socket
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build  # noqa: E402  CSVの読み込みは build.py と同じものを使う

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36 tenki-kansoku-linkcheck")


def fetch(url):
    """(分類, くわしい内容) を返す。分類は ok / broken / blocked。"""
    last = None
    for _ in range(2):  # 一時的な失敗に備えて2回まで試す
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja,en;q=0.8"})
            with urllib.request.urlopen(req, timeout=25) as res:
                res.read(2048)
                return "ok", str(res.status)
        except urllib.error.HTTPError as ex:
            if ex.code in (404, 410):
                return "broken", "ページが見つかりません（%d）" % ex.code
            if ex.code in (401, 403, 405, 429):
                return "blocked", "自動の確認を受け付けていません（%d）" % ex.code
            last = ("broken", "サーバーの不具合（%d）" % ex.code)
        except (socket.timeout, TimeoutError) as ex:
            # 自動の確認にだけ応答しないサイトがある（ブラウザで開けば見られることが多い）
            last = ("blocked", "応答がありません")
        except (urllib.error.URLError, ConnectionError) as ex:
            reason = getattr(ex, "reason", ex)
            if isinstance(reason, (socket.timeout, TimeoutError)):
                last = ("blocked", "応答がありません")
            elif isinstance(reason, socket.gaierror):
                last = ("broken", "ドメインが見つかりません（サイトが閉鎖されたか、URLの誤りの可能性）")
            else:
                last = ("broken", "つながりません（%s）" % reason)
        except Exception as ex:  # 予想外の失敗も報告に残す
            last = ("broken", "確認できませんでした（%s）" % ex)
    return last


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "link-report.md"
    items = [it for it in build.parse_rows(build.fetch_csv(build.CONF["csv_url"])) if it["listed"]]
    targets = [it for it in items if it["url"]]
    no_url = [it for it in items if not it["url"]]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda it: (it, fetch(it["url"])), targets))
    broken = [(it, d) for it, (k, d) in results if k == "broken"]
    blocked = [(it, d) for it, (k, d) in results if k == "blocked"]
    print("点検 %d件：つながらない %d件、自動では確認できない %d件、URLなし %d件"
          % (len(targets), len(broken), len(blocked), len(no_url)))
    if not broken and not no_url:
        return
    today = datetime.datetime.now(build.JST).date()
    lines = ["掲載中の公式サイトを %s に自動で開いて確かめました（%d件）。" % (build.fmt_date(today), len(targets)),
             "スプレッドシートは変えていません。内容を確かめ、必要ならスプレッドシートの状態を「要更新」や「非公開」にしてください。", ""]
    if broken:
        lines += ["## つながらなかったもの（ブラウザで開いて確かめてください）", "",
                  "自動の点検は GitHub のサーバーから開くため、ブラウザでは見られるのに「見つかりません」と出るサイトもあります。"
                  "「ドメインが見つかりません」は、サイトの閉鎖やURLの誤りの可能性が高いものです。", "",
                  "| ID | タイトル | URL | 内容 |", "|---|---|---|---|"]
        lines += ["| %s | %s | %s | %s |" % (it["id"], it["title"], it["url"], d) for it, d in broken]
        lines.append("")
    if no_url:
        lines += ["## 公式サイトのURLがないもの", ""]
        lines += ["- %s %s" % (it["id"], it["title"]) for it in no_url]
        lines.append("")
    if blocked:
        lines += ["## 参考：自動では確認できなかったサイト", "",
                  "自動の確認を受け付けない、または応答しなかったサイトです。ブラウザで開けば見られることが多いので、問題とは限りません。", ""]
        lines += ["- %s %s（%s）" % (it["id"], it["title"], d) for it, d in blocked]
        lines.append("")
    lines.append("一時的な不具合のこともあるので、翌週も同じものが出たら対応を検討してください。")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
