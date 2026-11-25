# Uygulama planı: Demo izi sayfası

- [x] 1. `ui/demo/build.py`: sekiz adımı süreç içinde çalıştır, görünüm modeline çevir, sıfırla
  - _Gereksinimler: 1.1, 1.2, 1.4, 3.2_
- [x] 2. `ui/demo/template.html`: mobil tek sütun, ajan şeridi, araç ayrıntısı, kaynak rozeti
  - _Gereksinimler: 1.2, 1.3, 1.4, 4.1, 4.2_
- [x] 3. Dürüstlük metinleri: kurallı mod uyarısı, müdür adımı, simülasyon notu; ham nottaki şifre üstü çizili
  - _Gereksinimler: 2.1–2.3, 3.1_
- [x] 4. QR üretimi ve hikaye Sahne 8 kapanışında gösterim; `/demo/` bağlaması
  - _Gereksinimler: 4.3_
- [x] 5. Kabul testi `api/tests/test_demo_page.py`
  - _Gereksinimler: 1.1, 1.2, 3.1, 3.2_
- [x] 6. QR AWS web adresine (`/demo/`) yönlendirildi; dağıtım main'e push ile CI'dan
  - _Gereksinimler: 4.3_
- [ ] 7. Canlı (Bedrock) koşuyla yeniden üret: düşünceler şablon değil Claude'un kendi metni olur
  - _Gereksinimler: 2.1_
- [x] 8. Hikaye kapanış QR'ı canlı akışa (`/flow/`) gider; QR tarayıcıda sayfanın kökünden üretilir (`.kiro/specs/canli-akis/`). `/demo/` adresi geçmiş koşu sayfası olarak kalır
  - _Gereksinimler: 4.3_
