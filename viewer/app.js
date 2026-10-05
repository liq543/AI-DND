// Live Table: real-time view of the signed game log. Read-only except for DM-requested rolls.
// State arrives over SSE; new animation cues play first (fx.js), then the new state is committed to the page.
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const COND_ICON = { blinded: "blindfold", charmed: "charm", deafened: "silenced", frightened: "screaming", grappled: "grab",
    incapacitated: "knocked-out-stars", invisible: "invisible", paralyzed: "frozen-body", petrified: "stone-bust", poisoned: "poison-bottle",
    prone: "falling", restrained: "manacles", stunned: "knockout", unconscious: "sleepy", raging: "enrage", dodging: "dodging" };
  const FX = window.TableFX;
  let S = null, viewMap = null, followActive = true, lastHandout = "", sheetId = null, firstLoad = true, cameraFollow = true;
  const zoom = {}; // per map: {s, x, y, user, userAt}

  // ------------------------------------------------------------ lookups & art
  const entity = (id) => S && (S.party.find(p => p.id === id) || S.others.find(o => o.id === id) || (S.offstage || []).find(o => o.id === id));
  const nameOf = (id) => (entity(id) || {}).name || id || "DM";
  const faceUrl = (id) => `/api/art/face/${encodeURIComponent(id)}.svg?v=${(entity(id) || {}).art || ""}`;
  const portraitUrl = (id) => `/api/art/portrait/${encodeURIComponent(id)}.svg?v=${(entity(id) || {}).art || ""}`;
  const bustUrl = (id) => `/api/art/bust/${encodeURIComponent(id)}.svg?v=${(entity(id) || {}).art || ""}`;
  const itemArt = (owner, it) => `/api/art/item/${encodeURIComponent(owner)}/${encodeURIComponent(it.id)}.svg?v=${it.art || ""}`;
  const sideOf = (e) => !e ? "neutral" : e.kind === "pc" ? "pc" : (e.side || "enemy");
  const avatar = (id, cls = "") => `<span class="av ${sideOf(entity(id))} ${cls}"><img src="${faceUrl(id)}" alt="" loading="lazy"></span>`;

  // ------------------------------------------------------------ live connection
  function connect() {
    const es = new EventSource("/events");
    es.addEventListener("update", () => refresh());
    es.onopen = () => $("#conn").classList.add("live");
    es.onerror = () => { $("#conn").classList.remove("live"); };
  }
  let refreshing = Promise.resolve();
  function refresh() { refreshing = refreshing.then(doRefresh, doRefresh); return refreshing; }
  async function doRefresh() {
    let st;
    try { st = await (await fetch("/api/state", { cache: "no-store" })).json(); } catch { return; }
    if (st.error) { showAlert(st.error); return; }
    hideAlert();
    S = st; FX.setState(S);
    const cues = FX.collect(S);
    if (!firstLoad && (cues.length || FX.playing)) {
      prefetchMap();
      if (FX.settings().sync === "off") renderPanels();
      FX.play(cues).then(() => render());           // commit once everything queued so far has played
      return;
    }
    firstLoad = false;
    render();
  }

  function showAlert(msg) { const a = $("#alert"); a.textContent = msg; a.hidden = false; $("#integrity").className = "bad"; $("#integrity").textContent = "⚠ integrity check failed"; }
  function hideAlert() { $("#alert").hidden = true; }

  // ------------------------------------------------------------ render all
  function render() {
    if (FX.playing) return;                            // the queue's own .then() commits when it drains
    renderPanels();
    renderMapTabs(); renderMap();
    if (window.TableStory) window.TableStory.update(S);
  }
  function renderPanels() {
    $("#title").textContent = S.campaign || "Live Table";
    document.title = (S.campaign || "Live Table") + " · Live Table";
    $("#meta").innerHTML = `<span class="chip2">Session <b>${S.session}</b></span><span class="chip2">🕯 ${esc(S.time)}</span>` +
      (S.combat ? `<span class="chip2 round">⚔ Round ${S.combat.round}</span>` : `<span class="chip2">Exploring</span>`) +
      (S.overrides.length ? `<span class="chip2 warn" title="${esc(S.overrides.map(o => o.what + ': ' + o.reason).join('\n'))}">⚠ ${S.overrides.length} DM override${S.overrides.length > 1 ? "s" : ""}</span>` : "");
    $("#integrity").className = "";
    $("#integrity").innerHTML = `<span class="ok">✔</span> Signed log`;
    $("#integrity").title = `Every change is a signed, hash-chained event. Tampering is detected.\n${S.events} events · ${S.roll_count} rolls · head ${S.head}`;
    renderFxMenu();
    renderScene(); renderInitBar(); renderParty(); renderTurns(); renderDice(); renderLog(); renderSheet(); renderJournal(); renderRequests(); renderHandout();
    animateBars();
  }

  let sceneKey = "";
  function renderScene() {
    const sc = S.view.scene, el = $("#scene");
    if (!sc) { el.hidden = true; sceneKey = ""; return; }
    el.hidden = false;
    const key = JSON.stringify(sc);
    if (key === sceneKey) return;
    sceneKey = key;
    el.innerHTML = `${sc.image ? `<div class="simg" style="background-image:url('/asset/${esc(sc.image)}')"></div>` : ""}<div class="stxt"><h2>${esc(sc.title)}</h2>${sc.text ? `<p>${esc(sc.text)}</p>` : ""}</div>`;
    el.classList.remove("enter"); void el.offsetWidth; el.classList.add("enter");
  }

  // ------------------------------------------------------------ initiative bar (always visible in combat)
  function renderInitBar() {
    const el = $("#initbar"), c = S.combat;
    if (!c) { el.hidden = true; return; }
    el.hidden = false;
    const cur = c.order.findIndex(o => o.current);
    el.innerHTML = `<span class="lbl"><small>Round</small>${c.round}</span>` + c.order.map((o, i) =>
      `<button class="ib ${o.side} ${o.current ? "current" : ""} ${i === (cur + 1) % c.order.length && c.order.length > 1 ? "next" : ""} ${/Down/.test(o.status) || o.status.startsWith("0/") ? "down" : ""}"
        data-open="${esc(o.id)}" title="${esc(o.name)} · initiative ${o.init} · ${esc(o.status)}">
        <span class="av ${o.side}"><img src="${faceUrl(o.id)}" alt=""></span><span class="n">${esc(o.name)}</span><span class="i">${o.init}</span></button>`).join("");
    el.querySelectorAll("[data-open]").forEach(b => b.onclick = () => openEntity(b.dataset.open));
    const curEl = el.querySelector(".current"); if (curEl) curEl.scrollIntoView({ block: "nearest", inline: "center", behavior: "smooth" });
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
  const SCHOOL_CLR = { abjuration: "#4a8cf0", conjuration: "#e0a030", divination: "#9ad0ff", enchantment: "#ff8ae8", evocation: "#ff6a3a",
    illusion: "#b070f0", necromancy: "#7ac050", transmutation: "#d8c050" };
  async function openSpell(slug) {
    const j = await (await fetch(`/api/spell/${encodeURIComponent(slug)}`)).json();
    if (j.error) { toast("✖ " + j.error, "bad"); return; }
    const school = (String(j.md).match(/\b(abjuration|conjuration|divination|enchantment|evocation|illusion|necromancy|transmutation)\b/i) || [])[1] || "";
    const body = md(j.md).replace(/^<h2>.*?<\/h2>/, "");
    openModal(`<div class="spellcard" style="--sc:${SCHOOL_CLR[school.toLowerCase()] || "#9b6cf0"}"><div class="sphead"><div class="spic">✦</div><div>
      <h2>${esc(j.name)}</h2><div class="muted">${esc(school ? school.charAt(0).toUpperCase() + school.slice(1) : "Spell")}</div></div></div>
      <div class="spbody">${body}</div><p class="muted small">SRD 5.2 text · <a href="https://www.dndbeyond.com/spells?filter-search=${encodeURIComponent(j.name)}" target="_blank" rel="noopener">look it up online</a></p></div>`);
  }
  document.addEventListener("click", (e) => { const a = e.target.closest("a.spell"); if (a) { e.preventDefault(); e.stopPropagation(); openSpell(a.dataset.spell); } });

  // ------------------------------------------------------------ creature info (what the party knows)
  async function openCreature(id) {
    const r = await fetch(`/api/creature/${encodeURIComponent(id)}`); const c = await r.json();
    if (c.error) { openModal(`<img class="bigart" src="/api/card/creature/${encodeURIComponent(id)}.svg">`); return; }
    const row = (k, v) => (v === undefined || v === null || v === "" || (Array.isArray(v) && !v.length)) ? "" : `<tr><th>${k}</th><td>${v}</td></tr>`;
    const conds = c.conditions.map(x => `${chipCond(x.name)}<span class="muted small"> ${esc(x.source || "")}${x.until ? " · until " + esc(x.until) : ""}</span>`).join("<br>");
    const st = String(c.status).split(" ")[0];
    let h = `<div class="ccard ${esc(c.side)}"><div class="chead"><img class="cport" src="/api/art/portrait/${esc(c.id)}.svg?v=${esc(c.art || "")}" alt="">
      <div class="ctitle"><h2>${esc(c.name)}</h2><div class="csub">${esc(c.size || "")} ${esc(c.type || "")}${c.alignment ? ", " + esc(c.alignment) : ""}</div>
      <div class="cchips"><span class="sidechip ${esc(c.side)}">${esc(c.side)}</span><span class="status ${esc(st)}">${esc(c.status)}</span></div>
      ${c.appearance ? `<p class="looks">${(() => { const r = linkify(esc(c.appearance), { kind: "e", id: c.id }); return restoreTokens(r.text, r.tokens); })()}</p>` : `<p class="looks muted">No description yet.</p>`}
      </div></div><div class="cbody"><table class="t ckv">`;
    if (c.full) h += row("HP", `${hpBar(c.hp, c.hp_max, 0, "c:" + c.id)}`) + row("AC", c.ac) + row("Speed", Object.entries(c.speed || {}).map(([k, v]) => `${k} ${v} ft`).join(", "));
    else h += row("AC", c.ac_known ? `${c.ac_known} <span class="muted">(revealed by attack rolls)</span>` : `<span class="muted">unknown until someone attacks it</span>`);
    h += row("Conditions", conds) + row("Attacks seen", c.attacks_seen.map(esc).join(", ")) + row("Saves seen", c.saves_seen.map(esc).join("<br>"))
      + row("Record", (c.hits_taken + c.misses_against) ? `hit ${c.hits_taken}× · missed ${c.misses_against}× · ${c.damage_dealt_to} damage taken` : (c.damage_dealt_to ? `${c.damage_dealt_to} damage taken` : ""))
      + `</table>`;
    let xused = [];
    if (c.lore.length) h += `<h4>What you know</h4><ul class="lore">${c.lore.map(l => { const r = linkify(esc(l), { kind: "e", id: c.id });
      r.used.forEach(u => { if (!xused.find(v => sameTarget(v.target, u.target))) xused.push(u); });
      return `<li>${restoreTokens(r.text, r.tokens)}</li>`; }).join("")}</ul>`;
    const cw = String(c.name).split(/\s+/);
    h += connectedSection(xused, backlinks({ kind: "e", id: c.id }, [c.name, cw.length > 1 ? cw[cw.length - 1] : ""]));
    if (c.full && c.actions && c.actions.length) h += `<h4>Actions</h4>${c.actions.map(a => `<p><b>${esc(a.name)}.</b> ${md(a.text).replace(/<\/?p>/g, " ")}</p>`).join("")}`;
    if (!c.full) h += `<p class="muted small hint">Its stat block stays hidden: this card shows only what your characters have seen. A knowledge check (Arcana, History, Nature, Religion) can earn more, which the DM adds here.</p>`;
    openModal(h + `</div></div>`);
    animateBars();
  }

  // ------------------------------------------------------------ maps
  function renderMapTabs() {
    const maps = Object.values(S.maps);
    const active = S.view.map;
    const world = (maps.find(m => m.world) || {}).id;     // the world map of record: always open, the default view
    if (followActive || !viewMap || !S.maps[viewMap]) viewMap = active || world;
    const key = JSON.stringify([maps.map(m => [m.id, m.name, m.level, m.parent]), viewMap, active]);
    if ($("#maptabs").dataset.key === key) return;
    $("#maptabs").dataset.key = key;
    // the hierarchy (region > town or area > quarter > interior): each tab follows its parent, marked with its level
    const LEVEL_ICON = { region: "🗺", area: "🏘", section: "▦", interior: "🚪" };
    const LEVEL_TIP = { region: "The world map: open it any time", area: "The whole town or area", section: "A quarter or part of it", interior: "Inside a building" };
    const depth = m => { let d = 0, p = m.parent, seen = {}; while (p && S.maps[p] && !seen[p]) { seen[p] = 1; d++; p = S.maps[p].parent; } return d; };
    $("#maptabs").innerHTML = maps.map(m => {
      const lv = m.world ? "region" : (m.level || "section");
      const d = depth(m);
      return `<button data-map="${esc(m.id)}" class="lv-${lv}${m.id === viewMap ? " on" : ""}${m.world ? " world" : ""}" title="${LEVEL_TIP[lv] || ""}">${d ? '<span class="lvsep">›</span>' : ""}${m.id === active ? '<span class="cur" title="On the table"></span>' : ""}${LEVEL_ICON[lv] || ""} ${esc(m.name)}</button>`;
    }).join("");
    $("#maptabs").querySelectorAll("button").forEach(b => b.onclick = () => { viewMap = b.dataset.map; followActive = viewMap === S.view.map; renderMapTabs(); renderMap(true); });
  }
  let mapKey = "", prefetched = {};
  function mapUrl(id, seq) { return `/api/map/${encodeURIComponent(id)}.svg?v=${seq}`; }
  function fetchMap(id, seq) {
    const k = id + ":" + seq;
    if (!prefetched[k]) prefetched[k] = fetch(mapUrl(id, seq), { cache: "no-store" }).then(r => r.ok ? r.text() : null).catch(() => null);
    return prefetched[k];
  }
  function prefetchMap() { const id = (followActive || !viewMap) ? S.view.map : viewMap; if (id && S.maps[id]) fetchMap(id, S.seq); }
  async function renderMap(force) {
    if (!viewMap) { $("#nomap").hidden = false; $("#map").innerHTML = ""; return; }
    $("#nomap").hidden = true;
    const key = viewMap + ":" + S.seq;
    if (key === mapKey && !force) return;
    mapKey = key;
    const text = await fetchMap(viewMap, S.seq);
    for (const k in prefetched) if (k !== key) delete prefetched[k];
    if (!text || mapKey !== key) return;
    const firstTime = !zoom[viewMap];
    const oldFog = $("#map #fog");
    const fogClone = oldFog && oldFog.cloneNode(true);
    $("#map").innerHTML = text;
    FX.committed();
    if (fogClone && $("#map #fog")) {            // newly revealed ground fades in instead of popping
      fogClone.removeAttribute("id"); $("#map #fog").after(fogClone);
      fogClone.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 450, easing: "ease-out" }).finished.then(() => fogClone.remove());
    }
    wireMap();
    if (firstTime || !zoom[viewMap].user) { fit(); requestAnimationFrame(() => { if (!zoom[viewMap].user) fit(); }); } else applyZoom();
    if (S.combat && S.combat.current && followActive && cameraFollow && FX.settings().camera !== "off") camera([tokenCenter(S.combat.current)], false, 400);
  }
  function wireMap() {
    $("#map").querySelectorAll(".token").forEach(t => t.onclick = (ev) => {
      ev.stopPropagation();
      const ids = (t.dataset.stack || "").split(",").filter(Boolean);
      if (ids.length < 2) return openEntity(t.dataset.id);
      openModal(`<div class="info"><h2>Who's here?</h2><div class="muted">${ids.length} creatures share this square</div><div class="picker">` +
        ids.map(id => `<button data-pick="${esc(id)}">${avatar(id)}<span>${esc(nameOf(id))}</span>
          <span class="muted">${esc((entity(id) || {}).status || ((entity(id) || {}).hp !== undefined ? entity(id).hp + "/" + entity(id).hp_max : ""))}</span></button>`).join("") + `</div></div>`);
      document.querySelectorAll("#modal [data-pick]").forEach(b => b.onclick = () => { closeModal(); openEntity(b.dataset.pick); });
    });
    $("#map").querySelectorAll(".poi").forEach(t => t.onclick = (ev) => {
      ev.stopPropagation();
      const p = ((S.maps[viewMap] || {}).pois || []).find(x => x.id === t.dataset.poi); if (!p) return;
      const j = (S.journal || []).find(x => x.id === p.journal);
      if (j) openJournalEntry(j); else openModal(`<div class="info"><h2>${esc(p.name)}</h2><p class="muted">Noted at (${p.x},${p.y}).</p></div>`);
    });
    $("#map").querySelectorAll(".flooritem").forEach(t => t.onclick = (ev) => {
      ev.stopPropagation();
      // everything on this tile: the container's contents, or every item lying there
      const M_ = S.maps[viewMap] || {}, [tx, ty] = String(t.dataset.tile || "").split(",").map(Number);
      const box = (M_.containers || []).find(c => c.id === t.dataset.box);
      const here = (M_.floor || []).filter(f => f.x === tx && f.y === ty);
      if (!here.length && !box) return;
      const cp = box ? (box.coins_cp || 0) : 0;
      const coinRow = cp ? `<li class="flrow"><div class="flart" style="display:flex;align-items:center;justify-content:center;font-size:22px">🪙</div>
        <div><b>${Math.floor(cp / 100).toLocaleString()} crowns</b>${cp % 100 ? `<span class="muted"> ${Math.floor(cp % 100 / 10)} sp ${cp % 10} cp</span>` : ""}<div class="muted small">coin in the ${esc(box.name.replace(/^the /i, ""))}</div></div></li>` : "";
      const rows = here.map(f => `<li class="flrow" data-flitem="${esc(f.id)}" title="View this item"><img class="flart" src="/api/art/floor/${esc(viewMap)}/${esc(f.id)}.svg?v=${esc(f.art || "")}" alt="">
        <div><b>${f.qty > 1 ? f.qty + "× " : ""}${esc(f.name)}</b><div class="muted small">${esc(f.note || "")}${f.in && !box ? " · in a container" : ""}</div></div></li>`).join("");
      const title = box ? esc(box.name) : (here.length === 1 ? esc(here[0].name) : `${here.length} items on the floor`);
      openModal(`<div class="info floor"><h2>${title}</h2><div class="muted">${box ? "A container" : "On the floor"} at (${tx},${ty})${box && box.text ? " · " + esc(box.text) : ""}</div>
        ${here.length || cp ? `<ul class="fllist">${coinRow}${rows}</ul>` : `<p class="muted">Empty.</p>`}
        <p class="muted small">Anyone in or next to that square can ${box ? "take things out or put things in" : "pick these up"} (a free object interaction on their turn). Just tell the DM.</p></div>`);
      document.querySelectorAll("#modal [data-flitem]").forEach(li => li.onclick = () => openItem(`floor~${viewMap}`, li.dataset.flitem));
    });
  }
  function svgSize() { const s = $("#map svg"); return s ? [s.width.baseVal.value, s.height.baseVal.value] : [1, 1]; }
  function fit(animate) {
    // frame the explored part of a fogged map, or the whole map otherwise
    const vp = $("#viewport").getBoundingClientRect(), [W, H] = svgSize();
    const f = ($("#map svg")?.dataset.focus || `0,0,${W},${H}`).split(",").map(Number);
    const [fx, fy, fw, fh] = f;
    const s = Math.min(3, Math.min(vp.width / fw, vp.height / fh) * 0.92);
    zoom[viewMap] = { s, x: (vp.width - fw * s) / 2 - fx * s, y: (vp.height - fh * s) / 2 - fy * s };
    if (animate) return glide(420);
    applyZoom();
  }
  function applyZoom() { const z = zoom[viewMap]; if (z) $("#mapwrap").style.transform = `translate(${z.x}px,${z.y}px) scale(${z.s})`; }
  function glide(dur) {
    const w = $("#mapwrap");
    w.style.transition = `transform ${Math.max(0, dur)}ms cubic-bezier(.3,.7,.3,1)`; applyZoom();
    return new Promise(r => setTimeout(() => { w.style.transition = ""; r(); }, Math.max(0, dur) + 20));
  }
  function tokenCenter(id) {
    const t = id && document.querySelector(`#map .token[data-id="${CSS.escape(id)}"]`);
    return t ? { x: +t.dataset.cx, y: +t.dataset.cy } : null;
  }
  // camera for the animation layer: keep the points in view (points are map coordinates)
  function camera(points, force, dur = 400) {
    const z = zoom[viewMap]; points = points.filter(Boolean);
    if (!z || !points.length) return Promise.resolve();
    if (!force && (!followActive || !cameraFollow)) return Promise.resolve();
    if (!force && z.userAt && Date.now() - z.userAt < 3500) return Promise.resolve();   // the player is looking around: don't fight them
    const vp = $("#viewport").getBoundingClientRect(), m = Math.min(90, vp.width * .15);
    const inside = points.every(p => { const sx = p.x * z.s + z.x, sy = p.y * z.s + z.y; return sx > m && sx < vp.width - m && sy > m && sy < vp.height - m; });
    if (inside && !force) return Promise.resolve();
    const cx = points.reduce((s, p) => s + p.x, 0) / points.length, cy = points.reduce((s, p) => s + p.y, 0) / points.length;
    z.x = vp.width / 2 - cx * z.s; z.y = vp.height / 2 - cy * z.s;
    return glide(dur);
  }
  (function panzoom() {
    const vp = $("#viewport"); let drag = null;
    const touched = (z) => { z.user = true; z.userAt = Date.now(); };
    vp.addEventListener("wheel", (e) => {
      e.preventDefault(); const z = zoom[viewMap]; if (!z) return;
      const r = vp.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
      const f = e.deltaY < 0 ? 1.15 : 1 / 1.15, ns = Math.min(6, Math.max(0.1, z.s * f));
      z.x = mx - (mx - z.x) * (ns / z.s); z.y = my - (my - z.y) * (ns / z.s); z.s = ns; touched(z); applyZoom();
    }, { passive: false });
    vp.addEventListener("pointerdown", (e) => { if (e.target.closest(".mapctl, #skipfx")) return; drag = { x: e.clientX, y: e.clientY }; vp.classList.add("drag"); });
    window.addEventListener("pointermove", (e) => { if (!drag) return; const z = zoom[viewMap]; if (!z) return; z.x += e.clientX - drag.x; z.y += e.clientY - drag.y; touched(z); drag = { x: e.clientX, y: e.clientY }; applyZoom(); });
    window.addEventListener("pointerup", () => { drag = null; vp.classList.remove("drag"); });
    document.querySelectorAll(".mapctl button").forEach(b => b.onclick = () => {
      if (b.dataset.z === "follow") { cameraFollow = !cameraFollow; lsSet("cameraFollow", cameraFollow); b.classList.toggle("on", cameraFollow);
        toast(cameraFollow ? "Camera follows the action" : "Camera stays where you put it"); return; }
      const z = zoom[viewMap]; if (!z) return;
      if (b.dataset.z === "fit") { z.user = false; return fit(true); }
      touched(z);
      const vr = vp.getBoundingClientRect(), f = b.dataset.z === "in" ? 1.25 : 0.8, ns = z.s * f;
      z.x = vr.width / 2 - (vr.width / 2 - z.x) * f; z.y = vr.height / 2 - (vr.height / 2 - z.y) * f; z.s = ns; glide(180);
    });
    new ResizeObserver(() => { if (viewMap && zoom[viewMap] && !zoom[viewMap].user) fit(); }).observe(vp);
    $("#skipfx").onclick = (e) => { e.stopPropagation(); FX.skip(); };
  })();

  // ------------------------------------------------------------ bars that animate between renders
  const barMemory = {};
  function hpBar(hp, max, tmp, key) {
    const f = Math.max(0, Math.min(1, hp / Math.max(1, max)));
    const from = key && barMemory[key] !== undefined ? barMemory[key] : f;
    const cls = (x) => x > .5 ? "" : x > .25 ? "mid" : "low";
    const t = tmp ? `<i class="tmp" style="width:${Math.min(100, tmp / max * 100)}%"></i>` : "";
    return `<div class="bar ${cls(f)}" ${key ? `data-bar="${esc(key)}" data-to="${f}"` : ""}><i class="fill ${cls(f)}" style="width:${from * 100}%"></i>${t}<span>${hp} / ${max}${tmp ? ` <em>+${tmp}</em>` : ""}</span></div>`;
  }
  function animateBars() {
    requestAnimationFrame(() => document.querySelectorAll(".bar[data-bar]").forEach(b => {
      const key = b.dataset.bar, to = +b.dataset.to, from = barMemory[key];
      const fill = b.querySelector(".fill"); if (!fill) return;
      fill.style.width = to * 100 + "%";
      if (from !== undefined && Math.abs(from - to) > .001) {
        const card = b.closest(".pcard, .ocard, .shead");
        if (card) { card.classList.remove("hurt", "healed"); void card.offsetWidth; card.classList.add(to < from ? "hurt" : "healed"); }
      }
      barMemory[key] = to;
    }));
  }

  // ------------------------------------------------------------ party
  const pips = (n, full, cls = "") => `<span class="pips ${cls}">${Array.from({ length: n }, (_, i) => `<i class="${i < full ? "full" : ""}"></i>`).join("")}</span>`;
  const chipCond = (c) => `<span class="chip cond">${COND_ICON[c] ? `<img src="/api/icon/${COND_ICON[c]}.svg?c=%23ffd899" alt="">` : ""}${esc(c)}</span>`;
  function renderParty() {
    const cur = S.combat && S.combat.current;
    let h = S.party.map(p => {
      const cls = Object.entries(p.classes).map(([c, l]) => `${c} ${l}`).join(" / ");
      const slots = Object.entries(p.slots).map(([lv, s]) => `<span class="slot" title="Level ${lv} spell slots: ${s.left}/${s.max}"><small>L${lv}</small>${pips(s.max, s.left)}</span>`).join("");
      const pact = p.pact ? `<span class="slot" title="Pact slots"><small>Pact ${p.pact.level}</small>${pips(p.pact.count, p.pact.left)}</span>` : "";
      const res = Object.entries(p.resources).map(([n, r]) => `<span class="chip res" title="${esc(n)}">${esc(n)} <b>${r.max - r.used}/${r.max}</b></span>`).join("");
      const death = p.hp === 0 && !p.dead ? `<div class="deaths"><span>Death saves</span>${pips(3, p.death?.success || 0, "ds")} ${pips(3, p.death?.fail || 0, "df")}${p.death?.stable ? ` <b class="stable">stable</b>` : ""}</div>` : "";
      const tags = [cur === p.id ? `<span class="tag act">Acting</span>` : "", p.dead ? `<span class="tag dead">† Dead</span>` : p.hp === 0 ? `<span class="tag down">Down</span>` : ""].join("");
      return `<div class="pcard ${cur === p.id ? "turn" : ""} ${p.hp === 0 || p.dead ? "down" : ""}" data-open="${p.id}">
        <div class="port"><img src="${bustUrl(p.id)}" alt="">${p.inspiration ? '<span class="insp" title="Heroic Inspiration">★</span>' : ""}</div>
        <div class="pbody"><div class="ptop"><h3>${esc(p.name)}</h3>${tags}</div>
        <div class="sub">${esc(p.species)} · ${esc(cls)}${p.player ? ` · <span class="muted">${esc(p.player)}</span>` : ""}</div>
        ${hpBar(p.hp, p.hp_max, p.temp_hp, "p:" + p.id)}
        <div class="stats"><span title="Armor Class"><i>🛡</i><b>${p.ac}</b></span><span title="Speed"><i>👣</i><b>${p.speed.walk}</b></span>
          <span title="Initiative"><i>⚡</i><b>${p.init >= 0 ? "+" : ""}${p.init}</b></span><span title="Passive Perception"><i>👁</i><b>${p.passive_perception}</b></span></div>
        ${slots || pact ? `<div class="slots">${slots}${pact}</div>` : ""}${death}
        ${p.conditions.length || p.exhaustion || p.concentration || res ? `<div class="chips">${p.conditions.map(chipCond).join("")}${p.exhaustion ? `<span class="chip cond">exhaustion ${p.exhaustion}</span>` : ""}${p.concentration ? `<span class="chip conc">◎ ${esc(p.concentration)}</span>` : ""}${res}</div>` : ""}
        </div></div>`;
    }).join("");
    const others = S.others;
    if (others.length) {
      h += `<h4 class="sect">Also here <span class="cnt">${others.length}</span></h4><div class="others">` + others.map(o => `<div class="ocard ${esc(o.side)} ${o.dead ? "gone" : ""}" data-open="${o.id}">
        ${avatar(o.id)}<div class="otxt"><b>${esc(o.name)}</b><div class="muted small ol">${esc(o.size || "")} ${esc((o.type || "").split(" ")[0])}</div>
        ${o.hp !== undefined ? hpBar(o.hp, o.hp_max, 0, "o:" + o.id) : ""}${o.conditions.length ? `<div class="chips">${o.conditions.map(chipCond).join("")}</div>` : ""}</div>
        ${o.hp !== undefined ? "" : `<span class="status ${o.status.split(" ")[0]}">${o.status}</span>`}</div>`).join("") + `</div>`;
    }
    if (!S.party.length) h = `<div class="empty"><div class="eic">⚔</div><p>No characters yet.</p><p class="muted small">The DM creates characters with the engine; they appear here the moment they exist.</p></div>` + h;
    $("#panel-party").innerHTML = h;
    $("#panel-party").querySelectorAll("[data-open]").forEach(el => el.onclick = () => openEntity(el.dataset.open));
  }

  // ------------------------------------------------------------ turns
  function renderTurns() {
    const c = S.combat, el = $("#panel-turns");
    if (!c) { el.innerHTML = `<div class="empty"><div class="eic">⚔</div><p>Not in combat.</p><p class="muted small">When a fight starts, the initiative order, whose turn it is and what they have left to spend appear here.</p></div>`; return; }
    const curI = c.order.findIndex(o => o.current);
    let h = `<div class="roundhead"><div class="rnum"><small>Round</small><b>${c.round}</b></div><div><b>${esc(nameOf(c.current) || "—")}</b><div class="muted small">is acting · turn ${curI + 1} of ${c.order.length}</div></div></div>`;
    if (c.economy) {
      const e = c.economy;
      h += `<div class="econ"><div class="${e.action ? "" : "used"}"><b>⚔</b>Action</div><div class="${e.bonus ? "" : "used"}"><b>✦</b>Bonus</div><div class="${e.reaction ? "" : "used"}"><b>↺</b>Reaction</div><div class="${e.move_left > 0 ? "" : "used"}"><b>${e.move_left}</b>ft move</div></div>`;
      if (e.attacks_left) h += `<p class="muted small center">${e.attacks_left} attack${e.attacks_left > 1 ? "s" : ""} left in this Attack action.</p>`;
    }
    h += `<div class="order">` + c.order.map((o, i) => `<div class="turn-row ${o.side} ${o.current ? "current" : ""} ${i === (curI + 1) % c.order.length && c.order.length > 1 ? "next" : ""}" data-open="${o.id}">
      <span class="init">${o.init}</span>${avatar(o.id)}<span class="tn"><b>${esc(o.name)}</b>${o.current ? `<small>acting</small>` : i === (curI + 1) % c.order.length ? `<small>up next</small>` : ""}</span>
      <span class="status ${String(o.status).split(" ")[0]}">${esc(o.status)}</span></div>`).join("") + `</div>`;
    el.innerHTML = h;
    el.querySelectorAll("[data-open]").forEach(x => x.onclick = () => openEntity(x.dataset.open));
  }

  // ------------------------------------------------------------ dice
  function faces(r) {
    return (r.terms || []).map(t => {
      if (t.flat !== undefined) return `<span class="face flat">${t.flat >= 0 ? "+" : ""}${t.flat}</span>`;
      const sides = +((t.dice || "").split("d")[1] || 6);
      const kept = [...(t.kept || [])];
      return (t.faces || []).map(f => { const k = kept.indexOf(f); const drop = k < 0; if (!drop) kept.splice(k, 1);
        return `<span class="face d${sides} ${drop ? "drop" : ""} ${sides === 20 && f === 20 ? "max" : sides === 20 && f === 1 ? "min" : ""}">${f}</span>`; }).join("");
    }).join("");
  }
  let diceKey = "";
  function renderDice() {
    const key = S.rolls.length + ":" + (S.rolls[S.rolls.length - 1] || {}).id;
    if (key === diceKey) return;
    diceKey = key;
    const rolls = [...S.rolls].reverse();
    $("#panel-dice").innerHTML = rolls.length ? rolls.map((r, i) => `<div class="roll ${r.nat === 20 ? "n20" : r.nat === 1 ? "n1" : ""} ${i === 0 ? "newest" : ""}">
      ${r.who && entity(r.who) ? avatar(r.who) : `<span class="av dm">DM</span>`}
      <div class="rmain"><div class="who">${esc(nameOf(r.who))}<span class="muted"> · #${esc(r.id)}${r.crit ? " · critical (dice doubled)" : ""}</span></div><div class="what">${esc(r.purpose)}</div>
      <div class="rres">${faces(r)}${r.mode ? `<span class="mode ${r.mode}">${r.mode === "adv" ? "advantage" : "disadvantage"}</span>` : ""}</div></div>
      <div class="total">${r.total}${r.nat === 20 ? "<small>nat 20</small>" : r.nat === 1 ? "<small>nat 1</small>" : ""}</div></div>`).join("")
      : `<div class="empty"><div class="eic">🎲</div><p>No rolls yet.</p><p class="muted small">Every roll the engine makes appears here with its individual dice.</p></div>`;
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
  const LOG_FILTERS = { all: () => true, story: (f) => ["narration", "speech", "scene", "handout", "map", "info"].includes(f.kind),
    combat: (f) => ["attack", "damage", "heal", "condition", "turn", "combat", "spell", "move", "action", "warning"].includes(f.kind),
    rolls: (f) => ["roll", "request", "roll-hidden"].includes(f.kind) || /\d+d\d+/.test(f.text || ""),
    loot: (f) => ["item", "xp", "rest", "coins"].includes(f.kind) };
  const LOG_PAGE = 30; let logPage = 0, logFilter = null, logKey = "";
  function nameWords(s) {
    return String(s || "").toLowerCase().replace(/['’]/g, "").split(/[^a-z0-9]+/).filter(Boolean);
  }
  function speakerId(name) {
    const n = nameWords(name);
    if (!n.length) return;
    const all = [...S.party, ...S.others, ...(S.offstage || [])];
    const words = (e) => nameWords(e.name);
    return (all.find(e => words(e).join(" ") === n.join(" ")) || all.find(e => words(e)[0] === n[0]) || {}).id;
  }
  function renderLog() {
    if (logFilter === null) logFilter = lsGet("logFilter", "all");
    const el = $("#panel-log");
    const feed = [...S.feed].filter(f => f.kind !== "fx").reverse().filter(LOG_FILTERS[logFilter] || LOG_FILTERS.all);
    const key = JSON.stringify([S.feed.length, logFilter, logPage, (S.feed[S.feed.length - 1] || {}).seq]);
    if (key === logKey) return;
    logKey = key;
    const pages = Math.max(1, Math.ceil(feed.length / LOG_PAGE));
    logPage = Math.min(logPage, pages - 1);
    const rows = feed.slice(logPage * LOG_PAGE, (logPage + 1) * LOG_PAGE);
    const chips = `<div class="logf">${Object.keys(LOG_FILTERS).map(k => `<button data-lf="${k}" class="${k === logFilter ? "on" : ""}">${k[0].toUpperCase() + k.slice(1)}</button>`).join("")}</div>`;
    const pager = pages > 1 ? `<div class="pager"><button data-p="first" ${logPage === 0 ? "disabled" : ""}>⏮ Latest</button><button data-p="prev" ${logPage === 0 ? "disabled" : ""}>‹ Newer</button>
      <span>Page ${logPage + 1} / ${pages}</span><button data-p="next" ${logPage >= pages - 1 ? "disabled" : ""}>Older ›</button></div>` : "";
    el.innerHTML = chips + pager + (rows.map(f => {
      if (f.kind === "speech") { const sid = (f.who && entity(f.who)) ? f.who : speakerId(f.speaker);
        return `<div class="feed speech">${sid ? avatar(sid) : `<span class="av dm">${esc(String(f.speaker || "?")[0])}</span>`}<div class="bub"><b>${esc(f.speaker)}</b>${esc(f.text)}</div></div>`; }
      if (f.kind === "turn") return `<div class="feed turn"><span>${linkSpells(f)}</span></div>`;
      if (f.kind === "combat" && /^— Round/.test(f.text)) return `<div class="feed round"><span>${esc(f.text.replace(/—/g, "").trim())}</span></div>`;
      return `<div class="feed k-${esc(f.kind)}">${linkSpells(f)}</div>`;
    }).join("") || `<div class="empty"><p class="muted">Nothing here yet.</p></div>`) + pager;
    el.querySelectorAll(".pager button").forEach(b => b.onclick = () => {
      logPage = b.dataset.p === "first" ? 0 : b.dataset.p === "prev" ? logPage - 1 : logPage + 1; renderLog(); el.scrollTop = 0; });
    el.querySelectorAll("[data-lf]").forEach(b => b.onclick = () => { logFilter = b.dataset.lf; lsSet("logFilter", logFilter); logPage = 0; renderLog(); });
    if (logPage === 0) el.scrollTop = 0;
  }

  // ------------------------------------------------------------ journal: handouts, clues, known facts, own notes
  let journalKey = "", notesTimer;
  let pins = null;
  function jThumb(e) {
    if (e.kind === "item" && e.owner) { const p = S.party.find(x => x.id === e.owner); const it = p && p.inventory.find(i => i.id === e.item);
      return `<img src="${it ? itemArt(e.owner, it) : `/api/art/item/${encodeURIComponent(e.owner)}/${encodeURIComponent(e.item)}.svg`}" alt="">`; }
    if (e.kind === "srd-item") return `<img src="/api/art/item/srd/${encodeURIComponent(e.ref)}.svg" alt="">`;
    if (e.kind === "creature") return `<img class="round" src="/api/art/face/${encodeURIComponent(e.ref)}.svg" alt="">`;
    if (e.kind === "asset") return `<img src="/asset/${encodeURIComponent(e.ref)}" alt="">`;
    return `<img src="/api/icon/scroll-unfurled.svg?c=%23d8b36a" alt="">`;
  }
  const jRow = (e) => `<div class="jentry"><a data-j="${esc(e.id)}"><span class="jth">${jThumb(e)}</span><div><b>${esc(e.title)}</b>
      <div class="muted small">Session ${e.session} · ${esc(e.time)}</div></div></a>
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
    else if (e.kind === "asset") openModal(`<img class="bigart" src="/asset/${e.ref}">`);
    else openModal(`<div class="info"><h2>${esc(e.title)}</h2></div>`);
  }
  function renderJournal() {
    const el = $("#panel-journal"), j = S.journal || [], lore = S.lore || [];
    if (pins === null) { pins = []; loadPins(); }
    const key = JSON.stringify([j.length, j.map(e => e.cat === "place" ? "p" : "c").join(""), lore.map(l => l.facts.length), pins]);
    if (key === journalKey && el.innerHTML) return;
    journalKey = key;
    // Handouts & clues: what the DM showed on purpose (story items, letters, clues). Map objects (points of interest)
    // live apart under "Places & objects", grouped by where they were seen, so room furniture never buries the clues.
    const recentAll = [...j].reverse();
    const recent = recentAll.filter(e => e.cat !== "place"), places = recentAll.filter(e => e.cat === "place");
    const pinned = recentAll.filter(e => pins.includes(e.id));
    const entries = recent.slice(0, 4).map(jRow).join("") || `<p class="muted small">Nothing yet. Every handout, item card and clue the DM shows you lands here.</p>`;
    const older = recent.length > 4 ? `<button class="jolder" id="jolder">All entries (${recent.length}) ▾</button>` : "";
    const byPlace = [];
    places.forEach(e => { const w = e.where || "Elsewhere"; let g = byPlace.find(x => x[0] === w); if (!g) byPlace.push(g = [w, []]); g[1].push(e); });
    const placesBtn = places.length ? `<h4 class="sect">Places &amp; objects</h4><button class="jolder" id="jplaces">${places.length} things noticed in ${byPlace.length} places ▾</button>` : "";
    const facts = lore.map(l => `<button class="jchip" data-lore="${esc(l.id)}"><span class="av tiny ${sideOf(entity(l.id))}"><img src="/api/art/face/${esc(l.id)}.svg" alt=""></span>${esc(l.name)} <span class="muted">${l.facts.length}</span></button>`).join("");
    const notesVal = $("#mynotes") ? $("#mynotes").value : null, notesH = $("#mynotes") ? $("#mynotes").style.height : "";
    el.innerHTML = `<div class="jtop">${pinned.length ? `<h4 class="sect">📌 Pinned</h4>${pinned.map(jRow).join("")}` : ""}<h4 class="sect">Handouts &amp; clues</h4>${entries}${older}
      ${facts ? `<h4 class="sect">What you know</h4><div class="jchips">${facts}</div>` : ""}${placesBtn}</div>
      <h4 class="sect">My notes</h4><textarea id="mynotes" placeholder="Your own notes. Saved automatically with the campaign."></textarea><div id="notesaved" class="muted small"></div>`;
    if (older) $("#jolder").onclick = () => {
      openModal(`<div class="info"><h2>Handouts &amp; clues</h2><div class="muted">Everything you've been shown, newest first. 📌 to pin.</div><div class="jall">${recent.map(jRow).join("")}</div></div>`);
      wireJournal($("#modalbody"), j);
    };
    if (placesBtn) $("#jplaces").onclick = () => {
      openModal(`<div class="info"><h2>Places &amp; objects</h2><div class="muted">What you noticed on the maps, by place, most recent first. Click a marker on the map, or an entry here. 📌 to pin.</div>
        <div class="jall">${byPlace.map(([w, es]) => `<h4 class="sect">${esc(w)}</h4>${es.map(jRow).join("")}`).join("")}</div></div>`);
      wireJournal($("#modalbody"), j);
    };
    el.querySelectorAll("[data-lore]").forEach(b => b.onclick = () => {
      const l = lore.find(x => x.id === b.dataset.lore); if (!l) return;
      openModal(`<div class="info"><div class="ihead"><span class="av big ${sideOf(entity(l.id))}"><img src="/api/art/face/${esc(l.id)}.svg" alt=""></span><div><h2>${esc(l.name)}</h2><div class="muted">What you know</div></div></div>
        <ul class="lore">${l.facts.map(f => `<li>${esc(f)}</li>`).join("")}</ul><p><a class="spell" id="jopen">Open ${esc(l.name)}'s card</a></p></div>`);
      $("#jopen").onclick = (ev) => { ev.stopPropagation(); openEntity(l.id); };
    });
    wireJournal(el.querySelector(".jtop"), j);
    const ta = $("#mynotes");
    if (notesH) ta.style.height = notesH;
    if (notesVal !== null) ta.value = notesVal;
    const load = async () => { try { const r = await (await fetch("/api/notes")).json(); ta.value = r.text || ""; } catch {} };
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
    if (!S.party.length) { el.innerHTML = `<div class="empty"><div class="eic">📜</div><p>No characters yet.</p></div>`; return; }
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
        ${S.party.length > 1 ? `<div class="whopick">${S.party.map(x => `<button data-pc="${x.id}" class="${x.id === sheetId ? "on" : ""}" title="${esc(x.name)}${x.player ? " (" + esc(x.player) + ")" : ""}">${avatar(x.id)}<span>${esc(x.name.split(" ")[0])}</span></button>`).join("")}</div>` : ""}
        <div class="who"><img class="sport" src="${bustUrl(p.id)}" alt="" data-portrait="${p.id}" title="View portrait">
          <div class="wtxt"><h3>${esc(p.name)} ${p.inspiration ? '<span class="insp" title="Heroic Inspiration">★</span>' : ""}${p.dead ? ' <span class="dead">† dead</span>' : ""}</h3>
            <div class="sub">${esc(p.species)} · ${cls}${subs.length ? ` <span class="muted">(${subs.map(esc).join(", ")})</span>` : ""}</div>
            <div class="sub muted">${esc(p.background)} · Level ${p.level}${p.player ? ` · played by ${esc(p.player)}` : ""}</div></div></div>
        ${hpBar(p.hp, p.hp_max, p.temp_hp, "s:" + p.id)}
        <div class="tiles">${tile("AC", p.ac, p.ac_why)}${tile("Init", sgn(p.init))}${tile("Speed", p.speed.walk + (p.speed.fly ? `<i> / fly ${p.speed.fly}</i>` : ""))}${tile("Prof", "+" + p.pb)}${tile("Passive", p.passive_perception, "Passive Perception")}${tile("Purse", `<span class="purse">${esc(p.wealth)}</span>`, p.wealth)}</div>
        <div class="xp" title="XP ${p.xp}${p.xp_next ? " / " + p.xp_next + " for level " + (p.level + 1) : ""}"><i style="width:${xpPct}%"></i><span>XP ${p.xp}${p.xp_next ? " / " + p.xp_next : ""}</span></div>
        ${p.conditions.length || p.exhaustion || p.concentration ? `<div class="chips">${p.conditions.map(chipCond).join("")}${p.exhaustion ? `<span class="chip cond">exhaustion ${p.exhaustion}</span>` : ""}${p.concentration ? `<span class="chip conc">◎ ${esc(p.concentration)}</span>` : ""}</div>` : ""}
      </div>
      <nav class="stabs" role="tablist">${tabs.map(([k, l]) => `<button role="tab" data-st="${k}" class="${k === sheetTab ? "on" : ""}">${l}</button>`).join("")}</nav>
      <div class="sbody">${sheetSection(p, sheetTab)}</div></div>`;
    if (html === lastSheetHtml && $(".sheet2", el)) return;   // live update that did not touch this sheet: keep the DOM (no flicker)
    lastSheetHtml = html; el.innerHTML = html;

    el.querySelectorAll("[data-pc]").forEach(b => b.onclick = () => { sheetId = b.dataset.pc; renderSheet(); animateBars(); });
    el.querySelectorAll("[data-st]").forEach(b => b.onclick = () => { sheetTab = b.dataset.st; lsSet("sheetTab", sheetTab); renderSheet(); $(".sbody", el).scrollTop = 0; });
    const sp = $("[data-portrait]", el); if (sp) sp.onclick = () => openModal(`<img class="bigart portrait" src="${portraitUrl(p.id)}" alt="${esc(p.name)}">`);
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
    const art = (a) => { const it = a.item && p.inventory.find(i => i.id === a.item); return it ? `<img src="${itemArt(p.id, it)}" alt="">` : `<img src="/api/icon/fist.svg?c=%23d8b36a" alt="">`; };
    return `<div class="atk">${list.map(a => `<div class="acard" ${a.item ? `data-item="${esc(a.item)}"` : ""}>${art(a)}<b>${esc(a.name)}</b><span class="hit">${sgn(a.bonus)}</span>
      <span class="dmg">${esc(a.damage)} ${esc(a.type)}</span><span class="muted rng">${a.range ? a.range.join("/") + " ft" : "reach " + esc(a.reach)}${a.mastery ? ` · <i>${esc(a.mastery)}</i>` : ""}</span></div>`).join("") || `<p class="muted">No attacks.</p>`}</div>`;
  }
  function sheetOverview(p) {
    const eq = p.inventory.filter(i => i.equipped || i.attuned);
    const slots = slotRows(p);
    return `${abilityGrid(p)}
      <h4>Attacks</h4>${attackCards(p, 3)}${p.attacks.length > 3 ? `<a class="more" data-go="combat">All ${p.attacks.length} attacks →</a>` : ""}
      ${slots ? `<h4>Spell slots</h4>${slots}` : ""}
      <h4>Equipped</h4><div class="inv2">${eq.map(i => itemRow(i, p)).join("") || `<p class="muted">Nothing equipped.</p>`}</div>
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
  function itemRow(i, p) {
    const tags = [i.equipped ? '<span class="tag eq">Equipped</span>' : "", i.attuned ? '<span class="tag eq">Attuned</span>' : "", i.lit ? '<span class="tag lit">Lit</span>' : "",
      i.rarity && i.rarity !== "Mundane" ? `<span class="tag r-${esc(String(i.rarity).toLowerCase().replace(/\s+/g, "-"))}">${esc(i.rarity)}</span>` : "",
      i.magic && !i.identified ? '<span class="tag unk">Unidentified</span>' : ""].join("");
    return `<div class="irow ${i.rarity ? "r-" + esc(String(i.rarity).toLowerCase().replace(/\s+/g, "-")) : ""}" data-item="${i.id}" title="${esc(i.source || "")}"><span class="ith"><img src="${itemArt(p.id, i)}" alt="" loading="lazy"></span>
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
          <div class="inv2">${grp.items.map(i => itemRow(i, p)).join("")}</div></details>`;
      }).join("") || `<p class="muted">${q ? "No items match." : "Empty."}</p>`}`;
  }
  function sheetAbout(p) {
    const choices = Object.entries(p.choices || {}).filter(([k, v]) => v && (typeof v !== "object" || Object.keys(v).length));
    return `<div class="aboutport"><img src="${portraitUrl(p.id)}" alt="" data-portrait2="1"></div>
      <div class="kv"><span>Species</span><b>${esc(p.species)}</b></div><div class="kv"><span>Background</span><b>${esc(p.background)}</b></div>
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
    const ap = $("[data-portrait2]", el); if (ap) ap.onclick = () => openModal(`<img class="bigart portrait" src="${portraitUrl(p.id)}" alt="${esc(p.name)}">`);
    const s = $("#invsearch", el);
    if (s) s.oninput = () => { invFilter = s.value; renderSheet(); };
  }
  function firstLine(t) { const s = String(t).replace(/[*_#|]/g, "").replace(/\s+/g, " ").trim(); return s.length > 90 ? s.slice(0, 88) + "…" : s; }

  // ------------------------------------------------------------ requests, handouts, modal
  let reqKey = "";
  function renderRequests() {
    const key = JSON.stringify(S.requests);
    if (key === reqKey) return;
    reqKey = key;
    $("#requests").innerHTML = S.requests.map(r => `<div class="req">${r.who ? avatar(r.who) : ""}<span class="rtxt"><small>The DM asks for a roll</small><b>${esc(r.name)}</b> ${esc(r.label)}</span>
      <button data-req="${r.id}"><svg viewBox="0 0 100 100" aria-hidden="true"><polygon points="50,4 93,28 93,72 50,96 7,72 7,28"/></svg>Roll</button></div>`).join("");
    $("#requests").querySelectorAll("button").forEach(b => b.onclick = async () => {
      b.disabled = true; b.classList.add("rolling");
      const res = await fetch(`/api/request/${b.dataset.req}/roll`, { method: "POST", headers: { "X-Requested-With": "dnd-vtt" } });
      const j = await res.json();
      if (j.error) toast("✖ " + j.error, "bad");
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
    const pc = S.party.find(p => p.id === owner), pit = pc && pc.inventory.find(i => i.id === id);
    const onFloor = String(owner).startsWith("floor~");
    const art = owner === "srd" ? `/api/art/item/srd/${encodeURIComponent(id)}.svg`
      : onFloor ? `/api/art/floor/${encodeURIComponent(owner.slice(6))}/${encodeURIComponent(id)}.svg`
      : `/api/art/item/${encodeURIComponent(owner)}/${encodeURIComponent(id)}.svg?v=${pit ? pit.art : ""}`;
    openModal(`<div class="icard2 ${it.magic ? "magic" : ""}" style="--rc:${clr}">
      <div class="ihead"><div class="iicon"><img src="${art}" alt=""></div>
        <div class="ititle"><h2>${esc(it.name)}</h2><div class="isub">${esc(it.subtitle || "")}</div>
        ${it.rarity ? `<span class="rchip">${esc(it.rarity)}</span>` : ""}${!it.identified ? `<span class="rchip unk">Unidentified</span>` : ""}
        ${tags.map(t => `<span class="tchip">${esc(t)}</span>`).join("")}</div></div>
      ${it.note ? `<div class="isec"><h4>What you see</h4><p class="inote2">${esc(it.note)}</p></div>` : ""}
      ${stats ? `<div class="istats">${stats}</div>` : ""}
      ${it.identified && it.rules_md ? `<div class="isec"><h4>${it.magic ? "Properties" : "Description"}</h4><div class="irules">${md(it.rules_md)}</div></div>` : ""}
      ${!it.identified ? `<div class="isec unk"><h4>Properties unknown</h4><p>It hums with magic when you hold it, but what it does is a mystery. Learn its properties with the <a class="spell" data-spell="identify">Identify</a> spell, or by focusing on it through a Short Rest while touching it (tell the DM).</p></div>` : ""}
      ${it.source ? `<div class="ifoot">${esc(it.source)}</div>` : ""}</div>`);
  }
  function renderHandout() {
    const h = S.view.handout, key = JSON.stringify(h || null);
    if (key === lastHandout) return;
    lastHandout = key;
    if (!h) return;
    let src = "";
    if (h.kind === "item") { openItem(h.owner, h.item); return; }
    if (h.kind === "srd-item") { openItem("srd", h.ref); return; }
    if (h.kind === "creature") { openCreature(h.ref); return; }
    else if (h.kind === "asset") src = `/asset/${h.ref}`;
    else if (h.kind === "text") { openModal(parchment(h.title, h.text)); return; }
    else src = `/api/card/handout.svg?v=${S.seq}`;
    openModal(`<img class="bigart" src="${src}" alt="${esc(h.title)}">`);
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
    if (p) { sheetId = id; switchTab("sheet"); renderSheet(); animateBars(); return; }
    openCreature(id);
  }
  function openModal(html) {
    $("#modalbody").innerHTML = html;
    const m = $("#modal"); m.hidden = false; m.classList.remove("show"); void m.offsetWidth; m.classList.add("show");
  }
  function closeModal() { $("#modal").hidden = true; }
  $("#modal").onclick = (e) => { if (e.target.id === "modal" || e.target.classList.contains("x")) closeModal(); };
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { if (!$("#modal").hidden) closeModal(); else if (!$("#fxmenu").hidden) toggleFxMenu(false); }
  });
  function toast(msg, kind = "") {
    const t = document.createElement("div"); t.className = "toast " + kind; t.textContent = msg;
    $("#toasts").appendChild(t);
    setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 400); }, 3800);
  }
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

  // ------------------------------------------------------------ viewer animation preference (the DM's setting is the default)
  function renderFxMenu() {
    const a = FX.settings(), p = FX.pref(), dm = { ...(S.view.anim || {}) };
    $("#fxlabel").textContent = p === "off" ? "Animations off" : p === "reduced" ? "Reduced motion" : (dm.preset && dm.preset !== "custom" ? dm.preset[0].toUpperCase() + dm.preset.slice(1) : "Animations");
    $("#fxbtn").classList.toggle("dim", p === "off");
    $("#fxdm").innerHTML = `DM's table: <b>${esc(dm.preset || "standard")}</b> · speed ${(+dm.speed || 1)}× · camera ${esc(dm.camera || "follow")}` +
      (a.ambient && a.ambient !== "none" ? ` · ${esc(a.ambient)}` : "");
    document.querySelectorAll('input[name="fxpref"]').forEach(r => r.checked = r.value === p);
  }
  function toggleFxMenu(show) {
    const m = $("#fxmenu"); show = show ?? m.hidden; m.hidden = !show; $("#fxbtn").setAttribute("aria-expanded", show);
  }
  $("#fxbtn").onclick = (e) => { e.stopPropagation(); toggleFxMenu(); };
  document.addEventListener("click", (e) => { if (!e.target.closest("#fxmenu, #fxbtn")) toggleFxMenu(false); });
  document.querySelectorAll('input[name="fxpref"]').forEach(r => r.onchange = () => { FX.setPref(r.value); renderFxMenu(); toast(r.parentElement.querySelector("b").textContent); });

  cameraFollow = lsGet("cameraFollow", true);
  $("#followbtn").classList.toggle("on", cameraFollow);
  try { const t = localStorage.getItem("tab"); if (t) switchTab(t); } catch {}

  FX.init({ esc, nameOf, entity: (id) => entity(id), faceUrl, camera, fit: (a) => fit(a), viewMap: () => viewMap,
    scale: () => (zoom[viewMap] || {}).s || 1 });
  if (window.TableStory) window.TableStory.init({ esc, avatar, speakerId, openModal });
  connect(); refresh();
})();
