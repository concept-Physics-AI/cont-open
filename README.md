# ConT (Conception Teacher)

> 상태: 참고

**현재 최우선 목표:** 실제 대화와 문맥 유지, 작업 계획과 순차 실행, 다양한 결과물 생성, 선택한 결과 편집, 결과 간 일관성, 작업 저장과 이어 하기. M01·M03·M04·M10과 프로젝트 관리를 먼저 연결하고, M02는 근거를 보강하며 M05~M09는 필요한 전문 기능으로 연결한다.

**개발 순서:** 기존 AI 모델로 생성형 소프트웨어 완성 → 실제 사용 평가 → 필요한 데이터 확보·학습. 지금은 대화·생성·선택 편집·저장 연결에 집중하며, 학습용 데이터 구축과 자체 모델 학습은 후속 단계로 둔다. 사용자 입력 처리와 실제 생성·복원 시험은 지금 수행한다.

[제품 기준](ARCHITECTURE.md) · [첫 완성본 인수 흐름](docs/generative_workflow.md) · [개발 순서](docs/roadmap.md) · [차별화 제안](docs/differentiation.md). 이 목표가 모두 구현됐다는 뜻은 아니다.

한국형 **물리 기반 생성형 AI**. 현실 세계를 가상의 AI 환경으로 옮기고, 그 환경을 다시 현실 세계와 연결한다.
대화로 목적을 이해하고 **설명·이미지·도식·그래프·3D·4D를 순차적으로 생성하고 수정하며, 작업을 저장해 이어 가는 것**이 제품 개발의 중심이다. 체결·하이브리드 본딩·관절은 이 능력을 적용하는 사례다.

만든 곳: ㈜컨셉션. 이 저장소는 개발 과정을 밖에서 확인할 수 있도록 공개한다.

## 먼저 알아 둘 것

- **모든 결과는 "검증 전"이다.** 실측이나 다른 해석 프로그램, 표준 예제와 대조한 것이 아직 하나도 없다. 설계 판단의 근거로 쓰지 않는다.
- **실측으로 평가한 산업별 제품 학습 모형은 아직 없다.** 열 PINN 연구 코드와 합성 데이터의 M05·M06 학습 실험은 있다. LLM은 의도·계획·설명을 맡고 물리 결과 수치는 계산·측정 결과에서 가져온다.
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
| 설비 진단 (Fab으로 만든 것의 예) | 정상 기준, 이상 징후, 추이 | [docs/diagnosis.md](docs/diagnosis.md) |
| ConT Fab: 고르기 | 물리 정보를 상품처럼 골라 바구니에 담는다. 미리보기는 엔진을 돌린 결과 | [docs/fab_store.md](docs/fab_store.md) |
| 설비 이상진단 화면 (ConT Fab으로 만든 화면의 한 예) | 현장 설정, 신호와 정상 범위, 관찰 사실 · 원인 후보 · 다음 점검 | [docs/diagnosis_screen.md](docs/diagnosis_screen.md) |

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
