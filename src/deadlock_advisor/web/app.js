const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
let lastVersion = -1;
let lastState = null;

function heroHtml(h, big = false) {
  const mu = h.matchup;
  // the matchup is *your* hero's win rate against this one, not theirs
  const wr = mu ? `<div class="wr ${mu.wr >= 50 ? "good" : "bad"}" title="Sua taxa de vitória contra ${esc(h.name)}">sua WR ${mu.wr}%<span class="stats"> · ${mu.matches} partidas</span></div>` : "";
  return `<div class="${big ? "hero-big" : "hero"}"><img src="${esc(h.image)}" alt=""><div><div>${esc(h.name)}</div>${wr}</div></div>`;
}

function itemHtml(it) {
  const cls = it.lift > 0 ? "pos" : it.lift < 0 ? "neg" : "";
  const sign = it.lift > 0 ? "+" : "";
  const stats = it.wr != null ? `<span class="stats"> · ${it.wr}% <span class="lift ${cls}">(${sign}${it.lift})</span></span>` : "";
  const cost = it.upgrade_cost != null ? `+${it.upgrade_cost}` : `${it.cost}`;
  const title = it.wr != null
    ? `Comprado em média aos ${it.avg_buy_min} min · ${it.matches} partidas · popularidade ${it.pop}%`
    : "Componente: compre antes para depois evoluir";
  const step = it.upgrades_to ? `<div class="step">→ vira ${esc(it.upgrades_to)}</div>` : "";
  return `<div class="item ${esc(it.slot)}${it.upgrades_to ? " component" : ""}" title="${esc(title)}">
    <img src="${esc(it.image)}" alt="">
    <div><div class="name">${esc(it.name)}${it.active ? " ⚡" : ""}</div>
    <div class="meta">${cost}${stats}</div>${step}</div></div>`;
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

function renderAbilities(order) {
  $("#abilities").classList.toggle("hidden", !order);
  if (!order) return;
  $("#abilities-meta").textContent = order.matches
    ? `a ordem dos jogadores do herói · ${order.matches.toLocaleString("pt-BR")} partidas seguiram esse caminho`
    : "a ordem dos jogadores do herói";
  const tierLabel = (t) => (t === 0 ? "•" : t);
  const head = `<div class="ab-head"></div>` + order.steps.map((_, i) => `<div class="ab-n">${i + 1}</div>`).join("");
  const rows = order.abilities.map((a) => `<div class="ab-name" title="${esc(a.name)}">
      ${a.image ? `<img src="${esc(a.image)}" alt="">` : ""}<span><b>${a.slot}</b> ${esc(a.name)}</span></div>` +
    order.steps.map((s) => s.id === a.id
      ? `<div class="ab-cell on t${s.tier}" title="${s.tier ? `melhoria ${s.tier} (${s.cost} ponto${s.cost > 1 ? "s" : ""})` : "desbloquear"}${s.avg_min ? ` · ~${s.avg_min} min` : ""}">${tierLabel(s.tier)}</div>`
      : `<div class="ab-cell"></div>`).join("")).join("");
  const grid = $("#ability-grid");
  grid.style.gridTemplateColumns = `minmax(110px, 170px) repeat(${order.steps.length}, minmax(18px, 1fr))`;
  grid.innerHTML = head + rows;
}

function renderUpdate(u) {
  if (u?.current) $("#app-version").textContent = `v${u.current}`;
  const show = u && (u.available || u.state === "downloading" || u.state === "installing" || u.state === "error");
  $("#update").classList.toggle("hidden", !show);
  if (!show) return;
  $("#update-msg").textContent = u.message || "";
  $("#update-go").classList.toggle("hidden", !(u.can_install && u.state === "ready"));
}

// ---------- storage: per-viewer conveniences only; the page works without it ----------
const LS = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
};

// ---------- first run ----------
// Steam can take a while to save launch options to disk, so after "Já adicionei" the
// launch step is proven by the game itself: console.log written after that click.
function onboarding(c) {
  const confirmedAt = +(LS.get("condebugConfirmedAt") || 0);
  const found = !!(c.game_dir && c.account_id);
  const condebug = found && (c.condebug === true || (c.condebug === null && c.console_log) || confirmedAt > 0);
  // in order: an old console.log must not tick "open the game" before -condebug is there
  const launched = condebug && !!c.console_log && (!confirmedAt || (c.console_log_mtime || 0) * 1000 > confirmedAt);
  const done = !!c.ok || (found && condebug && launched);
  if (done) LS.set("onboarded", "1");
  return { found, condebug, launched, done };
}

let setupTimer = null;
function renderOnboard(c) {
  const o = onboarding(c);
  const show = !o.done && LS.get("onboarded") !== "1";
  $("#onboard").classList.toggle("hidden", !show);
  // keep re-checking on its own while the player is busy in Steam
  if (show && !setupTimer) setupTimer = setInterval(() => fetch("/api/setup").catch(() => {}), 4000);
  if (!show && setupTimer) { clearInterval(setupTimer); setupTimer = null; }
  if (!show) return o;
  $("#find-msg").textContent = o.found
    ? `Deadlock em ${c.game_dir} · conta ${c.account_id}`
    : !c.steam_found ? "Não encontrei a Steam. Escolha a pasta do Deadlock manualmente."
    : !c.game_dir ? "Não encontrei o Deadlock nas bibliotecas da Steam. Escolha a pasta manualmente."
    : "Não encontrei sua conta. Abra a Steam logado, ou informe o SteamID3 nas configurações.";
  const steps = [["find", o.found], ["condebug", o.condebug], ["launch", o.launched]];
  const current = steps.find(([, ok]) => !ok)?.[0];
  for (const [name, ok] of steps) {
    const li = document.querySelector(`[data-step="${name}"]`);
    li.className = ok ? "done" : name === current ? "current" : "todo";
    li.querySelector(".state").textContent = ok ? "✔ feito" : name === current ? "agora" : "";
  }
  return o;
}

function renderGuide(s, ready) {
  const show = ready && !s.recommendation;
  $("#guide").classList.toggle("hidden", !show);
  if (!show) return;
  const at = s.status === "loading" ? "loading" : "queue";
  for (const li of document.querySelectorAll("[data-flow]")) li.classList.toggle("current", li.dataset.flow === at);
}

function render(s) {
  const o = renderOnboard(s.setup || {});
  const ready = o.done || LS.get("onboarded") === "1";
  renderGuide(s, ready);
  renderUpdate(s.update);
  renderSwaps(s);
  const st = $("#status");
  // the server can still say "setup" when Steam hasn't saved -condebug yet but the game proved it
  const status = s.status === "setup" && ready ? "idle" : s.status;
  st.className = `status ${status}`;
  $("#status-msg").textContent = status !== s.status ? "Aguardando partida…" : (s.message || s.status);
  const rec = s.recommendation;
  for (const id of ["#now", "#lane", "#full", "#enemies"]) $(id).classList.toggle("hidden", !rec);
  renderAbilities(rec?.ability_order);
  const waiting = !!(s.roster && s.roster.lanes_final === false);
  $("#copy-build").disabled = waiting;
  $("#copy-build").textContent = waiting ? "Aguardando lanes…" : "Copiar build para o jogo";
  $("#copy-msg").innerHTML = waiting ? "As lanes ainda podem ser trocadas. O botão libera quando elas travarem."
    : s.copied ? `Copiado “${esc(s.copied.name)}”. Agora cole no jogo. As trocas sugeridas comparam com essa build.`
    : "";
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
  $("#copy-msg").textContent = "Copiado! Agora cole no jogo: Loja → Explorar guias → Criar guia → Colar guia.";
});

// ---------- first-run buttons ----------
$("#copy-condebug").addEventListener("click", async () => {
  await navigator.clipboard?.writeText("-condebug").catch(() => {});
  $("#copy-condebug").textContent = "Copiado!";
  setTimeout(() => { $("#copy-condebug").textContent = "Copiar"; }, 2000);
});
$("#condebug-done").addEventListener("click", () => {
  LS.set("condebugConfirmedAt", String(Date.now()));
  if (lastState) render(lastState);
  fetch("/api/setup").catch(() => {});
});
for (const b of document.querySelectorAll("[data-open-settings]")) b.addEventListener("click", () => {
  $("#settings").open = true;
  $("#settings").scrollIntoView({ behavior: "smooth" });
});

// ---------- numbers on items: off by default, they made the page feel busy ----------
function applyStats(on) {
  document.body.classList.toggle("show-stats", on);
  $("#show-stats").checked = on;
}
applyStats(LS.get("showStats") === "1");
$("#show-stats").addEventListener("change", (e) => {
  LS.set("showStats", e.target.checked ? "1" : "0");
  applyStats(e.target.checked);
});

$("#update-go").addEventListener("click", async () => {
  const r = await (await fetch("/api/update", { method: "POST" })).json().catch(() => ({}));
  $("#update-msg").textContent = r.error || "Instalando a atualização… o app reabre sozinho.";
  $("#update-go").classList.add("hidden");
});

// refresh "lida há Xs" between polls
setInterval(() => { const m = $("#swaps-meta"); if (m && lastState) renderSwaps(lastState); }, 15000);


// ---------- settings ----------
const form = $("#settings-form");
const FALLBACK = { "engine.lane_window_s": 600, "engine.lane_budget": 5600 };
function fillSettings(v) {
  $("#settings-path").textContent = v.path;
  for (const el of form.elements) {
    if (!el.name) continue;
    const user = v.user[el.name], eff = v.effective[el.name];
    if (el.type === "checkbox") el.checked = !!(user ?? eff);
    else if (el.name === "game_dir" || el.name === "account_id") {
      el.value = user ?? "";
      if (eff) el.placeholder = `detectada: ${eff}`;
    } else el.value = user ?? eff ?? FALLBACK[el.name] ?? "";
  }
}
async function loadSettings() {
  try { fillSettings(await (await fetch("/api/settings")).json()); } catch {}
}
form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const body = {};
  for (const el of form.elements) {
    if (el.name) body[el.name] = el.type === "checkbox" ? el.checked : el.value;
  }
  for (const el of form.querySelectorAll(".error")) el.classList.remove("error");
  const r = await (await fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).json();
  if (r.errors && Object.keys(r.errors).length) {
    for (const k of Object.keys(r.errors)) form.elements[k]?.classList.add("error");
    $("#settings-msg").textContent = Object.entries(r.errors).map(([k, m]) => `${k}: ${m}`).join(" · ");
    return;
  }
  if (r.settings) fillSettings(r.settings);
  const restart = (r.restart || []).length > 0;
  $("#settings-restart").classList.toggle("hidden", !restart);
  $("#settings-msg").textContent = restart ? "Salvo. Algumas mudanças só valem depois de reiniciar." : "Salvo.";
});
$("#settings-restart").addEventListener("click", async () => {
  const r = await (await fetch("/api/restart", { method: "POST" })).json().catch(() => ({}));
  $("#settings-msg").textContent = r.error || "Reiniciando…";
  if (!r.error) setTimeout(() => location.reload(), 4000);
});

poll();
setupManual();
loadSettings();
