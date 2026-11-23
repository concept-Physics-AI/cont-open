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
