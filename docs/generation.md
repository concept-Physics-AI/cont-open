# 이미지 생성 (cont.generation)

> 상태: 보조

## 제품 안에서의 우선순위

M04는 M01·M03·M10 및 프로젝트 관리와 함께 최우선 핵심이다. 실제 생성 → 화면 표시 → 대상 선택 → 부분 수정 → 관련 결과 갱신 → 저장의 한 흐름으로 개발한다. 산업별 예측 모델과 실측 데이터는 설명 이미지 생성의 선행조건이 아니다. 상세 연결과 인수는 [generative_workflow.md](generative_workflow.md)를 따른다.

설명 이미지·공정 단계 애니메이션은 생성/구성할 수 있다. 정확한 치수 표기·그래프는 구조화된 값으로 그리고, 온도·응력·변형의 분포는 계산·측정 결과를 참조한다. 이미지에서 만든 3D는 자동으로 치수가 보장된 CAD가 되지 않는다. 공통 부품 ID와 구조 명세를 먼저 두고, 2D와 3D의 일치는 명시적 대응과 검수로 확인한다.

인터페이스·Fake 어댑터·시험 틀에 더해 diffusers 어댑터와 SDXL 설정이 추가됐다(PR #93). 기본 용도 연결은 아직 fake이며 실제 가중치로 생성한 파일·실행 로그의 인수는 이 변경에서 확인하지 않았다.

## 구조

- 호출: `get_generator(purpose="general").generate(ImageRequest(prompt, width, height, seed))` → `ImageResult`.
- 모델은 설정이 정한다: `config/generation/models.yaml` (+ `models.local.yaml`, git 제외). `CONT_GEN_MODEL`이 용도 연결보다 앞선다.
- 결과 기록(`record()`): 모델 이름, 실제 가중치, 시드, 크기, 이미지 sha256, `real`. 같은 결과를 다시 만들 근거다.
- `real=False`(가짜) 결과는 실제 생성 성공으로 세지 않는다. 가짜는 작은 그라디언트 PNG를 요청 내용에서 결정적으로 그린다.
- diffusers·transformers는 `src/cont/generation/` 안에서만 가져온다(`config/authority.yaml`).

## 후보와 순서 (2026-11-25 결정)

| 순위 | 모델 | 용도 | 라이선스(웹 자료, 모델 카드 원문 확인 전) |
|---|---|---|---|
| 1 | FLUX.2 klein 4B | general | Apache 2.0 |
| 2 | Qwen-Image-2512 (양자화) | text_heavy | Apache 2.0 |
| 3 | SDXL 1.0 | draft, 시험 틀 검증용 기준선 | OpenRAIL++-M (사용 제한 조항) |

제외: FLUX.1 dev, FLUX.2 klein 9B·dev(비상업), Qwen-Image-2.1(연구용 라이선스라는 자료가 있음), SD 3.5(매출 조건), HiDream-I1(16GB에 빠듯).

## 단계

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | 인터페이스, 가짜 어댑터, 설정, 시험 | 완료 |
| 2 | SDXL 어댑터 + 실행 환경 설치, 실제 생성 확인 | 어댑터·설정·주입 시험 구현(PR #93). 실제 모델 생성 인수는 별도 확인 필요 |
| 3 | FLUX.2 klein, Qwen-Image 어댑터, 같은 문항으로 속도·VRAM·글자 정확도 비교 | 미착수 |
| 4 | 비교 결과로 용도 연결 확정 | 미착수 |

실제 모델을 부르는 시험은 기본으로 끈다. 가중치와 설치 경로는 저장소 밖(`models.local.yaml`)에 둔다.
