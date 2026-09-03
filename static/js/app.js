const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

const state = {
  filters: { game: "NLHE" },
  route: "overview",
  handId: null,
  chart: null,
  chart2: null,
  replay: null,
  step: 0,
};

let leakTimer = null;

function qs(extra = {}) {
  const f = { ...state.filters, ...extra };
  const p = new URLSearchParams();
  Object.entries(f).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") p.set(k, v);
  });
  return p.toString();
}

async function api(path) {
  const sep = path.includes("?") ? "&" : "?";
  const res = await fetch(path + (path.includes("/api/") && !path.includes("import") ? sep + qs() : ""));
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function money(n, signed = false) {
  const v = Number(n || 0);
  const abs = Math.abs(v).toFixed(2);
  if (!signed) return "$" + abs;
  return (v > 0 ? "+$" : v < 0 ? "-$" : "$") + abs;
}

function clsMoney(n) {
  const v = Number(n || 0);
  return v > 0 ? "win" : v < 0 ? "loss" : "";
}

function pct(n) {
  return n == null ? "—" : Number(n).toFixed(1) + "%";
}

function num(n, d = 1) {
  return n == null ? "—" : Number(n).toFixed(d);
}

function signedNum(n, d = 1) {
  if (n == null) return "—";
  const v = Number(n);
  const s = v.toFixed(d);
  return (v > 0 ? "+" : "") + s;
}

function suitClass(card) {
  if (!card) return "";
  return "dh".includes(card[1]) ? "red" : "";
}

function prettyCard(card) {
  if (!card) return "";
  const suits = { s: "♠", h: "♥", d: "♦", c: "♣" };
  return card[0] + (suits[card[1]] || card[1]);
}

function cardEl(card, back = false) {
  if (back) return `<span class="pcard back">?</span>`;
  if (!card) return "";
  return `<span class="pcard ${suitClass(card)}">${prettyCard(card)}</span>`;
}

function cardsHtml(str, hidden = false) {
  const parts = Array.isArray(str)
    ? str.filter(Boolean)
    : String(str || "").trim().split(/\s+/).filter(Boolean);
  if (hidden) return (parts.length ? parts : ["", ""]).map(() => cardEl(null, true)).join("");
  return parts.map((c) => cardEl(c)).join("");
}

function readFilters() {
  const form = $("#filters");
  const data = Object.fromEntries(new FormData(form).entries());
  state.filters = data;
}

function bindFilters() {
  const form = $("#filters");
  form.game.value = state.filters.game || "NLHE";
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    readFilters();
    render();
  });
  $("#reset-filters").addEventListener("click", () => {
    form.reset();
    form.game.value = "NLHE";
    readFilters();
    render();
  });
}

function setNav() {
  $$(".nav nav a").forEach((a) => {
    a.classList.toggle("active", a.dataset.route === state.route);
  });
}

function parseHash() {
  const h = location.hash.replace(/^#\/?/, "");
  const [route, id] = h.split("/");
  state.route = route || "overview";
  state.handId = id || null;
}

async function render() {
  if (leakTimer) {
    clearInterval(leakTimer);
    leakTimer = null;
  }
  parseHash();
  setNav();
  const app = $("#app");
  app.innerHTML = `<div class="loading">Loading…</div>`;
  try {
    if (state.route === "overview") await renderOverview(app);
    else if (state.route === "sessions") await renderSessions(app);
    else if (state.route === "hands") await renderHands(app);
    else if (state.route === "reports") await renderReports(app);
    else if (state.route === "matrix") await renderMatrix(app);
    else if (state.route === "players") await renderPlayers(app);
    else if (state.route === "graphs") await renderGraphs(app);
    else if (state.route === "solver") await renderSolver(app);
    else if (state.route === "import") await renderImport(app);
    else await renderOverview(app);
  } catch (err) {
    app.innerHTML = `<div class="empty">Could not load this view. ${err.message}</div>`;
  }
}

function kpi(label, value, hint, klass = "") {
  return `<article><div class="lbl">${label}</div><div class="val ${klass}">${value}</div><div class="hint">${hint || ""}</div></article>`;
}

function hudCell(label, value) {
  return `<article><div class="lbl">${label}</div><div class="val">${value}</div></article>`;
}

async function renderOverview(app) {
  const [sum, graph, leaks, ext, gto] = await Promise.all([
    api("/api/summary"),
    api("/api/graph"),
    api("/api/leaks"),
    api("/api/extrema"),
    api("/api/solver/leaks").catch(() => null),
  ]);
  $("#nav-foot").innerHTML = `${sum.hands.toLocaleString()} hands<br>${sum.first_hand || ""} → ${sum.last_hand || ""}`;
  app.innerHTML = `
    <div class="headline">
      <h1>Overview</h1>
      <div class="sub">${sum.first_hand || "—"} to ${sum.last_hand || "—"}</div>
    </div>
    <section class="kpi">
      ${kpi("Net won", money(sum.net, true), `${sum.hands.toLocaleString()} hands`, clsMoney(sum.net))}
      <article>
        <div class="lbl">BB / 100</div>
        <div class="val-pair">
          <div>
            <div class="n ${clsMoney(sum.bb100_before)}">${signedNum(sum.bb100_before)}</div>
            <div class="hint">before rake</div>
          </div>
          <div>
            <div class="n ${clsMoney(sum.bb100)}">${signedNum(sum.bb100)}</div>
            <div class="hint">after rake</div>
          </div>
        </div>
      </article>
      ${kpi("Won / lost", `${sum.won_hands} / ${sum.lost_hands}`, "hands decided")}
      ${kpi("Rake paid", money(sum.rake_paid), "from pots you won")}
    </section>
    <section class="hud">
      ${hudCell("VPIP", pct(sum.vpip))}
      ${hudCell("PFR", pct(sum.pfr))}
      ${hudCell("3-bet", pct(sum.threebet))}
      ${hudCell("Fold to 3-bet", pct(sum.fold_to_3bet))}
      ${hudCell("Steal", pct(sum.steal))}
      ${hudCell("Fold vs steal", pct(sum.fold_to_steal))}
      ${hudCell("C-bet flop", pct(sum.cbet_flop))}
      ${hudCell("Fold to c-bet", pct(sum.fold_to_cbet))}
      ${hudCell("WTSD", pct(sum.wtsd))}
      ${hudCell("W$SD", pct(sum.wsd))}
      ${hudCell("W$WSF", pct(sum.wwsf))}
      ${hudCell("AF", num(sum.af, 2))}
    </section>
    <div class="split">
      <div class="card">
        <h2>Cumulative winnings</h2>
        <div class="chart-box"><canvas id="eq-chart"></canvas></div>
        <p class="note">${money(graph.gross, true)} before rake · ${money(graph.net, true)} after rake · ${money(graph.rake_paid)} rake paid</p>
      </div>
      <div class="card">
        <h2>Leak finder vs 6-max cash</h2>
        ${leaks.map((l) => `
          <div class="leak">
            <div>
              <strong>${l.label}</strong>
              <p>${l.note}. Target ${l.low}–${l.high}${l.unit === "x" ? "x" : l.unit === "pp" ? " pp" : "%"}.</p>
            </div>
            <div>
              <div>${l.value}${l.unit === "x" ? "x" : l.unit === "pp" ? " pp" : "%"}</div>
              <div class="status ${l.status}">${l.status === "ok" ? "in range" : l.status}</div>
            </div>
          </div>
        `).join("")}
        ${gto && gto.spots ? `
          <div class="leak">
            <div>
              <strong>GTO mismatch (sample)</strong>
              <p>TexasSolver vs your ${gto.spots} biggest HU pots. Frequencies only — not true chip EV.</p>
            </div>
            <div>
              <div class="loss">${money(gto.ev_lost)}</div>
              <div class="status"><a href="#/solver">open solver</a></div>
            </div>
          </div>
        ` : ""}
      </div>
    </div>
    <div class="split" style="margin-top:16px">
      ${potList("Biggest wins", ext.wins)}
      ${potList("Biggest losses", ext.losses)}
    </div>
  `;
  drawEquity($("#eq-chart"), graph.points);
}

function potList(title, rows) {
  return `<div class="card"><h2>${title}</h2>
    <table>
      <thead><tr><th>When</th><th>Hand</th><th>Pos</th><th class="num">Net</th></tr></thead>
      <tbody>
        ${rows.map((r) => `<tr class="clickable" data-hand="${r.id}">
          <td>${r.played_at.slice(5, 16)}</td>
          <td>${r.cards || "—"}</td>
          <td>${r.pos}</td>
          <td class="num ${clsMoney(r.net)}">${money(r.net, true)}</td>
        </tr>`).join("")}
      </tbody>
    </table>
  </div>`;
}

function drawEquity(canvas, points) {
  if (state.chart) {
    state.chart.destroy();
    state.chart = null;
  }
  if (!window.Chart || !canvas || !points.length) return;
  const after = points.map((p) => p.net);
  const before = points.map((p) => (p.gross != null ? p.gross : p.net));
  const afterEnd = after[after.length - 1] || 0;
  state.chart = new Chart(canvas, {
    type: "line",
    data: {
      labels: points.map((p) => p.i),
      datasets: [
        {
          label: "Before rake",
          data: before,
          borderColor: "#74a8ff",
          backgroundColor: "transparent",
          fill: false,
          pointRadius: 0,
          borderWidth: 2,
          tension: 0.15,
        },
        {
          label: "After rake",
          data: after,
          borderColor: afterEnd >= 0 ? "#3dcf8e" : "#ef6b73",
          backgroundColor: afterEnd >= 0 ? "rgba(61,207,142,0.10)" : "rgba(239,107,115,0.10)",
          fill: true,
          pointRadius: 0,
          borderWidth: 2,
          tension: 0.15,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          labels: { color: "#c5cdd8", boxWidth: 12, boxHeight: 2, padding: 12 },
        },
      },
      scales: {
        x: {
          title: { display: true, text: "Hands", color: "#8d95a8" },
          ticks: { color: "#8d95a8", maxTicksLimit: 8 },
          grid: { color: "#2d3548" },
        },
        y: {
          title: { display: true, text: "Net ($)", color: "#8d95a8" },
          ticks: { color: "#8d95a8" },
          grid: { color: "#2d3548" },
        },
      },
    },
  });
}

async function renderSessions(app) {
  const rows = await api("/api/sessions");
  app.innerHTML = `
    <div class="headline"><h1>Sessions</h1><div class="sub">${rows.length} sessions (20-minute gap)</div></div>
    <div class="card">
      <table>
        <thead>
          <tr>
            <th>Start</th><th>End</th><th class="num">Min</th><th class="num">Hands</th>
            <th class="num">VPIP</th><th class="num">PFR</th><th class="num">BB/100</th>
            <th class="num">$/hr</th><th class="num">Net</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((r) => `<tr>
            <td>${r.started_at}</td>
            <td>${r.ended_at}</td>
            <td class="num">${r.duration_min}</td>
            <td class="num">${r.hands}</td>
            <td class="num">${pct(r.vpip)}</td>
            <td class="num">${pct(r.pfr)}</td>
            <td class="num ${clsMoney(r.bb100)}">${num(r.bb100, 1)}</td>
            <td class="num">${r.hourly == null ? "—" : money(r.hourly, true)}</td>
            <td class="num ${clsMoney(r.net)}">${money(r.net, true)}</td>
          </tr>`).join("")}
        </tbody>
      </table>
    </div>`;
}

async function renderHands(app) {
  const page = Number(new URLSearchParams(location.hash.split("?")[1] || "").get("page") || 1);
  const data = await api("/api/hands?" + qs({ page, page_size: 40, sort: "-ts" }));
  const selected = state.handId || (data.rows[0] && data.rows[0].id);
  app.innerHTML = `
    <div class="headline">
      <h1>Hands</h1>
      <div class="sub">${data.total.toLocaleString()} matching</div>
    </div>
    <div class="hands-layout">
      <div class="card">
        <table>
          <thead>
            <tr>
              <th>Time</th><th>Pos</th><th>Cards</th><th>Board</th>
              <th class="num">Pot</th><th class="num">Net</th>
            </tr>
          </thead>
          <tbody>
            ${data.rows.map((r) => `<tr class="clickable ${r.id === selected ? "active" : ""}" data-hand="${r.id}">
              <td>${r.played_at.slice(5)}</td>
              <td>${r.pos}</td>
              <td>${r.cards || "—"}</td>
              <td>${r.board || "—"}</td>
              <td class="num">${money(r.pot)}</td>
              <td class="num ${clsMoney(r.net)}">${money(r.net, true)}</td>
            </tr>`).join("")}
          </tbody>
        </table>
        <div class="pager">
          <span>Page ${data.page} of ${Math.max(1, Math.ceil(data.total / data.page_size))}</span>
          <button ${data.page <= 1 ? "disabled" : ""} data-page="${data.page - 1}">Prev</button>
          <button ${data.page * data.page_size >= data.total ? "disabled" : ""} data-page="${data.page + 1}">Next</button>
        </div>
      </div>
      <div class="replayer" id="replayer"><div class="empty">Select a hand</div></div>
    </div>
  `;
  app.querySelectorAll("[data-page]").forEach((btn) => {
    btn.addEventListener("click", () => {
      location.hash = "#/hands";
      state.handPage = Number(btn.dataset.page);
      renderHandsPaged(app, Number(btn.dataset.page));
    });
  });
  if (selected) await mountReplayer($("#replayer"), selected);
}

async function renderHandsPaged(app, page) {
  const data = await api("/api/hands?" + qs({ page, page_size: 40, sort: "-ts" }));
  const tbody = app.querySelector("tbody");
  tbody.innerHTML = data.rows.map((r) => `<tr class="clickable" data-hand="${r.id}">
    <td>${r.played_at.slice(5)}</td>
    <td>${r.pos}</td>
    <td>${r.cards || "—"}</td>
    <td>${r.board || "—"}</td>
    <td class="num">${money(r.pot)}</td>
    <td class="num ${clsMoney(r.net)}">${money(r.net, true)}</td>
  </tr>`).join("");
  bindHandClicks();
}

async function mountReplayer(el, id, opts = {}) {
  const [detail, review] = await Promise.all([
    fetch("/api/hands/" + encodeURIComponent(id)).then((r) => r.json()),
    fetch("/api/solver/review/" + encodeURIComponent(id)).then((r) => r.ok ? r.json() : null).catch(() => null),
  ]);
  if (!detail.replay) {
    el.innerHTML = `<pre class="action-log">${detail.raw || "No replay"}</pre>`;
    return;
  }
  state.replay = detail;
  const acts = detail.replay.actions.filter((a) =>
    ["sb", "bb", "post", "fold", "check", "call", "bet", "raise", "uncalled", "collect", "show"].includes(a.type)
  );
  state.replayActs = acts;
  state.gtoReview = review && review.ok ? review : null;
  const idx = state.gtoReview && state.gtoReview.decision_index != null
    ? Number(state.gtoReview.decision_index)
    : null;
  state.gtoDecisionIndex = Number.isInteger(idx) && idx >= 0 ? idx : null;
  if (opts.seekGto !== false && state.gtoDecisionIndex != null) {
    state.step = state.gtoDecisionIndex;
  } else {
    state.step = 0;
  }
  paintReplayer(el);
}

function paintReplayer(el) {
  const d = state.replay;
  const r = d.replay;
  const acts = state.replayActs;
  const step = state.step;
  const shown = acts.slice(0, step);
  const last = shown[shown.length - 1];
  const street = last ? last.street : "preflop";
  const board = boardForStreet(r.board, street);
  const seats = r.seats || [];
  const hero = seats.find((s) => s.is_hero) || seats[0];
  const n = Math.max(seats.length, 6);
  const heroIdx = Math.max(0, seats.findIndex((s) => s.is_hero));
  const layout = [
    { x: 50, y: 88 },
    { x: 14, y: 68 },
    { x: 14, y: 28 },
    { x: 50, y: 12 },
    { x: 86, y: 28 },
    { x: 86, y: 68 },
  ];
  const folded = new Set(shown.filter((a) => a.type === "fold").map((a) => a.player));
  const invested = {};
  seats.forEach((s) => (invested[s.name] = 0));
  shown.forEach((a) => {
    if (["sb", "bb", "post", "call", "bet", "raise"].includes(a.type)) {
      invested[a.player] = (invested[a.player] || 0) + (a.amount || 0);
    }
    if (a.type === "uncalled") invested[a.player] = Math.max(0, (invested[a.player] || 0) - (a.amount || 0));
  });
  const potCents = Object.values(invested).reduce((s, v) => s + v, 0);
  const showdown = street.includes("showdown") || shown.some((a) => a.type === "show");

  el.innerHTML = `
    <div style="display:flex;justify-content:space-between;gap:8px;margin-bottom:8px">
      <strong>${d.id}</strong>
      <span class="sub">${d.played_at} · ${d.pos} · ${money(d.net, true)}</span>
    </div>
    <div class="board-row">${board.map((c) => cardEl(c)).join("") || "<span class='sub'>No board yet</span>"}</div>
    <div class="table-wrap">
      <div class="pot"><div>Pot</div><div class="amt">${money(potCents / 100)}</div></div>
      ${seats.map((s, i) => {
        const vis = (i - heroIdx + n) % n;
        const loc = layout[vis] || layout[0];
        const cards = s.cards || [];
        let hole;
        if (s.is_hero) hole = cardsHtml(cards, false);
        else if (showdown && cards.length) hole = cardsHtml(cards, false);
        else if (!folded.has(s.name)) hole = cardsHtml(cards, true);
        else hole = "";
        return `<div class="seat ${s.is_hero ? "hero" : ""} ${last && last.player === s.name ? "active" : ""}" style="left:${loc.x}%;top:${loc.y}%">
          <div class="cards">${hole}</div>
          <div class="name">${s.name}${folded.has(s.name) ? " (fold)" : ""}</div>
          <div class="meta">${s.position} · ${money((s.stack || 0) / 100)}</div>
        </div>`;
      }).join("")}
    </div>
    <div class="replay-controls">
      <button data-rel="prev">Prev</button>
      <button data-rel="next">${state.gtoReview && step === state.gtoDecisionIndex ? "Take action" : "Next"}</button>
      <button data-rel="end">End</button>
      <button class="primary" data-rel="solver">Solve this spot</button>
    </div>
    ${state.gtoReview && state.gtoDecisionIndex != null ? gtoPolicyHtml(state.gtoReview, step > state.gtoDecisionIndex) : ""}
    <div class="action-log">
      ${acts.map((a, i) => `<div class="${i === step - 1 ? "on" : i === step ? "pending" : ""}">${a.street} · ${a.player} ${a.type}${a.amount ? " " + money(a.amount / 100) : ""}${a.to_amount ? " to " + money(a.to_amount / 100) : ""}</div>`).join("")}
    </div>
    <details style="margin-top:8px"><summary>Raw history</summary><pre class="action-log">${d.raw}</pre></details>
  `;
  el.querySelector("[data-rel=prev]").onclick = () => { state.step = Math.max(0, step - 1); paintReplayer(el); };
  el.querySelector("[data-rel=next]").onclick = () => { state.step = Math.min(acts.length, step + 1); paintReplayer(el); };
  el.querySelector("[data-rel=end]").onclick = () => { state.step = acts.length; paintReplayer(el); };
  el.querySelector("[data-rel=solver]").onclick = () => { location.hash = "#/solver/" + encodeURIComponent(d.id); };
  const focus = el.querySelector(".action-log .on, .action-log .pending");
  if (focus) focus.scrollIntoView({ block: "nearest" });
}

function boardForStreet(board, street) {
  const cards = board || [];
  if (street === "preflop") return [];
  if (street === "flop") return cards.slice(0, 3);
  if (street === "turn") return cards.slice(0, 4);
  return cards.slice(0, 5);
}

async function renderReports(app) {
  const [pos, time, leaks] = await Promise.all([
    api("/api/positions"),
    api("/api/time"),
    api("/api/leaks"),
  ]);
  app.innerHTML = `
    <div class="headline"><h1>Reports</h1><div class="sub">Position, clock, and leak tracker</div></div>
    <div class="card" style="margin-bottom:16px">
      <h2>By position</h2>
      <table>
        <thead><tr>
          <th>Pos</th><th class="num">Hands</th><th class="num">VPIP</th><th class="num">PFR</th>
          <th class="num">3-bet</th><th class="num">Steal</th><th class="num">WTSD</th>
          <th class="num">BB/100</th><th class="num">Net</th>
        </tr></thead>
        <tbody>
          ${pos.map((r) => `<tr>
            <td>${r.pos}</td>
            <td class="num">${r.hands}</td>
            <td class="num">${pct(r.vpip)}</td>
            <td class="num">${pct(r.pfr)}</td>
            <td class="num">${pct(r.threebet)}</td>
            <td class="num">${pct(r.steal)}</td>
            <td class="num">${pct(r.wtsd)}</td>
            <td class="num ${clsMoney(r.bb100)}">${num(r.bb100, 1)}</td>
            <td class="num ${clsMoney(r.net)}">${money(r.net, true)}</td>
          </tr>`).join("")}
        </tbody>
      </table>
    </div>
    <div class="split">
      <div class="card">
        <h2>By hour</h2>
        <table>
          <thead><tr><th>Hour</th><th class="num">Hands</th><th class="num">VPIP</th><th class="num">BB/100</th><th class="num">Net</th></tr></thead>
          <tbody>
            ${time.hours.map((r) => `<tr>
              <td>${String(r.hour).padStart(2, "0")}:00</td>
              <td class="num">${r.hands}</td>
              <td class="num">${pct(r.vpip)}</td>
              <td class="num ${clsMoney(r.bb100)}">${num(r.bb100, 1)}</td>
              <td class="num ${clsMoney(r.net)}">${money(r.net, true)}</td>
            </tr>`).join("")}
          </tbody>
        </table>
      </div>
      <div class="card">
        <h2>By day</h2>
        <table>
          <thead><tr><th>Day</th><th class="num">Hands</th><th class="num">BB/100</th><th class="num">Net</th></tr></thead>
          <tbody>
            ${time.days.map((r) => `<tr>
              <td>${r.day}</td>
              <td class="num">${r.hands}</td>
              <td class="num ${clsMoney(r.bb100)}">${num(r.bb100, 1)}</td>
              <td class="num ${clsMoney(r.net)}">${money(r.net, true)}</td>
            </tr>`).join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

async function renderMatrix(app) {
  const rows = await api("/api/starting-hands");
  const by = Object.fromEntries(rows.map((r) => [r.hand, r]));
  const ranks = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"];
  const cells = [];
  ranks.forEach((a, i) => {
    ranks.forEach((b, j) => {
      let key;
      if (i === j) key = a + a;
      else if (i < j) key = a + b + "s";
      else key = b + a + "o";
      cells.push({ key, data: by[key] });
    });
  });
  const withHands = cells.filter((c) => c.data && c.data.hands);
  const maxAbs = Math.max(20, ...withHands.map((c) => Math.abs(c.data.bb100 || 0)));
  function bg(d) {
    if (!d || !d.hands) return "#161b27";
    const t = Math.max(-1, Math.min(1, (d.bb100 || 0) / maxAbs));
    if (t >= 0) return `rgba(61, 207, 142, ${0.12 + t * 0.55})`;
    return `rgba(239, 107, 115, ${0.12 + -t * 0.55})`;
  }
  let html = `<div class="headline"><h1>Starting hands</h1><div class="sub">Color = BB/100. Click a cell to filter hands.</div></div>
    <div class="card" style="overflow:auto">
    <table class="matrix"><tbody>`;
  ranks.forEach((a, i) => {
    html += "<tr>";
    ranks.forEach((b, j) => {
      let key;
      if (i === j) key = a + a;
      else if (i < j) key = a + b + "s";
      else key = b + a + "o";
      const d = by[key];
      html += `<td data-handkey="${key}" style="background:${bg(d)}" title="${key}">
        <span class="h">${key}</span>
        <span class="n">${d ? d.hands : ""}</span>
      </td>`;
    });
    html += "</tr>";
  });
  html += `</tbody></table>
    <p class="note">Upper triangle is suited, lower is offsuit, diagonal is pairs. Sample size is on each tile.</p>
    </div>`;
  app.innerHTML = html;
  app.querySelectorAll("[data-handkey]").forEach((td) => {
    td.addEventListener("click", () => {
      const form = $("#filters");
      form.q.value = "";
      state.filters = { ...state.filters, hand: td.dataset.handkey };
      location.hash = "#/hands";
    });
  });
}

async function renderPlayers(app) {
  const data = await api("/api/players?" + qs({ min_hands: 5, page_size: 50 }));
  app.innerHTML = `
    <div class="headline"><h1>Players</h1><div class="sub">${data.total} opponents with 5+ hands — Rush IDs rarely repeat</div></div>
    <div class="card">
      <table>
        <thead>
          <tr>
            <th>Player</th><th class="num">Hands</th><th class="num">VPIP</th><th class="num">PFR</th>
            <th class="num">3-bet</th><th class="num">C-bet</th><th class="num">WTSD</th><th class="num">W$SD</th>
          </tr>
        </thead>
        <tbody>
          ${data.rows.map((r) => `<tr>
            <td>${r.name}</td>
            <td class="num">${r.hands}</td>
            <td class="num">${pct(r.vpip)}</td>
            <td class="num">${pct(r.pfr)}</td>
            <td class="num">${pct(r.threebet)}</td>
            <td class="num">${pct(r.cbet_flop)}</td>
            <td class="num">${pct(r.wtsd)}</td>
            <td class="num">${pct(r.wsd)}</td>
          </tr>`).join("")}
        </tbody>
      </table>
    </div>`;
}

async function renderGraphs(app) {
  const [graph, time] = await Promise.all([api("/api/graph"), api("/api/time")]);
  app.innerHTML = `
    <div class="headline"><h1>Graphs</h1><div class="sub">${graph.hands.toLocaleString()} hands · ${money(graph.gross, true)} before rake · ${money(graph.net, true)} after rake</div></div>
    <div class="card" style="margin-bottom:16px">
      <h2>Cumulative $</h2>
      <div class="chart-box"><canvas id="g1"></canvas></div>
    </div>
    <div class="card">
      <h2>Daily net</h2>
      <div class="chart-box"><canvas id="g2"></canvas></div>
    </div>`;
  drawEquity($("#g1"), graph.points);
  if (state.chart2) { state.chart2.destroy(); state.chart2 = null; }
  if (!window.Chart) return;
  state.chart2 = new Chart($("#g2"), {
    type: "bar",
    data: {
      labels: time.days.map((d) => d.day.slice(5)),
      datasets: [{
        label: "Net ($)",
        data: time.days.map((d) => d.net),
        backgroundColor: time.days.map((d) => d.net >= 0 ? "rgba(61,207,142,0.7)" : "rgba(239,107,115,0.7)"),
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#8d95a8" }, grid: { color: "#2d3548" } },
        y: { ticks: { color: "#8d95a8" }, grid: { color: "#2d3548" } },
      },
    },
  });
}

function importSummary(json) {
  const parsed = json.parsed || 0;
  const inserted = json.inserted || 0;
  const skipped = json.skipped || 0;
  const total = (json.total || 0).toLocaleString();
  if (!parsed && !inserted) return `Nothing imported. Database still has ${total} hands.`;
  if (skipped && !inserted) {
    return `All ${parsed.toLocaleString()} hands were already in the database (${total} total).`;
  }
  if (skipped) {
    return `Parsed ${parsed.toLocaleString()} hands, added ${inserted.toLocaleString()} new, skipped ${skipped.toLocaleString()} duplicates. Database now has ${total}.`;
  }
  return `Parsed ${parsed.toLocaleString()} hands, added ${inserted.toLocaleString()}. Database now has ${total}.`;
}

function mixBars(actions, freqs, opts = {}) {
  if (!actions || !freqs) return "";
  return actions.map((a, i) => {
    const p = Math.round((Number(freqs[i]) || 0) * 1000) / 10;
    const mark = a === opts.match ? " match" : a === opts.best ? " best" : "";
    return `<div class="mix${mark}"><span class="mix-lbl">${a}</span><span class="mix-bar"><i style="width:${Math.min(100, p)}%"></i></span><span class="mix-n">${p}%</span></div>`;
  }).join("");
}

function gtoPolicyHtml(review, revealed) {
  if (!review) return "";
  const street = (review.street || "").toUpperCase();
  if (!revealed) {
    return `<div class="gto-panel pending">
      <h2>Your ${street} decision</h2>
      <p class="note">Prior action is on the table. Press <strong>Take action</strong> to play <strong>${review.hero_action || "your line"}</strong> and see the GTO mix.</p>
    </div>`;
  }
  const mix = review.mix || {};
  const bars = mix.actions && mix.freqs
    ? mixBars(mix.actions, mix.freqs, { match: review.gto_match, best: review.gto_best })
    : "";
  const youPct = review.gto_freq == null ? "—" : (Math.round(Number(review.gto_freq) * 1000) / 10) + "%";
  return `<div class="gto-panel">
    <h2>GTO policy · ${street} · ${(review.hero_role || "").toUpperCase()}</h2>
    <p>You took <strong>${review.hero_action || "—"}</strong> (${youPct} of GTO). Solver prefers <strong>${review.gto_best || "—"}</strong>.</p>
    ${bars}
    ${review.note ? `<p class="note">${review.note}</p>` : ""}
    <p class="note">Frequencies for your combo vs a default 6-max cash range — not true chip EV.</p>
  </div>`;
}

function leakChips(items) {
  if (!items || !items.length) return "";
  return `<div class="leak-stats">${items.map((x) => `
    <div class="leak-chip"><div class="k">${x.key} · ${x.n}</div><div class="v loss">${money(x.ev_lost)}</div></div>
  `).join("")}</div>`;
}

function leakTable(rows) {
  if (!rows || !rows.length) return `<p class="note">No scored spots yet. Run an analysis on your worst HU pots.</p>`;
  return `<table>
    <thead><tr>
      <th>Hand</th><th>Street</th><th>Pos</th><th>You</th><th>GTO</th>
      <th class="num">GTO %</th><th class="num">Est. leak</th><th class="num">Net</th>
    </tr></thead>
    <tbody>
      ${rows.map((r) => `
        <tr class="clickable" data-gto-hand="${r.id}">
          <td>${cardsHtml(r.cards)} <span class="note" style="margin:0">${r.board || ""}</span></td>
          <td>${(r.street || "").toUpperCase()} ${r.role || ""}</td>
          <td>${r.pos || ""}</td>
          <td>${r.action || ""}</td>
          <td>${r.gto_best || "—"} ${r.gto_match && r.gto_match !== r.gto_best ? "vs " + r.gto_match : ""}</td>
          <td class="num">${r.gto_freq == null ? "—" : Math.round(Number(r.gto_freq) * 1000) / 10}%</td>
          <td class="num loss">${money(r.ev_lost)}</td>
          <td class="num ${clsMoney(r.net)}">${money(r.net, true)}</td>
        </tr>
        ${r.note ? `<tr><td colspan="8" class="note" style="margin:0;border:0">${r.note}</td></tr>` : ""}
      `).join("")}
    </tbody>
  </table>`;
}

function paintLeakPanel(el, cat, leaks, job) {
  if (!el) return;
  const j = job || (leaks && leaks.job) || (cat && cat.job) || { state: "idle" };
  const running = j.state === "running";
  const pctDone = j.total ? Math.round((100 * (j.done || 0)) / j.total) : (running ? 5 : 0);
  const eligible = cat ? cat.eligible : 0;
  const streets = cat && cat.by_street
    ? Object.entries(cat.by_street).map(([k, n]) => `${n} ${k}`).join(" · ")
    : "";
  const roles = cat && cat.by_role
    ? Object.entries(cat.by_role).map(([k, n]) => `${n} ${k.toUpperCase()}`).join(" · ")
    : "";
  el.innerHTML = `
    <h2>Where you lose EV vs GTO</h2>
    <p class="note">${(leaks && leaks.note) || (cat && cat.note) || ""}</p>
    <p>${eligible.toLocaleString()} HU postflop spots in this filter${streets ? " · " + streets : ""}${roles ? " · " + roles : ""}.</p>
    <div class="solver-tools">
      <label>Sample
        <select id="leak-limit">
          <option value="8">8 spots</option>
          <option value="12" selected>12 spots</option>
          <option value="20">20 spots</option>
          <option value="0">All eligible (~30s each)</option>
        </select>
      </label>
      <label>Pick
        <select id="leak-by">
          <option value="loss" selected>Biggest losses first</option>
          <option value="pot">Biggest pots first</option>
        </select>
      </label>
      <label>Quality
        <select id="leak-preset">
          <option value="quick">Quick (~30s cap)</option>
          <option value="audit" selected>Audit</option>
          <option value="fast">Fast</option>
        </select>
      </label>
      <button class="primary" id="leak-run" ${running || !(cat && cat.installed) ? "disabled" : ""}>
        ${running ? "Solving…" : "Analyze biggest leaks"}
      </button>
    </div>
    ${running || j.state === "done" || j.state === "error" ? `
      <div class="progress-track"><i style="width:${pctDone}%"></i></div>
      <p class="note">${j.message || ""} ${j.total ? j.done + " / " + j.total : ""}</p>
    ` : ""}
    ${leaks && leaks.spots ? `
      <p>Estimated mismatch <strong class="loss">${money(leaks.ev_lost)}</strong> across ${leaks.spots} scored spots.</p>
      <h2 style="margin-top:16px">By street</h2>
      ${leakChips(leaks.by_street)}
      <h2>IP vs OOP</h2>
      ${leakChips(leaks.by_role)}
      <h2>By action</h2>
      ${leakChips(leaks.by_action)}
      <h2>By position</h2>
      ${leakChips(leaks.by_pos)}
      <h2>Worst mismatches</h2>
      ${leakTable(leaks.worst)}
      <p class="note">Click a hand to replay all prior action, then take your line to see the GTO mix.</p>
    ` : (running ? `<p class="note">Solving in the background. You can leave this page open — results fill in as spots finish.</p>` : `<p class="note">Sample your biggest losing HU pots, or run every eligible spot (~30s cap each). Click a scored hand to replay it.</p>`)}
  `;
  const limitSel = $("#leak-limit", el);
  const presetSel = $("#leak-preset", el);
  if (limitSel && presetSel) {
    limitSel.onchange = () => {
      if (limitSel.value === "0") presetSel.value = "quick";
    };
  }
  el.querySelectorAll("[data-gto-hand]").forEach((row) => {
    if (state.replay && state.replay.id === row.dataset.gtoHand) row.classList.add("active");
    row.onclick = async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const box = $("#gto-replay");
      if (!box) return;
      box.style.display = "block";
      el.querySelectorAll("[data-gto-hand]").forEach((r) => r.classList.toggle("active", r === row));
      await mountReplayer(box, row.dataset.gtoHand, { seekGto: true });
      box.scrollIntoView({ behavior: "smooth", block: "nearest" });
    };
  });
  const run = $("#leak-run", el);
  if (run && !running) {
    run.onclick = async () => {
      run.disabled = true;
      const limit = Number($("#leak-limit", el).value);
      const body = {
        limit,
        by: $("#leak-by", el).value,
        preset: limit === 0 ? ($("#leak-preset", el).value || "quick") : $("#leak-preset", el).value,
      };
      const json = await fetch("/api/solver/analyze?" + qs(), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }).then((r) => r.json());
      if (!json.ok) {
        el.insertAdjacentHTML("beforeend", `<p class="note" style="color:var(--red)">${json.error || "Could not start"}</p>`);
        run.disabled = false;
        return;
      }
      pollLeaks(el, cat);
    };
  }
}

async function refreshLeaks(el, cat) {
  const [leaks, job] = await Promise.all([
    api("/api/solver/leaks"),
    fetch("/api/solver/job").then((r) => r.json()),
  ]);
  const nextCat = cat || await api("/api/solver/catalog");
  paintLeakPanel(el, nextCat, leaks, job);
  return { job, cat: nextCat };
}

function pollLeaks(el, cat) {
  if (leakTimer) clearInterval(leakTimer);
  let held = cat;
  const tick = async () => {
    const out = await refreshLeaks(el, held);
    held = out.cat;
    if (!out.job || out.job.state !== "running") {
      clearInterval(leakTimer);
      leakTimer = null;
    }
  };
  leakTimer = setInterval(tick, 3000);
  tick();
}

function strategyBlock(title, node) {
  if (!node) return "";
  const avgFreqs = node.actions.map((a) => node.average[a] || 0);
  const hero = node.hero
    ? `<div class="hero-mix"><strong>Your hand ${node.hero.combo}</strong>${mixBars(node.actions, node.hero.freqs)}</div>`
    : "";
  return `<div class="card" style="margin-bottom:12px">
    <h2>${title} · ${String(node.actor || "").toUpperCase()}</h2>
    <p class="note">${node.combo_count || 0} combos in range</p>
    ${hero}
    <div style="margin-top:8px"><strong>Range mix</strong>${mixBars(node.actions, avgFreqs)}</div>
  </div>`;
}

async function renderSolver(app) {
  const st = await fetch("/api/solver/status").then((r) => r.json());
  let pre = null;
  let err = "";
  if (state.handId) {
    pre = await fetch("/api/solver/from-hand/" + encodeURIComponent(state.handId)).then((r) => r.json());
    if (pre && pre.ok === false) err = pre.error || "Could not build a solver spot from this hand.";
  }
  const board = pre && pre.ok ? pre.board_text : "Qs,Jh,2h";
  const pot = pre && pre.ok ? pre.pot : 50;
  const stack = pre && pre.ok ? pre.effective_stack : 200;
  const ip = pre && pre.ok ? pre.range_ip : "";
  const oop = pre && pre.ok ? pre.range_oop : "";
  const hero = pre && pre.ok ? pre.hero_cards : "";
  const role = pre && pre.ok ? pre.hero_role : "";
  app.innerHTML = `
    <div class="headline">
      <div>
        <h1>GTO solver</h1>
        <div class="sub">TexasSolver · heads-up postflop Hold'em</div>
      </div>
      <div class="sub">${st.installed ? "console_solver.exe ready" : "binary not found"}</div>
    </div>
    ${st.installed ? "" : `<p class="note">Expected at tools/texassolver/bin. Run <code>python tools/setup_texassolver.py</code> if you need to re-download.</p>`}
    ${err ? `<p class="note" style="color:var(--red)">${err}</p>` : ""}
    ${pre && pre.ok ? `<p class="note">${pre.street.toUpperCase()} HU · OOP ${pre.oop.position} (${pre.oop.name}) · IP ${pre.ip.position} (${pre.ip.name})${pre.note ? " · " + pre.note : ""}</p>` : ""}
    <div class="card" style="margin-bottom:16px" id="leak-panel"><p class="note">Scanning HU spots in the database…</p></div>
    <div class="card replayer" id="gto-replay" style="display:none;margin-bottom:16px"></div>
    <div class="card" style="margin-bottom:16px">
      <form id="solve-form" class="solver-form">
        <label>Board <input name="board" value="${board}" placeholder="Qs,Jh,2h" /></label>
        <label>Pot (cents) <input name="pot" type="number" value="${pot}" /></label>
        <label>Effective stack (cents) <input name="effective_stack" type="number" value="${stack}" /></label>
        <label>Hero cards <input name="hero_cards" value="${hero}" placeholder="Ah Kd" /></label>
        <label>Hero role
          <select name="hero_role">
            <option value="" ${!role ? "selected" : ""}>Unknown</option>
            <option value="oop" ${role === "oop" ? "selected" : ""}>OOP</option>
            <option value="ip" ${role === "ip" ? "selected" : ""}>IP</option>
          </select>
        </label>
        <label>Quality
          <select name="preset">
            <option value="fast" selected>Fast (~1 min)</option>
            <option value="normal">Normal</option>
            <option value="quality">Quality (slow)</option>
          </select>
        </label>
        <label class="grow">IP range <textarea name="range_ip" rows="3">${ip}</textarea></label>
        <label class="grow">OOP range <textarea name="range_oop" rows="3">${oop}</textarea></label>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="primary" type="submit" ${st.installed ? "" : "disabled"}>Solve</button>
          <button type="button" id="open-gui" ${st.gui ? "" : "disabled"}>Open TexasSolver GUI</button>
        </div>
      </form>
    </div>
    <div id="solve-out"><p class="note">Leave ranges blank to use TexasSolver's default 6-max cash ranges. Fast preset is a coarse solve so the UI stays usable.</p></div>
  `;
  $("#open-gui").onclick = async () => {
    const json = await fetch("/api/solver/gui", { method: "POST" }).then((r) => r.json());
    $("#solve-out").innerHTML = json.ok ? `<p class="note">GUI launched.</p>` : `<p class="note">${json.error}</p>`;
  };
  $("#solve-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = Object.fromEntries(fd.entries());
    body.pot = Number(body.pot);
    body.effective_stack = Number(body.effective_stack);
    $("#solve-out").innerHTML = `<p class="note">Solving… this can take a minute. Keep this tab open.</p>`;
    try {
      const json = await fetch("/api/solver/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }).then((r) => r.json());
      if (!json.ok) {
        $("#solve-out").innerHTML = `<p class="note" style="color:var(--red)">${json.error || "Solve failed"}</p><pre class="action-log">${json.log || ""}</pre>`;
        return;
      }
      const s = json.strategy;
      $("#solve-out").innerHTML = `
        <p class="note">Finished in ${json.seconds}s · ${json.spot.board} · pot ${json.spot.pot} · stack ${json.spot.effective_stack}</p>
        ${strategyBlock("First to act", s.root)}
        ${strategyBlock("After check (IP)", s.after_check)}
        <details><summary>Solver log</summary><pre class="action-log">${json.log || ""}</pre></details>
      `;
    } catch (ex) {
      $("#solve-out").innerHTML = `<p class="note" style="color:var(--red)">${ex.message}</p>`;
    }
  });
  (async () => {
    const panel = $("#leak-panel");
    try {
      const [cat, leaks, job] = await Promise.all([
        api("/api/solver/catalog"),
        api("/api/solver/leaks"),
        fetch("/api/solver/job").then((r) => r.json()),
      ]);
      paintLeakPanel(panel, cat, leaks, job);
      if (job && job.state === "running") pollLeaks(panel, cat);
    } catch (ex) {
      panel.innerHTML = `<p class="note" style="color:var(--red)">${ex.message}</p>`;
    }
  })();
}

async function renderImport(app) {
  const health = await fetch("/api/health").then((r) => r.json());
  app.innerHTML = `
    <div class="headline"><h1>Import</h1><div class="sub">${health.hands.toLocaleString()} hands in database</div></div>
    <div class="drop" id="drop">
      <p>Drop GGPoker .zip or .txt hand histories here, or choose files.</p>
      <p><input type="file" id="files" multiple accept=".zip,.txt" /></p>
      <p><button class="primary" id="do-import">Import selected</button>
         <button id="rebuild">Rebuild from bundled zips</button></p>
      <p class="note" id="import-status"></p>
    </div>
    <p class="note">GGPoker emails a zip of Rush & Cash / cash text files. Hands are de-duplicated by hand ID, so overlapping downloads are safe to drop in again. The parser understands NLHE, PLO, run-it-twice, EV cashout, and cash drops.</p>
  `;
  const drop = $("#drop");
  const status = $("#import-status");
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => {
    $("#files").files = e.dataTransfer.files;
  });
  $("#do-import").onclick = async () => {
    const files = $("#files").files;
    if (!files.length) { status.textContent = "Choose files first."; return; }
    status.textContent = "Importing…";
    const body = new FormData();
    [...files].forEach((f) => body.append("files", f));
    const res = await fetch("/api/import", { method: "POST", body });
    const json = await res.json();
    status.textContent = importSummary(json);
    $("#nav-foot").textContent = json.total + " hands";
  };
  $("#rebuild").onclick = async () => {
    status.textContent = "Clearing database and re-importing data/imports…";
    const json = await fetch("/api/rebuild", { method: "POST" }).then((r) => r.json());
    status.textContent = importSummary(json);
  };
}

function bindHandClicks() {
  document.addEventListener("click", async (e) => {
    const row = e.target.closest("[data-hand]");
    if (!row) return;
    const id = row.dataset.hand;
    if (state.route !== "hands") {
      location.hash = "#/hands/" + id;
      return;
    }
    const box = $("#replayer");
    if (box) await mountReplayer(box, id);
  });
}

window.addEventListener("hashchange", render);
bindFilters();
bindHandClicks();
readFilters();
if (!location.hash) location.hash = "#/overview";
else render();
