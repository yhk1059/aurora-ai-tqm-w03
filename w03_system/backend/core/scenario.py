"""시연 액션 목록 실행: scenarios/*.json의 단계를 순서대로 actions.execute로 실행한다.

기준: brain/3-design/demo-scenarios.md, architecture.md (`POST /scenarios/{name}`, 테스트 전략).
- 상태는 actions.execute로만 바꾼다. DB를 직접 고치지 않는다(시연 출발 상태도 재현 가능한 액션 기록이다).
- [모의] 입력은 scenarios/ 폴더에만 있다. 이 모듈은 파일을 읽어 실행할 뿐이다.

단계 형식: {"id", "action"(null이면 설명만 있는 단계), "actor", "inputs", "source", "note", "setup"(선택)}
실행 중에 ID가 정해지는 대상은 조건으로 가리킨다. 실행 직전에 실제 ID로 바꾼다(정확히 하나여야 한다).
- "task":  {"type", "customer_id"(선택)}           → task_id  (열린 작업 중)
- "claim": {"batch_id"(선택), "customer_id"(선택)} → claim_id (미확정 클레임 중)
- "plan":  {"state"}                                → plan_id  (그 상태인 가장 최근 버전)
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.core import actions, db, rules

SCENARIO_DIR = Path(__file__).resolve().parents[2] / "scenarios"
RESET_ACTOR = "quality_owner"
EXAMPLES_FILE = "reply-examples.json"  # 화면 폼의 모의 입력 예시. 시나리오가 아니다


class ScenarioError(Exception):
    """단계 실행 실패. step_id = 실패한 단계, cause = 원래 예외."""

    def __init__(self, name: str, step_id: str, message: str, cause: Exception | None = None):
        super().__init__(f"[{name} {step_id}] {message}")
        self.name, self.step_id, self.cause = name, step_id, cause


def _path(name: str) -> Path:
    path = (SCENARIO_DIR / f"{name}.json").resolve()
    if path.parent != SCENARIO_DIR.resolve() or path.name == EXAMPLES_FILE or not path.is_file():
        raise ValueError(f"없는 시나리오: {name}")
    return path


def load_scenario(name: str) -> dict:
    with open(_path(name), encoding="utf-8") as f:
        return json.load(f)


def list_scenarios() -> list[dict]:
    out = []
    for p in sorted(SCENARIO_DIR.glob("*.json")):
        if p.name == EXAMPLES_FILE:
            continue
        with open(p, encoding="utf-8") as f:
            s = json.load(f)
        out.append({"name": s["name"], "title": s["title"], "description": s["description"],
                    "step_count": len(s["steps"]),
                    "action_count": sum(1 for st in s["steps"] if st.get("action")),
                    "setup_count": sum(1 for st in s["steps"] if st.get("setup") and st.get("action"))})
    return out


def list_reply_examples() -> list[dict]:
    """화면 입력 폼의 모의 입력 예시(scenarios/reply-examples.json의 examples 그대로)."""
    with open(SCENARIO_DIR / EXAMPLES_FILE, encoding="utf-8") as f:
        return json.load(f)["examples"]


# ---------------------------------------------------------------------------
# 조건 → 실제 ID (읽기만 한다)
# ---------------------------------------------------------------------------


def _one(kind: str, cond: dict, ids: list[str]) -> str:
    if len(ids) != 1:
        raise ValueError(f"{kind} 조건 {cond}에 맞는 대상이 {len(ids)}개다: {ids}")
    return ids[0]


def _find_task(conn, cond: dict) -> str:
    ids = [t["id"] for t in db.list_objects(conn, "task")
           if t["state"] == rules.TASK_OPEN and t["attrs"].get("type") == cond["type"]
           and ("customer_id" not in cond or t["attrs"].get("customer_id") == cond["customer_id"])]
    return _one("작업", cond, ids)


def _find_claim(conn, cond: dict) -> str:
    ids = []
    for c in db.list_objects(conn, "claim"):
        if not rules._is_pending(c):
            continue
        batch = db.find_links(conn, rel="CLAIMED_ON", src=("claim", c["id"]))
        cust = db.find_links(conn, rel="CLAIMED_BY", src=("claim", c["id"]))
        if "batch_id" in cond and (not batch or batch[0]["dst_id"] != cond["batch_id"]):
            continue
        if "customer_id" in cond and (not cust or cust[0]["dst_id"] != cond["customer_id"]):
            continue
        ids.append(c["id"])
    return _one("클레임", cond, ids)


def _find_plan(conn, cond: dict) -> str:
    plans = sorted((p for p in db.list_objects(conn, "resupply_plan") if p["state"] == cond["state"]),
                   key=lambda p: p["attrs"]["version"])
    if not plans:
        raise ValueError(f"계획 조건 {cond}에 맞는 대상이 없다")
    return plans[-1]["id"]


_SELECTORS = {"task": ("task_id", _find_task), "claim": ("claim_id", _find_claim), "plan": ("plan_id", _find_plan)}


def resolve_inputs(conn, inputs: dict) -> dict:
    out = {}
    for k, v in (inputs or {}).items():
        if k in _SELECTORS:
            key, fn = _SELECTORS[k]
            out[key] = fn(conn, v)
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------


def run_scenario(conn, name: str, *, upto: str | None = None, setup_only: bool = False) -> list[dict]:
    """DB를 초기화(reset)한 뒤 단계를 순서대로 actions.execute로 실행한다.
    upto = 이 단계 id까지(포함) 실행. setup_only = setup 단계만 실행.
    단계별 결과(id, action, ActionResult 요약)를 돌려준다. 단계가 실패하면 ScenarioError를 낸다."""
    scenario = load_scenario(name)
    steps = scenario["steps"]
    if upto is not None and upto not in [s["id"] for s in steps]:
        raise ValueError(f"{name}에 없는 단계: {upto}")
    if setup_only:
        steps = [s for s in steps if s.get("setup")]

    actions.execute(conn, "reset", RESET_ACTOR, {})
    results = []
    for step in steps:
        entry = {"id": step["id"], "action": step.get("action"), "actor": step.get("actor"),
                 "source": step.get("source"), "note": step.get("note")}
        if step.get("action"):
            try:
                inputs = resolve_inputs(conn, step.get("inputs") or {})
                res = actions.execute(conn, step["action"], step["actor"], inputs)
            except (actions.ActionError, ValueError, KeyError) as e:
                raise ScenarioError(name, step["id"], str(e), e) from e
            entry.update({"inputs": inputs, "seq": res.seq, "auto_seqs": res.auto_seqs,
                          "change_count": len(res.changes), "created": res.created})
        results.append(entry)
        if step["id"] == upto:
            break
    return results
