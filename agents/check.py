"""Bedrock bağlantı kontrolü: etkinlik günü AWS hesabı gelince ilk komut.

python -m agents.check
"""
from __future__ import annotations

import os
import time

from .llm import LLM


def main() -> int:
    llm = LLM(mode="live")
    print(f"Model: {llm.model}\nİstemci: {llm.bedrock_client} (CM_BEDROCK_CLIENT)\nBölge: {llm.region}\nKimlik: "
          f"{'CM_BEDROCK_API_KEY' if os.environ.get('CM_BEDROCK_API_KEY') else os.environ.get('AWS_PROFILE') or 'varsayılan AWS zinciri'}")
    import anthropic

    t = time.time()
    try:
        r = llm.client().messages.create(model=llm.model, max_tokens=200, output_config={"effort": "low"},
                                         messages=[{"role": "user", "content": "Tek kelimeyle cevap ver: Türkiye'nin başkenti?"}])
    except anthropic.AuthenticationError as e:
        print(f"✗ Kimlik doğrulanamadı (401). AWS kimlik bilgilerini ya da CM_BEDROCK_API_KEY'i kontrol edin.\n  {e}")
        return 1
    except anthropic.PermissionDeniedError as e:
        print(f"✗ Erişim yok (403). Bedrock konsolu → Model access → bu modele erişim isteyin; IAM'de bedrock:InvokeModel izni olmalı.\n  {e}")
        return 1
    except anthropic.NotFoundError as e:
        print(f"✗ Model bulunamadı (404). CM_MODEL_ID ve AWS_REGION'ı kontrol edin; model bu bölgede olmayabilir.\n  {e}")
        return 1
    except anthropic.APIStatusError as e:
        print(f"✗ API hatası {e.status_code}: {e.message}")
        return 1
    except anthropic.APIConnectionError as e:
        print(f"✗ Bağlantı hatası: {e}")
        return 1
    text = "".join(b.text for b in r.content if b.type == "text")
    print(f"✓ Yanıt ({time.time() - t:.1f} sn, stop_reason={r.stop_reason}): {text.strip()}")

    # 2. adım: ajanların kullandığı istek biçimiyle (strict araç, effort, önbellek, bitiş aracı) mini döngü
    from .llm import AgentError, Tool, obj

    calls = []
    tools = [Tool("add", "İki tam sayıyı toplar.", obj({"a": {"type": "integer"}, "b": {"type": "integer"}}),
                  lambda i: calls.append(i) or {"result": i["a"] + i["b"]}),
             Tool("finish", "Sonucu kaydeder (son adım).", obj({"answer": {"type": "integer"}}))]
    t = time.time()
    try:
        run = llm.run_agent(agent="check", system="Sen bir test ajanısın. Önce `add` aracını kullan, sonra sonucu `finish` ile kaydet.",
                            user="17 ile 25'i topla.", tools=tools, finish_tool="finish", effort="low", max_turns=4)
    except AgentError as e:
        print(f"✗ Ajan döngüsü başarısız: {e}\n  İpucu: CM_AUTO_CACHE=0 ile tekrar deneyin; sorun sürerse isteği llm.py'de yazdırın.")
        return 1
    ok = run.final_input == {"answer": 42} and calls
    print(f"{'✓' if ok else '✗'} Ajan döngüsü ({time.time() - t:.1f} sn, {run.requests} istek): araç çağrıları {calls}, sonuç {run.final_input}")
    print(f"  Token: {run.usage}")
    print("Sonraki adım: CM_LLM_MODE=live ile API'yi başlatın ya da demo akışını CM_LLM_MODE=record ile kaydedin.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
