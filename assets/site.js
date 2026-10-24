// 明るい表示とダーク表示の切り替え。最初は明るい表示で、選んだ表示はこのブラウザに記憶する
(function () {
  var root = document.documentElement;
  var button = document.getElementById("theme-toggle");
  if (!button) return;

  function apply(dark) {
    if (dark) root.setAttribute("data-theme", "dark");
    else root.removeAttribute("data-theme");
    button.setAttribute("aria-pressed", dark ? "true" : "false");
    button.textContent = dark ? "ライト表示" : "ダーク表示";
  }

  apply(root.getAttribute("data-theme") === "dark");
  button.addEventListener("click", function () {
    var dark = root.getAttribute("data-theme") !== "dark";
    apply(dark);
    try { localStorage.setItem("theme", dark ? "dark" : "light"); } catch (e) {}
  });
})();

// ヘッダーの検索：虫めがねを押すとキーワード欄を開く（JavaScriptが使えないときは探すページへ移る）
(function () {
  var btn = document.getElementById("header-search-btn");
  var form = document.getElementById("header-search");
  if (!btn || !form) return;
  btn.addEventListener("click", function (ev) {
    ev.preventDefault();
    var q = document.getElementById("q");
    if (q) { q.focus(); q.scrollIntoView({ block: "center" }); return; } // 探すページでは、ページのキーワード欄を使う
    form.hidden = !form.hidden;
    btn.setAttribute("aria-expanded", form.hidden ? "false" : "true");
    if (!form.hidden) document.getElementById("header-q").focus();
  });
})();

// スマホのメニュー：ボタンを押すとヘッダーの下にメニューを開く（JavaScriptが使えないときは最初から表示）
(function () {
  var btn = document.getElementById("menu-btn");
  var nav = document.getElementById("global-nav");
  if (!btn || !nav) return;
  btn.addEventListener("click", function () {
    var open = !nav.classList.contains("open");
    nav.classList.toggle("open", open);
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  });
})();

// あとで見る：選んだ掲載情報のIDを、このブラウザの中（localStorage）にだけ残す。どこにも送信しない
(function () {
  var KEY = "tenki-saved";
  var ICON = '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M6 3h12v18l-6-4.5L6 21z" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>';
  var ok = true;
  function load() {
    try { var v = JSON.parse(localStorage.getItem(KEY) || "[]"); return Array.isArray(v) ? v : []; }
    catch (e) { ok = false; return []; }
  }
  function store(list) {
    try { localStorage.setItem(KEY, JSON.stringify(list)); } catch (e) { ok = false; }
  }
  try { localStorage.setItem(KEY + "-test", "1"); localStorage.removeItem(KEY + "-test"); } catch (e) { ok = false; }
  if (!ok) return; // 保存できないブラウザではボタンを出さない

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function has(id) { return load().indexOf(id) >= 0; }
  function toggle(id) {
    var list = load(), i = list.indexOf(id);
    if (i >= 0) list.splice(i, 1); else list.unshift(id);
    store(list);
    return i < 0;
  }

  function paint(btn) {
    var on = has(btn.getAttribute("data-save"));
    btn.hidden = false;
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    var label = btn.querySelector("span");
    if (label) label.textContent = on ? "あとで見るに入れました" : "あとで見る";
    else btn.setAttribute("aria-label", "「" + btn.getAttribute("data-title") + "」を" + (on ? "あとで見るから外す" : "あとで見る"));
  }
  function paintAll() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-save]"), paint);
    var n = load().length, c = document.getElementById("saved-count");
    if (c) c.textContent = n ? "（" + n + "）" : "";
  }

  window.TenkiSaved = {
    button: function (id, title) {
      var on = has(id);
      return '<button type="button" class="save-btn" data-save="' + esc(id) + '" data-title="' + esc(title) + '" aria-pressed="' + on +
        '" aria-label="「' + esc(title) + "」を" + (on ? "あとで見るから外す" : "あとで見る") + '">' + ICON + "</button>";
    }
  };

  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-save]");
    if (!btn) return;
    ev.preventDefault();
    toggle(btn.getAttribute("data-save"));
    paintAll();
    if (document.getElementById("saved-list")) renderSaved();
  });
  paintAll();

  // あとで見るのページ：残したIDを search.json と照らし合わせてカードにする
  var listEl = document.getElementById("saved-list");
  var statusEl = document.getElementById("saved-status");
  var clearBtn = document.getElementById("saved-clear");
  var items = null;
  function whenLine(it) {
    var tenki = it.tenki.indexOf("共通") >= 0 ? "どの転機にも" : it.tenki.join("、");
    return [tenki, it.stages.join("、")].filter(Boolean).join("｜");
  }
  // カードの上の画像（掲載先のシェア用画像）。画像がなければタイプの絵文字（build.py の item_media と同じ形）
  function mediaHtml(img) {
    img = img || {};
    if (img.src) return '<div class="card-media media-' + esc(img.fit) + '" aria-hidden="true"><img src="' + esc(img.src) + '" alt="" loading="lazy" decoding="async"></div>';
    return '<div class="card-media media-none" aria-hidden="true"><span>' + esc(img.emoji || "") + "</span></div>";
  }
  function cardHtml(it) {
    var tags = '<span class="tag tag-kind">' + esc(it.kind) + "</span>" + (it.cost ? '<span class="tag tag-cost">' + esc(it.cost) + "</span>" : "");
    return '<li class="card"><a href="/item/' + encodeURIComponent(it.id) + '/">' + mediaHtml(it.img) + '<div class="card-body"><p class="card-when">' +
      esc(whenLine(it)) + "</p><h3>" + esc(it.title) + '</h3><p class="card-line">' + esc(it.line) + '</p><div class="card-foot"><div class="tags">' + tags +
      "</div></div></div></a>" +
      window.TenkiSaved.button(it.id, it.title) + "</li>";
  }
  function endedHtml(id) {
    return '<li class="card"><a href="/item/' + encodeURIComponent(id) + '/"><h3>掲載を終えた情報（' + esc(id) + '）</h3><p class="card-line">提供が終わったか、掲載を終えました。</p></a>' +
      window.TenkiSaved.button(id, id) + "</li>";
  }
  function renderSaved() {
    if (!items) return;
    var ids = load();
    listEl.innerHTML = ids.map(function (id) { return items[id] ? cardHtml(items[id]) : endedHtml(id); }).join("");
    statusEl.textContent = ids.length ? ids.length + "件" : "まだ何も残していません。気になったカードの右上のボタンを押すと、ここに並びます。";
    clearBtn.hidden = !ids.length;
  }
  if (listEl) {
    clearBtn.addEventListener("click", function () { store([]); paintAll(); renderSaved(); });
    fetch("/search.json").then(function (r) { return r.json(); }).then(function (data) {
      items = {};
      data.items.forEach(function (it) { items[it.id] = it; });
      renderSaved();
    }).catch(function () { statusEl.textContent = "データを読み込めませんでした。時間をおいて開き直してください。"; });
  }
})();

// トップの「タイプごとに見る」の棚：いまの位置（1 / 8）、パソコンの矢印、キーボードの左右キー。自動では動かさない
(function () {
  var blocks = document.querySelectorAll(".shelf-block, .new-block");
  if (!blocks.length) return;
  Array.prototype.forEach.call(blocks, function (block) {
    var shelf = block.querySelector(".shelf, .news-list");
    var cards = shelf.querySelectorAll("li.card:not(.card-more)");
    var dots = block.querySelectorAll(".shelf-dots i");
    var arrows = block.querySelector(".shelf-arrows");
    var prev = block.querySelector('.shelf-arrow[data-dir="-1"]');
    var next = block.querySelector('.shelf-arrow[data-dir="1"]');
    function step() {
      var first = shelf.querySelector("li");
      var gap = parseFloat(getComputedStyle(shelf).columnGap) || 0;
      return first ? first.getBoundingClientRect().width + gap : shelf.clientWidth;
    }
    function update() {
      var scrollable = shelf.scrollWidth > shelf.clientWidth + 4;
      block.classList.toggle("no-scroll", !scrollable);
      if (arrows) arrows.hidden = !scrollable;
      var i = Math.min(cards.length - 1, Math.round(shelf.scrollLeft / step()));
      Array.prototype.forEach.call(dots, function (d, j) { d.classList.toggle("on", j === i); });
      if (prev) prev.disabled = shelf.scrollLeft < 4;
      if (next) next.disabled = shelf.scrollLeft + shelf.clientWidth >= shelf.scrollWidth - 4;
    }
    function move(dir, page) {
      var amount = page ? Math.max(step(), Math.floor(shelf.clientWidth / step()) * step()) : step();
      shelf.scrollBy({ left: dir * amount, behavior: "smooth" });
    }
    if (prev) prev.addEventListener("click", function () { move(-1, true); });
    if (next) next.addEventListener("click", function () { move(1, true); });
    shelf.addEventListener("keydown", function (ev) {
      if (ev.target !== shelf || (ev.key !== "ArrowRight" && ev.key !== "ArrowLeft")) return;
      ev.preventDefault();
      move(ev.key === "ArrowRight" ? 1 : -1, false);
    });
    var ticking = false;
    shelf.addEventListener("scroll", function () {
      if (ticking) return;
      ticking = true;
      setTimeout(function () { ticking = false; update(); }, 60);
    }, { passive: true });
    window.addEventListener("resize", update);
    update();
  });
})();
