# 이미지 생성 연결 (자체 모델)

ConT의 모든 모듈은 `cont.generation.get_generator(purpose=...)`로만 이미지를 만든다.
어떤 모델을 쓸지는 코드가 아니라 설정이 정한다.

| 파일 | 내용 |
|---|---|
| `models.yaml` | 공용 목록과 용도 연결 (git에 올라감) |
| `models.local.yaml` | 이 PC의 가중치 경로 등 (git 제외) |

- 용도: `draft`(빠른 시안), `general`(기본), `text_heavy`(글자·도면). 용도에 어느 모델을 연결할지는 비교 시험 뒤에 정한다.
- 고르기: `CONT_GEN_MODEL=<이름>` (없으면 용도 연결, 그것도 없으면 `default`)
- 새 모델: `cont.generation.register_type("이름", 클래스)`로 타입을 더하고 `models.yaml`에 한 줄을 더한다. 다른 코드는 바꾸지 않는다.
- `real: false` 결과(가짜)는 실제 생성 성공으로 세지 않는다.
