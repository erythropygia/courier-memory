/* Küçük yardımcılar: MapLibre ifadeleri (dalga, renk geçişi) + WebGL yoksa aynı ifadeleri JS'te değerlendiren yorumlayıcı. */
window.CM = window.CM || {};
(function (CM) {
  const W = 0.28; // dalga cephesinin genişliği (0–1 gecikme ölçeğinde)

  // dalga: t 0..1 sahne ilerlemesi, dk kutunun gecikmesi (0..1) → 0..1 (sayı; katman başına sabit opaklık için)
  CM.dg = (t, mins) => Math.min(1, Math.max(0, (t * (1 + W) - mins) / W));

  CM.easing = {
    io: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
    out: (t) => 1 - Math.pow(1 - t, 3),
  };

  // --- yorumlayıcı (yalnız kullandığımız alt küme)
  function ev(e, p) {
    if (!Array.isArray(e)) return e;
    const [op, ...a] = e;
    switch (op) {
      case 'get': return p[a[0]];
      case 'literal': return a[0];
      case '+': return a.reduce((s, x) => s + ev(x, p), 0);
      case '-': return a.length === 1 ? -ev(a[0], p) : ev(a[0], p) - ev(a[1], p);
      case '*': return a.reduce((s, x) => s * ev(x, p), 1);
      case '/': return ev(a[0], p) / ev(a[1], p);
      case 'min': return Math.min(...a.map((x) => ev(x, p)));
      case 'max': return Math.max(...a.map((x) => ev(x, p)));
      case '<': return ev(a[0], p) < ev(a[1], p);
      case '>': return ev(a[0], p) > ev(a[1], p);
      case '==': return ev(a[0], p) === ev(a[1], p);
      case 'coalesce': for (const x of a) { const v = ev(x, p); if (v != null) return v; } return null;
      case 'case': {
        for (let i = 0; i + 1 < a.length; i += 2) if (ev(a[i], p)) return ev(a[i + 1], p);
        return ev(a[a.length - 1], p);
      }
      case 'match': {
        const v = ev(a[0], p);
        for (let i = 1; i + 1 < a.length; i += 2) {
          const k = a[i];
          if (Array.isArray(k) ? k.includes(v) : k === v) return ev(a[i + 1], p);
        }
        return ev(a[a.length - 1], p);
      }
      case 'to-color': return ev(a[0], p);
      case 'zoom': return 12;
      case 'interpolate': { // 2D yedekte zoom sabit: ikinci durağın çıktısı
        const outs = a.slice(2).filter((_, i) => i % 2 === 1);
        return ev(outs[Math.min(1, outs.length - 1)], p);
      }
      default: return null;
    }
  }
  CM.evaluate = ev;
})(window.CM);
