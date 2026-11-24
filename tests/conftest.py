"""시험 공통 설정: 화면 시험이 PINN을 오래 학습하지 않도록 열 비교 화면은 짧은 설정을 쓴다 (수렴을 기대하지 않는 시험용)."""
import os

os.environ.setdefault("CONT_HEAT_COMPARE_PROFILE", "smoke")
