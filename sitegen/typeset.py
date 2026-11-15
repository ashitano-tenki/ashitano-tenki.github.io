"""見出しの組み方（2026-11-15 の改善の見本で採用した案14・15）。

- 文節で改行する（案15）：BudouX（Google の文節区切り）で題名を文節に分け、切れ目に <wbr> を入れて `word-break: keep-all` で折り返す。
  CSS の `word-break: auto-phrase` は Chrome だけなので、iPhone の Safari や Firefox でも「スポットコンサ／ル」のように言葉の途中で折り返さないようにする。
  BudouX はサイトを作るときに手元で動くだけで、ページを開く人の通信は増えない。入っていない環境では <wbr> を入れずに作る（見た目は今までと同じ）。
- 約物を詰める（案14）：見出しの書体 Zen Kaku Gothic New（Google Fonts 版）には palt も約物の半角詰めもない（2026-11-15 に実測）。
  そのため、見出しの約物を <span class="yk"> で包み、style.css の負の余白で半分ほど詰める（閉じ括弧と句読点は右を、開き括弧は左を）。

使うのは見出しの書体の部分（カードの題名・紹介ページの見出し・観測ノートの見出し）だけ。aria-label・title・og:title・検索のデータには使わない。
JS で作るカード（探す・あとで見る）は、search.json の "wb"（文節の切れ目の位置）を使って同じ形にする（assets/search.js・site.js）。
"""
import html

try:
    import budoux
    _PARSER = budoux.load_default_japanese_parser()
except Exception:  # 入っていない環境（.venv が作れなかったときなど）では文節に分けない
    _PARSER = None

OPEN = "「『（［【〔〈《“‘"
CLOSE = "」』）］】〕〉》”’"
PUNCT = "、。，．"


def break_points(text):
    """文節の切れ目の位置（文字の番号。0 と末尾は含めない）。開き括弧の直後・閉じ括弧と句読点の直前には切れ目を置かない"""
    if not _PARSER or not text:
        return []
    cand, pos = set(), 0
    for ph in _PARSER.parse(text)[:-1]:
        pos += len(ph)
        cand.add(pos)
    # BudouX は中黒（・）とスラッシュで切らないので、そのあとも切れ目にする（「スポットコンサル・副業プラットフォーム」が1つの塊にならないように）
    cand |= {i + 1 for i, ch in enumerate(text) if ch in "・/／"}
    return sorted(p for p in cand if 0 < p < len(text) and text[p - 1] not in OPEN and text[p] not in CLOSE + PUNCT)


def _yk(ch):
    if ch in CLOSE:
        return '<span class="yk">%s</span>' % html.escape(ch)
    if ch in PUNCT:
        return '<span class="yk yk-p">%s</span>' % html.escape(ch)
    if ch in OPEN:
        return '<span class="yk yk-o">%s</span>' % html.escape(ch)
    return html.escape(ch)


def heading(text, wrap=True):
    """見出しの文字を、文節の切れ目に <wbr>、約物を <span class="yk"> で包んだ HTML にする。
    wrap=True は全体を <span class="wb">（keep-all で折り返す）で包む。外側の要素がすでに keep-all のとき（観測ノートの見出し）は wrap=False"""
    text = text or ""
    points = set(break_points(text))
    out = "".join(("<wbr>" if i in points else "") + _yk(ch) for i, ch in enumerate(text))
    return '<span class="wb">%s</span>' % out if wrap else out
