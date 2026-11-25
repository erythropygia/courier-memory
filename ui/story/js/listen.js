/* Sesli not → metin: önce sunucu (/api/transcribe, Amazon Transcribe tr-TR), kapalıysa (501) ya da hata → tarayıcı
   ses tanıması (Web Speech API). Hikaye (js/listen.js) ve eski tek sayfa (ui/story/js/listen.js) aynı dosyayı yükler.
   Kayıt MediaRecorder ile alınır (Chrome/Edge webm-opus, Safari mp4); tarayıcıda 16 kHz mono 16 bit PCM'e çevrilip
   ham gövde olarak gönderilir (Transcribe Streaming webm/mp4 kabul etmez). CM'ye bağımlı değil: window.CMListen. */
(function () {
  const RATE = 16000, MAX_MS = 60000, MIN_S = 0.3;
  let server = null; // null: bilinmiyor · true: sunucu tanıması açık · false: tarayıcıya düş

  const AC = () => window.AudioContext || window.webkitAudioContext;
  const OAC = () => window.OfflineAudioContext || window.webkitOfflineAudioContext;
  const canRecord = () => !!(window.MediaRecorder && navigator.mediaDevices && navigator.mediaDevices.getUserMedia && AC() && OAC());
  const browserSR = () => window.SpeechRecognition || window.webkitSpeechRecognition || null;

  async function timed(url, opt, ms) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), ms);
    try { return await fetch(url, { ...opt, signal: ctrl.signal }); } finally { clearTimeout(t); }
  }

  // sunucu tanıması açık mı (bir kez sorulur; 501/ağ hatası → tarayıcı)
  async function serverReady(base) {
    if (server !== null) return server;
    if (!canRecord()) return (server = false);
    try { server = (await timed((base || '') + '/api/transcribe', {}, 4000)).ok; } catch (e) { server = false; }
    return server;
  }

  // basılı tutma süresince kayıt; stop() → Blob
  async function start() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    const rec = new MediaRecorder(stream), parts = [];
    rec.ondataavailable = (e) => { if (e.data && e.data.size) parts.push(e.data); };
    const done = new Promise((res) => {
      rec.onstop = () => { stream.getTracks().forEach((t) => t.stop()); res(new Blob(parts, { type: rec.mimeType || 'audio/webm' })); };
    });
    rec.start();
    const limit = setTimeout(() => rec.state !== 'inactive' && rec.stop(), MAX_MS);
    return { stop() { clearTimeout(limit); if (rec.state !== 'inactive') rec.stop(); return done; } };
  }

  function decode(ac, data) {
    return new Promise((res, rej) => { const p = ac.decodeAudioData(data, res, rej); if (p && p.then) p.then(res, rej); });
  }
  // kayıt → 16 kHz mono PCM s16le (çok kısaysa null)
  async function toPcm(blob) {
    const ac = new (AC())();
    let buf;
    try { buf = await decode(ac, await blob.arrayBuffer()); } finally { if (ac.close) ac.close(); }
    if (!buf || buf.duration < MIN_S) return null;
    const off = new (OAC())(1, Math.ceil(Math.min(buf.duration, MAX_MS / 1000) * RATE), RATE);
    const src = off.createBufferSource();
    src.buffer = buf; src.connect(off.destination); src.start();
    const f = (await off.startRendering()).getChannelData(0), out = new DataView(new ArrayBuffer(f.length * 2));
    for (let i = 0; i < f.length; i++) { const s = Math.max(-1, Math.min(1, f[i])); out.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true); }
    return out.buffer;
  }

  // kayıt → metin; hata: e.status (501: sunucu kapalı), e.detail (Türkçe ileti)
  async function transcribe(base, blob) {
    const body = await toPcm(blob);
    if (!body) return '';
    let r;
    try { r = await timed((base || '') + '/api/transcribe', { method: 'POST', headers: { 'Content-Type': 'audio/pcm;rate=' + RATE }, body }, 45000); }
    catch (x) { const e = new Error(x.name === 'AbortError' ? 'Ses çözümleme zaman aşımına uğradı.' : 'API’ye ulaşılamadı.'); e.status = 0; e.detail = e.message; throw e; }
    if (r.ok) return ((await r.json()).text || '').trim();
    const e = new Error('HTTP ' + r.status);
    e.status = r.status;
    try { e.detail = (await r.json()).detail; } catch (x) { /* gövde yok */ }
    throw e;
  }

  /* Bas-konuş düğmesi: basılı tutunca kayıt, bırakınca metin input'a. Sunucu açıksa Transcribe, değilse tarayıcı.
     o: { button, input, base, append (önceki metne ekle), notify(ileti) } */
  function pushToTalk(o) {
    const SR = browserSR(), b = o.button, notify = o.notify || ((m) => console.warn(m));
    let held = false, session = null, rec = null, prev = '';
    const write = (t) => { o.input.value = prev + t; };
    const recording = (on) => b.classList.toggle('record', on);
    const busy = (on) => {
      if (on) { b.dataset.label = b.innerHTML; b.textContent = 'Çözümleniyor…'; } else if (b.dataset.label != null) { b.innerHTML = b.dataset.label; delete b.dataset.label; }
      b.disabled = on; o.input.placeholder = on ? 'çözümleniyor…' : (o.input.dataset.placeholder ?? o.input.placeholder);
    };
    o.input.dataset.placeholder ??= o.input.placeholder;
    serverReady(o.base).then((ok) => { if (!ok && !SR) b.hidden = true; });

    function startBrowser() {
      rec = new SR(); rec.lang = 'tr-TR'; rec.interimResults = true; rec.continuous = true;
      rec.onresult = (ev) => { let t = ''; for (let i = 0; i < ev.results.length; i++) t += ev.results[i][0].transcript; write(t); };
      rec.onerror = (ev) => notify('Ses tanıma kullanılamıyor (' + (ev.error || 'hata') + '). Notu yazabilirsiniz.');
      rec.onend = () => { recording(false); rec = null; };
      rec.start(); recording(true);
    }
    async function startServer() {
      const s = await start();
      if (!held) { s.stop(); return; } // izin penceresi açıkken bırakıldı: kaydı at
      session = s; recording(true);
    }
    async function finishServer() {
      const s = session;
      session = null; recording(false);
      if (!s) return;
      busy(true);
      let t = '', err = null;
      try { t = await transcribe(o.base, await s.stop()); } catch (e) { err = e; }
      busy(false);
      if (t) write(t);
      else if (!err) notify('Ses anlaşılamadı; tekrar deneyin ya da notu yazın.');
      else if (SR) { fallback(); notify((err.detail || 'Sunucu ses tanıması kullanılamadı.') + ' Tarayıcı tanımasına geçildi; tekrar basılı tutup konuşun.'); }
      else notify(err.detail || err.message || 'Ses çözümlenemedi.');
    }
    b.addEventListener('pointerdown', async (e) => {
      e.preventDefault();
      if (held || b.disabled) return;
      held = true;
      prev = o.append && o.input.value.trim() ? o.input.value.trim() + ' ' : '';
      try {
        if (await serverReady(o.base)) await startServer();
        else if (SR && held) startBrowser();
      } catch (err) {
        recording(false);
        notify(err && err.name === 'NotAllowedError' ? 'Mikrofon izni yok; notu yazabilirsiniz.' : 'Ses kaydı başlatılamadı; notu yazabilirsiniz.');
      }
    });
    const up = () => { if (!held) return; held = false; if (rec) rec.stop(); else finishServer(); };
    ['pointerup', 'pointerleave', 'pointercancel'].forEach((ev) => b.addEventListener(ev, up));
  }
  function fallback() { server = false; } // bu oturumda tarayıcı tanımasına geç

  window.CMListen = {
    canRecord, browserSR, serverReady, start, transcribe, pushToTalk, fallback,
    available: () => canRecord() || !!browserSR(),
    get server() { return server; },
  };
})();
