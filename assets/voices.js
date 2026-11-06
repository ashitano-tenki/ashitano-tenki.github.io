// 転機の声（/voices/）：ページに並んだ記事カードを、ブラウザの中で絞り込み・検索・並び替えする。
// 操作は「探す」ページ（search.js）とそろえる。カードは build.py が書き出し、条件は data-* 属性に入っている
(function () {
  var PAGE = window.TENKI_PAGE_SIZE || 20;
  var form = document.getElementById("vfilters");
  if (!form) return;
  var FILTERS = ["tenki", "stage", "trigger", "age", "source"].filter(function (f) { return form.querySelector('[name="' + f + '"]'); });
  var LABELS = { tenki: "転機", stage: "段階", trigger: "きっかけ", age: "年代", source: "発信元", item: "掲載" };
  var FIELDS = ["q"].concat(FILTERS, ["item", "sort"]);
  var list = document.getElementById("voices");
  var cards = Array.prototype.slice.call(list.children);
  var countEl = document.getElementById("result-count");
  var moreBtn = document.getElementById("more");
  var chipsEl = document.getElementById("active-chips");
  var toggle = document.getElementById("filter-toggle");
  var panel = document.getElementById("filter-panel");
  var filterCount = document.getElementById("filter-count");
  var qInput = document.getElementById("vq");
  var itemFilter = "";  // 紹介ページの「一覧で見る」から来たときの掲載ID（?item=R0436）。画面には札で出す
  var results = [], shown = 0;

  cards.forEach(function (li, i) {
    li._order = i;  // 書き出した順＝公開日の新しい順
    li._vals = {};
    FILTERS.concat(["item"]).forEach(function (f) { li._vals[f] = (li.getAttribute("data-" + f) || "").split("|").filter(Boolean); });
  });

  function normalize(s) {
    s = (s || "").normalize("NFKC").toLowerCase();
    return s.replace(/[ぁ-ゖ]/g, function (c) { return String.fromCharCode(c.charCodeAt(0) + 0x60); });
  }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; });
  }
  function setRadio(name, v) {
    var hit = Array.prototype.filter.call(form.querySelectorAll('input[name="' + name + '"]'), function (x) { return x.value === v; })[0];
    if (hit) hit.checked = true;
    return !!hit;
  }
  function readForm() {
    var s = {};
    FIELDS.forEach(function (f) {
      if (f === "item") { s.item = itemFilter; return; }
      var el = form.elements[f];
      s[f] = el ? (el.value || "").trim() : "";
    });
    return s;
  }
  function writeForm(s) {
    FILTERS.forEach(function (f) { if (!setRadio(f, s[f] || "")) setRadio(f, ""); });
    qInput.value = s.q || "";
    form.elements.sort.value = s.sort === "old" ? "old" : "";
    itemFilter = s.item || "";
  }
  function updateUrl(s) {
    var p = new URLSearchParams();
    FIELDS.forEach(function (f) { if (s[f]) p.set(f, s[f]); });
    var qs = p.toString();
    history.replaceState(null, "", location.pathname + (qs ? "?" + qs : ""));
  }
  function match(s) {
    var terms = normalize(s.q).split(/\s+/).filter(Boolean);
    return cards.filter(function (li) {
      for (var i = 0; i < FILTERS.length; i++) {
        var f = FILTERS[i];
        if (s[f] && li._vals[f].indexOf(s[f]) < 0) return false;
      }
      if (s.item && li._vals.item.indexOf(s.item) < 0) return false;
      var text = li.getAttribute("data-text") || "";
      return terms.every(function (t) { return text.indexOf(t) >= 0; });
    });
  }
  function without(s, field) {
    var o = {};
    for (var k in s) o[k] = s[k];
    o[field] = "";
    return o;
  }
  // ボタンごとに「それを選んだら何件になるか」を付け、0件になるものは押せなくする
  function updateCounts(s) {
    FILTERS.forEach(function (f) {
      Array.prototype.forEach.call(form.querySelectorAll('input[name="' + f + '"]'), function (input) {
        var t = without(s, f);
        t[f] = input.value;
        var n = match(t).length;
        input.parentNode.querySelector("i").textContent = n;
        input.disabled = n === 0 && input.value !== s[f];
        input.parentNode.classList.toggle("off", input.disabled);
      });
    });
  }
  function chipText(f, s) {
    if (f === "q") return "「" + s.q + "」";
    if (f === "item") {  // 掲載IDではなく、カードの「この話に出てくるもの」にある名前で出す
      var a = list.querySelector('.voice-refs a[href="/item/' + s.item + '/"]');
      return (a ? a.textContent : s.item) + "が出てくる話";
    }
    return LABELS[f] + "：" + s[f];
  }
  function renderChips(s) {
    var chips = [];
    ["q", "item"].concat(FILTERS).forEach(function (f) { if (s[f]) chips.push({ field: f, text: chipText(f, s) }); });
    chipsEl.hidden = !chips.length;
    chipsEl.innerHTML = chips.map(function (c) {
      return '<button type="button" class="active-chip" data-field="' + c.field + '" aria-label="' + esc(c.text) + 'を外す">' +
        esc(c.text) + '<span aria-hidden="true">×</span></button>';
    }).join("") + (chips.length > 1 ? '<button type="button" class="link-button" data-field="all">すべて外す</button>' : "");
    var n = FILTERS.filter(function (f) { return s[f]; }).length;
    filterCount.textContent = n ? "（" + n + "）" : "";
    var barBtn = document.getElementById("bar-filter");
    if (barBtn) barBtn.textContent = "絞り込む" + (n ? "（" + n + "）" : "");
  }
  function render(reset) {
    if (reset) shown = 0;
    shown = Math.min(results.length, shown + PAGE);
    cards.forEach(function (li) { li.hidden = true; });
    results.forEach(function (li, i) { li.hidden = i >= shown; list.appendChild(li); });
    moreBtn.hidden = shown >= results.length;
    if (!moreBtn.hidden) moreBtn.textContent = "もっと見る（残り" + (results.length - shown) + "件）";
  }
  function run() {
    var s = readForm();
    updateUrl(s);
    results = match(s);
    results.sort(function (a, b) {
      var ma = a.getAttribute("data-month"), mb = b.getAttribute("data-month");
      if (s.sort === "old") return (ma < mb ? -1 : ma > mb ? 1 : b._order - a._order);
      return a._order - b._order;
    });
    renderChips(s);
    updateCounts(s);
    countEl.textContent = results.length ? results.length + "件" : "見つかりませんでした。条件を外すか、別の言葉で探してみてください。";
    render(true);
  }
  function setPanel(open) {
    panel.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }
  function clearField(f) {
    if (f === "item") { itemFilter = ""; return; }
    if (FILTERS.indexOf(f) >= 0) { setRadio(f, ""); return; }
    form.elements[f].value = "";
  }

  var timer;
  form.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(run, 200); });
  form.addEventListener("change", run);
  form.addEventListener("submit", function (ev) { ev.preventDefault(); run(); });
  // 選んでいるボタンをもう一度押すと外れる（「すべて」に戻る）
  var wasChecked = null;
  form.addEventListener("pointerdown", function (ev) {
    var label = ev.target.closest(".fchip");
    var input = label && label.querySelector("input");
    wasChecked = input && input.checked && input.value ? input : null;
  });
  form.addEventListener("click", function (ev) {
    var label = ev.target.closest(".fchip");
    var input = label && label.querySelector("input");
    if (input && input === wasChecked && ev.target === input) { setRadio(input.name, ""); wasChecked = null; run(); }
  });
  moreBtn.addEventListener("click", function () { render(false); });
  // カードの札（転機の種類・年代・きっかけ）を押すと、その条件で絞り込み、一覧の頭に戻る
  list.addEventListener("click", function (ev) {
    var b = ev.target.closest("button[data-f]");
    if (!b) return;
    if (!setRadio(b.getAttribute("data-f"), b.getAttribute("data-v"))) return;
    run();
    var bar = document.querySelector(".result-bar");
    if (bar) bar.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  });
  toggle.addEventListener("click", function () { setPanel(!panel.classList.contains("open")); });
  // スマホの帯の「絞り込む」は site.js が開け閉めする（探すページと同じ）
  chipsEl.addEventListener("click", function (ev) {
    var b = ev.target.closest("button[data-field]");
    if (!b) return;
    var f = b.getAttribute("data-field");
    (f === "all" ? ["q", "item"].concat(FILTERS) : [f]).forEach(clearField);
    run();
  });

  var p = new URLSearchParams(location.search), init = {};
  FIELDS.forEach(function (f) { init[f] = p.get(f) || ""; });
  writeForm(init);
  run();
})();
