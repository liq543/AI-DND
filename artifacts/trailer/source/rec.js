// Record the live table while running a timed script of engine commands / page JS.
// usage: node rec.js plan.json      plan: {out, duration, dpr, setup:[js], actions:[{at, engine:"args..."}|{at, js:"..."}|{at, shot:"name"}], quality}
const fs = require('fs'), path = require('path'), { execFile } = require('child_process');
const puppeteer = require('puppeteer-core');
const SP = 'C:/Users/ggore/AppData/Local/Temp/claude/C--Users-ggore-Documents-Coding-Projects-dnd/ffba5656-8650-4779-acd6-0b45027684c2/scratchpad';
const EXE = SP + '/tools/browsers/chrome-headless-shell/win64-155.0.8059.39/chrome-headless-shell-win64/chrome-headless-shell.exe';
const REPO = 'C:/Users/ggore/Documents/Coding Projects/dnd';
const env = { ...process.env, DND_CAMPAIGNS: SP + '/sandbox/campaigns', DND_ENGINE_HOME: SP + '/sandbox/home', PYTHONIOENCODING: 'utf-8' };
const sleep = ms => new Promise(r => setTimeout(r, ms));
function engine(args) {
  return new Promise(res => execFile('py', ['-m', 'engine', ...args], { cwd: REPO, env, maxBuffer: 1 << 24 }, (e, so, se) => {
    const out = (so || '') + (se || ''); fs.appendFileSync(plan.out + '/engine.log', '$ ' + args.join(' ') + '\n' + out + '\n'); res(out);
  }));
}
function split(s) { const a = []; s.replace(/"([^"]*)"|'([^']*)'|(\S+)/g, (m, d, q, w) => a.push(d ?? q ?? w)); return a; }
const plan = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
(async () => {
  fs.mkdirSync(plan.out + '/frames', { recursive: true });
  for (const c of plan.pre || []) await engine(split(c));
  const b = await puppeteer.launch({ executablePath: EXE, headless: 'shell', args: ['--window-size=1920,1080', '--hide-scrollbars'] });
  const p = await b.newPage();
  const dpr = plan.dpr || 1;
  await p.setViewport({ width: plan.w || 1920, height: plan.h || 1080, deviceScaleFactor: dpr });
  await p.goto('http://localhost:8799/', { waitUntil: 'networkidle2' });
  await sleep(plan.settle || 2500);
  for (const js of plan.setup || []) { await p.evaluate(js); await sleep(400); }
  for (const a of plan.setupActions || []) {
    if (a.wheel) { const [x, y, n] = a.wheel; await p.mouse.move(x, y); for (let i = 0; i < Math.abs(n); i++) { await p.mouse.wheel({ deltaY: n < 0 ? -100 : 100 }); await sleep(60); } }
    if (a.drag) { const [x1, y1, x2, y2] = a.drag; await p.mouse.move(x1, y1); await p.mouse.down(); for (let i = 1; i <= 12; i++) { await p.mouse.move(x1 + (x2 - x1) * i / 12, y1 + (y2 - y1) * i / 12); await sleep(16); } await p.mouse.up(); }
    if (a.js) await p.evaluate(a.js);
    if (a.engine) await engine(split(a.engine));
    await sleep(a.wait || 300);
  }
  await sleep(plan.settle2 || 800);
  const cdp = await p.createCDPSession();
  const stamps = []; let n = 0; const t0 = Date.now();
  if (plan.duration) {
    cdp.on('Page.screencastFrame', async f => {
      const name = String(n++).padStart(5, '0') + '.jpg';
      fs.writeFileSync(plan.out + '/frames/' + name, Buffer.from(f.data, 'base64'));
      stamps.push([name, Date.now() - t0]);
      try { await cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }); } catch (e) {}
    });
    await cdp.send('Page.startScreencast', { format: 'jpeg', quality: plan.quality || 92, maxWidth: (plan.w || 1920) * dpr, maxHeight: (plan.h || 1080) * dpr, everyNthFrame: 1 });
  }
  const acts = (plan.actions || []).slice().sort((a, b) => a.at - b.at);
  for (const a of acts) {
    const wait = a.at - (Date.now() - t0); if (wait > 0) await sleep(wait);
    if (a.engine) await engine(split(a.engine));
    if (a.js) { try { const r = await p.evaluate(a.js); if (r !== undefined) fs.appendFileSync(plan.out + '/engine.log', 'JS> ' + JSON.stringify(r) + '\n'); } catch (e) { fs.appendFileSync(plan.out + '/engine.log', 'JSERR ' + e.message + '\n'); } }
    if (a.wheel) { const [x, y, n] = a.wheel; await p.mouse.move(x, y); for (let i = 0; i < Math.abs(n); i++) { await p.mouse.wheel({ deltaY: n < 0 ? -100 : 100 }); await sleep(a.step || 40); } }
    if (a.drag) { const [x1, y1, x2, y2] = a.drag; await p.mouse.move(x1, y1); await p.mouse.down(); const k = a.steps || 12; for (let i = 1; i <= k; i++) { await p.mouse.move(x1 + (x2 - x1) * i / k, y1 + (y2 - y1) * i / k); await sleep(a.step || 16); } await p.mouse.up(); }
    if (a.wait) await sleep(a.wait);
    if (a.shot) await p.screenshot({ path: plan.out + '/' + a.shot + '.png', type: 'png' });
    stamps.push(['@' + (a.engine || a.js || a.shot || '').slice(0, 60), Date.now() - t0]);
  }
  if (plan.duration) { const w = plan.duration - (Date.now() - t0); if (w > 0) await sleep(w); await cdp.send('Page.stopScreencast'); }
  fs.writeFileSync(plan.out + '/stamps.json', JSON.stringify(stamps));
  console.log('frames', n, 'secs', (Date.now() - t0) / 1000, 'fps', (n / ((Date.now() - t0) / 1000)).toFixed(1));
  await b.close();
})();
