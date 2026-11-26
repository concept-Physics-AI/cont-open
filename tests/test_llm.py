from cont.llm import Message, get_provider, list_providers, register_type


def test_echo_provider_from_config(monkeypatch):
    monkeypatch.setenv("CONT_LLM_PROVIDER", "echo")
    p = get_provider()
    r = p.complete([Message("user", "hello")])
    assert r.text == "hello" and r.provider == "echo"


def test_config_lists_known_providers():
    names = set(list_providers())
    assert {"echo", "ollama_local"} <= names


def test_register_new_type(monkeypatch, tmp_path):
    class Fixed:
        def __init__(self, name, model, **_):
            self.name, self.model = name, model

        def complete(self, messages, **opts):
            from cont.llm import LLMResponse
            return LLMResponse("fixed", self.name, self.model)

    register_type("fixed_test", Fixed)
    (tmp_path / "llm").mkdir()
    (tmp_path / "llm" / "providers.yaml").write_text(
        "default: f\nproviders:\n  f: {type: fixed_test, model: m}\n", encoding="utf-8")
    assert get_provider(config_dir=tmp_path).complete([]).text == "fixed"


def _fake_http(monkeypatch, message):
    import io
    import json as _json
    import urllib.request

    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: R(_json.dumps({"choices": [{"message": message}]}).encode()))


def test_openai_compatible_uses_commentary_tool_call_when_content_is_empty(monkeypatch):
    from cont.llm.providers import OpenAICompatible
    from cont.llm import Message
    p = OpenAICompatible("t", "m", "http://x/v1")
    plan = '{"steps":[]}'
    _fake_http(monkeypatch, {"content": "", "tool_calls": [{"function": {"name": "commentary", "arguments": plan}}]})
    assert p.complete([Message("user", "hi")]).text == plan
    _fake_http(monkeypatch, {"content": "본문", "tool_calls": [{"function": {"name": "commentary", "arguments": plan}}]})
    assert p.complete([Message("user", "hi")]).text == "본문"                      # 본문이 있으면 그대로
    _fake_http(monkeypatch, {"content": "", "tool_calls": [{"function": {"name": "other", "arguments": plan}}]})
    assert p.complete([Message("user", "hi")]).text == ""                         # 다른 이름의 도구 호출은 쓰지 않는다
    _fake_http(monkeypatch, {"content": None})
    assert p.complete([Message("user", "hi")]).text == ""
