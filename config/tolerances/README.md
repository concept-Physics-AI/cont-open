# 허용 오차 프로파일

허용 오차는 **코드에 고정하지 않는다.** 사용 환경(재료, 공정, 고객 기준, 시험 장비)마다 다르기 때문이다.

- `default.yaml`: 모든 항목이 `limit: null`이다. 이 경우 ConT는 **편차만 계산해서 보고하고, 합격·불합격 판정은 하지 않는다.**
- 판정이 필요한 환경이 생기면 `profiles/<이름>.yaml`을 만들고 필요한 항목만 적는다. 적지 않은 항목은 default를 따른다.
- 고르는 방법: 환경 변수 `CONT_TOLERANCE_PROFILE=<이름>` (없으면 default)
- 개인·현장 전용 값은 `profiles/<이름>.local.yaml`로 저장한다. 이 파일은 git에 올라가지 않는다.
- 항목 하나만 잠깐 바꿀 때: `CONT_TOL__<항목>__LIMIT=0.05` 같은 환경 변수가 프로파일보다 우선한다.

항목(quantity) 이름은 default.yaml에 있는 것을 쓰고, 새 물리량이 생기면 default.yaml에 `limit: null`로 먼저 추가한다.

`mode`:
- `relative`: |계산값 − 기준값| / |기준값|
- `absolute`: |계산값 − 기준값| (단위는 `unit`)
- `range_match`: 기준 범위와 겹치는지
- `rank`: 추천 순위가 기준 상위 N 안에 드는지
