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

// 段階の言葉（準備・遭遇・順応・安定）の説明の小窓（2026-11-15 見本の案7のA）。
// 小窓はページの下に段階ごとに1つずつある（sitegen/parts.py の stage_pops）。カードの段階の言葉はボタンで、
// マウスでは当てると開き、外すと閉じる。指では押すと開き、ほかの場所を押すか Esc で閉じる（popover の light dismiss）。
// アンカー配置が使えるブラウザでは押した言葉のすぐ下に、使えないブラウザでは画面の下に出す
(function () {
  var slugs = {};
  Array.prototype.forEach.call(document.querySelectorAll(".stage-pop"), function (pop) {
    var b = pop.querySelector(".stage-pop-name b");
    if (b) slugs[b.textContent] = pop.id;
  });
  function escH(s) { return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  // JS で作るカード（探す・あとで見る・ほかの情報をチェック）の「誰の・いつの」一行
  window.TenkiWhen = function (it) {
    var tenki = it.tenki.indexOf("共通") >= 0 ? "どの転機にも" : it.tenki.join("、");
    var stages = it.stages.map(function (n) {
      return slugs[n] ? '<button type="button" class="stage-term" popovertarget="' + slugs[n] + '">' + escH(n) + "</button>" : escH(n);
    }).join("、");
    return [escH(tenki), stages].filter(Boolean).join("｜");
  };
  var probe = document.querySelector(".stage-pop");
  if (!probe || !probe.showPopover) return;
  var canAnchor = !!(window.CSS && CSS.supports && CSS.supports("position-area: block-end") && CSS.supports("anchor-name: --a"));
  var current = {}, timers = {}, pinned = null;
  function isOpen(pop) { try { return pop.matches(":popover-open"); } catch (e) { return false; } }
  function hide(pop) { if (isOpen(pop)) pop.hidePopover(); }
  function popOf(btn) { return document.getElementById(btn.getAttribute("popovertarget")); }
  function show(btn, pop, viaHover) {
    clearTimeout(timers[pop.id]);
    if (isOpen(pop)) {
      if (current[pop.id] === btn) { if (!viaHover) pop.removeAttribute("data-hover"); return; }
      hide(pop);
    }
    if (current[pop.id]) { current[pop.id].style.removeProperty("anchor-name"); current[pop.id].removeAttribute("data-open"); }
    if (canAnchor) {
      btn.style.setProperty("anchor-name", "--" + pop.id);
      pop.style.setProperty("position-anchor", "--" + pop.id);
      pop.classList.add("anchored");
    }
    current[pop.id] = btn;
    if (viaHover) pop.setAttribute("data-hover", ""); else pop.removeAttribute("data-hover");
    try { pop.showPopover({ source: btn }); } catch (e) { pop.showPopover(); }
  }
  function later(pop) {
    clearTimeout(timers[pop.id]);
    timers[pop.id] = setTimeout(function () { if (pop.hasAttribute("data-hover")) hide(pop); }, 200);
  }
  function isPinned(btn, pop) { return isOpen(pop) && current[pop.id] === btn && !pop.hasAttribute("data-hover"); }
  document.addEventListener("pointerdown", function (ev) {
    var btn = ev.target.closest && ev.target.closest(".stage-term");
    pinned = btn ? isPinned(btn, popOf(btn)) : null;
  });
  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest && ev.target.closest(".stage-term");
    if (!btn) return;
    var pop = popOf(btn);
    if (!pop) return;
    ev.preventDefault();  // popovertarget の開け閉めの代わりに、ここで開け閉めする（JS がないときは popovertarget だけで開く）
    var was = pinned === null ? isPinned(btn, pop) : pinned;
    pinned = null;
    if (was) { hide(pop); return; }
    show(btn, pop, false);
  });
  document.addEventListener("pointerover", function (ev) {
    if (ev.pointerType !== "mouse") return;
    var btn = ev.target.closest && ev.target.closest(".stage-term");
    if (btn && !btn.contains(ev.relatedTarget)) show(btn, popOf(btn), true);
    var pop = ev.target.closest && ev.target.closest(".stage-pop");
    if (pop) clearTimeout(timers[pop.id]);
  });
  document.addEventListener("pointerout", function (ev) {
    if (ev.pointerType !== "mouse") return;
    var el = ev.target.closest && (ev.target.closest(".stage-term") || ev.target.closest(".stage-pop"));
    if (!el || el.contains(ev.relatedTarget)) return;
    later(el.classList.contains("stage-pop") ? el : popOf(el));
  });
  Array.prototype.forEach.call(document.querySelectorAll(".stage-pop"), function (pop) {
    pop.addEventListener("toggle", function (ev) {
      var btn = current[pop.id];
      if (btn) { if (ev.newState === "open") btn.setAttribute("data-open", ""); else btn.removeAttribute("data-open"); }
    });
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
  // 絵文字を Noto の画像で出す（build.py の emoji_img と同じファイル名。assets/emoji/ に置いてある）
  function emoImg(s) {
    if (!s) return "";
    var cps = [];
    Array.from(s).forEach(function (ch) { var c = ch.codePointAt(0); if (c === 0xfe0f) return; var h = c.toString(16); cps.push(h.length < 4 ? ("000" + h).slice(-4) : h); });
    return '<img class="emo" src="/assets/emoji/' + cps.join("_") + '.svg" alt="' + esc(s) + '" draggable="false">';
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
    if (h) { h.innerHTML = '<span class="saved-n">' + (n > 99 ? "99+" : String(n)) + "</span>"; h.hidden = !n; }
  }

  function restart(el, cls) { el.classList.remove(cls); void el.offsetWidth; el.classList.add(cls); }

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
    var h = document.getElementById("saved-count-h"), wasHidden = !h || h.hidden;
    toggle(btn.getAttribute("data-save"));
    paintAll();
    // 残したときの手応え（2026-11-15 見本の案10）：しおりが跳ね、ヘッダーの数がぽんと動く。外すときは静かに（動きは style.css）
    if (btn.getAttribute("aria-pressed") === "true") {
      restart(btn, "save-pop");
      if (h) { restart(h, wasHidden ? "saved-in" : "saved-bump"); restart(h.parentNode, "saved-flash"); }
    } else {
      btn.classList.remove("save-pop");
    }
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
    return '<div class="card-media media-none" aria-hidden="true"><span>' + emoImg(img.emoji) + "</span></div>";
  }
  // カードの形は sitegen/parts.py の card() と同じ（題名のリンクの範囲をカード全体に広げ、段階の言葉は説明を開くボタン。2026-11-15）
  // 題名：文節の切れ目（search.json の wb）に <wbr>、約物を <span class="yk"> で包む（sitegen/typeset.py と同じ。2026-11-15 見本の案14・15）
  function titleHtml(it) {
    var pts = {}, OPEN = "「『（［【〔〈《“‘", CLOSE = "」』）］】〕〉》”’", PUNCT = "、。，．";
    (it.wb || []).forEach(function (p) { pts[p] = true; });
    return '<span class="wb">' + Array.from(it.title || "").map(function (ch, i) {
      var c = CLOSE.indexOf(ch) >= 0 ? "yk" : PUNCT.indexOf(ch) >= 0 ? "yk yk-p" : OPEN.indexOf(ch) >= 0 ? "yk yk-o" : "";
      return (pts[i] ? "<wbr>" : "") + (c ? '<span class="' + c + '">' + esc(ch) + "</span>" : esc(ch));
    }).join("") + "</span>";
  }
  function cardHtml(it) {
    var tags = '<span class="tag tag-kind">' + esc(it.kind) + "</span>";
    return '<li class="card"><div class="card-box">' + mediaHtml(it.img) + '<div class="card-body"><p class="card-when" title="' + esc(whenLine(it)) + '">' +
      window.TenkiWhen(it) + '</p><h3><a class="card-link" href="/item/' + encodeURIComponent(it.id) + '/" aria-label="' + esc(it.title + "（" + whenLine(it) + "）") + '">' +
      titleHtml(it) + '</a></h3><p class="card-line">' + esc(it.line) + '</p><div class="card-foot"><div class="tags">' + tags +
      "</div></div></div></div>" +
      window.TenkiSaved.button(it.id, it.title) + "</li>";
  }
  window.TenkiCard = cardHtml;  // 紹介ページの「ほかの情報をチェック」でも同じカードを使う
  function endedHtml(id) {
    return '<li class="card"><div class="card-box"><div class="card-body"><h3><a class="card-link" href="/item/' + encodeURIComponent(id) + '/">掲載を終えた情報（' + esc(id) + '）</a></h3><p class="card-line">提供が終わったか、掲載を終えました。</p></div></div>' +
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

// ヘッダーは上に固定。探すページの帯はヘッダーのすぐ下に付ける
(function () {
  var header = document.querySelector(".site-header");
  if (!header) return;
  function apply() { document.documentElement.style.setProperty("--header-h", header.offsetHeight + "px"); }
  if (window.ResizeObserver) new ResizeObserver(apply).observe(header); else window.addEventListener("resize", apply);
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

// アクセス解析：「あとで見る」「共有」が押された掲載と、あしたの転機のページから外へ移った数を数える（「公式サイトを見る」は data-goatcounter-click で数える）
(function () {
  function count(path, title) {
    if (window.goatcounter && window.goatcounter.count) window.goatcounter.count({ path: path, title: title, event: true });
  }
  document.addEventListener("click", function (ev) {
    var save = ev.target.closest(".save-wide[data-save], .save-btn[data-save]");
    if (save && save.getAttribute("aria-pressed") === "true") count("save/" + save.getAttribute("data-save"), save.getAttribute("data-title") || "");
    var share = ev.target.closest(".share-btn");
    if (share) count("share/" + location.pathname.split("/")[2], share.getAttribute("data-share-title") || "");
    // あしたの転機のページ（/project/）から外のページ（note・Facebookグループ・Podcast など）へ移った数。行き先のサイト名だけを送る
    var out = location.pathname.indexOf("/project/") === 0 && ev.target.closest("main a[href^='http']");
    if (out && !out.hasAttribute("data-goatcounter-click")) {
      var host = out.hostname.replace(/^www\./, "");
      count("project-out/" + host, "あしたの転機から：" + host);
    }
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

// 紹介ページの下の「あわせて見たいもの」：手段（タイプ）ごとのボタンで中身を切り替える
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

// トップの件数の数字を0から数え上げる（動きを減らす設定の端末では、そのまま出す）
// ページの読み込み（画像・見出しの書体）と重なると数字の増え方がカクカクするので、読み込みが終わってから始める。
// 待っているあいだは数字を隠し、桁が増えても横にずれないよう幅を先に取っておく。すべての数字を1つの流れで動かす
(function () {
  var counters = Array.prototype.filter.call(document.querySelectorAll("[data-count]"), function (el) {
    return parseInt(el.getAttribute("data-count"), 10) > 0;
  });
  if (!window.requestAnimationFrame || window.matchMedia("(prefers-reduced-motion: reduce)").matches || !counters.length) return;
  counters.forEach(function (el) {
    el.style.opacity = "0";
  });
  var started = false;
  function startCount() {
    if (started) return;
    started = true;
    var t0 = null;
    function step(t) {
      if (t0 === null) t0 = t;
      var p = Math.min(1, (t - t0) / 1000), k = 1 - Math.pow(1 - p, 3);
      counters.forEach(function (el) { el.textContent = String(Math.round(parseInt(el.getAttribute("data-count"), 10) * k)); });
      if (p < 1) requestAnimationFrame(step);
      else counters.forEach(function (el) { el.style.minWidth = ""; });
    }
    /* 数え上げ中に横の文字が動かないよう、書体を読み込んだあとの最後の数字の幅をとり、終わったら外す */
    counters.forEach(function (el) { el.style.minWidth = Math.ceil(el.getBoundingClientRect().width) + "px"; el.textContent = "0"; el.style.opacity = ""; });
    requestAnimationFrame(step);
  }
  var whenLoaded = new Promise(function (ok) {
    if (document.readyState === "complete") ok(); else window.addEventListener("load", ok);
  });
  var whenFonts = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
  // 読み込みの直後のひと仕事が片づくのを2フレーム待ってから
  Promise.all([whenLoaded, whenFonts]).then(function () { requestAnimationFrame(function () { requestAnimationFrame(startCount); }); });
  setTimeout(startCount, 2500);  // 読み込みに時間がかかっても、2.5秒たったら始める
})();

// 紹介ページの「ほかの情報をチェック」：押すたびに、掲載中の全体から1件をランダムにめくる（いま見ている掲載と、直前に出したものは除く）。
// 一覧は押したときに /search.json から読む（コミュニティ図鑑の「ほかの事例をひく」と同じ形。2026-11-07）
(function () {
  var box = document.getElementById("pick-box");
  if (!box || !window.fetch || !window.TenkiCard) return;
  var btn = document.getElementById("pick-button"), cardEl = document.getElementById("pick-card"), label = document.getElementById("pick-label");
  var self = box.getAttribute("data-id"), list = null, last = box.getAttribute("data-first") || "";
  btn.hidden = false;  // 最初の1件はページに書いてある。めくるボタンは JavaScript が使えるときだけ出す
  function show() {
    var pool = list.filter(function (it) { return it.id !== self && it.id !== last; });
    if (!pool.length) return;
    var it = pool[Math.floor(Math.random() * pool.length)];
    last = it.id;
    cardEl.innerHTML = window.TenkiCard(it);
  }
  btn.addEventListener("click", function () {
    btn.classList.add("is-rolling");
    setTimeout(function () { btn.classList.remove("is-rolling"); }, 500);
    if (list) { show(); return; }
    btn.disabled = true;
    fetch("/search.json").then(function (r) { return r.json(); }).then(function (d) {
      list = d.items || [];
      show();
    }).catch(function () {
      cardEl.innerHTML = '<li class="pick-error">読み込めませんでした。時間をおいてもう一度押してください。</li>';
    }).then(function () { btn.disabled = false; });
  });
})();

// 転機の天気予報のグラフ（2026-11-15 の改善の見本で採用）
// 案1のB：グラフが画面に入ったら一度だけ、今年の線を左から描く（.play を付ける。動きは style.css。動きを減らす設定では描かない）
// 案2のB：グラフをなぞる（Tab で入って左右の矢印キーでも）と、その月の縦線と各年の点、吹き出しの数字が出る。値は spark() が data-yoho に書く
(function () {
  var figs = document.querySelectorAll(".yoho-years");
  if (!figs.length) return;
  if ("IntersectionObserver" in window && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add("play"); io.unobserve(en.target); } });
    }, { threshold: 0.5 });
    Array.prototype.forEach.call(figs, function (f) { io.observe(f); });
  }
  Array.prototype.forEach.call(document.querySelectorAll(".yoho-plot[data-yoho]"), function (plot) {
    var D;
    try { D = JSON.parse(plot.getAttribute("data-yoho")); } catch (err) { return; }
    var svg = plot.querySelector("svg"), vline = plot.querySelector(".yoho-vline"), pts = plot.querySelectorAll(".yoho-pt");
    var tip = plot.querySelector(".yoho-tip"), live = plot.parentNode.querySelector(".yoho-live");
    var cur = D.latest, on = false, touching = false;
    function rows(m) {
      return D.years.map(function (y) { var p = y.pts[m - 1]; return { year: y.year, cls: y.cls, y: p ? p[0] : null, v: p ? p[1] : null }; });
    }
    function draw(m, active) {
      cur = m; on = active;
      plot.classList.toggle("yoho-on", active);
      if (!active) { tip.hidden = true; return; }
      var x = D.x[m - 1], rs = rows(m), sum = 0, n = 0;
      vline.setAttribute("x1", x); vline.setAttribute("x2", x);
      tip.textContent = "";
      var h = document.createElement("b"); h.textContent = m + "月"; tip.appendChild(h);
      rs.forEach(function (r, i) {
        var c = pts[i];
        if (r.y === null) c.setAttribute("visibility", "hidden");
        else { c.removeAttribute("visibility"); c.setAttribute("cx", x); c.setAttribute("cy", r.y); sum += r.y; n++; }
        var row = document.createElement("span"), sw = document.createElement("i"), em = document.createElement("em");
        sw.className = "yoho-sw " + r.cls; em.textContent = r.v || "—";
        row.appendChild(sw); row.appendChild(document.createTextNode(r.year + "年")); row.appendChild(em);
        tip.appendChild(row);
      });
      // 右寄りの月では線の左に、点が上のほうにあるときは吹き出しを下に置く
      var px = x / D.w * 100, right = m > 7, high = n && sum / n < (D.h - D.b) / 2;
      tip.style.left = right ? "auto" : "calc(" + px + "% + 10px)";
      tip.style.right = right ? "calc(" + (100 - px) + "% + 10px)" : "auto";
      tip.style.top = high ? "auto" : "0";
      tip.style.bottom = high ? (D.b / D.h * 100) + "%" : "auto";
      tip.hidden = false;
    }
    function reset() { draw(D.latest, false); }
    function monthAt(clientX) {
      var r = svg.getBoundingClientRect(), vx = (clientX - r.left) / r.width * D.w, step = (D.x[11] - D.x[0]) / 11;
      return Math.max(1, Math.min(12, Math.round((vx - D.x[0]) / step) + 1));
    }
    plot.addEventListener("pointerdown", function (ev) { if (ev.pointerType !== "mouse") touching = true; draw(monthAt(ev.clientX), true); });
    plot.addEventListener("pointermove", function (ev) { if (ev.pointerType === "mouse" || touching) draw(monthAt(ev.clientX), true); });
    function lift(ev) { if (ev.pointerType !== "mouse") { touching = false; reset(); } }
    plot.addEventListener("pointerup", lift);
    plot.addEventListener("pointercancel", lift);
    plot.addEventListener("pointerleave", function (ev) { if (ev.pointerType === "mouse") reset(); });
    plot.addEventListener("keydown", function (ev) {
      var m = on ? cur : D.latest;
      if (ev.key === "ArrowLeft") m -= 1;
      else if (ev.key === "ArrowRight") m += 1;
      else if (ev.key === "Home") m = 1;
      else if (ev.key === "End") m = 12;
      else if (ev.key === "Escape") { reset(); return; }
      else return;
      ev.preventDefault();
      m = Math.max(1, Math.min(12, m));
      draw(m, true);
      if (live) live.textContent = rows(m).map(function (r) { return r.year + "年" + m + "月 " + (r.v || "データなし"); }).join("、");
    });
    plot.addEventListener("focus", function () {
      var kb = false;
      try { kb = plot.matches(":focus-visible"); } catch (err) {}
      if (kb && !touching) draw(D.latest, true);
    });
    plot.addEventListener("blur", function () { reset(); if (live) live.textContent = ""; });
  });
})();

// 観測ノートの目次：いま読んでいる節に印を付ける（2026-11-15 見本の案16のA）。
// 見出し（h2）が画面の上から3割の線より上に出たら、その節を読んでいるとみなす。上側の余白を大きく取り、速くスクロールしても取りこぼさない。
// 畳んだ目次（狭い画面）は、押したら閉じる
(function () {
  var links = document.querySelectorAll(".note-toc a");
  if (!links.length) return;
  Array.prototype.forEach.call(document.querySelectorAll(".note-toc-fold a"), function (a) {
    a.addEventListener("click", function () { var d = a.closest("details"); if (d) d.open = false; });
  });
  if (!("IntersectionObserver" in window)) return;
  var heads = Array.prototype.slice.call(document.querySelectorAll(".note-layout .prose h2[id]"));
  var passed = heads.map(function () { return false; }), cur = -2;
  function render() {
    var idx = passed.lastIndexOf(true);
    if (idx === cur) return;
    cur = idx;
    var id = idx >= 0 ? "#" + heads[idx].id : "";
    Array.prototype.forEach.call(links, function (a) {
      if (a.getAttribute("href") === id) a.setAttribute("aria-current", "location"); else a.removeAttribute("aria-current");
    });
  }
  var io = new IntersectionObserver(function (es) {
    es.forEach(function (en) { passed[heads.indexOf(en.target)] = en.isIntersecting; });
    render();
  }, { rootMargin: "100000px 0px -70% 0px" });
  heads.forEach(function (h) { io.observe(h); });
})();
