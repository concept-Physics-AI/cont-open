# 체결 팩 슬라이스 1: 계산 뼈대

볼트·너트와 판 2장으로 된 조인트를 치수로 정의하고, VDI 2230 해석식으로 체결력·응력·안전율을 계산해
공통 결과 형식(PhysicsAnswer)으로 낸다. 화면과 LLM은 없다.

## 쓰는 법

```python
from cont import packs

ans = packs.get("fastening").solve({
    "joint": {
        "size": "M10", "property_class": "10.9", "outer_diameter": 40.0,
        "plate_head": {"thickness": 15.0, "youngs_modulus": 205000.0},
        "plate_nut":  {"thickness": 15.0, "youngs_modulus": 205000.0},
    },
    "load": {"tightening_torque": 50.0, "friction_thread": 0.12, "friction_head": 0.12,
             "friction_range": [0.10, 0.14], "axial_load_max": 6000.0},
}, question="M10 10.9 볼트를 50 N·m로 조이면?")

for q in ans.quantities:
    print(q.label, q.value, q.unit, q.expected_range, q.note)
```

단위는 길이 mm, 힘 N, 응력 MPa, 토크 N·m이다.

## 계산하는 것

| 물리량 | 식 |
|---|---|
| 조임 토크 → 체결력 | M_A = F_M (0.16 P + 0.58 d2 mu_G + D_Km/2 · mu_K) |
| 마찰 산포에 따른 체결력 범위 | 마찰 최소·최대에서 같은 식 |
| 볼트 컴플라이언스 | 머리(0.5 d) + 축부 + 물리지 않은 나사부 + 물린 나사부(0.5 d) + 너트(0.4 d) |
| 판 컴플라이언스 | 대칭 변형 원뿔 + 슬리브. 두 판의 탄성계수가 달라도 구간별로 계산 |
| 하중 분담계수 | Phi_n = n · delta_P / (delta_S + delta_P) |
| 볼트 등가응력 (조임·운전) | 인장 + 나사부 비틀림, 운전 시 비틀림은 절반 |
| 벌어짐 시작 하중, 잔류 체결력, 미끄럼 안전율 | F_KR,min = F_M,min − F_Z − (1 − Phi_n) F_A |
| 좌면 압력, 면압 안전율 | p = F_S,max / A_p (판의 한계 면압을 준 경우에만 안전율) |
| 응력 진폭, 피로 안전율 | sigma_ASV = 0.85 (150/d + 45) |

## 범위 밖 (슬라이스 1)

- 편심 체결·편심 하중, 열 하중, 탭 구멍 체결(ESV), 와셔
- 나사산 전단(필요 물림 길이): 답변 묶음에 값 없이 "미구현"으로 표시한다
- 조임 방법별 조임 계수 표, 표면 거칠기별 함몰량 표: 지금은 마찰 범위와 함몰량을 직접 입력한다
- CAD 형상 생성(CadQuery 등): 조인트는 치수 데이터로만 있다
- 합격·불합격 판정: 값만 보고한다

## 신뢰도

답변 묶음의 신뢰도는 "중간"이다. 식의 내부 일관성(닫힌 식과의 일치, 하중 평형, 표준 응력 단면적)은 테스트로
확인했지만, 표준 예제와 FEM 기준값 대조는 슬라이스 2에서 한다. 표준 데이터(`tables/iso_metric.yaml`)도 그때
원문과 다시 대조한다.
