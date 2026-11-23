import json
import threading
import urllib.request

import pytest

from cont.dialogue import ask, facts, focus, rule_answer
from cont.dialogue.serve import example_answers, make_server
from cont.llm import LLMResponse
from cont.packs.diagnosis.demo import synthetic_equipment
from cont.view import render_equipment


@pytest.fixture(scope="module")
def eq():
    return synthetic_equipment()


class Fake:
    """실제 API를 부르지 않는 가짜 공급자."""
    name, model = "fake", "fake"

    def __init__(self, text=None, error=None):
        self.text, self.error, self.seen = text, error, None

    def complete(self, messages, **opts):
        self.seen = messages
        if self.error:
            raise self.error
        return LLMResponse(self.text, self.name, self.model)


def names(question, eq):
    return [s.name for s, _ in focus(question, eq)]


def test_focus_follows_what_the_question_points_at(eq):
    assert names("이 설비 지금 어떤가요?", eq) == ["주 구동부", "유압 공급 라인", "가열 구역", "동작 사이클"]
    assert names("유압 쪽은 언제부터 이상했나요?", eq) == ["유압 공급 라인"]
    assert names("가열 구역 온도는 괜찮은가요?", eq) == ["가열 구역"]          # 구동부의 '구동부 온도'를 끌고 오지 않는다
    assert names("전류랑 압력은 어때요?", eq) == ["주 구동부", "유압 공급 라인"]
    (s, cols), = focus("구동부 진동이 왜 커졌나요?", eq)
    assert s.name == "주 구동부" and cols == {"vibration"}


def test_rule_answer_needs_no_llm_and_does_not_claim_a_cause(eq):
    r = ask("구동부 진동이 왜 커졌나요?", eq)
    assert r.source == "rule" and r.systems == ("주 구동부",)
    assert "진동 증가" in r.text and "1709~1999" in r.text and "전류" not in r.text
    assert "원인은 이 변화를 단서로" in r.text and "신뢰도는 낮음" in r.text
    assert rule_answer("구동부 진동이 왜 커졌나요?", eq) == r.text            # 같은 질문에는 같은 답
    assert "첫 이상 시각은 1205입니다" in ask("유압 쪽은 언제부터 이상했나요?", eq).text
    assert ask("가열 구역은 괜찮은가요?", eq).text.startswith("가열 구역은 같은 운전조건의 정상 범위 안에서")
    t = ask("구동부 온도는 정상인가요?", eq).text
    assert "구동부 온도는 같은 운전조건의 정상 범위 안" in t and "다만 이 계통의 다른 신호에는 이상 징후" in t


def test_llm_only_rewords_the_facts_it_is_given(eq):
    fake = Fake("유압 공급 라인에서 유량이 평균 2.5L/min 줄었습니다. 원인은 점검으로 확인해 주세요.")
    r = ask("유압 쪽 유량은 어떤가요?", eq, fake)
    assert r.source == "llm" and r.text.startswith("유압 공급 라인에서")
    system, user = fake.seen
    assert system.role == "system" and "숫자를 새로 만들거나 바꾸지 않는다" in system.content
    assert "진단 사실:" in user.content and "유량 감소" in user.content and "주 구동부" not in user.content
    assert user.content.endswith("질문: 유압 쪽 유량은 어떤가요?")


def test_falls_back_to_the_rule_answer_when_the_llm_is_wrong_or_away(eq):
    q = "유압 쪽 유량은 어떤가요?"
    made_up = ask(q, eq, Fake("유량이 37% 줄었고 필터 수명은 12일 남았습니다."))
    assert made_up.source == "rule" and "진단 사실에 없는 숫자" in made_up.note and "37" in made_up.note
    assert made_up.text == rule_answer(q, eq)
    assert ask(q, eq, Fake(error=ConnectionError("down"))).note.startswith("LLM을 부르지 못해")
    assert ask(q, eq, Fake("  ")).note == "LLM 응답이 비어 규칙 답을 씀"
    text, used = facts(q, eq)
    assert used == ("유압 공급 라인",) and "한계: 진단은" in text


def test_screen_carries_example_answers_and_the_server_answers_typed_questions(eq):
    qa = example_answers(eq)
    page = render_equipment(eq, qa=qa)
    assert "묻고 답하기" in page and page.count("data-i=") == len(qa) and "<form>" not in page and "http" not in page
    assert "묻고 답하기" not in render_equipment(eq)
    srv = make_server(eq, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        home = urllib.request.urlopen(base + "/", timeout=5).read().decode("utf-8")
        assert "<form>" in home and '"ask_url": "/ask"' in home
        req = urllib.request.Request(base + "/ask", data=json.dumps({"question": "동작 사이클은 어떤가요?"}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        d = json.loads(urllib.request.urlopen(req, timeout=5).read())
        assert "사이클 지연" in d["text"] and d["systems"] == ["동작 사이클"] and "규칙으로 만듦" in d["source"]
        bad = urllib.request.Request(base + "/ask", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(bad, timeout=5)
        assert e.value.code == 400
    finally:
        srv.shutdown(); srv.server_close()


def test_guards_added_after_running_a_real_model(eq):
    """2026-11-23 대표 PC의 실제 모델(gpt-oss:20b)이 낸 답에서 본 문제를 막는다."""
    q = "유압 쪽은 언제부터 이상했나요?"
    unit = ask(q, eq, Fake("유압 공급 라인에서 가장 먼저 이상이 나타난 시점은 1205시입니다."))
    assert unit.source == "rule" and unit.note == "LLM 응답이 시각 값에 없는 단위를 붙여 규칙 답을 씀"
    sure = ask("구동부 진동이 왜 커졌나요?", eq, Fake("진동이 커졌습니다. 베어링이 손상됐을 가능성이 높습니다."))
    assert sure.source == "rule" and "가능성이 높" in sure.note
    fine = ask(q, eq, Fake("**결론**: 유압 공급 라인은 1205부터 차압이 정상 범위를 벗어났습니다."))
    assert fine.source == "llm" and "**" not in fine.text and fine.text.startswith("결론: 유압 공급 라인은 1205부터")
    from cont.dialogue.diagnosis_qa import SYSTEM_PROMPT
    assert all(w in SYSTEM_PROMPT for w in ("단위를 붙이지 않는다", "원인의 예를 스스로 들지 않는다", "다른 구간의 숫자와 섞지 않는다"))
    from cont.dialogue.serve import answer_text
    shown = answer_text(fine)
    assert "근거로 쓴 진단 결과" in shown and "차압(dp) 값이 1205~1217 구간" in shown and answer_text(unit) == unit.text
