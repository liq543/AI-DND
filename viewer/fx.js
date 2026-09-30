// Table FX: the animation layer of the live table.
// The engine sends "cues" (the structured side of the public log: moves, attacks, damage, spells, turns, DM effects).
// New cues play here in order, on top of the map as it was before the change; when the queue drains the app commits the
// new state (map, panels), so tokens never jump and a result never shows before its animation. The DM decides how the
// table animates (`python -m engine fx ...`); each viewer can still tone it down for themselves.
(() => {
  const NS = "http://www.w3.org/2000/svg";
  const $ = (s, el = document) => el.querySelector(s);
  const DTYPE = { fire: "#ff7a2a", cold: "#8ae0ff", lightning: "#d8ecff", thunder: "#a8b8ff", acid: "#a8f03a", poison: "#7ad05a",
    necrotic: "#a86ae0", radiant: "#ffe690", force: "#c8b0ff", psychic: "#ff8ae8", slashing: "#ffffff", piercing: "#f4f4f4",
    bludgeoning: "#f0e0c0" };
  const DEFAULTS = { speed: 1, moves: "on", attacks: "on", numbers: "on", turns: "on", camera: "follow", dice: "on", shake: "on",
    sync: "on", tokens: "art", ambient: "none", intensity: 0.6 };
  const reduceQuery = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : { matches: false };

  let S = null, app = null, lastSeq = null, queue = [], playing = false, waiters = [], skipping = false, gradCache = {};
  const offsets = {};                       // token id -> {dx, dy}: where an animation left a token (until the next commit)

  // ------------------------------------------------------------ settings: the DM's, softened by the viewer's own choice
  const pref = () => { try { return localStorage.getItem("fxpref") || (reduceQuery.matches ? "reduced" : "dm"); } catch { return "dm"; } };
  function settings() {
    const a = { ...DEFAULTS, ...((S && S.view && S.view.anim) || {}) };
    const p = pref();
    if (p === "off") Object.assign(a, { moves: "off", attacks: "off", numbers: "off", turns: "off", dice: "off", shake: "off", ambient: "none" });
    if (p === "reduced") Object.assign(a, { shake: "off", ambient: "none", speed: Math.max(1.6, +a.speed || 1) });
    a.speed = Math.max(0.25, Math.min(4, +a.speed || 1));
    return a;
  }
  const on = (k) => settings()[k] !== "off" && settings()[k] !== "none";
  const ms = (t) => skipping ? 0 : t / settings().speed;
  const wait = (t) => new Promise(r => setTimeout(r, ms(t)));

  // ------------------------------------------------------------ geometry on the map
  const svgEl = () => $("#map svg");
  const cell = () => +(svgEl()?.dataset.cell || 32);
  function layer() {
    let l = $("#fxlayer");
    const s = svgEl();
    if (!l) {
      l = document.createElementNS(NS, "svg");
      l.id = "fxlayer";
      l.innerHTML = `<defs><filter id="fxglow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3.5" result="b"/>
        <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <filter id="fxsoft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6"/></filter></defs>`;
      $("#mapwrap").appendChild(l);
    }
    if (s) { l.setAttribute("width", s.width.baseVal.value); l.setAttribute("height", s.height.baseVal.value);
      l.setAttribute("viewBox", s.getAttribute("viewBox")); }
    return l;
  }
  function mk(tag, attrs = {}, parent) {
    const el = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    (parent || layer()).appendChild(el);
    return el;
  }
  function grad(color) {
    if (gradCache[color] && document.getElementById(gradCache[color])) return gradCache[color];
    const id = "fxg" + Object.keys(gradCache).length + Math.random().toString(36).slice(2, 6);
    const g = mk("radialGradient", { id }, $("#fxlayer defs"));
    g.innerHTML = `<stop offset="0" stop-color="#fff" stop-opacity=".95"/><stop offset=".35" stop-color="${color}" stop-opacity=".85"/>
      <stop offset="1" stop-color="${color}" stop-opacity="0"/>`;
    return (gradCache[color] = id);
  }
  const tok = (id) => id ? document.querySelector(`#map .token[data-id="${CSS.escape(id)}"]`) : null;
  function base(t) {                          // a token's resting centre (from the renderer, or measured)
    if (t.dataset.cx === undefined) {
      const b = t.getBBox(); t.dataset.cx = b.x + b.width / 2; t.dataset.cy = b.y + b.height / 2; t.dataset.r = Math.min(b.width, b.height) / 2;
    }
    return { x: +t.dataset.cx, y: +t.dataset.cy, r: +t.dataset.r || cell() / 2 };
  }
  function center(id) {
    const t = tok(id); if (!t) return null;
    const o = offsets[id] || { dx: 0, dy: 0 }, b = base(t);
    return { x: b.x + o.dx, y: b.y + o.dy, r: b.r };
  }
  function point(p) {
    if (!p) return null;
    if (Array.isArray(p)) return { x: (p[0] + .5) * cell(), y: (p[1] + .5) * cell(), r: cell() / 2 };
    return center(p.id);
  }
  const dist = (a, b) => Math.hypot(b.x - a.x, b.y - a.y);
  function anim(el, frames, opt) {
    if (!el) return Promise.resolve();
    const d = ms(opt.duration), delay = opt.delay || 0;
    try {
      return el.animate(frames, { fill: "forwards", ...opt, delay: Number.isFinite(delay) ? delay : 0, duration: Number.isFinite(d) ? Math.max(1, d) : 1 }).finished.catch(() => {});
    } catch (e) { console.warn("fx: skipped an animation", e); return Promise.resolve(); }
  }
  const place = (id) => { const o = offsets[id] || { dx: 0, dy: 0 }; return `translate(${o.dx}px, ${o.dy}px)`; };
  function setOffset(id, dx, dy) {
    offsets[id] = { dx, dy };
    const t = tok(id); if (!t) return;
    t.getAnimations().forEach(a => a.cancel());
    t.style.transform = `translate(${dx}px, ${dy}px)`;
  }
  const colorOf = (c) => c.color || DTYPE[c.dtype] || (c.spell ? "#c8a8ff" : "#fff");

  // ------------------------------------------------------------ primitives (map coordinates)
  async function burst(p, color, radius, dur = 650) {
    const g = mk("g", { "pointer-events": "none" });
    const c = mk("circle", { cx: p.x, cy: p.y, r: radius, fill: `url(#${grad(color)})` }, g);
    const ring = mk("circle", { cx: p.x, cy: p.y, r: radius, fill: "none", stroke: color, "stroke-width": 3, filter: "url(#fxglow)" }, g);
    [c, ring].forEach(el => { el.style.transformOrigin = `${p.x}px ${p.y}px`; el.style.transformBox = "view-box"; });
    await Promise.all([anim(c, [{ transform: "scale(.15)", opacity: 1 }, { transform: "scale(1)", opacity: .9, offset: .45 }, { transform: "scale(1.08)", opacity: 0 }], { duration: dur, easing: "ease-out" }),
      anim(ring, [{ transform: "scale(.2)", opacity: 1 }, { transform: "scale(1.15)", opacity: 0 }], { duration: dur, easing: "ease-out" })]);
    g.remove();
  }
  async function ringFx(p, color, radius, dur = 900) {
    const r = mk("circle", { cx: p.x, cy: p.y, r: radius, fill: "none", stroke: color, "stroke-width": 4, filter: "url(#fxglow)" });
    r.style.transformOrigin = `${p.x}px ${p.y}px`; r.style.transformBox = "view-box";
    await anim(r, [{ transform: "scale(.1)", opacity: 1 }, { transform: "scale(1)", opacity: 0 }], { duration: dur, easing: "cubic-bezier(.2,.7,.3,1)" });
    r.remove();
  }
  // numbers and call-outs stay readable however far the map is zoomed out
  const ui = () => Math.max(1, Math.min(2.4, 1.15 / ((app && app.scale && app.scale()) || 1)));
  async function floatText(p, text, color = "#fff", size = 16, dur = 1100, weight = 800) {
    if (!p) return;
    size *= ui();
    const t = mk("text", { x: p.x, y: p.y - (p.r || 14) - 4 * ui(), "text-anchor": "middle", "font-size": size, "font-weight": weight,
      "font-family": "Georgia, serif", fill: color, stroke: "#120c08", "stroke-width": Math.max(3, size / 5), "paint-order": "stroke", "pointer-events": "none" });
    t.textContent = text;
    await anim(t, [{ transform: "translateY(6px) scale(.6)", opacity: 0 }, { transform: "translateY(-6px) scale(1.12)", opacity: 1, offset: .18 },
      { transform: "translateY(-14px) scale(1)", opacity: 1, offset: .65 }, { transform: "translateY(-30px) scale(.95)", opacity: 0 }],
      { duration: dur, easing: "ease-out" });
    t.remove();
  }
  async function projectile(a, b, color, kind = "orb") {
    const d = dist(a, b), dur = Math.min(900, Math.max(260, d * 1.4));
    const ang = Math.atan2(b.y - a.y, b.x - a.x) * 180 / Math.PI;
    const g = mk("g", { "pointer-events": "none" });
    if (kind === "arrow") {
      g.innerHTML = `<line x1="-16" y1="0" x2="8" y2="0" stroke="#e8d8b8" stroke-width="2.4"/><path d="M8,-4 L15,0 L8,4 Z" fill="#dfe6ec"/>
        <path d="M-16,0 l-5,-4 M-16,0 l-5,4 M-12,0 l-5,-4 M-12,0 l-5,4" stroke="${color === "#fff" ? "#c8402a" : color}" stroke-width="1.6"/>`;
    } else {
      g.innerHTML = `<circle r="11" fill="${color}" opacity=".35" filter="url(#fxsoft)"/><circle r="6" fill="url(#${grad(color)})" filter="url(#fxglow)"/>
        <circle r="2.5" fill="#fff"/>`;
      for (let i = 1; i <= 4; i++) trail(a, b, color, dur, i);
    }
    await anim(g, [{ transform: `translate(${a.x}px, ${a.y}px) rotate(${ang}deg)` }, { transform: `translate(${b.x}px, ${b.y}px) rotate(${ang}deg)` }],
      { duration: dur, easing: kind === "arrow" ? "cubic-bezier(.3,.1,.6,1)" : "ease-in" });
    g.remove();
  }
  function trail(a, b, color, dur, i) {
    const c = mk("circle", { r: 5 - i, fill: color, opacity: .5 - i * .1, "pointer-events": "none" });
    anim(c, [{ transform: `translate(${a.x}px, ${a.y}px)` }, { transform: `translate(${b.x}px, ${b.y}px)` }], { duration: dur, delay: ms(i * 26), easing: "ease-in" })
      .then(() => c.remove());
  }
  async function beam(a, b, color, dur = 700, jagged = false) {
    let d = `M${a.x},${a.y} L${b.x},${b.y}`;
    if (jagged) {
      const n = Math.max(4, Math.round(dist(a, b) / 18)), pts = [];
      for (let i = 0; i <= n; i++) {
        const t = i / n, j = i && i < n ? (Math.random() - .5) * 18 : 0;
        const nx = -(b.y - a.y) / (dist(a, b) || 1), ny = (b.x - a.x) / (dist(a, b) || 1);
        pts.push(`${a.x + (b.x - a.x) * t + nx * j},${a.y + (b.y - a.y) * t + ny * j}`);
      }
      d = "M" + pts.join(" L");
    }
    const g = mk("g", { "pointer-events": "none" });
    mk("path", { d, stroke: color, "stroke-width": jagged ? 5 : 9, fill: "none", "stroke-linecap": "round", opacity: .55, filter: "url(#fxsoft)" }, g);
    mk("path", { d, stroke: "#fff", "stroke-width": jagged ? 2 : 3, fill: "none", "stroke-linecap": "round", filter: "url(#fxglow)" }, g);
    await anim(g, jagged ? [{ opacity: 1 }, { opacity: .2, offset: .2 }, { opacity: 1, offset: .35 }, { opacity: .6, offset: .6 }, { opacity: 0 }]
      : [{ opacity: 0 }, { opacity: 1, offset: .15 }, { opacity: 1, offset: .7 }, { opacity: 0 }], { duration: dur });
    g.remove();
  }
  async function slash(p, color = "#fff", crit = false) {
    const r = (p.r || 16) * (crit ? 1.9 : 1.4), a = Math.random() * 60 - 30;
    const g = mk("g", { "pointer-events": "none", transform: `rotate(${a} ${p.x} ${p.y})` });
    const path = mk("path", { d: `M${p.x - r},${p.y - r * .6} Q${p.x + r * .2},${p.y - r * .1} ${p.x + r},${p.y + r * .7}`, fill: "none",
      stroke: color, "stroke-width": crit ? 6 : 4, "stroke-linecap": "round", filter: "url(#fxglow)" }, g);
    const len = r * 3;
    path.style.strokeDasharray = len; path.style.strokeDashoffset = len;
    await anim(path, [{ strokeDashoffset: len, opacity: 1 }, { strokeDashoffset: 0, opacity: 1, offset: .5 }, { strokeDashoffset: -len, opacity: 0 }], { duration: 380, easing: "ease-out" });
    g.remove();
  }
  async function sparkles(p, color, n = 8, dur = 900) {
    const all = [];
    for (let i = 0; i < n; i++) {
      const x = p.x + (Math.random() - .5) * (p.r || 16) * 2, y = p.y + (Math.random() - .3) * (p.r || 16);
      const s = mk("path", { d: `M${x},${y - 4} L${x + 1.2},${y - 1.2} L${x + 4},${y} L${x + 1.2},${y + 1.2} L${x},${y + 4} L${x - 1.2},${y + 1.2} L${x - 4},${y} L${x - 1.2},${y - 1.2} Z`,
        fill: color, filter: "url(#fxglow)", "pointer-events": "none" });
      all.push(anim(s, [{ transform: "translateY(0)", opacity: 0 }, { opacity: 1, offset: .3 }, { transform: `translateY(-${18 + Math.random() * 16}px)`, opacity: 0 }],
        { duration: dur, delay: ms(i * 40), easing: "ease-out" }).then(() => s.remove()));
    }
    await Promise.all(all);
  }
  async function smoke(p, color = "#b8b0a8", n = 6) {
    const all = [];
    for (let i = 0; i < n; i++) {
      const c = mk("circle", { cx: p.x + (Math.random() - .5) * 20, cy: p.y + (Math.random() - .5) * 14, r: 8 + Math.random() * 8, fill: color, opacity: .5, filter: "url(#fxsoft)" });
      c.style.transformOrigin = `${c.getAttribute("cx")}px ${c.getAttribute("cy")}px`; c.style.transformBox = "view-box";
      all.push(anim(c, [{ transform: "scale(.4)", opacity: .6 }, { transform: `translate(${(Math.random() - .5) * 20}px, -16px) scale(1.8)`, opacity: 0 }],
        { duration: 900, delay: ms(i * 50), easing: "ease-out" }).then(() => c.remove()));
    }
    await Promise.all(all);
  }
  async function dust(p) {
    const all = [];
    for (let i = 0; i < 4; i++) {
      const c = mk("circle", { cx: p.x, cy: p.y + (p.r || 14) * .7, r: 3, fill: "#d8ccb0", opacity: .6 });
      const dx = (i - 1.5) * 8;
      all.push(anim(c, [{ transform: "translate(0,0)", opacity: .6 }, { transform: `translate(${dx}px, -6px) scale(2)`, opacity: 0 }], { duration: 450, easing: "ease-out" }).then(() => c.remove()));
    }
    await Promise.all(all);
  }
  async function pingFx(p, color = "#6fb0ff") {
    for (let i = 0; i < 3; i++) { ringFx(p, color, (p.r || 16) * 2.2, 900); await wait(260); }
    await wait(500);
  }
  // token motions (compose with where an earlier animation left the token)
  async function shake(id, strength = 4) {
    const t = tok(id); if (!t) return;
    const o = offsets[id] || { dx: 0, dy: 0 }, f = (x, y) => ({ transform: `translate(${o.dx + x}px, ${o.dy + y}px)` });
    await anim(t, [f(0, 0), f(-strength, 1), f(strength, -1), f(-strength * .6, 0), f(strength * .4, 1), f(0, 0)], { duration: 320 });
  }
  async function flashToken(id, color) {
    const p = center(id); if (!p) return;
    const c = mk("circle", { cx: p.x, cy: p.y, r: p.r, fill: color, opacity: 0, "pointer-events": "none" });
    await anim(c, [{ opacity: .75 }, { opacity: 0 }], { duration: 420 });
    c.remove();
  }
  async function lunge(id, toward, frac = .38) {
    const t = tok(id), a = center(id); if (!t || !a || !toward) return;
    const o = offsets[id] || { dx: 0, dy: 0 };
    const dx = (toward.x - a.x) * frac, dy = (toward.y - a.y) * frac;
    await anim(t, [{ transform: `translate(${o.dx}px, ${o.dy}px)` }, { transform: `translate(${o.dx - dx * .15}px, ${o.dy - dy * .15}px)`, offset: .3 },
      { transform: `translate(${o.dx + dx}px, ${o.dy + dy}px)`, offset: .62 }], { duration: 300, easing: "ease-in" });
  }
  async function unlunge(id) {
    const t = tok(id); if (!t) return;
    await anim(t, [{ transform: place(id) }], { duration: 220, easing: "ease-out" });
  }
  async function dodge(id, from) {
    const t = tok(id), p = center(id); if (!t || !p) return;
    const o = offsets[id] || { dx: 0, dy: 0 };
    const ang = from ? Math.atan2(p.y - from.y, p.x - from.x) + Math.PI / 2 : 0, d = cell() * .28;
    await anim(t, [{ transform: `translate(${o.dx}px, ${o.dy}px)` }, { transform: `translate(${o.dx + Math.cos(ang) * d}px, ${o.dy + Math.sin(ang) * d}px)`, offset: .4 },
      { transform: `translate(${o.dx}px, ${o.dy}px)` }], { duration: 380, easing: "ease-in-out" });
  }
  async function fall(id) {
    const t = tok(id), p = center(id); if (!t || !p) return;
    const o = offsets[id] || { dx: 0, dy: 0 };
    t.style.transformBox = "view-box"; t.style.transformOrigin = `${base(t).x}px ${base(t).y}px`;
    smoke(p, "#6a5a5a", 5);
    await anim(t, [{ transform: `translate(${o.dx}px, ${o.dy}px) rotate(0deg)`, opacity: 1 },
      { transform: `translate(${o.dx}px, ${o.dy + 4}px) rotate(-80deg) scale(.8)`, opacity: .35 }], { duration: 650, easing: "cubic-bezier(.5,0,.8,.6)" });
  }
  function setBar(id, frac) {
    const t = tok(id); const bar = t && t.querySelector(".hpbar"); if (!bar) return;
    const w = +bar.dataset.w * Math.max(0, Math.min(1, frac));
    bar.setAttribute("fill", frac > .5 ? "#3cb371" : frac > .25 ? "#e0a030" : "#d9443b");
    anim(bar, [{ width: bar.getAttribute("width") + "px" }, { width: w + "px" }], { duration: 400, easing: "ease-out" }).then(() => bar.setAttribute("width", w));
  }

  // ------------------------------------------------------------ screen-level effects
  const screen = () => $("#fxscreen");
  async function banner(html, cls = "", dur = 1500) {
    if (skipping) return;
    const b = document.createElement("div");
    b.className = "fxbanner " + cls; b.innerHTML = html;
    screen().appendChild(b);
    await anim(b, [{ transform: "translate(-50%, -14px) scale(.96)", opacity: 0 }, { transform: "translate(-50%, 0) scale(1)", opacity: 1, offset: .14 },
      { transform: "translate(-50%, 0) scale(1)", opacity: 1, offset: .8 }, { transform: "translate(-50%, 8px) scale(.98)", opacity: 0 }], { duration: dur, easing: "ease-out" });
    b.remove();
  }
  async function screenFlash(color = "#fff", strength = .55, dur = 380) {
    const f = document.createElement("div");
    f.className = "fxflash"; f.style.background = color;
    screen().appendChild(f);
    await anim(f, [{ opacity: strength }, { opacity: 0 }], { duration: dur, easing: "ease-out" });
    f.remove();
  }
  async function screenShake(strength = 6) {
    if (!on("shake")) return;
    const v = $("#viewport");
    const k = (x, y) => ({ transform: `translate(${x}px, ${y}px)` });
    await anim(v, [k(0, 0), k(-strength, 2), k(strength, -2), k(-strength * .6, 1), k(strength * .5, -1), k(0, 0)], { duration: 360, fill: "none" });
  }

  // ------------------------------------------------------------ dice
  async function dice(rolls) {
    if (!on("dice") || !rolls.length || skipping) return;
    const d = document.createElement("div");
    d.className = "fxdice";
    d.innerHTML = rolls.slice(-4).map(r => `<div class="fxdie ${r.nat === 20 ? "n20" : r.nat === 1 ? "n1" : ""}">
      <div class="shape"><svg viewBox="0 0 100 100"><polygon points="50,4 93,28 93,72 50,96 7,72 7,28"/><polygon class="inner" points="50,22 76,66 24,66"/></svg>
      <b>${r.nat}</b></div><div class="lbl"><span>${app.esc(app.nameOf(r.who))}</span>${app.esc(r.purpose || "")}<i>${r.total}</i></div></div>`).join("");
    screen().appendChild(d);
    d.querySelectorAll(".shape").forEach((s, i) => s.animate([{ transform: "rotate(-420deg) scale(.3)", opacity: 0 }, { transform: "rotate(0) scale(1)", opacity: 1 }],
      { duration: ms(620), delay: ms(i * 90), easing: "cubic-bezier(.2,.8,.3,1)", fill: "both" }));
    await wait(1050 + Math.min(3, rolls.length - 1) * 120);
    await anim(d, [{ opacity: 1 }, { opacity: 0 }], { duration: 220 });
    d.remove();
  }

  // ------------------------------------------------------------ cue handlers
  const nameOf = (id) => app ? app.nameOf(id) : id;
  async function camera(points, force) {
    if (!app || !points.filter(Boolean).length) return;
    if (settings().camera === "off" && !force) return;
    await app.camera(points.filter(Boolean), force, ms(420));
  }
  async function doMove(c) {
    const t = tok(c.who); if (!t) return;
    const bb = base(t), n = Math.max(1, Math.round(bb.r * 2 / cell())) || 1;
    const base_ = { x: bb.x, y: bb.y };
    const pts = c.path.map(([x, y]) => ({ x: x * cell() + n * cell() / 2, y: y * cell() + n * cell() / 2 }));
    const o = offsets[c.who] || { dx: 0, dy: 0 };
    const start = { x: base_.x + o.dx, y: base_.y + o.dy };
    if (c.placed || c.forced) {                       // teleport / shove: vanish, reappear
      const end = pts[pts.length - 1];
      if (Math.abs(end.x - start.x) < 1 && Math.abs(end.y - start.y) < 1) return;
      smoke(start, c.forced ? "#d8ccb0" : "#b8a8e0", 4);
      await anim(t, [{ transform: `translate(${o.dx}px, ${o.dy}px)`, opacity: 1 }, { transform: `translate(${o.dx}px, ${o.dy}px)`, opacity: 0 }], { duration: 220 });
      setOffset(c.who, end.x - base_.x, end.y - base_.y);
      await camera([end]);
      await anim(t, [{ opacity: 0 }, { opacity: 1 }], { duration: 260 });
      ringFx({ ...end, r: +t.dataset.r }, "#e8d8a8", +t.dataset.r * 1.8, 520);
      return;
    }
    const all = [start, ...pts.filter((p, i) => i > 0 || Math.hypot(p.x - start.x, p.y - start.y) > 1)];
    if (all.length < 2) return;
    let total = 0; const seg = [0];
    for (let i = 1; i < all.length; i++) { total += dist(all[i - 1], all[i]); seg.push(total); }
    if (total < 1) return;
    await camera([all[0], all[all.length - 1]]);
    const frames = all.map((p, i) => ({ transform: `translate(${p.x - base_.x}px, ${p.y - base_.y}px)`, offset: seg[i] / total }));
    const dur = Math.min(2400, Math.max(320, (all.length - 1) * 170));
    dust(all[0]);
    await anim(t, frames, { duration: dur, easing: "ease-in-out" });
    const end = all[all.length - 1];
    offsets[c.who] = { dx: end.x - base_.x, dy: end.y - base_.y };
    t.getAnimations().forEach(a => a.cancel()); t.style.transform = `translate(${offsets[c.who].dx}px, ${offsets[c.who].dy}px)`;
    dust(end);
  }
  async function doAttack(c, next) {
    const a = center(c.who), b = center(c.target); if (!b) return;
    await camera([a, b]);
    const color = colorOf(c);
    const ranged = c.ranged || (a && dist(a, b) > cell() * 1.6);
    if (c.spell && a) {
      await ringFx(a, color, (a.r || 16) * 1.6, 420);
      await (c.dtype === "lightning" ? beam(a, b, color, 380, true) : projectile(a, b, color, "orb"));
    } else if (ranged && a) {
      await projectile(a, b, color, "arrow");
    } else if (a) {
      await lunge(c.who, b);
    }
    if (c.hit) {
      const dmg = next && next.k === "damage" && next.who === c.target ? next : null;
      const impact = [shake(c.target, c.crit ? 7 : 4), flashToken(c.target, c.crit ? "#ffd34d" : "#ff3b30")];
      impact.push(ranged || c.spell ? burst(b, c.crit ? "#ffd34d" : color, (b.r || 16) * (c.crit ? 2.4 : 1.5), 520) : slash(b, c.crit ? "#ffd34d" : "#fff", c.crit));
      if (c.crit) { impact.push(screenShake(7), screenFlash("#ffd34d", .25, 300)); floatText({ ...b, y: b.y - 14 }, "CRITICAL!", "#ffd34d", 14, 1200); }
      if (a && !ranged && !c.spell) impact.push(unlunge(c.who));
      await Promise.all(impact);
      if (dmg) { dmg._done = true; await doDamage(dmg); }
    } else {
      const miss = [dodge(c.target, a), on("numbers") ? floatText(b, c.nat === 1 ? "Fumble!" : "Miss", "#c8c0b4", 14, 900, 700) : null];
      if (a && !ranged && !c.spell) miss.push(unlunge(c.who));
      await Promise.all(miss);
    }
  }
  async function doDamage(c) {
    const p = center(c.who); if (!p) return;
    const color = c.dtype && DTYPE[c.dtype] && !["slashing", "piercing", "bludgeoning"].includes(c.dtype) ? DTYPE[c.dtype] : "#ff5a4a";
    if (on("numbers") && c.amount) floatText(p, `−${c.amount}`, color, c.crit ? 22 : 18, 1100);   // drifts on while the next cue starts
    if (c.hp !== undefined && c.hp !== null && c.hp_max) setBar(c.who, c.hp / c.hp_max);
    if (!c._done) { await camera([p]); await Promise.all([shake(c.who, 4), flashToken(c.who, "#ff3b30")]); }
    await wait(c.dead || c.down ? 150 : 420);
    if (c.dead || c.down) {
      await fall(c.who);
      if (on("numbers")) floatText(p, c.dead ? "Defeated" : "Down!", c.dead ? "#ff8a7a" : "#ffb070", 13, 1000, 700);
    }
  }
  async function doHeal(c) {
    const p = center(c.who); if (!p) return;
    await camera([p]);
    if (c.hp !== undefined && c.hp !== null && c.hp_max) setBar(c.who, c.hp / c.hp_max);
    await Promise.all([sparkles(p, c.temp ? "#8ac8ff" : "#7af0a0", 9), flashToken(c.who, c.temp ? "#8ac8ff" : "#7af0a0"),
      on("numbers") ? floatText(p, c.temp ? `+${c.temp} temp` : `+${c.amount}`, c.temp ? "#9ad0ff" : "#7af0a0", 17, 1100) : null]);
  }
  async function doCondition(c) {
    const p = center(c.who); if (!p || !on("numbers")) return;
    const label = c.cond.charAt(0).toUpperCase() + c.cond.slice(1);
    await floatText(p, c.on ? label : `${label} ends`, c.on ? "#ffd899" : "#b8b0a4", c.on ? 13 : 11, c.on ? 1000 : 800, c.on ? 800 : 600);
  }
  async function doSpell(c) {
    const a = center(c.who), color = colorOf(c);
    const ts = (c.targets || []).map(center).filter(Boolean);
    await camera([a, ...ts]);
    if (a) await ringFx(a, color, (a.r || 16) * 2, 500);
    if (c.fxkind === "save" || c.fxkind === "damage") {
      if (!ts.length) return;
      const cx = ts.reduce((s, p) => s + p.x, 0) / ts.length, cy = ts.reduce((s, p) => s + p.y, 0) / ts.length;
      const r = Math.max(cell() * 1.2, ...ts.map(p => dist(p, { x: cx, y: cy }) + (p.r || 16) * 1.3));
      if (a && dist(a, { x: cx, y: cy }) > cell() * 1.5) await projectile(a, { x: cx, y: cy }, color, "orb");
      await Promise.all([burst({ x: cx, y: cy }, color, r, 750), c.dtype === "thunder" || c.dtype === "fire" ? screenShake(4) : null]);
    } else if (c.fxkind === "heal") {
      await Promise.all(ts.map(p => sparkles(p, "#ffe690", 7)));
    } else if (c.fxkind === "darts" && a) {
      await Promise.all(ts.map((p, i) => wait(i * 90).then(() => projectile(a, p, "#c8b0ff", "orb"))));
    } else if (!c.fxkind || c.fxkind === "none") {
      await Promise.all(ts.map(p => sparkles(p, color, 6)));
    }
  }
  async function doSave(c) {
    const p = center(c.who); if (!p || !on("numbers")) return;
    if (c.death) {
      const txt = { success: "✓ death save", fail: "✗ death save", stable: "Stable", dead: "Died" }[c.death] || "";
      await floatText(p, txt, c.death === "success" || c.death === "stable" ? "#7af0a0" : "#ff7a6a", 13, 1000, 700);
      if (c.death === "dead") await fall(c.who);
      return;
    }
    await floatText(p, c.success ? `${(c.save || "").toUpperCase()} save ✓` : `${(c.save || "").toUpperCase()} save ✗`, c.success ? "#9ae8b0" : "#ffa090", 12, 850, 700);
  }
  function faceUrl(id) { return app ? app.faceUrl(id) : `/api/token/${encodeURIComponent(id)}.svg`; }
  async function doTurn(c, roundCue) {
    const p = center(c.who);
    const jobs = [camera([p])];
    if (on("turns")) {
      const who = app.entity(c.who) || {};
      const side = who.kind === "pc" ? "pc" : who.side || "enemy";
      jobs.push(banner(`<img src="${faceUrl(c.who)}" alt=""><div><small>${roundCue ? `Round ${roundCue.round}` : `Round ${c.round || ""}`}</small>
        <b>${app.esc(nameOf(c.who))}</b><span>${side === "pc" ? "Your turn" : side === "enemy" ? "Enemy turn" : "Turn"}</span></div>`, "turn " + side, 1500));
    }
    if (p) jobs.push(ringFx(p, "#ffd34d", (p.r || 16) * 2.2, 800));
    await Promise.all(jobs);
  }
  async function doCombat(c) {
    if (!on("turns")) return;
    if (c.phase === "start") {
      await Promise.all([screenFlash("#8a1010", .35, 600), screenShake(3),
        banner(`<div class="big">⚔</div><div><small>Combat</small><b>Roll for Initiative!</b></div>`, "combat", 1700)]);
    } else if (c.phase === "end") {
      await banner(`<div class="big">🏁</div><div><small>The dust settles</small><b>Combat ends</b></div>`, "combat end", 1600);
    }
  }
  async function doFx(c) {
    if (c.map && app.viewMap() && c.map !== app.viewMap() && !["banner", "flash", "shake"].includes(c.fx)) return;
    const color = c.color || "#ffd98a";
    const at = point(c.at), from = point(c.from), to = point(c.to);
    const radius = c.radius ? c.radius / 5 * cell() : cell() * 1.5;
    if (at || from) await camera([at, from, to], c.fx === "focus");
    switch (c.fx) {
      case "burst": return Promise.all([burst(at, color, radius, 800), radius > cell() * 3 ? screenShake(4) : null]);
      case "ring": return ringFx(at, color, radius, 1000);
      case "beam": return beam(from, to, color, 900);
      case "bolt": return Promise.all([beam(from, to, color, 500, true), screenFlash(color, .2, 250)]);
      case "projectile": return projectile(from, to, color, "orb").then(() => burst(to, color, cell() * .9, 450));
      case "flash": return screenFlash(color, .6, 500);
      case "shake": return screenShake(9);
      case "banner": return banner(`<div><b>${app.esc(c.label || "")}</b></div>`, "dm", 2400);
      case "focus": return c.fit ? app.fit(true) : wait(300);
      case "ping": return pingFx(at, c.color || "#6fb0ff");
      case "float": return floatText(at, c.label || "", color === "#ffd98a" ? "#fff" : color, 15, 1500);
      case "sparkle": return sparkles(at, color, 12, 1100);
      case "smoke": return smoke(at, c.color || "#9a948a", 9);
    }
  }

  // ------------------------------------------------------------ the queue
  function collect(st) {
    const cues = st.cues || [], rolls = (st.rolls || []).filter(r => r.seq);
    const maxSeq = Math.max(0, ...cues.map(c => c.seq || 0), ...rolls.map(r => r.seq || 0));
    if (lastSeq === null) { lastSeq = maxSeq; return []; }        // first load: nothing replays
    const fresh = cues.filter(c => c.seq > lastSeq).map(c => ({ ...c }));
    const byRoll = {}; rolls.forEach(r => byRoll[r.id] = r);
    const used = new Set(fresh.map(c => c.roll).filter(Boolean));
    fresh.forEach(c => { if (c.roll && byRoll[c.roll] && byRoll[c.roll].nat !== null && byRoll[c.roll].nat !== undefined) c.die = byRoll[c.roll]; });
    const loose = rolls.filter(r => r.seq > lastSeq && !used.has(r.id) && r.nat !== null && r.nat !== undefined)
      .map(r => ({ k: "die", seq: r.seq, rolls: [r] }));
    lastSeq = Math.max(lastSeq, maxSeq);
    const out = [...fresh, ...loose].sort((a, b) => a.seq - b.seq);
    const start = out.findIndex(c => c.k === "combat" && c.phase === "start");   // the engine rolls initiative before it
    if (start > 0) out.unshift(...out.splice(start, 1));                         // announces the fight; the table shows it first
    const merged = [];                                              // consecutive loose dice show together
    for (const c of out) { const p = merged[merged.length - 1]; if (c.k === "die" && p && p.k === "die") p.rolls.push(...c.rolls); else merged.push(c); }
    return merged;
  }
  function relevant(c) {
    const s = settings();
    if (c.k === "move") return s.moves !== "off";
    if (["attack", "damage", "heal", "condition", "spell", "roll"].includes(c.k)) return s.attacks !== "off" || (c.die && s.dice !== "off");
    if (c.k === "turn") return s.turns !== "off" || s.camera !== "off";
    if (c.k === "combat") return s.turns !== "off";
    if (c.k === "die") return s.dice !== "off";
    if (c.k === "speech" || c.k === "narration") return !!window.TableStory;   // the story plays in order with the action
    return c.k === "fx";
  }
  async function handle(c, i, list) {
    const s = settings();
    if (c.die && s.dice !== "off" && c.k !== "roll") await dice([c.die]);
    switch (c.k) {
      case "move": return s.moves !== "off" && doMove(c);
      case "attack": return s.attacks !== "off" && doAttack(c, list[i + 1]);
      case "damage": return s.attacks !== "off" && !c._done && doDamage(c);
      case "heal": return s.attacks !== "off" && doHeal(c);
      case "condition": return s.attacks !== "off" && doCondition(c);
      case "spell": return s.attacks !== "off" && doSpell(c);
      case "roll": if (c.die && s.dice !== "off") await dice([c.die]); return s.attacks !== "off" && doSave(c);
      case "turn": return doTurn(c, list[i - 1] && list[i - 1].k === "combat" && list[i - 1].phase === "round" ? list[i - 1] : null);
      case "combat": return doCombat(c);
      case "die": return dice(c.rolls);
      case "fx": return doFx(c);
      case "speech": case "narration": return wait(window.TableStory.live(c));
    }
  }
  async function loop() {
    if (playing) return;
    playing = true;
    document.body.classList.add("fx-playing");
    try {
      while (queue.length) {
        if (document.hidden || queue.length > 60) skipping = true;
        const list = queue.splice(0, queue.length);
        for (let i = 0; i < list.length; i++) {
          const c = list[i];
          try {
            if (c.k === "move" && c.group) {             // a party moving together moves together
              const grp = [c]; while (list[i + 1] && list[i + 1].k === "move" && list[i + 1].group === c.group) grp.push(list[++i]);
              await Promise.all(grp.map(doMove));
            } else if ((c.k === "roll" || c.k === "condition") && !c.die) { // quick call-outs overlap a little
              handle(c, i, list); await wait(260);
            } else await handle(c, i, list);
          } catch (e) { console.warn("fx cue failed", c, e); }
        }
      }
    } finally {
      playing = false; skipping = false;
      document.body.classList.remove("fx-playing");
      const w = waiters.splice(0); w.forEach(r => r());
    }
  }

  // ------------------------------------------------------------ ambient weather (screen space, canvas)
  let amb = { kind: "none", raf: 0, parts: [], canvas: null, t: 0, flash: 0 };
  function ambient(kind, intensity) {
    const cv = $("#ambient"); if (!cv) return;
    amb.canvas = cv;
    if (kind === amb.kind && intensity === amb.intensity) return;
    amb.kind = kind; amb.intensity = intensity; amb.parts = [];
    cv.className = "amb-" + kind;
    cancelAnimationFrame(amb.raf);
    if (kind === "none") { cv.getContext("2d").clearRect(0, 0, cv.width, cv.height); return; }
    const step = (ts) => {
      const dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
      if (cv.width !== Math.round(w * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
      const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
      const want = Math.round({ rain: 180, storm: 260, snow: 110, fog: 9, embers: 60, ash: 70, motes: 45 }[kind] * (amb.intensity || .6) * Math.min(1.5, w * h / 900000));
      while (amb.parts.length < want) amb.parts.push(spawn(kind, w, h, true));
      if (amb.parts.length > want) amb.parts.length = want;
      for (const p of amb.parts) { move(kind, p, w, h); drawPart(ctx, kind, p); }
      if (kind === "storm") {
        if (Math.random() < .0025) amb.flash = 1;
        if (amb.flash > 0) { ctx.fillStyle = `rgba(220,230,255,${amb.flash * .35})`; ctx.fillRect(0, 0, w, h); amb.flash -= .06; }
      }
      amb.raf = document.hidden ? setTimeout(() => requestAnimationFrame(step), 500) : requestAnimationFrame(step);
    };
    amb.raf = requestAnimationFrame(step);
  }
  function spawn(kind, w, h, anywhere) {
    const r = Math.random;
    const y0 = anywhere ? r() * h : -20;
    if (kind === "rain" || kind === "storm") return { x: r() * (w + 200) - 100, y: y0, v: 9 + r() * 6, l: 10 + r() * 14, a: .15 + r() * .25 };
    if (kind === "snow") return { x: r() * w, y: y0, v: .4 + r() * 1, s: 1 + r() * 2.6, ph: r() * 6, a: .4 + r() * .5 };
    if (kind === "fog") return { x: r() * w, y: r() * h, v: .15 + r() * .25, s: 120 + r() * 200, a: .05 + r() * .06 };
    if (kind === "embers") return { x: r() * w, y: anywhere ? r() * h : h + 10, v: .6 + r() * 1.4, s: 1 + r() * 2, ph: r() * 6, a: .5 + r() * .5, life: 1 };
    if (kind === "ash") return { x: r() * w, y: y0, v: .3 + r() * .7, s: 1 + r() * 2.2, ph: r() * 6, a: .3 + r() * .4 };
    return { x: r() * w, y: r() * h, v: .1 + r() * .3, s: 1 + r() * 2, ph: r() * 6, a: .2 + r() * .5 };
  }
  function move(kind, p, w, h) {
    const sp = Math.min(2, settings().speed);
    if (kind === "rain" || kind === "storm") { p.y += p.v * sp; p.x += p.v * .25 * sp; if (p.y > h + 20) Object.assign(p, spawn(kind, w, h)); }
    else if (kind === "snow" || kind === "ash") { p.y += p.v; p.ph += .02; p.x += Math.sin(p.ph) * .5; if (p.y > h + 10) Object.assign(p, spawn(kind, w, h)); }
    else if (kind === "fog") { p.x += p.v; if (p.x - p.s > w) { p.x = -p.s; p.y = Math.random() * h; } }
    else if (kind === "embers") { p.y -= p.v; p.ph += .05; p.x += Math.sin(p.ph) * .6; p.a -= .002; if (p.y < -10 || p.a <= 0) Object.assign(p, spawn(kind, w, h)); }
    else { p.ph += .01; p.x += Math.cos(p.ph) * p.v; p.y += Math.sin(p.ph * 1.3) * p.v; if (p.x < -5 || p.x > w + 5 || p.y < -5 || p.y > h + 5) Object.assign(p, spawn(kind, w, h, true)); }
  }
  function drawPart(ctx, kind, p) {
    if (kind === "rain" || kind === "storm") { ctx.strokeStyle = `rgba(190,210,240,${p.a})`; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x - p.l * .25, p.y - p.l); ctx.stroke(); }
    else if (kind === "fog") { const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.s); g.addColorStop(0, `rgba(210,215,220,${p.a})`); g.addColorStop(1, "rgba(210,215,220,0)"); ctx.fillStyle = g; ctx.beginPath(); ctx.arc(p.x, p.y, p.s, 0, 7); ctx.fill(); }
    else {
      const col = kind === "embers" ? `rgba(255,${140 + Math.round(Math.sin(p.ph) * 40)},60,${Math.max(0, p.a)})` : kind === "snow" ? `rgba(245,248,255,${p.a})`
        : kind === "ash" ? `rgba(160,150,140,${p.a})` : `rgba(255,236,170,${p.a * (.6 + Math.sin(p.ph * 3) * .4)})`;
      ctx.fillStyle = col; ctx.beginPath(); ctx.arc(p.x, p.y, p.s, 0, 7); ctx.fill();
      if (kind === "embers" || kind === "motes") { ctx.fillStyle = col.replace(/[\d.]+\)$/, "0.15)"); ctx.beginPath(); ctx.arc(p.x, p.y, p.s * 3, 0, 7); ctx.fill(); }
    }
  }

  // ------------------------------------------------------------ public API
  window.TableFX = {
    init(api) { app = api; },
    setState(st) { S = st; const a = settings(); ambient(a.ambient || "none", +a.intensity || .6); },
    settings, pref,
    setPref(p) { try { localStorage.setItem("fxpref", p); } catch {} const a = settings(); ambient(a.ambient || "none", +a.intensity || .6); },
    collect,
    // play new cues; resolves once everything queued so far has played
    play(cues) {
      const list = cues.filter(relevant);
      if (!list.length) return playing ? new Promise(r => waiters.push(r)) : Promise.resolve();
      queue.push(...list);
      const p = new Promise(r => waiters.push(r));
      loop();
      return p;
    },
    get playing() { return playing; },
    skip() { skipping = true; },
    // the app swapped in a new map: every token is where the state says, so animation offsets are spent
    committed() { for (const k in offsets) delete offsets[k]; layer(); },
    reset() { lastSeq = null; },
  };
})();
