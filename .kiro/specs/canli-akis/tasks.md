# Uygulama planı: Canlı akış

- [x] 1. `api/live.py`: tek koşu, olay listesi, sekiz adımlık zincir; `/api/live`, `/api/live/start`, `/api/live/stream` (SSE, async)
  - _Gereksinimler: 1.1–1.5, 5.3_
- [x] 2. `ui/flow/index.html`: olay güdümlü izleyici; sunum modu ("Günü planla", `start`, `qr`); biten adıma dönüş, "Canlıya dön"
  - _Gereksinimler: 2.1, 2.2, 2.4, 3.3_
- [x] 3. Telefon düzeni (≤ 760 px tek sütun, iz kendi kutusunda)
  - _Gereksinimler: 2.3_
- [x] 4. Hikaye: Sahne 2 harita + "Günü planla", Sahne 3 akış ekranı; tuş iletimi
  - _Gereksinimler: 3.1–3.3_
- [x] 5. QR: `js/qr.js` + `vendor/qrcode.js`; sağ alt, Q; kapanış sahnesi `/flow/`
  - _Gereksinimler: 4.1, 4.2_
- [x] 6. Göreli sonda-`/` yönlendirmesi (HTTPS)
  - _Gereksinimler: 5.1_
- [x] 7. Kabul testi `api/tests/test_live.py`
  - _Gereksinimler: 1.1–1.3, 1.5, 5.1, 5.2_
- [ ] 8. ALB'yi yalnız CloudFront'a aç (doğrudan `http://<ALB>` erişimi kapanır)
  - _Gereksinimler: 5.1_
