/* Courier Memory · demo arayüzü (tek sayfa). Yalnız /api/... uç noktalarını kullanır (docs/sozlesmeler.md §4). */
'use strict';

(function () {
  const CM = window.CM;
  const { h, clear, $, $$, nf, pct } = CM;
  const R = CM.COLOR;
  const ARMS = ['A', 'B', 'C', 'D'];

  const S = {
    meta: null,
    proj: null,
    day: null,
    screen: 'branch',
    snap(arm, day) {
      return CM.fetch(`/api/day/${arm}/${day}`);
    },
  };

  /* ====================================================================== yardımcılar */
  function stopFields(fields) {
    const F = {};
    (fields || CM.STOP_FIELDS).forEach((f, i) => (F[f] = i));
    return F;
  }
  function stopObject(arr, F, i) {
    return {
      i,
      address: arr[F.address],
      lat: arr[F.lat],
      lng: arr[F.lng],
      n: arr[F.n],
      eta: arr[F.eta],
      ok: arr[F.ok],
      fail: arr[F.fail],
      deferred: arr[F.deferred],
      reason: arr[F.reason],
      hint: arr[F.hint],
      unfamiliar: arr[F.unfamiliar],
    };
  }
  function stopStatus(d) {
    if (d.fail > 0) return 'fail';
    if (d.deferred > 0 && !d.ok) return 'deferred';
    return 'ok';
  }
  function resultText(d) {
    if (d.fail > 0) return 'Başarısız' + (d.reason ? ': ' + (CM.REASON[d.reason] || d.reason) : '');
    if (d.deferred > 0 && !d.ok) return 'Planlı erteleme (kapalı olduğu biliniyordu)';
    if (d.deferred > 0) return 'Teslim edildi · ' + d.deferred + ' gönderi ertelendi';
    return 'İlk denemede teslim';
  }
  function dayLabel(day) {
    const w = CM.dayName(S.meta, day);
    return `Gün ${day}` + (w ? ` · ${CM.DAY_NAME[w] || w}` : '');
  }
  function loading(text) {
    return h('div', { class: 'loading' }, h('span', { class: 'returning', 'aria-hidden': 'true' }), text || 'Yükleniyor…');
  }
  function errorBox(e, extra) {
    return h('div', { class: 'error-box', role: 'alert' }, h('b', { text: 'Hata' }), ' ', e && e.message ? e.message : String(e), extra ? h('div', { class: 'alt', text: extra }) : null);
  }
  function stepsList(steps, title) {
    const items = (steps || []).filter(Boolean);
    const d = h('details', { class: 'steps' }, h('summary', null, (title || 'Ajan ne yaptı?') + ` (${items.length} adım)`));
    if (!items.length) {
      d.appendChild(h('div', { class: 'alt', text: 'Bu yanıt için araç çağrısı yapılmadı.' }));
      return d;
    }
    const ol = h('ol');
    for (const a of items) {
      const input = a.input && Object.keys(a.input).length ? JSON.stringify(a.input) : '';
      ol.appendChild(
        h('li', null, h('code', { text: a.tool || '?' }), a.summary ? h('span', { class: 'step-summary', text: ' → ' + a.summary }) : null, input ? h('div', { class: 'step-input', text: input }) : null)
      );
    }
    d.appendChild(ol);
    return d;
  }

  /* ====================================================================== üst bar */
  function modBadge(mode, error) {
    const el = $('#mod');
    if (!el) return;
    if (error) {
      el.className = 'badge mod closed';
      clear(el, h('i', { class: 'point' }), 'API yok');
      el.title = error.message || '';
      return;
    }
    el.className = 'badge mod mod-' + mode;
    clear(el, h('i', { class: 'point' }), 'Mod: ' + (CM.MOD[mode] || mode));
    const d = S.status || {};
    const md = d.models || {};
    const mdText = Object.keys(md).length ? 'Modeller: ' + [['assignment', 'Atama'], ['memory', 'Hafıza'], ['briefing', 'Brifing']].filter(([k]) => md[k]).map(([k, name]) => `${name} ${CM.modelShort(md[k])}`).join(' · ') : '';
    el.title = [mdText, !mdText && d.model ? 'Model: ' + d.model : '', d.region ? 'Bölge: ' + d.region : '', d.run_id ? 'Çalıştırma: ' + d.run_id : '', d.cassettes !== undefined ? 'Kayıt: ' + d.cassettes : '']
      .filter(Boolean)
      .join('\n');
  }

  async function loadStatus() {
    try {
      S.status = await CM.api('/api/status');
      modBadge(S.status.mode);
    } catch (e) {
      modBadge(null, e);
    }
  }

  CM.event.addEventListener('agent', (e) => {
    const d = e.detail || {};
    const el = $('#degraded');
    if (el) {
      el.hidden = !d.degraded;
      el.title = d.degraded ? 'Canlı LLM yanıt vermedi; deterministik yedek kullanıldı.' + (d.error ? '\n' + d.error : '') : '';
    }
  });

  function daySelector() {
    const sel = $('#day');
    clear(sel);
    const crit = S.meta.critical || {};
    for (const d of S.meta.eval_days || []) {
      const w = CM.dayName(S.meta, d);
      sel.appendChild(h('option', { value: d, text: `Gün ${d} · ${w}` + (d === crit.day ? ' · demo günü' : '') }));
    }
    sel.value = String(S.day);
    sel.addEventListener('change', () => adjustDay(+sel.value));
  }

  function adjustDay(d) {
    if (!(S.meta.eval_days || []).includes(d)) return;
    S.day = d;
    $('#day').value = String(d);
    SCREEN[S.screen].show();
  }

  const SCREEN = {};
  function showScreen(name) {
    if (!SCREEN[name]) name = 'branch';
    S.screen = name;
    for (const b of $$('.tabs [data-screen]')) {
      const on = b.dataset.screen === name;
      b.classList.toggle('active', on);
      b.setAttribute('aria-selected', on);
    }
    for (const select of $$('.screen')) select.classList.toggle('active', select.id === 'screen-' + name);
    if (location.hash !== '#' + name) history.replaceState(null, '', '#' + name);
    CM.hint.hide();
    if (name !== 'courier' && Courier.pause) {
      Courier.pause();
      CM.speech.cancel();
    }
    SCREEN[name].show();
  }

  /* ====================================================================== 1. ŞUBE */
  const Branch = {
    days: new Map(),
    st() {
      if (!this.days.has(S.day)) this.days.set(S.day, { proposal: null, assignment: null, total: null, previous: null, selected: null, chat: [], approved: false, loading: false });
      return this.days.get(S.day);
    },

    init() {
      this.map = new CM.MapView($('#branch-map'), {
        proj: S.proj,
        label: 'Günün kümeleri ve rotaları',
        onOver: (n, ev) => this.over(n, ev),
        onSelect: (n) => this.selectCluster(n ? n.route : null, true),
      });
      $('#btn-propose').addEventListener('click', () => this.propose());
      $('#btn-approve').addEventListener('click', () => this.approve());
      $('#branch-result').addEventListener('change', () => this.drawMap(false));
      $('#question-form').addEventListener('submit', (e) => {
        e.preventDefault();
        const q = $('#question').value.trim();
        if (q) this.ask(q);
      });
      clear(
        $('#branch-legend'),
        CM.mapLegend([
          { type: 'line', color: R.type.senior, text: 'Kıdemli' },
          { type: 'line', color: R.type.reserve, text: 'Yedek' },
          { type: 'line', color: R.type.new, text: 'Yeni' },
          { type: 'line', color: R.type.borrowed, text: 'Ödünç' },
          { type: 'point', status: 'ok', color: R.faded, text: 'Teslim' },
          { type: 'point', status: 'fail', text: 'Başarısız' },
          { type: 'point', status: 'deferred', text: 'Ertelendi' },
          { type: 'point', status: 'ok', hint: true, color: R.faded, text: 'İpuçlu durak' },
          { type: 'block', color: CM.BLOCK_TONE.busy_residential, text: 'Yoğun konut' },
          { type: 'block', color: CM.BLOCK_TONE.site, text: 'Site' },
          { type: 'block', color: CM.BLOCK_TONE.industrial, text: 'Sanayi' },
          { type: 'block', color: CM.BLOCK_TONE.business_center, text: 'İş merkezi' },
        ])
      );
    },

    async show() {
      if (this.drawnDay === S.day && this.snapD) return;
      this.drawnDay = S.day;
      const day = S.day;
      $('#branch-map-alt').textContent = dayLabel(day) + ' · ' + ((S.meta.arms && S.meta.arms.D) || 'Yeni yapı · çekirdek bölge + hafıza');
      this.drawPanel();
      try {
        const snap = await S.snap('D', day);
        if (day !== S.day) return;
        this.snapD = snap;
        this.F = stopFields(snap.stop_fields);
        this.drawMap(true);
      } catch (e) {
        clear($('#branch-map-status'), errorBox(e));
      }
    },

    assignedCourier(cluster) {
      const st = this.st();
      if (st.assignment) {
        const a = st.assignment.find((x) => +x.cluster === +cluster);
        if (a) return { id: a.courier, name: a.courier_name, type: a.courier_type };
      }
      const r = this.snapD && this.snapD.routes.find((x) => +x.route === +cluster);
      return r ? { id: r.courier, name: r.courier_name, type: r.courier_kind } : null;
    },

    drawMap(fit) {
      const snap = this.snapD;
      if (!snap) return;
      const result = $('#branch-result').checked;
      const F = this.F;
      const routes = snap.routes.map((r) => {
        const k = this.assignedCourier(r.route) || { name: r.courier_name, type: r.courier_kind };
        const type = k.type || 'senior';
        return {
          id: r.route,
          color: R.type[type] || R.type.senior,
          thickness: type === 'senior' ? 1.4 : 2.4,
          css_class: 'type-' + type,
          label: { text: k.name, bold: type !== 'senior' },
          data: r,
          stops: r.stops.map((a, i) => {
            const d = stopObject(a, F, i);
            return { lat: d.lat, lng: d.lng, status: result ? stopStatus(d) : 'ok', hint: !!d.hint, data: d };
          }),
        };
      });
      this.map.draw({ routes, depot: snap.depot || S.meta.depot, border: fit ? undefined : false });
      const st = this.st();
      if (st.selected !== null && st.selected !== undefined) this.map.highlight(st.selected);
      const dur = $('#branch-map-status');
      const top = snap.routes.reduce(
        (a, r) => {
          for (const s of r.stops) {
            a.stop++;
            a.fail += s[F.fail] > 0 ? 1 : 0;
            a.hint += s[F.hint] ? 1 : 0;
            a.unfamiliar += s[F.unfamiliar] ? 1 : 0;
          }
          return a;
        },
        { stop: 0, fail: 0, hint: 0, unfamiliar: 0 }
      );
      clear(dur, h('span', null, h('b', { text: nf(snap.routes.length) }), ' küme'), h('span', null, h('b', { text: nf(top.stop) }), ' durak'), h('span', null, h('b', { text: pct(1 - top.unfamiliar / Math.max(1, top.stop), 0) }), ' kendi bölgesinde'), h('span', null, h('b', { text: nf(top.hint) }), ' ipuçlu'), result ? h('span', null, h('b', { text: nf(top.fail) }), ' başarısız durak') : null);
    },

    over(n, ev) {
      if (!n) {
        this.map.highlight(null, 'hover');
        CM.hint.hide();
        return;
      }
      this.map.highlight(n.route, 'hover');
      const r = n.r;
      const d = n.data;
      const k = this.assignedCourier(r.route) || {};
      const hints = (r.hints && r.hints[String(d.address)]) || [];
      const content = [
        h('div', { class: 'tt-title' }, `Küme ${r.route} · `, k.name || r.courier_name, ' ', CM.typeBadge(k.type || r.courier_kind)),
        h('div', { class: 'tt-alt', text: `${nf(r.stops.length)} durak · ${nf(r.km, 1)} km · ${nf(r.minutes)} dk` }),
        k.id && k.id !== r.courier && $('#branch-result').checked ? h('div', { class: 'tt-alt', text: `Gün sonu sonuçları simülasyondaki kuryeye ait: ${r.courier_name}` }) : null,
        h('hr'),
        CM.hintRow(null, `${d.i + 1}. durak`, `${CM.hhmm(d.eta)} · ${nf(d.n)} gönderi · adres #${d.address}`),
        $('#branch-result').checked ? h('div', { class: 'tt-result tt-' + stopStatus(d), text: resultText(d) }) : null,
        d.unfamiliar ? h('div', { class: 'tt-alt', text: 'Kurye bu bloğa yabancı' }) : null,
        hints.map((t) => h('div', { class: 'tt-hint', text: '“' + t + '”' })),
        h('div', { class: 'tt-note', text: 'Tıklayın: kümeyi seç' }),
      ];
      CM.hint.show(ev.clientX, ev.clientY, content);
    },

    selectCluster(cluster, fromMap) {
      const st = this.st();
      st.selected = cluster === null || cluster === undefined || st.selected === cluster ? null : cluster;
      this.map.highlight(st.selected);
      for (const tr of $$('#assignment-table tbody tr')) {
        const on = st.selected !== null && +tr.dataset.cluster === +st.selected;
        tr.classList.toggle('selected', on);
        if (on && fromMap) tr.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
      this.drawChips();
    },

    /* ------------------------------------------------ panel */
    drawPanel() {
      this.drawSummary();
      this.drawTable();
      this.drawRationale();
      this.drawChat();
      this.drawChips();
    },

    drawSummary() {
      const st = this.st();
      const el = $('#assignment-summary');
      const btn = $('#btn-propose');
      btn.disabled = st.loading;
      btn.textContent = st.loading ? 'Ajan çalışıyor…' : st.proposal ? 'Yeniden öner' : 'Atama önerisi al';
      if (st.error && !st.proposal) {
        clear(el, errorBox(st.error, 'API ve ajan katmanı çalışıyor mu? (uvicorn api.main:app)'));
        return;
      }
      if (!st.proposal && !st.assignment) {
        clear(el, h('div', { class: 'empty' }, h('b', { text: 'Sabah planı hazır.' }), ' Atama Ajanı günün kümelerine kurye önersin: düğmeye basın.'));
        el.classList.toggle('faded', false);
        return;
      }
      el.classList.toggle('faded', st.loading);
      const t = st.total || (st.proposal && st.proposal.total) || {};
      const first = (st.proposal && st.proposal.total) || t;
      const rnd = st.proposal && st.proposal.comparison ? st.proposal.comparison.history_blind_expected_fails : null;
      const on_leave = (st.proposal && st.proposal.on_leave) || [];
      const empty = (st.proposal && st.proposal.idle_available) || [];
      const diff = t.expected_fails - first.expected_fails;
      const stopTop = (st.assignment || []).reduce((a, x) => a + (x.stop || 0), 0);
      const max = Math.max(rnd || 0, t.expected_fails || 0, 1);
      const compare =
        rnd !== null && rnd !== undefined
          ? h(
              'div',
              { class: 'compare' },
              h('div', { class: 'compare-row' }, h('span', { class: 'compare-name', text: 'Geçmişe bakmadan' }), h('span', { class: 'compare-trace' }, h('i', { class: 'compare-bar gray', style: { width: (100 * rnd) / max + '%' } })), h('b', { text: nf(rnd, 1) })),
              h('div', { class: 'compare-row' }, h('span', { class: 'compare-name', text: st.previous ? 'Senaryo' : 'Önerilen' }), h('span', { class: 'compare-trace' }, h('i', { class: 'compare-bar', style: { width: (100 * t.expected_fails) / max + '%' } })), h('b', { text: nf(t.expected_fails, 1) }))
            )
          : null;
      clear(
        el,
        h(
          'div',
          { class: 'stat large' },
          h('div', { class: 'stat-name', text: 'Beklenen başarısız teslim' }),
          h('div', { class: 'stat-value' }, nf(t.expected_fails, 1), rnd ? h('span', { class: 'stat-delta', text: ' ' + CM.markedPct((100 * (t.expected_fails - rnd)) / rnd, 0) + ' geçmişe bakmadan atamaya göre' }) : null),
          st.previous && Math.abs(diff) > 0.04 ? h('div', { class: 'stat-alt', text: 'Öneriye göre ' + CM.marked(diff, 1) }) : null,
          stopTop
            ? h('div', { class: 'stat-alt zone-sentence' }, (() => {
                const n = Math.round(100 * (1 - (t.unfamiliar_stop || 0) / stopTop));
                return [`Kuryeler durakların `, h('b', { text: `%${n}${CM.locativeSuffix(n)}` }), ' kendi bölgesinde; dinamik plan yalnız sınırları esnetir.'];
              })())
            : null,
          compare
        ),
        h(
          'div',
          { class: 'stat-pair' },
          h(
            'div',
            { class: 'stat' },
            h('div', { class: 'stat-name', title: 'Kendi bölgesinde durak payı = 1 − yabancı durak payı' }, 'Kendi bölgesinde'),
            h('div', { class: 'stat-value mid' }, pct(1 - (t.unfamiliar_stop || 0) / Math.max(1, stopTop), 0), h('span', { class: 'stat-delta', text: ' durakların' })),
            h('div', { class: 'stat-alt short', text: `yabancı ${nf(t.unfamiliar_stop)} durak · ${nf(t.memory_unfamiliar)} notlu` }),
            t.unfamiliar_stop ? h('div', { class: 'measures', title: 'Yabancı durakların hafızada notu olan payı' }, h('i', { style: { width: (100 * t.memory_unfamiliar) / t.unfamiliar_stop + '%' } })) : null
          ),
          h(
            'div',
            { class: 'stat' },
            h('div', { class: 'stat-name', text: 'Bugün çalışmayan · boşta' }),
            h('div', { class: 'stat-value mid' }, nf(on_leave.length), h('span', { class: 'stat-delta', text: ' · ' + nf(empty.length) + ' boşta' })),
            h('div', { class: 'stat-alt short', text: on_leave.length ? on_leave.map((x) => x.name).join(', ') : 'İzinli kurye yok' })
          )
        )
      );
    },

    drawTable() {
      const st = this.st();
      const tb = $('#assignment-table');
      const rows = (st.assignment || []).slice().sort((a, b) => a.cluster - b.cluster);
      tb.classList.toggle('faded', st.loading);
      if (!rows.length) {
        clear(tb);
        $('#assignment-alt-info').textContent = '';
        $('#btn-approve').disabled = true;
        $('#btn-back').hidden = true;
        return;
      }
      const previous = st.previous || {};
      const tbody = h('tbody');
      for (const a of rows) {
        const legacy = previous[a.cluster];
        const is_changed = legacy && legacy.courier !== a.courier;
        const tr = h(
          'tr',
          {
            class: (is_changed ? 'is_changed ' : '') + (st.selected !== null && +st.selected === +a.cluster ? 'selected' : ''),
            dataset: { cluster: a.cluster },
            tabindex: 0,
            onclick: () => this.selectCluster(a.cluster),
            onkeydown: (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                this.selectCluster(a.cluster);
              }
            },
            onmouseenter: () => this.map.highlight(a.cluster, 'hover'),
            onmouseleave: () => this.map.highlight(null, 'hover'),
          },
          h('td', { class: 'count', text: a.cluster }),
          h(
            'td',
            { class: 'courier-cell' },
            h('span', { class: 'courier-name' + (a.courier_type !== 'senior' ? ' bold' : ''), text: a.courier_name || a.courier }),
            ' ',
            CM.typeBadge(a.courier_type),
            is_changed ? h('div', { class: 'previous', text: 'önceki: ' + (legacy.courier_name || legacy.courier) }) : null
          ),
          h('td', { class: 'count', text: nf(a.stop) }),
          h('td', { class: 'count', text: nf(a.expected_fails, 1) }),
          a.unfamiliar_stop
            ? h('td', { class: 'unfamiliar' }, h('span', { class: 'count', text: `${nf(a.memory_unfamiliar)} / ${nf(a.unfamiliar_stop)}` }), h('span', { class: 'measures small' }, h('i', { style: { width: (100 * a.memory_unfamiliar) / a.unfamiliar_stop + '%' } })))
            : h('td', { class: 'unfamiliar faded-text', text: 'tanıdık' })
        );
        tbody.appendChild(tr);
      }
      clear(
        tb,
        h(
          'thead',
          null,
          h('tr', null, h('th', { text: 'Küme' }), h('th', { text: 'Kurye' }), h('th', { class: 'count', text: 'Durak' }), h('th', { class: 'count wrap', title: 'Beklenen başarısız teslim', text: 'Beklenen başarısız' }), h('th', { class: 'wrap', title: 'Kuryenin yabancı olduğu durakların kaçında hafızada not var', text: 'Hafızalı / yabancı durak' }))
        ),
        tbody
      );
      const changed = rows.filter((a) => previous[a.cluster] && previous[a.cluster].courier !== a.courier).length;
      $('#assignment-alt-info').textContent = st.approved ? 'Atama onaylandı.' : changed ? `${changed} kümede kurye değişti (senaryo).` : `${rows.length} küme · son onay şube müdüründe`;
      const bo = $('#btn-approve');
      bo.disabled = st.loading || st.approved;
      bo.textContent = st.approved ? 'Onaylandı ✓' : 'Onayla';
      $('#btn-back').hidden = !(st.proposal && st.previous);
    },

    drawRationale() {
      const st = this.st();
      const el = $('#rationale');
      const o = st.proposal;
      if (!o) {
        clear(el, h('div', { class: 'empty', text: 'Öneri gelince ajanın gerekçesi ve öne çıkanlar burada görünür.' }));
        return;
      }
      clear(
        el,
        o.highlights && o.highlights.length ? h('ul', { class: 'highlight' }, o.highlights.map((t) => h('li', null, CM.text(t, 'row-inner')))) : null,
        o.rationale && o.rationale.length ? h('ul', { class: 'rationale-list' }, o.rationale.map((t) => h('li', null, CM.text(t, 'row-inner')))) : null,
        stepsList(o.steps)
      );
    },

    drawChips() {
      const st = this.st();
      const el = $('#chips');
      const at = st.assignment || [];
      let target = null;
      if (st.selected !== null && st.selected !== undefined) {
        const a = at.find((x) => +x.cluster === +st.selected);
        if (a) target = a.courier_name;
        else {
          const k = this.assignedCourier(st.selected);
          if (k) target = k.name;
        }
      }
      const crit = S.meta.critical || {};
      if (!target && S.day === crit.day) target = crit.courier_name;
      if (!target) {
        const a = at.find((x) => x.courier_type !== 'senior');
        if (a) target = a.courier_name;
      }
      if (!target && this.snapD) {
        const r = this.snapD.routes.find((x) => x.courier_kind !== 'senior') || this.snapD.routes[0];
        if (r) target = r.courier_name;
      }
      const questions = [];
      if (target) {
        questions.push(`${target} yerine yedek kurye gönderirsem?`, `${target} bugün gelmezse?`);
        const empty = ((st.proposal && st.proposal.idle_available) || []).filter((b) => !at.some((a) => a.courier === b.id) && b.name !== target);
        if (empty.length) questions.push(`${target} yerine ${empty[0].name} gönderirsem?`);
      }
      clear(
        el,
        questions.map((q) =>
          h('button', { type: 'button', class: 'chip', disabled: st.loading, onclick: () => this.ask(q) }, q)
        )
      );
    },

    drawChat() {
      const st = this.st();
      const el = $('#chat');
      if (!st.chat.length) {
        clear(el, h('div', { class: 'empty', text: 'Senaryo sorun: ajan araçla yeniden hesaplar, farkı anlatır. Dönen atama tabloya işlenir; son onay sizde.' }));
        return;
      }
      clear(
        el,
        st.chat.map((m) => {
          if (m.role === 'manager') return h('div', { class: 'message manager' }, h('div', { class: 'bubble', text: m.text }));
          if (m.waiting) return h('div', { class: 'message agent' }, h('div', { class: 'bubble' }, loading('Atama Ajanı hesaplıyor…')));
          if (m.error) return h('div', { class: 'message agent' }, h('div', { class: 'bubble error' }, errorBox(m.error)));
          return h('div', { class: 'message agent' }, h('div', { class: 'bubble' }, CM.text(m.text), m.diff ? this.drawDiff(m.diff) : null, stepsList(m.steps)));
        })
      );
      el.scrollTop = el.scrollHeight;
    },

    drawDiff(f) {
      if (typeof f === 'string') return h('div', { class: 'diff' }, f);
      if (Array.isArray(f)) return h('div', { class: 'diff' }, f.map((x) => h('span', { class: 'diff-chip', text: String(x) })));
      const NAME = { expected_fails: 'Beklenen başarısız', unfamiliar_stop: 'Yabancı durak', memory_unfamiliar: 'Hafızalı yabancı', changed_clusters: 'Değişen kümeler' };
      const out = [];
      for (const [k, v] of Object.entries(f)) {
        if (v === null || v === undefined) continue;
        let value;
        if (Array.isArray(v)) value = v.length ? v.join(', ') : 'offline';
        else if (typeof v === 'number') value = CM.marked(v, Number.isInteger(v) ? 0 : 1);
        else value = String(v);
        out.push(h('span', { class: 'diff-chip' }, (NAME[k] || k) + ' ', h('b', { text: value })));
      }
      return out.length ? h('div', { class: 'diff' }, out) : null;
    },

    /* ------------------------------------------------ ajan çağrıları */
    async propose() {
      const st = this.st();
      const day = S.day;
      st.loading = true;
      st.error = null;
      this.drawPanel();
      try {
        const r = await CM.api('/api/assignment/propose', { method: 'POST', body: { day: day } });
        st.proposal = r;
        st.assignment = r.assignment || [];
        st.total = r.total;
        st.previous = null;
        st.approved = false;
      } catch (e) {
        st.error = e;
        CM.notify('Atama önerisi alınamadı: ' + e.message, 'error');
      } finally {
        st.loading = false;
        if (day === S.day) {
          this.drawPanel();
          this.drawMap(false);
        }
      }
    },

    async ask(question) {
      const st = this.st();
      const day = S.day;
      if (st.loading) return;
      const history = st.chat.filter((m) => !m.waiting && !m.error && m.text).map((m) => ({ role: m.role, text: m.text }));
      st.chat.push({ role: 'manager', text: question });
      const wait = { role: 'agent', waiting: true };
      st.chat.push(wait);
      st.loading = true;
      $('#question').value = '';
      this.drawPanel();
      try {
        const body = { day: day, question, history };
        if (st.assignment && st.assignment.length) body.current = st.assignment.map((a) => ({ cluster: a.cluster, courier: a.courier }));
        const r = await CM.api('/api/assignment/ask', { method: 'POST', body });
        Object.assign(wait, { waiting: false, text: r.response || '(yanıt boş)', diff: r.diff, steps: r.steps });
        if (r.assignment && r.assignment.length) {
          const prev = {};
          for (const a of st.assignment || []) prev[a.cluster] = a;
          st.previous = prev;
          st.assignment = r.assignment;
          st.total = r.total || st.total;
          st.approved = false;
          const n = r.assignment.filter((a) => prev[a.cluster] && prev[a.cluster].courier !== a.courier).length;
          CM.notify(`Senaryo tabloya işlendi: ${n} kümede kurye değişti.`);
        }
      } catch (e) {
        Object.assign(wait, { waiting: false, error: e });
      } finally {
        st.loading = false;
        if (day === S.day) {
          this.drawPanel();
          this.drawMap(false);
        }
      }
    },

    backToProposal() {
      const st = this.st();
      if (!st.proposal) return;
      st.assignment = st.proposal.assignment;
      st.total = st.proposal.total;
      st.previous = null;
      st.approved = false;
      this.drawPanel();
      this.drawMap(false);
    },

    async approve() {
      const st = this.st();
      if (!st.assignment || !st.assignment.length) return;
      const btn = $('#btn-approve');
      btn.disabled = true;
      try {
        const r = await CM.api('/api/assignment/approve', { method: 'POST', body: { day: S.day, assignment: st.assignment.map((a) => ({ cluster: a.cluster, courier: a.courier })) } });
        if (r && r.ok === false) throw new Error('Sunucu onayı kabul etmedi.');
        st.approved = true;
        CM.notify(`${dayLabel(S.day)} ataması onaylandı.`, 'good');
      } catch (e) {
        CM.notify('Onay gönderilemedi: ' + e.message, 'error');
      } finally {
        this.drawTable();
      }
    },
  };
  SCREEN.branch = Branch;

  /* ====================================================================== 2. KURYE */
  const BASE_DURATION = 40; // sn: 1× hızda tüm rota (ipucu bekleme hariç)
  const EXAMPLE_NOTES = [
    'site güvenliği kimlik istiyor, kayıt yaptırınca giriyorsunuz. yönetici Ahmet bey 0532 412 55 10',
    'sitenin önünde park yeri yok, aracı arka sokaktaki otoparka bırakıp yürüyün',
    'asansör yok, 4. kata merdivenle çıkılıyor',
    'numara tabelası yok, eczanenin yanındaki yeşil boyalı bina',
    'öğlen 12 ile 13:30 arası iş yeri kapalı, kimse açmıyor',
    'trafik berbattı bugün',
  ];

  const Courier = {
    briefCache: new Map(),
    selected: null,
    playback: { running: false, speed: 1, speech: true, seg: 0, t: 0, idx: -1, wait: false, last: 0, done: false },

    init() {
      this.map = new CM.MapView($('#courier-map'), {
        proj: S.proj,
        label: 'Kuryenin rotası',
        onOver: (n, ev) => this.over(n, ev),
        onSelect: (n) => {
          if (n) this.git(n.i, true);
        },
      });
      $('#courier-map').classList.add('single');
      $('#courier-select').addEventListener('change', () => {
        this.selected = $('#courier-select').value;
        this.load();
      });
      $('#btn-play').addEventListener('click', () => (this.playback.running ? this.pause() : this.play()));
      $('#btn-restart').addEventListener('click', () => this.restart());
      for (const b of $$('#speed button')) {
        b.addEventListener('click', () => {
          this.playback.speed = +b.dataset.speed;
          for (const x of $$('#speed button')) x.setAttribute('aria-pressed', x === b);
        });
      }
      $('#sound-on').addEventListener('change', (e) => {
        this.playback.speech = e.target.checked;
        if (!this.playback.speech) CM.speech.cancel();
      });
      $('#btn-listen').addEventListener('click', () => this.listen());
      $('#note-form').addEventListener('submit', (e) => {
        e.preventDefault();
        this.sendNote();
      });
      clear(
        $('#note-chips'),
        EXAMPLE_NOTES.map((t) =>
          h(
            'button',
            {
              type: 'button',
              class: 'chip',
              onclick: () => {
                $('#note-text').value = t;
                $('#note-text').focus();
              },
            },
            t
          )
        )
      );
      this.microphone();
      clear(
        $('#courier-legend'),
        CM.mapLegend([
          { type: 'point', status: 'plan', color: R.faded, text: 'Sıradaki durak' },
          { type: 'point', status: 'ok', color: R.faded, text: 'Teslim' },
          { type: 'point', status: 'fail', text: 'Başarısız' },
          { type: 'point', status: 'deferred', text: 'Ertelendi' },
          { type: 'point', status: 'plan', hint: true, color: R.faded, text: 'Kapı ipucu var' },
        ])
      );
    },

    async show() {
      if (this.drawnDay === S.day && this.brief !== undefined) return;
      this.drawnDay = S.day;
      const day = S.day;
      let snap;
      try {
        snap = await S.snap('D', day);
      } catch (e) {
        clear($('#briefing-text'), errorBox(e));
        return;
      }
      if (day !== S.day) return;
      this.snapD = snap;
      const sel = $('#courier-select');
      const routes = snap.routes.slice().sort((a, b) => (a.courier < b.courier ? -1 : 1));
      clear(sel, routes.map((r) => h('option', { value: r.courier, text: `${r.courier_name} · ${CM.TYPE[r.courier_kind] || r.courier_kind} · ${r.stops.length} durak` })));
      const crit = S.meta.critical || {};
      const var_ = (id) => routes.some((r) => r.courier === id);
      if (!this.selected || !var_(this.selected)) {
        this.selected = var_(crit.courier) ? crit.courier : (routes.find((r) => r.courier_kind !== 'senior') || routes[0] || {}).courier;
      }
      sel.value = this.selected;
      this.loadTomorrow(day);
      await this.load();
      this.memorySummary();
    },

    async loadTomorrow(day) {
      this.tomorrow = null;
      const g = (S.meta.eval_days || []).find((x) => x > day);
      if (g === undefined) return;
      try {
        const snap = await S.snap('D', g);
        if (day !== S.day) return;
        const F = stopFields(snap.stop_fields);
        const address = new Map();
        for (const r of snap.routes) for (const st of r.stops) address.set(+st[F.address], r.courier_name);
        this.tomorrow = { day: g, address };
        this.drawNoteTarget();
      } catch (e) {
        /* isteğe bağlı */
      }
    },

    async load() {
      this.pause();
      CM.speech.cancel();
      const day = S.day,
        courier = this.selected;
      if (!courier) return;
      this.brief = null;
      this.clearNoteResult();
      clear($('#briefing-text'), loading('Brifing Ajanı hazırlıyor…'));
      clear($('#briefing-warning'));
      this.doorEmpty();
      const route = this.snapD.routes.find((r) => r.courier === courier);
      // rota önce anlık görüntüden; brifing gelince onunkiyle güncellenir
      this.setupRoute(route, this.snapD.stop_fields, []);
      const key = day + '/' + courier;
      try {
        let p = this.briefCache.get(key);
        if (!p) {
          p = CM.api(`/api/briefing/${day}/${encodeURIComponent(courier)}`);
          this.briefCache.set(key, p);
          p.catch(() => this.briefCache.delete(key));
        }
        const b = await p;
        if (day !== S.day || courier !== this.selected) return;
        this.brief = b;
        const fields = b.stop_fields || (b.route && b.route.stop_fields) || S.meta.stop_fields || this.snapD.stop_fields;
        this.setupRoute(b.route && b.route.stops ? b.route : route, fields, b.door_sentences || []);
        this.drawBriefing();
      } catch (e) {
        if (day !== S.day || courier !== this.selected) return;
        this.brief = false;
        clear($('#briefing-text'), errorBox(e, 'Rota anlık görüntüden gösteriliyor; kapı ipuçları için brifing gerekli.'));
      }
    },

    setupRoute(route, fields, door) {
      if (!route) return;
      const F = stopFields(fields);
      this.route = route;
      this.stops = route.stops.map((a, i) => stopObject(a, F, i));
      this.door = new Map();
      for (const k of door) {
        let i = this.stops.findIndex((d) => +d.address === +k.address);
        if (i < 0 && k.order) i = k.order - 1;
        if (i >= 0 && i < this.stops.length && !this.door.has(i)) this.door.set(i, Object.assign({ status: null }, k));
      }
      const type = route.courier_kind || (this.brief && this.brief.courier_type) || 'senior';
      this.color = type === 'senior' ? '#5d6b7a' : R.type[type] || R.type.senior;
      const depot = (this.snapD && this.snapD.depot) || S.meta.depot;
      this.depot = depot;
      this.map.draw({
        routes: [
          {
            id: 0,
            color: this.color,
            thickness: 2.4,
            drawFromDepot: true,
            data: route,
            stops: this.stops.map((d) => ({ lat: d.lat, lng: d.lng, status: 'plan', hint: this.door.has(d.i), data: d })),
          },
        ],
        depot,
        border: false,
      });
      // görünüm rotaya sığar; şube uzaksa bağlantı çizgisi kenardan çıkar
      this.map.limit(this.map.routeBorder(0), 0.08);
      // oynatma yolu (dünya koordinatı)
      const p = S.proj;
      this.path = [[p.x(depot[1]), p.y(depot[0])]].concat(this.stops.map((d) => [p.x(d.lng), p.y(d.lat)]));
      const L = [];
      let top = 0;
      for (let i = 0; i < this.path.length - 1; i++) {
        const l = Math.hypot(this.path[i + 1][0] - this.path[i][0], this.path[i + 1][1] - this.path[i][1]);
        L.push(l);
        top += l;
      }
      this.segL = L;
      // şubeden ilk durağa ayak sabit kısa sürer; süre duraklar arası yola dağıtılır
      this.totalL = top - (L[0] || 0) || top || 1;
      this.restart();
      this.drawSummary();
      this.drawStrip();
    },

    drawSummary() {
      const r = this.route;
      if (!r) return;
      const hinted = this.door.size;
      const unfamiliar = this.stops.filter((d) => d.unfamiliar).length;
      clear(
        $('#courier-route-summary'),
        h('span', null, h('b', { text: nf(this.stops.length) }), ' durak'),
        h('span', null, h('b', { text: nf(r.km, 1) }), ' km'),
        h('span', null, h('b', { text: nf(r.minutes) }), ' dk'),
        h('span', null, h('b', { text: nf(unfamiliar) }), ' yabancı'),
        h('span', null, h('b', { text: nf(hinted) }), ' kapı ipucu')
      );
      const k = this.brief || {};
      const name = k.courier_name || r.courier_name;
      clear($('#phone-who'), h('div', { class: 'phone-name' }, h('b', { text: name }), ' ', CM.typeBadge(k.courier_type || r.courier_kind)), h('div', { class: 'alt', text: dayLabel(S.day) }));
    },

    drawBriefing() {
      const b = this.brief;
      if (!b) return;
      clear($('#briefing-text'), CM.text(b.morning_briefing || '(brifing boş)'));
      clear($('#briefing-warning'), (b.warnings || []).map((u) => h('li', null, h('span', { class: 'warning-icon', 'aria-hidden': 'true', text: '!' }), u)));
      const name = $('#briefing-step');
      clear(name, stepsList(b.steps));
      this.drawSummary();
      this.doorEmpty();
    },

    listen() {
      const b = this.brief;
      const btn = $('#btn-listen');
      if (btn.dataset.playing === '1') {
        CM.speech.cancel();
        return;
      }
      if (!b || !b.morning_briefing) return;
      this.pause();
      btn.dataset.playing = '1';
      btn.textContent = '■ Durdur';
      const s = CM.speech.say(b.morning_briefing);
      s.done.finally(() => {
        btn.dataset.playing = '0';
        btn.textContent = '▶ Dinle';
        $('#speech-source').textContent = CM.speech.source;
      });
    },

    /* ------------------------------------------------ oynatma */
    play() {
      if (!this.stops || !this.stops.length) return;
      if (this.playback.done) this.restart();
      CM.speech.cancel();
      $('#btn-listen').dataset.playing = '0';
      $('#btn-listen').textContent = '▶ Dinle';
      this.playback.running = true;
      this.playback.last = performance.now();
      this.updateButton();
      const step = (ts) => {
        if (!this.playback.running) return;
        const dt = Math.min(0.1, (ts - this.playback.last) / 1000);
        this.playback.last = ts;
        if (!this.playback.wait) this.advance(dt);
        this._shelf = requestAnimationFrame(step);
      };
      this._shelf = requestAnimationFrame(step);
    },

    pause() {
      if (!this.playback) return;
      this.playback.running = false;
      if (this._shelf) cancelAnimationFrame(this._shelf);
      this._shelf = null;
      this.updateButton();
    },

    restart() {
      this.pause();
      CM.speech.cancel();
      Object.assign(this.playback, { seg: 0, t: 0, idx: -1, wait: false, done: false, token: (this.playback.token || 0) + 1 });
      (this.stops || []).forEach((d) => this.map.updateStop(0, d.i, 'plan', this.door.has(d.i)));
      if (this.depot) this.map.marker(this.depot[0], this.depot[1]);
      this.map.ring(null);
      this.doorEmpty();
      this.drawProgress();
    },

    git(i, click) {
      // haritadan/şeritten seçilen durağa atla (duraklatılmış olarak)
      this.pause();
      CM.speech.cancel();
      this.playback.token = (this.playback.token || 0) + 1;
      this.playback.wait = false;
      this.playback.done = i >= this.stops.length - 1;
      this.stops.forEach((d) => this.map.updateStop(0, d.i, d.i <= i ? stopStatus(d) : 'plan', this.door.has(d.i)));
      this.playback.idx = i;
      this.playback.seg = i + 1;
      this.playback.t = 0;
      const d = this.stops[i];
      this.map.marker(d.lat, d.lng);
      this.map.ring(d.lat, d.lng);
      if (this.door.has(i)) this.showDoor(i, false);
      else this.doorEmpty(click ? i : undefined);
      this.drawProgress();
    },

    advance(dt) {
      const o = this.playback;
      const n = this.stops.length;
      if (o.seg >= n) {
        o.done = true;
        this.pause();
        this.drawProgress();
        return;
      }
      const segDuration = (o.seg === 0 ? 1.2 : Math.max(0.08, (BASE_DURATION * this.segL[o.seg]) / this.totalL)) / o.speed;
      o.t += dt / segDuration;
      if (o.t >= 1) {
        o.t = 0;
        const i = o.seg; // durak i'ye varıldı
        const d = this.stops[i];
        o.idx = i;
        o.seg = i + 1;
        this.map.updateStop(0, i, stopStatus(d), this.door.has(i));
        this.map.marker(d.lat, d.lng);
        this.map.center(d.lat, d.lng);
        this.drawProgress();
        if (this.door.has(i)) this.waitAtDoor(i);
        return;
      }
      // projeksiyon doğrusal: lat/lng üzerinde doğrusal ara değer, dünyada da doğrusaldır
      const d0 = o.seg === 0 ? { lat: this.depot[0], lng: this.depot[1] } : this.stops[o.seg - 1];
      const d1 = this.stops[o.seg];
      this.map.marker(d0.lat + (d1.lat - d0.lat) * o.t, d0.lng + (d1.lng - d0.lng) * o.t);
    },

    waitAtDoor(i) {
      const o = this.playback;
      o.wait = true;
      const token = o.token;
      this.showDoor(i, true);
      const min = new Promise((r) => setTimeout(r, 1100 / o.speed));
      const speech = o.speech ? CM.speech.say(this.door.get(i).sentence).done : Promise.resolve();
      Promise.all([min, speech]).then(() => {
        if (token !== this.playback.token) return;
        this.playback.wait = false;
        this.playback.last = performance.now();
        $('#speech-source').textContent = CM.speech.source;
      });
    },

    updateButton() {
      const b = $('#btn-play');
      if (!b) return;
      b.textContent = this.playback.running ? '❚❚ Duraklat' : this.playback.done ? '▶ Yeniden oynat' : this.playback.idx >= 0 ? '▶ Devam et' : '▶ Rotayı oynat';
      b.setAttribute('aria-pressed', this.playback.running);
    },

    drawProgress() {
      const o = this.playback;
      const n = this.stops ? this.stops.length : 0;
      const d = o.idx >= 0 ? this.stops[o.idx] : null;
      $('#progress').textContent = d ? `${o.idx + 1}. durak / ${n} · ${CM.hhmm(d.eta)}` : `Şubeden çıkış · ${n} durak`;
      $('#phone-hour').textContent = d ? CM.hhmm(d.eta) : '09:00';
      const cursor = $('#strip-cursor');
      if (cursor && n) {
        const x = d ? ((o.idx + 0.5) / n) * 100 : 0;
        cursor.style.left = x + '%';
      }
      for (const el of $$('#stop-strip .strip-tick')) el.classList.toggle('passed', +el.dataset.i <= o.idx);
      this.drawNoteTarget();
      this.updateButton();
    },

    drawStrip() {
      const el = $('#stop-strip');
      const n = this.stops.length;
      const container = h('div', { class: 'strip-inner' });
      this.stops.forEach((d) => {
        const k = this.door.has(d.i);
        container.appendChild(
          h('button', {
            type: 'button',
            class: 'strip-tick' + (k ? ' hint' : '') + (d.fail > 0 ? ' fail' : ''),
            style: { left: (d.i / n) * 100 + '%', width: 100 / n + '%' },
            dataset: { i: d.i },
            'aria-label': `${d.i + 1}. durak${k ? ', kapı ipucu var' : ''}`,
            onclick: () => this.git(d.i, true),
            onpointermove: (e) => {
              const kk = this.door.get(d.i);
              CM.hint.show(e.clientX, e.clientY, [h('div', { class: 'tt-title', text: `${d.i + 1}. durak · ${CM.hhmm(d.eta)}` }), h('div', { class: 'tt-alt', text: `${nf(d.n)} gönderi · adres #${d.address}` }), kk ? h('div', { class: 'tt-hint', text: '“' + kk.sentence + '”' }) : null]);
            },
            onpointerleave: () => CM.hint.hide(),
          })
        );
      });
      container.appendChild(h('div', { id: 'strip-cursor', class: 'strip-cursor' }));
      clear(el, container);
    },

    over(n, ev) {
      if (!n) {
        CM.hint.hide();
        return;
      }
      const d = n.data;
      const k = this.door.get(d.i);
      const passed = d.i <= this.playback.idx;
      CM.hint.show(ev.clientX, ev.clientY, [
        h('div', { class: 'tt-title', text: `${d.i + 1}. durak · ${CM.hhmm(d.eta)}` }),
        h('div', { class: 'tt-alt', text: `${nf(d.n)} gönderi · adres #${d.address}` + (d.unfamiliar ? ' · yabancı blok' : '') }),
        passed ? h('div', { class: 'tt-result tt-' + stopStatus(d), text: resultText(d) }) : null,
        k ? h('div', { class: 'tt-hint', text: '“' + k.sentence + '”' }) : null,
        h('div', { class: 'tt-note', text: 'Tıklayın: işaretçiyi buraya getir' }),
      ]);
    },

    /* ------------------------------------------------ kapı kartı */
    doorEmpty(selectedIdx) {
      const el = $('#phone-door');
      if (!el) return;
      el.classList.remove('active');
      const o = this.playback;
      let next = null;
      if (this.door) for (const i of [...this.door.keys()].sort((a, b) => a - b)) if (i > o.idx) {
        next = i;
        break;
      }
      const d = selectedIdx !== undefined ? this.stops[selectedIdx] : null;
      clear(
        el,
        h('div', { class: 'door-label', text: 'Kapıda' }),
        d
          ? h('div', { class: 'door-empty' }, `${d.i + 1}. durak · bu adres için kapı ipucu yok.`)
          : h('div', { class: 'door-empty' }, this.brief === null ? 'Brifing bekleniyor…' : 'Rotayı oynatın: notlu kapıya yaklaşınca ipucu burada büyük yazılır ve sesli okunur.'),
        next !== null ? h('div', { class: 'door-next', text: `Sıradaki ipucu: ${next + 1}. durak · ${CM.hhmm(this.stops[next].eta)}` }) : null
      );
    },

    showDoor(i, auto) {
      const el = $('#phone-door');
      const k = this.door.get(i);
      const d = this.stops[i];
      el.classList.add('active');
      const result = h('div', { class: 'door-result' });
      const btnG = h('button', { type: 'button', class: 'gb valid', onclick: () => this.feedback(i, true, result, [btnG, btnD]) }, '✓ Hâlâ geçerli');
      const btnD = h('button', { type: 'button', class: 'gb degismis', onclick: () => this.feedback(i, false, result, [btnG, btnD]) }, '✗ Değişmiş');
      if (k.status) {
        btnG.disabled = btnD.disabled = true;
        result.textContent = k.status;
      }
      clear(
        el,
        h('div', { class: 'door-label' }, `Kapıda · ${i + 1}. durak · ${CM.hhmm(d.eta)}`, h('button', { type: 'button', class: 'door-repeat', title: 'Tekrar dinle', 'aria-label': 'Tekrar dinle', onclick: () => CM.speech.say(k.sentence) }, CM.icon('speaker', 17))),
        h('div', { class: 'door-sentence', text: k.sentence }),
        k.records && k.records.length ? h('div', { class: 'door-types' }, k.records.map((x) => h('span', { class: 'door-type', text: CM.QUIRK[x.type] || x.type || x.id }))) : null,
        h('div', { class: 'gb-row' }, btnG, btnD),
        result
      );
      if (auto) {
        el.classList.remove('pulse');
        void el.offsetWidth;
        el.classList.add('pulse');
      }
    },

    async feedback(i, valid, resultEl, btns) {
      const k = this.door.get(i);
      const d = this.stops[i];
      btns.forEach((b) => (b.disabled = true));
      resultEl.textContent = 'Hafızaya gönderiliyor…';
      try {
        // Cümlenin dayandığı kayıtlar brifingle gelir (kayitlar[]); yoksa adres sorgusuyla eşleştir.
        let ids = (k.records || []).map((x) => x && x.id).filter(Boolean);
        if (!ids.length) {
          let record = k.record || k.record_id || null;
          if (record && typeof record === 'object') record = record.id;
          if (!record) {
            const r = await CM.api(`/api/memory?day=${S.day}&adres=${encodeURIComponent(d.address)}`);
            const es = (r && r.entries) || [];
            const e = es.find((x) => x.text === k.sentence) || es[0];
            if (!e) throw new Error('Bu adres için hafıza kaydı bulunamadı.');
            record = e.id;
          }
          ids = [record];
        }
        const results = await Promise.all(ids.map((record) => CM.api('/api/memory/feedback', { method: 'POST', body: { day: S.day, record, valid } })));
        const done = results.filter((r) => r && r.ok !== false);
        if (!done.length) throw new Error('Kayıt güncellenemedi.');
        const names = done.map((r, j) => (r.record && r.record.id) || ids[j]).join(', ');
        const single = done.length === 1 ? done[0].record || {} : {};
        k.status = valid
          ? `Teşekkürler. ${done.length > 1 ? done.length + ' kayıt' : 'Kayıt'} teyit edildi: ${names}` + (single.sources ? ` (kaynak: ${single.sources}).` : '.')
          : `${done.length > 1 ? done.length + ' kayıt' : 'Kayıt'} hafızadan düşürüldü (${names}); bir daha söylenmeyecek.`;
        resultEl.textContent = k.status;
        resultEl.className = 'door-result ' + (valid ? 'good' : 'neutral');
        this.briefCache.clear();
        this.memorySummary();
      } catch (e) {
        resultEl.textContent = 'Geri bildirim gönderilemedi: ' + e.message;
        resultEl.className = 'door-result error';
        btns.forEach((b) => (b.disabled = false));
      }
    },

    /* ------------------------------------------------ not bırak */
    targetStop() {
      const i = this.playback.idx;
      return i >= 0 && this.stops ? this.stops[i] : null;
    },

    drawNoteTarget() {
      const el = $('#note-target');
      if (!el) return;
      const d = this.targetStop();
      const icon = h('span', { class: 'target-icon' }, CM.icon('position', 16));
      if (d) {
        const y = this.tomorrow && this.tomorrow.address.get(+d.address);
        clear(el, icon, h('span', null, h('b', { text: `${d.i + 1}. durak` }), ` · adres #${d.address} · ${CM.hhmm(d.eta)}`, y ? h('span', { class: 'tomorrow', text: ` · ertesi gün (gün ${this.tomorrow.day}) yine teslimat var` }) : null));
      } else clear(el, icon, h('span', { class: 'faded-text', text: 'Konum yok: rotayı oynatın ya da haritada bir durağa tıklayın.' }));
    },

    microphone() {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      const btn = $('#btn-microphone');
      if (!SR) {
        btn.hidden = true;
        return;
      }
      btn.hidden = false;
      clear(btn, CM.icon('microphone', 15), ' Bas-konuş');
      let rec = null;
      let previous = '';
      const finish = () => {
        if (rec) rec.stop();
      };
      btn.addEventListener('pointerdown', (e) => {
        e.preventDefault();
        try {
          rec = new SR();
          rec.lang = 'tr-TR';
          rec.interimResults = true;
          rec.continuous = true;
          previous = $('#note-text').value ? $('#note-text').value.trim() + ' ' : '';
          rec.onresult = (ev) => {
            let t = '';
            for (let i = 0; i < ev.results.length; i++) t += ev.results[i][0].transcript;
            $('#note-text').value = previous + t;
          };
          rec.onerror = (ev) => {
            CM.notify('Ses tanıma kullanılamıyor (' + (ev.error || 'error') + '). Notu yazabilirsiniz.', 'error');
          };
          rec.onend = () => {
            btn.classList.remove('record');
            rec = null;
          };
          rec.start();
          btn.classList.add('record');
        } catch (err) {
          CM.notify('Ses tanıma başlatılamadı.', 'error');
        }
      });
      btn.addEventListener('pointerup', finish);
      btn.addEventListener('pointerleave', finish);
    },

    clearNoteResult() {
      clear($('#note-result'), h('div', { class: 'empty', text: 'Hafıza Ajanı notu adrese bağlar, türünü çıkarır, kişisel veriyi ayıklar. Sonuç burada görünür.' }));
    },

    async sendNote() {
      const text = $('#note-text').value.trim();
      if (!text) {
        $('#note-text').focus();
        return;
      }
      const d = this.targetStop();
      const body = { day: S.day, courier: this.selected, text };
      if (d) {
        body.lat = d.lat;
        body.lng = d.lng;
        body.minute = Math.round(d.eta);
      }
      const btn = $('#btn-note');
      btn.disabled = true;
      clear($('#note-result'), loading('Hafıza Ajanı notu işliyor…'));
      try {
        const r = await CM.api('/api/note', { method: 'POST', body });
        this.drawNoteResult(r, text);
        if (r.status === 'saved' || r.status === 'updated') {
          this.briefCache.clear();
          $('#note-text').value = '';
        }
        this.memorySummary();
      } catch (e) {
        clear($('#note-result'), errorBox(e));
      } finally {
        btn.disabled = false;
      }
    },

    drawNoteResult(r, text) {
      const STATUS_CLASS = { saved: 'good', updated: 'good', noise: 'neutral', uncertain: 'warning', rejected: 'critical' };
      const STATUS_ICON = { saved: '✓', updated: '✓', noise: '–', uncertain: '?', rejected: '✗' };
      const a = r.address;
      const row = (name, value) => h('div', { class: 'ks' }, h('span', { class: 'ks-name', text: name }), h('span', { class: 'ks-value' }, value));
      const card = h(
        'div',
        { class: 'note-result-inner' },
        h(
          'div',
          { class: 'ks-top' },
          h('span', { class: 'status-badge ' + (STATUS_CLASS[r.status] || 'neutral') }, h('i', { 'aria-hidden': 'true', text: STATUS_ICON[r.status] || '·' }), CM.NOTE_STATUS[r.status] || r.status),
          r.personal_data_redacted ? h('span', { class: 'status-badge shield' }, h('i', null, CM.icon('shield', 13)), 'Kişisel veri ayıklandı') : null
        ),
        h('div', { class: 'ks-note', text: '“' + text + '”' }),
        r.summary ? h('div', { class: 'ks-summary', text: r.summary }) : null,
        a ? row('Bağlanan adres', [h('b', { text: a.label || '#' + a.id }), ` · ${CM.ADDRESS_TYPE[a.type] || a.type || ''} · #${a.id}`]) : null,
        r.type ? row('Tür', CM.QUIRK[r.type] || r.type) : null,
        r.hint ? row('Kaydedilen ipucu', h('b', { class: 'ks-hint', text: '“' + r.hint + '”' })) : null,
        r.record ? row('Kayıt', `${r.record.id || r.record}` + (r.record.sources ? ` · ${r.record.sources} kaynak` : '')) : null,
        r.question ? h('div', { class: 'ks-question' }, h('b', { text: 'Ajan soruyor: ' }), r.question) : null,
        h('div', { id: 'next-day' }),
        stepsList(r.steps)
      );
      clear($('#note-result'), card);
      if (a && (r.status === 'saved' || r.status === 'updated')) {
        const i = this.stops.findIndex((d) => +d.address === +a.id);
        if (i >= 0) {
          this.map.updateStop(0, i, i <= this.playback.idx ? stopStatus(this.stops[i]) : 'plan', true);
          this.map.ring(this.stops[i].lat, this.stops[i].lng);
        } else if (a.lat !== undefined) this.map.ring(a.lat, a.lng);
        this.nextDay(a);
      }
    },

    async nextDay(a) {
      const el = $('#next-day');
      const candidates = (S.meta.eval_days || []).filter((g) => g > S.day).slice(0, 6);
      if (!el || !candidates.length) return;
      try {
        let r = null,
          next = null;
        for (const g of candidates) {
          const snap = await S.snap('D', g);
          const F = stopFields(snap.stop_fields);
          r = snap.routes.find((x) => x.stops.some((s) => +s[F.address] === +a.id));
          if (r) {
            next = g;
            break;
          }
        }
        if (!r || !document.body.contains(el)) {
          if (document.body.contains(el)) el.appendChild(h('div', { class: 'alt', text: 'Bu adrese sonraki günlerde teslimat yok; ipucu hafızada bekliyor.' }));
          return;
        }
        clear(
          el,
          h(
            'button',
            {
              type: 'button',
              class: 'ertesi',
              onclick: () => {
                this.selected = r.courier;
                adjustDay(next);
              },
            },
            h('b', { text: dayLabel(next) + ': ' }),
            `bu adrese ${r.courier_name} (${CM.TYPE[r.courier_kind] || r.courier_kind}) gidiyor → brifingini aç`
          )
        );
      } catch (e) {
        /* ertesi gün bilgisi isteğe bağlı */
      }
    },

    async memorySummary() {
      const el = $('#memory-summary');
      try {
        const r = await CM.api(`/api/memory/summary?day=${S.day}`);
        clear(el, 'Adres hafızasında ', h('b', { text: nf(r.total) }), ' geçerli kayıt' + (r.last && r.last.length ? ` · ${r.last.length} tanesi bu oturumda yazıldı/güncellendi` : ''));
      } catch (e) {
        el.textContent = '';
      }
    },
  };
  SCREEN.courier = Courier;

  /* ====================================================================== 3. SİMÜLASYON */
  const SWEEP_NAME = {
    'outcome.eta_nav': 'Yabancı blokta bilgi eksikliği etkisi',
    'quirks.prevalence_scale': 'Püf noktası sıklığı',
    'couriers.note_propensity_scale': 'Not bırakma eğilimi',
    'memory.parse_accuracy': 'Hafıza Ajanı ayrıştırma doğruluğu',
  };
  const SHORT = { A: 'sabit bölge', B: 'geçmişe bakmadan', C: 'çekirdek bölge', D: 'çekirdek + hafıza' };
  const sweepFormat = (k, v) => (/accuracy/.test(k) ? pct(v, 0) : '×' + nf(v, /\.\d\d/.test(String(v)) ? 2 : 1));

  const Sim = {
    compareArm: 'A',
    period: 'demo',
    async show() {
      if (!this.summary) {
        for (const b of $$('#period-select button')) {
          b.addEventListener('click', () => {
            if (this.period === b.dataset.period || !this.summary) return;
            this.period = b.dataset.period;
            for (const x of $$('#period-select button')) x.setAttribute('aria-pressed', x === b);
            this.drawPeriod();
          });
        }
        clear($('#kpi'), loading('Simülasyon özeti yükleniyor…'));
        try {
          this.summary = await CM.fetch('/api/summary');
        } catch (e) {
          clear($('#kpi'), errorBox(e));
          return;
        }
        if (!this.summary.long_term) {
          const b = $('#period-select [data-period=uzun]');
          b.disabled = true;
          b.title = 'Uzun dönem çalıştırması yok';
        }
        this.drawPeriod();
        this.drawSweep();
        for (const b of $$('#compare-select button')) {
          b.addEventListener('click', () => {
            this.compareArm = b.dataset.arm;
            for (const x of $$('#compare-select button')) x.setAttribute('aria-pressed', x === b);
            this.drawCompare();
          });
        }
      }
      if (this.drawnDay !== S.day) {
        this.drawnDay = S.day;
        if (this.dailyCard) this.dailyCard.refresh();
        this.drawCompare();
      }
    },

    source() {
      return this.period === 'long' && this.summary.long_term ? this.summary.long_term : this.summary;
    },
    metaD() {
      return (this.period === 'long' && this.summary.long_term && this.summary.long_term.meta) || S.meta;
    },
    arms() {
      const s = this.source().summary || {};
      return s.arms || s;
    },
    daily() {
      const d = this.source().daily || {};
      return d.arms || d;
    },
    learning() {
      const l = this.source().learning_curve || {};
      return l.arms || l;
    },
    armName(k) {
      const m = this.metaD();
      return (m.arms && m.arms[k]) || (S.meta.arms && S.meta.arms[k]) || (this.arms()[k] && this.arms()[k].label) || k;
    },

    drawPeriod() {
      $('#screen-simulation').classList.toggle('long', this.period === 'long');
      this.drawKpi();
      this.charts();
      if (this.period === 'long') this.drawLong();
      this.drawNote();
    },

    drawKpi() {
      const A = this.arms();
      const dl = (this.source().summary && this.source().summary.deltas) || {};
      const diff = {
        A: () => 'Kurye her gün aynı sabit bölgede; bölgesini tanır.',
        B: () => (dl.B_vs_A ? `A'ya göre araç-gün ${CM.markedPct(dl.B_vs_A.vehicle_days_pct)} · km ${CM.markedPct(dl.B_vs_A.km_pct)}` : ''),
        C: () => (dl.C_vs_B ? `B'ye göre ${CM.marked(dl.C_vs_B.first_attempt_pp, 2)} puan · önlenebilir ${CM.markedPct(dl.C_vs_B.preventable_fail_pct)}` : ''),
        D: () => (dl.D_vs_C ? `C'ye göre ${CM.marked(dl.D_vs_C.first_attempt_pp, 2)} puan · önlenebilir ${CM.markedPct(dl.D_vs_C.preventable_fail_pct)}` : ''),
      };
      const METRIC = [
        ['first_attempt_rate', 'İlk denemede teslim', (v) => pct(v, 1), true],
        ['preventable_fail', 'Önlenebilir başarısızlık', (v) => nf(v), false, 'Bilgiyle önlenebilir başarısızlık: adres bulunamadı, kapalı, giriş yapılamadı, alıcıya ulaşılamadı'],
        ['couriers_per_day', 'Kurye / gün', (v) => nf(v, 1)],
        ['in_band_share', 'Vardiya bandında', (v) => pct(v, 1)],
        ['unfamiliar_share', 'Kendi bölgesinde', (v) => (v === undefined ? '–' : pct(1 - v, 1)), false, 'Kendi bölgesinde durak payı = 1 − yabancı durak payı'],
        ['memory_coverage', 'Hafıza kapsamı', (v) => pct(v, 1)],
      ];
      clear(
        $('#kpi'),
        ARMS.map((k) => {
          const a = A[k] || {};
          return h(
            'div',
            { class: 'card kpi-card' },
            h('div', { class: 'kpi-head' }, h('i', { class: 'kpi-key', style: { background: R.arm[k] } }), h('b', { text: k }), h('span', { text: this.armName(k).replace(/^Yeni yapı · /, 'Yeni yapı · ') })),
            h(
              'div',
              { class: 'kpi-grid' },
              METRIC.map(([area, name, f, large, explanation]) => h('div', { class: 'kpi-cell' + (large ? ' large' : ''), title: explanation || name }, h('div', { class: 'kpi-name', text: name }), h('div', { class: 'kpi-value', text: f(a[area]) })))
            ),
            h('div', { class: 'kpi-diff', text: diff[k]() })
          );
        })
      );
      const ev = this.metaD().eval_days || [];
      $('#kpi-period').textContent =
        this.period === 'long'
          ? `${ev.length} iş günü · ödünç/yeni kurye ve izinler döneme yayılmış · aynı talep, aynı rastgele sayılar`
          : `Gün ${ev[0]}–${ev[ev.length - 1]} (${ev.length} gün) · aynı talep, aynı rastgele sayılar`;
    },

    charts() {
      const D = this.daily();
      const ser = ARMS.map((k) => ({ id: k, name: k + ' · ' + this.armName(k).replace(/^Yeni yapı · /, ''), short: k, color: R.arm[k] }));
      clear($('#lj-daily'), CM.legend(ser.map((s) => ({ name: s.name, color: s.color }))));
      // --- günlük ilk denemede teslim
      const all = ARMS.flatMap((k) => (D[k] || []).map((x) => x.first_attempt_rate));
      const y0 = Math.floor(Math.min(...all) * 100 - 0.4) / 100,
        y1 = Math.ceil(Math.max(...all) * 100 + 0.2) / 100;
      const days = Array.from(new Set(ARMS.flatMap((k) => (D[k] || []).map((x) => x.day)))).sort((a, b) => a - b);
      this.dailyCard = CM.chartCard(
        $('#g-daily'),
        $('#tb-daily'),
        (container) =>
          CM.lineChart(container, {
            label: 'Günlük ilk denemede teslim oranı, dört kol',
            series: ser.map((s) => Object.assign({}, s, { points: (D[s.id] || []).map((x) => ({ x: x.day, y: x.first_attempt_rate })) })),
            xArea: [days[0], days[days.length - 1]],
            xTick: days.filter((g, i) => i % 2 === 0),
            xFormat: (v) => String(v),
            yArea: [y0, y1],
            yTick: CM.ticks(y0, y1, 0.01),
            yFormat: (v, detail) => pct(v, detail ? 1 : 0),
            markX: this.period === 'demo' ? S.day : null,
            markLabel: 'seçili gün',
            hintTitle: (x) => dayLabel(x),
            onTick: this.period === 'demo' ? (x) => adjustDay(x) : null,
          }),
        () =>
          CM.table(
            ['Gün'].concat(ARMS),
            days.map((g) => [dayLabel(g)].concat(ARMS.map((k) => pct(((D[k] || []).find((x) => x.day === g) || {}).first_attempt_rate, 1))))
          )
      );
      // --- başarısızlık nedenleri
      const A = this.arms();
      const preventable = (this.summary.summary && this.summary.summary.preventable_reasons) || ['address_not_found', 'closed', 'entry_failed', 'recipient_unreachable'];
      const reasons = preventable.concat(Object.keys(CM.REASON).filter((r) => !preventable.includes(r)));
      const groups = reasons.map((r) => ({ id: r, name: CM.REASON[r] || r, accent: preventable.includes(r), alt: preventable.includes(r) ? 'bilgiyle önlenebilir' : 'hafızayla önlenemez', values: Object.fromEntries(ARMS.map((k) => [k, ((A[k] || {}).fail_by_reason || {})[r] || 0])) }));
      const mx = Math.max(...groups.flatMap((g) => Object.values(g.values)), 1);
      const step = CM.tickStep(mx, 4);
      clear($('#lj-reason'), CM.legend(ser.map((s) => ({ name: s.short + ' · ' + SHORT[s.id], color: s.color })), 'bar-fill'));
      $('#reason-alt').textContent = `${(this.metaD().eval_days || []).length} günde toplam`;
      CM.chartCard(
        $('#g-reason'),
        $('#tb-reason'),
        (container) =>
          CM.groupBar(container, {
            label: 'Başarısızlık nedenleri, dört kol',
            groups,
            series: ser,
            max: Math.ceil(mx / step) * step,
            ticks: CM.ticks(0, Math.ceil(mx / step) * step, step),
            format: (v) => nf(v),
            labelSeries: 'D',
            leftGap: 138,
          }),
        () => CM.table(['Neden'].concat(ARMS), groups.map((g) => [g.name + (g.accent ? ' (önlenebilir)' : '')].concat(ARMS.map((k) => nf(g.values[k])))))
      );
      // --- öğrenme eğrisi (yeni + ödünç; C ve D)
      const L = this.learning();
      const curve = (arm) => {
        const by = new Map();
        for (const [id, v] of Object.entries(L[arm] || {})) {
          if (!['new', 'borrowed'].includes(v.kind)) continue;
          (v.days || []).forEach((d, i) => {
            const k = i + 1;
            if (!by.has(k)) by.set(k, { top: 0, n: 0, hint: 0, names: [] });
            const o = by.get(k);
            o.top += d.rate;
            o.n++;
            o.hint += d.hinted || 0;
            o.names.push(id);
          });
        }
        return [...by.entries()].sort((a, b) => a[0] - b[0]).map(([k, o]) => ({ x: k, y: o.top / o.n, n: o.n, hint: o.hint, names: o.names, extra: o.n + ' kurye' }));
      };
      const name = {};
      ((this.couriers && this.couriers.couriers) || []).forEach((c) => (name[c.id] = c.name));
      const eC = curve('C'),
        eD = curve('D');
      const allL = eC.concat(eD).map((p) => p.y);
      const ser2 = [
        { id: 'C', name: 'C · ' + SHORT.C, short: 'C', color: R.arm.C, points: eC },
        { id: 'D', name: 'D · ' + SHORT.D, short: 'D', color: R.arm.D, points: eD },
      ];
      clear($('#lj-learning'), CM.legend(ser2));
      if (!allL.length) {
        clear($('#g-learning'), h('div', { class: 'empty', text: 'Yeni ya da ödünç kurye verisi yok.' }));
      } else {
        const ly0 = Math.floor(Math.min(...allL) * 100 - 0.5) / 100,
          ly1 = Math.min(1, Math.ceil(Math.max(...allL) * 100 + 0.3) / 100);
        const maxK = Math.max(...eC.concat(eD).map((p) => p.x));
        CM.chartCard(
          $('#g-learning'),
          $('#tb-learning'),
          (container) =>
            CM.lineChart(container, {
              label: 'Yeni ve ödünç kuryelerde öğrenme eğrisi',
              series: ser2,
              pointMark: true,
              xArea: [1, maxK],
              xTick: maxK > 20 ? [1].concat(CM.ticks(5, maxK, 5)) : CM.ticks(1, maxK, maxK > 8 ? 2 : 1),
              xFormat: (v) => String(v),
              yArea: [ly0, ly1],
              yTick: CM.ticks(ly0, ly1, ly1 - ly0 > 0.06 ? 0.02 : 0.01),
              yFormat: (v, detail) => pct(v, detail ? 1 : 0),
              hintTitle: (x) => `Kuryenin ${x}. günü`,
              hintExtra: (x) => {
                const pc = eC.find((p) => p.x === x),
                  pd = eD.find((p) => p.x === x);
                const nm = (p) => (p ? p.names.map((i) => name[i] || i).join(', ') : '–');
                return h('div', { class: 'tt-alt' }, h('div', { text: 'C: ' + nm(pc) }), h('div', { text: 'D: ' + nm(pd) + (pd ? ` · ${nf(pd.hint)} ipuçlu durak` : '') }));
              },
            }),
          () => {
            const xs = Array.from(new Set(eC.concat(eD).map((p) => p.x))).sort((a, b) => a - b);
            return CM.table(
              ['Kuryenin günü', 'C', 'C kurye', 'D', 'D kurye'],
              xs.map((x) => {
                const pc = eC.find((p) => p.x === x),
                  pd = eD.find((p) => p.x === x);
                return [x + '. gün', pc ? pct(pc.y, 1) : '–', pc ? nf(pc.n) : '–', pd ? pct(pd.y, 1) : '–', pd ? nf(pd.n) : '–'];
              })
            );
          }
        );
      }
    },

    drawSweep() {
      const sw = this.summary.sweep;
      const el = $('#sweep');
      if (!sw || !sw.rows || !sw.rows.length) {
        clear(el, h('div', { class: 'empty large-empty' }, h('b', { text: 'Sağlamlık taraması henüz yok.' }), h('div', { text: 'Tarama çalıştırıldığında dört parametre için kaydırıcılar burada açılır.' })));
        return;
      }
      const keys = sw.keys || Object.keys(sw.rows[0].params || {});
      const values = sw.values || {};
      const select = {};
      for (const k of keys) {
        const vs = values[k] || Array.from(new Set(sw.rows.map((r) => r.params[k]))).sort((a, b) => a - b);
        values[k] = vs;
        const mid = vs.findIndex((v) => Math.abs(v - 1) < 1e-9);
        select[k] = mid >= 0 ? mid : Math.floor(vs.length / 2);
      }
      const nCombo = sw.rows.length;
      const share = sw.order_share !== undefined ? sw.order_share : sw.rows.filter((r) => r.order_D_ge_C_ge_B).length / nCombo;
      const result = h('div', { class: 'sweep-result' });
      const sliders = h(
        'div',
        { class: 'sliders' },
        keys.map((k) => {
          const vs = values[k];
          const value = h('b', { class: 'kd-value', text: sweepFormat(k, vs[select[k]]) });
          const inp = h('input', { type: 'range', min: 0, max: vs.length - 1, step: 1, value: select[k], 'aria-label': SWEEP_NAME[k] || k });
          inp.addEventListener('input', () => {
            select[k] = +inp.value;
            value.textContent = sweepFormat(k, vs[select[k]]);
            draw();
          });
          return h('label', { class: 'slider' }, h('span', { class: 'kd-name' }, SWEEP_NAME[k] || k, ' ', value), inp, h('span', { class: 'kd-tick' }, vs.map((v) => h('i', { text: sweepFormat(k, v) }))));
        })
      );
      const draw = () => {
        const row = sw.rows.find((r) => keys.every((k) => Math.abs(+r.params[k] - +values[k][select[k]]) < 1e-9 || r.params[k] === values[k][select[k]]));
        if (!row) {
          clear(result, h('div', { class: 'empty', text: 'Bu kombinasyon taranmadı.' }));
          return;
        }
        const vs = ARMS.map((k) => (row.arms[k] || {}).first_attempt_rate).filter((v) => v !== undefined);
        const a0 = Math.floor(Math.min(...vs) * 100 - 0.5) / 100,
          a1 = Math.ceil(Math.max(...vs) * 100 + 0.5) / 100;
        const ok = row.order_D_ge_C_ge_B !== undefined ? row.order_D_ge_C_ge_B : row.arms.D.first_attempt_rate >= row.arms.C.first_attempt_rate && row.arms.C.first_attempt_rate >= row.arms.B.first_attempt_rate;
        const g = h('div', { class: 'sweep-chart' });
        clear(
          result,
          g,
          h(
            'div',
            { class: 'sweep-status' },
            h('span', { class: 'status-badge ' + (ok ? 'good' : 'warning') }, h('i', { 'aria-hidden': 'true', text: ok ? '✓' : '!' }), ok ? 'D ≥ C ≥ B bu kombinasyonda geçerli' : 'D ≥ C ≥ B bu kombinasyonda geçerli değil'),
            row.pp ? h('span', { class: 'alt', text: `C−B ${CM.marked(row.pp.C_vs_B, 2)} puan · D−C ${CM.marked(row.pp.D_vs_C, 2)} puan` }) : null
          )
        );
        requestAnimationFrame(() =>
          CM.pointChart(g, {
            label: 'Seçili parametrelerle ilk denemede teslim',
            title: 'İlk denemede teslim',
            rows: ARMS.map((k) => ({ id: k, name: k + ' · ' + SHORT[k], color: R.arm[k], value: (row.arms[k] || {}).first_attempt_rate })),
            area: [a0, a1],
            ticks: CM.ticks(a0, a1, a1 - a0 > 0.05 ? 0.02 : 0.01),
            format: (v, d) => pct(v, d ? 1 : 0),
            leftGap: 150,
          })
        );
      };
      clear(
        el,
        h('div', { class: 'sweep-head' }, h('div', { class: 'hero-small', text: pct(share, 0) }), h('div', null, h('b', { text: 'D ≥ C ≥ B sıralaması kombinasyonların ' + pct(share, 0) + CM.locativeSuffix(Math.round(100 * share)) + ' geçerli' }), h('div', { class: 'alt', text: `${nf(nCombo)} kombinasyon × ${nf(sw.seeds || 1)} seed · ilk denemede teslime göre` }))),
        sliders,
        result
      );
      draw();
    },

    async drawCompare() {
      const day = S.day;
      const left = this.compareArm;
      $('#compare-day').textContent = dayLabel(day);
      if (!this.minis) {
        const sync = (source) => (vb) => {
          for (const m of this.minis) if (m !== source) m.adjustView(vb);
        };
        const m1 = new CM.MapView($('#compare-left'), { proj: S.proj, mini: true, label: 'Sol kol haritası', onOver: (n, ev) => this.compareOver(n, ev, 0) });
        const m2 = new CM.MapView($('#compare-right'), { proj: S.proj, mini: true, label: 'D kolu haritası', onOver: (n, ev) => this.compareOver(n, ev, 1) });
        m1.opts.onView = sync(m1);
        m2.opts.onView = sync(m2);
        this.minis = [m1, m2];
        clear(
          $('#compare-legend'),
          CM.mapLegend([
            { type: 'line', color: R.arm[left], text: 'Rota (kol rengi)' },
            { type: 'point', status: 'fail', text: 'Başarısız durak' },
            { type: 'point', status: 'deferred', text: 'Planlı erteleme' },
          ])
        );
      }
      const arms = [left, 'D'];
      try {
        const snaps = await Promise.all(arms.map((k) => S.snap(k, day)));
        if (day !== S.day || left !== this.compareArm) return;
        this.compareSnap = snaps;
        let border = null;
        snaps.forEach((snap, mi) => {
          const F = stopFields(snap.stop_fields);
          const arm = arms[mi];
          const t = { stop: 0, ok: 0, fail: 0, unfamiliar: 0, km: 0 };
          const routes = snap.routes.map((r) => {
            t.km += r.km || 0;
            return {
              id: r.route,
              color: R.arm[arm],
              thickness: 1.1,
              data: r,
              stops: r.stops.map((a, i) => {
                const d = stopObject(a, F, i);
                t.stop++;
                t.ok += d.ok;
                t.fail += d.fail;
                t.unfamiliar += d.unfamiliar ? 1 : 0;
                const dd = stopStatus(d);
                return { lat: d.lat, lng: d.lng, status: dd === 'ok' ? 'hidden' : dd, data: d };
              }),
            };
          });
          this.minis[mi].draw({ routes, depot: snap.depot, border: false });
          const s = this.minis[mi].points.reduce((b, n) => ({ x0: Math.min(b.x0, n.x), y0: Math.min(b.y0, n.y), x1: Math.max(b.x1, n.x), y1: Math.max(b.y1, n.y) }), border || { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity });
          border = s;
          clear(
            $(mi === 0 ? '#compare-left-alt' : '#compare-right-alt'),
            h('div', { class: 'compare-head' }, h('i', { class: 'lj-line', style: { background: R.arm[arm] } }), h('b', { text: arm }), ' ', this.armName(arm)),
            h('div', { class: 'compare-figure' }, h('span', null, h('b', { text: nf(snap.routes.length) }), ' kurye'), h('span', null, h('b', { text: pct(t.ok / Math.max(1, t.ok + t.fail), 1) }), ' ilk denemede'), h('span', null, h('b', { text: nf(t.fail) }), ' başarısız'), h('span', null, h('b', { text: nf(t.km) }), ' km'), h('span', null, h('b', { text: pct(t.unfamiliar / Math.max(1, t.stop), 0) }), ' yabancı'))
          );
        });
        for (const m of this.minis) m.limit(border, 0.05);
        const lj = $('#compare-legend .lj-line');
        if (lj) lj.style.background = R.arm[left];
      } catch (e) {
        clear($('#compare-left-alt'), errorBox(e));
      }
    },

    compareOver(n, ev, mi) {
      if (!n) {
        CM.hint.hide();
        return;
      }
      const d = n.data,
        r = n.r;
      CM.hint.show(ev.clientX, ev.clientY, [h('div', { class: 'tt-title' }, `${r.courier_name} `, CM.typeBadge(r.courier_kind)), h('div', { class: 'tt-alt', text: `${d.i + 1}. durak · ${CM.hhmm(d.eta)}` }), h('div', { class: 'tt-result tt-' + stopStatus(d), text: resultText(d) })]);
      void mi;
    },

    drawNote() {
      const el = $('#sim-note');
      const m = this.metaD();
      const parts = [];
      if (this.period === 'demo') {
        const rc = this.summary.recovery || {};
        const e = rc.end_of_eval_C || rc.end_of_warmup;
        const w = rc.end_of_warmup;
        parts.push(
          h('h3', { text: 'Uyum tahmincisi doğrulaması' }),
          e
            ? h(
                'p',
                null,
                'Tahmin edilen kurye etkisi ile gizli gerçek beceri arasındaki sıra korelasyonu ',
                h('b', { text: nf(e.spearman_estimate, 2) }),
                ` (bölge zorluğundan arındırılmamış ham oran: ${nf(e.spearman_naive, 2)}; n = ${nf(e.n)}).`,
                w && w !== e ? ` Isınma sonunda: ${nf(w.spearman_estimate, 2)} (ham ${nf(w.spearman_naive, 2)}; n = ${nf(w.n)}).` : ''
              )
            : h('p', { class: 'faded-text', text: 'Doğrulama verisi yok.' })
        );
      }
      parts.push(this.calibration());
      parts.push(
        h('h3', { text: 'Bu rakamlar ne anlatır?' }),
        h('p', null, 'Dört kol aynı günlerde, aynı talep ve aynı rastgele sayılarla koşar; fark politikadan gelir. Simülasyon ', h('b', { text: 'mekanizmayı' }), ' gösterir, etkinin büyüklüğünü kanıtlamaz: rakamlar bu parametrelerle geçerlidir.'),
        h('p', null, 'Yeni yapıda kurye her gün kendi çekirdek bölgesinde kalır; dinamik plan yalnız sınırları ve fazla işi talebe göre esnetir. Kaydırma yalnız zorunlu anlarda olur (izin, ayrılma, yeni ya da ödünç kurye); hafıza bilgiyi tam o anlarda taşır.'),
        h('div', { class: 'work' }, h('span', { text: 'Çalıştırma' }), h('code', { text: m.run_id || '' }), h('span', { text: `seed ${m.seed} · ${m.warmup_days} gün ısınma · ${(m.eval_days || []).length} gün değerlendirme` }))
      );
      clear(el, parts);
    },

    calibration() {
      const k = this.summary.calibration;
      if (!k || !k.rows || !k.rows.length) return null;
      const n = k.rows.length;
      const uy = k.rows.filter((r) => r.compatible).length;
      const format = (measure, v) => {
        if (v === null || v === undefined) return '–';
        if (/rate|repeat|one_time|share/.test(measure)) return pct(v, 1);
        if (/deviation/.test(measure)) return nf(v, 2);
        if (Math.abs(v) >= 100) return nf(v, 0);
        return nf(v, Math.abs(v) < 10 ? 2 : 1);
      };
      return h(
        'details',
        { class: 'calibration' },
        h('summary', null, h('span', { class: 'status-badge ' + (uy === n ? 'good' : 'warning') }, h('i', { 'aria-hidden': 'true', text: uy === n ? '✓' : '!' }), `${uy}/${n}`), ' Uygulama verisi, saha verisinden türetilmiş toplu hedeflere kalibre'),
        h('div', { class: 'alt', text: 'Hedef değerler saha verisinin toplu özetidir ve şirket içi olduğu için gösterilmez; yalnız uygulama verisinin değerleri ve uyum durumu.' }),
        h(
          'table',
          { class: 'data-table calibration-table' },
          h('thead', null, h('tr', null, h('th', { text: 'Ölçü' }), h('th', { text: 'Uygulama verisi' }), h('th', { text: '' }))),
          h(
            'tbody',
            null,
            k.rows.map((r) =>
              h('tr', null, h('th', { text: r.explanation || r.measure, title: r.measure }), h('td', { text: format(r.measure, r.value) }), h('td', { class: r.compatible ? 'good-text' : 'warning-text', text: r.compatible ? '✓ hedefle uyumlu' : '! sapma' }))
            )
          )
        )
      );
    },

    drawLong() {
      const D = this.daily();
      const dD = D.D || [],
        dC = D.C || [];
      const days = dD.map((x) => x.day);
      const diff = dD.map((x, i) => (dC[i] && dC[i].day === x.day ? 100 * (x.first_attempt_rate - dC[i].first_attempt_rate) : null));
      const diffMean = CM.movingMean(diff, 5);
      const coverage = dD.map((x) => x.memory_coverage);
      const coverageMean = CM.movingMean(coverage, 5);
      const point = (ys) => days.map((g, i) => ({ x: g, y: ys[i] }));
      const xTick = days.filter((g, i) => i % 10 === 0).concat(days.length ? [days[days.length - 1]] : []);
      const fx = diffMean.concat(diff).filter((v) => v !== null);
      const fa = Math.max(0.5, Math.ceil(Math.max(...fx.map(Math.abs)) * 2) / 2);
      const fStep = fa >= 1 ? 0.5 : 0.25;
      const table = () =>
        CM.table(
          ['Gün', 'D − C (puan)', '5 gün ort.', 'Hafıza kapsamı', '5 gün ort.'],
          days.map((g, i) => [String(g), CM.marked(diff[i], 2), CM.marked(diffMean[i], 2), pct(coverage[i], 1), pct(coverageMean[i], 1)])
        );
      CM.chartCard(
        $('#g-udiff'),
        $('#tb-useries'),
        (container) =>
          CM.lineChart(container, {
            label: 'D eksi C, ilk denemede teslim farkı, 5 günlük ortalama',
            series: [
              { id: 'daily', name: 'günlük', color: R.gray, thin: true, unlabeled: true, points: point(diff) },
              { id: 'mean', name: '5 gün ort.', short: 'D−C', color: R.arm.D, points: point(diffMean) },
            ],
            xArea: [days[0], days[days.length - 1]],
            xTick,
            xFormat: (v) => String(v),
            yArea: [-fa, fa],
            yTick: CM.ticks(-fa, fa, fStep),
            zero: true,
            yFormat: (v, d) => CM.marked(v, d ? 2 : fStep < 0.5 ? 2 : 1),
            hintTitle: (x) => `Gün ${x}`,
          }),
        table
      );
      const km = Math.min(1, Math.ceil(Math.max(...coverage.concat(coverageMean).filter((v) => v !== null)) * 20 + 0.5) / 20);
      CM.chartCard($('#g-ucoverage'), null, (container) =>
        CM.lineChart(container, {
          label: 'D kolunda hafıza kapsamı, 5 günlük ortalama',
          series: [
            { id: 'daily', name: 'günlük', color: R.gray, thin: true, unlabeled: true, points: point(coverage) },
            { id: 'mean', name: '5 gün ort.', short: 'D', color: R.arm.D, points: point(coverageMean) },
          ],
          xArea: [days[0], days[days.length - 1]],
          xTick,
          xFormat: (v) => String(v),
          yArea: [0, km],
          yTick: CM.ticks(0, km, km > 0.3 ? 0.1 : 0.05),
          yFormat: (v, d) => pct(v, d ? 1 : 0),
          hintTitle: (x) => `Gün ${x}`,
        })
      );
      this.drawMessage();
    },

    drawMessage() {
      const D = this.daily();
      const A = this.arms();
      const mean = (arm, f) => {
        const xs = D[arm] || [];
        return xs.length ? xs.reduce((a, x) => a + (f(x) || 0), 0) / xs.length : null;
      };
      const ARM_3 = [
        ['A', 'Bugün', 'sabit bölge'],
        ['B', 'Ajansız geçiş', 'agent offline'],
        ['D', 'Courier Memory', 'çekirdek bölge'],
      ];
      const ROW = [
        { name: 'Kendi bölgesinde durak payı', hint: '1 − yabancı durak payı', summary: (k) => (A[k] && A[k].unfamiliar_share !== undefined ? 1 - A[k].unfamiliar_share : null), b: (v) => pct(v, 0), lowIsBad: true, top: 1 },
        { name: 'Kurye / gün', f: (x) => x.couriers, b: (v) => nf(v, 1) },
        { name: 'Başarısız teslim / gün', f: (x) => x.fail, b: (v) => nf(v, 0), bad: true },
        { name: 'Fazla mesai, saat / gün', f: (x) => (x.overtime_minutes || 0) / 60, b: (v) => nf(v, 1), bad: true },
        { name: 'İş yükü sapması', hint: 'kuryeler arası değişim katsayısı', f: (x) => x.workload_cv, b: (v) => nf(v, 2) },
      ];
      const deg = ROW.map((r) => ARM_3.map(([k]) => (r.summary ? r.summary(k) : mean(k, r.f))));
      const [pA, pB, pD] = deg[0],
        [kA, kB, kD] = deg[1],
        [fA, fB, fD] = deg[2];
      const rows = ROW.map((r, i) => {
        const vs = deg[i];
        const mx = r.top || Math.max(...vs.filter((x) => x !== null), 1e-9) * 1.1;
        return h(
          'tr',
          null,
          h('th', { title: r.hint || '' }, h('b', { text: r.name })),
          ARM_3.map(([k], j) => {
            const v = vs[j];
            const bad = k !== 'A' && vs[0] !== null && v !== null && ((r.bad && v > vs[0] * 1.05) || (r.lowIsBad && v < vs[0] - 0.05));
            return h('td', { class: 'count ' + (k === 'D' ? 'k-memory' : k === 'B' ? 'k-risk' : 'k-today') + (bad ? ' bad' : '') }, h('span', { class: 'kd-main', text: v === null ? '–' : r.b(v) }));
          }),
          h(
            'td',
            { class: 'point-trace-cell' },
            h(
              'div',
              { class: 'triple-trace', title: ARM_3.map(([k, name], j) => `${name}: ${vs[j] === null ? '–' : r.b(vs[j])}`).join(' · ') },
              ARM_3.map(([k], j) => (vs[j] === null ? null : h('i', { class: 'triple-point n-' + k, style: { left: (100 * vs[j]) / mx + '%', background: R.arm[k] } })))
            )
          )
        );
      });
      const same = fD !== null && fA !== null && fD <= fA * 1.03;
      const pn = Math.round(100 * (pD || 0));
      const zone = `kuryeler durakların %${pn}${CM.locativeSuffix(pn)} kendi bölgesinde`;
      const headline =
        (pD !== null && pD >= 0.9 ? `Kaydırmıyoruz: ${zone}; değişen yalnız sınırlar. ` : `${zone.charAt(0).toUpperCase() + zone.slice(1)}. `) +
        `Aynı iş günde ${nf(Math.abs(kA - kD), 1)} kurye ${kA >= kD ? 'daha az' : 'daha fazla'}, ` +
        (same ? 'kalite bugünkü düzeyde.' : `başarısız teslim ${nf(fA)} → ${nf(fD)} / gün.`);
      clear(
        $('#u-message'),
        h('div', { class: 'u-headline', text: headline }),
        h(
          'table',
          { class: 'compare3 message3' },
          h(
            'thead',
            null,
            h(
              'tr',
              null,
              h('th', { text: 'Günlük ortalama' }),
              ARM_3.map(([k, name, alt]) => h('th', { class: 'count ' + (k === 'D' ? 'k-memory' : k === 'B' ? 'k-risk' : 'k-today') }, h('i', { class: 'kpi-key', style: { background: R.arm[k] } }), h('div', { class: 'kb-top', text: name }), h('div', { class: 'kb-alt' }, k === 'B' ? h('span', { class: 'risk-badge', text: 'risk' }) : null, alt))),
              h('th', { class: 'point-trace-cell alt', text: 'sıfırdan ölçekli' })
            )
          ),
          h('tbody', null, rows)
        ),
        h('div', { class: 'chart-note', text: `Ayrıntı · ilk denemede teslim: bugün ${pct((A.A || {}).first_attempt_rate, 1)} · ajansız ${pct((A.B || {}).first_attempt_rate, 1)} · Courier Memory ${pct((A.D || {}).first_attempt_rate, 1)}.` })
      );
    },
  };
  SCREEN.simulation = Sim;

  /* ====================================================================== 4. DEĞER */
  const AGENT_NAME = {
    propose_assignment: ['Atama Ajanı', 'sabah önerisi'],
    ask_assignment: ['Atama Ajanı', 'senaryo sorusu'],
    memory: ['Hafıza Ajanı', 'not başına'],
    briefing: ['Brifing Ajanı', 'kurye başına'],
  };
  const MODEL_PARAM = [
    ['model_assignment', 'assignment', 'Atama'],
    ['model_memory', 'memory', 'Hafıza'],
    ['model_briefing', 'briefing', 'Brifing'],
  ];
  const ASSUMPTION = [
    { k: 'courier_daily_cost_tl', name: 'Kurye günlük maliyeti', min: 2000, max: 6000, step: 100, f: (v) => nf(v, 0) + ' TL' },
    { k: 'usd_try', name: 'Dolar kuru', min: 30, max: 60, step: 1, f: (v) => nf(v, 0) + ' TL' },
    { k: 'fails_other_tl', name: 'Başarısız deneme · diğer', long: 'Başarısız denemenin diğer maliyeti (iade, çağrı)', min: 0, max: 100, step: 5, f: (v) => nf(v, 0) + ' TL' },
    { k: 'km_cost_tl', name: 'Km maliyeti', min: 2, max: 12, step: 0.5, f: (v) => nf(v, 1) + ' TL' },
    { k: 'daily_assignment_question', name: 'Senaryo sorusu / gün', min: 0, max: 10, step: 1, f: (v) => nf(v, 0) },
  ];
  const VALUE_COLOR = { increase: R.arm.D, decrease: '#e34948', total: '#3d3c39', side: R.axis };
  /* Operasyon şelalesi: maliyet azalışı olumlu (iyi), artışı risk (ciddi); toplamlar nötr, sonuç vurgulu */
  const OP_COLOR = { start: '#8a8880', decrease: '#0ca30c', increase: '#ec835a', result: R.arm.D };
  const modelName = (v, id) => ((v.models || []).find((m) => m.id === id) || {}).name || id || '–';
  const million = (x) => (Math.abs(x) >= 1e6 ? nf(x / 1e6, 1) + ' milyon TL' : CM.tl(x));
  const shortTL = (x) => (Math.abs(x) >= 1e9 ? nf(x / 1e9, 2) + ' mlr' : Math.abs(x) >= 1e6 ? nf(x / 1e6, 1) + ' mn' : Math.abs(x) >= 1e3 ? nf(x / 1e3, 0) + ' bin' : nf(x, 0));

  const Value = {
    param: {},
    compare: 'vs_C',
    unit: 'gun',
    seq: 0,

    async show() {
      if (this.ready) return;
      this.ready = true;
      CM.fetch('/api/summary')
        .then((o) => {
          this.summary = o;
          if (this.v) {
            this.drawCompare();
            this.drawOpWaterfall();
          }
        })
        .catch(() => {});
      const seg = (sel, attr, fn) =>
        $$(sel + ' button').forEach((b) =>
          b.addEventListener('click', () => {
            for (const x of $$(sel + ' button')) x.setAttribute('aria-pressed', x === b);
            fn(b.dataset[attr]);
          })
        );
      seg('#gain-select', 'compare', (v) => {
        this.compare = v;
        if (this.v) this.drawGain();
      });
      seg('#waterfall-unit', 'unit', (v) => {
        this.unit = v;
        if (this.v) this.drawOpWaterfall();
      });
      seg('#agent-view', 'view', (v) => {
        $('#agent-cost').hidden = v !== 'cost';
        $('#agent-return').hidden = v !== 'roi';
      });
      $('#compare-c').addEventListener('change', () => this.v && this.drawCompare());
      $('#assumption-reset').addEventListener('click', () => this.reset());
      clear($('#headline'), loading('Ekonomi hesaplanıyor…'));
      await this.load();
    },

    overTime() {
      clearTimeout(this._t);
      this._t = setTimeout(() => this.load(), 250);
    },

    async load() {
      clearTimeout(this._t);
      const n = ++this.seq;
      const qs = new URLSearchParams(this.param).toString();
      $('#screen-value').classList.add('reaggregate');
      try {
        const v = await CM.api('/api/economics' + (qs ? '?' + qs : ''));
        if (n !== this.seq) return;
        if (!this.defaults) this.defaults = JSON.parse(JSON.stringify(v.assumptions || {}));
        this.v = v;
        if (!this.hasControls) this.setupControls();
        this.draw();
      } catch (e) {
        if (n !== this.seq) return;
        if (this.v) CM.notify('Ekonomi yeniden hesaplanamadı: ' + e.message, 'error');
        else clear($('#headline'), errorBox(e, 'API çalışıyor mu? (GET /api/economics)'));
      } finally {
        if (n === this.seq) $('#screen-value').classList.remove('reaggregate');
      }
    },

    setupControls() {
      this.hasControls = true;
      const va = this.defaults;
      this.slider = {};
      clear(
        $('#assumptions'),
        ASSUMPTION.map((c) => {
          const v0 = va[c.k] !== undefined ? +va[c.k] : c.min;
          const value = h('b', { class: 'kd-value', text: c.f(v0) });
          const inp = h('input', { type: 'range', min: c.min, max: c.max, step: c.step, value: v0, 'aria-label': c.long || c.name });
          inp.addEventListener('input', () => {
            value.textContent = c.f(+inp.value);
            this.param[c.k] = inp.value;
            this.overTime();
          });
          this.slider[c.k] = { inp, value, c };
          return h('label', { class: 'slider row', title: `${c.long || c.name} · varsayılan ${c.f(v0)} · aralık ${c.f(c.min)}–${c.f(c.max)}` }, h('span', { class: 'kd-name' }, c.name, ' ', value), h('span', { class: 'kd-order' }, h('i', { class: 'kd-end', text: nf(c.min, c.step < 1 ? 1 : 0) }), inp, h('i', { class: 'kd-end', text: nf(c.max, c.step < 1 ? 1 : 0) })));
        })
      );
      const v = this.v;
      this.selector = {};
      const am = va.agent_model || {};
      const selections = MODEL_PARAM.map(([param, key, name]) => {
        const sel = h('select', { 'aria-label': name + ' Ajanı modeli' }, (v.models || []).map((m) => h('option', { value: m.id, text: String(m.name || m.id).replace(/^Claude /, '') })));
        sel.value = am[key] || '';
        sel.addEventListener('change', () => {
          this.param[param] = sel.value;
          this.load();
        });
        this.selector[param] = { sel, v0: am[key] || '' };
        return h('label', { class: 'model-select' }, h('span', { text: name }), sel);
      });
      const cache = h('input', { type: 'checkbox' });
      cache.checked = !!va.cache;
      cache.addEventListener('change', () => {
        this.param.cache = cache.checked ? 'true' : 'false';
        this.load();
      });
      this.cache = cache;
      clear($('#model-selection'), selections, h('label', { class: 'key', title: 'Sabit istem ve araç tanımları önbellekten okunur' }, cache, 'Önbellek'));
    },

    reset() {
      this.param = {};
      const va = this.defaults || {};
      for (const o of Object.values(this.slider || {})) {
        const v0 = va[o.c.k] !== undefined ? +va[o.c.k] : o.c.min;
        o.inp.value = v0;
        o.value.textContent = o.c.f(v0);
      }
      for (const o of Object.values(this.selector || {})) o.sel.value = o.v0;
      if (this.cache) this.cache.checked = !!va.cache;
      this.load();
    },

    yearTimes() {
      const m = this.v.headline || {};
      if (m.savings_tl_day && m.savings_tl_year) return m.savings_tl_year / m.savings_tl_day;
      const A = ((this.v.operation || {}).arms || {}).A;
      return A && A.total_tl_day ? A.total_tl_year / A.total_tl_day : 306;
    },

    ownZone(arm) {
      const o = this.summary;
      if (!o) return null;
      const kay = this.v && this.v.source_running === 'long_term' && o.long_term ? o.long_term.summary : o.summary;
      const a = kay && (kay.arms || kay)[arm];
      return a && a.unfamiliar_share !== undefined ? 1 - a.unfamiliar_share : null;
    },

    selectScenario(sc) {
      const p = {};
      for (const c of ASSUMPTION) if (c.k in this.param) p[c.k] = this.param[c.k];
      p.scenario = sc;
      this.param = p;
      this.load();
    },

    drawScenario() {
      const v = this.v;
      const ls = v.llm_scenarios || [];
      const el = $('#scenario-select');
      el.hidden = !ls.length;
      if (!ls.length) return;
      const special = ['model_assignment', 'model_memory', 'model_briefing', 'cache'].some((k) => k in this.param);
      const active = special ? null : v.scenario || this.param.scenario || 'cautious';
      clear(
        el,
        ls.map((sc) => {
          const [name, ...desc] = String(sc.name || sc.scenario).split(':');
          const rate = sc.savings_rate;
          return h(
            'button',
            { type: 'button', class: 'scenario-card sk-' + sc.scenario, 'aria-pressed': active === sc.scenario, title: sc.name || '', onclick: () => this.selectScenario(sc.scenario) },
            h('div', { class: 'sk-head' }, h('i', { class: 'sk-mark', 'aria-hidden': 'true' }), h('b', { text: name.trim() }), h('span', { class: 'sk-desc', text: desc.join(':').trim() })),
            h('div', { class: 'sk-value' }, h('b', { text: CM.tl(sc.llm_tl_day) + ' / gün' }), ` · ${nf(sc.per_shipment_kurus, 2)} kr / gönderi`),
            h('div', { class: 'sk-alt' }, `tasarrufa oranı ${pct(rate, rate < 0.01 ? 2 : 1)} · getiri ${CM.times(sc.memory_return_multiple)}`)
          );
        }),
        h('div', { class: 'sk-special alt' }, special ? 'Özel model seçimi: senaryo yerine aşağıdaki seçim geçerli. ' : '', h('span', { class: 'sk-note', text: 'Optimize: kalite canlı ölçümle doğrulanır (Hafıza Ajanı değerlendirmesi).' }))
      );
    },

    draw() {
      const am = (this.v.assumptions || {}).agent_model || {};
      for (const [param, key] of MODEL_PARAM) {
        const o = this.selector && this.selector[param];
        if (o && am[key]) o.sel.value = am[key];
      }
      if (this.cache) this.cache.checked = !!(this.v.assumptions || {}).cache;
      this.drawScenario();
      this.drawHeadline();
      this.drawOpWaterfall();
      this.drawCompare();
      this.drawAgentHeadline();
      this.drawCost();
      this.drawGain();
      this.drawScale();
    },

    /* ------------------------------------------------ manşet: operasyon maliyeti tasarrufu */
    drawHeadline() {
      const v = this.v;
      const m = v.headline || {};
      const calib = m.quality || {};
      const va = v.assumptions || {};
      const L = v.llm || {};
      const sameQuality = calib.fails_per_day_memory !== undefined && calib.fails_per_day_memory <= calib.fails_per_day_current * 1.03;
      const box = (name, value, alt, cls) => h('div', { class: 'm-box ' + (cls || '') }, h('div', { class: 'stat-name' }, name), h('div', { class: 'm-value' }, value), alt ? h('div', { class: 'stat-alt' }, alt) : null);
      const gk = Math.round(this.yearTimes());
      clear(
        $('#headline'),
        h(
          'div',
          { class: 'headline-sentence' },
          'Şube başına yılda ',
          h('b', { text: million(m.savings_tl_year) }),
          ' daha düşük operasyon maliyeti · gönderi başına ',
          h('b', { text: `${nf(m.per_shipment_before_tl, 1)} → ${nf(m.per_shipment_after_tl, 1)} TL` }),
          ' · ',
          sameQuality ? 'başarısız teslim bugünkü düzeyde' : h('span', null, 'başarısız teslim ', h('b', { text: `${nf(calib.fails_per_day_current)} → ${nf(calib.fails_per_day_memory)}` }), ' / gün')
        ),
        h(
          'div',
          { class: 'm-boxes' },
          box('Günlük tasarruf', CM.tl(m.savings_tl_day), `bugüne göre ${pct(m.savings_rate, 1)} daha düşük`, 'accent'),
          box('Yıllık tasarruf', CM.tl(m.savings_tl_year), `şube başına · ${nf(gk)} iş günü`),
          box('Gönderi başına maliyet', `${nf(m.per_shipment_before_tl, 2)} → ${nf(m.per_shipment_after_tl, 2)} TL`, 'bugün → Courier Memory ile'),
          box(
            'Başarısız teslim / gün',
            h('span', { class: 'triple' }, h('span', null, nf(calib.fails_per_day_current)), h('span', { class: 'triple-risk' }, nf(calib.fails_per_day_agentless)), h('span', null, nf(calib.fails_per_day_memory))),
            h('span', { class: 'triple-alt' }, h('span', null, 'bugün'), h('span', null, 'ajansız'), h('span', null, 'hafızalı'))
          ),
          box(h('span', null, h('i', { class: 'm-warning-icon', 'aria-hidden': 'true', text: '!' }), 'Ajansız geçişin ek maliyeti'), '+' + CM.tl(m.agentless_extra_cost_tl_day) + ' / gün', `yılda +${million(m.agentless_extra_cost_tl_year)}`, 'risk'),
          box('LLM maliyetinin tasarrufa oranı', pct(m.llm_share, m.llm_share < 0.01 ? 2 : 1), `${CM.tl(L.daily_tl)} / gün · ${v.scenario === 'optimize' ? 'optimize' : v.scenario === 'cautious' ? 'cautious' : 'üç ajan'}`)
        ),
        h(
          'div',
          { class: 'm-dip' },
          h('span', null, h('b', { text: 'Karşılaştırma: ' }), 'Bugün (sabit bölge) → yeni yapı + Courier Memory', ` · ${nf(v.day_count)} iş günlük ${v.source_running === 'long_term' ? 'uzun dönem ' : ''}çalıştırma · tahmini parametrelerle`),
          h('span', null, h('span', { class: 'assumption-label small', text: 'tahmini' }), ` kurye günlük maliyeti ${CM.tl(va.courier_daily_cost_tl)}`)
        )
      );
    },

    /* ------------------------------------------------ ana görsel: operasyon maliyeti şelalesi */
    drawOpWaterfall() {
      const v = this.v;
      const op = v.operation || {};
      const K = op.arms || {};
      const k = this.yearTimes();
      const year = this.unit === 'year';
      const c = year ? k : 1;
      $('#opwaterfall-alt').textContent = year ? `şube başına · TL / yıl (${nf(Math.round(k))} iş günü)` : 'şube başına · TL / gün';
      const diff = (a, b, area, d) => (K[a] && K[b] ? K[b][area] - K[a][area] : null);
      const marked = (x, d) => (x === null ? '' : (x > 0 ? '+' : '') + nf(x, d));
      const kb = (arm) => this.ownZone(arm);
      const findCode = (a) => {
        if (a.code) return a.code;
        const t = (a.step || '').toLocaleLowerCase('tr');
        if (a.type === 'start') return 'today';
        if (a.type === 'result') return 'result';
        if (t.includes('dynamic')) return 'dynamic';
        if (t.includes('ajansız') || t.includes('agentless')) return 'agentless';
        if (t.includes('assignment')) return 'assignment';
        if (t.includes('hafıza') || t.includes('memory')) return 'memory';
        return '';
      };
      const findExplanation = (a) => {
        const code = findCode(a);
        if (code === 'today' && K.A) return `${nf(K.A.courier, 1)} kurye · ${nf(K.A.fails_per_day)} başarısız · ${nf(K.A.overtime_hour_day, 1)} sa mesai`;
        if (code === 'result' && K.D) return `${nf(K.D.courier, 1)} kurye · ${nf(K.D.fails_per_day)} başarısız · ${nf(K.D.overtime_hour_day, 1)} sa mesai`;
        if (code === 'dynamic') return `${marked(diff('A', 'B', 'courier'), 1)} kurye / gün`;
        if (code === 'agentless') return `${marked(diff('A', 'B', 'fails_per_day'), 0)} başarısız · ${marked(diff('A', 'B', 'overtime_hour_day'), 1)} sa mesai`;
        if (code === 'assignment') return (kb('B') !== null && kb('C') !== null ? `bölgede ${pct(kb('B'), 0)} → ${pct(kb('C'), 0)} · ` : '') + `${marked(diff('B', 'C', 'fails_per_day'), 0)} başarısız`;
        if (code === 'memory') return `${marked(diff('C', 'D', 'fails_per_day'), 0)} başarısız · ${marked(diff('C', 'D', 'overtime_hour_day'), 1)} sa mesai`;
        return '';
      };
      const steps = (op.waterfall || []).map((a) => {
        const [name, ...remaining] = String(a.step || '').split(':');
        const alt = remaining.join(':').replace(/\s*\(.*\)\s*$/, '').trim();
        return { name: name.trim(), alt, fullName: a.step, explanation: findExplanation(a), value: a.tl_day * c, type: a.type };
      });
      const first = steps.find((a) => a.type === 'start'),
        last = steps.find((a) => a.type === 'result');
      const label2 = (x, type) => (type === 'start' || type === 'result' ? CM.tl(x) : (x > 0 ? '+' : '−') + CM.tl(Math.abs(x)));
      CM.chartCard(
        $('#g-opwaterfall'),
        $('#tb-opwaterfall'),
        (container) =>
          CM.waterfallVertical(container, {
            label: 'Operasyon maliyeti şelalesi: bugünden yeni yapı + Courier Memory’ye',
            steps: steps.map((a) => Object.assign({}, a, { name: a.name })),
            color: OP_COLOR,
            format: (t) => (t === 0 ? '0' : year && t >= 1e6 ? nf(t / 1e6, 0) + ' mn' : nf(t / 1e3, 0) + ' bin'),
            label2,
            labelHeight: 76,
            diff: first && last ? { text: '−' + CM.tl(first.value - last.value), alt: `tasarruf · ${pct((first.value - last.value) / first.value, 1)}` } : null,
          }),
        () => {
          let lvl = 0;
          return CM.table(
            ['Adım', year ? 'TL / yıl' : 'TL / gün', 'Sonrası', 'Açıklama'],
            steps.map((a) => {
              lvl = a.type === 'start' || a.type === 'result' ? a.value : lvl + a.value;
              return [a.fullName, label2(a.value, a.type), CM.tl(lvl), a.explanation];
            })
          );
        }
      );
      clear(
        $('#opwaterfall-legend'),
        CM.mapLegend([
          { type: 'block', color: OP_COLOR.decrease, text: 'Maliyet azalır' },
          { type: 'block', color: OP_COLOR.increase, text: 'Maliyet artar (risk)' },
          { type: 'block', color: OP_COLOR.start, text: 'Bugün' },
          { type: 'block', color: OP_COLOR.result, text: 'Courier Memory ile' },
        ])
      );
      const va = v.assumptions || {};
      clear(
        $('#opwaterfall-note'),
        'Tasarrufun çoğu daha az kurye-gününden gelir; kurye günlük maliyeti ',
        h('b', { text: CM.tl(va.courier_daily_cost_tl) }),
        ' ',
        h('span', { class: 'assumption-label small', text: 'tahmini' }),
        '.'
      );
      $('#opwaterfall-note').title = op.explanation || '';
    },

    /* ------------------------------------------------ üç durum karşılaştırma tablosu */
    drawCompare() {
      const v = this.v;
      const K = (v.operation || {}).arms || {};
      const A = K.A;
      if (!A) {
        clear($('#compare-table'), h('div', { class: 'empty', text: 'Operasyon verisi yok.' }));
        return;
      }
      const arms = ['A', 'B'].concat($('#compare-c').checked && K.C ? ['C'] : []).concat(['D']).filter((x) => K[x]);
      const CLASS = { A: 'k-today', B: 'k-risk', C: 'k-ara', D: 'k-memory' };
      const TOP = { A: 'Bugün', B: 'Yeni yapı · ajansız', C: '+ Atama Ajanı', D: 'Yeni yapı + Courier Memory' };
      const ALT = { A: 'sabit bölge', B: 'bilgi kişiyle gider', C: 'çekirdek bölge', D: 'çekirdek bölge · üç ajan' };
      const ROW = [
        { k: 'own', name: 'Kendi bölgesinde', value: (kk) => this.ownZone(kk), f: (x) => (x === null ? '–' : pct(x, 0)), df: (d) => CM.marked(100 * d, 0), lowIsBad: true, bold: true, explanation: 'Kendi bölgesinde durak payı = 1 − yabancı durak payı (uzun dönem)' },
        { k: 'courier', name: 'Kurye', f: (x) => nf(x, 1), df: (d) => CM.marked(d, 1) },
        { k: 'fails_per_day', name: 'Başarısız teslim', f: (x) => nf(x), df: (d) => CM.marked(d, 0), bad: 'increase' },
        { k: 'overtime_hour_day', name: 'Fazla mesai (saat)', f: (x) => nf(x, 1), df: (d) => CM.marked(d, 1), bad: 'increase' },
        { k: 'total_tl_day', name: 'Operasyon maliyeti', f: (x) => CM.tl(x), df: null, bad: 'increase', bold: true },
        { k: 'per_shipment_tl', name: 'Gönderi başına', f: (x) => nf(x, 2) + ' TL', df: (d) => CM.marked(d, 2), bad: 'increase' },
      ];
      const body = ROW.map((r) =>
        h(
          'tr',
          { class: r.bold ? 'bold-row' : '' },
          h('th', { text: r.name, title: r.explanation || '' }),
          arms.map((kk) => {
            const al = (k2) => (r.value ? r.value(k2) : K[k2][r.k]);
            const x = al(kk);
            const a0 = al('A');
            const d = kk === 'A' || x === null || a0 === null ? null : x - a0;
            const bad = d !== null && ((r.bad && d > Math.abs(a0) * 0.05) || (r.lowIsBad && d < -0.05));
            return h('td', { class: CLASS[kk] + (bad ? ' bad' : '') }, h('div', { class: 'kd-row', title: d !== null ? 'Bugüne göre: ' + (r.df ? r.df(d) : (d > 0 ? '+' : '') + r.f(d)) : '' }, r.df && d !== null && Math.abs(d) > 1e-9 ? h('span', { class: 'kd-diff', text: r.df(d) }) : null, h('span', { class: 'kd-main', text: r.f(x) })));
          })
        )
      );
      const annual = h(
        'tr',
        { class: 'annual-row' },
        h('th', { text: 'Yıllık fark' }),
        arms.map((kk) => {
          if (kk === 'A') return h('td', { class: CLASS.A }, h('div', { class: 'kd-main', text: '—' }));
          const d = (K[kk].total_tl_year || K[kk].total_tl_day * this.yearTimes()) - (A.total_tl_year || A.total_tl_day * this.yearTimes());
          return h('td', { class: CLASS[kk] + (d > 0 ? ' bad' : ' good-cell'), title: d > 0 ? 'bugüne göre daha pahalı' : 'bugüne göre tasarruf' }, h('div', { class: 'kd-row' }, h('span', { class: 'kd-main', text: (d > 0 ? '+' : '−') + shortTL(Math.abs(d)) + ' TL' })));
        })
      );
      const detail = h(
        'tr',
        { class: 'detail-row' },
        h('th', { text: 'İlk deneme · km' }),
        arms.map((kk) => h('td', { class: CLASS[kk], text: `${pct(K[kk].first_attempt, 1)} · ${nf(K[kk].km_day)}` }))
      );
      clear(
        $('#compare-table'),
        h(
          'table',
          { class: 'compare3 ' + (arms.length > 3 ? 'dort' : '') },
          h('colgroup', null, h('col', { class: 'c-name' }), arms.map(() => h('col'))),
          h(
            'thead',
            null,
            h(
              'tr',
              null,
              h('th'),
              arms.map((kk) =>
                h(
                  'th',
                  { class: CLASS[kk] },
                  h('i', { class: 'kpi-key', style: { background: R.arm[kk] } }),
                  h('div', { class: 'kb-top', text: TOP[kk] }),
                  h('div', { class: 'kb-alt' }, kk === 'B' ? h('span', { class: 'risk-badge', text: 'risk' }) : null, ALT[kk])
                )
              )
            )
          ),
          h('tbody', null, body, annual, detail)
        )
      );
    },

    /* ------------------------------------------------ ikinci düzey: ajanların maliyeti ve getirisi */
    drawAgentHeadline() {
      const v = this.v;
      const L = v.llm || {},
        c = (v.gain || {}).vs_C || {},
        b = (v.gain || {}).vs_B || {};
      clear(
        $('#agent-headline'),
        h('div', { class: 'agent-headline-sentence', title: 'Hafıza + Brifing’in çekirdek bölgeli planın (C) üstüne katkısı' }, 'Gönderi başına ', h('b', { text: nf(L.per_shipment_kurus, 2) + ' kuruş' }), ' LLM → Hafıza + Brifing günde ', h('b', { text: CM.tl(c.net_tl_day) }), ' net · getiri ', h('b', { text: CM.times(c.return_multiple) })),
        h('div', { class: 'alt', text: `Üst sınır (üç ajan, geçmişe bakmadan atamaya göre): net ${CM.tl(b.net_tl_day)} / gün · getiri ${CM.times(b.return_multiple)}` })
      );
    },

    drawCost() {
      const v = this.v;
      const L = v.llm || {},
        hc = v.volume_day || {},
        tok = hc.token || {};
      const aj = L.agents || {};
      const top = L.daily_tl || Object.values(aj).reduce((a, x) => a + (x.daily_tl || 0), 0) || 1;
      const order = ['propose_assignment', 'ask_assignment', 'memory', 'briefing'].filter((k) => aj[k]).concat(Object.keys(aj).filter((k) => !AGENT_NAME[k]));
      const sourceBadge = (k) =>
        /measure|olc|ölç/.test(k || '') ? h('span', { class: 'status-badge good small-badge' }, h('i', { 'aria-hidden': 'true', text: '✓' }), 'ölçüm') : h('span', { class: 'status-badge small-badge', title: 'Token sayısı tahmindir; canlı ölçümle güncellenir' }, h('i', { 'aria-hidden': 'true', text: '≈' }), k || 'estimate');
      const rows = order.map((k) => {
        const a = aj[k];
        const [name, task] = AGENT_NAME[k] || [k, ''];
        const tc = a.token_call || {};
        return h(
          'tr',
          { title: `${name} · ${task} · ${modelName(v, a.model)}` },
          h('th', null, h('b', { text: name.replace(' Ajanı', '') }), h('span', { class: 'alt', text: ' · ' + task + ' ' }), sourceBadge(a.source)),
          h('td', { class: 'count', text: nf(a.call_day, 1) }),
          h('td', { class: 'count', text: `${shortTL(tc.input)} + ${shortTL(tc.output)}` }),
          h('td', { class: 'count', text: CM.tl(a.per_call_tl, a.per_call_tl < 1 ? 3 : 2) }),
          h('td', { class: 'count' }, h('b', { text: CM.tl(a.daily_tl, 1) }), h('span', { class: 'measures cost-measures row-inner-measures', title: `Günlük LLM maliyetinin ${pct((a.daily_tl || 0) / top, 0)}’i` }, h('i', { style: { width: (100 * (a.daily_tl || 0)) / top + '%' } })))
        );
      });
      clear(
        $('#cost'),
        h(
          'table',
          { class: 'cost-table' },
          h('thead', null, h('tr', null, h('th', { text: `Ajan · ${nf(hc.llm_call)} çağrı / gün` }), h('th', { class: 'count', text: 'Çağrı / gün' }), h('th', { class: 'count', text: 'Token / çağrı' }), h('th', { class: 'count', text: 'TL / çağrı' }), h('th', { class: 'count', text: 'TL / gün' }))),
          h('tbody', null, rows),
          h('tfoot', null, h('tr', null, h('th', { title: `Not başına ${CM.tl(L.per_note_tl, 2)} · brifing başına ${CM.tl(L.per_briefing_tl, 2)}` }, 'Toplam ', h('span', { class: 'alt', text: `· ${nf(L.per_shipment_kurus, 2)} kuruş / gönderi` })), h('td', { class: 'count', text: nf(hc.llm_call) }), h('td', { class: 'count', text: `${shortTL(tok.input)} + ${shortTL(tok.output)}` }), h('td'), h('td', { class: 'count' }, h('b', { text: CM.tl(L.daily_tl, 1) }))))
        ),
        h('div', { class: 'chart-note', title: (v.assumptions || {}).price_source || '' }, 'Token sayıları tahmin; liste fiyatı (Bedrock farklı olabilir).')
      );
    },

    drawGain() {
      const v = this.v;
      const k = (v.gain || {})[this.compare] || {};
      const va = v.assumptions || {};
      const llm = (v.llm || {}).daily_tl || 0;
      const top = this.compare === 'vs_B';
      const compareName = top ? 'Üç ajan (D) ← geçmişe bakmadan atama (B)' : 'Hafıza + Brifing (D) ← çekirdek bölgeli plan (C)';
      clear($('#gain-explanation'), top ? h('span', { class: 'upper-limit-badge', text: 'ÜST SINIR' }) : null, h('b', { text: compareName, title: k.comparison || '' }), ` · TL / gün · getiri ${CM.times(k.return_multiple)}`);
      const b1 = k.fails_tl_day || 0,
        b2 = k.overtime_tl_day || 0,
        mins = k.direct_gain_tl_day || b1 + b2,
        net = k.net_tl_day !== undefined ? k.net_tl_day : mins - llm;
      const rows = [
        { name: 'Önlenen başarısız teslim', alt: `${nf(k.prevented_fails_day, 1)} / gün × ${CM.tl(va.failed_attempt_tl, 0)}`, head: 0, last: b1, type: 'increase', label: '+' + CM.tl(b1) },
        { name: 'Önlenen fazla mesai', alt: `${nf(k.prevented_overtime_min_day)} dk / gün`, head: b1, last: b1 + b2, type: 'increase', label: '+' + CM.tl(b2) },
        { name: 'Doğrudan kazanç', head: 0, last: mins, type: 'total', label: CM.tl(mins) },
        { name: 'LLM maliyeti', head: mins, last: mins - llm, type: 'decrease', label: '−' + CM.tl(llm) },
        { name: 'Net kazanç', head: 0, last: net, type: 'total', label: CM.tl(net) },
        { name: 'Kapasite (getiriye katılmaz)', alt: `${nf(k.capacity_courier_hour_day, 1)} kurye-saat`, head: 0, last: k.capacity_tl_day || 0, type: 'side', label: '≈ ' + CM.tl(k.capacity_tl_day), note: 'Kapıda kazanılan süre kurye zamanını serbest bırakır; ek iş verilmedikçe paraya dönmez.' },
      ];
      const mx = Math.max(mins, k.capacity_tl_day || 0, 1);
      const step = CM.tickStep(mx, 4);
      const max = Math.ceil(mx / step) * step;
      CM.chartCard(
        $('#g-waterfall'),
        null,
        (container) =>
          CM.waterfall(container, {
            label: 'Hafıza ve Brifing kazanç bileşenleri, TL / gün',
            rows,
            max,
            ticks: CM.ticks(0, max, step),
            format: (t) => (t >= 1e6 ? nf(t / 1e6, 1) + ' mn' : nf(t)),
            divider: 5,
            leftGap: 190,
            colorIncrease: VALUE_COLOR.increase,
            colorDecrease: VALUE_COLOR.decrease,
            colorTotal: VALUE_COLOR.total,
            colorSide: VALUE_COLOR.side,
          }),
        () => CM.table(['Bileşen', 'TL / gün', 'Açıklama'], rows.map((r) => [r.name, r.label, r.alt || '']))
      );
      clear(
        $('#waterfall-legend'),
        CM.mapLegend([
          { type: 'block', color: VALUE_COLOR.increase, text: 'Kazanç' },
          { type: 'block', color: VALUE_COLOR.decrease, text: 'LLM maliyeti' },
          { type: 'block', color: VALUE_COLOR.total, text: 'Toplam' },
          { type: 'block', color: VALUE_COLOR.side, text: 'Getiriye katılmayan' },
        ])
      );
      const va2 = v.assumptions || {};
      clear($('#derived'), 'Türetilen: kurye dakikası ', h('b', { text: nf(va2.courier_min_tl, 2) + ' TL' }), ' · başarısız deneme ', h('b', { text: CM.tl(va2.failed_attempt_tl, 0) }), ` (ikinci deneme ${nf(va2.second_attempt_min)} dk + yol + diğer) · fazla mesai ×${nf(va2.overtime_multiplier, 1)}`);
    },

    drawScale() {
      const v = this.v;
      const ol = v.scale || [];
      const op = new Map(((v.operation || {}).scale || []).map((r) => [r.branch, r]));
      clear(
        $('#scale'),
        h(
          'table',
          { class: 'data-table scale-table' },
          h('thead', null, h('tr', null, h('th', { text: 'Şube' }), h('th', { text: 'Operasyon tasarrufu', title: 'Bugüne göre, yeni yapı + Courier Memory' }), h('th', { text: 'Ajansız ek maliyet', title: 'Ajansız geçişin bugüne göre ek maliyeti' }), h('th', { text: 'LLM' }), h('th', { text: 'Hafıza + Brifing net', title: 'Uyumlu atamaya göre' }))),
          h(
            'tbody',
            null,
            ol.map((r) => {
              const o = op.get(r.branch) || {};
              return h('tr', null, h('th', { text: nf(r.branch) }), h('td', null, h('b', { text: shortTL(o.savings_tl_year) })), h('td', { class: 'warning-text', text: o.agentless_extra_cost_tl_year !== undefined ? '+' + shortTL(o.agentless_extra_cost_tl_year) : '–' }), h('td', { text: shortTL(r.llm_tl_year) }), h('td', { text: shortTL(r.net_tl_year_vs_C) }));
            })
          )
        )
      );
      const am = (v.assumptions || {}).agent_model || {};
      const all = Object.values(am);
      const mk = v.model_comparison || [];
      CM.chartCard(
        $('#g-model'),
        null,
        (container) =>
          CM.simpleBar(container, {
            label: 'Model başına gönderi maliyeti',
            title: 'Gönderi başına',
            color: VALUE_COLOR.decrease,
            leftGap: 118,
            rightGap: 150,
            rows: mk.map((m) => ({
              name: m.name || modelName(v, m.model),
              value: m.per_shipment_kurus,
              label: `${nf(m.per_shipment_kurus, 2)} kr · getiri ${CM.times(m.return_multiple_vs_C)}`,
              accent: all.length && all.every((x) => x === m.model),
              note: `LLM ${CM.tl(m.llm_tl_day)} / gün`,
            })),
          }),
        () => CM.table(['Model', 'Gönderi başına', 'LLM / gün', 'Getiri'], mk.map((m) => [m.name || m.model, nf(m.per_shipment_kurus, 2) + ' kr', CM.tl(m.llm_tl_day), CM.times(m.return_multiple_vs_C)]))
      );
    },
  };
  SCREEN.value = Value;

  /* ====================================================================== başlat */
  async function start() {
    for (const b of $$('.tabs [data-screen]')) b.addEventListener('click', () => showScreen(b.dataset.screen));
    window.addEventListener('hashchange', () => showScreen(location.hash.slice(1)));
    document.addEventListener('keydown', (e) => {
      if (e.target.closest('input, textarea, select')) return;
      if (e.key === '1') showScreen('branch');
      else if (e.key === '2') showScreen('courier');
      else if (e.key === '3') showScreen('simulation');
      else if (e.key === '4') showScreen('value');
    });
    loadStatus();
    try {
      const [meta, blocks] = await Promise.all([CM.fetch('/api/meta'), CM.fetch('/api/blocks')]);
      S.meta = meta;
      S.proj = CM.projection(blocks);
    } catch (e) {
      clear($('main'), h('div', { class: 'opening-error' }, errorBox(e, 'API çalışıyor mu? Proje kökünde: uvicorn api.main:app --port 8765')));
      return;
    }
    CM.fetch('/api/couriers')
      .then((k) => (Sim.couriers = k))
      .catch(() => {});
    const crit = S.meta.critical || {};
    const days = S.meta.eval_days || [];
    S.day = days.includes(crit.day) ? crit.day : days[0];
    if (S.meta.label) $('#data-label').textContent = S.meta.label;
    daySelector();
    Branch.init();
    Courier.init();
    $('#btn-back').addEventListener('click', () => Branch.backToProposal());
    showScreen(location.hash.slice(1) || 'branch');
  }

  CM.status = S;
  CM.screens = SCREEN;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
