/* Canlı akış QR'ı: sunum ekranında sağ altta. Adres sayfanın kendi kökünden kurulur (HTTPS sayfa → HTTPS adres),
   hedef izleme modundaki /flow/ (koşu başlatamaz). Sahne 2–3'te kendiliğinden görünür; Q her sahnede açar/kapatır.
   Kodlayıcı: vendor/qrcode.js (Kazuhiko Arase, MIT). */
(function (CM) {
  CM.flowUrl = () => new URL(CM.API ? CM.API.replace(/\/$/, '') + '/flow/' : '../flow/', location.href).href;
  CM.qrSvg = function (text, alt) {
    if (!window.qrcode) return '';
    const q = qrcode(0, 'M');
    q.addData(text);
    q.make();
    return q.createSvgTag({ cellSize: 4, margin: 2, scalable: true, alt: alt || 'QR kodu' });
  };

  let auto = false, manual = null, built = '';
  function draw() {
    const el = CM.$('qr');
    if (!el) return;
    const show = manual ?? auto;
    const url = CM.flowUrl();
    if (show && built !== url) {
      el.innerHTML = `<b>Telefonda canlı izleyin</b><div class="q">${CM.qrSvg(url, 'Canlı akış QR kodu')}</div><small>${CM.escape(url.replace(/^https?:\/\//, ''))}</small>`;
      built = url;
    }
    el.hidden = !show;
  }
  CM.qrAuto = (on) => { auto = !!on; manual = null; draw(); };     // sahne değişince sahnenin varsayılanı
  CM.toggleQr = () => { manual = !(manual ?? auto); draw(); };
})(window.CM);
