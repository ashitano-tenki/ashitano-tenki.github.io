// 一覧ページ：search.json を読み込み、ブラウザの中で絞り込みと検索をする
(function () {
  document.documentElement.classList.add("js");
  var PAGE = window.TENKI_PAGE_SIZE || 20;
  var THIS_YEAR = window.TENKI_THIS_YEAR || new Date().getFullYear();
  var FIELDS = ["q", "tenki", "stage", "kind", "sort"];
  var FILTERS = ["tenki", "stage", "kind"]; // 「絞り込む」の中にある条件
  var SELECTS = ["tenki", "stage", "kind"];
  var LABELS = { kind: "タイプ", tenki: "転機", stage: "段階" };
  var COMMON = "共通", OTHER = "その他";
  var form = document.getElementById("filters");
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
  // 選択肢のもとの名前を覚えておき、件数を付け直せるようにする
  SELECTS.forEach(function (f) {
    Array.prototype.forEach.call(form.elements[f].options, function (o) { o.dataset.label = o.textContent; });
  });
  var data = null, results = [], shown = 0;

  function normalize(s) {
    s = (s || "").normalize("NFKC").toLowerCase();
    return s.replace(/[ぁ-ゖ]/g, function (c) { return String.fromCharCode(c.charCodeAt(0) + 0x60); });
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // 言い換え表を使って、検索語ごとに一緒に探す言葉を集める
  function alternatives(term) {
    var alts = [term];
    data.synonyms.forEach(function (group) {
      var hit = group.some(function (w) { return w === term || (term.length >= 2 && w.indexOf(term) >= 0); });
      if (hit) group.forEach(function (w) { if (alts.indexOf(w) < 0) alts.push(w); });
    });
    return alts;
  }

  function readParams() {
    var p = new URLSearchParams(location.search), state = {};
    FIELDS.forEach(function (f) { state[f] = p.get(f) || ""; });
    return state;
  }

  function writeForm(state) {
    FIELDS.forEach(function (f) {
      var el = form.elements[f];
      if (!el) return;
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

  // 選択肢ごとに「それを選んだら何件になるか」を付け、0件になるものは選べなくする
  function updateCounts(state) {
    SELECTS.forEach(function (f) {
      var base = without(state, f);
      Array.prototype.forEach.call(form.elements[f].options, function (o) {
        var s = without(base, f);
        s[f] = o.value;
        var n = match(s).length;
        o.textContent = (o.dataset.label || o.value) + "（" + n + "）";
        o.disabled = n === 0 && o.value !== state[f];
      });
    });
  }

  // 0件のとき、どの条件を外せば見つかるかを示す
  function renderZeroHelp(state) {
    var hints = [];
    if (!results.length) {
      ["q"].concat(FILTERS).forEach(function (f) {
        if (!state[f]) return;
        var n = match(without(state, f)).length;
        if (n) hints.push('<button type="button" class="link-button" data-field="' + f + '">' + esc(chipText(f, state)) + "を外すと" + n + "件</button>");
      });
    }
    zeroHelp.hidden = !hints.length;
    zeroHelp.innerHTML = hints.length ? "<span>条件を外すと見つかります：</span>" + hints.join("") : "";
  }

  function filter(state) {
    var out = match(state);
    if (state.sort === "new") {
      out.sort(function (a, b) { return a.added < b.added ? 1 : a.added > b.added ? -1 : a.rank - b.rank; });
    } else {
      out.sort(function (a, b) { return a.rank - b.rank; });
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

  function cardHtml(it) {
    var tags = '<span class="tag tag-kind">' + esc(it.kind) + "</span>";
    if (it.cost) tags += '<span class="tag tag-cost">' + esc(it.cost) + "</span>";
    return '<li class="card"><a href="/item/' + encodeURIComponent(it.id) + '/">' +
      '<p class="card-when">' + esc(whenLine(it)) + "</p>" +
      "<h3>" + esc(it.title) + "</h3>" +
      '<p class="card-line">' + esc(it.line) + "</p>" +
      '<div class="card-foot"><div class="tags">' + tags + '</div><span class="card-date">' + esc(addedLabel(it.added)) + "</span></div>" +
      "</a>" + (window.TenkiSaved ? window.TenkiSaved.button(it.id, it.title) : "") + "</li>";
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
  }

  function countText(state) {
    var parts = [];
    if (state.q) parts.push("「" + state.q + "」");
    FILTERS.forEach(function (f) { if (state[f]) parts.push(state[f]); });
    var cond = parts.length ? "（" + parts.join("・") + "）" : "";
    if (!results.length) return "見つかりませんでした" + cond + "。条件を外すか、別の言葉で探してみてください。";
    return results.length + "件" + cond;
  }

  function render(reset) {
    if (reset) { list.innerHTML = ""; shown = 0; }
    var next = results.slice(shown, shown + PAGE);
    list.insertAdjacentHTML("beforeend", next.map(cardHtml).join(""));
    shown += next.length;
    moreBtn.hidden = shown >= results.length;
    if (!moreBtn.hidden) moreBtn.textContent = "もっと見る（残り" + (results.length - shown) + "件）";
  }

  // 何も見つからなかったキーワードを、アクセス解析（GoatCounter）に送る。入力の途中では送らず、同じ言葉は1回だけ
  var zeroTimer, zeroSent = {};
  function reportZero(state) {
    clearTimeout(zeroTimer);
    var q = (state.q || "").trim();
    if (results.length || !q || zeroSent[q]) return;
    zeroTimer = setTimeout(function () {
      if (!window.goatcounter || !window.goatcounter.count) return;
      zeroSent[q] = true;
      window.goatcounter.count({ path: "search-zero/" + q.slice(0, 50), title: "0件：" + q.slice(0, 50), event: true });
    }, 2000);
  }

  function run() {
    var state = readForm();
    updateUrl(state);
    results = filter(state);
    renderChips(state);
    updateCounts(state);
    renderZeroHelp(state);
    countEl.textContent = countText(state);
    render(true);
    reportZero(state);
  }

  function setPanel(open) {
    panel.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }

  var timer;
  form.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(run, 200); });
  form.addEventListener("change", run);
  form.addEventListener("submit", function (ev) { ev.preventDefault(); run(); });
  moreBtn.addEventListener("click", function () { render(false); });
  toggle.addEventListener("click", function () { setPanel(!panel.classList.contains("open")); });
  function clearField(k) {
    var el = form.elements[k];
    if (el.type === "checkbox") el.checked = false; else el.value = "";
  }
  function onRemove(ev) {
    var b = ev.target.closest("button[data-field]");
    if (!b) return;
    var f = b.getAttribute("data-field");
    (f === "all" ? ["q"].concat(FILTERS) : [f]).forEach(clearField);
    run();
  }
  chipsEl.addEventListener("click", onRemove);
  zeroHelp.addEventListener("click", onRemove);

  fetch("/search.json")
    .then(function (r) { return r.json(); })
    .then(function (json) {
      data = json;
      writeForm(readParams());
      run();
    })
    .catch(function () { countEl.textContent = "データを読み込めませんでした。時間をおいて開き直してください。"; });
})();
