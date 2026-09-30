// Table Story: what just happened, shown on the map itself.
// The DM's lines for the current beat (one DM turn: lines logged close together) appear as speech bubbles over the
// speaker's token, captions by the creature a narration line is about (`say --at <id>`), and a story strip along the
// bottom of the map. Bubbles follow their tokens through pan, zoom and animation. A new beat replaces the old one.
(() => {
  const GAP = 90 * 1000;          // lines logged closer together than this belong to the same beat
  const MAX_LINES = 7, STRIP_LINES = 4, MAX_BUBBLE = 110;
  const $ = (s, el = document) => el.querySelector(s);
  let S = null, app = null, beat = [], bubbles = [], raf = 0, lastKey = "";

  const tsOf = (f) => { const t = Date.parse(f.ts || ""); return Number.isNaN(t) ? 0 : t; };
  const esc = (s) => app ? app.esc(s) : String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const clip = (s, n) => s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s;
  const collapsed = () => { try { return localStorage.getItem("storyCollapsed") === "1"; } catch { return false; } };
  const bubblesOff = () => { try { return localStorage.getItem("storyBubbles") === "off"; } catch { return false; } };
  function setBubblesOff(off) {
    try { localStorage.setItem("storyBubbles", off ? "off" : "on"); } catch {}
    draw();
  }

  // the latest beat, from the public feed (the source of truth)
  function beatFrom(feed) {
    const lines = [];
    let prev = null;
    for (let i = feed.length - 1; i >= 0; i--) {
      const f = feed[i], t = tsOf(f);
      if (prev !== null && t && prev - t > GAP) break;
      if (t) prev = t;
      if (f.kind === "speech" || f.kind === "narration") lines.unshift(f);
      if (lines.length >= MAX_LINES) break;
    }
    return lines;
  }

  // the whole conversation: every line since the scene began (or the last 80), grouped into beats
  function thread(feed) {
    const lines = [];
    for (let i = feed.length - 1; i >= 0 && lines.length < 80; i--) {
      const f = feed[i];
      if (f.kind === "scene" && lines.length) break;
      if (f.kind === "speech" || f.kind === "narration") lines.unshift(f);
    }
    const beats = [];
    lines.forEach(f => {
      const last = beats[beats.length - 1], prev = last && last[last.length - 1];
      if (!last || (tsOf(f) && tsOf(prev) && tsOf(f) - tsOf(prev) > GAP)) beats.push([f]); else last.push(f);
    });
    return beats;
  }
  function openThread(focusSeq) {
    if (!app || !app.openModal) return;
    const beats = thread((S && S.feed || []).filter(f => f.kind !== "fx"));
    const row = (f) => {
      const who = f.who || (f.kind === "speech" && app.speakerId ? app.speakerId(f.speaker) : null);
      const mark = f.seq === focusSeq ? " focus" : "";
      if (f.kind === "narration") return `<div class="th-line narration${mark}" data-seq="${f.seq}">${esc(f.text || "")}</div>`;
      const av = who ? app.avatar(who, "th-av") : `<span class="av dm th-av">${esc(String(f.speaker || "?")[0])}</span>`;
      return `<div class="th-line speech${mark}" data-seq="${f.seq}">${av}<div class="th-bub"><b>${esc(f.speaker || "")}</b>${esc(f.text || "")}</div></div>`;
    };
    const body = beats.map((b, i) => `<div class="th-beat${i === beats.length - 1 ? " now" : ""}">` +
      `<div class="th-when">${i === beats.length - 1 ? "Just now" : "Earlier"}</div>${b.map(row).join("")}</div>`).join("");
    app.openModal(`<div class="info thread"><h2>The conversation</h2><div class="muted">Everything said and done in this scene, oldest first.</div>
      <div class="th-body">${body || `<p class="muted">Nothing yet.</p>`}</div></div>`);
    const box = document.querySelector("#modal .th-body");
    const focus = box && (box.querySelector(".focus") || box.lastElementChild);
    if (focus) focus.scrollIntoView({ block: "center" });
  }

  function layers() {
    const vp = $("#viewport"); if (!vp) return {};
    let talk = $("#talk"), strip = $("#story");
    if (!talk) { talk = document.createElement("div"); talk.id = "talk"; vp.appendChild(talk); }
    if (!strip) {
      strip = document.createElement("div"); strip.id = "story"; vp.appendChild(strip);
      strip.addEventListener("click", (ev) => {
        if (ev.target.closest(".st-toggle")) {
          try { localStorage.setItem("storyCollapsed", collapsed() ? "0" : "1"); } catch {}
          draw();
          return;
        }
        const line = ev.target.closest("[data-seq]");
        openThread(line ? +line.dataset.seq : null);
      });
      talk.addEventListener("click", (ev) => {
        if (ev.target.closest(".b-x")) { setBubblesOff(true); return; }   // one × closes every bubble
        const b = ev.target.closest("[data-seq]");
        if (b) openThread(+b.dataset.seq);
      });
    }
    let reopen = $("#talkshow");
    if (!reopen) {
      reopen = document.createElement("button");
      reopen.id = "talkshow"; reopen.title = "Show speech bubbles"; reopen.textContent = "💬";
      reopen.addEventListener("click", () => setBubblesOff(false));
      vp.appendChild(reopen);
    }
    return { talk, strip, reopen };
  }

  function speakerLine(f) {
    const who = f.who || (app && app.speakerId ? app.speakerId(f.speaker) : null);
    const av = who && app ? app.avatar(who, "st-av") : `<span class="av dm st-av">${esc(String(f.speaker || "?")[0])}</span>`;
    return `<div class="st-line speech" data-seq="${f.seq}" title="${esc(f.text || "")}">${av}<div class="st-txt"><b>${esc(f.speaker || "")}</b> ${esc(f.text || "")}</div></div>`;
  }

  function draw() {
    const { talk, strip, reopen } = layers(); if (!talk) return;
    // the strip: the last few lines of the beat, newest at the bottom (each clamped to two lines; hover for the rest)
    if (!beat.length) { strip.hidden = true; }
    else {
      strip.hidden = false;
      strip.classList.toggle("collapsed", collapsed());
      const shown = beat.slice(-STRIP_LINES);
      const lines = shown.map((f, i) => {
        const cls = i < shown.length - 2 ? " old" : "";
        return f.kind === "speech" ? speakerLine(f).replace('class="st-line speech"', `class="st-line speech${cls}"`)
          : `<div class="st-line narration${cls}" data-seq="${f.seq}" title="${esc(f.text || "")}"><div class="st-txt">${esc(f.text || "")}</div></div>`;
      }).join("");
      const more = beat.length > shown.length ? ` · ${beat.length} lines, full text in the Log` : "";
      strip.innerHTML = `<div class="st-head"><span>Just now${more}</span><button class="st-toggle" title="Show / hide">${collapsed() ? "▴" : "▾"}</button></div>` +
        (collapsed() ? "" : `<div class="st-body">${lines}</div>`);
    }
    // bubbles: the latest line per creature, by its token
    const latest = new Map();
    beat.forEach((f, i) => {
      const who = f.who || (f.kind === "speech" && app && app.speakerId ? app.speakerId(f.speaker) : null);
      if (who) latest.set(who, { f: { ...f, who }, i });
    });
    talk.innerHTML = "";
    const off = bubblesOff();
    reopen.hidden = !(off && latest.size);                // the tiny button only matters when there are bubbles to show
    bubbles = off ? [] : [...latest.values()].map(({ f, i }) => {
      const el = document.createElement("div");
      el.className = (f.kind === "speech" ? "bubble" : "caption") + (i < beat.length - 3 ? " old" : "") + (i === beat.length - 1 ? " fresh" : "");
      el.title = "Click for the whole conversation"; el.dataset.seq = f.seq;
      el.innerHTML = `<button class="b-x" title="Hide all bubbles">×</button>` +
        (f.kind === "speech" ? `<b>${esc(f.speaker || "")}</b>${esc(clip(f.text || "", MAX_BUBBLE))}` : esc(clip(f.text || "", MAX_BUBBLE)));
      talk.appendChild(el);
      return { el, who: f.who, kind: f.kind };
    });
    if (bubbles.length && !raf) raf = requestAnimationFrame(tick);
  }

  // keep each bubble on its token (pan, zoom, animation), and keep bubbles from sitting on each other
  function tick() {
    raf = 0;
    const vp = $("#viewport"); if (!vp || !bubbles.length) return;
    const V = vp.getBoundingClientRect(), placed = [];
    const order = bubbles.map(b => {
      const t = document.querySelector(`#map .token[data-id="${CSS.escape(b.who)}"]`);
      return { b, r: t ? t.getBoundingClientRect() : null };
    }).sort((a, b) => (a.r ? a.r.top : 0) - (b.r ? b.r.top : 0));
    for (const { b, r } of order) {
      if (!r || r.width === 0) { b.el.style.display = "none"; continue; }
      b.el.style.display = "";
      const w = b.el.offsetWidth, h = b.el.offsetHeight;
      let x = r.left + r.width / 2 - V.left - w / 2;
      let y = b.kind === "speech" ? r.top - V.top - h - 8 : r.bottom - V.top + 16;
      x = Math.max(6, Math.min(V.width - w - 6, x));
      for (let guard = 0; guard < 8; guard++) {        // nudge off any bubble already placed
        const hit = placed.find(p => x < p.x + p.w && x + w > p.x && y < p.y + p.h && y + h > p.y);
        if (!hit) break;
        y = b.kind === "speech" ? hit.y - h - 4 : hit.y + hit.h + 4;
      }
      y = Math.max(4, Math.min(V.height - h - 4, y));
      placed.push({ x, y, w, h });
      b.el.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)`;
    }
    raf = requestAnimationFrame(tick);
  }

  window.TableStory = {
    init(api) { app = api; },
    // the committed state: rebuild the beat from the feed
    update(st) {
      S = st;
      const feed = (S.feed || []).filter(f => f.kind !== "fx");
      const next = beatFrom(feed);
      const key = next.map(f => f.seq).join(",");
      if (key === lastKey) return;
      lastKey = key; beat = next; draw();
    },
    // during an animation: a line arrives in order with the moves and attacks around it
    live(c) {
      const f = { kind: c.k, text: c.text, speaker: c.speaker, who: c.who, ts: c.ts, seq: c.seq };
      const last = beat[beat.length - 1];
      if (last && tsOf(f) && tsOf(last) && tsOf(f) - tsOf(last) > GAP) beat = [];
      beat.push(f); if (beat.length > MAX_LINES) beat.shift();
      lastKey = ""; draw();
      return Math.min(3200, Math.max(900, (c.text || "").length * 38));   // time to read it, in ms
    },
  };
})();
