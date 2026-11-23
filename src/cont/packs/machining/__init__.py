"""절삭가공 물리 팩 (슬라이스 1): 선삭의 절삭력·동력·표면 거칠기, 키엔츨레 식."""
from cont.packs import register
from cont.packs.machining.cut import TurningCut
from cont.packs.machining.pack import MachiningPack, answer

PACK = register(MachiningPack())

__all__ = ["TurningCut", "MachiningPack", "PACK", "answer"]
