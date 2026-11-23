# ConT (Conception Teacher)

한국형 **물리 기반 생성형 AI**. 현실 세계를 가상의 AI 환경으로 옮기고, 그 환경을 다시 현실 세계와 연결한다.
만들어 내는 것은 대화, 코드, 이미지, 물리 이미지, 영상, 3D CAD이고, 지금 개발의 중심은 **체결(볼트 조인트)과 3D CAD**다.

만든 곳: ㈜컨셉션. 이 저장소는 개발 과정을 밖에서 확인할 수 있도록 공개한다.

## 먼저 알아 둘 것

- **모든 결과는 "검증 전"이다.** 실측이나 다른 해석 프로그램, 표준 예제와 대조한 것이 아직 하나도 없다. 설계 판단의 근거로 쓰지 않는다.
- **학습된 모형은 없다.** 숫자는 해석식, 수치해석, 닫힌 식의 역산, 통계에서 나온다. LLM은 말만 다듬고 숫자를 만들지 않는다.
- **확인하지 않은 값이 있다.** 표의 `verified: false`와 설정의 "잠정"이 그것이다 (볼트 머리·너트 높이, 절삭 재료 값, 불확도의 잠정값 등).
- **판정하지 않는다.** 합격·불합격의 기준(허용 오차)을 아직 정하지 않았다. 값과 편차만 보고한다.
- **라이선스는 아직 정하지 않았다.** [NOTICE.md](NOTICE.md)를 본다.

어떤 모형으로 숫자를 내는지는 [docs/physics_models.md](docs/physics_models.md)에 식과 함께 있다.

## 지금 되는 것

| 영역 | 되는 것 | 문서 |
|---|---|---|
| 체결 계산 | 토크 → 체결력, 강성, 하중 분담, 응력, 안전율 (VDI 2230 Part 1의 식) | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 체결 화면과 대화 | 말로 설계를 바꾸면 3D, 그래프, 숫자가 따라 바뀐다. 바뀐 곳을 표시한다 | [docs/fastening_screen.md](docs/fastening_screen.md) |
| 설계 추천 | 목표 안전율을 주면 규격·등급·토크의 조합을 찾는다 | [docs/fastening_recommend.md](docs/fastening_recommend.md) |
| 3D 형상 | 치수 → 형상 명세 → 화면용 3D, STL, STEP | [docs/shape.md](docs/shape.md) |
| 응력 분포 | 판 안의 응력을 축대칭 유한요소로 풀어 물리 이미지로 그린다 | [docs/fastening_field.md](docs/fastening_field.md) |
| 숨은 물리의 복원 | 볼트 늘어남 관측 → 체결력·마찰계수 추정 (범위, 잔차, 증거, 식별가능성) | [docs/fastening_estimate.md](docs/fastening_estimate.md) |
| 현장 계측 추천 | 어떤 센서를 어떻게 연결할지, 이 조인트에서 신호가 얼마나 나오는지 | [docs/fastening_sensing.md](docs/fastening_sensing.md) |
| 절삭가공 | 선삭의 절삭력·동력 (계산만) | [docs/machining_slice1.md](docs/machining_slice1.md) |
| 설비 진단 (ConT Fab) | 정상 기준, 이상 징후, 추이 | [docs/diagnosis.md](docs/diagnosis.md) |

## 돌려 보기

Python 3.11 이상.

```
python -m venv .venv
.venv\Scripts\activate          (Windows)   또는   source .venv/bin/activate
pip install -e .[dev]
pytest
```

체결 화면을 파일 하나로 만들기 (서버 없이 브라우저로 연다):

```
python -m cont.dialogue.serve_fastening --out fastening_demo.html
```

직접 말로 바꿔 보기 (LLM 없이도 규칙으로 동작한다):

```
python -m cont.dialogue.serve_fastening
```

## 원칙

- 물리 값은 물리 팩(해석식, 수치해석)에서만 나온다. LLM과 생성 모델은 물리 값을 만들지 않는다.
- 모든 값에 지위를 붙인다: 입력, 관측, 추정, 해석, 예측, 생성 후보. 불확실성, 물리잔차, 검증 상태를 숨기지 않는다 ([docs/hidden_physics.md](docs/hidden_physics.md)).
- 값을 코드에 박지 않는다. 표준 데이터는 표에, 바뀌는 값은 `config/`와 환경 변수에 둔다.
- 새 기능에는 테스트를 붙인다. `pytest`가 통과해야 병합한다.
- 문서는 한국어, 코드의 이름은 영어.

## 문서

- [ARCHITECTURE.md](ARCHITECTURE.md) — 구조와 모듈, 정체성, 물리 영역의 순서
- [docs/physics_models.md](docs/physics_models.md) — 쓰는 물리·수학 모형과 앞으로의 구성
- [docs/hidden_physics.md](docs/hidden_physics.md) — 보이는 물리와 숨은 물리: 정의, 값의 지위, 화면 규칙
- [docs/generation.md](docs/generation.md) — 만들어 내는 것(대화·코드·이미지·물리 이미지·영상·3D CAD)의 자리
- [CONTRIBUTING.md](CONTRIBUTING.md) — 의견과 오류를 알려 주는 방법
- [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md) — AI 개발 도구가 따르는 규칙

## 개발 방식

코드의 기준은 이 저장소 하나다. 시연 화면은 https://concept-physics-ai.github.io/cont-open/ 에 있고 main이 바뀔 때마다 새로 만들어진다. 한 브랜치에 한 가지 일을 하고, PR로 올려 대표가 병합한다. 개발에는 AI 개발 도구를 쓰며 그 규칙이 [CLAUDE.md](CLAUDE.md)에 있다.
이전의 저장소들은 보관되어 있고 참고만 한다. 거기서 가져온 생각에는 문서에 출처를 적는다 (보관 저장소는 비공개라 밖에서는 열리지 않는다).
