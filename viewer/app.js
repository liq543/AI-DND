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
    renderScene(); renderInitBar(); renderMapTabs(); renderMap(prev); renderParty(); renderTurns(); renderDice(prev); renderLog(); renderSheet(); renderJournal(); renderRequests(); renderHandout();
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
      <div class="status ${esc(String(c.status).split(" ")[0])}" style="margin-top:4px">${esc(c.status)}</div></div></div>
      ${c.appearance ? `<p class="looks">${(() => { const r = linkify(esc(c.appearance), { kind: "e", id: c.id }); return restoreTokens(r.text, r.tokens); })()}</p>` : `<p class="looks muted">No description yet.</p>`}<table class="t kv">`;
    if (c.full) h += row("HP", `${c.hp} / ${c.hp_max}`) + row("AC", c.ac) + row("Speed", Object.entries(c.speed || {}).map(([k, v]) => `${k} ${v} ft`).join(", "));
    else h += row("AC", c.ac_known ? `${c.ac_known} <span class="muted">(revealed by attack rolls)</span>` : `<span class="muted">unknown until someone attacks it</span>`);
    h += row("Conditions", conds) + row("Attacks seen", c.attacks_seen.map(esc).join(", ")) + row("Saves seen", c.saves_seen.map(esc).join("<br>"))
      + row("Record", (c.hits_taken + c.misses_against) ? `hit ${c.hits_taken}× · missed ${c.misses_against}× · ${c.damage_dealt_to} damage taken` : (c.damage_dealt_to ? `${c.damage_dealt_to} damage taken` : ""))
      + `</table>`;
    let xused = [];
    if (c.lore.length) h += `<h4>What you know</h4><ul>${c.lore.map(l => { const r = linkify(esc(l), { kind: "e", id: c.id });
      r.used.forEach(u => { if (!xused.find(v => sameTarget(v.target, u.target))) xused.push(u); });
      return `<li>${restoreTokens(r.text, r.tokens)}</li>`; }).join("")}</ul>`;
    const cw = String(c.name).split(/\s+/);
    h += connectedSection(xused, backlinks({ kind: "e", id: c.id }, [c.name, cw.length > 1 ? cw[cw.length - 1] : ""]));
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
    $("#map").querySelectorAll(".poi").forEach(t => t.onclick = (ev) => {
      ev.stopPropagation();
      const p = ((S.maps[viewMap] || {}).pois || []).find(x => x.id === t.dataset.poi); if (!p) return;
      const j = (S.journal || []).find(x => x.id === p.journal);
      if (j) openJournalEntry(j); else openModal(`<div class="info"><h2>${esc(p.name)}</h2><p class="muted">Noted at (${p.x},${p.y}).</p></div>`);
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

  // ------------------------------------------------------------ journal: handouts, clues, known facts, own notes
  let journalKey = "", notesLoaded = false, notesTimer;
  const JICON = { text: "📜", item: "🎒", creature: "👁", asset: "🖼", "srd-item": "✨" };
  let pins = null;
  const jRow = (e) => `<div class="jentry"><a data-j="${esc(e.id)}"><span>${JICON[e.kind] || "📜"}</span><div><b>${esc(e.title)}</b>
      <div class="muted">Session ${e.session} · ${esc(e.time)}</div></div></a>
      <button class="jpin ${pins && pins.includes(e.id) ? "on" : ""}" data-pin="${esc(e.id)}" title="${pins && pins.includes(e.id) ? "Unpin" : "Pin"}">📌</button></div>`;
  async function loadPins() { try { pins = (await (await fetch("/api/pins")).json()).pins || []; } catch { pins = []; } journalKey = ""; renderJournal(); }
  async function togglePin(id) {
    pins = pins.includes(id) ? pins.filter(x => x !== id) : [...pins, id];
    journalKey = ""; renderJournal();
    await fetch("/api/pins", { method: "POST", headers: { "X-Requested-With": "dnd-vtt" }, body: JSON.stringify(pins) });
  }
  function wireJournal(root, j) {
    root.querySelectorAll("[data-j]").forEach(a => a.onclick = () => openJournalEntry(j.find(x => x.id === a.dataset.j)));
    root.querySelectorAll("[data-pin]").forEach(b => b.onclick = (ev) => { ev.stopPropagation(); togglePin(b.dataset.pin);
      if (root.id === "modalbody") { b.classList.toggle("on"); } });
  }
  function openJournalEntry(e) {
    if (!e) return;
    if (e.kind === "text") openModal(parchment(e.title, e.text, e.id));
    else if (e.kind === "item") openItem(e.owner, e.item);
    else if (e.kind === "srd-item") openItem("srd", e.ref);
    else if (e.kind === "creature") openCreature(e.ref);
    else if (e.kind === "asset") openModal(`<img src="/asset/${e.ref}">`);
    else openModal(`<div class="info"><h2>${esc(e.title)}</h2></div>`);
  }
  function renderJournal() {
    const el = $("#panel-journal"), j = S.journal || [], lore = S.lore || [];
    if (pins === null) { pins = []; loadPins(); }
    const key = JSON.stringify([j.length, lore.map(l => l.facts.length), pins]);
    if (key === journalKey && el.innerHTML) return;
    journalKey = key;
    const recent = [...j].reverse();
    const pinned = recent.filter(e => pins.includes(e.id));
    const entries = recent.slice(0, 3).map(jRow).join("") || `<p class="muted">Nothing yet. Every handout, item card and clue the DM shows you lands here.</p>`;
    const older = recent.length > 3 ? `<button class="jolder" id="jolder">Older entries (${recent.length - 3}) ▾</button>` : "";
    const facts = lore.map(l => `<button class="jchip" data-lore="${esc(l.id)}">${esc(l.name)} <span class="muted">${l.facts.length}</span></button>`).join("");
    const notesVal = $("#mynotes") ? $("#mynotes").value : null, notesH = $("#mynotes") ? $("#mynotes").style.height : "";
    el.innerHTML = `<div class="jtop">${pinned.length ? `<h4>📌 Pinned</h4>${pinned.map(jRow).join("")}` : ""}<h4>Handouts &amp; clues</h4>${entries}${older}
      ${facts ? `<h4>What you know</h4><div class="jchips">${facts}</div>` : ""}</div>
      <h4>My notes</h4><textarea id="mynotes" placeholder="Your own notes. Saved automatically with the campaign."></textarea><div id="notesaved" class="muted" style="font-size:11px"></div>`;
    if (older) $("#jolder").onclick = () => {
      openModal(`<div class="info"><h2>Journal</h2><div class="muted">Everything you've been shown, newest first. 📌 to pin.</div><div class="jall">${recent.map(jRow).join("")}</div></div>`);
      wireJournal($("#modalbody"), j);
    };
    el.querySelectorAll("[data-lore]").forEach(b => b.onclick = () => {
      const l = lore.find(x => x.id === b.dataset.lore); if (!l) return;
      openModal(`<div class="info"><h2>${esc(l.name)}</h2><div class="muted">What you know</div><ul>${l.facts.map(f => `<li>${esc(f)}</li>`).join("")}</ul>
        <p><a class="spell" id="jopen">Open ${esc(l.name)}'s info panel</a></p></div>`);
      $("#jopen").onclick = (ev) => { ev.stopPropagation(); openEntity(l.id); };
    });
    wireJournal(el.querySelector(".jtop"), j);
    const ta = $("#mynotes");
    if (notesH) ta.style.height = notesH;
    if (notesVal !== null) { ta.value = notesVal; notesLoaded = true; }
    const load = async () => { try { const r = await (await fetch("/api/notes")).json(); ta.value = r.text || ""; notesLoaded = true; } catch {} };
    if (notesVal === null) load();
    ta.oninput = () => { clearTimeout(notesTimer); $("#notesaved").textContent = "…";
      notesTimer = setTimeout(async () => {
        await fetch("/api/notes", { method: "POST", headers: { "X-Requested-With": "dnd-vtt" }, body: ta.value });
        $("#notesaved").textContent = "Saved."; }, 600); };
  }

  // ------------------------------------------------------------ sheet
  // A header that stays put (who, HP, core numbers) + sub-menus, so the sheet is never one long scroll.
  const lsGet = (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } };
  const lsSet = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} };
  let sheetTab = lsGet("sheetTab", "overview"), invOpen = lsGet("invOpen", {}), featOpen = lsGet("featOpen", {}), invFilter = "";
  const sheetScroll = {}; let lastSheetHtml = "";
  const SKILL_AB = { acrobatics: "dex", "animal handling": "wis", arcana: "int", athletics: "str", deception: "cha", history: "int",
    insight: "wis", intimidation: "cha", investigation: "int", medicine: "wis", nature: "int", perception: "wis", performance: "cha",
    persuasion: "cha", religion: "int", "sleight of hand": "dex", stealth: "dex", survival: "wis" };
  const AB = ["str", "dex", "con", "int", "wis", "cha"];
  const AB_NAME = { str: "Strength", dex: "Dexterity", con: "Constitution", int: "Intelligence", wis: "Wisdom", cha: "Charisma" };
  const sgn = (n) => (n >= 0 ? "+" : "") + n;

  function sheetTabsFor(p) {
    const hasSpells = Object.keys(p.spellcasting || {}).length || (p.granted_spells || []).length;
    return [["overview", "Overview"], ["combat", "Combat"], ["skills", "Skills"], ...(hasSpells ? [["spells", "Spells"]] : []),
      ["features", "Features"], ["inventory", `Inventory <span class="cnt">${p.inventory.length}</span>`], ["about", "About"]];
  }

  function renderSheet() {
    const el = $("#panel-sheet");
    if (!S.party.length) { el.innerHTML = `<p class="muted">No characters yet.</p>`; return; }
    if (!sheetId || !S.party.find(p => p.id === sheetId)) sheetId = S.party[0].id;
    const p = S.party.find(x => x.id === sheetId);
    const tabs = sheetTabsFor(p);
    if (!tabs.find(t => t[0] === sheetTab)) sheetTab = "overview";
    // keep scroll position and a focused search box across live re-renders
    const body = $(".sbody", el);
    if (body) sheetScroll[el.dataset.key] = [body.scrollTop, el.scrollTop];
    const search = $("#invsearch", el), hadFocus = search && document.activeElement === search, caret = hadFocus ? search.selectionStart : 0;
    const key = p.id + ":" + sheetTab;
    el.dataset.key = key;

    const cls = Object.entries(p.classes).map(([c, l]) => `${esc(c)} ${l}`).join(" / ");
    const subs = Object.values(p.subclasses || {});
    const tile = (label, val, title = "") => `<div class="tile" ${title ? `title="${esc(title)}"` : ""}><small>${label}</small><b>${val}</b></div>`;
    const xpPct = p.xp_next ? Math.min(100, Math.round(p.xp / p.xp_next * 100)) : 100;
    const html = `<div class="sheet2">
      <div class="shead">
        ${S.party.length > 1 ? `<select id="sheetsel" aria-label="Character">${S.party.map(x => `<option value="${x.id}" ${x.id === sheetId ? "selected" : ""}>${esc(x.name)}${x.player ? " — " + esc(x.player) : ""}</option>`).join("")}</select>` : ""}
        <div class="who"><img src="/api/portrait/${p.id}.svg" alt="">
          <div class="wtxt"><h3>${esc(p.name)} ${p.inspiration ? '<span class="insp" title="Heroic Inspiration">★</span>' : ""}${p.dead ? ' <span class="dead">† dead</span>' : ""}</h3>
            <div class="sub">${esc(p.species)} · ${cls}${subs.length ? ` <span class="muted">(${subs.map(esc).join(", ")})</span>` : ""}</div>
            <div class="sub muted">${esc(p.background)} · Level ${p.level}</div></div></div>
        ${hpBar(p.hp, p.hp_max, p.temp_hp)}
        <div class="tiles">${tile("AC", p.ac, p.ac_why)}${tile("Init", sgn(p.init))}${tile("Speed", p.speed.walk + (p.speed.fly ? `<i> / fly ${p.speed.fly}</i>` : ""))}${tile("Prof", "+" + p.pb)}${tile("Passive", p.passive_perception, "Passive Perception")}${tile("Purse", `<span class="purse">${esc(p.wealth)}</span>`, p.wealth)}</div>
        <div class="xp" title="XP ${p.xp}${p.xp_next ? " / " + p.xp_next + " for level " + (p.level + 1) : ""}"><i style="width:${xpPct}%"></i><span>XP ${p.xp}${p.xp_next ? " / " + p.xp_next : ""}</span></div>
        ${p.conditions.length || p.exhaustion || p.concentration ? `<div class="chips">${p.conditions.map(chipCond).join("")}${p.exhaustion ? `<span class="chip cond">exhaustion ${p.exhaustion}</span>` : ""}${p.concentration ? `<span class="chip conc">◎ ${esc(p.concentration)}</span>` : ""}</div>` : ""}
      </div>
      <nav class="stabs" role="tablist">${tabs.map(([k, l]) => `<button role="tab" data-st="${k}" class="${k === sheetTab ? "on" : ""}">${l}</button>`).join("")}</nav>
      <div class="sbody">${sheetSection(p, sheetTab)}</div></div>`;
    if (html === lastSheetHtml && $(".sheet2", el)) return;   // live update that did not touch this sheet: keep the DOM (no flicker)
    lastSheetHtml = html; el.innerHTML = html;

    const sel = $("#sheetsel", el); if (sel) sel.onchange = (e) => { sheetId = e.target.value; renderSheet(); };
    el.querySelectorAll("[data-st]").forEach(b => b.onclick = () => { sheetTab = b.dataset.st; lsSet("sheetTab", sheetTab); renderSheet(); $(".sbody", el).scrollTop = 0; });
    wireSheet(el, p);
    const nb = $(".sbody", el), sv = sheetScroll[key]; if (nb && sv) { nb.scrollTop = sv[0]; el.scrollTop = sv[1]; }
    const ns = $("#invsearch", el); if (ns && hadFocus) { ns.focus(); ns.setSelectionRange(caret, caret); }
  }

  function sheetSection(p, tab) {
    if (tab === "overview") return sheetOverview(p);
    if (tab === "combat") return sheetCombat(p);
    if (tab === "skills") return sheetSkills(p);
    if (tab === "spells") return sheetSpells(p);
    if (tab === "features") return sheetFeatures(p);
    if (tab === "inventory") return sheetInventory(p);
    return sheetAbout(p);
  }

  function abilityGrid(p) {
    return `<div class="abil2">${AB.map(a => `<div class="${p.save_profs.includes(a) ? "sp" : ""}" title="${AB_NAME[a]} — save ${sgn(p.saves[a])}${p.save_profs.includes(a) ? " (proficient)" : ""}">
      <small>${a.toUpperCase()}</small><b>${sgn(p.mods[a])}</b><span class="score">${p.abilities[a]}</span><span class="save">save ${sgn(p.saves[a])}${p.save_profs.includes(a) ? " ●" : ""}</span></div>`).join("")}</div>`;
  }
  function resourceRows(p) {
    const rows = Object.entries(p.resources || {}).map(([n, r]) => `<div class="res"><span>${esc(n)}</span>${pips(r.max, r.max - r.used)}<span class="muted">${r.max - r.used}/${r.max}${r.short ? " · " + (r.short === "all" ? "short rest" : r.short === "one" ? "1 per short rest" : "long rest") : " · long rest"}</span></div>`);
    const hd = Object.entries(p.hit_dice || {}).map(([c, h]) => `<div class="res"><span>Hit Point Dice (${esc(c)})</span>${pips(h.max, h.left)}<span class="muted">${h.left}/${h.max}</span></div>`);
    return rows.concat(hd).join("") || `<p class="muted">No limited-use features.</p>`;
  }
  function slotRows(p) {
    const s = Object.entries(p.slots || {}).map(([lv, x]) => `<div class="res"><span>Level ${lv} slots</span>${pips(x.max, x.left)}<span class="muted">${x.left}/${x.max}</span></div>`);
    if (p.pact) s.push(`<div class="res"><span>Pact slots (L${p.pact.level})</span>${pips(p.pact.count, p.pact.left)}<span class="muted">${p.pact.left}/${p.pact.count}</span></div>`);
    return s.join("");
  }
  function attackCards(p, limit) {
    const list = limit ? p.attacks.slice(0, limit) : p.attacks;
    return `<div class="atk">${list.map(a => `<div class="acard"><b>${esc(a.name)}</b><span class="hit">${sgn(a.bonus)}</span>
      <span class="dmg">${esc(a.damage)} ${esc(a.type)}</span><span class="muted rng">${a.range ? a.range.join("/") + " ft" : "reach " + esc(a.reach)}${a.mastery ? ` · <i>${esc(a.mastery)}</i>` : ""}</span></div>`).join("") || `<p class="muted">No attacks.</p>`}</div>`;
  }
  function sheetOverview(p) {
    const eq = p.inventory.filter(i => i.equipped || i.attuned);
    const slots = slotRows(p);
    return `${abilityGrid(p)}
      <h4>Attacks</h4>${attackCards(p, 3)}${p.attacks.length > 3 ? `<a class="more" data-go="combat">All ${p.attacks.length} attacks →</a>` : ""}
      ${slots ? `<h4>Spell slots</h4>${slots}` : ""}
      <h4>Equipped</h4><div class="inv2">${eq.map(itemRow).join("") || `<p class="muted">Nothing equipped.</p>`}</div>
      ${Object.keys(p.resources || {}).length ? `<h4>Features to track</h4>${Object.entries(p.resources).map(([n, r]) => `<div class="res"><span>${esc(n)}</span>${pips(r.max, r.max - r.used)}</div>`).join("")}` : ""}`;
  }
  function sheetCombat(p) {
    const death = p.hp === 0 && !p.dead ? `<h4>Death saves</h4><div class="res"><span>Successes</span>${pips(3, p.death?.success || 0, "ds")}</div><div class="res"><span>Failures</span>${pips(3, p.death?.fail || 0, "df")}</div>${p.death?.stable ? `<p class="muted">Stable.</p>` : ""}` : "";
    const sp = Object.entries(p.speed || {}).filter(([k, v]) => v).map(([k, v]) => `${esc(k)} ${v} ft`).join(" · ");
    return `${death}<h4>Attacks <span class="muted">(${p.attacks.length})</span></h4>${attackCards(p)}
      <h4>Defences &amp; movement</h4><div class="kv"><span>Armor Class</span><b>${p.ac}</b><span class="muted">${esc(p.ac_why)}</span></div>
      <div class="kv"><span>Speed</span><b>${esc(sp)}</b></div><div class="kv"><span>Initiative</span><b>${sgn(p.init)}</b></div>
      <h4>Resources &amp; recovery</h4>${resourceRows(p)}
      ${slotRows(p) ? `<h4>Spell slots</h4>${slotRows(p)}` : ""}`;
  }
  function sheetSkills(p) {
    const by = {}; Object.entries(p.skills).forEach(([s, v]) => { (by[SKILL_AB[s] || "other"] ||= []).push([s, v]); });
    const mark = (s) => p.expertise.includes(s) ? `<i class="ex" title="Expertise">◆</i>` : p.skill_profs.includes(s) ? `<i class="pr" title="Proficient">●</i>` : `<i class="no">○</i>`;
    const passive = (s) => 10 + (p.skills[s] ?? 0);
    return `<h4>Saving throws</h4><div class="grid2">${AB.map(a => `<div class="row2 ${p.save_profs.includes(a) ? "p" : ""}">${p.save_profs.includes(a) ? '<i class="pr">●</i>' : '<i class="no">○</i>'}<span>${AB_NAME[a]}</span><b>${sgn(p.saves[a])}</b></div>`).join("")}</div>
      <h4>Skills</h4><div class="skgroups">${AB.filter(a => by[a]).map(a => `<div class="skg"><div class="skh">${AB_NAME[a]} <span class="muted">${sgn(p.mods[a])}</span></div>
        ${by[a].map(([s, v]) => `<div class="row2 ${p.skill_profs.includes(s) ? "p" : ""}">${mark(s)}<span>${esc(s)}</span><b>${sgn(v)}</b></div>`).join("")}</div>`).join("")}</div>
      <h4>Passive senses</h4><div class="grid2"><div class="row2"><i>👁</i><span>Perception</span><b>${p.passive_perception}</b></div><div class="row2"><i>💭</i><span>Insight</span><b>${passive("insight")}</b></div><div class="row2"><i>🔍</i><span>Investigation</span><b>${passive("investigation")}</b></div></div>
      <p class="muted legend">◆ expertise · ● proficient · ○ untrained</p>`;
  }
  function sheetSpells(p) {
    const casting = Object.entries(p.spellcasting || {}).map(([c, s]) => `<div class="kv"><span>${esc(c)}</span><b>DC ${s.dc}</b><span class="muted">attack ${sgn(s.attack)}</span></div>`).join("");
    const list = (label, arr) => arr && arr.length ? `<h4>${label} <span class="muted">(${arr.length})</span></h4><div class="spells">${arr.map(s => `<span class="sp">${spellLink(s)}</span>`).join("")}</div>` : "";
    const granted = (p.granted_spells || []).length ? `<h4>Granted</h4><div class="spells">${p.granted_spells.map(g => `<span class="sp">${spellLink(g.slug)}<small class="muted">${esc(g.source)}${g.free_used ? " · free cast used" : ""}</small></span>`).join("")}</div>` : "";
    return `${casting ? `<h4>Spellcasting</h4>${casting}` : ""}${slotRows(p) ? `<h4>Slots</h4>${slotRows(p)}` : ""}
      ${list("Cantrips", p.spells.cantrips)}${list("Prepared", p.spells.prepared)}${list("Spellbook", p.spells.spellbook)}${granted}`;
  }
  function featGroupKey(f, p) {
    const src = String(f.source || "");
    if (Object.keys(p.classes).some(c => src.startsWith(c))) return src.replace(/\s*\d+$/, "");
    if (Object.values(p.subclasses || {}).some(s => src.startsWith(s))) return src.replace(/\s*\d+$/, "");
    if (src === p.species) return "Species: " + src;
    return "Feats & origin";
  }
  function sheetFeatures(p) {
    const groups = {};
    (p.features || []).forEach((f, i) => { (groups[featGroupKey(f, p)] ||= []).push([f, i]); });
    return Object.entries(groups).map(([g, fs]) => {
      const open = featOpen[p.id + ":" + g] ?? true;
      return `<details class="grp" data-fg="${esc(g)}" ${open ? "open" : ""}><summary>${esc(g)} <span class="cnt">${fs.length}</span></summary>
        <div class="feats">${fs.map(([f, i]) => `<a class="feat" data-feat="${i}"><b>${esc(f.name)}</b> <span class="muted">${esc(f.source)}</span>${f.text ? `<span class="fsum">${esc(firstLine(f.text))}</span>` : ""}</a>`).join("")}</div></details>`;
    }).join("") || `<p class="muted">No features.</p>`;
  }
  function itemRow(i) {
    const tags = [i.equipped ? '<span class="tag eq">Equipped</span>' : "", i.attuned ? '<span class="tag eq">Attuned</span>' : "", i.lit ? '<span class="tag lit">Lit</span>' : "",
      i.rarity && i.rarity !== "Mundane" ? `<span class="tag r-${esc(String(i.rarity).toLowerCase().replace(/\s+/g, "-"))}">${esc(i.rarity)}</span>` : ""].join("");
    return `<div class="irow" data-item="${i.id}" title="${esc(i.source || "")}"><img src="/api/icon/${iconFor(i)}.svg?c=%23fff" alt="">
      <div class="itxt"><div class="iname">${i.qty > 1 ? `<span class="qty">${i.qty}×</span>` : ""}${esc(i.alias || i.name)}${i.alias ? ` <span class="muted">(${esc(i.name)})</span>` : ""}</div>
      ${i.note ? `<div class="inote">${esc(firstLine(i.note))}</div>` : ""}</div><div class="itags">${tags}</div></div>`;
  }
  function invGroups(p) {
    const g = new Map(), add = (k, label, i, closed) => { if (!g.has(k)) g.set(k, { label, items: [], closed }); g.get(k).items.push(i); };
    const q = invFilter.trim().toLowerCase();
    for (const i of p.inventory) {
      if (q && !`${i.name} ${i.alias || ""} ${i.note || ""} ${i.source || ""}`.toLowerCase().includes(q)) continue;
      const pack = /\(unpacked from ([^)]+)\)/.exec(i.source || "");
      if (i.equipped || i.attuned) add("equipped", "Equipped", i);
      else if (pack) add("pack:" + pack[1], "🎒 " + pack[1], i, true);
      else if (i.kind === "weapon") add("weapons", "Weapons", i);
      else if (i.kind === "armor" || i.kind === "shield") add("armor", "Armor & shields", i);
      else if (i.magic || i.kind === "consumable" || /potion|scroll/i.test(i.name)) add("magic", "Magic & consumables", i);
      else if (/^(stolen|loot|reward|gift|quest|found)/i.test(i.source || "")) add("loot", "Loot, clues & keepsakes", i);
      else add("gear", "Gear & tools", i);
    }
    const order = ["equipped", "weapons", "armor", "magic", "loot", "gear"];
    return [...g.entries()].sort((a, b) => (order.indexOf(a[0]) + 1 || 99) - (order.indexOf(b[0]) + 1 || 99));
  }
  function sheetInventory(p) {
    const coins = Object.entries(p.coins || {}).filter(([k, v]) => v).map(([k, v]) => `<span class="coin c-${esc(k)}">${v} ${esc(k.toUpperCase())}</span>`).join("") || `<span class="muted">No coins</span>`;
    const groups = invGroups(p);
    const q = invFilter.trim();
    return `<div class="invbar"><input id="invsearch" type="search" placeholder="Search ${p.inventory.length} items…" value="${esc(invFilter)}" aria-label="Search inventory">
        <button data-inv="expand" title="Expand all">▾</button><button data-inv="collapse" title="Collapse all">▸</button></div>
      <div class="coins">${coins}${Object.values(p.coins || {}).filter(Boolean).length > 1 ? ` <span class="muted">· total ${esc(p.wealth)}</span>` : ""}</div>
      ${groups.map(([k, grp]) => {
        const open = q ? true : (invOpen[p.id + ":" + k] ?? !grp.closed);
        const n = grp.items.reduce((s, i) => s + (i.qty || 1), 0);
        return `<details class="grp" data-ig="${esc(k)}" ${open ? "open" : ""}><summary>${esc(grp.label)} <span class="cnt">${grp.items.length}${n !== grp.items.length ? ` · ${n} pcs` : ""}</span></summary>
          <div class="inv2">${grp.items.map(itemRow).join("")}</div></details>`;
      }).join("") || `<p class="muted">${q ? "No items match." : "Empty."}</p>`}`;
  }
  function sheetAbout(p) {
    const choices = Object.entries(p.choices || {}).filter(([k, v]) => v && (typeof v !== "object" || Object.keys(v).length));
    return `<div class="kv"><span>Species</span><b>${esc(p.species)}</b></div><div class="kv"><span>Background</span><b>${esc(p.background)}</b></div>
      <div class="kv"><span>Class</span><b>${Object.entries(p.classes).map(([c, l]) => esc(c) + " " + l).join(" / ")}</b></div>
      ${(p.feats || []).length ? `<div class="kv"><span>Feats</span><b>${p.feats.map(esc).join(", ")}</b></div>` : ""}
      <h4>Languages</h4><div class="chips">${p.languages.map(l => `<span class="chip">${esc(l)}</span>`).join("")}</div>
      <h4>Tools</h4><div class="chips">${(p.tools || []).map(t => `<span class="chip">${esc(t)}</span>`).join("") || '<span class="muted">None</span>'}</div>
      ${choices.length ? `<h4>Build choices</h4>${choices.map(([k, v]) => `<div class="kv"><span>${esc(k.replace(/_/g, " "))}</span><b>${esc(Array.isArray(v) ? v.join(", ") : typeof v === "object" ? Object.entries(v).map(([a, b]) => a + ": " + b).join(", ") : v)}</b></div>`).join("")}` : ""}`;
  }
  function wireSheet(el, p) {
    el.querySelectorAll("[data-feat]").forEach(x => x.onclick = () => { const f = p.features[+x.dataset.feat];
      openModal(`<div class="info"><h2>${esc(f.name)}</h2><div class="muted">${esc(f.source)}</div>${md(f.text || "No rules text found.")}</div>`); });
    el.querySelectorAll("[data-item]").forEach(x => x.onclick = () => openItem(p.id, x.dataset.item));
    el.querySelectorAll("[data-go]").forEach(a => a.onclick = () => { sheetTab = a.dataset.go; lsSet("sheetTab", sheetTab); renderSheet(); });
    el.querySelectorAll("details[data-ig]").forEach(d => d.ontoggle = () => { if (invFilter.trim()) return; invOpen[p.id + ":" + d.dataset.ig] = d.open; lsSet("invOpen", invOpen); });
    el.querySelectorAll("details[data-fg]").forEach(d => d.ontoggle = () => { featOpen[p.id + ":" + d.dataset.fg] = d.open; lsSet("featOpen", featOpen); });
    el.querySelectorAll("[data-inv]").forEach(b => b.onclick = () => {
      invGroups(p).forEach(([k]) => { invOpen[p.id + ":" + k] = b.dataset.inv === "expand"; }); lsSet("invOpen", invOpen); renderSheet(); });
    const s = $("#invsearch", el);
    if (s) s.oninput = () => { invFilter = s.value; renderSheet(); };
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
  // ------------------------------------------------------------ item cards (HTML: grows with its text, respects identification)
  const RARITY_CLR = { Common: "#9aa0a6", Uncommon: "#3fa34d", Rare: "#3d7be0", "Very Rare": "#9b4de0", Legendary: "#e08a1e", Artifact: "#c23b3b" };
  async function openItem(owner, id) {
    let it;
    try { it = await (await fetch(`/api/item/${encodeURIComponent(owner)}/${encodeURIComponent(id)}`)).json(); } catch { it = null; }
    if (!it || it.error) { openModal(`<div class="info"><h2>Unknown item</h2></div>`); return; }
    const clr = it.identified ? (RARITY_CLR[it.rarity] || (it.magic ? "#8a6d3a" : "#7a6a52")) : "#6a5f72";
    const tags = [it.equipped ? "Equipped" : "", it.attuned ? "Attuned" : "", it.lit ? "Lit" : "", it.qty > 1 ? `${it.qty} carried` : "",
      it.attunement ? "Requires attunement" : ""].filter(Boolean);
    const stats = (it.stats || []).map(([k, v]) => `<div class="st"><small>${esc(k)}</small><b>${esc(v)}</b></div>`).join("");
    openModal(`<div class="icard2" style="--rc:${clr}">
      <div class="ihead"><div class="iicon"><img src="/api/icon/${iconFor({ name: it.base || it.name, kind: it.kind })}.svg?c=%23f3e7cc" alt=""></div>
        <div class="ititle"><h2>${esc(it.name)}</h2><div class="isub">${esc(it.subtitle || "")}</div>
        ${it.rarity ? `<span class="rchip">${esc(it.rarity)}</span>` : ""}${!it.identified ? `<span class="rchip unk">Unidentified</span>` : ""}
        ${tags.map(t => `<span class="tchip">${esc(t)}</span>`).join("")}</div></div>
      ${it.note ? `<div class="isec"><h4>What you see</h4><p class="inote2">${esc(it.note)}</p></div>` : ""}
      ${stats ? `<div class="istats">${stats}</div>` : ""}
      ${it.identified && it.rules_md ? `<div class="isec"><h4>${it.magic ? "Properties" : "Description"}</h4><div class="irules">${linkSpellsInHtml(md(it.rules_md))}</div></div>` : ""}
      ${!it.identified ? `<div class="isec unk"><h4>Properties unknown</h4><p>It hums with magic when you hold it, but what it does is a mystery. Learn its properties with the <a class="spell" data-spell="identify">Identify</a> spell, or by focusing on it through a Short Rest while touching it (tell the DM).</p></div>` : ""}
      ${it.source ? `<div class="ifoot">${esc(it.source)}</div>` : ""}</div>`);
  }
  const linkSpellsInHtml = (h) => h;
  function renderHandout() {
    const h = S.view.handout, key = JSON.stringify(h || null) + (h ? "" : "");
    if (key === lastHandout) return;
    lastHandout = key;
    if (!h) return;
    let src = "";
    if (h.kind === "item") { openItem(h.owner, h.item); return; }
    if (h.kind === "srd-item") { openItem("srd", h.ref); return; }
    if (h.kind === "creature") src = `/api/card/creature/${h.ref}.svg`;
    else if (h.kind === "asset") src = `/asset/${h.ref}`;
    else if (h.kind === "text") { openModal(parchment(h.title, h.text)); return; }
    else src = `/api/card/handout.svg?v=${S.seq}`;
    openModal(`<img src="${src}" alt="${esc(h.title)}">`);
  }
  // ------------------------------------------------------------ cross-links between journal entries, people and things
  // Every known name (journal entries, crew, NPCs with known facts, creatures in view) becomes a link wherever it is
  // mentioned; every card lists what it links to and what links back to it ("Connected").
  function xrefTargets() {
    const out = [];
    const add = (alias, target, label) => { alias = String(alias || "").trim(); if (alias.length >= 4) out.push({ alias, target, label }); };
    for (const e of (S.journal || [])) {
      const t = { kind: "j", id: e.id }, title = e.title || "";
      add(title, t, title);
      add(title.split(" (")[0], t, title);
      title.split(/\s+—\s+/).forEach(part => add(part, t, title));
      if (/^the /i.test(title.split(" (")[0])) add(title.split(" (")[0].replace(/^the /i, ""), t, title);
    }
    const people = [...(S.party || []), ...(S.lore || []), ...(S.others || [])];
    const seen = new Set();
    for (const c of people) {
      if (!c || seen.has(c.id)) continue; seen.add(c.id);
      const t = { kind: "e", id: c.id }, words = String(c.name).split(/\s+/);
      add(c.name, t, c.name);
      if (words.length > 1) { add(words[0], t, c.name); add(words[words.length - 1], t, c.name); }
    }
    // longest first so "The Silver Key" wins over "Silver"; ignore titles and generic words
    const stop = new Set(["The", "A", "An", "Old", "Young", "Lord", "Lady", "Sir", "Dame", "Master", "Mistress", "Brother", "Sister",
      "Father", "Mother", "Captain", "Sergeant", "Lieutenant", "Guard", "Commoner", "Bandit", "Cultist", "Scout", "Noble"]);
    return out.filter(x => !stop.has(x.alias)).sort((a, b) => b.alias.length - a.alias.length);
  }
  const sameTarget = (a, b) => a && b && a.kind === b.kind && a.id === b.id;
  function linkify(escapedText, self) {
    // replace aliases with placeholder tokens first (so later replacements can't touch inserted HTML)
    const targets = xrefTargets(), used = [], tokens = [];
    let t = escapedText;
    for (const x of targets) {
      if (sameTarget(x.target, self)) continue;
      const a = esc(x.alias).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const re = new RegExp(`(^|[^\\w\\u0001])(${a})(?![\\w\\u0002])`, "g");
      if (!re.test(t)) continue;
      t = t.replace(re, (m, pre, name) => { tokens.push({ name, target: x.target }); return `${pre}\u0001${tokens.length - 1}\u0002`; });
      if (!used.find(u => sameTarget(u.target, x.target))) used.push(x);
    }
    return { text: t, tokens, used };
  }
  const xrefAnchor = (tk) => `<a class="xref" data-xk="${tk.target.kind}" data-xid="${esc(tk.target.id)}">${tk.name}</a>`;
  const restoreTokens = (html, tokens) => html.replace(/\u0001(\d+)\u0002/g, (m, i) => xrefAnchor(tokens[+i]));
  function backlinks(self, selfNames) {
    // journal entries whose text mentions this entry/creature
    const names = selfNames.filter(n => n && n.length >= 4);
    return (S.journal || []).filter(e => !(self.kind === "j" && e.id === self.id) &&
      names.some(n => new RegExp(`(^|\\W)${n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(\\W|$)`, "i").test((e.title || "") + " " + (e.text || ""))));
  }
  function connectedSection(used, back) {
    const items = [];
    for (const u of used) items.push(`<a class="xref chip" data-xk="${u.target.kind}" data-xid="${esc(u.target.id)}">${u.target.kind === "j" ? "📜" : "👤"} ${esc(u.label)}</a>`);
    for (const e of back) if (!used.find(u => u.target.kind === "j" && u.target.id === e.id))
      items.push(`<a class="xref chip" data-xk="j" data-xid="${esc(e.id)}">↩ ${esc(e.title)}</a>`);
    return items.length ? `<div class="connected"><div class="clbl">Connected</div>${items.join("")}</div>` : "";
  }
  document.addEventListener("click", (ev) => {
    const a = ev.target.closest("a.xref"); if (!a) return;
    ev.preventDefault(); ev.stopPropagation();
    if (a.dataset.xk === "j") openJournalEntry((S.journal || []).find(x => x.id === a.dataset.xid));
    else openEntity(a.dataset.xid);
  });

  // "Name:" speaker markers in handouts: every party member's first name, plus linked names
  function pcMarkerRe() {
    const names = (S.party || []).map(p => String(p.name).split(/\s+/)[0]).filter(n => n.length > 1)
      .map(n => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    return new RegExp(`\\s+(${names.length ? `(?:${names.join("|")})|` : ""}\u0001\\d+\u0002):(?=\\s)`, "g");
  }
  // text handouts: a parchment card that grows to fit (scrolls only if taller than the screen)
  function parchment(title, text, jid) {
    const self = jid ? { kind: "j", id: jid } : null;
    const { text: linked, tokens, used } = linkify(esc(String(text || "").replace(/\\n/g, "\n")), self);
    // "LABEL:" markers (caps words, numbers, commas, apostrophes: "PROBLEM 1, GETTING IN:", "THE RING'S CLOCK:") start a
    // new line in bold, as do "<PC name>:" markers (any party member's first name)
    let t = linked.replace(/\s*((?:[A-Z][A-Z]*(?:&#39;|['’])?[A-Z]*|\d+)(?:,?\s+(?:[A-Z][A-Z]*(?:&#39;|['’])?[A-Z]*|\d+))*):(?=\s)/g,
      (m, label) => /[A-Z]{2}/.test(label) && label.length >= 3 ? `\n<b>${label}:</b>` : m)
      .replace(pcMarkerRe(), "\n<b>$1:</b>");
    const body = restoreTokens(t.split(/\n+/).map(l => l.trim()).filter(Boolean).map(l => `<p>${l}</p>`).join(""), tokens);
    const back = self ? backlinks(self, [title, String(title || "").split(" (")[0]]) : [];
    return `<div class="parchment"><h2>${esc(title || "Handout")}</h2><div class="sub">Handout</div>${body}${connectedSection(used, back)}</div>`;
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
  (function sideGrip() {
    const side = $("#side"), grip = $("#sidegrip");
    if (!side || !grip) return;
    const apply = (w) => { side.style.width = Math.round(Math.max(300, Math.min(window.innerWidth * 0.7, w))) + "px"; };
    const saved = lsGet("sideWidth", null); if (saved) apply(saved);
    grip.onpointerdown = (e) => {
      e.preventDefault(); grip.setPointerCapture(e.pointerId); document.body.classList.add("resizing");
      const move = (ev) => { apply(window.innerWidth - ev.clientX); window.dispatchEvent(new Event("resize")); };
      const up = () => { grip.onpointermove = null; grip.onpointerup = null; document.body.classList.remove("resizing");
        lsSet("sideWidth", side.getBoundingClientRect().width); window.dispatchEvent(new Event("resize")); };
      grip.onpointermove = move; grip.onpointerup = up;
    };
    grip.ondblclick = () => { side.style.width = ""; lsSet("sideWidth", null); window.dispatchEvent(new Event("resize")); };
  })();
  try { const t = localStorage.getItem("tab"); if (t) switchTab(t); } catch {}

  connect(); refresh();
})();
