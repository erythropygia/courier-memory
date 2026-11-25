/* Sahne 3–7 ortak yardımcıları: API (yoksa kayıtlı yanıt), ajan izi satırı, ses, pano, etiket işaretleri.
   Kayıtlı yanıtlar: data/fallback.json (tools/record_fallback.py; anahtar "GET /api/..." ya da "POST /api/...#ad"). */
(function (CM) {
  // API tabanı: ?api= verilmişse o; yoksa sayfa bir ters vekilin arkasındaysa (ör. /proxy/<port>/) o önek.
  CM.API = new URLSearchParams(location.search).get('api') || (location.pathname.match(/^(.*?\/proxy\/\d+)\//) || [])[1] || '';
  const status = (CM.apiStatus = { offline: new URLSearchParams(location.search).has('record'), mod: '' });
  let fallback = null;

  async function timed(url, opt = {}, ms = 8000) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), ms);
    try { return await fetch(url, { ...opt, signal: ctrl.signal }); } finally { clearTimeout(t); }
  }
  CM.timed = timed;
  async function loadFallback() {
    if (!fallback) fallback = await fetch('data/fallback.json').then((r) => r.json()).catch(() => ({}));
    return fallback;
  }

  /* yol: "/api/..."; govde: POST gövdesi (yoksa GET); ad: aynı yola farklı gövdeli POST'ların kayıt adı.
     HTTP hatası (4xx/5xx) hata olarak döner; ağ hatası/zaman aşımı → kayıtlı yanıt (durum.yok = true). */
  CM.api = async function (path, body, { name = '', ms = 9000 } = {}) {
    const key = (body ? 'POST ' : 'GET ') + path + (name ? '#' + name : '');
    if (!status.offline) {
      try {
        const opt = body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {};
        const r = await timed(CM.API + path, opt, ms);
        if (r.ok) return await r.json();
        const e = new Error(`${path}: HTTP ${r.status}`);
        e.status = r.status;
        try { e.detail = (await r.json()).detail; } catch (x) { /* gövde yok */ }
        throw e;
      } catch (e) {
        if (e.status) throw e;
        console.warn('API yok, kayıtlı yanıtlar kullanılıyor:', e);
        status.offline = true;
      }
    }
    const y = await loadFallback();
    if (key in y) return JSON.parse(JSON.stringify(y[key]));
    const e = new Error('Kayıtlı yanıt yok: ' + key);
    e.noRecord = true;
    throw e;
  };
  // mod rozeti: "Mod: mock · kurallı yedek" ya da "API yok · kayıtlı yanıt"
  CM.writeMode = async function (el) {
    if (!status.mod && !status.offline) {
      try { status.mod = (await CM.api('/api/status')).mode; } catch (e) { /* aşağıda */ }
    }
    const name = { mock: 'mock · kurallı yedek', live: 'canlı · LLM', record: 'canlı · kayıt', replay: 'kayıttan · LLM' }[status.mod] || status.mod;
    const m = el || CM.$('mod');
    m.textContent = status.offline ? 'API yok · kayıtlı yanıt' : 'Mod: ' + name;
    m.classList.toggle('live', !status.offline && (status.mod === 'live' || status.mod === 'record'));
  };

  // ------------------------------------------------------------ ajan izi (Orkestratör / Hasat aynı biçim, docs/sozlesmeler.md §5)
  const shortOk = (v) => typeof v !== 'object' || (Array.isArray(v) && v.every((x) => typeof x !== 'object'));
  CM.traceRow = function (e) {
    const kay = { rule: 'KURAL', llm: 'LLM', human: 'İNSAN' }[e.source] || (e.source || '').toUpperCase();
    let text = '';
    switch (e.type) {
      case 'start': text = e.task === 'ask' ? `Soru: ${e.question || ''}` : `Koşu başladı · gün ${e.day} · ${{ plan: 'günü planla', harvest: 'hasat' }[e.task] || e.task || ''}`; break;
      case 'decision': text = e.text; break;
      case 'tool': {
        const g = Object.entries(e.input || {}).filter(([, v]) => v !== '' && v != null && !(Array.isArray(v) && !v.length) && shortOk(v))
          .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(',') : v}`).join(', ');
        text = `${e.tool}(${g.length > 34 ? g.slice(0, 33) + '…' : g})`; break;
      }
      case 'result': text = '← ' + (e.summary || ''); break;
      case 'error': text = `${e.tool}: ${e.text}`; break;
      case 'fallback': text = e.text; break;
      case 'proposal': text = 'Gerekçeli plan hazır; acil durum denetimi'; break;
      case 'escalation': text = 'Acil durum, müdüre eskale: ' + (e.reasons || []).map((r) => r.text).join(' · '); break;
      case 'auto_decision': text = e.text || 'Acil durum yok: plan müdüre gitmeden kesinleşti'; break;
      case 'awaiting_approval': text = 'Acil durum: müdür kararı bekleniyor'; break;
      case 'human_decision': text = `Müdür kararı: ${{ approval: 'onaylandı', ret: 'reddedildi', edit: 'düzenlendi' }[e.decision] || e.decision}${e.note ? ' · ' + e.note : ''}`; break;
      case 'response': text = 'Yanıt: ' + (e.response || ''); break;
      case 'done': text = e.text || ({ finalized: 'Plan kesinleşti', rejected: 'Plan reddedildi', error: 'Hata' }[e.status] || 'Bitti'); break;
      default: text = e.text || e.type;
    }
    if ((e.type === 'decision' || e.type === 'response') && text.length > 150) text = text.slice(0, 148) + '…';
    const li = document.createElement('li');
    li.className = 't-' + e.type;
    li.innerHTML = `<span class="k ${e.source || ''}">${kay}</span><span></span>`;
    li.lastChild.textContent = text;
    return li;
  };
  // izi panele sırayla ekle (eskiler soluk); baslik: panelin üst yazısı
  CM.openTrace = function (title) {
    CM.$('trace').hidden = false;
    CM.$('trace').querySelector('.trace-head span').textContent = title || 'Orkestratör izi';
    requestAnimationFrame(() => CM.$('trace').classList.add('open'));
  };
  CM.closeTrace = function () { CM.$('trace').classList.remove('open'); CM.$('trace-wait').hidden = true; };
  CM.writeTrace = function (events, { expire = true, next = true, duration = 220 } = {}) {
    const ul = CM.$('trace-list');
    if (expire) [...ul.children].forEach((li) => li.classList.add('legacy'));
    const no = (CM.writeTrace.no = (CM.writeTrace.no || 0) + 1);
    events.forEach((e, j) => {
      const li = CM.traceRow(e);
      ul.appendChild(li);
      if (next) setTimeout(() => no === CM.writeTrace.no && li.classList.add('view'), 80 + j * duration);
      else li.classList.add('view');
    });
    while (ul.children.length > 26) ul.removeChild(ul.firstChild);
    return new Promise((r) => setTimeout(r, next ? 80 + events.length * duration : 0));
  };
  CM.waitTrace = (b) => { CM.$('trace-wait').hidden = !b; };

  // ------------------------------------------------------------ ses: önce /api/ses (Polly), 501/hata → tarayıcı (tr-TR)
  CM.speech = (function () {
    let noServer = false, trVoice = null, active = null;
    const selectVoice = () => {
      if (!('speechSynthesis' in window)) return null;
      trVoice = speechSynthesis.getVoices().find((v) => /^tr(-|_|$)/i.test(v.lang)) || null;
      return trVoice;
    };
    if ('speechSynthesis' in window) { selectVoice(); speechSynthesis.addEventListener && speechSynthesis.addEventListener('voiceschanged', selectVoice); }
    function browser(text, d) {
      return new Promise((res) => {
        if (!('speechSynthesis' in window)) { setTimeout(res, Math.min(5000, 600 + text.length * 50)); return; }
        speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(text);
        u.lang = 'tr-TR';
        if (trVoice || selectVoice()) u.voice = trVoice;
        u.rate = 1.03;
        const guv = setTimeout(res, 2500 + text.length * 95); // bazı tarayıcılar 'end' olayını kaçırır
        u.onend = u.onerror = () => { clearTimeout(guv); res(); };
        if (!d.cancel) speechSynthesis.speak(u); else res();
      });
    }
    async function server(text, d) {
      const r = await fetch(CM.API + '/api/speech?text=' + encodeURIComponent(text.slice(0, 600)));
      if (!r.ok || !(r.headers.get('content-type') || '').startsWith('audio')) throw new Error('sunucu sesi yok');
      const url = URL.createObjectURL(await r.blob());
      if (d.cancel) return;
      await new Promise((res) => { const a = new Audio(url); d.a = a; a.onended = a.onerror = res; a.play().catch(res); });
    }
    return {
      say(text) {
        this.cancel();
        const d = (active = { cancel: false });
        const p = (async () => {
          if (!noServer && !CM.apiStatus.offline) {
            try { await server(text, d); return; } catch (e) { noServer = true; }
          }
          await browser(text, d);
        })();
        return p;
      },
      cancel() {
        if (active) { active.cancel = true; if (active.a) active.a.pause(); }
        if ('speechSynthesis' in window) speechSynthesis.cancel();
      },
    };
  })();

  // ------------------------------------------------------------ pano (perde üstü içerik alanı) ve küçük DOM yardımcıları
  CM.board = function (html, css_class) {
    const p = CM.$('board');
    p.className = css_class || '';
    p.innerHTML = html || '';
    if (html) requestAnimationFrame(() => requestAnimationFrame(() => p.classList.add('view')));
    return p;
  };
  CM.side = function (html, css_class) {          // sağ yan panel (iz paneliyle aynı yerde; kurye telefonu, kartlar)
    const p = CM.$('side');
    p.className = css_class || '';
    p.innerHTML = html || '';
    if (html) requestAnimationFrame(() => requestAnimationFrame(() => p.classList.add('open')));
    return p;
  };
  // hızlı güncellenen rakam (oynatma sırasında): giriş animasyonu yok
  CM.figureMoment = function (stats, note) {
    CM.figure(stats, note);
    CM.$('figure').querySelectorAll('.stat, .note').forEach((e) => { e.style.transition = 'none'; e.classList.add('view'); });
  };
  CM.marked = (v, nd = 0) => (v > 0 ? '+' : v < 0 ? '−' : '±') + CM.count(Math.abs(v), nd);
  CM.curtain = (open) => CM.$('curtain').classList.toggle('open', !!open);
  CM.escape = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  CM.hhmm = (mins) => { const m = Math.round(mins); return `${String(Math.floor(m / 60) % 24).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`; };
  CM.deleteMark = (items) => { for (const m of items.splice(0)) m.remove(); };
  CM.labelEl = function (top, alt, css_class) {
    const el = document.createElement('div');
    el.className = 'label ' + (css_class || '');
    el.innerHTML = `${CM.escape(top)}${alt ? `<small>${CM.escape(alt)}</small>` : ''}`;
    return el;
  };
  CM.ringEl = function (css_class) {
    const el = document.createElement('div');
    el.className = 'ring ' + (css_class || '');
    return el;
  };
  CM.QUIRK = { back_entry: 'Arka giriş', saturday_closed: 'Cumartesi kapalı', lunch_break: 'Öğle arası', safety: 'Güvenlik', bell: 'Zil',
    position_wrong: 'Konum hatalı', reception: 'Resepsiyon', temporary_closed: 'Geçici kapalı', roadwork: 'Yol çalışması',
    park: 'Park', building_access: 'Bina erişimi', directions: 'Adres tarifi', animal: 'Hayvan', other_info: 'Not' };
  CM.TYPE = { senior: 'kıdemli', reserve: 'yedek', new: 'yeni kurye', borrowed: 'komşu şubeden' };

  // GET önbelleği (meta, özet gibi değişmeyen yanıtlar) ve demo seçimleri (data/fallback.json → demo; tools/record_fallback.py üretir)
  const cache = new Map();
  CM.al = (path) => { if (!cache.has(path)) cache.set(path, CM.api(path).catch((e) => { cache.delete(path); throw e; })); return cache.get(path); };
  CM.demo = async () => (await loadFallback()).demo || {};

  // sim adresi → Beykoz konumu (data/sim_mapping.json; Sahne 2 ile aynı eşleme)
  let match = null;
  CM.mapping = async () => (match ||= await fetch('data/sim_mapping.json').then((r) => r.json()));
  CM.position = (address) => { const q = match && match.address['a' + address]; return q ? [q[1], q[0]] : null; }; // [lng, lat]
  let s2 = null;
  CM.scene2Data = async () => (s2 ||= await fetch('data/scene2.json').then((r) => r.json()));
})(window.CM);
