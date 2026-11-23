"""특화 이상진단: 공통 진단이 찾은 변화가 "이 공정에서 무엇을 뜻하는가".

공통 진단 위에 얹는다. 세 가지 방식이 있다.
- 해석 규칙(interpret): 공통 진단의 상태 변화를 공정의 말로 옮긴다 (공정 지식표)
- 스트로크 부하 곡선(stroke): 반복 동작 한 번의 부하 곡선에서 어느 구간이 평소와 다른지 (새 계산)
- 품질 예측(predict): 공정 값으로 두께 같은 품질 값을 예측한다 (정답 데이터로 만든 모델)
"""
from cont.packs.diagnosis.special.interpret import Finding, Interpretation, interpret
from cont.packs.diagnosis.special.predict import QualityModel, QualityPrediction, assess_quality, fit_quality
from cont.packs.diagnosis.special.stroke import StrokeDiagnosis, diagnose_stroke

__all__ = ["Finding", "Interpretation", "QualityModel", "QualityPrediction", "StrokeDiagnosis",
           "assess_quality", "diagnose_stroke", "fit_quality", "interpret"]
