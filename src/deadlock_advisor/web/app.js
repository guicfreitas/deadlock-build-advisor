const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
let lastVersion = -1;

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

function render(s) {
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
  $("#lane-meta").textContent = `primeiros ${rec.settings.lane_window_min} min · ${rec.lane_cost} almas`;
  $("#lane-items").innerHTML = rec.lane_build.map(itemHtml).join("");
  $("#mid-items").innerHTML = rec.full_build.mid.map(itemHtml).join("");
  $("#late-items").innerHTML = rec.full_build.late.map(itemHtml).join("");
  $("#enemy-list").innerHTML = rec.enemies.map((e) => `<div class="enemy">${heroHtml(e)}
      <div class="counters">${e.counters.map(itemHtml).join("") || '<span class="hint">sem item com vantagem clara</span>'}</div></div>`).join("");
}

async function poll() {
  try {
    const s = await (await fetch("/api/state")).json();
    if (s.version !== lastVersion) { lastVersion = s.version; render(s); }
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

poll();
setupManual();
