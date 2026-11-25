/* Sunucu denetimi: → / boşluk / PageDown sonraki adım, ← / PageUp geri, R sahneyi baştan, A açıklama satırı, 1–8 sahne. Adres: #sahne/adım */
(function (CM) {
  const NAMES = { 1: 'Sorun', 2: 'Sabah', 3: 'Onay', 4: 'Kapıda', 5: 'Hasat', 6: 'Öğrenme', 7: 'Değer', 8: 'Kapanış' };
  let active = null, step = 0, busy = false;

  CM.drawStep = function (n, i) {
    const a = CM.$('steps');
    a.innerHTML = '';
    for (let k = 0; k < n; k++) { const t = document.createElement('i'); if (k <= i) t.className = 'ok'; a.appendChild(t); }
  };
  function writeHash() {
    history.replaceState(null, '', `#${active.no}/${step}`);
    if (active.no !== 2 && CM.drawNarration) CM.drawNarration(active.no, step);   // Sahne 2 vuruşla ilerler, kendisi çizer
  }

  async function openScene(no, firstStep = 0) {
    const s = CM.scenes[no];
    if (!s || busy) return;
    busy = true;
    try {
      if (active) active.leaving();
      active = s;
      CM.$('scene-no').textContent = `${s.no} · ${s.name}`;
      CM.$('scene-title').textContent = s.title;
      CM.$('attribution').innerHTML = s.attribution;
      document.querySelectorAll('#scenes button').forEach((b) => b.classList.toggle('active', +b.dataset.no === no));
      await s.enter();
      step = 0;
      if (s.step) {
        step = Math.min(firstStep, s.stepCount - 1);
        s.step(step, step === 0 ? null : undefined);
        CM.drawStep(s.stepCount, step);
      } else if (firstStep > 0) {
        for (let k = 0; k < firstStep; k++) s.next();
      }
      writeHash();
    } finally { busy = false; }
  }

  function next() {
    if (!active || busy) return;
    // sahnenin bekleyen eylemi (ör. "Bugünün soruları", "Simüle kıdemli cevaplasın") → önce o çalışır
    if (typeof active.pending === 'function') { const f = active.pending; active.pending = null; f(); return; }
    if (active.next) { if (!active.next()) nextScene(); return; }
    if (step < active.stepCount - 1) { const o = step; step++; active.step(step, o); CM.drawStep(active.stepCount, step); writeHash(); }
    else nextScene();
  }
  function back() {
    if (!active || busy) return;
    if (active.back) { if (!active.back() && CM.scenes[active.no - 1]) openScene(active.no - 1, 99); return; }
    if (step > 0) { const o = step; step--; active.step(step, o); CM.drawStep(active.stepCount, step); writeHash(); }
    else if (CM.scenes[active.no - 1]) openScene(active.no - 1, 99);
  }
  CM.openScene = (no, first) => openScene(no, first);
  CM.next = () => next();
  function nextScene() { if (CM.scenes[active.no + 1]) openScene(active.no + 1); }
  function restart() {
    if (!active) return;
    if (active.restart) { active.restart(); return; }
    openScene(active.no, 0);
  }

  document.addEventListener('keydown', (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.target && e.target.closest && e.target.closest('input, textarea, select')) return; // serbest soru / not yazılırken
    const k = e.key;
    if (k === 'ArrowRight' || k === ' ' || k === 'PageDown' || k === 'Enter') { e.preventDefault(); next(); }
    else if (k === 'ArrowLeft' || k === 'PageUp' || k === 'Backspace') { e.preventDefault(); back(); }
    else if (k === 'r' || k === 'R') restart();
    else if ((k === 'a' || k === 'A') && CM.toggleNarration) CM.toggleNarration();
    else if (/^[1-8]$/.test(k) && CM.scenes[+k]) openScene(+k);
  });

  async function start() {
    const nav = CM.$('scenes');
    for (let n = 1; n <= 8; n++) {
      const b = document.createElement('button');
      b.textContent = n; b.dataset.no = n; b.title = NAMES[n] + (CM.scenes[n] ? '' : ' (yapılmadı)');
      b.disabled = !CM.scenes[n];
      b.onclick = () => openScene(n);
      nav.appendChild(b);
    }
    CM.$('next').onclick = next;
    CM.$('back').onclick = back;
    CM.$('narration-key').onclick = () => CM.toggleNarration && CM.toggleNarration();
    await CM.H.setup({ center: [29.19, 41.14], zoom: 11.4, pitch: 40, bearing: -8 });
    const m = location.hash.match(/^#(\d)(?:\/(\d+))?/);
    await openScene(m && CM.scenes[+m[1]] ? +m[1] : 1, m && m[2] ? +m[2] : 0);
  }
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(start); else start();
})(window.CM);
