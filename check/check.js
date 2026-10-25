(() => {
  // 質問と結果の文章は config/check.json（build.py が window.CHECK_DATA として埋め込む）
  const D = window.CHECK_DATA;
  const NOTE_URL = "https://note.com/chlorine0528/m/m206813f097e5";
  const FB_URL = "https://www.facebook.com/share/g/1JmZs5Et5r";
  const SHARE_URL = "https://ashitano-tenki.github.io/check/";
  // 結果ごとのシェア用URL（/check/sogu/ など）。SNSで段階ごとの画像が出て、開くとこのページに移る
  const STAGE_SLUG = { "準備": "junbi", "遭遇": "sogu", "順応": "junno", "安定": "antei" };
  const HASHTAGS = ["あしたの転機", "転機の段階セルフチェック"];
  const HISTORY_KEY = "tenki-check-history";

  const STAGES = ["準備", "遭遇", "順応", "安定"];
  const SUBS = ["もやもや", "情報あつめ", "決断と行動"];
  const S4 = ["状況", "自分", "支え", "戦略"];
  const STAGE_INFO = {
    "準備": { short: "転機を考え、備える時期", desc: "気持ちは動き始めているけれど、まだ形にはなっていない段階です。迷いがあるのは、真剣に考えている証拠でもあります。" },
    "遭遇": { short: "新しい環境に入った直後", desc: "覚えることが多く、前の環境とのちがいに戸惑いやすい時期です。うまくいかないことがあっても、それは転機のふつうの一場面です。" },
    "順応": { short: "慣れていく時期", desc: "進め方がわかってきて、自分なりのやり方を試せるようになる時期です。手応えと違和感の両方を、言葉にしておくと後で役立ちます。" },
    "安定": { short: "落ち着き、次を見すえる時期", desc: "迷わずに動けるようになり、気持ちにも余裕が出てくる時期です。転機はくり返し訪れるので、ここが次のサイクルの入口にもなります。" }
  };
  const SCALE = ["とてもあてはまる", "ややあてはまる", "あまりあてはまらない", "あてはまらない"];
  const sv = i => 3 - i; // 選んだ位置 → あてはまり度（3〜0）

  // 観測所のおすすめ（サイトを作るたびに書き出す picks.json）。読めなかったときは null のまま
  let PICKS = null;
  const picksReady = fetch("/check/picks.json", { cache: "no-cache" })
    .then(res => { if (!res.ok) throw new Error(res.status); return res.json(); })
    .then(data => { if (Array.isArray(data.items) && data.items.length) PICKS = data.items; })
    .catch(() => {});

  // 回答はこのページの中だけに持つ（どこにも送らない）
  const A = {};
  const isBefore = () => A.phase !== 2;

  // 質問の並び。2問目（いまの状況）の答えで、4問目と段階の確かめの質問が入れ替わる
  function questions() {
    const before = isBefore();
    const q = [
      { key: "tenki", part: "いまの転機", text: "いま向き合っている転機に、いちばん近いものはどれですか？", opts: D.tenki },
      { key: "phase", part: "いまの転機", text: D.phase.text, opts: D.phase.opts },
      { key: "chosen", part: "いまの転機", text: D.chosen.text, opts: D.chosen.opts },
      before ? { key: "when", part: "いまの転機", text: D.when.text, opts: D.when.opts }
             : { key: "since", part: "いまの転機", text: D.since.text, opts: D.since.opts }
    ];
    (before ? D.before_items : D.after_items).forEach((t, i) =>
      q.push({ key: (before ? "b" : "a") + i, part: "いまの段階", text: t, scale: true }));
    S4.forEach(s => D.s4[s].items.forEach((t, i) => q.push({ key: "s_" + s + i, part: "転機を乗り切る4つの資源", text: t, scale: true })));
    q.push({ key: "want", part: "いま、ほしいもの", text: D.want.text, opts: D.want.opts.map(o => o.label) });
    return q;
  }

  let idx = -1; // -1: はじめ、questions().length: 結果
  const app = document.getElementById("app");
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const count = (path, title) => { if (window.goatcounter && window.goatcounter.count) window.goatcounter.count({ path, title: title || path, event: true }); };

  function loadHistory() { try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]") || []; } catch (e) { return []; } }
  function saveHistory(list) { try { localStorage.setItem(HISTORY_KEY, JSON.stringify(list.slice(-10))); return true; } catch (e) { return false; } }
  const fmtDate = iso => { const d = new Date(iso); return (d.getMonth() + 1) + "月" + d.getDate() + "日"; };
  const placeLabel = h => h.stage + (h.sub ? "・" + h.sub : "");

  function cycleSvg(active) {
    const pos = { "準備": [180, 52], "遭遇": [308, 180], "順応": [180, 308], "安定": [52, 180] };
    const nodes = STAGES.map(s => {
      const [x, y] = pos[s];
      const on = s === active;
      return `<g>
        <circle cx="${x}" cy="${y}" r="38" style="fill:var(${on ? "--ck-node-on-bg" : "--ck-card"});stroke:var(${on ? "--ck-node-on-bg" : "--ck-sky-bright"})" stroke-width="2"/>
        <text x="${x}" y="${y + 7}" text-anchor="middle" font-size="20" font-weight="700" style="fill:var(${on ? "--ck-node-on-fg" : "--ck-ink"})">${s}</text>
      </g>`;
    }).join("");
    return `<svg class="cycle" viewBox="0 0 360 360" role="img" aria-label="転機のサイクル：準備、遭遇、順応、安定をくり返す${active ? "。いまは" + active : ""}">
      <defs><marker id="ah" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" style="fill:var(--ck-sky-bright)"/></marker></defs>
      <circle cx="180" cy="180" r="128" fill="none" style="stroke:var(--ck-line)" stroke-width="2"/>
      <path d="M 222 66 A 128 128 0 0 1 294 138" fill="none" style="stroke:var(--ck-sky-bright)" stroke-width="2" marker-end="url(#ah)"/>
      <path d="M 294 222 A 128 128 0 0 1 222 294" fill="none" style="stroke:var(--ck-sky-bright)" stroke-width="2" marker-end="url(#ah)"/>
      <path d="M 138 294 A 128 128 0 0 1 66 222" fill="none" style="stroke:var(--ck-sky-bright)" stroke-width="2" marker-end="url(#ah)"/>
      <path d="M 66 138 A 128 128 0 0 1 138 66" fill="none" style="stroke:var(--ck-sky-bright)" stroke-width="2" marker-end="url(#ah)"/>
      <text x="180" y="176" text-anchor="middle" font-size="13" style="fill:var(--ck-text-sub)">転機は</text>
      <text x="180" y="196" text-anchor="middle" font-size="13" style="fill:var(--ck-text-sub)">くり返し訪れる</text>
      ${nodes}
    </svg>`;
  }

  function renderIntro() {
    const hist = loadHistory();
    const last = hist[hist.length - 1];
    const total = questions().length;
    app.innerHTML = `<div class="stack-lg">
      <section class="stack">
        <h1>転機の段階<wbr>セルフチェック</h1>
        <p class="lead">転職、独立、副業、学び直し。キャリアの転機には「段階」があります。いまの段階と、転機を乗り切るための4つの資源のバランスを、${total}の質問でふりかえってみましょう。</p>
        <div class="meta"><span class="tag">全${total}問</span><span class="tag">約3分</span><span class="tag">登録不要</span></div>
        ${last ? `<p class="prev-note">前回（${fmtDate(last.at)}）は、${esc(last.tenki === "まだはっきりしない" ? "" : last.tenki + "の")}<b>${esc(placeLabel(last))}</b>でした。</p>` : ""}
        <div><button class="btn btn-primary" id="start">チェックを始める</button></div>
      </section>
      <section class="stack">
        ${cycleSvg(null)}
        <div class="stage-list">
          ${STAGES.map(s => `<div><b>${s}</b><span>${STAGE_INFO[s].short}</span></div>`).join("")}
        </div>
        <p class="small">心理学者ナイジェル・ニコルソンの「トランジション・サイクル」と、ナンシー・シュロスバーグの「4S」（状況・自分・支え・戦略）をもとにしています。診断ではなく、いまの自分をふりかえるきっかけとして使ってください。回答はこのページの中だけで使い、どこにも送信しません。</p>
      </section>
    </div>`;
    document.getElementById("start").onclick = () => { count("check-start", "セルフチェックを始めた"); go(0); };
  }

  function renderQuestion() {
    const qs = questions();
    const q = qs[idx];
    const a = A[q.key];
    const pct = Math.round((idx / qs.length) * 100);
    const opts = q.scale ? SCALE : q.opts;
    const body = `<div class="${q.scale ? "scale" : "opts"}" role="group" aria-labelledby="qt">
      ${opts.map((label, i) => `<button class="opt" data-i="${i}" aria-pressed="${a === i}">${esc(label)}</button>`).join("")}
    </div>`;
    app.innerHTML = `<div class="stack" style="gap:24px">
      <div class="progress" aria-hidden="true"><i style="width:${pct}%"></i></div>
      <div class="qhead"><p class="label">${esc(q.part)}</p><span class="qcount">${idx + 1} / ${qs.length}</span></div>
      <p class="qtext" id="qt">${esc(q.text)}</p>
      ${body}
      <div class="qnav">
        <button class="btn btn-ghost" id="back">${idx === 0 ? "はじめに戻る" : "前の質問へ"}</button>
        ${a !== undefined && idx < qs.length - 1 ? `<button class="btn btn-ghost" id="next">次の質問へ</button>` : ""}
      </div>
    </div>`;
    app.querySelectorAll(".opt").forEach(b => b.onclick = () => {
      const v = Number(b.dataset.i);
      // 入る前／入った後が変わったら、その後に分かれる質問の答えを消す（意味が変わるため）
      if (q.key === "phase" && A.phase !== undefined && (A.phase === 2) !== (v === 2)) {
        ["when", "since", "b0", "b1", "b2", "a0", "a1", "a2"].forEach(k => delete A[k]);
      }
      A[q.key] = v;
      go(idx + 1);
    });
    document.getElementById("back").onclick = () => go(idx - 1);
    const nx = document.getElementById("next");
    if (nx) nx.onclick = () => go(idx + 1);
  }

  function score() {
    const tenki = D.tenki[A.tenki] || "まだはっきりしない";
    const unexpected = A.chosen >= 2;
    let stage, sub = null, note = "", nextHint = false;
    if (isBefore()) {
      // 新しい環境に入る前は「準備」。そのなかの位置を、3問と時期の見通しで決める
      stage = "準備";
      const [v0, v1, v2] = [sv(A.b0), sv(A.b1), sv(A.b2)];
      const decide = v2 >= 2 || A.when === 3 || (A.phase === 1 && A.when >= 2);
      sub = decide ? "決断と行動" : (v0 >= 2 || v1 >= 2 || A.phase === 1) ? "情報あつめ" : "もやもや";
    } else {
      // 入った後は、入ってからの期間を土台に、慣れ具合で前後に調整する
      stage = ["遭遇", "順応", "安定"][A.since];
      const adapt = sv(A.a0) + sv(A.a1), next = sv(A.a2);
      if (stage === "遭遇" && adapt >= 5) { stage = "順応"; note = "入ってまだ日は浅いものの、思ったより早く慣れてきているようです。"; }
      else if (stage === "順応" && adapt <= 1) { stage = "遭遇"; note = "期間のわりに、まだ戸惑いが大きいようです。人によって慣れる早さはちがうので、あせらなくて大丈夫です。"; }
      else if (stage === "順応" && adapt >= 5 && next >= 2) { stage = "安定"; note = "1年たっていなくても、もう落ち着いて次を見すえ始めているようです。"; }
      else if (stage === "安定" && adapt <= 2) { stage = "順応"; note = "1年以上たっても、まだ慣れきっていない感覚があるようです。"; }
      nextHint = stage === "安定" && next >= 2;
    }
    const s4 = {};
    S4.forEach(s => { s4[s] = sv(A["s_" + s + "0"]) + sv(A["s_" + s + "1"]); });
    // いちばん手薄な資源。同点のときは、思いがけない転機なら支え・状況を、それ以外は支え・戦略を先にする
    const order = unexpected ? ["支え", "状況", "自分", "戦略"] : ["支え", "戦略", "自分", "状況"];
    const min = Math.min(...S4.map(s => s4[s]));
    const low = min <= 4 ? order.find(s => s4[s] === min) : null;
    const want = D.want.opts[A.want] || null;
    return { tenki, unexpected, stage, sub, note, nextHint, s4, low, want };
  }
  const level = v => v <= 2 ? "手薄" : v <= 4 ? "ほどほど" : "十分";

  function pickItems(r) {
    const lowTypes = r.low ? D.s4[r.low].types : [];
    const scored = PICKS.map(p => {
      let s = 0;
      if (p.stage.includes(r.stage)) s += 4;
      if (p.tenki.includes(r.tenki)) s += 3; else if (p.tenki.includes("共通")) s += 1;
      if (lowTypes.includes(p.type)) s += 3;
      if (r.want && p.type === r.want.type) s += 2;
      return { p, s };
    }).filter(x => x.s > 0).sort((a, b) => b.s - a.s || a.p.rank - b.p.rank);
    const out = scored.slice(0, 3).map(x => x.p);
    // 手薄な資源を補うものが1件もなければ、3件目をそのタイプのいちばん合うものに入れ替える
    if (lowTypes.length && !out.some(p => lowTypes.includes(p.type))) {
      const alt = scored.find(x => lowTypes.includes(x.p.type));
      if (alt) out[out.length - 1] = alt.p;
    }
    return out;
  }

  function listUrl(r) {
    const p = new URLSearchParams();
    if (r.tenki !== "まだはっきりしない") p.set("tenki", r.tenki);
    p.set("stage", r.stage);
    return "/search/?" + p.toString();
  }

  function mediaHtml(img) {
    img = img || {};
    if (img.src) return `<div class="card-media media-${esc(img.fit)}" aria-hidden="true"><img src="${esc(img.src)}" alt="" loading="lazy" decoding="async"></div>`;
    return `<div class="card-media media-none" aria-hidden="true"><span>${esc(img.emoji || "")}</span></div>`;
  }

  // アクセス解析：結果に出たおすすめが押されたら、どの掲載かを数える（回答や結果は送らない）
  document.addEventListener("click", ev => {
    const a = ev.target.closest(".pick a");
    if (!a) return;
    const card = a.closest(".pick");
    count("check-pick/" + card.dataset.pick, card.dataset.pickTitle);
  });

  function observatoryHtml(r) {
    if (!PICKS) return `<p><a href="/">あしたの転機観測所で、転機に役立つサービスを探す</a></p>`;
    const picks = pickItems(r);
    const why = r.low ? `いまの段階と、手薄な「${r.low}」を補えそうなものを選びました。` : "いまの段階に合いそうなものを選びました。";
    return `<section class="stack">
        <h2>あしたの転機観測所から</h2>
        <p class="lead">転機に役立つ民間のサービスや情報を集めている「あしたの転機観測所」から、${why}</p>
        <div class="picks">
          ${picks.map(p => `<article class="card pick" data-pick="${esc(p.id)}" data-pick-title="${esc(p.title)}">
            ${mediaHtml(p.img)}
            <div class="pick-body">
            <div class="pick-top"><span class="pick-type">${esc(p.type)}</span><span class="small">${esc(p.stage.join("、"))}向け</span></div>
            <h3>${p.url ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a>` : esc(p.title)}</h3>
            <p>${esc(p.memo)}</p>
            ${p.page ? `<p class="small"><a href="${esc(p.page)}">観測所の紹介ページを見る</a></p>` : ""}
            </div>
          </article>`).join("")}
        </div>
        <p><a href="${esc(listUrl(r))}">${esc(r.tenki === "まだはっきりしない" ? `「${r.stage}」の段階で役立つものを、観測所ですべて見る` : `「${r.tenki}×${r.stage}」で役立つものを、観測所ですべて見る`)}</a></p>
      </section>`;
  }

  function memoText(r) {
    const chosen = D.chosen.opts[A.chosen] || "";
    const lines = [
      "【転機の段階セルフチェック　相談メモ】",
      "転機：" + r.tenki + "（" + chosen.replace(/（.*）/, "") + "）",
      "いまの段階：" + r.stage + (r.sub ? "（" + r.sub + "）" : ""),
      "4つの資源：" + S4.map(s => s + "は" + level(r.s4[s])).join("、"),
      r.low ? "いちばん手薄なもの：" + r.low : "",
      r.want ? "いま、いちばんほしいもの：" + r.want.label : "",
      "（" + fmtDate(new Date().toISOString()) + "にチェック）"
    ];
    return lines.filter(Boolean).join("\n");
  }

  function renderResult() {
    const r = score();
    const info = STAGE_INFO[r.stage];
    const combo = (D.combos[r.tenki] || {})[r.stage] || D.generic[r.stage];
    const tenkiLabel = r.tenki === "まだはっきりしない" ? "転機" : `${r.tenki}の転機`;
    const comboLabel = r.tenki === "まだはっきりしない" ? r.stage : `${r.tenki}×${r.stage}`;
    const hist = loadHistory();
    const prev = hist[hist.length - 1];
    const placeNow = { stage: r.stage, sub: r.sub };
    count("check-done/" + r.stage + (r.sub ? "-" + r.sub : ""), "セルフチェックを終えた：" + placeLabel(placeNow));

    const shareBody = `「転機の段階セルフチェック」をやってみたら、いまは「${r.stage}」の段階でした。`;
    const tagText = HASHTAGS.map(t => "#" + t).join(" ");
    const shareUrl = SHARE_URL + STAGE_SLUG[r.stage] + "/";
    const shareText = `${shareBody}\n${shareUrl}\n${tagText}`;
    const xUrl = "https://twitter.com/intent/tweet?text=" + encodeURIComponent(shareBody) + "&url=" + encodeURIComponent(shareUrl) + "&hashtags=" + encodeURIComponent(HASHTAGS.join(","));
    const fbUrl = "https://www.facebook.com/sharer/sharer.php?u=" + encodeURIComponent(shareUrl);
    const memo = memoText(r);

    app.innerHTML = `<div class="stack-lg">
      <section class="result-hero">
        <p>${esc(tenkiLabel)}のなかで、いまのあなたは</p>
        <p class="stage-name">${r.stage}</p>
        ${r.sub ? `<div class="sub-steps" aria-label="準備のなかの位置：${esc(r.sub)}">${SUBS.map(s => `<span${s === r.sub ? ' class="on"' : ""}>${s}</span>`).join("")}</div>` : ""}
        <p>${info.short}にいるようです。${esc(r.note)}${r.nextHint ? esc(D.next_hint) : ""}</p>
      </section>

      ${r.unexpected ? `<p class="gentle">${esc(D.unexpected)}</p>` : ""}

      <section class="stack">
        ${cycleSvg(r.stage)}
        <h2>「${r.stage}${r.sub ? "・" + r.sub : ""}」はどんな時期？</h2>
        <p class="lead">${esc(r.sub ? D.sub[r.sub].desc : info.desc)}</p>
        <div class="card stack">
          <h3>この時期によくあること</h3>
          <ul class="common">${combo.common.map(s => `<li>${esc(s)}</li>`).join("")}</ul>
        </div>
        <div class="card stack">
          <h3>次の一歩（${esc(comboLabel)}）</h3>
          <ol class="steps">${combo.steps.map(s => `<li>${esc(s)}</li>`).join("")}</ol>
        </div>
      </section>

      <section class="stack">
        <h2>転機を乗り切る<wbr>4つの資源</h2>
        <div class="s4" aria-label="4つの資源のバランス">
          ${S4.map(s => `<div class="s4-row${s === r.low ? " low" : ""}"><b>${s}</b><div class="track"><i style="width:${Math.max(6, Math.round(r.s4[s] / 6 * 100))}%"></i></div><span class="lv">${level(r.s4[s])}</span><span class="s4-short">${esc(D.s4[s].short)}</span></div>`).join("")}
        </div>
        ${r.low ? `<p class="lead"><b>いちばん手薄なのは「${r.low}」です。</b>${esc(D.s4[r.low].low)}</p>`
                : `<p class="lead">4つの資源が、どれもある程度そろっています。いまの支えや進め方を保ちながら、次の一歩に進んでみてください。</p>`}
      </section>

      <div id="observatory"></div>

      <section class="stack memo-sec">
        <h2>相談メモ</h2>
        <p class="small">キャリアコンサルタントや信頼できる人に相談するときに、そのまま見せたり送ったりできます。</p>
        <p class="memo" id="memo">${esc(memo)}</p>
        <div class="share no-print">
          <button id="memo-copy">メモをコピー</button>
          <button id="memo-print">印刷する</button>
        </div>
      </section>

      <section class="stack no-print">
        <h2>前回と比べる</h2>
        ${prev ? `<p class="prev-note">前回（${fmtDate(prev.at)}）は <b>${esc(placeLabel(prev))}</b>、いまは <b>${esc(placeLabel(placeNow))}</b> です。</p>` : ""}
        <p class="small">結果を残すと、次にチェックしたときに比べられます。残した結果は、この端末のこのブラウザの中だけに保存し、どこにも送りません。</p>
        <div class="share"><button id="save">この結果を残す</button>${hist.length ? `<button id="forget">残した結果を消す</button>` : ""}</div>
        <p class="small" id="savenote" aria-live="polite"></p>
      </section>

      <hr class="rule">

      <section class="stack no-print">
        <h2>転機を<wbr>ひとりで抱えこまないために</h2>
        <p class="lead">「あしたの転機」は、キャリアの転機について考え、語り合うコミュニティです。いろいろな転機を経験した人の話に触れてみてください。</p>
        <div class="links">
          <a class="card linkcard" href="${FB_URL}" target="_blank" rel="noopener"><b>Facebookグループ</b><span>転機について語り合う場。気軽にのぞいてみてください</span></a>
          <a class="card linkcard" href="${NOTE_URL}" target="_blank" rel="noopener"><b>noteマガジン</b><span>転機にまつわる話を、記事で読めます</span></a>
        </div>
      </section>

      <section class="stack no-print">
        <h3>結果をシェアする</h3>
        <p class="share-text" id="sharetext">${esc(shareText)}</p>
        <div class="share">
          <a href="${xUrl}" target="_blank" rel="noopener">Xでシェア</a>
          <a href="${fbUrl}" target="_blank" rel="noopener" id="fbshare">Facebookでシェア</a>
          <button id="copy">文章をコピー</button>
        </div>
        <p class="small" id="sharenote" aria-live="polite">Facebookでシェアするときは、上の文章が自動でコピーされます。開いた画面の投稿欄に貼り付けてください。</p>
      </section>

      <div class="no-print"><button class="btn btn-ghost" id="retry">もう一度チェックする</button></div>

      <footer class="stack">
        <p class="small">このチェックは、心理学者ナイジェル・ニコルソンの「トランジション・サイクル」（準備・遭遇・順応・安定）と、ナンシー・シュロスバーグの「4S」（状況・自分・支え・戦略）をもとに、黒田悠介（キャリア研究家）が作りました。医学的・心理学的な診断ではありません。回答はこのページの中だけで使い、どこにも送信しません。</p>
      </footer>
    </div>`;

    const obs = document.getElementById("observatory");
    const fillObs = () => { if (obs.isConnected) obs.innerHTML = observatoryHtml(r); };
    fillObs();
    picksReady.then(fillObs);

    const copyText = (text, btn, label, onFail) => {
      const done = () => { btn.textContent = "コピーしました"; setTimeout(() => btn.textContent = label, 2000); };
      try { navigator.clipboard.writeText(text).then(done, onFail); } catch (e) { onFail(); }
    };
    const selectEl = id => { const range = document.createRange(); range.selectNodeContents(document.getElementById(id)); const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range); };

    const memoBtn = document.getElementById("memo-copy");
    memoBtn.onclick = () => copyText(memo, memoBtn, "メモをコピー", () => { selectEl("memo"); memoBtn.textContent = "選択しました。コピーしてください"; });
    document.getElementById("memo-print").onclick = () => window.print();

    const saveBtn = document.getElementById("save"), saveNote = document.getElementById("savenote");
    saveBtn.onclick = () => {
      const list = loadHistory();
      list.push({ at: new Date().toISOString(), tenki: r.tenki, stage: r.stage, sub: r.sub, s4: r.s4 });
      if (saveHistory(list)) { saveBtn.disabled = true; saveBtn.textContent = "残しました"; saveNote.textContent = "次にチェックしたときに、前回として表示します。"; }
      else saveNote.textContent = "このブラウザでは結果を残せませんでした。";
    };
    const forget = document.getElementById("forget");
    if (forget) forget.onclick = () => { try { localStorage.removeItem(HISTORY_KEY); } catch (e) {} forget.remove(); saveNote.textContent = "残した結果を消しました。"; };

    document.getElementById("retry").onclick = () => { Object.keys(A).forEach(k => delete A[k]); go(-1); };
    const copyBtn = document.getElementById("copy");
    copyBtn.onclick = () => copyText(shareText, copyBtn, "文章をコピー", () => { selectEl("sharetext"); copyBtn.textContent = "選択しました。コピーしてください"; });
    const note = document.getElementById("sharenote");
    // Facebookはシェア画面に投稿文を入れておけないため、Xと同じ投稿文をコピーしてから開き、貼り付けてもらう
    document.getElementById("fbshare").onclick = ev => {
      ev.preventDefault();
      let copying;
      try { copying = navigator.clipboard.writeText(shareText); } catch (e) { copying = Promise.reject(e); }
      window.open(fbUrl, "_blank", "noopener");
      copying.then(() => { note.textContent = "投稿文をコピーしました。開いたFacebookの画面で、投稿欄に貼り付けてください。"; },
        () => { selectEl("sharetext"); note.textContent = "上の文章を選択しました。コピーして、Facebookの投稿欄に貼り付けてください。"; });
    };
  }

  function go(n) {
    const total = questions().length;
    idx = Math.max(-1, Math.min(n, total));
    document.body.classList.toggle("in-question", idx >= 0 && idx < total);
    if (idx === -1) renderIntro();
    else if (idx === total) renderResult();
    else renderQuestion();
    window.scrollTo({ top: 0 });
    const focusEl = app.querySelector("#qt, h1, .result-hero");
    if (focusEl) { focusEl.setAttribute("tabindex", "-1"); focusEl.focus({ preventScroll: true }); }
  }

  window.__tenki = { A, questions, score, go }; // 確認用
  renderIntro();
})();
