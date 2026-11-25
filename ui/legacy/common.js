/* Courier Memory · ortak yardımcılar: biçim, API, DOM, ipucu kutusu, ses.
   Dış bağımlılık yok. Diğer betikler CM ad alanını kullanır. */
'use strict';

const CM = (window.CM = window.CM || {});

/* ------------------------------------------------------------------ sözlük */
CM.TYPE = { senior: 'kıdemli', reserve: 'yedek', new: 'yeni', borrowed: 'ödünç' };
CM.REASON = {
  recipient_absent: 'Alıcı yok',
  address_not_found: 'Adres bulunamadı',
  closed: 'Kapalı',
  entry_failed: 'Giriş yapılamadı',
  recipient_unreachable: 'Alıcıya ulaşılamadı',
  wrong_deferral: 'Yanlış erteleme',
  other: 'Diğer',
};
CM.QUIRK = {
  back_entry: 'Arka giriş',
  saturday_closed: 'Cumartesi kapalı',
  lunch_break: 'Öğle arası',
  safety: 'Güvenlik',
  bell: 'Zil',
  position_wrong: 'Konum hatalı',
  reception: 'Resepsiyon',
  temporary_closed: 'Geçici kapalı',
  roadwork: 'Yol çalışması',
  park: 'Park',
  building_access: 'Bina erişimi',
  directions: 'Adres tarifi',
  animal: 'Hayvan',
  other_info: 'Not',
};
CM.ADDRESS_TYPE = { apartment: 'Apartman', workplace: 'İş yeri', site: 'Site', house: 'Müstakil ev', collection_point: 'Toplu teslim noktası' };
CM.BLOCK_TYPE = { busy_residential: 'Yoğun konut', site: 'Site', industrial: 'Sanayi', business_center: 'İş merkezi', rural: 'Kırsal' };
CM.MOD = { mock: 'Deterministik yedek', live: 'Canlı LLM', record: 'Canlı · kayıt', replay: 'Kayıttan oynatma' };
CM.NOTE_STATUS = {
  saved: 'Kaydedildi',
  updated: 'Güncellendi',
  noise: 'Gürültü · kaydedilmedi',
  uncertain: 'Belirsiz · soru soruldu',
  rejected: 'Reddedildi',
};
CM.DAY_NAME = { Pzt: 'Pazartesi', Sal: 'Salı', 'Çar': 'Çarşamba', Per: 'Perşembe', Cum: 'Cuma', Cmt: 'Cumartesi' };
CM.STOP_FIELDS = ['address', 'lat', 'lng', 'n', 'eta', 'ok', 'fail', 'deferred', 'reason', 'hint', 'unfamiliar'];

/* Renkler (dataviz: doğrulanmış kategorik yuvalar; style.css ile aynı değerler) */
CM.COLOR = {
  arm: { D: '#2a78d6', C: '#eb6834', B: '#1baf7a', A: '#eda100' },
  type: { senior: '#9a988f', reserve: '#e87ba4', new: '#008300', borrowed: '#6250d6' },
  fails: '#d03b3b',
  deferred: '#fab219',
  ink: '#0b0b0b',
  secondary: '#52514e',
  faded: '#898781',
  grid: '#e1e0d9',
  axis: '#c3c2b7',
  surface: '#fcfcfb',
  gray: '#b9b7ae',
};

/* ------------------------------------------------------------------ biçim (Türkçe) */
const _nfCache = new Map();
CM.nf = function (x, d = 0) {
  if (x === null || x === undefined || Number.isNaN(+x)) return '–';
  let f = _nfCache.get(d);
  if (!f) {
    f = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: d, maximumFractionDigits: d });
    _nfCache.set(d, f);
  }
  return f.format(+x).replace('-', '−');
};
CM.pct = (x, d = 1) => (x === null || x === undefined || Number.isNaN(+x) ? '–' : '%' + CM.nf(100 * x, d));
CM.marked = (x, d = 1) => (x === null || x === undefined ? '–' : (x > 0 ? '+' : x < 0 ? '' : '±') + CM.nf(x, d));
CM.markedPct = (x, d = 1) =>
  x === null || x === undefined ? '–' : (x > 0 ? '+' : x < 0 ? '−' : '±') + '%' + CM.nf(Math.abs(x), d);
/* TL: büyük değerler kısaltılır (1,2 mn TL), küçükler ondalıklı */
CM.tl = function (x, d) {
  if (x === null || x === undefined || Number.isNaN(+x)) return '–';
  const a = Math.abs(+x);
  if (a >= 1e9) return CM.nf(x / 1e9, 1) + ' mlr TL';
  if (a >= 1e6) return CM.nf(x / 1e6, 1) + ' mn TL';
  if (a >= 1000) return CM.nf(x, 0) + ' TL';
  if (d === undefined) d = Number.isInteger(+x) ? 0 : a < 10 ? 2 : 1;
  return CM.nf(x, d) + ' TL';
};
/* anthropic.claude-opus-5-5 → Opus 5.5 */
CM.modelShort = function (id) {
  const m = /claude-([a-z]+)-(\d+)-(\d+)/i.exec(String(id || ''));
  return m ? m[1].charAt(0).toUpperCase() + m[1].slice(1) + ' ' + m[2] + '.' + m[3] : String(id || '–');
};
CM.times = (x) => (x === null || x === undefined ? '–' : CM.nf(x, x >= 100 ? 0 : 1) + '×');
CM.hhmm = function (m) {
  if (m === null || m === undefined || Number.isNaN(+m)) return '–';
  const t = Math.round(+m);
  return String(Math.floor(t / 60) % 24).padStart(2, '0') + ':' + String(t % 60).padStart(2, '0');
};
CM.dayName = function (meta, day) {
  const w = meta && meta.weekday_names ? meta.weekday_names[day % 6] : '';
  return w || '';
};

/* ------------------------------------------------------------------ DOM */
CM.h = function (tag, attrs, ...kids) {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'text') el.textContent = v;
      else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
      else if (k === 'dataset') Object.assign(el.dataset, v);
      else el.setAttribute(k, v === true ? '' : v);
    }
  }
  CM.add(el, kids);
  return el;
};
CM.add = function (el, kids) {
  for (const k of kids.flat(Infinity)) {
    if (k === null || k === undefined || k === false) continue;
    el.appendChild(k instanceof Node ? k : document.createTextNode(String(k)));
  }
  return el;
};
CM.clear = function (el, ...kids) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return CM.add(el, kids);
};
CM.$ = (sel, root = document) => root.querySelector(sel);
CM.$$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const SVGNS = 'http://www.w3.org/2000/svg';
CM.s = function (tag, attrs, ...kids) {
  const el = document.createElementNS(SVGNS, tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'text') el.textContent = v;
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v);
    }
  }
  for (const k of kids.flat(Infinity)) {
    if (k === null || k === undefined || k === false) continue;
    el.appendChild(k instanceof Node ? k : document.createTextNode(String(k)));
  }
  return el;
};

/* Ajan metni: güvenli biçimde paragraf + **kalın** desteği (innerHTML yok). */
CM.text = function (str, cls) {
  const wrap = CM.h('div', { class: cls || 'text' });
  const paras = String(str || '').split(/\n{2,}/);
  for (const p of paras) {
    const el = CM.h('p');
    const lines = p.split('\n');
    lines.forEach((line, li) => {
      const parts = line.replace(/^\s*[-*•]\s+/, '• ').split(/(\*\*[^*]+\*\*)/);
      for (const part of parts) {
        if (/^\*\*[^*]+\*\*$/.test(part)) el.appendChild(CM.h('strong', { text: part.slice(2, -2) }));
        else if (part) el.appendChild(document.createTextNode(part));
      }
      if (li < lines.length - 1) el.appendChild(CM.h('br'));
    });
    wrap.appendChild(el);
  }
  return wrap;
};

/* Küçük çizgi ikonları (emoji yazı tipine bağımlı olmamak için SVG) */
const ICON = {
  speaker: ['M4 9.5v5h3.5l4.5 4v-13l-4.5 4z', 'M15.5 9a4 4 0 0 1 0 6', 'M18 6.5a7.5 7.5 0 0 1 0 11'],
  microphone: ['M9.5 6a2.5 2.5 0 0 1 5 0v5a2.5 2.5 0 0 1-5 0z', 'M6 11a6 6 0 0 0 12 0', 'M12 17v3.5'],
  position: ['M12 21s-6-5.6-6-10.5a6 6 0 0 1 12 0C18 15.4 12 21 12 21z', 'M12 12.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4z'],
  shield: ['M12 3.5l7 2.8v4.9c0 4.6-3 7.6-7 9.3-4-1.7-7-4.7-7-9.3V6.3z', 'M9 12l2.2 2.2L15.5 10'],
};
CM.icon = function (name, boy) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', boy || 15);
  svg.setAttribute('height', boy || 15);
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('class', 'icon');
  for (const d of ICON[name] || []) {
    const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    p.setAttribute('d', d);
    svg.appendChild(p);
  }
  return svg;
};

/* Sayıya iyelik + bulunma eki: 100 → ’ünde, 85 → ’inde, 60 → ’ında */
CM.locativeSuffix = function (n) {
  n = Math.abs(Math.round(n));
  const last = n % 10;
  if (last) return { 1: '’inde', 2: '’sinde', 3: '’ünde', 4: '’ünde', 5: '’inde', 6: '’sında', 7: '’sinde', 8: '’inde', 9: '’unda' }[last];
  const on = Math.floor(n / 10) % 10;
  if (on) return { 1: '’unda', 2: '’sinde', 3: '’unda', 4: '’ında', 5: '’sinde', 6: '’ında', 7: '’inde', 8: '’inde', 9: '’ında' }[on];
  if (n === 0) return '’ında';
  return n % 1000 === 0 ? '’inde' : '’ünde';
};

CM.typeBadge = function (kind) {
  const k = kind || 'senior';
  return CM.h('span', { class: 'badge type type-' + k }, CM.h('i', { class: 'point' }), CM.TYPE[k] || k);
};

/* ------------------------------------------------------------------ API */
CM.event = new EventTarget();

function errorText(data, status) {
  if (data && typeof data === 'object') {
    const d = data.detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) return d.map((x) => (x && x.msg) || JSON.stringify(x)).join('; ');
  }
  if (typeof data === 'string' && data.length < 200 && data.trim()) return data;
  return 'Sunucu hatası (HTTP ' + status + ')';
}

CM.api = async function (path, { method = 'GET', body, timeout = 180000 } = {}) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeout);
  try {
    let res;
    try {
      res = await fetch(path, {
        method,
        headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: ctrl.signal,
      });
    } catch (e) {
      const err = new Error(e.name === 'AbortError' ? 'İstek zaman aşımına uğradı.' : 'API’ye ulaşılamadı.');
      err.status = 0;
      throw err;
    }
    const ct = res.headers.get('content-type') || '';
    const data = ct.includes('json') ? await res.json().catch(() => null) : await res.text();
    if (!res.ok) {
      const err = new Error(errorText(data, res.status));
      err.status = res.status;
      err.data = data;
      throw err;
    }
    if (data && typeof data === 'object' && !Array.isArray(data) && ('degraded' in data || 'mode' in data)) {
      CM.event.dispatchEvent(new CustomEvent('agent', { detail: data }));
    }
    return data;
  } finally {
    clearTimeout(t);
  }
};

/* Basit önbellekli GET */
const _getCache = new Map();
CM.fetch = function (path) {
  if (!_getCache.has(path)) {
    const p = CM.api(path).catch((e) => {
      _getCache.delete(path);
      throw e;
    });
    _getCache.set(path, p);
  }
  return _getCache.get(path);
};

/* ------------------------------------------------------------------ ipucu kutusu (tooltip) */
CM.hint = (function () {
  let el = null;
  function box() {
    if (!el) {
      el = CM.h('div', { class: 'tooltip', role: 'tooltip' });
      document.body.appendChild(el);
    }
    return el;
  }
  return {
    show(x, y, content) {
      const k = box();
      CM.clear(k, content);
      k.style.display = 'block';
      const r = k.getBoundingClientRect();
      let lx = x + 14;
      let ly = y + 14;
      if (lx + r.width > window.innerWidth - 8) lx = x - r.width - 14;
      if (ly + r.height > window.innerHeight - 8) ly = y - r.height - 14;
      k.style.left = Math.max(4, lx) + 'px';
      k.style.top = Math.max(4, ly) + 'px';
    },
    hide() {
      if (el) el.style.display = 'none';
    },
  };
})();

/* Tooltip içeriği: değer önde, ad arkada; seri anahtarı kısa çizgi. */
CM.hintRow = function (color, value, name, cls) {
  return CM.h(
    'div',
    { class: 'tt-row ' + (cls || '') },
    color ? CM.h('i', { class: 'tt-key', style: { background: color } }) : null,
    CM.h('b', { text: value }),
    name ? CM.h('span', { text: name }) : null
  );
};

/* ------------------------------------------------------------------ bildirim (toast) */
CM.notify = function (message, type) {
  let container = CM.$('#notifications');
  if (!container) {
    container = CM.h('div', { id: 'notifications' });
    document.body.appendChild(container);
  }
  const el = CM.h('div', { class: 'notification ' + (type || '') }, message);
  container.appendChild(el);
  setTimeout(() => el.classList.add('leaving'), 3600);
  setTimeout(() => el.remove(), 4200);
};

/* ------------------------------------------------------------------ ses
   Önce sunucu sesi (/api/ses, Polly). 501 ya da hata → tarayıcı speechSynthesis (tr-TR).
   soyle(metin) → { bitti: Promise, iptal() } */
CM.speech = (function () {
  let backend = null; // null: bilinmiyor, 'sunucu' | 'tarayici'
  let active = null;
  const blobCache = new Map();
  let trVoice = null;

  function selectVoice() {
    if (!('speechSynthesis' in window)) return null;
    const v = window.speechSynthesis.getVoices();
    trVoice = v.find((x) => /^tr(-|_|$)/i.test(x.lang)) || null;
    return trVoice;
  }
  if ('speechSynthesis' in window) {
    selectVoice();
    window.speechSynthesis.addEventListener && window.speechSynthesis.addEventListener('voiceschanged', selectVoice);
  }

  function splitSentences(text) {
    const parts = String(text)
      .replace(/\s+/g, ' ')
      .match(/[^.!?…]+[.!?…]*\s*/g);
    return (parts || [text]).map((s) => s.trim()).filter(Boolean);
  }

  function browserSpeak(text, status) {
    return new Promise((resolve) => {
      if (!('speechSynthesis' in window)) {
        setTimeout(resolve, Math.min(6000, 600 + text.length * 55));
        return;
      }
      const synth = window.speechSynthesis;
      synth.cancel();
      const parts = splitSentences(text);
      let i = 0;
      const next = () => {
        if (status.cancel || i >= parts.length) {
          resolve();
          return;
        }
        const u = new SpeechSynthesisUtterance(parts[i++]);
        u.lang = 'tr-TR';
        if (trVoice || selectVoice()) u.voice = trVoice;
        u.rate = 1.02;
        let done = false;
        const resume = () => {
          if (done) return;
          done = true;
          clearTimeout(safety);
          next();
        };
        // Bazı tarayıcılar 'end' olayını kaçırır: süre tahminiyle güvenlik zamanlayıcısı.
        const safety = setTimeout(resume, 2500 + u.text.length * 110);
        u.onend = resume;
        u.onerror = resume;
        synth.speak(u);
      };
      next();
    });
  }

  async function serverSpeak(text, status) {
    let url = blobCache.get(text);
    if (!url) {
      const res = await fetch('/api/speech?text=' + encodeURIComponent(text.slice(0, 600)));
      const ct = res.headers.get('content-type') || '';
      if (!res.ok || !ct.startsWith('audio')) {
        const e = new Error('sunucu sesi yok');
        e.status = res.status;
        throw e;
      }
      url = URL.createObjectURL(await res.blob());
      blobCache.set(text, url);
    }
    if (status.cancel) return;
    await new Promise((resolve) => {
      const a = new Audio(url);
      status.audio = a;
      a.onended = resolve;
      a.onerror = resolve;
      a.play().catch(resolve);
    });
  }

  function say(text) {
    cancel();
    const status = { cancel: false, audio: null };
    const done = (async () => {
      if (!text) return;
      if (backend !== 'browser') {
        try {
          await serverSpeak(text, status);
          backend = 'server';
          return;
        } catch (e) {
          backend = 'browser';
        }
      }
      if (!status.cancel) await browserSpeak(text, status);
    })();
    active = {
      done,
      cancel() {
        status.cancel = true;
        if (status.audio) {
          status.audio.pause();
          status.audio.dispatchEvent(new Event('ended'));
        }
        if ('speechSynthesis' in window) window.speechSynthesis.cancel();
      },
    };
    const ben = active;
    done.finally(() => {
      if (active === ben) active = null;
    });
    return active;
  }

  function cancel() {
    if (active) active.cancel();
    active = null;
  }

  return {
    say,
    cancel,
    get speaking() {
      return !!active;
    },
    get source() {
      return backend === 'server' ? 'Sunucu sesi' : backend === 'browser' ? 'Tarayıcı sesi' : '';
    },
  };
})();
