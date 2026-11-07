#!/usr/bin/env python3
"""あしたの転機観測所のサイトを作るスクリプト。

公開用CSVを読み込み、_site/ に静的なHTMLを書き出す。
Python の標準ライブラリだけで動く。ページの作り方は sitegen/ にある（このファイルは入口と全体の流れ）。

  python3 build.py                 # CSVをネットから取得して作る
  python3 build.py --csv data.csv  # 手元のCSVから作る
  python3 build.py --allow-decrease  # 件数が大きく減っても公開を止めない
"""
import argparse
import datetime
import json
import os
import shutil
import sys

# ページの作り方は sitegen/ に分けてある（core：設定とデータ、parts：部品、pages：主なページ、notes・voices・project：それぞれのページ、output：ページ以外の書き出し）。
# tools/ のスクリプトが build.〇〇 で使えるよう、すべての名前をここに読み込む
from sitegen.core import *  # noqa: F401,F403
from sitegen.parts import *  # noqa: F401,F403
from sitegen.project import *  # noqa: F401,F403
from sitegen.notes import *  # noqa: F401,F403
from sitegen.voices import *  # noqa: F401,F403
from sitegen.pages import *  # noqa: F401,F403
from sitegen.output import *  # noqa: F401,F403


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="手元のCSVファイルを使う")
    ap.add_argument("--allow-decrease", action="store_true", help="件数が大きく減っても公開する")
    ap.add_argument("--today", help="今日の日付（確認用。例: 2026-10-22）")
    ap.add_argument("--save-data", action="store_true",
                    help="読み込んだCSVを data/latest.csv に残す（毎日の自動更新で使い、変更の履歴にする）")
    ap.add_argument("--voices-csv", help="転機の声に手元のCSVファイルを使う（確認用）")
    ap.add_argument("--drafts", action="store_true", help="観測ノートの下書き（draft: true）も、検索に出ない形で作る（確認用）")
    args = ap.parse_args()

    if args.csv:
        with open(args.csv, encoding="utf-8-sig") as f:
            text = f.read()
    else:
        text = fetch_csv(CONF["csv_url"])
    items = parse_rows(text)
    listed = [it for it in items if it["listed"]]
    check_counts(items, listed, args.allow_decrease)

    today = (datetime.date.fromisoformat(args.today) if args.today
             else datetime.datetime.now(JST).date())
    since = today - datetime.timedelta(days=CONF["new_days"] - 1)
    new_items = [it for it in listed if it["added"] and since <= it["added"] <= today]
    ctx = {
        "today": today,
        "version": assets_version(),
        "sitemap": [],
        "new_items": new_items,
        "new_ids": {it["id"] for it in new_items},
        "tenki_count": {t["name"]: sum(1 for it in listed if matches_tenki(it, t["name"])) for t in TENKI},
        "notes": load_notes(listed, args.drafts),
        "voices": parse_voices(voices_text(args.voices_csv)),
        "item_ids": {it["id"] for it in items},  # 紹介ページがある掲載ID（転機の声の JSON の items に使う）
    }


    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(os.path.join(ROOT, "assets"), os.path.join(OUT, "assets"))
    # 紹介ページごとの共有画像（tools/make_item_og.py が og-items/ に作る。なければ作らない）
    og_dir = os.path.join(ROOT, "og-items")
    if os.path.isdir(og_dir):
        shutil.copytree(og_dir, os.path.join(OUT, "images", "og"))
    # 掲載先の画像（画像が取れて、除外していないものだけ）
    os.makedirs(os.path.join(OUT, "images", "items"))
    for item_id in IMAGES:
        for name in (item_id + ".webp", item_id + "-s.webp"):
            shutil.copy2(os.path.join(ROOT, "images", "items", name), os.path.join(OUT, "images", "items", name))

    build_home(listed, ctx)
    build_search(listed, ctx)
    build_tenki(listed, ctx)
    for it in items:
        build_item(it, listed, ctx)
    build_report(listed, ctx)
    build_about(listed, ctx)
    build_404(ctx)
    build_saved(ctx)
    build_guide(listed, ctx)
    build_project(ctx)
    build_notes(ctx["notes"], listed, ctx)
    build_voices(ctx["voices"], listed, ctx)
    build_check(listed, ctx)
    build_search_json(listed, ctx)
    write_items_json(listed, ctx)
    build_feed(listed, ctx)
    build_meta_files(ctx)

    meta = {"built": today.isoformat(), "total": len(items), "listed": len(listed)}
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    with open(os.path.join(ROOT, "data", "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")
    if args.save_data:
        save_snapshot(text)
        if VOICES_TEXT.get("text"):
            with open(VOICES_SNAPSHOT, "w", encoding="utf-8") as f:
                f.write(VOICES_TEXT["text"])
        if PROJECT_TEXT.get("text"):
            with open(PROJECT_SNAPSHOT, "w", encoding="utf-8") as f:
                f.write(PROJECT_TEXT["text"])
    print("作成しました: 全%d件（掲載中%d件、今週の新着%d件、%s %d件、ページ%d枚）"
          % (len(items), len(listed), len(new_items), VOICES_LABEL, len(ctx["voices"]), len(ctx["sitemap"])))


if __name__ == "__main__":
    try:
        main()
    except BuildError as ex:
        print("中止: %s" % ex, file=sys.stderr)
        sys.exit(1)
