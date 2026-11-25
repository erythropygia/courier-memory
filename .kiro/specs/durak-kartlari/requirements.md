# Gereksinimler: Durak bilgi kartları ve yaklaşma tetiği (Faz 2d)

## Giriş

Kuryenin bıraktığı her bilgi rotayı değiştirmez: "sitenin önünde park yeri yok, aracı arka sokaktaki otoparka bırakın", "asansör yok, 4. kat", "bahçede köpek var". Bu bilgiler hafızaya yazılır, plana ve rotaya girmez, kuryeye doğru anda **durak kartı** olarak verilir. Sözleşme: `docs/sozlesmeler.md` §11.

## Gereksinimler

### Gereksinim 1: Bilgi türleri
**Kullanıcı hikayesi:** Bir kurye olarak, park yeri ya da kat bilgisi gibi notlarımın atılmamasını istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL hafıza türlerini rotayı etkileyen türler (`QUIRK_KINDS`) ve yalnız bilgi taşıyan türler (`INFO_KINDS = park, building_access, directions, animal, other_info`) olarak ayırmalıdır.
2. WHEN rota ya da plan hesaplanırken THE SYSTEM SHALL bilgi türlerini yok saymalıdır; simülasyonla eşitlik ve yayımlanan rakamlar değişmez.
3. WHEN kurallı sınıflandırıcı bir notu değerlendirirken THE SYSTEM SHALL rotayı etkileyen türe öncelik vermeli; bilgi türü yalnız açıkça daha çok anahtar kelime eşleşirse seçilir.
4. THE SYSTEM SHALL simülatörün ürettiği notların hiçbirini bilgi türü olarak sınıflandırmamalıdır.
5. WHEN bilgi türünde kayıt yazılırken THE SYSTEM SHALL ipucu metni olarak notun temizlenmiş halini kullanmalıdır (tek cümle, en çok 140 karakter); kalıp cümle yoktur.

### Gereksinim 2: Şifre koruması
**Kullanıcı hikayesi:** Bir site yöneticisi olarak, kapı şifremizin bir kargo sisteminde durmasını istemiyorum.

#### Kabul kriterleri
1. IF hafızaya yazılacak metin kapı ya da bina şifresi, giriş kodu ya da alarm kodu içeriyorsa THEN THE SYSTEM SHALL yazmayı reddetmelidir.
2. WHEN kurallı yol şifre içeren bir notu işlerken THE SYSTEM SHALL şifre geçen parçayı ayıklamalı, notun kalanını kaydetmeli ve `personal_data_redacted: true` bildirmelidir.

### Gereksinim 3: Kart
**Kullanıcı hikayesi:** Bir kurye olarak, bilginin nereden geldiğini ve ne kadar güvenilir olduğunu bilmek istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL her geçerli hafıza kaydını yapılı bir karta çevirmelidir: tür, başlık, metin, an, kaynak sayısı, güven, rotayı etkileyip etkilemediği.
2. THE SYSTEM SHALL anı türden çıkarmalıdır: `park, directions, position_wrong, roadwork, back_entry` → `approaching`; diğerleri → `at_door`.
3. THE SYSTEM SHALL güveni şöyle belirlemelidir: teyide alınmışsa `needs_confirmation`; en az iki kaynak ya da kurye teyidi varsa `confirmed`; yoksa `single_source`.
4. THE SYSTEM SHALL kartları brifingle aynı gün ve saat süzgecinden geçirmelidir (Çarşamba günü "Cumartesi kapalı" gösterilmez).
5. THE SYSTEM SHALL durak içinde kartları şu sırayla vermelidir: yaklaşırken, rotayı etkileyen, çok kaynaklı.

### Gereksinim 4: Yaklaşma tetiği
**Kullanıcı hikayesi:** Bir kurye olarak, park bilgisini durağa varmadan, zil bilgisini kapıda duymak istiyorum.

#### Kabul kriterleri
1. WHEN kurye sıradaki durağa 400 m'den yakın ve 60 m'den uzaksa THE SYSTEM SHALL yalnız `approaching` kartlarını döndürmelidir.
2. WHEN kurye durağa 60 m'den yakınsa THE SYSTEM SHALL `at_door` kartlarını ve henüz söylenmemiş `approaching` kartlarını döndürmelidir.
3. WHEN kurye 400 m'den uzaksa THE SYSTEM SHALL kart döndürmemeli, bekleyen kart sayısını bildirmelidir.
4. THE SYSTEM SHALL istemcinin `shown` listesinde bildirdiği kartları tekrar söylememelidir.
5. THE SYSTEM SHALL bir tetikte en çok iki kart döndürmelidir (sürüş güvenliği).
6. THE SYSTEM SHALL tetiği durumsuz hesaplamalıdır: sunucuda kurye başına oturum tutulmaz, LLM çağrılmaz.
7. IF `next_order` rota dışındaysa ya da koordinat geçersizse THEN THE SYSTEM SHALL 422 döndürmelidir.
