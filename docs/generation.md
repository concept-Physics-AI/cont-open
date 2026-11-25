# 이미지 생성 (cont.generation)

> 상태: 1단계(인터페이스·가짜 어댑터·시험 틀) 완료. 실제 모델은 아직 하나도 붙이지 않았다.

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
| 2 | SDXL 어댑터 + 이 PC에 생성 도구 설치, 실제 생성 확인 | 대표 허락 받음, 미착수 |
| 3 | FLUX.2 klein, Qwen-Image 어댑터, 같은 문항으로 속도·VRAM·글자 정확도 비교 | 미착수 |
| 4 | 비교 결과로 용도 연결 확정 | 미착수 |

실제 모델을 부르는 시험은 기본으로 끈다. 가중치와 설치 경로는 저장소 밖(`models.local.yaml`)에 둔다.
