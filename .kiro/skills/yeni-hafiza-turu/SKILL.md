---
name: yeni-hafiza-turu
description: Şube hafızasına yeni bir kayıt türü ekler (ör. "teslimat saati tercihi", "yük asansörü") ve türü uçtan uca bağlar: tür listesi, sınıflandırıcı, kart, istem, arayüz etiketleri, testler, belgeler. "Yeni hafıza türü ekle", "yeni not türü" istendiğinde kullan.
---

# Yeni hafıza türü

Önce karar ver ve kullanıcıya onaylat: tür **rotayı etkiler mi**?
- Etkilemiyorsa bilgi türüdür (`INFO_KINDS`): simülatör değişmez, yayımlanan rakamlar değişmez. Bu skill bunu yapar.
- Etkiliyorsa simülatör, kalibrasyon ve yayım zinciri değişir; bu skill'in kapsamı dışıdır, ayrı spec aç.

Kod adı İngilizce `snake_case`, kullanıcıya görünen etiket Türkçe (`structure.md` → Adlandırma).

## Dokunulacak yerler (sırayla)

1. `agents/rundata.py` → `INFO_KINDS`
2. `agents/memory.py` → `INFO_KEYWORDS` (Türkçe anahtar kalıplar; tek başına belirsiz kelime koyma)
3. `agents/cards.py` → `TITLE`; durağa varmadan lazımsa `APPROACH_KINDS`
4. `agents/region.py` → `KIND_NAME`
5. `agents/prompts/memory.md` → tür listesi ve bir satır açıklama
6. Arayüz etiketleri: `ui/common.js` ve `ui-story/js/common.js` → `CM.QUIRK`; `ui-flow/index.html` → `KIND`
7. Testler: `agents/tests/test_cards.py` içine sınıflandırma ve kart testi; simülatör notlarının hiçbiri yeni türe düşmemeli (mevcut test bunu denetler)
8. Belgeler: `docs/sozlesmeler.md` §11, `.kiro/specs/durak-kartlari/` (gereksinim 1.1 ve görev listesi), `docs/ad-eslemesi.tsv` gerekirse

## Bitti sayılması için

```bash
PYTHONUTF8=1 CM_LLM_MODE=mock pytest -q agents/tests/test_cards.py api/tests/test_cards_api.py
```
ve bir gerçek saha cümlesiyle elle deneme: `POST /api/note` → `type` yeni tür, `GET /api/cards/32/O02` içinde kart. AgentCore'a da gidecekse `deploy/agentcore/bootstrap.sh` + `agentcore deploy`.
