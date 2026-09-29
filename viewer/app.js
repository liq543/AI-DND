// Live Table — real-time view of the signed game log. Read-only except for DM-requested rolls.
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const COND_ICON = { blinded: "blindfold", charmed: "charm", deafened: "silenced", frightened: "screaming", grappled: "grab",
    incapacitated: "knocked-out-stars", invisible: "invisible", paralyzed: "frozen-body", petrified: "stone-bust", poisoned: "poison-bottle",
    prone: "falling", restrained: "manacles", stunned: "knockout", unconscious: "sleepy", raging: "enrage", dodging: "dodging" };
  let S = null, lastSeq = -1, lastRoll = null, viewMap = null, followActive = true, lastHandout = "", sheetId = null;
  const zoom = {}; // per map: {s, x, y}

  // ------------------------------------------------------------ live connection
  function connect() {
    const es = new EventSource("/events");
    es.addEventListener("update", () => refresh());
    es.onopen = () => $("#conn").classList.add("live");
    es.onerror = () => { $("#conn").classList.remove("live"); };
  }
  async function refresh() {
    let st;
    try { st = await (await fetch("/api/state", { cache: "no-store" })).json(); } catch { return; }
    if (st.error) { showAlert(st.error); return; }
    hideAlert();
    const prev = S; S = st;
    render(prev);
  }

  function showAlert(msg) { const a = $("#alert"); a.textContent = msg; a.hidden = false; $("#integrity").className = "bad"; $("#integrity").textContent = "⚠ integrity check failed"; }
  function hideAlert() { $("#alert").hidden = true; }

  // ------------------------------------------------------------ render all
  function render(prev) {
    $("#title").textContent = S.campaign || "Live Table";
    document.title = (S.campaign || "Live Table") + " — Live Table";
    $("#meta").innerHTML = `<span>Session <b>${S.session}</b></span><span>${esc(S.time)}</span>` +
      (S.combat ? `<span class="round">Round ${S.combat.round}</span>` : `<span>Exploring</span>`) +
      (S.overrides.length ? `<span title="${esc(S.overrides.map(o => o.what + ': ' + o.reason).join('\n'))}" style="color:var(--amber)">⚠ ${S.overrides.length} DM override${S.overrides.length > 1 ? "s" : ""}</span>` : "");
    $("#integrity").className = "";
    $("#integrity").textContent = `✔ signed log · ${S.events} events · ${S.roll_count} rolls · ${S.head}`;
    renderScene(); renderInitBar(); renderMapTabs(); renderMap(prev); renderParty(); renderTurns(); renderDice(prev); renderLog(); renderSheet(); renderRequests(); renderHandout();
  }

  function renderScene() {
    const sc = S.view.scene, el = $("#scene");
    if (!sc) { el.hidden = true; return; }
    el.hidden = false;
    el.innerHTML = `<h2>${esc(sc.title)}</h2>${sc.text ? `<p>${esc(sc.text)}</p>` : ""}`;
  }

  // ------------------------------------------------------------ initiative bar (always visible in combat)
  function renderInitBar() {
    const el = $("#initbar"), c = S.combat;
    if (!c) { el.hidden = true; return; }
    el.hidden = false;
    el.innerHTML = `<span class="lbl">Round ${c.round}</span>` + c.order.map((o, i) =>
      `<button class="ib ${o.side} ${o.current ? "current" : ""}" data-open="${esc(o.id)}" title="${esc(o.name)} · initiative ${o.init} · ${esc(o.status)}">
        <img src="/api/token/${esc(o.id)}.svg" alt=""><span class="n">${esc(o.name)}</span><span class="i">${o.init}</span></button>` +
      (i < c.order.length - 1 ? `<span class="arrow">›</span>` : "")).join("");
    el.querySelectorAll("[data-open]").forEach(b => b.onclick = () => openEntity(b.dataset.open));
    const cur = el.querySelector(".current"); if (cur) cur.scrollIntoView({ block: "nearest", inline: "center" });
  }

  // ------------------------------------------------------------ spells (click any spell name)
  const SMALL = ["of", "and", "the", "from", "or"];
  const spellName = (slug) => String(slug).split("-").map(w => SMALL.includes(w) ? w : w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
  const spellLink = (slug) => `<a class="spell" data-spell="${esc(slug)}">${esc(spellName(slug))}</a>`;
  function md(text) {
    const lines = String(text).split(/\r?\n/); let out = "", list = false, table = [];
    const inline = (t) => esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\*(.+?)\*/g, "<i>$1</i>").replace(/\b_(.+?)_\b/g, "<i>$1</i>");
    const flushTable = () => {
      if (!table.length) return;
      out += `<table class="t">` + table.filter(r => !/^\|?\s*:?-{2,}/.test(r)).map((r, i) =>
        `<tr>${r.replace(/^\||\|$/g, "").split("|").map(c => i ? `<td>${inline(c.trim())}</td>` : `<th>${inline(c.trim())}</th>`).join("")}</tr>`).join("") + `</table>`;
      table = [];
    };
    for (const l of lines) {
      if (/^\s*\|/.test(l)) { table.push(l.trim()); continue; } else flushTable();
      if (/^\s*[-*] /.test(l)) { if (!list) { out += "<ul>"; list = true; } out += `<li>${inline(l.replace(/^\s*[-*] /, ""))}</li>`; continue; }
      if (list) { out += "</ul>"; list = false; }
      const h = l.match(/^(#{1,4})\s+(.*)/);
      if (h) { const n = Math.min(4, h[1].length + 1); out += `<h${n}>${inline(h[2])}</h${n}>`; }
      else if (l.trim()) out += `<p>${inline(l)}</p>`;
    }
    flushTable(); if (list) out += "</ul>";
    return out;
  }
  async function openSpell(slug) {
    const j = await (await fetch(`/api/spell/${encodeURIComponent(slug)}`)).json();
    if (j.error) { toast("✖ " + j.error); return; }
    openModal(`<div class="info spellinfo">${md(j.md)}<p class="muted" style="margin-top:10px">SRD 5.2 text · <a href="https://www.dndbeyond.com/spells?filter-search=${encodeURIComponent(j.name)}" target="_blank" rel="noopener">look it up online</a></p></div>`);
  }
  document.addEventListener("click", (e) => { const a = e.target.closest("a.spell"); if (a) { e.preventDefault(); e.stopPropagation(); openSpell(a.dataset.spell); } });

  // ------------------------------------------------------------ creature info (what the party knows)
  async function openCreature(id) {
    const r = await fetch(`/api/creature/${encodeURIComponent(id)}`); const c = await r.json();
    if (c.error) { openModal(`<img src="/api/card/creature/${id}.svg">`); return; }
    const row = (k, v) => (v === undefined || v === null || v === "" || (Array.isArray(v) && !v.length)) ? "" : `<tr><th>${k}</th><td>${v}</td></tr>`;
    const conds = c.conditions.map(x => `${chipCond(x.name)}<span class="muted" style="font-size:11px"> ${esc(x.source || "")}${x.until ? " · until " + esc(x.until) : ""}</span>`).join("<br>");
    let h = `<div class="info"><div class="ihead"><img src="/api/token/${esc(c.id)}.svg" alt=""><div><h2>${esc(c.name)}</h2>
      <div class="muted">${esc(c.size || "")} ${esc(c.type || "")} · <span class="side ${esc(c.side)}">${esc(c.side)}</span></div>
      <div class="status ${esc(String(c.status).split(" ")[0])}" style="margin-top:4px">${esc(c.status)}</div></div></div><table class="t kv">`;
    if (c.full) h += row("HP", `${c.hp} / ${c.hp_max}`) + row("AC", c.ac) + row("Speed", Object.entries(c.speed || {}).map(([k, v]) => `${k} ${v} ft`).join(", "));
    else h += row("AC", c.ac_known ? `${c.ac_known} <span class="muted">(revealed by attack rolls)</span>` : `<span class="muted">unknown until someone attacks it</span>`);
    h += row("Conditions", conds) + row("Attacks seen", c.attacks_seen.map(esc).join(", ")) + row("Saves seen", c.saves_seen.map(esc).join("<br>"))
      + row("Record", (c.hits_taken + c.misses_against) ? `hit ${c.hits_taken}× · missed ${c.misses_against}× · ${c.damage_dealt_to} damage taken` : (c.damage_dealt_to ? `${c.damage_dealt_to} damage taken` : ""))
      + `</table>`;
    if (c.lore.length) h += `<h4>What you know</h4><ul>${c.lore.map(l => `<li>${esc(l)}</li>`).join("")}</ul>`;
    if (c.full && c.actions && c.actions.length) h += `<h4>Actions</h4>${c.actions.map(a => `<p><b>${esc(a.name)}.</b> ${md(a.text).replace(/<\/?p>/g, " ")}</p>`).join("")}`;
    if (!c.full) h += `<p class="muted" style="font-size:11px;margin-top:10px">Its stat block stays hidden: this panel shows only what your characters have seen. A knowledge check (Arcana, History, Nature, Religion) can earn more, which the DM adds here.</p>`;
    openModal(h + `</div>`);
  }

  // ------------------------------------------------------------ maps
  function renderMapTabs() {
    const maps = Object.values(S.maps);
    const active = S.view.map;
    if (followActive || !viewMap || !S.maps[viewMap]) viewMap = active;
    $("#maptabs").innerHTML = maps.map(m => `<button data-map="${esc(m.id)}" class="${m.id === viewMap ? "on" : ""}">${esc(m.name)}${m.id === active ? ' <span class="cur">●</span>' : ""}</button>`).join("");
    $("#maptabs").querySelectorAll("button").forEach(b => b.onclick = () => { viewMap = b.dataset.map; followActive = viewMap === S.view.map; renderMapTabs(); renderMap(null, true); });
  }
  let mapKey = "";
  async function renderMap(prev, force) {
    if (!viewMap) { $("#nomap").hidden = false; $("#map").innerHTML = ""; return; }
    $("#nomap").hidden = true;
    const key = viewMap + ":" + S.seq;
    if (key === mapKey && !force) return;
    mapKey = key;
    const r = await fetch(`/api/map/${encodeURIComponent(viewMap)}.svg?v=${S.seq}`, { cache: "no-store" });
    if (!r.ok) return;
    const firstTime = !zoom[viewMap];
    $("#map").innerHTML = await r.text();
    $("#map").querySelectorAll(".token").forEach(t => t.onclick = (ev) => {
      ev.stopPropagation();
      const ids = (t.dataset.stack || "").split(",").filter(Boolean);
      if (ids.length < 2) return openEntity(t.dataset.id);
      const who = (id) => S.party.find(p => p.id === id) || S.others.find(o => o.id === id) || { name: id };
      openModal(`<div class="info"><h2>Who's here?</h2><div class="muted">${ids.length} creatures share this square</div><div class="picker">` +
        ids.map(id => `<button data-pick="${esc(id)}"><img src="/api/token/${esc(id)}.svg" alt=""><span>${esc(who(id).name)}</span>
          <span class="muted">${esc(who(id).status || (who(id).hp !== undefined ? who(id).hp + "/" + who(id).hp_max : ""))}</span></button>`).join("") + `</div></div>`);
      document.querySelectorAll("#modal [data-pick]").forEach(b => b.onclick = () => { $("#modal").hidden = true; openEntity(b.dataset.pick); });
    });
    $("#map").querySelectorAll(".flooritem").forEach(t => t.onclick = (ev) => {
      ev.stopPropagation();
      const f = (S.maps[viewMap].floor || []).find(x => x.id === t.dataset.floor); if (!f) return;
      openModal(`<div class="info"><h2>${esc(f.name)}</h2><div class="muted">On the floor at (${f.x},${f.y}) · ${esc(f.note)}</div>
        <p>${f.qty > 1 ? f.qty + "× " : ""}${esc(f.name)}. Anyone standing in or next to that square can pick it up (a free object interaction on their turn). Just tell the DM.</p></div>`);
    });
    if (firstTime || !zoom[viewMap].user) { fit(); requestAnimationFrame(() => { if (!zoom[viewMap].user) fit(); }); } else applyZoom();
    if (S.combat && S.combat.current && followActive) centerOn(S.combat.current, prev && prev.combat && prev.combat.current !== S.combat.current);
  }
  function svgSize() { const s = $("#map svg"); return s ? [s.width.baseVal.value, s.height.baseVal.value] : [1, 1]; }
  function fit() {
    // frame the explored part of a fogged map, or the whole map otherwise
    const vp = $("#viewport").getBoundingClientRect(), [W, H] = svgSize();
    const f = ($("#map svg")?.dataset.focus || `0,0,${W},${H}`).split(",").map(Number);
    const [fx, fy, fw, fh] = f;
    const s = Math.min(3, Math.min(vp.width / fw, vp.height / fh) * 0.92);
    zoom[viewMap] = { s, x: (vp.width - fw * s) / 2 - fx * s, y: (vp.height - fh * s) / 2 - fy * s };
    applyZoom();
  }
  function applyZoom() { const z = zoom[viewMap]; if (z) $("#mapwrap").style.transform = `translate(${z.x}px,${z.y}px) scale(${z.s})`; }
  function centerOn(id, animate) {
    const t = $(`#map .token[data-id="${CSS.escape(id)}"] circle:not([fill="none"])`);
    const z = zoom[viewMap]; if (!t || !z) return;
    const cx = +t.getAttribute("cx"), cy = +t.getAttribute("cy"), vp = $("#viewport").getBoundingClientRect();
    const sx = cx * z.s + z.x, sy = cy * z.s + z.y;
    if (sx > 60 && sx < vp.width - 60 && sy > 60 && sy < vp.height - 60) return;
    z.x = vp.width / 2 - cx * z.s; z.y = vp.height / 2 - cy * z.s;
    if (animate) $("#mapwrap").style.transition = "transform .4s"; applyZoom();
    setTimeout(() => $("#mapwrap").style.transition = "", 450);
  }
  (function panzoom() {
    const vp = $("#viewport"); let drag = null;
    vp.addEventListener("wheel", (e) => {
      e.preventDefault(); const z = zoom[viewMap]; if (!z) return;
      const r = vp.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
      const f = e.deltaY < 0 ? 1.15 : 1 / 1.15, ns = Math.min(6, Math.max(0.1, z.s * f));
      z.x = mx - (mx - z.x) * (ns / z.s); z.y = my - (my - z.y) * (ns / z.s); z.s = ns; z.user = true; applyZoom();
    }, { passive: false });
    vp.addEventListener("pointerdown", (e) => { if (e.target.closest(".mapctl")) return; drag = { x: e.clientX, y: e.clientY }; vp.classList.add("drag"); });
    window.addEventListener("pointermove", (e) => { if (!drag) return; const z = zoom[viewMap]; if (!z) return; z.x += e.clientX - drag.x; z.y += e.clientY - drag.y; z.user = true; drag = { x: e.clientX, y: e.clientY }; applyZoom(); });
    window.addEventListener("pointerup", () => { drag = null; vp.classList.remove("drag"); });
    document.querySelectorAll(".mapctl button").forEach(b => b.onclick = () => {
      const z = zoom[viewMap]; if (!z) return;
      if (b.dataset.z === "fit") { z.user = false; return fit(); }
      z.user = true;
      const vr = vp.getBoundingClientRect(), f = b.dataset.z === "in" ? 1.25 : 0.8, ns = z.s * f;
      z.x = vr.width / 2 - (vr.width / 2 - z.x) * f; z.y = vr.height / 2 - (vr.height / 2 - z.y) * f; z.s = ns; applyZoom();
    });
    new ResizeObserver(() => { if (viewMap && zoom[viewMap] && !zoom[viewMap].user) fit(); }).observe(vp);
  })();

  // ------------------------------------------------------------ party
  function hpBar(hp, max, tmp) {
    const f = Math.max(0, Math.min(1, hp / Math.max(1, max)));
    const cls = f > .5 ? "" : f > .25 ? "mid" : "low";
    const t = tmp ? `<i class="tmp" style="width:${Math.min(100, tmp / max * 100)}%"></i>` : "";
    return `<div class="bar"><i class="${cls}" style="width:${f * 100}%"></i>${t}<span>${hp} / ${max}${tmp ? ` (+${tmp})` : ""}</span></div>`;
  }
  const pips = (n, full, cls = "") => `<span class="pips ${cls}">${Array.from({ length: n }, (_, i) => `<i class="${i < full ? "full" : ""}"></i>`).join("")}</span>`;
  const chipCond = (c) => `<span class="chip cond">${COND_ICON[c] ? `<img src="/api/icon/${COND_ICON[c]}.svg?c=%23fff" alt="">` : ""}${esc(c)}</span>`;
  function renderParty() {
    const cur = S.combat && S.combat.current;
    let h = S.party.map(p => {
      const cls = Object.entries(p.classes).map(([c, l]) => `${c} ${l}`).join(" / ");
      const slots = Object.entries(p.slots).map(([lv, s]) => `<span title="level ${lv} slots">L${lv} ${pips(s.max, s.left)}</span>`).join(" ");
      const pact = p.pact ? `<span title="pact slots">Pact L${p.pact.level} ${pips(p.pact.count, p.pact.left)}</span>` : "";
      const res = Object.entries(p.resources).map(([n, r]) => `<span class="chip" title="${esc(n)}">${esc(n)} ${r.max - r.used}/${r.max}</span>`).join("");
      const death = p.hp === 0 && !p.dead ? `<div class="row">Death saves ${pips(3, p.death?.success || 0, "ds")} ${pips(3, p.death?.fail || 0, "df")}${p.death?.stable ? " · stable" : ""}</div>` : "";
      return `<div class="pc ${cur === p.id ? "turn" : ""} ${p.hp === 0 || p.dead ? "down" : ""}">
        <img src="/api/portrait/${p.id}.svg" alt="" data-open="${p.id}">
        <div><h3>${esc(p.name)} ${p.inspiration ? '<span title="Heroic Inspiration" style="color:var(--gold)">★</span>' : ""}${p.dead ? ' <span style="color:var(--red)">† dead</span>' : ""}</h3>
        <div class="sub">${esc(p.species)} ${esc(cls)} · ${esc(p.player || "")}</div>
        ${hpBar(p.hp, p.hp_max, p.temp_hp)}
        <div class="stats"><span>AC <b>${p.ac}</b></span><span>Spd <b>${p.speed.walk}</b></span><span>Init <b>${p.init >= 0 ? "+" : ""}${p.init}</b></span><span>PP <b>${p.passive_perception}</b></span><span>XP <b>${p.xp}</b>${p.xp_next ? "/" + p.xp_next : ""}</span></div>
        ${slots || pact ? `<div class="row">${slots} ${pact}</div>` : ""}${death}
        <div class="chips">${p.conditions.map(chipCond).join("")}${p.exhaustion ? `<span class="chip cond">exhaustion ${p.exhaustion}</span>` : ""}${p.concentration ? `<span class="chip conc">◎ ${esc(p.concentration)}</span>` : ""}${res}</div>
        </div></div>`;
    }).join("");
    const others = S.others.filter(o => !o.dead || true);
    if (others.length) {
      h += `<h4>On the map</h4><div class="others">` + others.map(o => `<div class="o" data-open="${o.id}"><img src="/api/token/${o.id}.svg" alt=""><div><b>${esc(o.name)}</b><div class="muted" style="font-size:11px">${esc(o.side)} · ${esc(o.size || "")} ${esc(o.type || "")}</div>
        <div class="chips">${o.conditions.map(chipCond).join("")}</div></div>${o.hp !== undefined ? `<span class="status">${o.hp}/${o.hp_max}</span>` : `<span class="status ${o.status.split(" ")[0]}">${o.status}</span>`}</div>`).join("") + `</div>`;
    }
    if (!S.party.length) h = `<p class="muted">No characters yet.</p>` + h;
    $("#panel-party").innerHTML = h;
    $("#panel-party").querySelectorAll("[data-open]").forEach(el => el.onclick = () => openEntity(el.dataset.open));
  }

  // ------------------------------------------------------------ turns
  function renderTurns() {
    const c = S.combat, el = $("#panel-turns");
    if (!c) { el.innerHTML = `<p class="muted">Not in combat.</p>`; return; }
    let h = `<h4>Round ${c.round}</h4>`;
    if (c.economy) {
      const e = c.economy;
      h += `<div class="econ"><div class="${e.action ? "" : "used"}"><b>⚔</b>Action</div><div class="${e.bonus ? "" : "used"}"><b>✦</b>Bonus</div><div class="${e.reaction ? "" : "used"}"><b>↺</b>Reaction</div><div><b>${e.move_left}</b>ft move</div></div>`;
      if (e.attacks_left) h += `<p class="muted">${e.attacks_left} attack(s) left in this Attack action.</p>`;
    }
    h += c.order.map(o => `<div class="turn-row ${o.side} ${o.current ? "current" : ""}" data-open="${o.id}"><span class="init">${o.init}</span><span>${esc(o.name)}</span><span class="status ${String(o.status).split(" ")[0]}">${esc(o.status)}</span></div>`).join("");
    el.innerHTML = h;
    el.querySelectorAll("[data-open]").forEach(x => x.onclick = () => openEntity(x.dataset.open));
  }

  // ------------------------------------------------------------ dice
  function faces(r) {
    return (r.terms || []).map(t => {
      if (t.flat !== undefined) return `<span class="face flat">${t.flat >= 0 ? "+" : ""}${t.flat}</span>`;
      const d20 = t.dice === "1d20" || (t.dice || "").endsWith("d20");
      const kept = [...(t.kept || [])];
      return (t.faces || []).map(f => { const k = kept.indexOf(f); const drop = k < 0; if (!drop) kept.splice(k, 1); return `<span class="face ${d20 ? "d20" : ""} ${drop ? "drop" : ""}">${f}</span>`; }).join("");
    }).join("");
  }
  const nameOf = (id) => (S.party.find(p => p.id === id) || S.others.find(o => o.id === id) || {}).name || id || "DM";
  function renderDice(prev) {
    const rolls = [...S.rolls].reverse();
    $("#panel-dice").innerHTML = rolls.length ? rolls.map(r => `<div class="roll ${r.nat === 20 ? "n20" : r.nat === 1 ? "n1" : ""}">
      <div class="who">${esc(nameOf(r.who))} · #${esc(r.id)}${r.crit ? " · critical (dice doubled)" : ""}</div><div class="what">${esc(r.purpose)}</div>
      <div class="res">${faces(r)}${r.mode ? `<span class="mode ${r.mode}">${r.mode === "adv" ? "advantage" : "disadvantage"}</span>` : ""}<span class="total">${r.total}</span></div></div>`).join("")
      : `<p class="muted">No rolls yet. Every roll made by the engine appears here with its individual dice.</p>`;
    const newest = S.rolls[S.rolls.length - 1];
    if (prev && newest && newest.id !== lastRoll) {
      const fresh = S.rolls.filter(r => !prev.rolls.find(p => p.id === r.id));
      const d20 = fresh.filter(r => r.nat !== null && r.nat !== undefined);
      if (d20.length) animateDie(d20[d20.length - 1]);
    }
    lastRoll = newest && newest.id;
  }
  let dieTimer;
  function animateDie(r) {
    const ov = $("#diceov"); ov.hidden = false; ov.className = r.nat === 20 ? "n20" : r.nat === 1 ? "n1" : "";
    $("#dieval").textContent = r.nat;
    $("#dielabel").textContent = `${nameOf(r.who)} — ${r.purpose}: ${r.total}`;
    const d = $("#diceov .die"); d.style.animation = "none"; void d.offsetWidth; d.style.animation = "";
    clearTimeout(dieTimer); dieTimer = setTimeout(() => ov.hidden = true, 1900);
  }

  // ------------------------------------------------------------ log
  const slugify = (n) => n.toLowerCase().replace(/&#39;|['’]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  function linkSpells(f) {
    let t = esc(f.text);
    t = t.replace(/(casts |Concentration \(|concentrating on )([A-Z][A-Za-z&#39;/ ]+?)(?= targeting| on | at level|\)|\.|,| —|$)/g,
      (m, pre, n) => pre + `<a class="spell" data-spell="${slugify(n)}">${n}</a>`);
    if (/prepares: /.test(f.text)) t = t.replace(/(prepares: )(.*)$/, (m, pre, list) => pre + list.replace(/\.$/, "").split(", ").map(n => `<a class="spell" data-spell="${slugify(n)}">${n}</a>`).join(", ") + ".");
    return t;
  }
  // newest first, 25 entries per page; page 1 always shows the latest events
  const LOG_PAGE = 25; let logPage = 0, logSeen = 0;
  function renderLog() {
    const el = $("#panel-log"), feed = [...S.feed].reverse();
    const pages = Math.max(1, Math.ceil(feed.length / LOG_PAGE));
    if (logPage > 0 && feed.length > logSeen) logPage += Math.floor((feed.length - logSeen) / LOG_PAGE) * 0; // stay on the chosen page
    logPage = Math.min(logPage, pages - 1); logSeen = feed.length;
    const rows = feed.slice(logPage * LOG_PAGE, (logPage + 1) * LOG_PAGE);
    const pager = `<div class="pager"><button data-p="first" ${logPage === 0 ? "disabled" : ""}>⏮ Latest</button><button data-p="prev" ${logPage === 0 ? "disabled" : ""}>‹ Newer</button>
      <span>Page ${logPage + 1} / ${pages}</span><button data-p="next" ${logPage >= pages - 1 ? "disabled" : ""}>Older ›</button></div>`;
    el.innerHTML = pager + rows.map(f => f.kind === "speech"
      ? `<div class="feed speech"><b>${esc(f.speaker)}:</b> ${esc(f.text)}</div>`
      : `<div class="feed ${esc(f.kind)}">${linkSpells(f)}</div>`).join("") + (pages > 1 ? pager : "");
    el.querySelectorAll(".pager button").forEach(b => b.onclick = () => {
      logPage = b.dataset.p === "first" ? 0 : b.dataset.p === "prev" ? logPage - 1 : logPage + 1; renderLog(); el.scrollTop = 0; });
    if (logPage === 0) el.scrollTop = 0;
  }

  // ------------------------------------------------------------ sheet
  function renderSheet() {
    const el = $("#panel-sheet");
    if (!S.party.length) { el.innerHTML = `<p class="muted">No characters yet.</p>`; return; }
    if (!sheetId || !S.party.find(p => p.id === sheetId)) sheetId = S.party[0].id;
    const p = S.party.find(x => x.id === sheetId);
    const ab = ["str", "dex", "con", "int", "wis", "cha"];
    const sign = (n) => (n >= 0 ? "+" : "") + n;
    el.innerHTML = `<div class="sheet"><select id="sheetsel">${S.party.map(x => `<option value="${x.id}" ${x.id === sheetId ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select>
      <div class="sub">${esc(p.species)} · ${Object.entries(p.classes).map(([c, l]) => c + " " + l).join(" / ")}${Object.values(p.subclasses || {}).length ? " (" + Object.values(p.subclasses).join(", ") + ")" : ""} · ${esc(p.background)}</div>
      <div class="stats" style="margin-top:6px"><span>HP <b>${p.hp}/${p.hp_max}</b></span><span title="${esc(p.ac_why)}">AC <b>${p.ac}</b></span><span>Prof <b>+${p.pb}</b></span><span>Speed <b>${p.speed.walk} ft</b></span><span>${esc(p.wealth)}</span></div>
      <div class="abil">${ab.map(a => `<div><small>${a.toUpperCase()}</small><b>${p.abilities[a]}</b><span>${sign(p.mods[a])}</span></div>`).join("")}</div>
      <h4>Saving throws</h4><div class="skills">${ab.map(a => `<div class="${p.save_profs.includes(a) ? "p" : ""}">${a.toUpperCase()} ${sign(p.saves[a])}</div>`).join("")}</div>
      <h4>Skills</h4><div class="skills">${Object.entries(p.skills).map(([s, v]) => `<div class="${p.skill_profs.includes(s) ? "p" : ""}">${p.expertise.includes(s) ? "◆" : p.skill_profs.includes(s) ? "●" : "○"} ${esc(s)} ${sign(v)}</div>`).join("")}</div>
      <h4>Attacks</h4><table class="t"><tr><th>Attack</th><th>Hit</th><th>Damage</th><th></th></tr>${p.attacks.map(a => `<tr><td>${esc(a.name)}</td><td>${sign(a.bonus)}</td><td>${esc(a.damage)} ${esc(a.type)}</td><td class="muted">${a.range ? a.range.join("/") + " ft" : "reach " + a.reach}${a.mastery ? " · " + esc(a.mastery) : ""}</td></tr>`).join("")}</table>
      ${Object.keys(p.spellcasting).length ? `<h4>Spells</h4>${Object.entries(p.spellcasting).map(([c, s]) => `<div class="muted">${c}: DC ${s.dc} · attack ${sign(s.attack)}</div>`).join("")}
        <div style="font-size:12px;margin-top:4px"><b>Cantrips:</b> ${(p.spells.cantrips || []).map(spellLink).join(", ") || "—"}<br><b>Prepared:</b> ${(p.spells.prepared || []).map(spellLink).join(", ") || "—"}${(p.spells.spellbook || []).length ? `<br><b>Spellbook:</b> ${p.spells.spellbook.map(spellLink).join(", ")}` : ""}</div>` : ""}
      ${p.granted_spells.length ? `<div style="font-size:12px;margin-top:4px"><b>Granted:</b> ${p.granted_spells.map(g => spellLink(g.slug) + (g.free_used ? ' <span class="muted">(free cast used)</span>' : "")).join(", ")}</div>` : ""}
      <h4>Features &amp; traits</h4><div class="feats">${(p.features || []).map((f, i) => `<a class="feat" data-feat="${i}"><b>${esc(f.name)}</b> <span class="muted">${esc(f.source)}</span>${f.text ? `<span class="fsum">${esc(firstLine(f.text))}</span>` : ""}</a>`).join("")}</div>
      <h4>Inventory</h4><div class="inv">${p.inventory.map(i => `<div data-item="${i.id}"><img src="/api/icon/${iconFor(i)}.svg?c=%23fff" alt="">${i.qty > 1 ? i.qty + "× " : ""}${esc(i.name)} ${i.equipped ? '<span class="eq">EQUIPPED</span>' : ""}${i.attuned ? '<span class="eq">ATTUNED</span>' : ""}${i.rarity ? ` <span class="muted">${esc(i.rarity)}</span>` : ""}</div>`).join("")}</div>
      <h4>Languages &amp; tools</h4><div style="font-size:12px">${p.languages.map(esc).join(", ")}<br><span class="muted">${(p.tools || []).map(esc).join(", ")}</span></div></div>`;
    $("#sheetsel").onchange = (e) => { sheetId = e.target.value; renderSheet(); };
    el.querySelectorAll("[data-feat]").forEach(x => x.onclick = () => { const f = p.features[+x.dataset.feat];
      openModal(`<div class="info"><h2>${esc(f.name)}</h2><div class="muted">${esc(f.source)}</div>${md(f.text || "No rules text found.")}</div>`); });
    el.querySelectorAll("[data-item]").forEach(x => x.onclick = () => openModal(`<img src="/api/card/item/${p.id}/${x.dataset.item}.svg">`));
  }
  function firstLine(t) { const s = String(t).replace(/[*_#|]/g, "").replace(/\s+/g, " ").trim(); return s.length > 90 ? s.slice(0, 88) + "…" : s; }
  function iconFor(i) {
    const n = i.name.toLowerCase();
    const map = [["potion", "potion-ball"], ["scroll", "scroll-unfurled"], ["sword", "broadsword"], ["axe", "battle-axe"], ["bow", "bow-arrow"],
      ["arrow", "arrow-cluster"], ["dagger", "plain-dagger"], ["mail", "chain-mail"], ["armor", "chest-armor"], ["shield", "round-shield"], ["staff", "wizard-staff"],
      ["pack", "knapsack"], ["book", "book-cover"], ["spear", "barbed-spear"], ["javelin", "thrown-spear"], ["mace", "flanged-mace"], ["ring", "ring"],
      ["cloak", "cloak"], ["robe", "robe"], ["clothes", "shirt"], ["kit", "first-aid-kit"], ["torch", "torch"], ["rope", "rope-coil"]];
    const hit = map.find(([k]) => n.includes(k));
    return hit ? hit[1] : "swap-bag";
  }

  // ------------------------------------------------------------ requests, handouts, modal
  function renderRequests() {
    $("#requests").innerHTML = S.requests.map(r => `<div class="req"><span>🎲 <b>${esc(r.name)}</b>: ${esc(r.label)}</span><button data-req="${r.id}">Roll</button></div>`).join("");
    $("#requests").querySelectorAll("button").forEach(b => b.onclick = async () => {
      b.disabled = true; b.textContent = "…";
      const res = await fetch(`/api/request/${b.dataset.req}/roll`, { method: "POST", headers: { "X-Requested-With": "dnd-vtt" } });
      const j = await res.json();
      toast(j.error ? "✖ " + j.error : (j.lines || []).slice(-3).join("\n"));
    });
  }
  function renderHandout() {
    const h = S.view.handout, key = JSON.stringify(h || null) + (h ? "" : "");
    if (key === lastHandout) return;
    lastHandout = key;
    if (!h) return;
    let src = "";
    if (h.kind === "item") src = `/api/card/item/${h.owner}/${h.item}.svg`;
    else if (h.kind === "creature") src = `/api/card/creature/${h.ref}.svg`;
    else if (h.kind === "asset") src = `/asset/${h.ref}`;
    else src = `/api/card/handout.svg?v=${S.seq}`;
    openModal(`<img src="${src}" alt="${esc(h.title)}">`);
  }
  function openEntity(id) {
    const p = S.party.find(x => x.id === id);
    if (p) { sheetId = id; switchTab("sheet"); renderSheet(); return; }
    openCreature(id);
  }
  function openModal(html) { $("#modalbody").innerHTML = html; $("#modal").hidden = false; }
  $("#modal").onclick = (e) => { if (e.target.id === "modal" || e.target.classList.contains("x")) $("#modal").hidden = true; };
  let toastTimer;
  function toast(msg) { const t = $("#toast"); t.textContent = msg; t.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => t.hidden = true, 4000); }
  function switchTab(name) {
    document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === name));
    document.querySelectorAll(".panel").forEach(p => p.classList.toggle("on", p.id === "panel-" + name));
    try { localStorage.setItem("tab", name); } catch {}
  }
  document.querySelectorAll("#tabs button").forEach(b => b.onclick = () => switchTab(b.dataset.tab));
  try { const t = localStorage.getItem("tab"); if (t) switchTab(t); } catch {}

  connect(); refresh();
})();
