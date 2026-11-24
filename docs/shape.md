# 형상 (C5): 치수에서 3D 형상으로

> 상태: 보조

2026-11-23 대표 결정(C안): 치수에서 **형상 명세**를 만드는 층을 두고, 화면용 3D는 저장소 안에서 직접 만들며,
CAD 파일(STEP)은 뒤에 CAD 엔진을 붙여 같은 명세에서 만든다. 이 문서는 첫 조각(화면용 3D까지)을 적는다.

## 구조

```
조인트 치수 (BoltedJoint)  →  형상 명세 (Assembly, Part)  →  화면용 메시 (Mesh)  →  3D 보기
packs/fastening/shape.py      shape/spec.py                  shape/mesh.py           view/viewer3d.py
                                     ├→ STEP 파일 (shape/step.py, 직접 쓰기)
                                     ├→ STL 파일 (shape/stl.py)
                                     └→ CAD 엔진으로 STEP (shape/cad_ocp.py, 선택. 검증과 복잡한 형상용)
```

- **LLM은 형상을 직접 그리지 않는다.** 대화는 치수만 바꾸고, 형상은 치수에서 다시 만들어진다.
- **형상 명세는 도구에 묶이지 않는다.** 한 축을 공유하는 부품의 모음이고, 부품은 아래·위 높이, 바깥 윤곽(원 또는 육각), 구멍 지름으로 정해진다.
- **화면용 메시**는 삼각형이다. 닫힌 메시인지, 면이 바깥을 향하는지, 부피가 수식과 맞는지 테스트로 확인한다 (원을 36각형으로 나눈 만큼, 0.6% 안).
- **3D 보기**는 화면 파일 안에 들어가는 작은 WebGL 보기다. 외부 라이브러리를 쓰지 않는다.

## 볼트 조인트의 형상

```python
from cont.packs.fastening.shape import joint_shape, bolt_length
from cont.shape import assembly_mesh

a = joint_shape(joint)          # 볼트 머리, 볼트 축, 머리 쪽 판, 너트 쪽 판, 너트
a.part("bolt_head").outer       # 맞변 거리
bolt_length(joint)              # 체결 길이 + 너트 높이 + 나사 2피치
assembly_mesh(a.opened(("plate_head", "plate_nut")))   # 판의 4분의 1을 잘라 낸 화면용 메시
```

z = 0 은 두 판이 맞닿는 면이고 머리 쪽이 위다. 머리 높이와 너트 높이, 너트 밖으로 나오는 나사 길이(피치의 2배)는
`packs/fastening/tables/iso_metric.yaml`에 있다.

## 파일로 내기

```
python -m cont.packs.fastening.export --step joint.step --stl joint.stl   # 둘 다 추가 설치 없이 된다
python -m cont.packs.fastening.export --size M16 --step m16.step
```

체결 서버(`python -m cont.dialogue.serve_fastening`)의 화면에서도 지금 조인트를 STEP·STL으로 받을 수 있다. 대화로 값을 바꾼 뒤 받으면 바뀐 형상이 나온다.

| 형식 | 무엇인가 | 만드는 코드 | 쓰임 |
|---|---|---|---|
| STEP | 부품마다 이름이 붙은 솔리드. 원은 진짜 원통면 | `shape/step.py` (직접 쓰기, 추가 설치 없음) | CAD 프로그램에서 열어 치수를 재고 고친다 |
| STL | 삼각형 면 | `shape/stl.py` (추가 설치 없음) | 3D 프린터, 보기 프로그램 |

### STEP을 직접 쓰는 이유 (2026-11-23 대표 결정)

대표 PC는 Windows의 Smart App Control이 켜져 있어 CAD 엔진(OpenCascade)의 DLL을 불러오지 못한다
("애플리케이션 제어 정책에서 이 파일을 차단했습니다"). 보안 설정을 우회하지 않는다.
볼트 조인트의 부품은 평면과 원통면만으로 된 기둥이라, STEP의 경계 표현을 저장소 안의 코드로 직접 적는다.

- 꼭짓점 → 모서리(직선, 원호) → 면(평면, 원통면) → 닫힌 껍질 → 솔리드 순서로 적는다. 원은 원호 둘, 원통면은 반쪽 둘로 나눈다.
- 부품 이름은 영어 식별자다 (`bolt_head`, `bolt_shank`, `plate_head`, `plate_nut`, `nut`). 단위는 mm. 파일에는 ASCII만 쓴다.
- **검증**: CAD 엔진이 있는 환경에서 이 파일을 다시 읽어, 솔리드마다 형상이 유효하고 부피가 수식과 일치하는지 테스트한다 (M6, M10, M24).
  CAD 엔진이 없는 환경에서는 그 테스트를 건너뛰고, 파일의 뼈대와 "모든 모서리를 두 면이 서로 반대 방향으로 한 번씩 쓰는지"만 확인한다.
- **한계**: 한 축에 늘어선 원·육각 기둥만 쓸 수 있다. 절삭 형상이나 금형처럼 곡면과 불리언 연산이 필요한 형상은 CAD 엔진으로 내야 한다.
  그때는 `shape/cad_ocp.py`(`pip install -e .[cad]`, `--engine ocp`)를 Linux 환경(서버, 컨테이너)에서 쓴다.
- 부품은 제자리에 놓인 솔리드 다섯 개다. 조립 관계와 색은 넣지 않는다.

## 지금의 한계

- **머리 높이와 너트 높이는 내가 표준(ISO 4014, ISO 4032)의 값으로 알고 적은 것이다.** 원문과 대조하지 않았다. 계산에는 쓰지 않고 형상에만 쓴다. 기준값 대조 조각에서 표 전체와 함께 다시 확인한다.
- 나사산, 모따기, 머리 밑 둥근 부분은 그리지 않는다. 볼트 축은 호칭 지름의 원기둥이다.
- 볼트 길이를 표준 길이 단계(40, 45, 50 ...)로 올리지 않는다.
- 판은 체결부 대체 바깥지름의 원판이다. 실제 판의 외형이 아니다.
- 한 축에 늘어선 부품만 나타낼 수 있다. 볼트가 여러 개인 체결부, 임의 형상은 아직 없다.
- 내보낸 STEP을 상용 CAD 프로그램에서 열어 보는 확인은 하지 않았다. CAD 엔진으로 다시 읽는 확인만 했다.
- 3D 보기는 정사영(원근 없음)이고, 치수 표시와 단면 위치 바꾸기가 없다.
