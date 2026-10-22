// 一覧ページ：search.json を読み込み、ブラウザの中で絞り込みと検索をする
(function () {
  var PAGE = window.TENKI_PAGE_SIZE || 20;
  var FIELDS = ["q", "kind", "tenki", "stage", "cost", "sort"];
  var COMMON = "共通", OTHER = "その他";
  var form = document.getElementById("filters");
  var list = document.getElementById("results");
  var countEl = document.getElementById("result-count");
  var moreBtn = document.getElementById("more");
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
      if (el.tagName === "SELECT" && state[f] && !Array.prototype.some.call(el.options, function (o) { return o.value === state[f]; })) {
        el.add(new Option(state[f], state[f]));
      }
      el.value = state[f];
    });
  }

  function readForm() {
    var state = {};
    FIELDS.forEach(function (f) { state[f] = (form.elements[f].value || "").trim(); });
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

  function filter(state) {
    var terms = normalize(state.q).split(/\s+/).filter(Boolean).map(alternatives);
    var out = data.items.filter(function (it) {
      if (state.kind && it.kind !== state.kind) return false;
      if (state.tenki && !matchTenki(it, state.tenki)) return false;
      if (state.stage && it.stages.indexOf(state.stage) < 0) return false;
      if (state.cost && it.cost !== state.cost) return false;
      return terms.every(function (alts) {
        return alts.some(function (w) { return it.text.indexOf(w) >= 0; });
      });
    });
    if (state.sort === "new") {
      out.sort(function (a, b) { return a.added < b.added ? 1 : a.added > b.added ? -1 : a.rank - b.rank; });
    } else {
      out.sort(function (a, b) { return a.rank - b.rank; });
    }
    return out;
  }

  function cardHtml(it) {
    var tags = '<span class="tag tag-kind">' + esc(it.kind) + "</span>";
    if (it.cost) tags += '<span class="tag tag-cost">' + esc(it.cost) + "</span>";
    it.tenki.forEach(function (t) { tags += '<span class="tag">' + esc(t) + "</span>"; });
    return '<li class="card"><a href="/item/' + encodeURIComponent(it.id) + '/"><h3>' +
      (it["new"] ? '<span class="new">新着</span>' : "") + esc(it.title) + "</h3><p>" + esc(it.line) +
      '</p><div class="tags">' + tags + "</div></a></li>";
  }

  function render(reset) {
    if (reset) { list.innerHTML = ""; shown = 0; }
    var next = results.slice(shown, shown + PAGE);
    list.insertAdjacentHTML("beforeend", next.map(cardHtml).join(""));
    shown += next.length;
    countEl.textContent = results.length ? results.length + "件見つかりました" : "条件に合うものが見つかりませんでした。条件を減らすか、別の言葉で探してみてください。";
    moreBtn.hidden = shown >= results.length;
    if (!moreBtn.hidden) moreBtn.textContent = "もっと見る（残り" + (results.length - shown) + "件）";
  }

  function run() {
    var state = readForm();
    updateUrl(state);
    results = filter(state);
    render(true);
  }

  var timer;
  form.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(run, 200); });
  form.addEventListener("change", run);
  form.addEventListener("submit", function (ev) { ev.preventDefault(); run(); });
  moreBtn.addEventListener("click", function () { render(false); });
  document.getElementById("reset").addEventListener("click", function () {
    FIELDS.forEach(function (f) { form.elements[f].value = ""; });
    run();
  });

  fetch("/search.json")
    .then(function (r) { return r.json(); })
    .then(function (json) {
      data = json;
      writeForm(readParams());
      results = filter(readForm());
      render(true);
    })
    .catch(function () { countEl.textContent = "データを読み込めませんでした。時間をおいて開き直してください。"; });
})();
