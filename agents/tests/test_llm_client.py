"""Bedrock istemci seçimi: Mantle (varsayılan) ↔ InvokeModel (çıkarım profili kimliğiyle; AgentCore çalışma ortamı)."""
import pytest

from agents.llm import LLM, AgentError


def test_default_client_is_mantle(monkeypatch):
    monkeypatch.delenv("CM_BEDROCK_CLIENT", raising=False)
    import anthropic

    llm = LLM(mode="live", region="us-east-1")
    assert llm.bedrock_client == "mantle" and isinstance(llm.client(), anthropic.AnthropicBedrockMantle)


def test_invoke_client_needs_inference_profile_id(monkeypatch):
    monkeypatch.setenv("CM_BEDROCK_CLIENT", "invoke")
    import anthropic

    with pytest.raises(AgentError, match="çıkarım profili"):
        LLM(mode="live", model="anthropic.claude-sonnet-4-6", region="us-east-1").client()
    llm = LLM(mode="live", model="global.anthropic.claude-sonnet-4-6", region="us-east-1")
    assert isinstance(llm.client(), anthropic.AnthropicBedrock)


def test_unknown_client_rejected(monkeypatch):
    monkeypatch.setenv("CM_BEDROCK_CLIENT", "converse")
    with pytest.raises(ValueError):
        LLM(mode="mock")
