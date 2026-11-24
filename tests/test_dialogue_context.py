"""문맥 전달과 실제 설계 반영을 검사한다. 실제 공급자의 언어 이해 성능 시험은 아니다."""
import json
import threading
import urllib.request

import pytest

from cont.dialogue.context import ContextLimits, build_messages
from cont.dialogue.fastening_chat import Session
from cont.dialogue.serve_fastening import example, make_server
from cont.llm import LLMResponse
from cont.packs.fastening.pack import answer


class RecordingProvider:
    name = model = "test"

    def __init__(self, response="{}"):
        self.response = response
        self.calls = []

    def complete(self, messages, **opts):
        self.calls.append(messages)
        return LLMResponse(self.response, self.name, self.model)


def current(messages):
    return json.loads(messages[1].content.split("\n", 1)[1])


def test_relative_followup_receives_applied_state_and_recomputes_physics():
    class RelativeProvider(RecordingProvider):
        def complete(self, messages, **opts):
            self.calls.append(messages)
            if messages[-1].content == "그 토크에서 10만 더":
                assert messages[-3].content == "토크 60으로"
                applied = json.loads(messages[-2].content)
                assert applied["applied_changes"] == {"tightening_torque": 60.0}
                value = current(messages)["load"]["tightening_torque"] + 10
            else:
                value = 60
            return LLMResponse(json.dumps({"tightening_torque": value}), self.name, self.model)

    p = RelativeProvider()
    s = Session(*example(), provider=p)
    s.say("토크 60으로")
    t = s.say("그 토크에서 10만 더")
    assert s.load.tightening_torque == 70
    assert t.after.value("preload") == answer(s.joint, s.load).value("preload")


def test_ten_turn_window_keeps_latest_state_after_old_request_drops_out():
    p = RecordingProvider('{"size": "M12"}')
    s = Session(*example(), provider=p, context_limits=ContextLimits(10, 16000))
    s.say("처음 규격을 M12로")
    p.response = "{}"
    for i in range(10):
        s.say(f"이력 {i}")
    s.say("지금 규격은?")
    messages = p.calls[-1]
    assert len(messages) == 23  # 지시문, 현재 상태, 왕복 10개, 현재 질문
    assert messages[2].content == "이력 0"
    assert current(messages)["joint"]["size"] == "M12"
    assert messages[-1].content == "지금 규격은?"


def test_failed_request_is_not_promoted_to_applied_state():
    p = RecordingProvider('{"size": "M7"}')
    s = Session(*example(), provider=p)
    assert s.say("M7로").kind == "failed"
    p.response = "{}"
    s.say("앞의 요청을 확인해줘")
    m = p.calls[-1]
    assert current(m)["joint"]["size"] == "M10"
    assert json.loads(m[-2].content) == {"outcome": "failed", "applied_changes": {}}


def test_sessions_using_one_provider_do_not_share_history_or_joint():
    p = RecordingProvider('{"size": "M12"}')
    first = Session(*example(), provider=p)
    second = Session(*example(), provider=p)
    first.say("첫 설계만 M12로")
    p.response = "{}"
    second.say("두 번째 설계 확인")
    assert len(p.calls[-1]) == 3
    assert current(p.calls[-1])["joint"]["size"] == "M10"
    assert first.joint.size == "M12"


def test_only_current_recommendations_are_carried():
    p = RecordingProvider('{"targets": {"safety_yield": 1.5}}')
    s = Session(*example(), provider=p)
    s.say("항복 안전율 1.5 이상이 되게")
    assert s.offers
    expected = dict(s.offers[0].changes)
    p.response = '{"choose": 1}'
    selected = s.say("첫 번째 것으로")
    assert current(p.calls[-1])["offers"][0] == {"choose": 1, "changes": expected}
    assert selected.changes == expected
    p.response = '{"tightening_torque": 60}'
    s.say("토크 60으로")
    p.response = "{}"
    s.say("현재 후보 확인")
    assert current(p.calls[-1])["offers"] == []


def test_budget_keeps_complete_pairs_and_preserves_current_question():
    limits = ContextLimits(10, 11)
    history = [("older", "long reply"), ("u", "a")]
    m = build_messages("s", "c", history, "question", limits)
    assert [x.content for x in m] == ["s", "c", "question"]
    m = build_messages("s", "c", history, "question", ContextLimits(10, 12))
    assert [x.content for x in m] == ["s", "c", "u", "a", "question"]
    assert [x.role for x in m] == ["system", "system", "user", "assistant", "user"]


def test_zero_history_and_oversized_latest_turn_do_not_reintroduce_old_turns():
    history = [("old", "reply"), ("long" * 10, "a")]
    for limits in (ContextLimits(0, 100), ContextLimits(10, 20)):
        m = build_messages("s", "c", history, "now", limits)
        assert [x.content for x in m] == ["s", "c", "now"]


def test_oversized_current_state_uses_existing_rule_fallback_without_provider_call():
    p = RecordingProvider('{"size": "M16"}')
    s = Session(*example(), provider=p, context_limits=ContextLimits(10, 1))
    t = s.say("토크 70으로")
    assert p.calls == [] and t.source == "rule"
    assert t.changes == {"tightening_torque": 70.0}
    assert "ValueError" in t.note and s.joint.size == "M10"


def test_provider_failure_and_invalid_output_keep_rule_fallback():
    p = RecordingProvider('{"preload": 999999}')
    s = Session(*example(), provider=p)
    assert s.say("토크 60으로").source == "rule"
    p.response = "{}"
    s.say("현재 조건 확인")
    assert current(p.calls[-1])["load"]["tightening_torque"] == 60
    assert "999999" not in " ".join(m.content for m in p.calls[-1])


@pytest.mark.parametrize("turns,chars", [(-1, 100), (True, 100), (1.5, 100), (1, 0), (1, True)])
def test_invalid_context_limits_rejected(turns, chars):
    with pytest.raises(ValueError):
        ContextLimits(turns, chars)


def test_http_reset_clears_history_and_preserves_custom_context_policy():
    p = RecordingProvider('{"size": "M12"}')
    s = Session(*example(), provider=p, context_limits=ContextLimits(0, 16000))
    server = make_server(s, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def post(path, body):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.load(response)

    try:
        post("/say", {"text": "M12로"})
        post("/reset", {})
        p.response = "{}"
        post("/say", {"text": "재시작 첫 질문"})
        assert current(p.calls[-1])["joint"]["size"] == "M10"
        post("/say", {"text": "재시작 둘째 질문"})
        assert len(p.calls[-1]) == 3
    finally:
        server.shutdown()
        server.server_close()
