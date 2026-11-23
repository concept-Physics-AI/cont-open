from dataclasses import replace

import pytest

from cont.dialogue.fastening_chat import Session, parse_choice, parse_targets
from cont.dialogue.serve_fastening import example
from cont.llm import LLMResponse
from cont.packs.fastening import vdi2230
from cont.packs.fastening.recommend import recommend, settings


class Fake:
    name, model = "fake", "fake"

    def __init__(self, text):
        self.text = text

    def complete(self, messages, **opts):
        return LLMResponse(self.text, self.name, self.model)


def test_every_candidate_really_meets_the_targets_and_sits_inside_its_torque_range():
    j, l = example()
    targets = {"safety_yield": 1.5, "safety_slip": 3.0}
    rec = recommend(j, l, targets)
    assert rec.total == 10 and not rec.current_ok and len(rec.candidates) == settings()["show"] == 3
    for c in rec.candidates:
        r = vdi2230.calculate(c.joint, c.load)
        assert r.safety_yield >= 1.5 and r.safety_slip >= 3.0
        assert c.torque_min <= c.torque <= c.torque_max and c.torque % 0.5 == pytest.approx(0, abs=1e-9)
        # 범위의 양 끝 바로 밖에서는 목표 가운데 하나가 깨진다
        low = vdi2230.calculate(c.joint, replace(c.load, tightening_torque=c.torque_min * 0.99))
        high = vdi2230.calculate(c.joint, replace(c.load, tightening_torque=c.torque_max * 1.01))
        assert low.safety_slip < 3.0 and high.safety_yield < 1.5
        assert c.values == pytest.approx({"safety_yield": r.safety_yield, "safety_slip": r.safety_slip})


def test_order_is_least_change_first():
    j, l = example()
    rec = recommend(j, l, {"safety_yield": 1.5})
    first, second, third = rec.candidates
    assert first.changes == {"tightening_torque": 47.5} and first.torque_min == 0.0          # 토크만 낮추면 된다
    assert second.changes == {"property_class": "12.9"} and third.changes == {"property_class": "8.8", "tightening_torque": 32.0}
    assert rec.answer.value("recommended_torque") == 47.5 and rec.answer.get("recommended_torque").expected_range == (0.0, first.torque_max)
    assert "비용·무게로 고른 순서가 아님" in rec.answer.basis[2] and rec.answer.confidence.level == "medium"
    met = recommend(j, l, {"safety_yield": 1.2})
    assert met.current_ok and met.candidates[0].changes == {} and met.answer.value("current_meets_targets") == 1.0
    sizes = [c.size for c in recommend(j, l, {"safety_yield": 1.5, "safety_slip": 3.0}).candidates]
    assert sizes == ["M16", "M20", "M24"]                                                      # 가까운 규격부터


def test_says_so_when_nothing_works_or_a_target_cannot_be_computed():
    j, l = example()
    none = recommend(j, l, {"safety_slip": 50.0})
    assert none.candidates == () and none.total == 0 and "목표를 낮추거나" in none.answer.basis[-1]
    with pytest.raises(ValueError, match="축직각 하중과 판 사이 마찰계수"):
        recommend(j, replace(l, transverse_load=0.0), {"safety_slip": 1.5})
    for bad in ({}, {"safety_magic": 2.0}, {"safety_yield": 0}):
        with pytest.raises(ValueError):
            recommend(j, l, bad)


def test_goal_words_and_choice_words_are_read():
    assert parse_targets("항복 안전율 1.5 이상이 되게 해 줘") == {"safety_yield": 1.5}
    assert parse_targets("항복 1.5 이상, 미끄럼 안전율은 2.5 이상") == {"safety_yield": 1.5, "safety_slip": 2.5}
    assert parse_targets("면압 안전율 1.2 이상 확보") == {"safety_pressure_head": 1.2, "safety_pressure_nut": 1.2}
    assert parse_targets("안전율 2 이상 되게") == {"safety_yield": 2.0}
    assert parse_targets("토크 60으로") == {} and parse_targets("항복 안전율이 얼마야") == {}
    assert (parse_choice("2번으로"), parse_choice("1안 적용"), parse_choice("토크 60")) == (2, 1, None)


def test_conversation_offers_first_and_changes_only_when_one_is_chosen():
    s = Session(*example())
    s.say("축방향 하중 12 kN")
    before = s.answer
    t = s.say("항복 안전율 1.5 이상, 미끄럼 안전율 2.5 이상이 되게 해 줘")
    assert t.changes == {} and s.answer is before and len(s.offers) == 3                    # 추천만 하고 바꾸지 않는다
    assert "1번: 규격 M16, 조임 토크 112.5 N·m" in t.reply and "비용이나 무게로 고른 순서가 아닙니다" in t.reply
    assert "안전율: 항복 2.62, 벌어짐 3.61, 미끄럼 2.51" in t.reply                          # 목표가 아닌 안전율도 함께 보인다
    assert s.say("7번으로").reply.startswith("7번 추천이 없습니다. 1~3번")
    done = s.say("1번으로")
    assert done.changes == {"size": "M16", "tightening_torque": 112.5} and s.joint.size == "M16" and s.offers == ()
    assert s.answer.value("safety_yield") >= 1.5 and s.answer.value("safety_slip") >= 2.5
    assert s.say("2번으로").reply == "2번 추천이 없습니다. 먼저 목표를 말해 추천을 받아 주세요."
    assert "이미 목표를 만족합니다" in s.say("벌어짐 안전율 3 이상 되게").reply
    assert s.say("1번으로").reply == "1번은 지금 설계 그대로입니다. 바꾼 것이 없습니다."
    assert s.say("피로 안전율 100 이상").reply.startswith("목표(피로 안전율 100 이상)를 만족하는 조합을 찾지 못했습니다")
    quiet = Session(example()[0], replace(example()[1], transverse_load=0.0))
    assert "추천을 만들지 못했습니다" in quiet.say("미끄럼 안전율 2 이상").reply


def test_llm_may_name_targets_or_a_choice_but_nothing_else():
    s = Session(*example(), provider=Fake('{"targets": {"safety_yield": 1.5}}'))
    t = s.say("볼트가 안 늘어나게 여유를 좀 줘")
    assert t.source == "llm" and len(s.offers) == 3 and "항복 안전율 1.5 이상" in t.reply
    s.provider = Fake('{"choose": 1}')
    assert s.say("첫 번째 걸로 하자").changes == {"tightening_torque": 47.5}
    for bad in ('{"targets": {"safety_magic": 3}}', '{"targets": {}}', '{"targets": {"safety_yield": "높게"}}', '{"choose": "첫째"}'):
        s2 = Session(*example(), provider=Fake(bad))
        t2 = s2.say("항복 안전율 1.5 이상")
        assert t2.source == "rule" and "규칙으로 읽음" in t2.note and len(s2.offers) == 3
