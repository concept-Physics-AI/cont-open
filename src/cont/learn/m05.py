"""M05 공통 공정 신호 해석의 기준선 A·B와 같은 시험 (Y4). 합성 신호만 쓴다. torch가 필요 없다.

A: 단계별 통계. 단계마다 응답의 평균·표준편차를 훈련 자료에서 잡고, 샘플을 가장 가까운 단계로 읽는다.
B: 물리 잔차 + 경량 트리. 지령을 알고 1차 지연 물리 모형으로 응답을 예측하고, 남은 잔차와 지령·예측을 입력으로
   작은 트리가 단계를 읽고 잔차를 보정한다.
둘 다 같은 분할(Y3: 로트 단위)과 같은 지표로 잰다. 합성 자료라고 결과에 적는다. 판정은 하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from cont.learn.split import assert_no_leakage, group_split

_CFG = Path(__file__).resolve().parents[3] / "config" / "learn" / "m05.yaml"


def config() -> dict[str, Any]:
    return yaml.safe_load(_CFG.read_text(encoding="utf-8"))


@dataclass
class Run:
    lot: str
    index: int
    cmd: np.ndarray
    resp: np.ndarray
    stage: np.ndarray                 # 정답 단계 번호
    events: list[tuple[int, int]]     # 정답 이상 구간 [시작, 끝)


def lag(cmd: np.ndarray, tau: float) -> np.ndarray:
    """1차 지연: resp[t+1] = resp[t] + (cmd[t] - resp[t]) / tau. 물리 모형이자 합성 신호의 법칙이다."""
    out = np.zeros_like(cmd, dtype=float)
    for t in range(len(cmd) - 1):
        out[t + 1] = out[t] + (cmd[t] - out[t]) / tau
    return out


def synthesize(cfg: dict[str, Any] | None = None) -> list[Run]:
    cfg = cfg or config()
    s = cfg["synthetic"]
    rng = np.random.default_rng(s["seed"])
    stages = s["stages"]
    lvl = s["level"]
    shapes = [np.zeros(stages[0]["length"]), np.linspace(0, lvl, stages[1]["length"]),
              np.full(stages[2]["length"], lvl), np.linspace(lvl, 0, stages[3]["length"])]
    cmd = np.concatenate(shapes)
    stage = np.concatenate([np.full(len(sh), i) for i, sh in enumerate(shapes)])
    hold_a, hold_b = stages[0]["length"] + stages[1]["length"], stages[0]["length"] + stages[1]["length"] + stages[2]["length"]
    runs: list[Run] = []
    for lot in range(s["lots"]):
        gain = 1.0 + rng.uniform(-s["lot_gain_spread"], s["lot_gain_spread"])
        tau = s["tau_nominal"] * (1.0 + rng.uniform(-s["lot_tau_spread"], s["lot_tau_spread"]))
        for k in range(s["runs_per_lot"]):
            resp = gain * lag(cmd, tau) + rng.normal(0.0, s["noise"], len(cmd))
            events: list[tuple[int, int]] = []
            if k == 0:
                a = int(rng.integers(hold_a + 10, hold_b - s["event"]["length"] - 5))
                b = a + s["event"]["length"]
                resp[a:b] += s["event"]["delta"]
                events.append((a, b))
            runs.append(Run(f"L{lot}", k, cmd, resp, stage, events))
    return runs


# ---- 경량 트리 (numpy만) -------------------------------------------------------------------------

class Tree:
    """깊이가 제한된 CART. task는 "class"(지니) 또는 "reg"(분산)."""

    def __init__(self, task: str, max_depth: int, min_leaf: int, thresholds: int):
        self.task, self.max_depth, self.min_leaf, self.nt = task, max_depth, min_leaf, thresholds
        self.node: Any = None

    def _leaf(self, y: np.ndarray) -> Any:
        return float(y.mean()) if self.task == "reg" else int(np.bincount(y).argmax())

    def _cost(self, y: np.ndarray) -> float:
        if self.task == "reg":
            return float(((y - y.mean()) ** 2).sum())
        p = np.bincount(y) / len(y)
        return float(len(y) * (1.0 - (p ** 2).sum()))

    def _build(self, X: np.ndarray, y: np.ndarray, depth: int) -> Any:
        if depth >= self.max_depth or len(y) < 2 * self.min_leaf or self._cost(y) == 0.0:
            return self._leaf(y)
        best = None
        for j in range(X.shape[1]):
            for th in np.unique(np.quantile(X[:, j], np.linspace(0.02, 0.98, self.nt))):
                m = X[:, j] <= th
                if m.sum() < self.min_leaf or (~m).sum() < self.min_leaf:
                    continue
                c = self._cost(y[m]) + self._cost(y[~m])
                if best is None or c < best[0]:
                    best = (c, j, float(th), m)
        if best is None or best[0] >= self._cost(y):
            return self._leaf(y)
        _, j, th, m = best
        return (j, th, self._build(X[m], y[m], depth + 1), self._build(X[~m], y[~m], depth + 1))

    def fit(self, X: np.ndarray, y: np.ndarray) -> "Tree":
        self.node = self._build(X, y.astype(int) if self.task == "class" else y.astype(float), 0)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        def one(x: np.ndarray, n: Any) -> float:
            while isinstance(n, tuple):
                n = n[2] if x[n[0]] <= n[1] else n[3]
            return n
        return np.array([one(x, self.node) for x in X])


# ---- 기준선 -------------------------------------------------------------------------------------

def _stack(runs: list[Run], f) -> np.ndarray:
    return np.concatenate([f(r) for r in runs])


class BaselineA:
    """단계별 통계: 단계마다 (응답 평균, 표준편차)와 응답·지령의 평균. 샘플을 가장 가까운 단계로 읽는다."""

    name = "A 단계별 통계"

    def fit(self, runs: list[Run], cfg: dict[str, Any]) -> "BaselineA":
        st = _stack(runs, lambda r: r.stage)
        resp, cmd = _stack(runs, lambda r: r.resp), _stack(runs, lambda r: r.cmd)
        n = int(st.max()) + 1
        self.mu = np.array([resp[st == i].mean() for i in range(n)])
        self.sd = np.array([max(resp[st == i].std(), 1e-6) for i in range(n)])
        self.cmu = np.array([cmd[st == i].mean() for i in range(n)])
        self.csd = np.array([max(cmd[st == i].std(), 1e-3) for i in range(n)])
        return self

    def stages(self, r: Run) -> np.ndarray:
        d = ((r.resp[:, None] - self.mu) / self.sd) ** 2 + ((r.cmd[:, None] - self.cmu) / self.csd) ** 2
        return d.argmin(axis=1)

    def expected(self, r: Run) -> np.ndarray:
        return self.mu[r.stage]                      # 정답 단계의 평균 (응답 모형 오차를 잰다)

    def deviation(self, r: Run, stg: np.ndarray) -> np.ndarray:
        return (r.resp - self.mu[stg]) / self.sd[stg]


class BaselineB:
    """물리 잔차 + 경량 트리."""

    name = "B 물리 잔차 + 트리"

    def _features(self, r: Run, tau: float) -> tuple[np.ndarray, np.ndarray]:
        p = lag(r.cmd, tau)
        res = r.resp - p
        dcmd = np.diff(r.cmd, prepend=r.cmd[0])
        return np.column_stack([r.cmd, p, r.resp, res, dcmd]), res

    def fit(self, runs: list[Run], cfg: dict[str, Any]) -> "BaselineB":
        self.tau = cfg["synthetic"]["tau_nominal"]
        t = cfg["tree"]
        X = np.vstack([self._features(r, self.tau)[0] for r in runs])
        res = _stack(runs, lambda r: self._features(r, self.tau)[1])
        st = _stack(runs, lambda r: r.stage)
        self.cls = Tree("class", t["max_depth"], t["min_leaf"], t["thresholds"]).fit(X, st)
        # 잔차 보정은 지령·예측만 입력으로 쓴다 (응답과 잔차를 입력에 넣으면 이상까지 따라 배운다)
        self.reg = Tree("reg", t["max_depth"], t["min_leaf"], t["thresholds"]).fit(X[:, [0, 1, 4]], res)
        corrected = res - self.reg.predict(X[:, [0, 1, 4]])
        self.sd = max(float(corrected.std()), 1e-6)
        return self

    def stages(self, r: Run) -> np.ndarray:
        return self.cls.predict(self._features(r, self.tau)[0]).astype(int)

    def expected(self, r: Run) -> np.ndarray:
        X, _ = self._features(r, self.tau)
        return X[:, 1] + self.reg.predict(X[:, [0, 1, 4]])

    def physics_only(self, r: Run) -> np.ndarray:
        return lag(r.cmd, self.tau)

    def deviation(self, r: Run, stg: np.ndarray) -> np.ndarray:
        return (r.resp - self.expected(r)) / self.sd


# ---- 지표 ---------------------------------------------------------------------------------------

def macro_f1(true: np.ndarray, pred: np.ndarray, n: int) -> float:
    f = []
    for c in range(n):
        tp = float(((pred == c) & (true == c)).sum())
        fp = float(((pred == c) & (true != c)).sum())
        fn = float(((pred != c) & (true == c)).sum())
        f.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return float(np.mean(f))


def boundary_errors(true: np.ndarray, pred: np.ndarray, reach: int) -> tuple[list[int], int, int]:
    """정답 경계마다 가장 가까운 예측 경계와의 샘플 차. reach 안에 없으면 놓친 것으로 센다. 예측 경계 수도 돌려준다."""
    tb = np.flatnonzero(np.diff(true) != 0) + 1
    pb = np.flatnonzero(np.diff(pred) != 0) + 1
    errs, missed = [], 0
    for b in tb:
        d = np.abs(pb - b) if len(pb) else np.array([reach + 1])
        if d.min() <= reach:
            errs.append(int(d.min()))
        else:
            missed += 1
    return errs, missed, len(pb)


def alarm_segments(dev: np.ndarray, k: float, min_samples: int) -> list[tuple[int, int]]:
    on = np.abs(dev) > k
    out, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and on[j]:
                j += 1
            if j - i >= min_samples:
                out.append((i, j))
            i = j
        else:
            i += 1
    return out


def _overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def evaluate_model(model: Any, test: list[Run], cfg: dict[str, Any]) -> dict[str, Any]:
    n_stage = len(cfg["synthetic"]["stages"])
    reach = cfg["boundary_match_samples"]
    dt = cfg["synthetic"]["sample_period_s"]
    al = cfg["alarm"]
    true_all, pred_all, berr, missed, spurious = [], [], [], 0, 0
    normal_err, phys_err = [], []
    hit = total_ev = false_alarms = 0
    samples = 0
    for r in test:
        pred = model.stages(r)
        true_all.append(r.stage); pred_all.append(pred)
        e, m, npb = boundary_errors(r.stage, pred, reach)
        berr += e; missed += m; spurious += max(npb - 3, 0)
        if not r.events:
            normal_err.append(model.expected(r) - r.resp)
            if hasattr(model, "physics_only"):
                phys_err.append(model.physics_only(r) - r.resp)
        segs = alarm_segments(model.deviation(r, pred), al["k_sigma"], al["min_samples"])
        for ev in r.events:
            total_ev += 1
            hit += any(_overlap(s, ev) for s in segs)
        false_alarms += sum(1 for s in segs if not any(_overlap(s, ev) for ev in r.events))
        samples += len(r.cmd)
    ne = np.concatenate(normal_err)
    out = {"stage_f1": macro_f1(np.concatenate(true_all), np.concatenate(pred_all), n_stage),
           "boundary_error_s": (float(np.mean(berr)) * dt) if berr else None, "boundaries_missed": missed,
           "spurious_boundaries_per_run": spurious / len(test),
           "normal_response_rmse": float(np.sqrt((ne ** 2).mean())),
           "event_recall": (hit / total_ev) if total_ev else None, "events": total_ev,
           "false_alarms_per_hour": false_alarms / (samples * dt / 3600.0)}
    if phys_err:
        out["physics_only_rmse"] = float(np.sqrt((np.concatenate(phys_err) ** 2).mean()))
    return out


def run_experiment(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """같은 합성 자료, 같은 로트 단위 분할에서 A와 B를 재서 보고한다. 판정은 하지 않는다."""
    cfg = cfg or config()
    runs = synthesize(cfg)
    rows = [{"lot": r.lot, "run": f"{r.lot}-{r.index}"} for r in runs]
    sp = group_split(rows, ["lot"], cfg["split"]["test_fraction"], cfg["split"]["seed"])
    assert_no_leakage(rows, sp)
    train = [runs[i] for i in sp.train if not runs[i].events]       # 훈련은 정상 실행만
    test = [runs[i] for i in sp.test]
    return {"data": "synthetic", "note": ("합성 신호의 결과이며 실제 설비 성능이 아니다. 판정하지 않는다. B는 신호를 만든 법칙(1차 지연)을 물리 모형으로 알고 있어 "
                     "구조적으로 유리하다. 이 차이를 실제 설비에서의 우위로 읽지 않는다. 로트 이득 차이는 B의 트리도 배우지 못한다 (physics_only_rmse와 비교)."),
            "split": {"fingerprint": sp.fingerprint, "train_runs": len(train), "test_runs": len(test),
                      "test_lots": sorted({runs[i].lot for i in sp.test})},
            "A": evaluate_model(BaselineA().fit(train, cfg), test, cfg),
            "B": evaluate_model(BaselineB().fit(train, cfg), test, cfg)}
