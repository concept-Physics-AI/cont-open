# 상단 Studio · Physics · FAB 전환 틀

세 제품 화면은 서버가 따로 돌아도 맨 위에 같은 막대(높이 40px)를 단다. 지금 있는 탭이 표시되고, 나머지를 누르면 그 제품으로 이동한다.

| 제품 | 하는 일 | 화면 | 기본 주소 |
|---|---|---|---|
| Studio | 대화로 물리와 일반 AI를 다루는 통합 작업 공간 | 체결 대화 화면 (`cont.dialogue.serve_fastening`) | 127.0.0.1:8766 |
| Physics | Studio와 FAB이 함께 쓰는 엔진과 서비스 | 엔진 목록 (`cont.view.physics_page`, 새로 만듦) | 127.0.0.1:8769 |
| FAB | 물리 정보를 골라 내 현장 화면을 꾸리는 곳 | 고르기 화면 (`cont.fab.store`), 이상진단 화면(FAB으로 만든 화면)도 FAB 쪽 | 127.0.0.1:8768 |

- 이름·한 줄 설명·주소는 `config/products.yaml`. 주소는 환경 변수 `CONT_STUDIO_URL`, `CONT_PHYSICS_URL`, `CONT_FAB_URL`로 바꾼다. 주소가 비어 있는 탭은 이동하지 않는다.
- 막대를 다는 코드는 `cont.view.switcher.with_switcher()` 하나이며, 화면마다 이 함수만 부른다.
- Physics 화면은 "지금 있는 엔진"(`config/physics/engines.yaml`, 코드의 팩 이름과 같은지 테스트로 확인)과 "아직 없는 엔진"(FAB 표현 유형이 기다리는 엔진)만 보인다. 엔진을 새로 만들지 않았고, 계산하지 않는다.
- 실행: `python -m cont.view.physics_page` (또는 `--out 파일.html`).

## 아직 안 된 것
- 세 제품이 한 서버·한 로그인으로 묶이지 않았다. 지금은 주소 이동이다.
- Studio에서 FAB으로 구성을 넘기는 기능은 없다.
- 공개 시연(정적 페이지)에서는 다른 제품의 주소를 모르면 탭이 눌리지 않는다.
