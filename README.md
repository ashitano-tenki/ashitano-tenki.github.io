# あしたの転機観測所

https://ashitano-tenki.github.io/

キャリアの転機に役立つ民間のサービスや情報を、転機の種類と時期から探せるサイトです。スプレッドシート「あしたの転機観測所 データベース」の `公開用` タブ（ウェブに公開したCSV）を毎日読み込み、サイトを作り直しています。

## 自動更新

- 毎日、日本時間の朝5時ごろに自動で更新します（GitHub Actions の「サイトを更新」）。
- 手動で更新するときは、リポジトリの「Actions」タブ →「サイトを更新」→「Run workflow」を押します。
- CSVを取得できないとき、掲載中が0件のとき、前回の半分未満に減ったときは公開を止め、前回のサイトをそのまま残します。データを意図して大きく減らしたときは、手動実行の画面で「件数が前回の半分未満に減っても公開する」に印を付けて実行します。
- GitHub 側の公開の段階が失敗したときは、1分おいてもう一度だけ自動で試します。
- 公開の前に `tools/check_site.py` が作ったサイトを点検します（サイト内のリンク・画像の行き先、title・h1 の数、見出しの段の飛び、画像の alt、id の重複）。問題があっても公開は止めず、Issue「サイトの自動点検で問題が見つかりました」で知らせます（開いている Issue は1つだけで、問題がなくなると自動で閉じます）。
- 自動実行の環境は ubuntu-24.04 に固定し、使う部品（actions）は版の印（SHA）で固定しています。権限は、作る側（記録の保存・Issue）と公開する側（Pages）で分けています。

## リンク切れの点検

- 毎週月曜の朝6時、掲載中（状態が「確認済み」「要更新」）のURLを自動で開いて確かめます（GitHub Actions の「リンク切れの点検」。手動でも実行できます）。
- 1回ですべては開かず、新しい掲載と前回問題があったものは毎週、残りは4週で一巡します（20分で打ち切り、そこまでを保存）。確かめた日は `data/linkcheck_seen.json` に残ります。
- 結果は 正常／移転／拒否／要確認 の4つに分け、`https://ashitano-tenki.github.io/linkcheck.json` に公開します（正常以外の行だけを載せます）。データ側の定期実行がこれを読んで、壊れたリンクを直します。
- 要確認があったときは、リポジトリの「Issues」にも報告を作ります。Issue ができると、GitHub アカウントのメールに通知が届きます。
- サイトの掲載は自動では変えません。

## 掲載先の画像

- 毎朝の「サイトを更新」で、サイトを作る前に `tools/fetch_images.py` が、掲載先の公式ページに設定されているシェア用の画像（OGP画像）を取得します。縮小して `images/items/` に保存し、紹介ページ（タイトルの上）とカード（上の横長の枠）に出します。
- 取得するのは、まだ確かめていない掲載・取得から30日たったもの・取れなかったもので7日たったものだけです（1回150件まで、同じサイトには間をあけます）。結果は `data/images.json` に残ります。
- 本（URLにISBNがあるもの）は、どの書店のページでも紀伊國屋書店の表紙画像を使い、なければ Amazon の画像置き場の表紙を使います（書店のページの画像は店のロゴのことが多いため。`cover_urls`）。
- URLにISBNがない本（電子書籍のページなど）は、書名から国立国会図書館サーチの公開検索でISBNを引き、表紙を取ります。書名の本題・副題が掲載の書名と合うものだけを使います。
- 本の表紙がISBNで取れないとき（紀伊國屋にない本）は、ふつうにページを読みます。楽天市場の本（item.rakuten.co.jp/book/番号）は自動の取得を断るので、同じ番号の楽天ブックスのページ（books.rakuten.co.jp/rb/番号）から表紙を取ります。
- ちがう掲載なのに同じ画像になったものは「サイト共通の画像」として使わず、作業ページで画像を頼みます。トップ以外のページなのにサイト共通らしい画像（ogp・logo・default などの名前）は「確認したいもの」として作業ページに出し、合っていれば `config/site.json` の `image_keep` に入ります。
- 紀伊國屋書店の本（ISBNから表紙の場所が決まる）、Spotify の番組（公式の oEmbed）、YouTube の動画（サムネイル）は、ページを読まずに画像を取ります。
- 本・Podcast 以外で画像が取れないもの（サイト共通の画像だったものを含む）は、公式ページのいちばん上を画面なしの Chrome でキャプチャして使います（`capture_page`、1440×820。`data/images.json` に `"capture": true`）。ほぼ一色の画面は使いません。
- 画像がないものは、タイプの絵文字を同じ枠に出します。
- 短い辺が200px未満の小さな画像は「small」として、画像あつめで大きな画像をお願いします。
- 紹介ページごとの共有画像（SNSでシェアしたときの画像）は、毎朝 `tools/make_item_og.py` がタイトル・タイプ・転機から作ります（`og-items/`、リポジトリには入れない）。
- 自動で取れないものは、作業ページ「観測所の画像あつめ」（https://claude.ai/artifact/JjtpaqzyTvauJNwfQvZdXx ）で画像のURLを入れ、Claude Code に渡します。渡したURLは `config/image_overrides.json`（`{"ID": "画像のURL"}`）に入り、公式ページを読まずにその画像を使います。作業ページでアップロードした画像（キャプチャなど）は `images/manual/` に置き、`{"ID": "file:images/manual/ID.png"}` の形で同じように使います。
- おすすめ順は、画像があるものを先に、そのなかで観測スコアの高い順です（「観測所について」の並び順の考え方にも書いています）。
- 掲載先から申し出があったときなど、画像を使いたくない掲載は `config/site.json` の `image_exclude` にIDを書きます（例：`["R0007"]`）。次の更新で画像が消えます。

## 転機の声

- 転機を経験した人のインタビュー記事を並べるページ（/voices/）です。観測所の一覧・検索・並び順には混ぜません。記事の本文や写真は載せず、タイトル・リンク・分類・こちらで書いた要約だけを出します。
- データはスプレッドシート「あしたの転機観測所 転機の声データベース」の `公開用` タブ（確認済みの行だけ）をCSVで公開したもので、毎朝の「サイトを更新」で一緒に読み込みます。読めない日は `data/voices.csv`（前回の中身）を使います。
- ページ名・紹介文・CSVのURL・発信元ごとの注記は `config/site.json` の `voices` にまとめています。ページ名を変えると、メニューや紹介ページの見出しも変わります。
- メニューには記事の件数にかかわらず入口を出します。記事が0件のあいだはページに「準備中」と出し、検索エンジンには載せません（1件以上になると自動で載ります）。
- 観測所IDがある記事は、観測所の紹介ページに「この情報が出てくる転機の声」として最大5件出ます（それより多いときは一覧へのリンク）。
- サイトを作るたびに `/voices/index.json` も書き出します（転機AIが読む。/voices/ と同じ記事・同じ順。キーは id・title・speaker・before・after・tenki・dankai・trigger・age・job・industry・source・summary・url・media・published・items・keywords）。一覧ページの head にこの場所を書き、各カードに `data-id`（V番号）を持たせています。
- 毎週のリンク点検で記事のURLも確かめ、`linkcheck.json` に `"kind": "声"` で出します（観測所の掲載は `"kind": "観測所"`。件数は `summary` が観測所、`voices_summary` が転機の声）。

## 観測ノート

- 転機ごとのよくある迷いと、役立つ掲載を紹介する記事のページ（/notes/）です。記事は `notes/*.md`（名前が「_」で始まるファイルは公開しない）。書き方の決めごとは `notes/_guide.md`、テーマの一覧は `notes/_themes.md` です。
- 定期作業（tenki-kansoku-notes-draft）が 2026-11-15 から毎週日曜と木曜に1本ずつ書き、確認なしで公開します（2026-11-05 黒田さんの判断。2026-11-07 のふりかえりでも、このままと決まりました）。
- 記事のシェア画像は `python3 tools/make_og_images.py --notes` で `assets/og/note-<スラッグ>.png` に作ります。
- サイトを作るたびに `/notes/index.json`（転機AIが読む）も書き出します。紹介ページには、その掲載が出てくるノートへの帯が出ます。

## 転機AIとのつなぎ目

- 転機AI（キャリア相談のAI、Claude のアーティファクト）の中身は Cowork の担当です。観測所の担当は、入口とデータの渡し方です。
- 入口：メニュー・紹介ページ（末尾に #掲載ID）・探す・トップの4か所。URLは `config/site.json` の `tenki_ai_url`。押された数は GoatCounter に `tenki-ai/〇〇` で残ります。
- 転機AIが読むデータ（サイトを作るたびに書き出す）：
  - `/items.json`：掲載中の全件をおすすめ順で（id・title・kind・tenki・stages・memo・url・provider・for・added・rank・page）。観測スコアと料金は入れません。
  - `/voices/index.json`：転機の声（下の「転機の声」）。
  - `/notes/index.json`：観測ノート。

## あしたの転機プロジェクト

- 観測所を含む、黒田さんの「あしたの転機プロジェクト」のページ（/project/）です。noteマガジン・イベント・コミュニティなどの一覧は、スプレッドシートの別のタブ（`config/site.json` の `project_csv_url`）から作ります。読めない日は `data/project.csv` を使います。

## アクセス解析

- GoatCounter（Cookie を使わない）で、見たページと、押されたもの（公式サイト・転機AI・あとで見る・共有・役に立った・探すページの検索語など）を数えます。`assets/count.js` は GoatCounter の公式のものに手を加え、URLの「?」以降は来た元（ref・utm）以外を送りません。

## AIのクローラー

- `robots.txt` で、AIの学習用のクローラー（GPTBot・ClaudeBot・Google-Extended・CCBot など）だけを断っています（2026-11-06 黒田さんの判断。コミュニティ図鑑と同じ）。一覧は `build.py` の `AI_TRAINING` です。
- AIの検索用のクローラー（OAI-SearchBot・Claude-SearchBot・PerplexityBot など）と、ふつうの検索エンジンは通します。AIの検索の答えに観測所が出典として出る道を残すためです。検索用まで断らないでください。
- robots.txt はお願いなので、守らない相手は止められません。転機AIなど、利用者のブラウザからの読み込みには影響しません。

## ファイルの役割

| ファイル | 中身 |
|---|---|
| `config/site.json` | サイト名、説明文、CSVのURL、誤り報告・問い合わせフォームのURL、転機AIのURL、アクセス解析のコード、転機の声とプロジェクトのCSVのURL、新着の日数、掛け合わせページを作る最低件数、画像の例外、種類（タイプ）の一覧（表示順・説明文・絵文字・リンクの文言）、トップの「こんな言葉で探せます」など。項目ごとの説明は「_〇〇 の説明」に書いてあります。ここにない種類のデータは表示しない |
| `config/image_overrides.json` | 画像あつめで渡してもらった画像（`{"ID": "画像のURL"}` または `"file:images/manual/ID.png"`） |
| `config/tenki.json` | 転機の種類と段階の名前・URL・ページの文面 |
| `config/tenki_notes.json` | 転機別ページと、転機×段階のページに載せる解説文 |
| `config/synonyms.json` | 検索の言い換え表（毎朝の更新で、言葉と掲載に漢字の読みを足すので、ひらがなでも探せる） |
| `build.py`・`sitegen/` | サイトを作るスクリプト。build.py は入口と全体の流れで、ページの作り方は sitegen/ に分けてあります（core：設定とデータの読み込み、parts：ヘッダー・カードなどの部品、pages：トップ・転機・紹介ページ・探すなど、notes・voices・project：観測ノート・転機の声・あしたの転機、output：検索用データ・RSS・サイトマップなど）。ページの文面の多くもここにあります |
| `check/index.html`・`check/check.js`・`config/check.json` | 転機の段階セルフチェック（/check/）。ページの枠が index.html、動きが check.js、質問・判定・結果の文章が config/check.json です。結果画面のおすすめは、サイトを作るたびに書き出す `/check/picks.json` から選びます。2026-11-06 からメニューには出していません（ページと入口の一部は残す） |
| `assets/` | 見た目（style.css）、探すページの動き（search.js。一覧は `/search.json`、キーワード検索用の文字は `/search-text.json` から）、転機の声の動き（voices.js）、全ページ共通の動き（site.js）、アクセス解析（count.js）、アイコン、SNS共有用の画像 |
| `notes/` | 観測ノートの記事と、書き方の決めごと |
| `tools/` | 画像の取得（fetch_images.py）、共有画像づくり（make_item_og.py・make_og_images.py）、画像あつめの反映（apply_manual_images.py）、リンク点検（check_links.py）、サイトの点検（check_site.py） |
| `assets/og/` | 転機別ページと掛け合わせページのSNS共有用画像。`config/tenki.json` の名前や見出しを変えたら、Macで `python3 tools/make_og_images.py` を実行して作り直す |
| `data/meta.json` | 前回公開したときの件数（件数チェックに使います） |
| `data/linkcheck.json`・`data/linkcheck_seen.json` | 毎週のリンク点検の結果（サイトでは /linkcheck.json として公開）と、掲載ごとの最後に確かめた日 |
| `data/images.json`・`images/items/` | 掲載先の画像の取得結果と、縮小した画像（`{ID}.webp` は紹介ページ用、`{ID}-s.webp` はカードの上の画像用（軽い WebP 形式）） |
| `data/latest.csv` | 毎日読み込んだデータの写し（観測スコアの列は除く）。履歴から、何がいつ変わったかを確かめられます |
| `data/voices.csv`・`data/project.csv` | 転機の声とプロジェクトのデータの写し（読めない日に使う） |

## 手元で試す

Claude Code の作業場所は `~/tenki-work` です（リポジトリの写し・Python の環境・gh。中身と作り直し方は `~/tenki-work/README.md`）。

```bash
~/tenki-work/venv/bin/python build.py
python3 -m http.server 8765 --directory _site
```

`data/meta.json` が変わりますが、手元の確認用なのでコミットしません。

## 画像の出典

ロゴ・ファビコン・SNS共有用画像の📡は、Google の [Noto Emoji](https://github.com/googlefonts/noto-emoji)（Apache License 2.0）の画像を使っています。
