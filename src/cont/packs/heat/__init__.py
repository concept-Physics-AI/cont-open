"""열 물리 팩 (두 번째 영역): 비정상 열전도 유한차분 풀이기와 해석해 기준 문제."""
from cont.packs import register
from cont.packs.heat.pack import HeatPack, answer

PACK = register(HeatPack())

__all__ = ["HeatPack", "PACK", "answer"]
