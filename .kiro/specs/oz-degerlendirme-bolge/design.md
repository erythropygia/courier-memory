# Tasarım: Değerlendirme Ajanı, Bölge Ajanı ve ajan akışı

| Dosya | Ne |
|---|---|
| `agents/feed.py` | `AgentFeed`: `add`, `update`, `items`, `reset`; dosya `agent_feed.json` (hafıza dosyasının yanında) |
| `agents/review.py` | `ReviewTools` (`trend`, `hint_outcomes`, `recurring_problems`, `duration_estimate`, `assignment_check`, `apply`), `ReviewStore.morning_review`, `ReviewStore.decision` |
| `agents/region.py` | `RegionStats`: blok istatistiği, zorluk endeksi, `cluster_card`, `branch_layer` |
| `agents/region_agent.py` | `RegionTools` (`branch_summary`, `hard_blocks`, `cluster_summary`, `open_question`), `RegionAgent.cluster_card`, `RegionAgent.branch` |
| `agents/memorybook.py` | `flag_for_confirmation`, `undo` |
| `agents/prompts/review.md`, `region.md` | Türkçe istemler, İngilizce araç adları |
| `api/main.py` | `/api/review/*`, `/api/region/*`, `/api/feed`, `/api/demo/reset` |

## Kararlar

- **Korkuluklar araçtadır, istemde değil.** Model `drop_record` istese de araç tek kaynak + iki çelişki şartını arar; şart yoksa eylemi `flag_for_confirmation`'a çevirir. Parametreler `PARAM_LIMITS` içinde kırpılır.
- **Her eylem akışa yazılır ve geri alınabilir.** Düşürme ve teyide alma `MemoryBook.undo` ile, parametre eski değeriyle döner. Akış olayı `undoable` taşır.
- **Canlı ve kurallı yol aynı araçları aynı sırayla çağırır**; iz biçimi Orkestratör'le aynıdır (`agents/trace.py`). Arayüz farkı yalnız `source` alanından anlar.
- **Zorluk kuryenin değil bloğun özelliğidir.** Endeks kuryeler arası karşılaştırma üretmez.
- **Soru kuyruğu ortaktır.** Bölge Ajanı'nın açtığı sorular Değerlendirme Ajanı'nın `question_queue`'suna düşer; Hasat Ajanı'yla aynı cevap yolundan (Hafıza Ajanı) geçer.

## Test

`agents/tests/test_review.py` (4), `agents/tests/test_region_agent.py` (5; sahte LLM ile canlı döngü ve hata durumunda kurala düşüş), `api/tests/test_review_region_api.py` (3).

## Açık riskler

- İki ajan da `agents.cost` ve `agents.economics` ajan listelerinde yok; token ve TL hesabına girmiyor.
- Değerlendirme Ajanı'nın `target` şeması `anyOf` kullanır; canlı Bedrock'ta sınanmadı.
