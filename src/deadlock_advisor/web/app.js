const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
let lastVersion = -1;
let lastState = null;

// ---------- translations: strings come from the app (/api/i18n), never hard-coded here ----------
let STR = {}, LANG = "en";
const T = (key, params = {}) => String(STR[key] ?? key).replace(/\{(\w+)\}/g, (_, n) => params[n] ?? "");
function applyI18n() {
  document.documentElement.lang = LANG;
  for (const el of document.querySelectorAll("[data-i18n]")) el.textContent = T(el.dataset.i18n);
  for (const el of document.querySelectorAll("[data-i18n-html]")) el.innerHTML = T(el.dataset.i18nHtml); // our own strings
  for (const el of document.querySelectorAll("[data-i18n-ph]")) el.placeholder = T(el.dataset.i18nPh);
  for (const el of document.querySelectorAll("[data-rank]")) el.textContent = T("set.rank.above", { rank: el.dataset.rank });
  document.body.classList.remove("i18n-pending");
}
async function loadI18n() {
  try {
    const r = await (await fetch("/api/i18n")).json();
    STR = r.strings || {}; LANG = r.lang || "en";
    const sel = $("#language");
    sel.innerHTML = `<option value="">${esc(T("set.language.auto"))}</option>` +
      (r.languages || []).map((l) => `<option value="${esc(l.code)}">${esc(l.name)}</option>`).join("");
  } catch { /* the page still works with raw keys; poll() reports the disconnect */ }
  applyI18n();
}

function heroHtml(h, big = false) {
  const mu = h.matchup;
  // the matchup is *your* hero's win rate against this one, not theirs
  const wr = mu ? `<div class="wr ${mu.wr >= 50 ? "good" : "bad"}" title="${esc(T("hero.wr_title", { name: h.name }))}">${esc(T("hero.wr", { wr: mu.wr }))}<span class="stats">${esc(T("hero.matches", { n: mu.matches }))}</span></div>` : "";
  return `<div class="${big ? "hero-big" : "hero"}"><img src="${esc(h.image)}" alt=""><div><div>${esc(h.name)}</div>${wr}</div></div>`;
}

function itemHtml(it) {
  const cls = it.lift > 0 ? "pos" : it.lift < 0 ? "neg" : "";
  const sign = it.lift > 0 ? "+" : "";
  const stats = it.wr != null ? `<span class="stats"> · ${it.wr}% <span class="lift ${cls}">(${sign}${it.lift})</span></span>` : "";
  const cost = it.upgrade_cost != null ? `+${it.upgrade_cost}` : `${it.cost}`;
  const title = it.wr != null
    ? T("item.stats_title", { min: it.avg_buy_min, n: it.matches, pop: it.pop })
    : T("item.component_title");
  const step = it.upgrades_to ? `<div class="step">${esc(T("item.becomes", { name: it.upgrades_to }))}</div>` : "";
  const why = it.why ? `<div class="why">${esc(it.why)}</div>` : "";
  const sell = it.sell_after_lane ? `<div class="sell" title="${esc(T("item.sell_title"))}">${esc(T("item.sell"))}</div>` : "";
  return `<div class="item ${esc(it.slot)}${it.upgrades_to ? " component" : ""}" title="${esc(title)}">
    <img src="${esc(it.image)}" alt="">
    <div><div class="name">${esc(it.name)}${it.active ? " ⚡" : ""}</div>
    <div class="meta">${cost}${stats}</div>${step}${why}${sell}</div></div>`;
}

function miniItem(it, cls = "") {
  if (!it) return "";
  return `<span class="mini ${esc(it.slot)} ${cls}"><img src="${esc(it.image)}" alt="">${esc(it.name)}</span>`;
}

function ago(ts) {
  const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
  return s < 60 ? T("ago.s", { n: s }) : T("ago.m", { n: Math.round(s / 60) });
}

function renderSwaps(s) {
  const live = s.live_items, list = live?.suggestions || [];
  $("#swaps").classList.toggle("hidden", !list.length);
  if (!list.length) return;
  const base = T(live.against_copied ? "swaps.base_copied" : "swaps.base_rec");
  $("#swaps-meta").textContent = T("swaps.meta", { base, ago: ago(live.updated_at) });
  $("#swap-list").innerHTML = list.map((x) => {
    const lift = x.lift ? `<span class="lift ${x.lift > 0 ? "pos" : "neg"}">${x.lift > 0 ? "+" : ""}${x.lift}% WR</span>` : "";
    const what = x.instead_of
      ? T("swaps.buy_instead", { buy: miniItem(x.buy, "buy"), drop: miniItem(x.instead_of, "drop") })
      : T("swaps.buy_also", { buy: miniItem(x.buy, "buy") });
    return `<div class="swap"><div class="what">${what} ${lift}</div>
      <div class="why">${T("swaps.against", { threat: esc(x.threat_label), reason: esc(x.reason) })}</div></div>`;
  }).join("");
}

function renderAbilities(order) {
  $("#abilities").classList.toggle("hidden", !order);
  if (!order) return;
  $("#abilities-meta").textContent = order.matches
    ? T("ab.meta_n", { n: order.matches.toLocaleString(LANG) })
    : T("ab.meta");
  const tierLabel = (t) => (t === 0 ? "•" : t);
  const head = `<div class="ab-head"></div>` + order.steps.map((_, i) => `<div class="ab-n">${i + 1}</div>`).join("");
  const rows = order.abilities.map((a) => `<div class="ab-name" title="${esc(a.name)}">
      ${a.image ? `<img src="${esc(a.image)}" alt="">` : ""}<span><b>${a.slot}</b> ${esc(a.name)}</span></div>` +
    order.steps.map((s) => s.id === a.id
      ? `<div class="ab-cell on t${s.tier}" title="${esc(s.tier ? T("ab.upgrade", { tier: s.tier, points: T(s.cost > 1 ? "ab.points" : "ab.point1", { n: s.cost }) }) : T("ab.unlock"))}${s.avg_min ? esc(T("ab.min", { n: s.avg_min })) : ""}">${tierLabel(s.tier)}</div>`
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
    ? T("onb.s1.found", { dir: c.game_dir, account: c.account_id })
    : !c.steam_found ? T("onb.s1.no_steam")
    : !c.game_dir ? T("onb.s1.no_game")
    : T("onb.s1.no_account");
  const steps = [["find", o.found], ["condebug", o.condebug], ["launch", o.launched]];
  const current = steps.find(([, ok]) => !ok)?.[0];
  for (const [name, ok] of steps) {
    const li = document.querySelector(`[data-step="${name}"]`);
    li.className = ok ? "done" : name === current ? "current" : "todo";
    li.querySelector(".state").textContent = ok ? T("onb.done") : name === current ? T("onb.now") : "";
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
  $("#status-msg").textContent = status !== s.status ? T("status.waiting") : (s.message || s.status);
  const rec = s.recommendation;
  for (const id of ["#now", "#lane", "#full", "#enemies"]) $(id).classList.toggle("hidden", !rec);
  renderAbilities(rec?.ability_order);
  const waiting = !!(s.roster && s.roster.lanes_final === false);
  $("#copy-build").disabled = waiting;
  $("#copy-build").textContent = T(waiting ? "now.waiting_lanes" : "now.copy");
  $("#copy-msg").textContent = waiting ? T("now.lanes_open")
    : s.copied ? T("now.copied", { name: s.copied.name })
    : "";
  if (!rec) return;
  $("#me").innerHTML = heroHtml(rec.hero, true);
  $("#lane-enemies").innerHTML = rec.lane_enemies.length
    ? rec.lane_enemies.map((h) => heroHtml(h)).join("")
    : `<span class="hint">${esc(T("now.lane_unknown"))}</span>`;
  const provisional = s.roster && !s.roster.lanes_locked ? T("lane.provisional") : "";
  $("#lane-meta").textContent = T("lane.meta", { min: rec.settings.lane_window_min, cost: rec.lane_cost }) + provisional;
  $("#lane-items").innerHTML = rec.lane_build.map(itemHtml).join("");
  $("#mid-items").innerHTML = rec.full_build.mid.map(itemHtml).join("");
  $("#late-items").innerHTML = rec.full_build.late.map(itemHtml).join("");
  $("#enemy-list").innerHTML = rec.enemies.map((e) => `<div class="enemy">${heroHtml(e)}
      <div class="counters">${e.counters.map(itemHtml).join("") || '<span class="hint">${esc(T("enemies.none"))}</span>'}</div></div>`).join("");
}

async function poll() {
  try {
    const s = await (await fetch("/api/state")).json();
    if (s.version !== lastVersion) { lastVersion = s.version; lastState = s; render(s); }
  } catch { $("#status-msg").textContent = T("status.disconnected"); }
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
  $("#copy-msg").textContent = T("now.copied_short");
});

// ---------- first-run buttons ----------
$("#copy-condebug").addEventListener("click", async () => {
  await navigator.clipboard?.writeText("-condebug").catch(() => {});
  $("#copy-condebug").textContent = T("onb.s2.copied");
  setTimeout(() => { $("#copy-condebug").textContent = T("onb.s2.copy"); }, 2000);
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
  $("#update-msg").textContent = r.error || T("update.installing");
  $("#update-go").classList.add("hidden");
});

// refresh "lida há Xs" between polls
setInterval(() => { const m = $("#swaps-meta"); if (m && lastState) renderSwaps(lastState); }, 15000);


// ---------- settings ----------
const form = $("#settings-form");
const FALLBACK = { "engine.lane_window_s": 600, "engine.lane_budget": 5600 };
function fillSettings(v) {
  for (const el of form.elements) {
    if (!el.name) continue;
    const user = v.user[el.name], eff = v.effective[el.name];
    if (el.type === "checkbox") el.checked = !!(user ?? eff);
    else if (el.name === "game_dir" || el.name === "account_id") {
      el.value = user ?? "";
      if (eff) el.placeholder = T("set.game_dir.detected", { v: eff });
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
    // name the field by its (translated) label, never by its internal key
    const label = (k) => (form.elements[k]?.closest("label")?.querySelector("span")?.textContent || "").trim();
    $("#settings-msg").textContent = Object.entries(r.errors).map(([k, m]) => `${label(k)}: ${m}`.replace(/^: /, "")).join(" · ");
    return;
  }
  if (r.settings) fillSettings(r.settings);
  const restart = (r.restart || []).length > 0;
  $("#settings-restart").classList.toggle("hidden", !restart);
  $("#settings-msg").textContent = T(restart ? "set.saved_restart" : "set.saved");
});
$("#settings-restart").addEventListener("click", async () => {
  const r = await (await fetch("/api/restart", { method: "POST" })).json().catch(() => ({}));
  $("#settings-msg").textContent = r.error || T("set.restarting");
  if (!r.error) setTimeout(() => location.reload(), 4000);
});

// ---------- feedback & support ----------
function diagnostics(about) {
  const c = lastState?.setup || {};
  const yn = (v) => (v ? "yes" : "no");
  return [`App version: ${about.version}`, `System: ${about.platform}`, `Language: ${about.language}`,
    `Status: ${lastState?.status ?? "unknown"}`,
    `Game found: ${yn(c.game_dir)} · Account found: ${yn(c.account_id)} · Game log on: ${yn(c.condebug ?? c.console_log)}`].join("\n");
}
async function setupFeedback() {
  let about;
  try { about = await (await fetch("/api/about")).json(); } catch { return; }
  const body = () => encodeURIComponent(
    `**What happened?**\n\n\n**What did you expect?**\n\n\n---\n${diagnostics(about)}`);
  $("#fb-bug").href = `${about.issues_url}?title=${encodeURIComponent("[Bug] ")}&body=${body()}`;
  $("#fb-idea").href = `${about.issues_url}?title=${encodeURIComponent("[Idea] ")}`;
  if (about.email) { $("#fb-email").href = `mailto:${about.email}?subject=${encodeURIComponent("Deadlock Build Advisor " + about.version)}`; $("#fb-email").classList.remove("hidden"); }
  if (about.discord) {
    const d = $("#fb-discord"), isLink = /^https?:\/\//.test(about.discord);
    d.classList.remove("hidden");
    if (isLink) d.href = about.discord;
    else {
      // a Discord username can't be opened as a link: show it and copy it on click
      d.textContent = `${T("fb.discord")}: ${about.discord}`;
      d.removeAttribute("target");
      d.href = "#";
      d.addEventListener("click", async (ev) => {
        ev.preventDefault();
        await navigator.clipboard?.writeText(about.discord).catch(() => {});
        $("#fb-diag-msg").textContent = T("fb.discord_copied");
        setTimeout(() => { $("#fb-diag-msg").textContent = ""; }, 4000);
      });
    }
  }
  $("#fb-diag").addEventListener("click", async () => {
    await navigator.clipboard?.writeText(diagnostics(about)).catch(() => {});
    $("#fb-diag-msg").textContent = T("fb.diag_copied");
    setTimeout(() => { $("#fb-diag-msg").textContent = ""; }, 4000);
  });
  // support is never pushed on the player: one quiet card at the bottom, hidden until links exist
  $("#support").classList.toggle("hidden", !(about.support || []).length);
  $("#support-links").innerHTML = (about.support || []).map((l) =>
    `<a class="btn ghost" target="_blank" rel="noopener" href="${esc(l.url)}">${esc(l.label)}</a>`).join("");
}

(async () => {
  await loadI18n();
  $("#status-msg").textContent = T("status.connecting");
  poll();
  setupManual();
  loadSettings();
  setupFeedback();
})();
