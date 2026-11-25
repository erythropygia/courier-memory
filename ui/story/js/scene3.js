/* Sahne 3 · Canlı akış: /flow/ akış ekranı sunum modunda (iframe, ?sunum=1). "Günü planla" sekiz adımlık ajan zincirini sunucuda
   bir kez başlatır (api/live.py); Sahne 2'nin butonuyla gelindiyse açılışta başlar (&start=1). QR ile gelen izleyiciler aynı
   olayları /flow/'da canlı izler, koşu başlatamaz. Harita perdenin arkasında; bu sahnede yan panel açılmaz.
   Akış ekranı odaktayken tuşlar hikayeye iletilir (main.js, message). */
(function (CM) {
  const S3 = {
    no: 3, name: 'Canlı akış', stepCount: 1,
    title: 'Gün 32 · ajan zinciri canlı · izleyiciler telefonda',
    attribution: '<b>Uygulama verisi · 1 aylık geçmiş</b> · ajanlar canlı çalışır · kurye adları ve adresler simülasyon',

    async enter() {
      CM.curtain(true);
      const url = new URL(CM.flowUrl());
      url.searchParams.set('sunum', '1');
      url.searchParams.set('qr', '1');                 // sağ alttaki QR'a yer bırak
      if (CM.liveStart) url.searchParams.set('start', '1');
      CM.liveStart = false;
      CM.board(`<iframe id="live-frame" title="Canlı akış" src="${CM.escape(url.href)}"></iframe>`, 'live');
    },
    step() {},
    leaving() { CM.board(''); CM.curtain(false); },
  };
  CM.scenes = CM.scenes || {};
  CM.scenes[3] = S3;
})(window.CM);
