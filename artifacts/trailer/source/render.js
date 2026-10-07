// node render.js outdir [t0] [t1] [fps] [list of explicit times...]
const fs = require('fs'); const puppeteer = require('puppeteer-core');
const SP = 'C:/Users/ggore/AppData/Local/Temp/claude/C--Users-ggore-Documents-Coding-Projects-dnd/ffba5656-8650-4779-acd6-0b45027684c2/scratchpad';
const EXE = SP + '/tools/browsers/chrome-headless-shell/win64-155.0.8059.39/chrome-headless-shell-win64/chrome-headless-shell.exe';
(async () => {
  const [out, a = '0', b = '88', fpsS = '30', ...explicit] = process.argv.slice(2);
  fs.mkdirSync(out, { recursive: true });
  const br = await puppeteer.launch({ executablePath: EXE, headless: 'shell', protocolTimeout: 600000,
    args: ['--allow-file-access-from-files', '--window-size=1920,1080', '--hide-scrollbars', '--force-color-profile=srgb', '--font-render-hinting=none'] });
  const p = await br.newPage(); await p.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  p.on('console', m => { if (m.type() === 'warning' || m.type() === 'error') console.log('page:', m.text()); });
  p.on('pageerror', e => console.log('PAGEERR', e.message));
  await p.goto('file:///' + SP + '/trailer/trailer.html', { waitUntil: 'networkidle0', timeout: 120000 });
  await p.evaluate(() => window.preload());
  const fps = +fpsS, times = explicit.length ? explicit.map(Number) : [];
  if (!times.length) { const n0 = Math.round(+a * fps), n1 = Math.round(+b * fps); for (let i = n0; i < n1; i++) times.push(i / fps); }
  const t0 = Date.now(); let k = 0;
  for (const T of times) {
    await p.evaluate(T => window.renderFrame(T), T);
    await p.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
    const name = explicit.length ? `t${T.toFixed(2)}.jpg` : `f${String(Math.round(T * fps)).padStart(5, '0')}.jpg`;
    await p.screenshot({ path: out + '/' + name, type: 'jpeg', quality: 93 });
    if (++k % 60 === 0) console.log(k, 'frames', ((Date.now() - t0) / k).toFixed(0), 'ms/frame');
  }
  console.log('done', k, 'in', ((Date.now() - t0) / 1000).toFixed(1), 's');
  await br.close();
})();
