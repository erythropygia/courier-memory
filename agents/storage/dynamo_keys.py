"""DynamoDB tek tablo anahtar düzeni (CM_STORAGE=dynamodb).

Tek tablo, isteğe bağlı (on-demand) faturalama, iki string anahtar: PK (bölüm) ve SK (sıralama). GSI yok;
tüm erişimler anahtarla (GetItem / Query / BatchGetItem) ve tutarlı okumayla yapılır.

  PK                                  SK                     içerik
  ----------------------------------  ---------------------  --------------------------------------------------
  MEMORY#{run_id}                     META                   çalıştırma başı hafıza durumu: generation, seed_day,
                                                             version (değişiklik sayacı), next_seq, entry_count,
                                                             previous_generation, seeded_at
  MEMORY#{run_id}#GEN#{generation}    ENTRY#{entry_id}       bir hafıza kaydı (MemoryBook giriş alanları + _seq)
  MEMORY#{run_id}#GEN#{generation}    LOG#{version:010d}     hafıza değişiklik günlüğü (operation, record, day, reason)
  FEED                                META                   ajan akışı durumu: generation, seq (son olay no),
                                                             previous_generation
  FEED#GEN#{generation}               EVENT#{n:010d}         bir ajan akışı olayı (AgentFeed olay alanları)
  USAGE#{YYYY-MM-DD}                  {zaman}#{ajan}#{rastgele}  bir model isteğinin token kullanımı

Nesil (generation): reset/tohumlama yeni bir bölüme yazılır, META tek koşullu yazımla yeni nesle geçirilir;
önceki nesil bir reset boyunca bekletilir (o anda okuyan süreçler için), ondan öncekiler silinir.

Eşzamanlılık: hafızadaki her değişiklik tek bir TransactWriteItems'tır: META.version koşullu artırılır
(iyimser kilit), kayıt yazılır ve LOG#{yeni sürüm} eklenir. Böylece günlük boşluksuz ve sıralıdır; diğer süreçler
META'yı okuyup yalnız yeni LOG kayıtlarının işaret ettiği girişleri yeniden okur. Akış olayları da aynı yolla
(META.seq koşullu) boşluksuz numaralanır.

Saklama: LOG# ve EVENT# öğeleri nesil içinde kırpılmaz (TTL yok); tam yükleme yalnız son 500 LOG'u, akış okuması
son MAX_EVENTS (2000) olayı okur. Eski nesiller reset'te silinir. Sayılar Decimal saklanır; tam değerli float
(ör. 2.0) okunurken int döner.
"""
from __future__ import annotations

PK = "PK"
SK = "SK"
META = "META"
FEED_PK = "FEED"
INITIAL_GENERATION = "0"
WIDTH = 10


def memory_meta_key(run_id: str) -> dict:
    return {PK: f"MEMORY#{run_id}", SK: META}


def memory_partition(run_id: str, generation: str) -> str:
    return f"MEMORY#{run_id}#GEN#{generation}"


def entry_key(run_id: str, generation: str, entry_id: str) -> dict:
    return {PK: memory_partition(run_id, generation), SK: f"ENTRY#{entry_id}"}


def log_sk(version: int) -> str:
    return f"LOG#{version:0{WIDTH}d}"


def feed_meta_key() -> dict:
    return {PK: FEED_PK, SK: META}


def feed_partition(generation: str) -> str:
    return f"{FEED_PK}#GEN#{generation}"


def event_sk(n: int) -> str:
    return f"EVENT#{n:0{WIDTH}d}"


def event_key(generation: str, n: int) -> dict:
    return {PK: feed_partition(generation), SK: event_sk(n)}


def usage_key(day: str, stamp: str, agent: str, nonce: str) -> dict:
    return {PK: f"USAGE#{day}", SK: f"{stamp}#{agent}#{nonce}"}


def table_definition(name: str) -> dict:
    """CreateTable parametreleri (dağıtım betiği ve testler aynı şemayı kullanır).

    SSESpecification bilerek verilmez: DynamoDB varsayılan şifrelemesi (AWS sahipli anahtar) her tabloda açıktır.
    """
    return {"TableName": name, "BillingMode": "PAY_PER_REQUEST",
            "AttributeDefinitions": [{"AttributeName": PK, "AttributeType": "S"}, {"AttributeName": SK, "AttributeType": "S"}],
            "KeySchema": [{"AttributeName": PK, "KeyType": "HASH"}, {"AttributeName": SK, "KeyType": "RANGE"}]}
