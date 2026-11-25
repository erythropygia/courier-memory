/* Sahne 2 · Sabah: olağan bir Çarşamba sabahı haritada. "Günü planla" (ya da →) sekiz adımlık ajan zincirini sunucuda canlı
   başlatır ve Sahne 3'ün akış ekranına geçer (api/live.py, ui/flow/). İzleyiciler aynı akışı sağ alttaki QR ile telefonda izler.
   Orkestratörün izi ve kararları akış ekranında; bu sahnede iz paneli açılmaz. */
(function (CM) {
  const INK = '#3A332D';
  let data = null, branch = null;

  function camera() {
    if (!CM.H.gl) return null;
    const w = innerWidth, h = innerHeight;
    const c = CM.H.map.cameraForBounds([[29.064, 41.047], [29.332, 41.235]], { padding: { left: w * 0.24, right: w * 0.24, top: h * 0.05, bottom: h * 0.12 }, bearing: -8 });
    return { center: c.center, zoom: c.zoom + 0.3, pitch: 42, bearing: -8 };
  }

  const S2 = {
    no: 2, name: 'Sabah', stepCount: 1,
    title: 'Gün 32 · Çarşamba sabahı · ajan zinciri günü planlamaya hazır',
    attribution: '<b>Uygulama verisi · 1 aylık geçmiş</b> · Harita: OpenStreetMap (OpenFreeMap © OpenMapTiles) · konumlar Beykoz saha verisi · sonuçlar simülasyon',

    async enter() {
      if (!data) data = await fetch('data/scene2.json').then((r) => r.json());
      CM.adjust({ v26: 0 });
      CM.H.frame([29.064, 41.047, 29.332, 41.235]);
      const dep = data.depot;
      const rad = ['interpolate', ['linear'], ['zoom'], 10, 1.8, 11, 2.2, 13, 3.2, 16, 6];
      const p26 = CM.gj(data.pts26.map((p) => CM.point(p[0], p[1], {})));
      CM.H.add({ id: 's2-p26', type: 'circle', data: p26, paint: (S) => ({ 'circle-radius': rad, 'circle-color': INK, 'circle-opacity': 0.6 * S.v26,
        'circle-stroke-color': '#FBF8F2', 'circle-stroke-width': 0, 'circle-stroke-opacity': 0.6 * S.v26 }) });
      branch = CM.H.mark(CM.branchEl(), [dep[1], dep[0]], 'left');
      CM.tween({ v26: 1 }, 1600);
      CM.H.end(camera(), 1800);
    },

    step() {
      CM.figure([]);
      CM.action('<button id="plan">Günü planla <span class="kbd">→</span></button><span class="hint">Sekiz ajan adımı canlı çalışır · izleyiciler sağ alttaki QR ile telefondan izler</span>');
      CM.$('plan').onclick = () => CM.next && CM.next();
    },
    next() { CM.liveStart = true; return false; },     // false → main.js sonraki sahneyi (3 · canlı akış) açar; akış orada başlar

    leaving() {
      if (branch) branch.remove();
      branch = null;
      CM.cards(''); CM.figure([]); CM.action('');
      CM.H.clear();
    },
  };
  CM.scenes = CM.scenes || {};
  CM.scenes[2] = S2;
})(window.CM);
