"""신호 분석 엔진: 파형을 주파수 성분, 시간별 주파수 변화, 값의 분포로 나눈다.

물리 가정이 없는 수학 계산(푸리에 변환, 통계)이라 알려진 신호를 넣어 결과가 맞는지 확인할 수 있다.
들어오는 것은 값의 배열과 샘플링 주파수(Hz)다. 단위는 부르는 쪽의 것을 그대로 쓴다.
무엇이 정상인지, 어느 주파수가 결함인지는 판단하지 않는다 (판정은 하지 않고 성분과 분포만 보고한다).
"""
from cont.signal.analysis import Distribution, Spectrogram, Spectrum, distribution, peaks, spectrogram, spectrum

__all__ = ["Distribution", "Spectrogram", "Spectrum", "distribution", "peaks", "spectrogram", "spectrum"]
