# 체결 기준 사례 적는 법

```yaml
cases:
  - name: 사례 이름
    source: "문서 이름, 판, 예제 번호, 쪽"     # 반드시 적는다. 없으면 거부된다
    joint: {size: M10, property_class: "10.9", plate_head: {thickness: 15, youngs_modulus: 205000}, plate_nut: {...}, outer_diameter: 40}
    load: {tightening_torque: 50, friction_thread: 0.12, friction_head: 0.12}
    expected:
      preload: {value: 30500, tolerance: torque_to_preload}     # 물리량 이름: 기준값과, 어느 허용 오차 항목으로 견줄지
      plate_resilience: {value: 6.5e-7, tolerance: stiffness_vs_formula}
```

- `expected`의 이름은 체결 답변 묶음의 물리량 이름(`preload`, `load_factor`, `safety_yield` ...)이다.
- `tolerance`는 `config/tolerances/default.yaml`의 항목 이름이다. 기본 프로파일은 한계가 없어 **편차만 보고하고 판정하지 않는다.**
- 값은 원문에서 옮겨 적고 단위를 이 저장소의 단위(mm, N, MPa, N·m)로 맞춘다. 맞추면서 바꾼 것이 있으면 `note`에 적는다.
