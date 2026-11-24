"""시험 공통 설정: 화면 시험이 PINN을 오래 학습하지 않도록 열 비교 화면은 짧은 설정을 쓴다 (수렴을 기대하지 않는 시험용)."""
import os

os.environ.setdefault("CONT_HEAT_COMPARE_PROFILE", "smoke")
# 시험을 둘 이상 동시에 돌리면 수치 라이브러리의 스레드가 CPU를 서로 뺏어 HTTP 시험이 시간초과로 실패했다.
# numpy를 불러오기 전에 스레드 수를 1로 고정한다 (이미 환경에 정해 둔 값이 있으면 그대로 둔다).
for _k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_k, "1")
