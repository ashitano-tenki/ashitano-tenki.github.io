// 一覧ページ：search.json を読み込み、ブラウザの中で絞り込みと検索をする
(function () {
  document.documentElement.classList.add("js");
  var PAGE = window.TENKI_PAGE_SIZE || 20;
  var THIS_YEAR = window.TENKI_THIS_YEAR || new Date().getFullYear();
  var FIELDS = ["q", "tenki", "stage", "kind", "sort"];
  var form = document.getElementById("filters");
  // 「絞り込む」の中にある条件（押すだけのボタン。中身はラジオボタン）
  var FILTERS = ["tenki", "stage", "kind"].filter(function (f) { return form.querySelector('[name="' + f + '"]'); });
  var LABELS = { kind: "タイプ", tenki: "転機", stage: "段階" };
  var COMMON = "共通", OTHER = "その他";
  var list = document.getElementById("results");
  var countEl = document.getElementById("result-count");
  var moreBtn = document.getElementById("more");
  var chipsEl = document.getElementById("active-chips");
  var toggle = document.getElementById("filter-toggle");
  var panel = document.getElementById("filter-panel");
  var filterCount = document.getElementById("filter-count");
  var zeroHelp = document.createElement("div");
  zeroHelp.className = "zero-help";
  zeroHelp.hidden = true;
  chipsEl.parentNode.insertBefore(zeroHelp, chipsEl.nextSibling);
  var data = null, results = [], shown = 0, byNew = false;  // byNew: 新着順のときだけカードに追加日を出す
  var ownCount = -1;  // 転機で絞ったとき、その転機ならではの件数（ここで「どの転機にも役立つもの」の区切りを入れる）。区切らないときは -1
  var startHelp = document.getElementById("start-help");
  var synNote = document.getElementById("syn-note");
  var suggestEl = document.getElementById("suggest");
  var qInput = document.getElementById("q");

  function normalize(s) {
    s = (s || "").normalize("NFKC").toLowerCase();
    return s.replace(/[ぁ-ゖ]/g, function (c) { return String.fromCharCode(c.charCodeAt(0) + 0x60); });
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  // 絵文字を Noto の画像で出す（build.py の emoji_img と同じファイル名。assets/emoji/ に置いてある）
  function emoImg(s) {
    if (!s) return "";
    var cps = [];
    Array.from(s).forEach(function (ch) { var c = ch.codePointAt(0); if (c === 0xfe0f) return; var h = c.toString(16); cps.push(h.length < 4 ? ("000" + h).slice(-4) : h); });
    return '<img class="emo" src="/assets/emoji/' + cps.join("_") + '.svg" alt="' + esc(s) + '" draggable="false">';
  }

  // 言い換え表を使って、検索語ごとに一緒に探す言葉を集める
  function alternatives(term) {
    var alts = [term];
    data.synonyms.forEach(function (group) {
      // 前の形（言葉の並びだけ）の search.json がブラウザに残っていても動くように
      if (Array.isArray(group)) group = { words: group, readings: [] };
      var hit = group.words.concat(group.readings).some(function (w) { return w === term || (term.length >= 2 && w.indexOf(term) >= 0); });
      if (hit) group.words.forEach(function (w) { if (alts.indexOf(w) < 0) alts.push(w); });
    });
    return alts;
  }

  function readParams() {
    var p = new URLSearchParams(location.search), state = {};
    FIELDS.forEach(function (f) { state[f] = p.get(f) || ""; });
    return state;
  }

  // ラジオボタンの組で、値が v のものを選ぶ（RadioNodeList の value に "" を入れても「すべて」は選ばれないため）
  function setRadio(name, v) {
    var hit = Array.prototype.filter.call(form.querySelectorAll('input[name="' + name + '"]'), function (x) { return x.value === v; })[0];
    if (hit) hit.checked = true;
    return !!hit;
  }

  function writeForm(state) {
    FIELDS.forEach(function (f) {
      var el = form.elements[f];
      if (!el) return;
      if (FILTERS.indexOf(f) >= 0) { if (!setRadio(f, state[f])) setRadio(f, ""); return; }
      if (el.type === "checkbox") { el.checked = state[f] === "1"; return; }
      if (el.tagName === "SELECT" && state[f] && !Array.prototype.some.call(el.options, function (o) { return o.value === state[f]; })) {
        el.add(new Option(state[f], state[f]));
      }
      el.value = state[f];
    });
  }

  function readForm() {
    var state = {};
    FIELDS.forEach(function (f) {
      var el = form.elements[f];
      if (!el) { state[f] = ""; return; }  // ページにない条件は空
      state[f] = el.type === "checkbox" ? (el.checked ? "1" : "") : (el.value || "").trim();
    });
    return state;
  }

  function updateUrl(state) {
    var p = new URLSearchParams();
    FIELDS.forEach(function (f) { if (state[f]) p.set(f, state[f]); });
    var qs = p.toString();
    history.replaceState(null, "", location.pathname + (qs ? "?" + qs : ""));
  }

  function matchTenki(item, name) {
    if (item.tenki.indexOf(name) >= 0) return true;
    return name !== COMMON && name !== OTHER && item.tenki.indexOf(COMMON) >= 0;
  }

  function match(state) {
    var terms = normalize(state.q).split(/\s+/).filter(Boolean).map(alternatives);
    return data.items.filter(function (it) {
      if (state.kind && it.kind !== state.kind) return false;
      if (state.tenki && !matchTenki(it, state.tenki)) return false;
      if (state.stage && it.stages.indexOf(state.stage) < 0) return false;
      return terms.every(function (alts) {
        return alts.some(function (w) { return it.text.indexOf(w) >= 0; });
      });
    });
  }

  function without(state, field) {
    var s = {};
    for (var k in state) s[k] = state[k];
    s[field] = "";
    return s;
  }

  // ボタンごとに「それを選んだら何件になるか」を付け、0件になるものは押せなくする
  function updateCounts(state) {
    FILTERS.forEach(function (f) {
      var base = without(state, f);
      Array.prototype.forEach.call(form.querySelectorAll('input[name="' + f + '"]'), function (input) {
        var s = without(base, f);
        s[f] = input.value;
        var n = match(s).length;
        input.parentNode.querySelector("i").textContent = n;
        input.disabled = n === 0 && input.value !== state[f];
        input.parentNode.classList.toggle("off", input.disabled);
      });
    });
  }

  // 0件のとき、どの条件を外せば見つかるかを示す
  // こんな言葉で探せます（config/site.json の start_words）。0件のときは、この中からランダムに8つを出す
  var POPULAR = (window.TENKI_POPULAR || ["転職エージェント", "確定申告", "コーチング", "学び直し"]).slice().sort(function () { return Math.random() - 0.5; }).slice(0, 8);

  function renderZeroHelp(state) {
    var hints = [];
    if (!results.length) {
      var onlyQ = state.q && !FILTERS.some(function (f) { return state[f]; });
      ["q"].concat(FILTERS).forEach(function (f) {
        if (!state[f] || (f === "q" && onlyQ)) return;  // キーワードだけのときは「外すと全件」は出さない
        var n = match(without(state, f)).length;
        if (n) hints.push('<button type="button" class="relax-btn" data-field="' + f + '">' + esc(chipText(f, state)) + "を外すと <b>" + n + "件</b></button>");
      });
    }
    var html = hints.length ? "<span>条件を1つ外すと見つかります：</span>" + hints.join("") : "";
    // キーワードだけで0件のときは、こんな言葉で探せますの言葉と「転機から探す」を出して、すぐに探し直せるようにする
    if (!results.length && state.q) {
      html += (html ? '<span class="zero-break"></span>' : "") + "<span>こんな言葉で探せます：</span>" + POPULAR.map(function (w) {
        return '<a class="zero-word" href="?q=' + encodeURIComponent(w) + '">' + esc(w) + "</a>";
      }).join("") + '<a class="zero-word" href="/tenki/">転機から探す</a>';
    }
    zeroHelp.hidden = !html;
    zeroHelp.innerHTML = html;
  }

  function filter(state) {
    ownCount = -1;
    var out = match(state);
    if (state.sort === "new") {
      out.sort(function (a, b) { return a.added < b.added ? 1 : a.added > b.added ? -1 : a.rank - b.rank; });
    } else {
      // キーワードがあるときは「タイトルにそのままある → 説明などにそのままある → 言い換えで当たった」の順に、そのなかをおすすめ順に
      var terms = normalize(state.q).split(/\s+/).filter(Boolean);
      var tier = function (it) {
        if (!terms.length) return 0;
        var title = normalize(it.title);
        if (terms.every(function (t) { return title.indexOf(t) >= 0; })) return 0;
        if (terms.every(function (t) { return it.text.indexOf(t) >= 0; })) return 1;
        return 2;
      };
      out.forEach(function (it) { it._tier = tier(it); });
      // 転機で絞ったときは、その転機ならではの掲載を先に、どの転機にも役立つ共通の掲載を後に（転機のページと同じ並び）
      var t = state.tenki, split = t && t !== COMMON && t !== OTHER;
      var grp = function (it) { return split && it.tenki.indexOf(t) < 0 ? 1 : 0; };
      // キーワードがあるときは観測スコアの順（srank）のまま。ないときは、同じ転機・提供元が続かないよう並べ直した順（rank）
      var key = terms.length ? function (it) { return it.srank || it.rank; } : function (it) { return it.rank; };
      out.sort(function (a, b) { return grp(a) - grp(b) || a._tier - b._tier || key(a) - key(b); });
      if (split) {
        ownCount = out.filter(function (it) { return grp(it) === 0; }).length;
        if (ownCount === 0 || ownCount === out.length) ownCount = -1;
      }
    }
    return out;
  }

  function whenLine(it) {
    var tenki = it.tenki.indexOf(COMMON) >= 0 ? "どの転機にも" : it.tenki.join("、");
    return [tenki, it.stages.join("、")].filter(Boolean).join("｜");
  }

  function addedLabel(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
    if (!m) return "";
    var y = +m[1], mo = +m[2], d = +m[3];
    return (y === THIS_YEAR ? "" : y + "年") + mo + "月" + d + "日に追加";
  }

  // カードの上の画像（掲載先のシェア用画像）。画像がなければタイプの絵文字（build.py の item_media と同じ形）
  function mediaHtml(img) {
    img = img || {};
    if (img.src) return '<div class="card-media media-' + esc(img.fit) + '" aria-hidden="true"><img src="' + esc(img.src) + '" alt="" loading="lazy" decoding="async"></div>';
    return '<div class="card-media media-none" aria-hidden="true"><span>' + emoImg(img.emoji) + "</span></div>";
  }
  // 探した言葉が当たったところを <strong class="hit"> で包む（2026-11-15 見本の案5。太字と空色の下線。黄色の蛍光ペンは使わない）。
  // 元の文字を1字ずつ normalize し、そろえた文字の位置を元の文字の位置に対応させて包む
  var hlWords = [];
  // 題名（head=true）は、文節の切れ目（search.json の wb）に <wbr> を入れ、約物を <span class="yk"> で包む（sitegen/typeset.py と同じ。案14・15）
  var OPEN = "「『（［【〔〈《“‘", CLOSE = "」』）］】〕〉》”’", PUNCT = "、。，．";
  function ykChar(ch) {
    if (CLOSE.indexOf(ch) >= 0) return '<span class="yk">' + esc(ch) + "</span>";
    if (PUNCT.indexOf(ch) >= 0) return '<span class="yk yk-p">' + esc(ch) + "</span>";
    if (OPEN.indexOf(ch) >= 0) return '<span class="yk yk-o">' + esc(ch) + "</span>";
    return esc(ch);
  }
  function mark(s, head, wb) {
    var points = {};
    (wb || []).forEach(function (p) { points[p] = true; });
    if (!hlWords.length && !head) return esc(s);
    var chars = Array.from(s || ""), norm = "", map = [], on = [];
    chars.forEach(function (ch, i) { var n = normalize(ch); for (var k = 0; k < n.length; k++) map.push(i); norm += n; on.push(false); });
    hlWords.forEach(function (w) {
      var p = norm.indexOf(w);
      while (p >= 0) { for (var k = p; k < p + w.length; k++) on[map[k]] = true; p = norm.indexOf(w, p + w.length); }
    });
    var out = "", open = false;
    chars.forEach(function (ch, i) {
      if (!on[i] && open) { out += "</strong>"; open = false; }
      if (head && points[i]) out += "<wbr>";
      if (on[i] && !open) { out += '<strong class="hit">'; open = true; }
      out += head ? ykChar(ch) : esc(ch);
    });
    out += open ? "</strong>" : "";
    return head ? '<span class="wb">' + out + "</span>" : out;
  }
  // カードに出ている題名と説明の1文目とタイプの札に、探した言葉（言い換えを含む）が1つも見えないとき、説明の中で当たった文を短く添える。
  // 当たった理由がカードから分かるように（2026-11-15）。言葉ごとに見て、見えない言葉があれば、その言葉が最初に出る文を使う
  var hlGroups = [];
  var SNIP_MAX = 64, SNIP_BEFORE = 20;
  function snippet(it) {
    if (!it.memo || !hlGroups.length) return "";
    var shown = normalize(it.title + " " + String(it.line || "").replace(/…$/, "") + " " + it.kind);
    var hidden = [];
    hlGroups.forEach(function (g) {
      if (!g.some(function (w) { return shown.indexOf(w) >= 0; })) hidden = hidden.concat(g);
    });
    if (!hidden.length) return "";
    var chars = Array.from(it.memo), norm = "", map = [];
    chars.forEach(function (ch, i) { var n = normalize(ch); for (var k = 0; k < n.length; k++) map.push(i); norm += n; });
    var best = -1, bestLen = 0;
    hidden.forEach(function (w) {
      var p = norm.indexOf(w);
      if (p >= 0 && (best < 0 || p < best)) { best = p; bestLen = w.length; }
    });
    if (best < 0) return "";  // 説明の外（運営元や読みなど）で当たったときは添えない
    var hs = map[best], he = map[best + bestLen - 1] + 1;
    // 当たった語を含む1文（「。」で区切る）。長いときは前後を切って「…」を付ける
    var ss = hs, se = he;
    while (ss > 0 && chars[ss - 1] !== "。") ss--;
    while (se < chars.length && chars[se - 1] !== "。") se++;
    var a = ss, b = se;
    if (b - a > SNIP_MAX) {
      a = Math.max(ss, hs - SNIP_BEFORE);
      b = Math.min(se, a + SNIP_MAX);
      if (b < he) { b = he; a = Math.max(ss, b - SNIP_MAX); }
      // 語の途中で切れないよう、切る所の近くに読点があればそこで切る
      for (var i = a; a > ss && i < hs - 4; i++) if (chars[i] === "、") { a = i + 1; break; }
      for (var j = b - 1; b < se && j > he + 8; j--) if (chars[j] === "、") { b = j + 1; break; }
    }
    var text = (a > ss ? "…" : "") + chars.slice(a, b).join("") + (b < se ? "…" : "");
    return '<p class="card-snip"><span class="visually-hidden">説明の中で当たった文：</span>' + mark(text) + "</p>";
  }
  function cardHtml(it, idx) {
    var tags = '<span class="tag tag-kind">' + mark(it.kind) + "</span>";
    // 絞り込みを変えたときに、画面の上のほうのカードがなめらかに動くよう、名前（--vt）を付けておく（使うのは入れ替えのあいだだけ）
    var vt = idx < 40 ? ' style="--vt: c-' + esc(it.id) + '"' : "";
    // カードの形は sitegen/parts.py の card() と同じ（題名のリンクの範囲をカード全体に広げ、段階の言葉は説明を開くボタン。2026-11-15）
    return '<li class="card"' + vt + '><div class="card-box">' + mediaHtml(it.img) + '<div class="card-body">' +
      '<p class="card-when" title="' + esc(whenLine(it)) + '">' + (window.TenkiWhen ? window.TenkiWhen(it) : esc(whenLine(it))) + "</p>" +
      '<h3><a class="card-link" href="/item/' + encodeURIComponent(it.id) + '/" aria-label="' + esc(it.title + "（" + whenLine(it) + "）") + '">' + mark(it.title, true, it.wb) + "</a></h3>" +
      '<p class="card-line">' + mark(it.line) + "</p>" + snippet(it) +
      '<div class="card-foot"><div class="tags">' + tags + "</div>" + (byNew ? '<span class="card-date">' + esc(addedLabel(it.added)) + "</span>" : "") + "</div>" +
      "</div></div>" + (window.TenkiSaved ? window.TenkiSaved.button(it.id, it.title) : "") + "</li>";
  }

  // 選んでいる条件を「×で外せる札」として並べる
  function chipText(f, state) {
    if (f === "q") return "「" + state.q + "」";
    return LABELS[f] + "：" + state[f];
  }

  function renderChips(state) {
    var chips = [];
    ["q"].concat(FILTERS).forEach(function (f) { if (state[f]) chips.push({ field: f, text: chipText(f, state) }); });
    chipsEl.hidden = !chips.length;
    chipsEl.innerHTML = chips.map(function (c) {
      return '<button type="button" class="active-chip" data-field="' + c.field + '" aria-label="' + esc(c.text) + 'を外す">' +
        esc(c.text) + '<span aria-hidden="true">×</span></button>';
    }).join("") + (chips.length > 1 ? '<button type="button" class="link-button" data-field="all">すべて外す</button>' : "");
    var n = FILTERS.filter(function (f) { return state[f]; }).length;
    filterCount.textContent = n ? "（" + n + "）" : "";
    var barBtn = document.getElementById("bar-filter");  // スマホの帯の「絞り込む」にも、選んでいる条件の数を出す
    if (barBtn) barBtn.textContent = "絞り込む" + (n ? "（" + n + "）" : "");
  }

  // 件数は「全N件中 M件」の形で、数字だけ大きく出す（コミュニティ図鑑と同じ形。2026-11-15）。
  // 選んでいる条件はすぐ下の札に出ているので、ここには書かない（条件で文の長さが変わり、横のボタンが動かないように）
  function countHtml() {
    var total = data.items.length;
    if (!results.length) return '<span class="count-total">' + total + "件中</span> <b>0</b>件。条件を外すか、別の言葉で探してみてください。";
    if (results.length === total) return '<span class="count-total">全</span><b>' + total + "</b>件";
    return '<span class="count-total">' + total + "件中</span> <b>" + results.length + "</b>件";
  }

  function render(reset) {
    if (reset) { list.innerHTML = ""; shown = 0; }
    var next = results.slice(shown, shown + PAGE);
    list.insertAdjacentHTML("beforeend", next.map(function (it, j) {
      return (shown + j === ownCount ? '<li class="list-divider" role="presentation"' + (shown + j < 40 ? ' style="--vt: c-divider"' : "") + '>どの転機にも役立つもの</li>' : "") + cardHtml(it, shown + j);
    }).join(""));
    shown += next.length;
    moreBtn.hidden = shown >= results.length;
    if (!moreBtn.hidden) moreBtn.textContent = "もっと見る（残り" + (results.length - shown) + "件）";
  }

  // 探した言葉を、アクセス解析（GoatCounter）に送る。見つかった言葉は search/〇〇、何も見つからなかった言葉は search-zero/〇〇。
  // 入力の途中では送らず（2秒止まってから）、同じ言葉は1回だけ。「こんな言葉で探せます」に足す言葉や、言い換え表の見直しに使う
  var zeroTimer, zeroSent = {};
  function reportZero(state) {
    clearTimeout(zeroTimer);
    var q = (state.q || "").trim();
    if (!q || q.length > 30 || zeroSent[q]) return;
    // メールアドレス・電話番号・URLのような、個人につながりうる言葉は記録しない
    if (/@|https?:|www\.|\d{2,4}[-‐－ー\s]?\d{2,4}[-‐－ー\s]?\d{3,4}|\d{7,}/.test(q.normalize("NFKC"))) return;
    var found = results.length > 0;
    zeroTimer = setTimeout(function () {
      if (!window.goatcounter || !window.goatcounter.count) return;
      zeroSent[q] = true;
      window.goatcounter.count({ path: (found ? "search/" : "search-zero/") + q, title: (found ? "検索：" : "0件：") + q, event: true });
    }, 2000);
  }

  // 言い換えで広げて探したときに、そのことを一言添える
  function renderSynNote(state) {
    var parts = [];
    normalize(state.q).split(/\s+/).filter(Boolean).forEach(function (t) {
      var alts = alternatives(t).filter(function (w) { return w !== t; });
      if (alts.length) parts.push("「" + esc(t) + "」と同じ意味の言葉（" + alts.slice(0, 3).map(function (w) { return '<strong class="hit">' + esc(w) + "</strong>"; }).join("・") + (alts.length > 3 ? "など" : "") + "）");
    });
    synNote.hidden = !parts.length || !results.length;
    synNote.innerHTML = parts.length ? parts.join("、") + "も含めて探しています。" : "";
  }

  // 入力中の候補：言い換え表の言葉から、入力した文字（ひらがなは読み）を含むものを最大5つ
  function renderSuggest() {
    var q = normalize(qInput.value.trim());
    var words = [];
    if (data && data.suggest && q.length >= 2) {
      data.suggest.forEach(function (o) {
        if (words.length >= 5) return;
        if (normalize(o.w) === q) return;
        if (normalize(o.w).indexOf(q) >= 0 || (o.r && o.r.indexOf(q) >= 0)) words.push(o.w);
      });
    }
    suggestEl.hidden = !words.length;
    suggestEl.innerHTML = words.map(function (w) {
      return '<li role="option"><button type="button" data-word="' + esc(w) + '">' + esc(w) + "</button></li>";
    }).join("");
  }

  function run() {
    var state = readForm();
    updateUrl(state);
    // キーワード検索用の文字（search-text.json）がまだ届いていないときは、届いてから探す
    if (state.q && !textReady) {
      countEl.textContent = "読み込んでいます…";
      return;
    }
    results = filter(state);
    byNew = state.sort === "new";
    hlWords = [];
    hlGroups = [];
    normalize(state.q).split(/\s+/).filter(Boolean).forEach(function (t) {
      var g = [];
      alternatives(t).forEach(function (w) { w = normalize(w); if (w && g.indexOf(w) < 0) g.push(w); if (w && hlWords.indexOf(w) < 0) hlWords.push(w); });
      hlGroups.push(g);
    });
    hlWords.sort(function (a, b) { return b.length - a.length; });
    renderChips(state);
    updateCounts(state);
    renderZeroHelp(state);
    renderSynNote(state);
    // こんな言葉で探せますは常に出しておき（高さが変わらないように）、いま探している言葉に印を付ける
    Array.prototype.forEach.call(startHelp.querySelectorAll(".start-word"), function (a) {
      if (a.textContent === state.q) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current");
    });
    countEl.innerHTML = countHtml();
    render(true);
    renderAiHelp();
    reportZero(state);
  }

  // 転機AIへの案内：結果が少ないときは結果の下に囲みで、多いときは一番下に1行で出す
  var aiHelp = document.getElementById("ai-help"), aiLine = document.getElementById("ai-line");
  function renderAiHelp() {
    if (!aiHelp || !aiLine) return;
    var few = results.length <= (parseInt(aiHelp.getAttribute("data-few"), 10) || 5);
    aiHelp.hidden = !few;
    aiLine.hidden = few;
  }

  function setPanel(open) {
    panel.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }

  // 絞り込みや並び順を変えたとき：残るカードは新しい位置へ滑り、外れるカードは薄くなって消え、入るカードはそっと現れる
  // （2026-11-15 見本の案6。同じページの View Transitions。対応していないブラウザ・動きを減らす設定では今までどおり一瞬で入れ替える）。
  // キーワードを打っている途中は動かさない（1文字ごとに動くと落ち着かないため）
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");
  function runMoving() {
    if (!document.startViewTransition || (reduce && reduce.matches) || document.hidden) { run(); return; }
    list.classList.add("vt-moving");
    var t = document.startViewTransition(run);
    var done = function () { list.classList.remove("vt-moving"); };
    t.finished.then(done, done);
  }

  var timer;
  form.addEventListener("input", function (ev) {
    if (ev.target !== qInput) return;  // ボタン・並び順は change で受ける
    renderSuggest();
    clearTimeout(timer); timer = setTimeout(run, 200);
  });
  // こんな言葉で探せます：押すと、ページを読み直さずにその言葉で探す（選んでいる条件はそのまま）。もう一度押すと外れる
  startHelp.addEventListener("click", function (ev) {
    var a = ev.target.closest(".start-word");
    if (!a) return;
    ev.preventDefault();
    qInput.value = a.getAttribute("aria-current") === "true" ? "" : a.textContent;
    run();
  });
  suggestEl.addEventListener("click", function (ev) {
    var b = ev.target.closest("button[data-word]");
    if (!b) return;
    qInput.value = b.getAttribute("data-word");
    suggestEl.hidden = true;
    run();
  });
  qInput.addEventListener("keydown", function (ev) { if (ev.key === "Escape") suggestEl.hidden = true; });
  document.addEventListener("click", function (ev) { if (!ev.target.closest(".search-q")) suggestEl.hidden = true; });
  // 選んでいるボタンをもう一度押すと外れる（「すべて」に戻る）
  var wasChecked = null;
  form.addEventListener("pointerdown", function (ev) {
    var label = ev.target.closest(".fchip");
    var input = label && label.querySelector("input");
    wasChecked = input && input.checked && input.value ? input : null;
  });
  form.addEventListener("click", function (ev) {
    var input = ev.target.closest(".fchip") && ev.target.closest(".fchip").querySelector("input");
    if (input && input === wasChecked && ev.target === input) {
      setRadio(input.name, "");
      wasChecked = null;
      runMoving();
    }
  });
  // カード／一覧の表示の切り替え（パソコン）。選んだ表示はこのブラウザに覚えておく
  var viewSwitch = document.querySelector(".view-switch");
  function setView(v) {
    list.classList.toggle("view-list", v === "list");
    Array.prototype.forEach.call(viewSwitch.querySelectorAll("button"), function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-view") === v)); });
  }
  if (viewSwitch) {
    try { setView(localStorage.getItem("tenki-view") || "card"); } catch (e) { setView("card"); }
    viewSwitch.addEventListener("click", function (ev) {
      var b = ev.target.closest("button[data-view]");
      if (!b) return;
      setView(b.getAttribute("data-view"));
      try { localStorage.setItem("tenki-view", b.getAttribute("data-view")); } catch (e) {}
    });
  }
  form.addEventListener("change", function (ev) { if (ev.target === qInput) run(); else runMoving(); });
  form.addEventListener("submit", function (ev) { ev.preventDefault(); run(); });
  moreBtn.addEventListener("click", function () { render(false); });
  toggle.addEventListener("click", function () { setPanel(!panel.classList.contains("open")); });
  function clearField(k) {
    if (FILTERS.indexOf(k) >= 0) { setRadio(k, ""); return; }
    var el = form.elements[k];
    if (el.type === "checkbox") el.checked = false; else el.value = "";
  }
  function onRemove(ev) {
    var b = ev.target.closest("button[data-field]");
    if (!b) return;
    var f = b.getAttribute("data-field");
    (f === "all" ? ["q"].concat(FILTERS) : [f]).forEach(clearField);
    runMoving();
  }
  chipsEl.addEventListener("click", onRemove);
  zeroHelp.addEventListener("click", onRemove);

  // 一覧に出すデータ（search.json）と、キーワード検索に使う文字（search-text.json、説明の全文と読み）を分けて読む。
  // 一覧は search.json だけで先に出し、キーワードがあるときは search-text.json が届いてから探す
  // （回線を取り合わないよう、search-text.json は一覧を出したあとに読み始める）
  var textReady = false;
  fetch("/search.json")
    .then(function (r) { return r.json(); })
    .then(function (json) {
      data = json;
      writeForm(readParams());
      run();
      return fetch("/search-text.json").then(function (r) { return r.json(); })
        .then(function (json) { return json || {}; }, function () { return null; })
        .then(function (json) {
          data.items.forEach(function (it) {
            // 説明（memo）はそのままの文字で届くので、「題名 説明」をそろえて残り（rest）の前につなぐ（sitegen/output.py と同じ並び）。
            // 前の形の search-text.json（text だけ）がブラウザに残っていればそれを使う。どちらも読めなければタイトルと説明の1文目で探す
            if (it.text !== undefined) return;
            if (json && json.memo && json.memo[it.id] !== undefined) {
              it.memo = json.memo[it.id];
              it.text = normalize(it.title + " " + it.memo) + " " + ((json.rest || {})[it.id] || "");
            } else if (json && json.text && json.text[it.id] !== undefined) {
              it.text = json.text[it.id];
            } else {
              it.text = normalize(it.title + " " + it.line);
            }
          });
          textReady = true;
          if (readForm().q) run();
        });
    })
    .catch(function () { countEl.textContent = "データを読み込めませんでした。時間をおいて開き直してください。"; });
})();
