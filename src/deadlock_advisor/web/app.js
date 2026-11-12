const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
let lastVersion = -1;
let lastState = null;

function heroHtml(h, big = false) {
  const mu = h.matchup;
  const wr = mu ? `<div class="wr ${mu.wr >= 50 ? "good" : "bad"}">${mu.wr}% WR · ${mu.matches} partidas</div>` : "";
  return `<div class="${big ? "hero-big" : "hero"}"><img src="${esc(h.image)}" alt=""><div><div>${esc(h.name)}</div>${wr}</div></div>`;
}

function itemHtml(it) {
  const cls = it.lift > 0 ? "pos" : it.lift < 0 ? "neg" : "";
  const sign = it.lift > 0 ? "+" : "";
  return `<div class="item ${esc(it.slot)}" title="Comprado em média aos ${it.avg_buy_min} min · ${it.matches} partidas · popularidade ${it.pop}%">
    <img src="${esc(it.image)}" alt="">
    <div><div class="name">${esc(it.name)}${it.active ? " ⚡" : ""}</div>
    <div class="meta">${it.cost} · ${it.wr}% <span class="lift ${cls}">(${sign}${it.lift})</span></div></div></div>`;
}

function miniItem(it, cls = "") {
  if (!it) return "";
  return `<span class="mini ${esc(it.slot)} ${cls}"><img src="${esc(it.image)}" alt="">${esc(it.name)}</span>`;
}

function ago(ts) {
  const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
  return s < 60 ? `há ${s}s` : `há ${Math.round(s / 60)} min`;
}

function renderSwaps(s) {
  const live = s.live_items, list = live?.suggestions || [];
  $("#swaps").classList.toggle("hidden", !list.length);
  if (!list.length) return;
  const base = live.against_copied ? "na build que você colou" : "na build recomendada";
  $("#swaps-meta").textContent = `${base} · itens dos inimigos lidos ${ago(live.updated_at)}`;
  $("#swap-list").innerHTML = list.map((x) => {
    const lift = x.lift ? `<span class="lift ${x.lift > 0 ? "pos" : "neg"}">${x.lift > 0 ? "+" : ""}${x.lift}% WR</span>` : "";
    const what = x.instead_of
      ? `Compre ${miniItem(x.buy, "buy")} em vez de ${miniItem(x.instead_of, "drop")}`
      : `Compre também ${miniItem(x.buy, "buy")}`;
    return `<div class="swap"><div class="what">${what} ${lift}</div>
      <div class="why">Contra <b>${esc(x.threat_label)}</b>: ${esc(x.reason)}</div></div>`;
  }).join("");
}

function render(s) {
  renderSwaps(s);
  $("#copybar").classList.toggle("hidden", !s.recommendation);
  if (s.copied) $("#copy-msg").innerHTML = `Copiado “${esc(s.copied.name)}”. As trocas acima comparam com essa build.`;
  const st = $("#status");
  st.className = `status ${s.status}`;
  $("#status-msg").textContent = s.message || s.status;
  const rec = s.recommendation;
  for (const id of ["#matchup", "#lane", "#full", "#enemies"]) $(id).classList.toggle("hidden", !rec);
  if (!rec) return;
  $("#me").innerHTML = heroHtml(rec.hero, true);
  $("#lane-enemies").innerHTML = rec.lane_enemies.length
    ? rec.lane_enemies.map((h) => heroHtml(h)).join("")
    : `<span class="hint">lane desconhecida — build de lane usa estatística geral</span>`;
  const provisional = s.roster && !s.roster.lanes_locked ? " · lane provisória (trocas ainda abertas)" : "";
  $("#lane-meta").textContent = `primeiros ${rec.settings.lane_window_min} min · ${rec.lane_cost} almas${provisional}`;
  $("#lane-items").innerHTML = rec.lane_build.map(itemHtml).join("");
  $("#mid-items").innerHTML = rec.full_build.mid.map(itemHtml).join("");
  $("#late-items").innerHTML = rec.full_build.late.map(itemHtml).join("");
  $("#enemy-list").innerHTML = rec.enemies.map((e) => `<div class="enemy">${heroHtml(e)}
      <div class="counters">${e.counters.map(itemHtml).join("") || '<span class="hint">sem item com vantagem clara</span>'}</div></div>`).join("");
}

async function poll() {
  try {
    const s = await (await fetch("/api/state")).json();
    if (s.version !== lastVersion) { lastVersion = s.version; lastState = s; render(s); }
  } catch { $("#status-msg").textContent = "App desconectado"; }
  setTimeout(poll, 1500);
}

// ---------- manual mode ----------
const picks = new Map(); // hero id -> "enemy" | "lane"
async function setupManual() {
  let heroes;
  try { heroes = await (await fetch("/api/heroes")).json(); } catch { return; }
  if (!Array.isArray(heroes)) return;
  $("#m-hero").innerHTML = heroes.map((h) => `<option value="${h.id}">${esc(h.name)}</option>`).join("");
  $("#m-grid").innerHTML = heroes.map((h) => `<div class="pick" data-id="${h.id}"><img src="${esc(h.image)}" alt="">${esc(h.name)}</div>`).join("");
  $("#m-grid").addEventListener("click", (ev) => {
    const el = ev.target.closest(".pick"); if (!el) return;
    const id = +el.dataset.id, cur = picks.get(id);
    const next = cur === undefined ? "enemy" : cur === "enemy" ? "lane" : undefined;
    if (next) picks.set(id, next); else picks.delete(id);
    el.classList.toggle("enemy-sel", next === "enemy");
    el.classList.toggle("lane-sel", next === "lane");
  });
  $("#m-go").addEventListener("click", async () => {
    const enemies = [...picks.keys()];
    const lane = enemies.filter((id) => picks.get(id) === "lane");
    await fetch("/api/manual", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hero_id: +$("#m-hero").value, enemies, lane_enemies: lane }) });
  });
  $("#m-match-go").addEventListener("click", async () => {
    const mid = $("#m-match").value.trim(); if (!mid) return;
    await fetch("/api/match", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ match_id: +mid }) });
  });
}

$("#copy-build").addEventListener("click", async () => {
  const r = await (await fetch("/api/copy-build", { method: "POST" })).json().catch(() => ({}));
  if (r.error) { $("#copy-msg").textContent = r.error; return; }
  // the app copies on the PC; if that failed (other OS), fall back to this browser
  if (!r.copied && navigator.clipboard) await navigator.clipboard.writeText(r.code).catch(() => {});
  $("#copy-msg").innerHTML = "Copiado! No Deadlock: loja → Explorar guias → crie um guia → <b>Colar guia</b>.";
});

// refresh "lida há Xs" between polls
setInterval(() => { const m = $("#swaps-meta"); if (m && lastState) renderSwaps(lastState); }, 15000);

poll();
setupManual();
