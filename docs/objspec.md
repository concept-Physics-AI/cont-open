# 공통 대상 명세 (objspec)

> 상태: 보조

같은 대상을 설명 이미지·3D·4D·그래프가 **같은 부품 ID**로 가리키게 하는 명세다. 로드맵 Y9의 첫 구현이며, 3D 장면·단계 4D·이미지 요청은 이 명세를 읽는다(그래프 연결은 아직 없고, 저장·재열기는 `service.project`가 맡는다). 구현 위치는 `src/cont/objspec/`.

## 무엇을 하나

| 질문 | 답 | 코드 |
|---|---|---|
| 이 그림의 "위 다이"는 3D의 어느 부품인가 | 부품 ID `die.si` | `ObjectSpec.part(id)` |
| 구조가 바뀌었나 | 내용 해시 `version`이 달라진다 (부모 version은 해시에 넣지 않는다) | `ObjectSpec.version` |
| 이 표현이 명세와 맞나 | 빠진 부품·모르는 ID·이름 불일치·다른 version을 나눠 보고한다 | `check` |
| 부품을 고치면 무엇을 다시 만들까 | 바뀐 부품을 가리키는 표현만 고른다. 카메라·속도 변경은 아무것도 고르지 않는다 | `affected` |
| 카메라를 돌리거나 한 단계만 느리게 하면 | `ViewState`만 바뀌고 구조 version은 그대로다 | `ViewState` |

## 첫 대상: 본딩 층 구조

`hybrid_bonding_stack()`은 아래 웨이퍼·아래 유전층·위 유전층·위 다이 네 부품과 접근·정렬·접촉 세 단계를 만든다. **치수는 설명용(`illustrative`)이며 실측이 아니다.** 사용자가 `edit_part`로 고치면 `user_input`이 된다. 단계의 시간 축은 공정 단계 순서(`process_stage`)이고 물리 시간이 아니다. 접합 품질·온도·응력은 이 명세에 없다.

## 3D 장면과 단계 4D 재생

`Timeline(spec, view)`가 단계별 길이(기본 2초 ÷ 속도, `config/objspec/playback.yaml`)와 부품별 자세를 정한다. 시작 자세(`start`)에서 단계 끝 자세로 smoothstep으로 움직이고, 단계에 없는 부품은 제자리다. `view/scene4d.py`는 같은 식을 JS로 돌려 WebGL 한 파일 HTML을 만든다(재생·멈춤, 위치 막대, 단계 버튼, 끌기·휠·키보드 카메라, 처음 시점 복귀, 자동 재생 없음). 속도를 바꾸면 그 단계 길이만, 카메라를 바꾸면 시점만 달라지고 부품 모양과 구조 version은 그대로다. 시험이 JS와 Python의 자세 값을 맞춰 보고, 실제 Chrome에서 그려지고 재생되는지 확인한다.

## 설명 이미지 연결

`generate_image(spec, generator, stage)`가 명세의 부품 목록과 아래→위 층 순서로 영어 프롬프트를 만들고(문구는 `config/objspec/image_prompt.yaml`), 생성 결과와 같은 부품 ID를 가리키는 `Representation`·기록(명세 version, 단계, 치수 상태)을 돌려준다. 부품을 고치면 `check`가 이미지를 `stale`로 표시하고 `affected`가 다시 만들 표현으로 고른다. 카메라·속도 변경은 이미지에 영향이 없다. **부품 목록은 프롬프트에 적은 것(`parts_declared_by: prompt`)이며, 그림이 그 층을 실제로 그렸는지는 확인하지 않는다.** 가짜 생성기 결과는 `real: false`로 남는다. 실제 모델(SDXL 등)로 돌린 그림의 층 일치는 사람이 보거나 이후 시각 검수가 맡는다.

## 선택한 부분만 고치기 (P4)

`select(spec, "위 다이")`가 부품 ID·이름·층 이름·이름 일부 순으로 찾아 부품 ID를 돌려주고, `select_region(spec, (x0,y0,x1,y1))`는 옆면 단면 도식 위 사각형이 덮은 부품을 고른다(상자의 절반 이상을 덮은 부품, 없으면 중심이 든 부품 하나). 모호하거나 없으면 `SelectionError`로 후보를 알리고 고치지 않는다. `edit_selection(spec, selection, z1=2.4)`는 선택한 부품에만 변경을 적용하고 변경 전후(`diff`)와 그대로인 부품(`unchanged`), 다시 만들 표현(`rebuild`)을 돌려준다. 같은 값으로 고친 것은 변경이 아니다. 단계 하나의 부품 자세는 `ObjectSpec.edit_stage_pose`로 고친다. 층이 겹치게 되는 변경은 막지 않고 `overlaps`로 알린다.

- 영역 선택은 **우리가 그린 옆면 도식(쉬는 자세)** 기준이다. 생성한 그림 위의 영역은 그림에 부품 위치 정보가 없어 풀 수 없다.
- 부품 사이 치수 정합(예: 위 다이가 아래보다 커도 되는가)은 판단하지 않는다.

## 저장과 다시 열기 (P6)

`save_project(root, project_id, name, spec, view, selection, playback_t, images)`가 한 폴더에 `manifest.json`, `files/`(명세 JSON·이미지 PNG), `ledger/`(기존 자료 장부 기록)를 쓴다. 명세는 장부의 원본(source), 고친 명세는 이전 명세를 부모로 둔 파생물, 이미지는 만든 때의 명세를 부모로 둔 파생물이다. `open_project(root)`는 파일만 읽어 같은 명세·카메라·단계 속도·선택·재생 위치·이미지로 복원하며 **모델을 부르지 않는다**. 화면은 `scene4d_page(state.spec, state.view, start_t=state.playback_t)`로 저장한 위치에서 다시 시작한다. `restore_version`은 이력의 이전 명세를 꺼낸다(현재 상태는 다시 저장해야 바뀐다).

| 상황 | 동작 |
|---|---|
| 저장 중 종료 | manifest를 임시 파일에 쓴 뒤 바꿔 넣으므로 직전 정상 저장이 남는다 |
| manifest 손상·손으로 고침(본문 해시 불일치) | 직전 정상 manifest로 열고 `recovered_from_previous`·`problems`로 알린다. 둘 다 못 쓰면 거절 |
| 명세 파일이 없거나 바뀜 | 열지 않는다 |
| 이미지 파일이 없거나 바뀜 | 열되 해당 이미지를 `missing`·`changed`로 표시하고 `problems`에 적는다 |
| 다른 프로젝트의 manifest·폴더 | 거절 |
| 지원하지 않는 저장 형식 버전 | 거절(추측해서 열지 않는다) |
| 동시 저장 | 잠금 파일로 거절. 오래된 잠금(`config/objspec/project.yaml`)은 지운다 |

- 이 저장에는 **대화와 계획 체크포인트가 없다**(대화 문맥은 `dialogue`가 따로 둔다. 하나로 묶는 일은 후속).
- 사용자별 분리와 접근 권한은 없다. 폴더가 곧 프로젝트다.

## 기존 것과의 관계

- 부품 형상은 기존 `cont.shape.Part`를 쓴다. `to_assembly()`로 기존 3D 메시와 CAD 내보내기로 이어진다.
- 실행 ID, 자료 장부(ledger) ID는 새로 만들지 않는다. 장부 등록은 부모 자료가 있어야 하므로, 명세를 저장 기록에 연결하는 일은 프로젝트 저장(P6)에서 정한다.

## 지금 없는 것

- 그림 픽셀에서 층·부품을 확인하는 시각 검수, 그래프 계열과 부품 ID의 연결
- 3D 장면을 직접 눌러 가리키는 선택(화면 상호작용), 생성한 그림 위의 영역 해석
- 대화·계획 체크포인트를 같은 저장에 묶기, 사용자별 분리
- 층 안의 구리 패드 같은 가로 방향 구조. 지금은 z로 쌓은 층만 표현한다
