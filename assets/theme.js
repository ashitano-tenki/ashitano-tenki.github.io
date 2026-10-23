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
