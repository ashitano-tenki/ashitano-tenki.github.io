# あしたの転機観測所

https://ashitano-tenki.github.io/

キャリアの転機に役立つ民間のサービスや情報を、転機の種類と時期から探せるサイトです。スプレッドシート「あしたの転機観測所 データベース」の `公開用` タブ（ウェブに公開したCSV）を毎日読み込み、サイトを作り直しています。

## 自動更新

- 毎日、日本時間の朝5時ごろに自動で更新します（GitHub Actions の「サイトを更新」）。
- 手動で更新するときは、リポジトリの「Actions」タブ →「サイトを更新」→「Run workflow」を押します。
- CSVを取得できないとき、掲載中が0件のとき、前回の半分未満に減ったときは公開を止め、前回のサイトをそのまま残します。データを意図して大きく減らしたときは、手動実行の画面で「件数が前回の半分未満に減っても公開する」に印を付けて実行します。

## ファイルの役割

| ファイル | 中身 |
|---|---|
| `config/site.json` | サイト名、説明文、CSVのURL、誤り報告フォームのURL、noteとFacebookグループのURL、新着の日数、掛け合わせページを作る最低件数など |
| `config/tenki.json` | 転機の種類と段階の名前・URL・ページの文面 |
| `config/synonyms.json` | 検索の言い換え表 |
| `build.py` | サイトを作るスクリプト（ページの文面の多くもここにあります） |
| `check/index.html` | 転機の段階セルフチェック（/check/）。質問・判定・結果の文章はこのファイルにあります。結果画面のおすすめは、サイトを作るたびに書き出す `check/picks.json` から選びます |
| `assets/` | 見た目（style.css）、検索の動き（search.js）、アイコン、SNS共有用の画像 |
| `assets/og/` | 転機別ページと掛け合わせページのSNS共有用画像。`config/tenki.json` の名前や見出しを変えたら、Macで `python3 tools/make_og_images.py` を実行して作り直す |
| `data/meta.json` | 前回公開したときの件数（件数チェックに使います） |

## 手元で試す

```bash
python3 build.py
python3 -m http.server 8765 --directory _site
```

## 画像の出典

ロゴ・ファビコン・SNS共有用画像の📡は、Google の [Noto Emoji](https://github.com/googlefonts/noto-emoji)（Apache License 2.0）の画像を使っています。
