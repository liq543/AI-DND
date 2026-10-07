// Display-only fixture study using the same animation layer as the live game.
(() => {
  const vp = document.querySelector('#viewport'), map = document.querySelector('#map');
  let scale = 1, mode = 'none', busy = false, section = -1;
  // Review-only frame intervals, published in DOM attributes for browser inspection.
  let frameLast=null, frameSamples=[];
  function studyFrame(now) {
    if (frameLast!==null && !document.hidden) frameSamples.push(now-frameLast);
    frameLast=now;
    if (frameSamples.length>=120) {
      const sorted=frameSamples.slice(-120).sort((a,b)=>a-b),status=document.querySelector('#labstatus');
      status.dataset.frameMedianMs=sorted[60].toFixed(2);
      status.dataset.frameP95Ms=sorted[114].toFixed(2);
      status.dataset.frameSamples='120';frameSamples=[];
    }
    requestAnimationFrame(studyFrame);
  }
  requestAnimationFrame(studyFrame);
  function fit() {
    const svg = map.querySelector('svg');
    const w = svg.width.baseVal.value, h = svg.height.baseVal.value;
    scale = Math.min((vp.clientWidth-36)/w, (vp.clientHeight-36)/h);
    if (section>=0) {
      scale*=2;
      const cx=w*(section%2 ? .75:.25),cy=h*(section<2?.25:.75);
      document.querySelector('#mapwrap').style.transform=`translate(${vp.clientWidth/2-cx*scale}px,${vp.clientHeight/2-cy*scale}px) scale(${scale})`;
      return;
    }
    document.querySelector('#mapwrap').style.transform = `translate(${(vp.clientWidth-w*scale)/2}px,${(vp.clientHeight-h*scale)/2}px) scale(${scale})`;
  }
  TableFX.init({scale:()=>scale, camera:()=>Promise.resolve(), viewMap:()=>null, fit:()=>fit(), esc:s=>String(s), entity:()=>null});
  TableFX.setPref('dm');
  const state = () => TableFX.setState({view:{anim:{ambient:mode,intensity:.6,shake:'off',camera:'off'}}});
  state(); fit(); TableFX.committed();
  document.querySelector('[data-map="0"]')?.classList.add('on');
  async function loadMap(index) {
    if (busy) return;
    delete map.dataset.readyIndex;delete map.dataset.cameraReady;
    const started=performance.now();
    map.innerHTML = await (await fetch('/map/'+index)).text();section=-1;
    map.dataset.mapIndex=index;
    document.querySelectorAll('[data-map]').forEach(b=>b.classList.toggle('on',b.dataset.map===String(index)));
    fit(); TableFX.committed();
    const sources=[...new Set([...map.querySelectorAll('image')].map(e=>e.href.baseVal))];
    await Promise.all(sources.map(async src=>{const image=new Image();image.src=src;try{await image.decode();}catch{}}));
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    const ms=Math.round(performance.now()-started);
    map.dataset.readyIndex=index;
    document.querySelector('#labstatus').dataset.paintReadyMs=String(ms);
    document.querySelector('#labstatus').textContent=`Ready · ${ms} ms`;
  }
  document.querySelectorAll('[data-map]').forEach(button => button.onclick=()=>loadMap(button.dataset.map));
  const catalogue=document.querySelector('#mapselect');
  if(catalogue)catalogue.onchange=()=>loadMap(catalogue.value);
  document.querySelectorAll('[data-camera]').forEach(b=>b.onclick=()=>{
    delete map.dataset.cameraReady;
    section=b.dataset.camera==='overview'?-1:(section+1)%4;fit();
    document.querySelector('#labstatus').textContent=section<0?'Overview':`Section ${section+1} of 4`;
    requestAnimationFrame(()=>requestAnimationFrame(()=>{map.dataset.cameraReady=String(section);}));
  });
  document.querySelectorAll('[data-effect]').forEach(button => button.onclick = async () => {
    if (button.dataset.effect === 'freeze') {
      const paused = button.textContent === 'Resume animation';
      TableFX.pauseVisuals(!paused);
      document.getAnimations().forEach(a => {
        if (paused) a.play();
        else {
          a.pause(); a.currentTime = Math.min(400, (a.effect.getTiming().duration || 1000)*.4);
          // Mirror the paused browser frame into inline styles for screenshot exporters.
          const el = a.effect.target, computed = getComputedStyle(el);
          el.style.transform = computed.transform; el.style.opacity = computed.opacity;
        }
      });
      button.textContent = paused ? 'Freeze frame' : 'Resume animation';
      return;
    }
    if (busy) return;
    const fx = button.dataset.effect;
    if (['embers','rain','fog','storm','snow','ash','motes','off'].includes(fx)) {
      mode = fx==='off' ? 'none' : fx; TableFX.setPref(fx==='off' ? 'off' : 'dm'); state();
      document.querySelector('#labstatus').textContent = fx==='off' ? 'Motion off' : fx+' active'; return;
    }
    TableFX.setPref('dm'); state(); busy = true;
    document.querySelector('#labstatus').textContent = 'Playing';
    const cue = {k:'fx',fx:fx==='spell'?'projectile':'ring',from:{id:'mage'},to:{id:'ranger'},at:{id:'ranger'},color:fx==='spell'?'#b8caff':'#f2d28c',radius:15};
    await TableFX.play([cue, {...cue}, {...cue}]);
    busy = false; document.querySelector('#labstatus').textContent = 'Ready';
  });
  new ResizeObserver(fit).observe(vp);
})();
