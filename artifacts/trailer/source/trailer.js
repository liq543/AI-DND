// Trailer compositor: everything is a pure function of time T (seconds). window.renderFrame(T) draws one frame.
(() => {
  const W = 1920, H = 1080, FPS = 30;
  const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
  const post = document.getElementById('post'), px = post.getContext('2d');
  const ov = document.getElementById('ov');

  // ------------------------------------------------------------------ math
  const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
  const lerp = (a, b, t) => a + (b - a) * t;
  const inv = (a, b, x) => clamp((x - a) / (b - a));
  const E = {
    lin: t => t, inOut: t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2,
    out: t => 1 - Math.pow(1 - t, 3), in: t => t * t * t, expo: t => t >= 1 ? 1 : 1 - Math.pow(2, -10 * t),
    back: t => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); },
    sine: t => -(Math.cos(Math.PI * t) - 1) / 2,
  };
  // opacity envelope: fade in over fi after a, fade out over fo before b
  const env = (T, a, b, fi = .35, fo = .35) => T < a || T > b ? 0 : Math.min(fi ? inv(a, a + fi, T) : 1, fo ? inv(b, b - fo, T) : 1);
  function hash(n) { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); }

  // ------------------------------------------------------------------ images
  const cache = new Map();
  function img(src) {
    if (!cache.has(src)) {
      const im = new Image(); im.src = src;
      cache.set(src, im.decode().then(() => im).catch(() => { console.warn('missing', src); return null; }));
    }
    return cache.get(src);
  }
  const ready = new Map();
  async function need(list) { for (const s of list) { if (!ready.has(s)) ready.set(s, await img(s)); } }
  const I = s => ready.get(s);

  // view: (fx, fy) = image point (0..1) at screen point (cx, cy); zoom = multiple of the cover scale
  function draw(src, { fx = .5, fy = .5, zoom = 1, alpha = 1, filter = 'none', cx = W / 2, cy = H / 2, crop = null, comp = 'source-over', sx = 0, sy = 0 } = {}) {
    const im = typeof src === 'string' ? I(src) : src; if (!im || alpha <= 0) return;
    let [x0, y0, w0, h0] = crop || [0, 0, im.naturalWidth, im.naturalHeight];
    const cover = Math.max(W / w0, H / h0), s = cover * zoom;
    ctx.save(); ctx.globalAlpha = clamp(alpha); ctx.filter = filter; ctx.globalCompositeOperation = comp;
    ctx.drawImage(im, x0, y0, w0, h0, cx - fx * w0 * s + sx, cy - fy * h0 * s + sy, w0 * s, h0 * s);
    ctx.restore();
  }
  const clipFrame = (name, lt) => { const c = EDL.clips[name]; return c.frames[clamp(Math.floor(lt * FPS + 1e-6), 0, c.frames.length - 1)]; };

  // ------------------------------------------------------------------ overlay elements (DOM), rebuilt lazily, hidden when unused
  const els = new Map(); let used = new Set();
  function el(id, cls, html) {
    let e = els.get(id);
    if (!e) { e = document.createElement('div'); e.className = 'el ' + (cls || ''); ov.appendChild(e); els.set(id, e); e._html = null; }
    if (html !== undefined && e._html !== html) { e.innerHTML = html; e._html = html; }
    used.add(id); e.style.display = ''; return e;
  }
  function style(e, o) { for (const k in o) e.style[k] = o[k]; return e; }
  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const typed = (s, T, a, cps) => s.slice(0, Math.max(0, Math.floor((T - a) * cps)));

  // feature callout, lower-left, wipes in
  function callout(id, T, a, b, h, s, side) {
    const o = env(T, a, b, .45, .35); if (o <= 0) return;
    const p = E.expo(inv(a, a + .7, T));
    const e = el('co-' + id, 'callout', `<div class="rule"></div><div class="h">${h}</div>${s ? `<div class="s">${s}</div>` : ''}`);
    style(e, side === 'right' ? { left: 'auto', right: '96px', textAlign: 'right', opacity: o, transform: `translateX(${(1 - p) * 60}px)` } : { opacity: o, transform: `translateX(${(1 - p) * -60}px)`, clipPath: `inset(-200px ${(1 - p) * 100}% -200px -300px)` });
  }

  // ------------------------------------------------------------------ post: embers, grain, vignette, bars, flash, leaks
  const grainTiles = [];
  for (let k = 0; k < 6; k++) {
    const c = document.createElement('canvas'); c.width = 480; c.height = 270; const g = c.getContext('2d'); const d = g.createImageData(480, 270);
    for (let i = 0; i < d.data.length; i += 4) { const v = 128 + (Math.random() - .5) * 90; d.data[i] = d.data[i + 1] = d.data[i + 2] = v; d.data[i + 3] = 255; }
    g.putImageData(d, 0, 0); grainTiles.push(c);
  }
  function embers(T, amount = 1, color = [255, 150, 70]) {
    if (amount <= 0) return;
    px.save(); px.globalCompositeOperation = 'lighter';
    const n = Math.floor(70 * amount);
    for (let i = 0; i < n; i++) {
      const life = 5 + hash(i) * 6, ph = (T + hash(i + 7) * life) % life, p = ph / life;
      const x = (hash(i + 3) * W + Math.sin((T + i) * .6 + i) * 40 + p * 120 * (hash(i + 5) - .3)) % W;
      const y = H + 20 - p * (H + 80) * (0.7 + hash(i + 9) * .6);
      const r = 1.2 + hash(i + 11) * 2.6, a = Math.sin(p * Math.PI) * (0.35 + .65 * hash(i + 13)) * Math.min(1, amount);
      const gr = px.createRadialGradient(x, y, 0, x, y, r * 4);
      gr.addColorStop(0, `rgba(${color[0]},${color[1]},${color[2]},${a})`); gr.addColorStop(1, 'rgba(0,0,0,0)');
      px.fillStyle = gr; px.beginPath(); px.arc(x, y, r * 4, 0, 7); px.fill();
    }
    px.restore();
  }
  function postfx(T, o) {
    px.clearRect(0, 0, W, H);
    if (o.leak > 0) {   // warm light leak drifting across
      px.save(); px.globalCompositeOperation = 'lighter';
      const x = W * (.15 + .7 * (.5 + .5 * Math.sin(T * .23))), y = H * (.3 + .2 * Math.sin(T * .31));
      const g = px.createRadialGradient(x, y, 0, x, y, 900); g.addColorStop(0, `rgba(255,140,60,${.22 * o.leak})`); g.addColorStop(1, 'rgba(0,0,0,0)');
      px.fillStyle = g; px.fillRect(0, 0, W, H); px.restore();
    }
    embers(T, o.embers || 0, o.emberColor);
    // vignette
    const v = o.vig ?? .55;
    if (v > 0) { const g = px.createRadialGradient(W / 2, H / 2, H * .35, W / 2, H / 2, H * 1.05); g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, `rgba(0,0,0,${v})`); px.fillStyle = g; px.fillRect(0, 0, W, H); }
    // grain
    px.save(); px.globalAlpha = o.grain ?? .06; px.globalCompositeOperation = 'overlay';
    const tile = grainTiles[Math.floor(T * 24) % grainTiles.length]; px.drawImage(tile, 0, 0, W, H); px.restore();
    // letterbox
    if (o.bars > 0) { px.fillStyle = '#000'; px.fillRect(0, 0, W, o.bars); px.fillRect(0, H - o.bars, W, o.bars); }
    if (o.flash > 0) { px.fillStyle = `rgba(255,248,235,${clamp(o.flash)})`; px.fillRect(0, 0, W, H); }
    if (o.black > 0) { px.fillStyle = `rgba(0,0,0,${clamp(o.black)})`; px.fillRect(0, 0, W, H); }
  }

  // ------------------------------------------------------------------ assets
  const A = {
    world: '../rec/hires/hollowmark.png', town: '../rec/hires/thornbury-town.png', rook: '../rec/hires/rookery.png',
    beechHi: '../rec/hires/beech-holloway.png', harrowHi: '../rec/hires/harrowgate.png', thornHi: '../rec/hires/thornbury.png', crowsHi: '../rec/hires/crowsfoot.png',
    gallowsHi: '../rec/hires/gallows-oak.png', barrowHi: '../rec/hires/barrow-gate.png',
    sheet: '../rec/static3x/sheet.png', dice: '../rec/static3x/dice.png', turns: '../rec/static3x/turns.png', log: '../rec/static3x/log.png',
    journal: '../rec/static1x/journal.png', party: '../rec/static1x/party.png',
    item: '../rec/static2/item-dagger.png', key: '../rec/static2/item-key.png', hesketh: '../rec/static2/creature-hesketh.png', writ: '../shots/t1.png', tamper: '../shots/tamper.png',
    mHarrow: '../rec/maps/map-harrowgate.png', mCrows: '../rec/maps/map-crowsfoot.png', mRook: '../rec/maps/map-rookery.png',
    kit: '../art/kit-bust.png', brakka: '../art/brakka-bust.png', corvin: '../art/corvin-bust.png', ottilie: '../art/ottilie-bust.png',
    stag: 'icons/stag-head.svg', crown: 'icons/sharp-crown.svg', d20: 'icons/dice-twenty-faces-twenty.svg',
  };
  const PANEL = [3040, 110, 800, 2050];   // the side panel in the 2x screenshots

  // ------------------------------------------------------------------ scenes
  // each: [t0, t1, needs(T) -> [srcs], render(T)]
  const S = [];
  const scene = (t0, t1, needs, render) => S.push({ t0, t1, needs, render });

  // A. COLD OPEN 0-8.1
  scene(0, 8.15, () => [A.world], T => {
    const p = E.inOut(inv(0, 8.1, T));
    const b = .30 + .12 * inv(5, 8, T);
    draw(A.world, { fx: lerp(.46, .33, p), fy: lerp(.58, .76, p), zoom: lerp(1.7, 2.9, p), filter: `brightness(${b}) saturate(.35) sepia(.45) contrast(1.1)` });
    const q1 = env(T, .8, 3.9, .8, .6), q2 = env(T, 4.3, 7.75, .8, .5);
    style(el('q1', 'quote', '<span style="opacity:.75">Two years ago,</span> they robbed the unrobbable.'), { top: '470px', opacity: q1, transform: `translateY(${(1 - q1) * 12}px)`, letterSpacing: `${.01 + .02 * inv(.8, 3.9, T)}em` });
    style(el('q2', 'quote', 'Now they want a <span class="gold" style="font-weight:600">crown</span>.'), { top: '470px', opacity: q2, transform: `translateY(${(1 - q2) * 12}px)`, fontSize: '64px' });
  });

  // B. TITLE 8-12.2
  scene(8, 12.25, () => [A.world, A.stag], T => {
    const lt = T - 8, p = E.out(inv(0, 4.2, lt));
    draw(A.world, { fx: .5, fy: .52, zoom: lerp(1.18, 1.06, p), filter: `brightness(${.42 - .1 * inv(3.6, 4.2, lt)}) saturate(.7) sepia(.25) blur(${2 * inv(3.7, 4.2, lt)}px)` });
    const ti = E.expo(inv(0, 1.1, lt)), o = env(T, 8.0, 12.2, .12, .4);
    style(el('t-kick', 'title kicker', 'The Jackdaw Saga &nbsp;·&nbsp; Chapter II'), { top: '330px', opacity: env(T, 8.45, 12.2, .6, .4) });
    style(el('t-icon', 'title', `<img src="${A.stag}" style="width:96px;height:96px;filter:sepia(1) saturate(3) hue-rotate(-12deg) brightness(.95) drop-shadow(0 0 18px rgba(255,180,80,.5))">`),
      { top: '372px', opacity: env(T, 8.25, 12.2, .5, .4), transform: `translateY(${(1 - ti) * -20}px)` });
    style(el('t-main', 'title gold', 'The Hollow Crown'), { top: '470px', font: '900 156px/1 Cinzel, serif', letterSpacing: `${.02 + .04 * (1 - ti)}em`, opacity: o,
      transform: `scale(${lerp(1.18, 1, ti)})`, filter: `blur(${(1 - ti) * 14}px) drop-shadow(0 0 30px rgba(255,170,70,.35)) drop-shadow(0 8px 20px rgba(0,0,0,.9))` });
    style(el('t-sub', 'quote', 'a campaign played at the <span class="gold" style="font-weight:600;font-style:normal;font-family:Cinzel;font-size:40px;letter-spacing:.08em">Live Table</span>'),
      { top: '660px', fontSize: '40px', opacity: env(T, 9.1, 12.2, .7, .4) });
  });

  // C1. WORLD 12-16.2
  const THORN = [37.5 / 120, 74.5 / 90];
  scene(12, 16.3, () => [A.world], T => {
    const lt = T - 12, p = E.inOut(inv(0, 4.3, lt));
    const fx = lerp(.56, THORN[0] + .04, p), fy = lerp(.40, THORN[1] - .06, p), z = lerp(2.2, 3.1, p) + 1.6 * E.in(inv(3.7, 4.3, lt));
    const o = inv(12, 12.35, T);
    draw(A.world, { fx, fy, zoom: z, alpha: o, filter: `brightness(${.92}) saturate(1.05) blur(${3 * E.in(inv(3.9, 4.3, lt))}px)` });
    // party marker pulse at Thornbury
    const s = Math.max(W / 3840, H / 2880) * z, mx = W / 2 + (THORN[0] - fx) * 3840 * s, my = H / 2 + (THORN[1] - fy) * 2880 * s;
    for (let k = 0; k < 2; k++) {
      const ph = ((T * .9 + k * .5) % 1); ctx.save(); ctx.globalAlpha = (1 - ph) * .9 * o; ctx.strokeStyle = '#ffd36b'; ctx.lineWidth = 4;
      ctx.beginPath(); ctx.arc(mx, my, 14 + ph * 60, 0, 7); ctx.stroke(); ctx.restore();
    }
    ctx.save(); ctx.globalAlpha = o; ctx.fillStyle = '#ffd36b'; ctx.shadowColor = '#ffb040'; ctx.shadowBlur = 20; ctx.beginPath(); ctx.arc(mx, my, 9, 0, 7); ctx.fill(); ctx.restore();
    callout('world', T, 12.45, 15.9, 'A whole kingdom', 'Region maps that fill in as you explore: roads, rivers, towns and ruins.');
  });

  // C2. TOWN 16-20.2
  scene(16, 20.3, () => [A.town], T => {
    const lt = T - 16, p = E.inOut(inv(0, 4.3, lt));
    const dive = 1 - E.out(inv(0, .55, lt));
    draw(A.town, { fx: lerp(.40, .52, p), fy: lerp(.56, .48, p), zoom: lerp(1.15, 1.45, p) * (1 + dive * 1.2), alpha: inv(16, 16.25, T),
      filter: `blur(${dive * 6}px) brightness(.95)` });
    callout('town', T, 16.45, 19.9, 'Towns at true scale', 'Every quarter, street and doorway, with a map for each building you walk into.');
  });

  // C3. TAVERN (live table) 20-24.2
  scene(20, 24.3, T => [clipFrame('tavern', T - 20)], T => {
    const lt = T - 20, p = E.inOut(inv(0, 4.3, lt));
    draw(clipFrame('tavern', lt), { fx: lerp(.5, .42, p), fy: lerp(.5, .40, p), zoom: lerp(1.0, 1.12, p), alpha: inv(20, 20.2, T) });
    callout('table', T, 20.4, 23.9, 'A living table', 'Maps, tokens, speech and story play out live in your browser as the DM runs the scene.');
  });

  // C4. CHAT: Claude as DM 24-28.2
  const CHAT1 = {
    you: 'Kit slides a crown across the bar. “A room, landlord. And whatever you’ve heard about the League house.”',
    cmd: '$ python -m engine contest kit deception --vs landlord-abel-fenn --vs-skill insight --passive',
    out: '⚖ Contest — Kit Corvell Deception 19 vs Landlord Abel Fenn passive Insight 10 → Kit Corvell wins.',
    dm: 'Abel Fenn’s rag stops halfway round the pot. He palms the coin, glances once at the hooded penitent by the hearth, and leans in…',
  };
  function chatPanel(id, T, a, b, rows, top = 190, left = 960) {
    const o = env(T, a, b, .35, .3); if (o <= 0) return;
    const html = `<div class="hd"><span class="dot"></span>Claude &nbsp;·&nbsp; Dungeon Master <span style="margin-left:auto;color:#7d766a">The Hollow Crown</span></div>` + rows.join('');
    const e = el(id, 'chat', html);
    style(e, { left: left + 'px', top: top + 'px', opacity: o, transform: `translateY(${(1 - E.out(inv(a, a + .5, T))) * 30}px) rotateY(-4deg)` });
    return e;
  }
  scene(24, 28.25, () => [clipFrame('tavern', 4.0)], T => {
    draw(clipFrame('tavern', 4.0), { zoom: 1.12, fx: .42, fy: .40, filter: 'blur(7px) brightness(.38) saturate(.8)' });
    const rows = [];
    const yt = typed(CHAT1.you, T, 24.3, 95);
    rows.push(`<div class="msg you"><div class="who">You · Kit</div><div class="txt">${esc(yt)}${T < 25.6 ? '<span class="cursor"></span>' : ''}</div></div>`);
    if (T > 25.7) rows.push(`<div class="term"><span class="cmd">${esc(typed(CHAT1.cmd, T, 25.7, 140))}</span>${T > 26.4 ? `\n<span class="ok">${esc(CHAT1.out)}</span>` : ''}</div>`);
    if (T > 26.85) rows.push(`<div class="msg dm"><div class="who">Dungeon Master</div><div class="txt">${esc(typed(CHAT1.dm, T, 26.85, 110))}</div></div>`);
    chatPanel('chat1', T, 24.05, 28.2, rows);
    callout('dm', T, 24.3, 28.0, 'Claude is your<br>Dungeon Master', 'It narrates, voices every NPC and runs the world.<br>The rules engine referees every roll.');
  });

  // D1. CREW 28-36.2
  const CREW = [
    { id: 'kit', name: 'Kit Corvell', line: 'Human · Rogue 6 · Thief', tag: '“the Jackdaw”', q: '“Hurry now. We are going to collect our debts.”', ac: 16, hp: 51, bg: A.beechHi, tint: '40,70,120' },
    { id: 'brakka', name: 'Brakka Holloway', line: 'Orc · Fighter 6 · Champion', tag: 'the muscle', q: '“Boss. Somebody need folding?”', ac: 19, hp: 58, bg: A.harrowHi, tint: '120,60,30' },
    { id: 'corvin', name: 'Corvin Asche', line: 'Human · Wizard 6 · Evoker', tag: 'forger & firestarter', q: '“Slow and proper. My favourite kind of theft.”', ac: 14, hp: 38, bg: A.rook, tint: '110,30,40' },
    { id: 'ottilie', name: 'Ottilie Marsh', line: 'Human · Bard 6 · Lore', tag: 'the convincer', q: '“Everyone remembers our faces, darling. It’s rather the point.”', ac: 13, hp: 39, bg: A.thornHi, tint: '90,50,120' },
  ];
  scene(28, 36.25, T => { const i = clamp(Math.floor((T - 28) / 2), 0, 3); return [CREW[i].bg, A[CREW[i].id]]; }, T => {
    const i = clamp(Math.floor((T - 28) / 2), 0, 3), c = CREW[i], lt = T - 28 - i * 2;
    const inP = E.expo(inv(0, .55, lt)), outP = E.in(inv(1.82, 2.0, lt)) * (i < 3 ? 1 : 0);
    draw(c.bg, { fx: .5 + .06 * Math.sin(i * 2), fy: .5, zoom: 1.25 + lt * .05, filter: 'blur(5px) brightness(.32) saturate(.6)', sx: (1 - inP) * 140 - outP * 160 });
    ctx.save(); ctx.globalCompositeOperation = 'soft-light'; ctx.fillStyle = `rgba(${c.tint},.7)`; ctx.fillRect(0, 0, W, H); ctx.restore();
    // slash flash between cards
    style(el('crew-hdr', 'kicker', 'Your crew'), { left: '120px', top: '92px', opacity: env(T, 28.1, 36.1, .3, .3) });
    const e = el('crew', 'card', `
      <div class="portrait" style="position:absolute;left:150px;top:250px;background-image:url(${A[c.id]})"></div>
      <div style="position:absolute;left:790px;top:300px">
        <div class="crew-line">${c.line}</div>
        <div class="crew-name gold" style="margin:18px 0 6px">${c.name}</div>
        <div style="font:italic 500 30px 'Cormorant Garamond',serif;color:#c9b58c;margin-bottom:34px">${c.tag}</div>
        <div><span class="chip"><small>AC</small>${c.ac}</span><span class="chip"><small>HP</small>${c.hp}</span><span class="chip"><small>LEVEL</small>6</span></div>
        <div class="crew-quote" style="margin-top:42px">${c.q}</div>
      </div>`);
    const portrait = e.firstElementChild, txt = e.children[1];
    style(portrait, { transform: `translateX(${(1 - inP) * -220 - outP * 300}px) rotateY(${(1 - inP) * 25 + 8}deg) scale(${1 + lt * .02})`, opacity: Math.min(inP, 1 - outP) });
    style(txt, { transform: `translateX(${(1 - inP) * 160 - outP * 200}px)`, opacity: Math.min(inP, 1 - outP) });
    const qe = txt.querySelector('.crew-quote'); qe.style.opacity = E.out(inv(.35, .9, lt)); qe.style.transform = `translateY(${(1 - E.out(inv(.35, .9, lt))) * 14}px)`;
    if (i === 3) style(e, { opacity: env(T, 28, 36.2, 0, .3) }); else style(e, { opacity: 1 });
  });

  // D2. SHEET + ITEM 36-40.2
  scene(36, 40.25, () => [A.sheet, A.item, A.rook], T => {
    const lt = T - 36, p = E.inOut(inv(0, 4.2, lt));
    draw(A.rook, { zoom: 1.3, filter: 'blur(9px) brightness(.25) saturate(.5)' });
    // sheet panel, floating
    const sh = el('sheet', 'shot', '');
    const ph = 1600 * .68;  // panel crop shown
    style(sh, { left: '170px', top: '70px', width: '560px', height: '940px', backgroundImage: `url(${A.sheet})`,
      backgroundSize: `${3840 * .7}px ${2160 * .7}px`, backgroundPosition: `${-3040 * .7}px ${-(110 + lerp(0, 700, p)) * .7}px`,
      opacity: env(T, 36, 40.2, .3, .3), transform: `rotateY(${lerp(14, 6, p)}deg) translateZ(${lerp(-60, 0, E.out(inv(0, .6, lt)))}px)` });
    // item card
    const io = env(T, 37.2, 40.2, .3, .3), ip = E.back(inv(37.2, 37.85, T));
    const it = el('itemc', 'shot', '');
    style(it, { left: '840px', top: '70px', width: `${620 * 1.08}px`, height: `${644 * 1.08}px`, backgroundImage: `url(${A.item})`,
      backgroundSize: `${1920 * 1.08}px ${1080 * 1.08}px`, backgroundPosition: `${-650 * 1.08}px ${-218 * 1.08}px`, opacity: io,
      transform: `scale(${lerp(.85, 1, ip)}) rotateY(${lerp(-18, -7, p)}deg)` });
    callout('sheet', T, 36.3, 39.9, 'Real character sheets', 'Spell slots, magic items, attunement and XP,<br>tracked by the engine.', 'right');
  });

  // D3. RULES GAG 40-44.2
  const CHAT2 = {
    you: 'Kit shoots the sergeant through the hedge.',
    cmd: '$ python -m engine attack kit sergeant-dorran-lerner shortbow --sneak',
    bad: '✖ RULE: Sergeant Dorran Lerner has Total Cover from Kit Corvell — it can’t be targeted directly.',
    dim: '  (nothing was changed)',
    dm: 'Nice try. The hedge has him covered. Step out onto the road and you’ll have your shot.',
  };
  scene(40, 44.25, () => [clipFrame('kit', 0)], T => {
    const shake = T > 41.55 && T < 41.9 ? Math.sin(T * 120) * 9 * (1 - inv(41.55, 41.9, T)) : 0;
    draw(clipFrame('kit', 0), { zoom: 1.15, fx: .4, fy: .5, filter: `blur(6px) brightness(${T > 41.55 && T < 41.75 ? .55 : .36}) saturate(${T > 41.55 && T < 41.8 ? 1.6 : .8})` });
    if (T > 41.55 && T < 41.85) { ctx.save(); ctx.globalAlpha = .18 * (1 - inv(41.55, 41.85, T)); ctx.fillStyle = '#ff2020'; ctx.fillRect(0, 0, W, H); ctx.restore(); }
    const rows = [];
    rows.push(`<div class="msg you"><div class="who">You · Kit</div><div class="txt">${esc(typed(CHAT2.you, T, 40.25, 70))}${T < 41 ? '<span class="cursor"></span>' : ''}</div></div>`);
    if (T > 40.95) rows.push(`<div class="term"><span class="cmd">${esc(typed(CHAT2.cmd, T, 40.95, 160))}</span>${T > 41.55 ? `\n<span class="bad">${esc(CHAT2.bad)}</span>\n<span class="dim">${CHAT2.dim}</span>` : ''}</div>`);
    if (T > 42.25) rows.push(`<div class="msg dm"><div class="who">Dungeon Master</div><div class="txt">${esc(typed(CHAT2.dm, T, 42.25, 80))}</div></div>`);
    const e = chatPanel('chat2', T, 40.05, 44.2, rows, 230);
    if (e) e.style.transform += ` translateX(${shake}px)`;
    callout('rules', T, 40.3, 44.0, 'A real rules engine', 'SRD 5.2, enforced on every move.<br>No fudging. No favours. If it isn’t in the engine, it didn’t happen.');
  });

  // E. COMBAT 44-60
  function combatClip(name, a, b, view, id, h, s) {
    scene(a, b + .05, T => [clipFrame(name, T - a)], T => {
      const lt = T - a, d = b - a, p = E.inOut(inv(0, d, lt));
      const v = view(p, lt);
      draw(clipFrame(name, lt), { ...v, alpha: 1 });
      if (h) callout(id, T, a + .15, b - .05, h, s);
    });
  }
  combatClip('init', 44, 46, p => ({ fx: .42, fy: .42, zoom: lerp(1.22, 1.3, p) }), 'init', 'Roll for initiative', 'Turn order, actions, movement and reactions, all on the table.');
  combatClip('fireball', 46, 50.47, p => ({ fx: lerp(.40, .36, p), fy: .5, zoom: lerp(1.35, 1.5, p) }), 'fb', 'Every roll is real', 'Spells, saves and damage resolved by the engine, every die face shown.');
  combatClip('kit', 50.47, 52.95, p => ({ fx: lerp(.38, .42, p), fy: .5, zoom: lerp(1.4, 1.5, p) }), 'kit', 'Rules-exact', 'Advantage, cover, Sneak Attack: the engine knows the SRD.');
  combatClip('brakka', 52.95, 55, p => ({ fx: .35, fy: .52, zoom: lerp(1.6, 1.75, p) }), 'brk', 'Critical hit', 'Weapon masteries, Action Surge, Graze: every feature works.');
  combatClip('mock', 55, 57, p => ({ fx: .36, fy: .44, zoom: lerp(1.45, 1.55, p) }), 'mock', 'A crew with a mouth on them', 'Companions fight, scheme, and talk back.');
  // E6. dice + chain 57-60
  scene(57, 60.02, () => [A.dice, clipFrame('mock', 2)], T => {
    const lt = T - 57, p = E.out(inv(0, 3, lt));
    draw(clipFrame('mock', 2), { zoom: 1.5, fx: .36, fy: .44, filter: 'blur(8px) brightness(.28)' });
    const dp = el('dicep', 'shot', '');
    style(dp, { left: '150px', top: '90px', width: '540px', height: '900px', backgroundImage: `url(${A.dice})`, backgroundSize: `${3840 * .675}px ${2160 * .675}px`,
      backgroundPosition: `${-3040 * .675}px ${-(110 + lerp(0, 120, p)) * .675}px`, opacity: env(T, 57, 60, .25, .1), transform: `rotateY(${lerp(16, 9, p)}deg)` });
    style(el('roll-h', 'gold', 'Every die. Every face.<br>Signed.'), { left: '800px', top: '250px', font: '900 76px/1.08 Cinzel, serif', opacity: env(T, 57.15, 60, .4, .1),
      transform: `translateX(${(1 - E.expo(inv(57.15, 57.8, T))) * 60}px)`, filter: 'drop-shadow(0 6px 20px rgba(0,0,0,.9))' });
    style(el('roll-s', '', 'Cryptographic dice. Every event HMAC-signed and hash-chained to the last: tamper with the log and the table knows.'),
      { left: '806px', top: '470px', width: '900px', font: '500 26px/1.45 Inter, sans-serif', color: '#e2dacb', opacity: env(T, 57.5, 60, .4, .1) });
    const blocks = [['#11290', 'Fireball · 8d6', '9abcd0b7'], ['#11291', 'DEX save · 14', 'e41f0a2c'], ['#11292', 'Defeated', '5c2e97d1'], ['#11293', 'Sneak Attack 3d6', 'a07733fe']];
    const ch = el('chain', 'chain', blocks.map((b, k) => `<div class="block" style="opacity:${E.out(inv(57.8 + k * .22, 58.1 + k * .22, T))}"><b>${b[0]}</b><br>${b[1]}<br><span class="h">🔒 ${b[2]}…</span></div>${k < 3 ? '<div style="align-self:center;color:#e8c27a">→</div>' : ''}`).join(''));
    style(ch, { left: '806px', top: '640px', opacity: env(T, 57.7, 60, .2, .1) });
  });

  // F. BREAK 60-64
  scene(60, 64.02, T => (T > 61.45 && T < 62.95) ? [clipFrame('rewind', T - 61.45)] : [], T => {
    ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
    const tl = [];
    tl.push(`<span style="color:#7d8590">&gt;</span> <span style="color:#e6e1d6">${esc(typed('quicksave before-the-ambush', T, 60.25, 30))}</span>${T < 61 ? '<span class="cursor"></span>' : ''}`);
    if (T > 60.98) tl.push(`<span style="color:#7fd99a">💾 Quicksaved 'before-the-ambush' at event 11162.</span>`);
    if (T > 62.95) tl.push(`<span style="color:#ffb27a">⏪ Quickloaded 'before-the-ambush': the game is exactly as it was at event 11162 (Day 11, 10:30).</span>`);
    if (T < 61.45 || T > 62.95) style(el('qs', '', tl.join('<br>')), { left: '200px', top: T > 62.95 ? '300px' : '470px', font: '400 30px/1.8 "JetBrains Mono", monospace', opacity: env(T, 60.1, 64, .1, .15) });
    if (T > 61.45 && T < 62.95) {
      const lt = T - 61.45, f = clipFrame('rewind', lt);
      draw(f, { zoom: 1.35, fx: .38, fy: .5, filter: 'saturate(1.4) contrast(1.15)' });
      draw(f, { zoom: 1.35, fx: .38, fy: .5, sx: 7, alpha: .35, comp: 'screen', filter: 'sepia(1) hue-rotate(-50deg) saturate(5)' });
      draw(f, { zoom: 1.35, fx: .38, fy: .5, sx: -7, alpha: .35, comp: 'screen', filter: 'sepia(1) hue-rotate(160deg) saturate(5)' });
      ctx.save(); ctx.globalAlpha = .22; ctx.fillStyle = '#000'; for (let y = (T * 400) % 6; y < H; y += 6) ctx.fillRect(0, y, W, 2); ctx.restore();
      const by = (T * 900) % (H + 200) - 100; ctx.save(); ctx.globalAlpha = .25; ctx.fillStyle = '#fff'; ctx.fillRect(0, by, W, 30); ctx.restore();
      style(el('vhs', 'vhs', '◀◀ REWIND'), { left: '80px', top: '70px', opacity: Math.floor(T * 4) % 2 ? 1 : .55 });
    }
    style(el('srt', 'title gold', 'Save. Reload. Try again.'), { top: '620px', font: '900 84px/1 Cinzel, serif', opacity: env(T, 63.15, 64.02, .25, .05),
      transform: `scale(${lerp(1.08, 1, E.out(inv(63.15, 63.8, T)))})` });
  });

  // G. MONTAGE 64-76: twelve beats
  const BEATS = [
    { k: 'clip', c: 'gate', v: { fx: .30, fy: .38, zoom: 1.45 }, h: 'Fight in the dark' },
    { k: 'img', s: A.rook, v: { fx: .5, fy: .45, zoom: 1.25 }, h: 'Build your lair' },
    { k: 'card', s: A.writ, crop: [640, 357, 640, 365], h: 'Handouts & clues' },
    { k: 'card', s: A.item, crop: [650, 218, 620, 644], h: 'Magic items' },
    { k: 'card', s: A.hesketh, crop: [636, 255, 648, 575], h: 'A cast with faces' },
    { k: 'img', s: A.harrowHi, v: { fx: .5, fy: .5, zoom: 1.2 }, h: 'Castles & keeps' },
    { k: 'panel', s: A.journal, h: 'A journal that keeps itself' },
    { k: 'panel', s: A.turns, h: 'Initiative at a glance' },
    { k: 'clip', c: 'roll', off: 2.4, v: { fx: .47, fy: .90, zoom: 1.9 }, h: 'Roll your own dice' },
    { k: 'img', s: A.tamper, v: { fx: .3, fy: .08, zoom: 1.9 }, h: 'Tamper-evident' },
    { k: 'img', s: A.crowsHi, v: { fx: .5, fy: .55, zoom: 1.2 }, h: 'Take a town' },
    { k: 'world', h: 'One saga, chapter by chapter' },
  ];
  scene(64, 76.02, T => {
    const i = clamp(Math.floor(T - 64), 0, 11), b = BEATS[i], lt = T - 64 - i;
    if (b.k === 'clip') return [clipFrame(b.c, (b.off || 0) + lt)];
    if (b.k === 'world') return [A.world];
    return [b.s, A.world];
  }, T => {
    const i = clamp(Math.floor(T - 64), 0, 11), b = BEATS[i], lt = T - 64 - i;
    const punch = 1 + .14 * (1 - E.expo(inv(0, .7, lt)));
    if (b.k === 'clip') draw(clipFrame(b.c, (b.off || 0) + lt), { ...b.v, zoom: b.v.zoom * punch });
    else if (b.k === 'img') draw(b.s, { ...b.v, zoom: b.v.zoom * punch, filter: 'brightness(.95)' });
    else if (b.k === 'world') {
      const p = E.inOut(inv(0, 1, lt)); draw(A.world, { fx: lerp(.33, .5, p), fy: lerp(.78, .5, p), zoom: lerp(3.2, 1.0, E.out(p)), filter: `brightness(${1 - .6 * inv(.6, 1, lt)})` });
    } else {
      draw(A.world, { zoom: 1.4, fx: .3 + i * .05, fy: .6, filter: 'blur(10px) brightness(.22) saturate(.6)' });
      if (b.k === 'card') {
        const [x, y, w, h] = b.crop, sc = Math.min(1280 / w, 700 / h) * punch * .92;
        ctx.save(); ctx.shadowColor = 'rgba(0,0,0,.8)'; ctx.shadowBlur = 60; ctx.shadowOffsetY = 20;
        ctx.drawImage(I(b.s), x, y, w, h, W / 2 - w * sc / 2, 420 - h * sc / 2, w * sc, h * sc); ctx.restore();
      } else {
        const sc = .42 * punch, w = 800 * sc, h = 1900 * sc;
        ctx.save(); ctx.shadowColor = 'rgba(0,0,0,.8)'; ctx.shadowBlur = 60;
        ctx.drawImage(I(b.s), 3040, 110, 800, 1900, W / 2 - w / 2, 40, w, h); ctx.restore();
      }
    }
    { const g = ctx.createLinearGradient(0, 700, 0, H); g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, 'rgba(0,0,0,.78)'); ctx.fillStyle = g; ctx.fillRect(0, 700, W, H - 700); }
    // beat flash + big word
    const fl = (1 - inv(0, .12, lt)) * .55;
    ctx.save(); ctx.globalAlpha = fl; ctx.fillStyle = '#fff4e0'; ctx.fillRect(0, 0, W, H); ctx.restore();
    const g = lt < .1 ? (hash(Math.floor(T * 60)) - .5) * 24 : 0;
    style(el('mt', 'mtext gold', b.h), { top: '860px', opacity: Math.min(1, inv(0, .08, lt), 1 - inv(.9, 1, lt) * (i === 11 ? 1 : 0)), transform: `translateX(${g}px) scale(${lerp(1.06, 1, E.out(inv(0, .4, lt)))})`,
      filter: 'drop-shadow(0 6px 18px rgba(0,0,0,.95)) drop-shadow(0 0 2px rgba(0,0,0,.9))', fontSize: b.h.length > 22 ? '74px' : '92px' });
  });

  // H. END 76-88
  scene(76, 88.01, () => [A.world, A.kit, A.brakka, A.corvin, A.ottilie], T => {
    const lt = T - 76;
    ctx.fillStyle = '#050505'; ctx.fillRect(0, 0, W, H);
    draw(A.world, { zoom: 1.12 + lt * .01, filter: 'brightness(.16) saturate(.4) sepia(.5) blur(2px)', alpha: env(T, 76, 83.8, .6, .6) });
    const lo = env(T, 76, 83.6, .05, .5), lp = E.expo(inv(76, 77.2, T));
    const logo = `<svg viewBox="0 0 100 100" width="130" height="130"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ff6a5a"/><stop offset="1" stop-color="#8e1a14"/></linearGradient></defs>
      <polygon points="50,4 93,28 93,72 50,96 7,72 7,28" fill="url(#g)" stroke="#ffd9a0" stroke-width="4"/><polygon points="50,22 76,66 24,66" fill="#d9443b" stroke="#ffd9a0" stroke-width="2.5" opacity=".95"/></svg>`;
    style(el('logo', 'title', logo), { top: '210px', opacity: lo, transform: `scale(${lerp(1.5, 1, lp)}) rotate(${(1 - lp) * -40}deg)`, filter: 'drop-shadow(0 0 30px rgba(255,90,60,.45))' });
    style(el('lt', 'title gold', 'Live Table'), { top: '370px', font: '900 150px/1 Cinzel, serif', letterSpacing: `${.04 + .06 * (1 - lp)}em`, opacity: lo,
      filter: `blur(${(1 - lp) * 10}px) drop-shadow(0 0 26px rgba(255,170,70,.3))` });
    style(el('tag', 'quote', 'Dungeons &amp; Dragons, with Claude as your Dungeon Master.'), { top: '560px', fontSize: '46px', opacity: env(T, 76.9, 83.6, .6, .5) });
    style(el('feat', 'featrow', 'SRD 5.2 rules engine &nbsp;·&nbsp; real dice &nbsp;·&nbsp; live maps &nbsp;·&nbsp; signed log &nbsp;·&nbsp; runs on your machine'),
      { top: '660px', opacity: env(T, 78.3, 83.6, .6, .5) });
    const co = env(T, 79.6, 83.6, .5, .5);
    style(el('cta', 'cta', 'Open a chat. Type <code>/new-game</code>'), { top: '750px', opacity: co, transform: `translateX(-50%) translateY(${(1 - E.out(inv(79.6, 80.2, T))) * 16}px)` });
    // the sting: the crew, waiting
    const so = env(T, 84.0, 88.0, .2, 1.6);
    if (so > 0) {
      const ids = ['kit', 'brakka', 'corvin', 'ottilie'];
      ids.forEach((id, k) => {
        const x = 300 + k * 340, rise = E.out(inv(84 + k * .08, 84.8 + k * .08, T));
        ctx.save(); ctx.globalAlpha = so * rise; ctx.filter = `brightness(${.85 + .15 * Math.sin(T * 2 + k)}) sepia(.2)`;
        ctx.shadowColor = 'rgba(0,0,0,.8)'; ctx.shadowBlur = 40;
        ctx.drawImage(I(A[id]), x, 260 + (1 - rise) * 40, 300, 300);
        ctx.strokeStyle = 'rgba(232,194,122,.6)'; ctx.lineWidth = 2; ctx.strokeRect(x, 260 + (1 - rise) * 40, 300, 300); ctx.restore();
      });
      style(el('sting1', 'title gold', 'The Hollow Crown'), { top: '640px', font: '900 64px/1 Cinzel, serif', letterSpacing: '.08em', opacity: so });
      style(el('sting2', 'quote', 'The crew is waiting.'), { top: '730px', fontSize: '40px', opacity: env(T, 84.6, 88, .4, 1.4) });
    }
  });

  // ------------------------------------------------------------------ frame
  function postParams(T) {
    const o = { vig: .55, grain: .07, embers: 0, leak: 0, bars: 0, flash: 0, black: 0 };
    if (T < 8.1) { o.bars = 132; o.embers = .9 * inv(0, 1.5, T); o.vig = .75; o.black = 1 - inv(0, 1.4, T); }
    else if (T < 12.25) { o.embers = 1.2; o.leak = .8; o.vig = .7; o.bars = 132 * (1 - E.inOut(inv(11.6, 12.2, T))); }
    if (T >= 28 && T < 36.2) o.embers = .5;
    if (T >= 44 && T < 60) o.vig = .5;
    if (T >= 76) { o.embers = 1.1; o.leak = .4; o.vig = .8; o.bars = 0; o.black = inv(87.1, 88, T); }
    if (T >= 84 && T < 88) o.embers = 1.4;
    // flashes on the big hits and cuts
    const hits = [[8.0, .95, .6], [12.0, .35, .25], [16.0, .3, .25], [28.0, .45, .3], [44.0, .6, .35], [64.0, .7, .3], [76.0, .85, .7], [84.0, .5, .5]];
    for (const [t, a, d] of hits) if (T >= t && T < t + d) o.flash = Math.max(o.flash, a * (1 - inv(t, t + d, T)));
    for (const t of [30, 32, 34]) if (T >= t - .06 && T < t + .14) o.flash = Math.max(o.flash, .25 * (1 - inv(t - .06, t + .14, T)));
    if (T >= 7.7 && T < 8) o.black = Math.max(o.black, 0);
    if (T >= 59.97 && T < 60.1) o.black = 1;
    return o;
  }

  window.renderFrame = async (T) => {
    used = new Set();
    const act = S.filter(s => T >= s.t0 && T < s.t1);
    const needs = []; act.forEach(s => needs.push(...(s.needs(T) || [])));
    await need(needs);
    ctx.globalAlpha = 1; ctx.filter = 'none'; ctx.globalCompositeOperation = 'source-over';
    ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
    for (const s of act) s.render(T);
    for (const [id, e] of els) if (!used.has(id)) e.style.display = 'none';
    postfx(T, postParams(T));
    // wait for any <img> inside overlays (icons) to be decoded
    await Promise.all([...ov.querySelectorAll('img')].map(i => i.complete ? 0 : i.decode().catch(() => 0)));
    return act.length;
  };
  window.DURATION = 88;
  window.preload = async () => { const F = ['900 40px Cinzel','700 40px Cinzel','italic 500 40px "Cormorant Garamond"','500 40px "Cormorant Garamond"','600 40px "Cormorant Garamond"','italic 600 40px "Cormorant Garamond"','400 20px Inter','500 20px Inter','600 20px Inter','700 20px Inter','400 20px "JetBrains Mono"','600 20px "JetBrains Mono"']; await Promise.all(F.map(f => document.fonts.load(f, 'Aa→✖⚖💾'))); await document.fonts.ready; await need(Object.values(A)); return true; };
})();
