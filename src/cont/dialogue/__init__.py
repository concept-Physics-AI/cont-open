"""C1 대화·조율: 질문을 받아 물리 팩의 결과로 답한다. 숫자는 팩이 내고, LLM은 말만 다듬는다."""
from cont.dialogue.diagnosis_qa import Reply, ask, facts, focus, rule_answer

__all__ = ["Reply", "ask", "facts", "focus", "rule_answer"]
