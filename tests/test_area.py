"""Studio가 질문의 물리 영역을 알아보는지: 모르면 추측하지 않고, 대화가 없는 영역은 계산하지 않고 알린다."""
from cont.dialogue.area import detect, not_ready_reply
from cont.dialogue.fastening_chat import Session
from cont.dialogue.serve_fastening import example, message


def test_detects_each_area_and_does_not_guess():
    assert detect("M10 볼트 토크를 80으로 바꿔 줘").key == "fastening"
    assert detect("선삭에서 절삭력이 얼마나 나와?").key == "machining"
    assert detect("모터 베어링 진동이 이상한데 진단해 줘").key == "diagnosis"
    assert detect("오늘 날씨 어때") is None                 # 모르면 추측하지 않는다
    assert detect("") is None


def test_tie_is_not_guessed():
    assert detect("볼트 진동") is None                      # 체결 1, 진단 1


def test_only_fastening_can_chat_now():
    assert detect("볼트 조임").chat is True
    assert detect("절삭력").chat is False and detect("진동 스펙트럼").chat is False


def test_message_about_other_area_does_not_compute_or_change_the_joint():
    s = Session(*example())
    before = (s.joint, s.load)
    m = message(s, "선삭 절삭력을 알려 줘")
    assert m["state"] is None and "절삭가공" in m["talk"]["text"] and "계산하지 않았습니다" in m["talk"]["text"]
    assert (s.joint, s.load) == before
    assert not_ready_reply(detect("진동")).startswith("설비 이상진단")


def test_fastening_questions_still_work_as_before():
    s = Session(*example())
    m = message(s, "토크를 60으로 줄여 줘")
    assert m["state"] is not None
