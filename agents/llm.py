"""Bedrock üzerinde Claude ile ajan döngüsü + kayıt-oynat + mock.

Modlar (CM_LLM_MODE):
  mock    LLM çağrısı yok; ajanlar deterministik yedek yollarını kullanır (varsayılan; AWS gerekmez).
  live    Bedrock'a gider.
  record  Bedrock'a gider ve her yanıtı cassettes/ altına kaydeder.
  replay  Ağa çıkmaz; kayıttan oynatır. Kayıt yoksa ajan mock yedeğine düşer.

İstemci (CM_BEDROCK_CLIENT):
  mantle  Bedrock Mantle uç noktası (varsayılan); model kimliği öneksiz, ör. anthropic.claude-opus-5-5.
  invoke  Bedrock Runtime InvokeModel (IAM: bedrock:InvokeModel*); model kimliği çıkarım profili biçiminde olmalı,
          ör. CM_MODEL_ID=global.anthropic.claude-sonnet-4-6. AgentCore çalışma ortamında izinli yol budur.

Bu modeldeki kurallar (bkz. .kiro/steering/tech.md):
- tool_choice any/tool YOK (400). auto + strict: true + istemde açık talimat.
- thinking disabled / budget_tokens YOK (400). Derinlik output_config.effort ile.
- temperature/top_p/top_k YOK. Assistant prefill YOK.
- stop_reason içerik okunmadan önce kontrol edilir.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .storage import usage_sinks

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "anthropic.claude-opus-5-5"
MODES = ("mock", "live", "record", "replay")
BEDROCK_CLIENTS = ("mantle", "invoke")
PROFILE_PREFIXES = ("global.", "us.", "eu.", "apac.", "au.", "jp.")
USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
log = logging.getLogger(__name__)


class AgentError(RuntimeError):
    pass


class CassetteMiss(AgentError):
    pass


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    fn: Callable[[dict], Any] | None = None       # None: bitiş aracı (girdisi sonuç olarak alınır)
    summarize: Callable[[dict, Any], str] | None = None

    def spec(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema, "strict": True}


@dataclass
class AgentRun:
    final_text: str | None = None
    final_input: dict | None = None
    steps: list[dict] = field(default_factory=list)
    turns: int = 0
    usage: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
                                                 "cache_creation_input_tokens": 0})
    requests: int = 0


def obj(properties: dict, required: list[str] | None = None) -> dict:
    """strict araç şeması: tüm alanlar zorunlu, ek alan yok. İsteğe bağlı alanlar null tipli olmalı."""
    return {"type": "object", "properties": properties, "required": required if required is not None else list(properties),
            "additionalProperties": False}


def nullable(schema: dict) -> dict:
    """Boş bırakılabilir alan: strict şemada desteklenen anyOf biçimi."""
    return {"anyOf": [schema, {"type": "null"}]}


def _short(x: Any, n: int = 160) -> str:
    s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)
    return s if len(s) <= n else s[: n - 1] + "…"


class LLM:
    def __init__(self, mode: str | None = None, model: str | None = None, region: str | None = None,
                 cassette_dir: Path | None = None):
        self.mode = (mode or os.environ.get("CM_LLM_MODE", "mock")).lower()
        if self.mode not in MODES:
            raise ValueError(f"CM_LLM_MODE geçersiz: {self.mode} (izinli: {MODES})")
        self.model = model or os.environ.get("CM_MODEL_ID", DEFAULT_MODEL)
        self.bedrock_client = os.environ.get("CM_BEDROCK_CLIENT", "mantle").lower()
        if self.bedrock_client not in BEDROCK_CLIENTS:
            raise ValueError(f"CM_BEDROCK_CLIENT geçersiz: {self.bedrock_client} (izinli: {BEDROCK_CLIENTS})")
        self.region = region or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
        self.cassette_dir = Path(cassette_dir or os.environ.get("CM_CASSETTE_DIR", ROOT / "cassettes"))
        self.usage_log = Path(os.environ.get("CM_USAGE_LOG", ROOT / "data" / "usage.jsonl"))
        self.usage_sinks = usage_sinks(self.usage_log)      # dosya; CM_STORAGE=dynamodb ise ayrıca tablo
        self.auto_cache = os.environ.get("CM_AUTO_CACHE", "1") == "1"
        self._client = None

    @property
    def uses_llm(self) -> bool:
        return self.mode != "mock"

    def cassette_count(self) -> int:
        return len(list(self.cassette_dir.glob("*.json"))) if self.cassette_dir.exists() else 0

    # ------------------------------------------------------------------ istemci
    def client(self):
        if self._client is None:
            import anthropic   # yalnız gerektiğinde içe aktar

            kw: dict[str, Any] = {"aws_region": self.region, "max_retries": 2, "timeout": 120.0}
            if os.environ.get("CM_BEDROCK_API_KEY"):
                kw["api_key"] = os.environ["CM_BEDROCK_API_KEY"]
            if os.environ.get("AWS_PROFILE"):
                kw["aws_profile"] = os.environ["AWS_PROFILE"]
            if self.bedrock_client == "invoke":
                if not self.model.startswith(PROFILE_PREFIXES):
                    raise AgentError(f"CM_BEDROCK_CLIENT=invoke için model kimliği çıkarım profili biçiminde olmalı "
                                     f"(ör. global.{self.model}); verilen: {self.model}")
                self._client = anthropic.AnthropicBedrock(**kw)
            else:
                self._client = anthropic.AnthropicBedrockMantle(**kw)
        return self._client

    # ------------------------------------------------------------------ tek çağrı (kayıt-oynat dahil)
    def _key(self, req: dict) -> str:
        return hashlib.sha256(json.dumps(req, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:32]

    def _call(self, agent: str, req: dict) -> dict:
        key = self._key(req)
        path = self.cassette_dir / f"{agent}-{key}.json"
        if self.mode == "replay":
            if not path.exists():
                raise CassetteMiss(f"Kayıt yok: {path.name}")
            return json.loads(path.read_text(encoding="utf-8"))["response"]
        import anthropic

        try:
            resp = self.client().messages.create(**req)
        except anthropic.RateLimitError as e:
            raise AgentError(f"Bedrock hız sınırı: {e}") from e
        except anthropic.APIStatusError as e:
            raise AgentError(f"Bedrock API hatası ({e.status_code}): {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise AgentError(f"Bedrock bağlantı hatası: {e}") from e
        data = resp.model_dump(mode="json", exclude_none=True)
        if self.mode == "record":
            self.cassette_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"agent": agent, "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                        "request": req, "response": data}, ensure_ascii=False, indent=1), encoding="utf-8")
        return data

    def _log_usage(self, agent: str, u: dict, seconds: float) -> None:
        """Canlı/kayıt modunda her isteğin token kullanımını yazar (data/usage.jsonl; dynamodb modunda tabloya da).

        Günlük hatası model çağrısını asla bozmaz: yalnız uyarı yazılır.
        """
        if self.mode not in ("live", "record") or not u:
            return
        row = {"agent": agent, "model": self.model, "t": time.strftime("%Y-%m-%dT%H:%M:%S"), "seconds": round(seconds, 2),
               **{k: int(u.get(k) or 0) for k in USAGE_FIELDS}}
        for sink in self.usage_sinks:
            try:
                sink.record(row)
            except Exception as e:  # noqa: BLE001 - maliyet günlüğü ikincil; ajan döngüsü sürmeli
                log.warning("Token kullanım kaydı yazılamadı (%s): %s", type(sink).__name__, e)

    # ------------------------------------------------------------------ ajan döngüsü
    def run_agent(self, *, agent: str, system: str, user: str | list, tools: list[Tool], finish_tool: str | None = None,
                  history: list[dict] | None = None, effort: str = "medium", max_turns: int = 10,
                  output_schema: dict | None = None, max_tokens: int = 16000,
                  on_text: Callable[[str], None] | None = None) -> AgentRun:
        """Araç kullanan ajan döngüsü. on_text: modelin her metin bloğu için çağrılır (ajan izi: 'karar' olayı)."""
        if not self.uses_llm:
            raise AgentError("mock modunda LLM çağrılmaz")
        by_name = {t.name: t for t in tools}
        messages: list[dict] = list(history or []) + [{"role": "user", "content": user}]
        out = AgentRun()
        nudged = False
        for turn in range(max_turns):
            out.turns = turn + 1
            req: dict[str, Any] = {
                "model": self.model, "max_tokens": max_tokens,
                "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                "messages": messages,
                "output_config": {"effort": effort},
            }
            if self.auto_cache:
                req["cache_control"] = {"type": "ephemeral"}     # otomatik önbellek: önceki turlar önbellekten okunur
            if tools:
                req["tools"] = [t.spec() for t in tools]
            if output_schema:
                req["output_config"]["format"] = {"type": "json_schema", "schema": output_schema}
            t0 = time.time()
            resp = self._call(agent, req)
            out.requests += 1
            u = resp.get("usage") or {}
            for k in out.usage:
                out.usage[k] += int(u.get(k) or 0)
            self._log_usage(agent, u, time.time() - t0)
            stop = resp.get("stop_reason")
            content = resp.get("content") or []
            if on_text and stop in ("tool_use", "end_turn", "stop_sequence") and not output_schema:
                for b in content:
                    if b.get("type") == "text" and (b.get("text") or "").strip():
                        on_text(b["text"].strip())
            if stop == "refusal":
                raise AgentError("Model isteği reddetti (refusal)")
            if stop == "max_tokens":
                raise AgentError("Yanıt max_tokens sınırına takıldı")
            if stop == "pause_turn":
                messages.append({"role": "assistant", "content": content})
                continue
            if stop == "tool_use":
                messages.append({"role": "assistant", "content": content})
                results = []
                finished = False
                for b in content:
                    if b.get("type") != "tool_use":
                        continue
                    name, inp = b["name"], b.get("input") or {}
                    if isinstance(inp, str):
                        inp = json.loads(inp)
                    tool = by_name.get(name)
                    if tool is None:
                        results.append({"type": "tool_result", "tool_use_id": b["id"], "content": f"Bilinmeyen araç: {name}", "is_error": True})
                        continue
                    if tool.fn is None or name == finish_tool:
                        out.final_input = inp
                        out.steps.append({"tool": name, "input": inp, "summary": "sonuç kaydedildi"})
                        results.append({"type": "tool_result", "tool_use_id": b["id"], "content": "Kaydedildi."})
                        finished = True
                        continue
                    try:
                        res = tool.fn(inp)
                        txt = res if isinstance(res, str) else json.dumps(res, ensure_ascii=False)
                        out.steps.append({"tool": name, "input": inp,
                                          "summary": tool.summarize(inp, res) if tool.summarize else _short(txt)})
                        results.append({"type": "tool_result", "tool_use_id": b["id"], "content": txt})
                    except Exception as e:  # araç hatası modele geri verilir; model düzeltebilir
                        out.steps.append({"tool": name, "input": inp, "summary": f"hata: {e}"})
                        results.append({"type": "tool_result", "tool_use_id": b["id"], "content": f"Hata: {e}", "is_error": True})
                if finished:
                    texts = [b.get("text", "") for b in content if b.get("type") == "text"]
                    out.final_text = "\n".join(t for t in texts if t) or out.final_text
                    return out
                messages.append({"role": "user", "content": results})
                continue
            # end_turn / stop_sequence
            texts = [b.get("text", "") for b in content if b.get("type") == "text"]
            out.final_text = "\n".join(t for t in texts if t)
            if output_schema and out.final_text:
                out.final_input = json.loads(out.final_text)
                return out
            if finish_tool and out.final_input is None and not nudged:
                nudged = True
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": f"Lütfen sonucu `{finish_tool}` aracıyla kaydet."})
                continue
            return out
        raise AgentError(f"{agent}: {max_turns} turda bitmedi")
