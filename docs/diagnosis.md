# 진단 팩: 설비 이상진단

> 상태: 보조

**이 팩의 위치**: 설비 이상진단은 ConT Fab으로 만든 것의 한 예다 (ARCHITECTURE.md의 "3제품 1코어", 2026-11-23 대표 정리). ConT Fab 자체가 아니다.
현장 설비의 신호를 받아 같은 운전조건의 평소와 비교하고, 관찰 사실, 원인 후보, 다음 점검을 낸다.
지금까지의 결과는 모두 가상 데이터로 확인한 것이며 현장 데이터로 검증하지 않았다.

## 정의

**공통 이상진단**: 설비 이름과 상관없이, 설비를 이루는 구성요소와 동작에 대해
"같은 운전조건의 평소와 지금이 다른가, 다르다면 어느 계통의 어떤 변화인가"를 답한다.

- 보는 단위: 구동계, 압력·유동계, 열관리계, 공정 동작·사이클
- 필요한 것: 정상 운전 데이터와 운전조건. 고장 사례는 없어도 된다
- 답: 부하 증가, 응답 지연, 온도 추종 불량, 사이클 편차처럼 일반적인 상태 변화
- 새 현장 적용: 신호 연결(열 이름 → 역할)과 기준값 설정만으로

**특화 이상진단**: 공통 진단이 찾아낸 변화가 "이 공정에서 무엇을 뜻하는가"를 답한다.

- 보는 단위: 특정 설비와 공정
- 필요한 것: 공정 지식과, 정비 이력·품질 측정값처럼 정답이 확인된 현장 데이터
- 답: 공구 파손, 가공 부하 이상, 토출 이상, 두께 예측처럼 그 공정의 말
- 새 현장 적용: 추가 개발이나 추가 학습

**경계**: 코드를 고치지 않고 설정만으로 다른 설비에 쓸 수 있으면 공통, 새 계산·모델·정답 데이터가 필요하면 특화다.
특화 진단은 공통 진단 위에 얹는다. 예: "스핀들 부하가 같은 조건의 평소보다 급격히 떨어졌다"(공통) → "공구 파손이다"(특화).

## 진행 순서

| 슬라이스 | 내용 | 상태 |
|---|---|---|
| D1 | 구동계 공통 진단(정상 기준, 이탈 검출, 상태 변화 유형)과 결과 화면 | 완료 |
| D2 | 압력·유동계, 열관리계, 공정 동작·사이클 모듈. 설비 한 대를 계통별로 묶은 진단과 화면 | 완료 |
| D3 | 대화로 묻기: 진단 결과에 대해 묻고 답하기, 화면의 질문 영역, 내 PC에서 띄우는 진단 서버 | 완료 |
| D4 | 특화 진단 1: 공정 해석 규칙(절삭·프레스·압출), 스트로크 부하 곡선, 품질(두께) 예측 | 완료 |
| D5 | 원인 후보와 점검 안내, 상태 추이 화면, 원인·점검 질문에 답하기 | 완료 |

## 쓰는 법

가상 설비(4계통)로 화면 만들기:

```
python -m cont.packs.diagnosis.demo --out demo.html
```

현장 설정 파일로 설비 한 대 진단하기. 설정 파일이 계통마다 CSV와 "열 이름 → 역할"을 잇는다:

```yaml
# site.yaml (CSV 경로는 이 파일 위치 기준)
equipment: 3호기
systems:
  - name: 주축 구동부
    module: drive
    normal: normal_drive.csv
    current: today_drive.csv
    time: t
    signals: {MTR01_A: current, VIB01: vibration}
    conditions: {LOAD_PCT: load, RPM: speed}
  - name: 유압 공급 라인
    module: pressure_flow
    normal: normal_hyd.csv
    current: today_hyd.csv
    signals: {PT01: pressure, FT01: flow}
    conditions: {P_SET: setpoint}
```

```
python -m cont.packs.diagnosis.demo --site site.yaml --out result.html
```

현장 데이터와 현장 설정 파일은 저장소에 넣지 않는다 (데이터는 Z:).

CSV 두 개(정상 구간, 진단할 구간)로 진단하기:

```
python -m cont.packs.diagnosis.demo --normal normal.csv --current now.csv \
    --signal MTR01_A=current --signal VIB01=vibration --condition LOAD_PCT=load --condition RPM=speed \
    --time t --out result.html
```

`--signal`과 `--condition`은 "현장 열 이름=모듈의 역할"이다. 모듈별 역할은 `src/cont/packs/diagnosis/tables/`에 있다.

| 모듈 | 신호 역할 | 운전조건 역할 |
|---|---|---|
| `drive` 구동계 | `current`, `torque`, `vibration`, `tracking_error`, `temperature` | `load`, `speed` |
| `pressure_flow` 압력·유동계 | `pressure`, `flow`, `pressure_drop`, `pulsation`, `response_time` | `setpoint`, `speed`, `valve` |
| `thermal` 열관리계 | `temperature`, `tracking_error`, `heater_output`, `coolant_delta` | `setpoint`, `ambient`, `load` |
| `cycle` 공정 동작·사이클 | `cycle_time`, `step_time`, `peak_load`, `energy`, `position_error` | `speed_setting`, `load` |

`cycle`은 표본 하나가 사이클 한 번이다. 사이클마다 한 줄로 요약한 값을 넣는다. 원시 신호에서 사이클을 잘라 요약하는 일은 아직 없다.

코드에서:

```python
from cont.packs.diagnosis import diagnose
from cont.view import render_diagnosis

d = diagnose("drive", normal, current, {"MTR01_A": "current"}, {"LOAD_PCT": "load"}, time="t")
d.answer            # 공통 결과 형식 (PhysicsAnswer)
render_diagnosis(d) # 한 파일 HTML

from cont.packs.diagnosis import diagnose_equipment, load_site
from cont.view import render_equipment

name, systems = load_site("site.yaml")
eq = diagnose_equipment(systems, name)   # 어느 계통에서 어떤 변화인지
render_equipment(eq)
```

## 묻고 답하기 (D3)

진단 결과에 대해 질문하면 답한다. 구현은 `src/cont/dialogue/`(C1 대화·조율)에 있다.

```
python -m cont.dialogue.serve                    # 가상 설비. 브라우저에서 http://127.0.0.1:8765
python -m cont.dialogue.serve --site site.yaml   # 현장 설정 파일
python -m cont.dialogue.serve --llm              # LLM으로 답의 말을 다듬는다 (config/llm의 기본 공급자)
```

```python
from cont.dialogue import ask
from cont.llm import get_provider

ask("유압 쪽은 언제부터 이상했나요?", eq)                  # 규칙으로 만든 답 (LLM 없음)
ask("유압 쪽은 언제부터 이상했나요?", eq, get_provider())  # LLM이 말을 다듬은 답
```

지키는 원칙:

- 숫자와 판정은 진단 팩이 낸 것만 쓴다. LLM에는 질문에 해당하는 "진단 사실"만 넘기고, LLM은 말을 다듬기만 한다.
- LLM 없이도 답한다. LLM이 꺼져 있거나, 응답이 비었거나, 진단 사실에 없는 숫자를 말하면 규칙으로 만든 답으로 돌아가고 그 이유를 남긴다.
- 원인을 단정하지 않는다. "왜"를 물으면 무엇이 어떻게 달라졌는지 답하고, 원인은 점검과 특화 진단의 몫이라고 말한다.
- 서버는 내 PC(127.0.0.1)에서만 받는다. 밖에서 접속하게 하려면 별도 설계가 필요하다.

지금은 진단이 끝난 결과에 대해 묻는 것까지다. "3호기 어제 데이터로 진단해 줘"처럼 대화로 진단을 시작하는 일,
앞 질문을 이어받는 일은 아직 없다. 질문이 어느 계통을 가리키는지는 계통 이름과 `tables/*.yaml`의 `keywords`로 찾는 단순한 방식이다.

## 특화 진단 (D4)

공통 진단 위에 얹는다. 구현은 `src/cont/packs/diagnosis/special/`, 공정 지식은 `tables/special/<공정>.yaml`에 있다.

| 방식 | 무엇을 답하나 | 필요한 것 | 예 |
|---|---|---|---|
| 해석 규칙 `interpret()` | 공통 진단의 변화가 이 공정에서 무엇을 뜻하는가 | 공정 지식표 | 주축 부하가 갑자기 떨어짐 → 공구 파손 의심 |
| 스트로크 부하 곡선 `diagnose_stroke()` | 스트로크의 어느 구간이 평소와 다른가 | 스트로크별 부하 곡선 (정상 구간) | 성형 구간의 가공 부하 이상 |
| 품질 예측 `fit_quality()`, `assess_quality()` | 공정 값으로 본 품질 값이 규격 안인가 | 실제로 잰 품질 값(정답)이 있는 데이터 | 필라멘트 두께 예측 |

```
python -m cont.packs.diagnosis.demo --special --out special.html   # 가상 데이터로 세 가지 시연
```

```python
from cont.packs.diagnosis.special import interpret, diagnose_stroke, fit_quality, assess_quality

interpret("cutting", eq).findings                       # eq: diagnose_equipment()의 결과
diagnose_stroke(normal_curves, current_curves, position)   # 표: 스트로크 수 × 위치 수
model = fit_quality(train, "thickness", ["screw", "puller", "melt"])
assess_quality(model, current, spec=(1.68, 1.82), time="t", unit="mm")
```

알아 둘 것:

- **해석 규칙은 내가 일반적인 공정 지식으로 쓴 출발점이다.** 현장의 정비 이력·공구 교체 기록·품질 기록과 맞춰 본 것이 아니다.
  그래서 결과는 "의심"이고 신뢰도는 "낮음"이다. 규칙은 `tables/special/*.yaml`만 고치면 바뀐다.
- 같은 변화도 시작 모양에 따라 뜻이 다르다. 이상 구간이 시작될 때 이탈이 한 번에 뛰면 "갑자기", 아니면 "서서히"로 본다
  (`config/diagnosis/default.yaml`의 `special.abrupt_jump_ratio`).
- 스트로크 곡선은 위치가 맞춰진 표를 받는다. 원시 신호에서 스트로크를 잘라 위치를 맞추는 일은 아직 없다.
- 품질 예측 모델은 1차식이다. 학습 때 보지 못한 운전 범위의 표본은 "범위 밖"으로 세어 알린다. 규격은 입력으로 받는다.
- 공정 이름은 `cutting`, `press`, `extrusion`이다. 사출, 슬롯다이, 롤프린팅, 임프린팅, 반송은 아직 없다.

## 점검 안내와 상태 추이 (D5)

```python
from cont.packs.diagnosis import guide, trend
from cont.packs.diagnosis.special import interpret

g = guide(eq)                              # 공통 진단의 변화마다 원인 후보와 확인할 것
g = guide(eq, interpret("cutting", eq))    # 특화 해석이 붙은 변화는 그 공정의 점검 항목으로 바꿔 준다
t = trend(eq)                              # 진단 구간을 토막으로 나눈 계통별 상태 추이
render_equipment(eq, guidance=g, trend=t)
```

- **점검 안내**는 원인을 판정하지 않는다. 후보와 확인할 것을 "먼저 시작된 변화부터, 확인하기 쉬운 것부터" 늘어놓는다. 확률 순서가 아니다.
- 지식표는 `tables/guidance.yaml`(공통)과 `tables/special/<공정>.yaml`의 `checks`(특화)다. **내가 일반적인 설비 지식으로 쓴 출발점이며 현장의 정비 이력으로 검증하지 않았다.** 표만 고치면 바뀐다.
- **상태 추이**는 새 판정이 아니라 공통 진단 결과를 토막별로 다시 센 것이다. 토막 수는 `config/diagnosis/default.yaml`의 `trend.windows`.
  한 번의 진단 구간 안에서의 추이다. 날마다의 진단을 쌓아 보는 장기 추이는 결과를 저장하는 곳이 정해진 뒤에 한다.
- 현장 설정 파일에 `special: cutting`처럼 공정을 적으면 화면과 진단 서버가 공정 해석과 그 공정의 점검 항목까지 보여 준다.
- 묻고 답하기는 "왜", "무엇을 점검" 같은 질문에 질문이 가리킨 계통·신호의 점검 항목을 붙여 답한다.

## 계산 방법

1. **정상 기준**: 신호를 운전조건의 1차식으로 맞추고, 남은 차이를 조건 구간별 중앙값과 산포(MAD)로 잡는다.
   부하나 속도가 바뀌어 신호가 움직이는 것은 이상이 아니다.
2. **이탈 검출**: 표본마다 같은 조건의 정상 기준과의 차이를 정상 산포의 배수로 나타내고,
   기준을 넘어 일정 길이 이상 이어진 구간을 이상 구간으로 본다.
3. **상태 변화 유형**: 어느 역할의 신호가 어느 방향으로 벗어났는지로 일반적인 이름을 붙인다.

기준값(`z_limit`, `min_run` 등)은 `config/diagnosis/default.yaml`에 있고 `CONT_DIAGNOSIS_PROFILE`로 현장별 설정을 고른다.

## 지금의 한계

- 가상 신호로 계산이 맞는지만 확인했다. 현장 데이터로 검증하지 않았고, 답변 묶음의 신뢰도는 "낮음"이다.
- 운전조건과 신호의 관계가 크게 굽어 있거나 운전 모드가 여러 개인 설비는 조건 구간 보정만으로 부족할 수 있다.
- 기동·정지, 설정값을 급하게 바꾼 직후 같은 과도 구간을 따로 다루지 않는다. 열관리계처럼 응답이 느린 계통에서는 이 구간이 이상으로 잡힐 수 있다.
- 계통 사이의 관계(예: 유량 감소와 구동부 전류 상승이 함께 나타남)는 아직 묶어 해석하지 않는다. 계통마다 따로 본다.
- 서서히 커지는 변화는 기준을 넘나드는 초입에서 이상 구간이 여러 개로 나뉘어 잡힐 수 있다.
- 주파수 분석(베어링 결함 주파수 등)은 아직 없다. 지금은 크기 신호만 본다.
- 묻고 답하기는 공통 진단 결과와 점검 안내를 다룬다. 스트로크 곡선과 품질 예측 결과에 대해 묻는 것은 아직 없다.
- 진단 결과를 저장하지 않는다. 그래서 어제와 오늘을 비교하는 장기 추이, 점검 결과를 되돌려 받아 지식표를 고치는 일은 아직 없다.
