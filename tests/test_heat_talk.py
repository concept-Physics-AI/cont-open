"""Studio 열 대화: 입력 조건만 읽고(규칙 또는 LLM), 숫자는 열 팩이 낸다. 실제 LLM은 부르지 않는다 (가짜 공급자)."""
import json

import pytest

from cont import packs
from cont.dialogue import heat_talk
from cont.dialogue.area import detect
from cont.dialogue.fastening_chat import Session
from cont.dialogue.serve_fastening import example, message
from cont.llm import LLMResponse


class Fake:
    name, model = "fake", "fake"

    def __init__(self, text=None, error=None):
        self.text, self.error, self.seen = text, error, None

    def complete(self, messages, **opts):
        self.seen = messages
        if self.error:
            raise self.error
        return LLMResponse(self.text, self.name, self.model)


def test_areas_know_heat_and_do_not_steal_fastening():
    a = detect("열확산계수 2e-4인 판을 30초 식히면 온도 변화가 어때?")
    assert a.key == "heat" and a.handler == "heat" and a.chat is False
    assert detect("2차원 판의 열전도를 계산해 줘").key == "heat"
    assert detect("M10 볼트 토크를 80으로 바꿔 줘").key == "fastening" and detect("M10 볼트 토크").handler is None
    assert detect("선삭에서 절삭력이 얼마나 나와?").key == "machining"


def test_rules_read_only_input_conditions():
    assert heat_talk.parse("열확산계수 2e-4로 30초 식혀 줘") == {"diffusivity": 2e-4, "duration": 30.0}
    assert heat_talk.parse("길이 5 cm 판, 경계 온도 25℃, 처음 온도 80℃로 균일하게 60초") == {
        "case": "step_1d", "length": pytest.approx(0.05), "t_wall": pytest.approx(298.15), "t_initial": pytest.approx(353.15),
        "duration": 60.0}
    assert heat_talk.parse("2차원 판") == {"case": "sine_2d"}
    assert heat_talk.parse("오늘 날씨 어때") == {}


def test_numbers_in_the_reply_come_from_the_heat_pack():
    r = heat_talk.reply("열확산계수 2e-4인 판을 30초 식히면 온도 변화가 어때?")
    a = packs.get("heat").solve({"diffusivity": 2e-4, "duration": 30.0})
    assert f"{a.value('peak_temperature'):.2f} K" in r["talk"]["text"] and f"{a.value('deviation_rms'):.2g}" in r["talk"]["text"]
    assert "합성 기준 문제" in r["talk"]["text"] and "판정하지 않습니다" in r["talk"]["text"]
    assert "규칙으로 읽음" in r["detail"] and a.truth_line().split("·")[0] in r["detail"] and r["state"] is None


def test_no_conditions_says_defaults_were_used():
    r = heat_talk.reply("열전도를 계산해 줘")
    assert "기본 기준 문제 값" in r["talk"]["text"]


def test_llm_proposes_inputs_and_invalid_or_result_keys_are_dropped():
    llm = Fake(json.dumps({"diffusivity": 2e-4, "duration": 10, "length": -1, "peak_temperature": 999.0, "case": "magic"}))
    p = heat_talk.propose("조건 말씀드립니다", llm)
    assert p.source == "llm" and p.inputs == {"diffusivity": 2e-4, "duration": 10.0}
    assert len(p.dropped) == 3 and any("peak_temperature" in d for d in p.dropped)    # 결과 숫자를 만들려는 제안은 버린다
    r = heat_talk.reply("조건 말씀드립니다", llm)
    assert "999" not in r["talk"]["text"] and "쓰지 않은 제안" in r["talk"]["text"]
    assert "LLM이 제안한 가상 입력" in r["detail"]
    assert "숫자 결과를 만들지" not in llm.seen[0].content and "계산 결과를 만들지 않는다" in llm.seen[0].content


def test_llm_failure_falls_back_to_rules_and_says_so():
    for bad in (Fake(error=TimeoutError("x")), Fake("not json"), Fake("[1, 2]")):
        p = heat_talk.propose("30초 식혀 줘", bad)
        assert p.source == "rule" and p.inputs == {"duration": 30.0} and "규칙으로 읽음" in p.note


def test_studio_message_routes_heat_without_touching_the_joint():
    s = Session(*example())
    before = (s.joint, s.load)
    m = message(s, "열확산계수 2e-4인 판을 30초 식히면 온도 변화가 어때?")
    assert m["state"] is None and "비정상 열전도" in m["talk"]["text"] and m["suggest"]
    assert (s.joint, s.load) == before
    assert message(s, "토크를 60으로 줄여 줘")["state"] is not None                # 체결 대화는 그대로
