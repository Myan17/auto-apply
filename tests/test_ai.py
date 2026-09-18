"""Resume tailoring and cover-letter generation.

The OpenAI client is replaced with a fake, so these tests make no network call
and need no API key. They pin input truncation (token budget), the
rate-limit fallback between models, and that a final rate limit surfaces
rather than being swallowed.
"""
from types import SimpleNamespace

import httpx
import openai
import pytest

from src.ai import cover_letter, tailor


def _rate_limit():
    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return openai.RateLimitError("rate limited", response=httpx.Response(429, request=req), body=None)


class _FakeClient:
    def __init__(self, behaviours):
        # behaviours: model name -> "ok" | "rate_limit"
        self.behaviours = behaviours
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, model, max_tokens, messages):
        self.calls.append({"model": model, "max_tokens": max_tokens, "messages": messages})
        if self.behaviours.get(model) == "rate_limit":
            raise _rate_limit()
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=f"  output from {model}  "))])


@pytest.fixture
def cfg():
    return SimpleNamespace(
        env=SimpleNamespace(openai_api_key="sk-test-not-real"),
        ai=SimpleNamespace(
            tailor_model="primary-model",
            model="fallback-model",
            max_tokens_resume=1500,
            max_tokens_cover_letter=800,
        ),
    )


def _install(monkeypatch, module, client):
    monkeypatch.setattr(module, "OpenAI", lambda api_key: client)


@pytest.mark.parametrize("module,call", [
    (tailor, lambda c: tailor.tailor_resume(c, "RESUME", "JD", "Acme", "SWE")),
    (cover_letter, lambda c: cover_letter.generate_cover_letter(c, "RESUME", "JD", "Acme", "SWE", "Test User")),
])
class TestGeneration:
    def test_returns_the_primary_models_output_stripped(self, monkeypatch, cfg, module, call):
        client = _FakeClient({"primary-model": "ok"})
        _install(monkeypatch, module, client)
        assert call(cfg) == "output from primary-model"
        assert [c["model"] for c in client.calls] == ["primary-model"]

    def test_falls_back_to_the_second_model_on_a_rate_limit(self, monkeypatch, cfg, module, call):
        client = _FakeClient({"primary-model": "rate_limit", "fallback-model": "ok"})
        _install(monkeypatch, module, client)
        assert call(cfg) == "output from fallback-model"
        assert [c["model"] for c in client.calls] == ["primary-model", "fallback-model"]

    def test_a_rate_limit_on_both_models_is_raised_not_swallowed(self, monkeypatch, cfg, module, call):
        # Silently returning None here would put an empty resume into an
        # application. The caller has to see the failure.
        client = _FakeClient({"primary-model": "rate_limit", "fallback-model": "rate_limit"})
        _install(monkeypatch, module, client)
        with pytest.raises(openai.RateLimitError):
            call(cfg)


@pytest.mark.parametrize("module,call,max_resume,max_jd", [
    (tailor, lambda c, r, j: tailor.tailor_resume(c, r, j, "Acme", "SWE"), 8_000, 12_000),
    (cover_letter, lambda c, r, j: cover_letter.generate_cover_letter(c, r, j, "Acme", "SWE", "U"), 8_000, 12_000),
])
def test_inputs_are_truncated_to_the_token_budget(monkeypatch, cfg, module, call, max_resume, max_jd):
    client = _FakeClient({"primary-model": "ok"})
    _install(monkeypatch, module, client)

    # Marker characters that never occur in the prompt templates themselves.
    resume_mark, jd_mark = "\u00a7", "\u00b6"
    call(cfg, resume_mark * (max_resume + 5_000), jd_mark * (max_jd + 5_000))

    user = client.calls[0]["messages"][1]["content"]
    assert user.count(resume_mark) == max_resume
    assert user.count(jd_mark) == max_jd


def test_the_tailor_prompt_forbids_fabrication():
    # The system prompt is the only guard against the model inventing
    # experience on a real application. Keep the instruction present.
    from src.ai.prompts import RESUME_TAILOR_SYSTEM

    assert "Do NOT invent" in RESUME_TAILOR_SYSTEM
