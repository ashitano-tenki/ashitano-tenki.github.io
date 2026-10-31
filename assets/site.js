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
  document.addEventListener("keydown", function (ev) {  // Esc で検索欄を閉じて、虫めがねに戻る
    if (ev.key !== "Escape" || form.hidden) return;
    form.hidden = true;
    btn.setAttribute("aria-expanded", "false");
    btn.focus();
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
  document.addEventListener("keydown", function (ev) {  // Esc でメニューを閉じて、メニューボタンに戻る
    if (ev.key !== "Escape" || !nav.classList.contains("open")) return;
    nav.classList.remove("open");
    btn.setAttribute("aria-expanded", "false");
    btn.focus();
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
    if (label) label.textContent = on ? "保存済み" : "あとで見る";  // 押した状態は短く（ボタンの幅をそろえているため）
    else btn.setAttribute("aria-label", "「" + btn.getAttribute("data-title") + "」を" + (on ? "あとで見るから外す" : "あとで見る"));
  }
  function paintAll() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-save]"), paint);
    var n = load().length, h = document.getElementById("saved-count-h");
    if (h) { h.textContent = n > 99 ? "99+" : String(n); h.hidden = !n; }
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
    var tags = '<span class="tag tag-kind">' + esc(it.kind) + "</span>";
    return '<li class="card"><a href="/item/' + encodeURIComponent(it.id) + '/" aria-label="' + esc(it.title + "（" + whenLine(it) + "）") + '">' + mediaHtml(it.img) + '<div class="card-body"><p class="card-when">' +
      esc(whenLine(it)) + "</p><h3>" + esc(it.title) + '</h3><p class="card-line">' + esc(it.line) + '</p><div class="card-foot"><div class="tags">' + tags +
      "</div></div></div></a>" +
      window.TenkiSaved.button(it.id, it.title) + "</li>";
  }
  function endedHtml(id) {
    return '<li class="card"><a href="/item/' + encodeURIComponent(id) + '/"><h3>掲載を終えた情報（' + esc(id) + '）</h3><p class="card-line">提供が終わったか、掲載を終えました。</p></a>' +
      window.TenkiSaved.button(id, id) + "</li>";
  }
  // 送られてきたリスト（/saved/?ids=R0001,R0002）。自分の保存は変えずに表示し、「入れる」を押したら自分の保存に足す
  var sharedIds = (new URLSearchParams(location.search).get("ids") || "").split(",").filter(function (id) { return /^R\d{3,6}$/.test(id); }).slice(0, 100);
  var importBtn = document.getElementById("saved-import"), shareBtn = document.getElementById("saved-share"), shareNote = document.getElementById("saved-share-note");
  function renderSaved() {
    if (!items) return;
    var shared = sharedIds.length > 0, ids = shared ? sharedIds : load();
    listEl.innerHTML = ids.map(function (id) { return items[id] ? cardHtml(items[id]) : endedHtml(id); }).join("");
    statusEl.textContent = shared ? "送られてきたリストです（" + ids.length + "件）。"
      : ids.length ? ids.length + "件" : "まだ何も残していません。";
    var emptyEl = document.getElementById("saved-empty");
    if (emptyEl) emptyEl.hidden = shared || ids.length > 0;
    clearBtn.hidden = shared || !ids.length;
    if (importBtn) importBtn.hidden = !shared;
    if (shareBtn) shareBtn.hidden = shared || !ids.length;
  }
  if (importBtn) importBtn.addEventListener("click", function () {
    var list = load();
    sharedIds.slice().reverse().forEach(function (id) { if (list.indexOf(id) < 0) list.unshift(id); });
    store(list); sharedIds = [];
    history.replaceState(null, "", location.pathname);
    paintAll(); renderSaved();
    shareNote.textContent = "あとで見るに入れました";
  });
  if (shareBtn) shareBtn.addEventListener("click", function () {
    var url = location.origin + location.pathname + "?ids=" + load().join(",");
    var data = { title: "あとで見るリスト｜あしたの転機観測所", url: url };
    if (navigator.share) { navigator.share(data).catch(function () {}); return; }
    if (navigator.clipboard) navigator.clipboard.writeText(url).then(function () { shareNote.textContent = "URLをコピーしました。ほかの端末や相手に送ってください"; },
      function () { shareNote.textContent = url; });
    else shareNote.textContent = url;
  });
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
  var blocks = document.querySelectorAll(".shelf-block, .sm-shelf-block");
  if (!blocks.length) return;
  Array.prototype.forEach.call(blocks, function (block) {
    var shelf = block.querySelector(".shelf, .sm-shelf");
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

// スマホ・タブレット：下に読むときはヘッダーを隠し、上に少し戻すと出す。探すページの帯はヘッダーの下に付いていく
(function () {
  var header = document.querySelector(".site-header");
  if (!header) return;
  var mq = window.matchMedia("(max-width: 759px)"), last = window.scrollY, ticking = false;
  function apply() {
    ticking = false;
    var y = window.scrollY, hidden = header.classList.contains("is-hidden");
    if (!mq.matches || y < 80 || header.querySelector(".open, [aria-expanded=\"true\"]")) hidden = false;
    else if (y > last + 6) hidden = true;
    else if (y < last - 6) hidden = false;
    header.classList.toggle("is-hidden", hidden);
    document.documentElement.style.setProperty("--header-h", hidden || !mq.matches ? "0px" : header.offsetHeight + "px");
    last = y;
  }
  window.addEventListener("scroll", function () { if (!ticking) { ticking = true; requestAnimationFrame(apply); } }, { passive: true });
  window.addEventListener("resize", apply);
  apply();
})();

// 探すページ（スマホ）：帯の「絞り込む」で条件の欄を開いて、そこまで戻る
(function () {
  var btn = document.getElementById("bar-filter"), toggle = document.getElementById("filter-toggle");
  if (!btn || !toggle) return;
  btn.addEventListener("click", function () {
    var open = toggle.getAttribute("aria-expanded") === "true";
    toggle.click();  // 開いていれば閉じ、閉じていれば開く
    btn.setAttribute("aria-expanded", open ? "false" : "true");
    if (!open) document.getElementById("filter-panel").scrollIntoView({ block: "start" });
  });
})();

// 紹介ページの「共有」：スマホは端末の共有メニュー、使えないときはURLをコピーする
(function () {
  var btn = document.querySelector(".share-btn");
  if (!btn) return;
  btn.hidden = false;
  var label = btn.querySelector("span");
  btn.addEventListener("click", function () {
    var data = { title: btn.getAttribute("data-share-title"), url: location.href.split("#")[0] };
    if (navigator.share) { navigator.share(data).catch(function () {}); return; }
    var done = function (ok) { label.textContent = ok ? "URLをコピーしました" : "コピーできませんでした"; setTimeout(function () { label.textContent = "共有"; }, 2000); };
    if (navigator.clipboard) navigator.clipboard.writeText(data.url).then(function () { done(true); }, function () { done(false); });
    else done(false);
  });
})();

// アクセス解析：「あとで見る」「共有」が押された掲載を数える（「公式サイトを見る」は data-goatcounter-click で数える）
(function () {
  function count(path, title) {
    if (window.goatcounter && window.goatcounter.count) window.goatcounter.count({ path: path, title: title, event: true });
  }
  document.addEventListener("click", function (ev) {
    var save = ev.target.closest(".save-wide[data-save], .save-btn[data-save]");
    if (save && save.getAttribute("aria-pressed") === "true") count("save/" + save.getAttribute("data-save"), save.getAttribute("data-title") || "");
    var share = ev.target.closest(".share-btn");
    if (share) count("share/" + location.pathname.split("/")[2], share.getAttribute("data-share-title") || "");
  });
})();

// 紹介ページの「この紹介は役に立ちましたか？」：押した結果をアクセス解析に記録する（人を特定する情報は送らない）。
// 同じ掲載に何度も押されないよう、押したことだけをこのブラウザに残す
(function () {
  var box = document.querySelector(".helpful");
  if (!box) return;
  var id = box.getAttribute("data-id"), key = "tenki-helpful", done = {};
  try { done = JSON.parse(localStorage.getItem(key) || "{}") || {}; } catch (e) { done = {}; }
  var thanks = box.querySelector(".helpful-thanks"), btns = box.querySelector(".helpful-btns");
  function finish() { btns.hidden = true; box.querySelector(".helpful-q").hidden = true; thanks.hidden = false; }
  box.hidden = false;
  if (done[id]) finish();
  box.addEventListener("click", function (ev) {
    var b = ev.target.closest("[data-helpful]");
    if (!b) return;
    var v = b.getAttribute("data-helpful");
    if (window.goatcounter && window.goatcounter.count)
      window.goatcounter.count({ path: "helpful/" + v + "/" + id, title: (v === "yes" ? "役に立った：" : "いまひとつ：") + box.getAttribute("data-title"), event: true });
    done[id] = v;
    try { localStorage.setItem(key, JSON.stringify(done)); } catch (e) {}
    finish();
  });
})();

// スマホの幅では、検索欄の薄い字を「キーワードで探す」だけにする（例が途中で切れないように）
(function () {
  if (!window.matchMedia || !window.matchMedia("(max-width: 639px)").matches) return;
  Array.prototype.forEach.call(document.querySelectorAll('input[type="search"][placeholder^="キーワードで探す（"]'), function (el) {
    el.setAttribute("placeholder", "キーワードで探す");
  });
})();

// 転機のページ：タイプの切り替えボタンを押すと、そのタイプの欄だけを表示する
(function () {
  Array.prototype.forEach.call(document.querySelectorAll(".kind-tabs"), function (tabs) {
    var area = tabs.parentNode.querySelector(".kind-area");
    if (!area) return;
    tabs.addEventListener("click", function (ev) {
      var b = ev.target.closest("button");
      if (!b) return;
      var kind = b.getAttribute("data-kind");
      Array.prototype.forEach.call(tabs.querySelectorAll("button"), function (x) { x.setAttribute("aria-pressed", String(x === b)); });
      Array.prototype.forEach.call(area.querySelectorAll(".kind-block"), function (sec) { sec.hidden = !!kind && sec.getAttribute("data-kind") !== kind; });
    });
  });
})();

// 観測レポート：転機のボタンで、その転機の新着だけを表示する。選んだ転機は URL（?tenki=）に残す
(function () {
  var tabs = document.querySelector(".report-tabs");
  if (!tabs) return;
  var weeks = document.querySelectorAll(".week");
  var empty = document.getElementById("report-empty");
  function apply(t) {
    Array.prototype.forEach.call(tabs.querySelectorAll("button"), function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-tenki") === t)); });
    var anyWeek = false;
    Array.prototype.forEach.call(weeks, function (week) {
      var weekN = 0;
      Array.prototype.forEach.call(week.querySelectorAll(".report-day"), function (day) {
        var n = 0;
        Array.prototype.forEach.call(day.querySelectorAll("li.card[data-tenki]"), function (li) {
          var show = !t || li.getAttribute("data-tenki").split(" ").indexOf(t) >= 0;
          li.hidden = !show;
          if (show) n++;
        });
        // 絞っているときは、その日の該当分をすべて開いて見せる（件数が少なくなるため）
        var details = day.querySelector("details");
        if (details) {
          details.open = !!t;
          details.querySelector("summary").hidden = !!t;
        }
        day.querySelector(".day-n").textContent = n;
        day.hidden = n === 0;
        weekN += n;
      });
      week.querySelector(".week-n").textContent = weekN;
      week.hidden = weekN === 0;
      if (weekN) anyWeek = true;
    });
    if (empty) empty.hidden = anyWeek;
    var url = new URL(location.href);
    if (t) url.searchParams.set("tenki", t); else url.searchParams.delete("tenki");
    history.replaceState(null, "", url.pathname + url.search + url.hash);
  }
  tabs.addEventListener("click", function (ev) {
    var b = ev.target.closest("button[data-tenki]");
    if (b) apply(b.getAttribute("data-tenki"));
  });
  var start = new URLSearchParams(location.search).get("tenki") || "";
  if (start && tabs.querySelector('button[data-tenki="' + start.replace(/"/g, "") + '"]')) apply(start);
})();

// 紹介ページの下の関連：「同じ転機・段階」と「次の段階」を切り替えボタンで1つにまとめる
(function () {
  var tabs = document.querySelector(".related-tabs");
  if (!tabs) return;
  var panels = tabs.parentNode.querySelectorAll(".related-panel");
  function show(n) {
    Array.prototype.forEach.call(tabs.querySelectorAll("button"), function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-panel") === n)); });
    Array.prototype.forEach.call(panels, function (p) { p.hidden = p.getAttribute("data-panel") !== n; });
  }
  tabs.addEventListener("click", function (ev) {
    var b = ev.target.closest("button[data-panel]");
    if (b) show(b.getAttribute("data-panel"));
  });
  show("0");
})();

// こんな言葉で探せます：ページを開くたびに、言葉の一覧からランダムに選んで出す（数は data-shown）
(function () {
  Array.prototype.forEach.call(document.querySelectorAll(".start-words[data-shown]"), function (box) {
    var words = Array.prototype.slice.call(box.querySelectorAll(".start-word"));
    var n = parseInt(box.getAttribute("data-shown"), 10) || 8;
    for (var i = words.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1)), t = words[i]; words[i] = words[j]; words[j] = t;
    }
    words.forEach(function (a, k) { a.hidden = k >= n; box.appendChild(a); });
  });
})();
