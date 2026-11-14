"""AI 단발 호출 4종: 입력 구성 → 호출 → 결과 정리 → ai_log 기록.

기준: brain/3-design/business-model.md §6(AI가 하는 일 4가지), §8-5, R3, R12, architecture.md "AI 호출".
- 입력은 사건 뷰(core.view)와 rules.py 결과에서 뽑는다. 원본 CSV를 통째로 넘기지 않는다.
- 이 모듈은 액션을 실행하지 않는다. DB 쓰기는 db.append_ai_log 하나뿐이고 그 기록만 커밋한다.
- 키가 없으면 호출하지 않고 기록도 남기지 않는다. 가짜 응답을 만들지 않는다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from backend.ai import client as ai_client
from backend.ai import prompts
from backend.core import db, loader, ontology, rules, view

MODEL = ai_client.MODEL
TASKS = ("agenda_summary", "classify_reply", "review_explanation", "notice_draft")

POLICY_DOC = "01_corevia/quality/quality_policy_cv.md"
RECALL_STATES = ["회수진행", "부분회수"]
PENDING_LEVELS = ["미확인", "확인요청중"]
NOTICE_TASK = "안내 대상 결정"


@dataclass
class AiResult:
    ok: bool
    task: str
    output: dict | None       # task별 형식
    log_id: int | None        # ai_log 순번
    error: str | None         # 'no_key' | 'refusal' | 'max_tokens' | 'api_error' | 'invalid_output'
    message: str | None       # 사람이 읽는 한국어 설명


# ---------------------------------------------------------------------------
# 공용
# ---------------------------------------------------------------------------


def _pct(x) -> str | None:
    return None if x is None else f"{x * 100:.1f}%"


def _qty(n) -> str | None:
    """수량은 천 단위 쉼표를 넣어 넘긴다. 모델이 옮겨 적을 때 화면 표기와 같아진다."""
    return None if n is None else f"{n:,}"


def _str_schema(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or list(props),
            "additionalProperties": False}


_STR = {"type": "string"}
_STR_LIST = {"type": "array", "items": _STR}


def _view(conn) -> dict:
    v = view.incident_view(conn)
    if v["incident"] is None:
        raise ValueError("열린 사건이 없다")
    return v


def _threshold_text(rule_id: str) -> dict | None:
    r = ontology.rule_def(rule_id)
    if r is None:
        return None
    out = {"규칙": rule_id, "내용": r["summary"]}
    if r.get("threshold"):
        out["기준값"] = r["threshold"]
    return out


def _batch_facts(vb: dict) -> dict:
    m = vb["metrics"]
    facts = {
        "배치": vb["id"], "제품": vb["attrs"].get("product"), "생산일": vb["attrs"].get("produced_date"),
        "QC 결과": vb["attrs"].get("qc_result"), "판정 상태": vb["state"],
        "사건에 묶인 이유": vb["part_of"]["reason"],
        "생산 수량(EA)": _qty(m["produced_qty"]), "확정 불량 수량(EA)": _qty(m["confirmed_qty"]),
        "불량률(생산 기준, R1)": _pct(m["defect_rate"]),
        "불량률(출하 기준, 참고)": _pct(m["defect_rate_shipped"]),
        "회수 기준(R2)": f"≥ {m['threshold']['value']}{m['threshold']['unit']} [{m['threshold']['source']}]",
        "기준 초과 여부": m["over_threshold"],
        "기준 초과일": m["threshold_crossed_date"],
        "미상신 경과일": m["days_unsubmitted"],
        "미확정 클레임 수량(EA)": _qty(m["pending_qty"]),
        "확정 시 불량률(R7-1, 참고)": _pct(m["rate_if_confirmed"]),
        "경고": [f"[{w['rule']}] {w['message']}" for w in vb["warnings"]],
        "출처": "판정 상태 [시스템], 수치 [도출: 원본 클레임·생산 기록]",
    }
    # 값이 없으면 키 자체를 뺀다. null도 모델이 "해제 예정일 미정"으로 읽고 요약에 쓴다.
    if m["release_due_date"] is not None:
        facts["관찰 해제 예정일"] = m["release_due_date"]
    if m["release_basis"] is not None:
        facts["해제 기준"] = m["release_basis"]
    return facts


def _unconfirmed(v: dict, batch_ids=None) -> list[dict]:
    out = []
    for l in v["network"]["shipped_to"]:
        if l["confirm"] in PENDING_LEVELS and (batch_ids is None or l["src"]["id"] in batch_ids):
            out.append({"배치": l["src"]["id"], "고객": l["dst"]["id"], "확인 수준": l["confirm"],
                        "클레임 건수": l["claims"]["count"], "클레임 수량(EA)": _qty(l["claims"]["qty"]),
                        "설명": "클레임은 있으나 출하 기록(SBL)에 없음 → 출하처 미확인 (R8)"})
    return out


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------------------
# task별 입력 구성 + 출력 확인
# ---------------------------------------------------------------------------


def _agenda_input(conn, params: dict) -> dict:
    v = _view(conn)
    ids = params.get("batch_ids")
    if not ids or not isinstance(ids, list):
        raise ValueError("batch_ids가 필요하다")
    by_id = {b["id"]: b for b in v["batches"]}
    missing = [b for b in ids if b not in by_id]
    if missing:
        raise ValueError(f"사건에 묶이지 않은 배치: {missing}")

    rejections = [d for d in v["decisions"] if d["type"] == "회수 범위" and d["result"] == "거절"
                  and any(t["type"] == "batch" and t["id"] in ids for t in d["targets"])]
    prior = None
    if rejections:
        last = rejections[-1]
        since = last["applied_date"]
        prior = {
            "이전 거절 결정": {"결정": last["id"], "적용일": since, "사유": last["reason"], "출처": last["source"]},
            "거절 뒤 새 근거": [
                {"이벤트": e["id"], "유형": e["type"], "적용일": e["applied_date"], "내용": e["content"],
                 "회신한 작업": e["answers"], "출처": e["source"]}
                for e in v["events"] if (e["applied_date"] or "") >= since
            ] + [
                {"클레임": c["id"], "배치": c["batch_id"], "고객": c["customer_id"], "상태": c["state"],
                 "수량(EA)": _qty(c["attrs"]["qty"]), "접수일": c["attrs"].get("received_date"), "출처": c["source"]}
                for c in v["claims"] if c["batch_id"] in ids and c["source"] == "모의"
                and (c["attrs"].get("received_date") or "") >= since
            ],
        }

    return {
        "사건": {"ID": v["incident"]["id"], "현재 적용일": v["incident"]["current_date"],
               "기점 로트": v["incident"]["origin_lots"], "사건 상태": v["incident"]["status"]},
        "안건 대상 배치": [_batch_facts(by_id[b]) for b in ids],
        "같은 사건의 다른 배치": [{"배치": b["id"], "판정 상태": b["state"], "QC 결과": b["attrs"].get("qc_result"),
                           "불량률(생산 기준)": _pct(b["metrics"]["defect_rate"])}
                          for b in v["batches"] if b["id"] not in ids],
        "출하처 미확인 고객": _unconfirmed(v, ids),
        "회수·재공급 보류 고객": v["held_customers"],
        "적용 규칙": [x for x in (_threshold_text(r) for r in ("R1", "R2", "R8", "R9", "R12")) if x],
        "정책 원문 [원본: quality/quality_policy_cv.md]": loader.read_text_source(POLICY_DOC),
        "이전 결정": prior,
        "원인 조사 상태": "미확인 (원인 조사 회신 없음)" if prior is None else "이전 결정 참조",
    }


_AGENDA_OPTIONS = ["전면 회수", "부분 회수", "조사계속"]
# 목록 길이 상한. 구조화 출력 스키마는 배열 길이 제한을 지원하지 않아 _check_agenda에서 확인한다.
# 배치별 수치는 화면이 시스템 값으로 따로 보이므로(AiDraft.tsx), AI 글은 짧게 묶는다.
_AGENDA_LIMITS = {"key_points": 3, "uncertainties": 4, "evidence": 5}
_AGENDA_IMPACT_LIMIT = 2

_AGENDA_SCHEMA = _str_schema({
    "headline": _STR,
    "key_points": _STR_LIST,
    "options": {"type": "array", "items": _str_schema({"option": {"type": "string", "enum": _AGENDA_OPTIONS},
                                                       "impact_points": _STR_LIST})},
    "uncertainties": _STR_LIST,
    "evidence": {"type": "array", "items": _str_schema({"source": {"type": "string", "enum": ontology.SOURCES},
                                                        "text": _STR})},
})


def _check_agenda(data: dict, inp: dict) -> str | None:
    options = data.get("options", [])
    if sorted(o.get("option") for o in options) != sorted(_AGENDA_OPTIONS):
        return "대안 세 가지(전면 회수 / 부분 회수 / 조사계속)가 한 번씩 있어야 한다"
    if not str(data.get("headline") or "").strip():
        return "headline이 비어 있다"
    for key, limit in _AGENDA_LIMITS.items():
        if len(data.get(key, [])) > limit:
            return f"{key}는 최대 {limit}개다 (받은 것 {len(data[key])}개)"
    for o in options:
        if len(o.get("impact_points", [])) > _AGENDA_IMPACT_LIMIT:
            return f"대안별 영향은 최대 {_AGENDA_IMPACT_LIMIT}개다 ({o['option']}: {len(o['impact_points'])}개)"
    return None


def _classify_allowed(task_type: str) -> list[str]:
    tdef = ontology.task_type_def(task_type)
    allowed = [r["result"] for r in tdef["allowed_results"]]
    return allowed + [ontology.AI_UNINTERPRETABLE] if allowed else []


def _classify_input(conn, params: dict) -> dict:
    v = _view(conn)
    tid, text = params.get("task_id"), params.get("reply_text")
    if not tid or not text or not str(text).strip():
        raise ValueError("task_id와 reply_text가 필요하다")
    task = next((t for t in v["tasks"] if t["id"] == tid), None)
    if task is None:
        raise ValueError(f"작업 없음: {tid}")
    allowed = _classify_allowed(task["type"])
    if not allowed:
        raise ValueError(f"회신 결과가 없는 작업 유형: {task['type']}")
    tdef = ontology.task_type_def(task["type"])
    return {
        "작업": {"ID": task["id"], "유형": task["type"], "코드": task["code"], "담당 부서": task["department"],
               "상태": task["state"], "기한": task["due_date"], "대상": task["targets"]},
        "허용 결과": [{"결과": r["result"], "효과": r["effect"]} for r in tdef["allowed_results"]]
                 + [{"결과": ontology.AI_UNINTERPRETABLE, "효과": "담당자가 직접 확인"}],
        "회신 원문": text,
    }


def _classify_schema(inp: dict) -> dict:
    allowed = [r["결과"] for r in inp["허용 결과"]]
    return _str_schema({"result": {"type": "string", "enum": allowed},
                        "evidence_sentence": _STR, "note": _STR})


def _check_classify(data: dict, inp: dict) -> str | None:
    allowed = [r["결과"] for r in inp["허용 결과"]]
    if data.get("result") not in allowed:
        return f"허용 결과 목록에 없는 값: {data.get('result')!r}"
    return None


def _action_name(key: str) -> str:
    """액션 키 → 화면 이름 (자동 처리는 이미 한글 이름이다)."""
    return (ontology.action_def(key) or {}).get("name", key)


def _actor_name(key: str) -> str:
    return ontology.ROLES.get(key, {}).get("name", key)


def _known_rule(rid) -> str | None:
    """규칙 정의에 있는 번호만 남긴다. 액션 기록의 rule 칸에는 문서 절 번호("§4-5")도 들어 있는데,
    AI 입력에 넣으면 설명에 그대로 옮겨 적는다."""
    return rid if rid and ontology.rule_def(rid) else None


def _change_for_ai(c: dict) -> dict:
    return c if _known_rule(c.get("rule")) else {k: v for k, v in c.items() if k != "rule"}


def _review_input(conn, params: dict) -> dict:
    v = _view(conn)
    lc = v["last_change"]
    if lc is None or lc["action"] == "reset":
        raise ValueError("설명할 최근 액션이 없다")
    log = {r["seq"]: r for r in v["log"]["actions"]}
    cause = log[lc["seq"]]["cause"] or {}

    rule_ids = list(cause.get("rules") or [])
    for s in lc["steps"]:
        for rid in [s.get("rule")] + [c.get("rule") for c in s["changes"]]:
            if rid and rid not in rule_ids:
                rule_ids.append(rid)
    rule_ids = [r for r in rule_ids if ontology.rule_def(r)]

    state_changes = [{"배치": c["target"]["id"], "이전": c["before"], "이후": c["after"], "규칙": c["rule"]}
                     for c in lc["changes"] if c["target"].get("type") == "batch" and c["field"] == "state"]
    touched = {c["배치"] for c in state_changes}
    if lc["inputs"].get("batch_id"):
        touched.add(lc["inputs"]["batch_id"])
    claim_id = lc["inputs"].get("claim_id") or cause.get("claim")
    if claim_id:
        cl = next((c for c in v["claims"] if c["id"] == claim_id), None)
        if cl and cl["batch_id"]:
            touched.add(cl["batch_id"])
    by_id = {b["id"]: b for b in v["batches"]}

    inp = {
        "들어온 입력": {"액션": _action_name(lc["action"]), "실행자": _actor_name(lc["actor"]),
                   "적용일": lc["applied_date"], "입력값": lc["inputs"]},
        "처리 단계": [{"순번": s["seq"], "처리": _action_name(s["action"]), "실행자": _actor_name(s["actor"]),
                   "규칙": _known_rule(s["rule"]), "이유": s["reason"],
                   "변경": [_change_for_ai(c) for c in s["changes"]]} for s in lc["steps"]],
        "적용 규칙": [_threshold_text(r) for r in rule_ids],
        "state_changes": state_changes or "상태 변화 없음",
        "관련 배치 현재 값": [_batch_facts(by_id[b]) for b in sorted(touched) if b in by_id],
        "현재 배치 판정 상태": {b["id"]: b["state"] for b in v["batches"]},
    }
    if cause.get("review"):
        inp["재검토 기록"] = cause["review"]
    ref = lc["inputs"].get("source_ref")
    if lc["action"] == "register_news" and ref:
        inp[f"보도 원문 [원본: {ref}]"] = loader.read_text_source(ref)
    return inp


_REVIEW_SCHEMA = _str_schema({"explanation": _STR, "conclusion": {"type": "string", "enum": ["유지", "변경"]}})


def _check_review(data: dict, inp: dict) -> str | None:
    return None if data.get("conclusion") in ("유지", "변경") else "conclusion은 유지 또는 변경이어야 한다"


def _notice_input(conn, params: dict) -> dict:
    v = _view(conn)
    recall = [b for b in v["batches"] if b["state"] in RECALL_STATES]
    if not recall:
        raise ValueError("회수 대상 배치가 없다")
    rids = {b["id"] for b in recall}
    notice = next((t for t in reversed(v["tasks"]) if t["type"] == NOTICE_TASK
                   and t["attrs"].get("notice_customers")), None)
    if notice:
        recipients, basis = list(notice["attrs"]["notice_customers"]), f"영업 결정 ({notice['id']}: {notice['result']})"
    else:
        recipients = [q["customer_id"] for q in v["recall_quantities"]]
        basis = "후보 (영업이 안내 대상을 아직 정하지 않음, R9-1)"
    decisions = [{"결정": d["id"], "결과": d["result"], "적용일": d["applied_date"],
                  "배치": [t["id"] for t in d["targets"] if t["id"] in rids]}
                 for d in v["decisions"] if d["type"] == "회수 범위" and d["result"] != "거절"
                 and any(t["id"] in rids for t in d["targets"])]
    return {
        "회수 배치": [{"배치": b["id"], "제품": b["attrs"].get("product"), "판정 상태": b["state"]} for b in recall],
        "회수 결정": decisions,
        "recipients": recipients,
        "안내 대상 근거": basis,
        "원인": "미확인 (원인 조사는 회수와 별도 트랙)",
    }


_NOTICE_SCHEMA = _str_schema({"draft": _STR, "recipients": _STR_LIST})


def _check_notice(data: dict, inp: dict) -> str | None:
    extra = [r for r in data.get("recipients", []) if r not in inp["recipients"]]
    return f"입력에 없는 수신 고객: {extra}" if extra else None


_SPECS = {
    "agenda_summary": (prompts.AGENDA_SUMMARY, _agenda_input, lambda inp: _AGENDA_SCHEMA, _check_agenda),
    "classify_reply": (prompts.CLASSIFY_REPLY, _classify_input, _classify_schema, _check_classify),
    "review_explanation": (prompts.REVIEW_EXPLANATION, _review_input, lambda inp: _REVIEW_SCHEMA, _check_review),
    "notice_draft": (prompts.NOTICE_DRAFT, _notice_input, lambda inp: _NOTICE_SCHEMA, _check_notice),
}


def build_request(conn, task: str, params: dict) -> dict:
    """AI에 보낼 요청(system, user, schema)과 구조화된 입력. 호출하지 않는다. 읽기만 한다."""
    if task not in _SPECS:
        raise ValueError(f"정의되지 않은 AI task: {task}")
    instruction, build, schema_of, _ = _SPECS[task]
    inp = build(conn, params or {})
    user = f"{instruction}\n\n입력:\n```json\n{_dump(inp)}\n```"
    return {"system": prompts.SYSTEM, "user": user, "schema": schema_of(inp), "input": inp}


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------


def run_task(conn, task: str, params: dict, *, client=None) -> AiResult:
    """task = 'agenda_summary' | 'classify_reply' | 'review_explanation' | 'notice_draft'.
    client를 넘기면 그것으로 호출한다 (테스트용 주입). 없으면 실제 SDK 클라이언트를 만든다.
    params가 잘못됐거나 사건 상태가 맞지 않으면 ValueError."""
    if task not in _SPECS:
        raise ValueError(f"정의되지 않은 AI task: {task}")
    if client is None and not ai_client.is_available():
        return AiResult(False, task, None, None, "no_key", "API 키가 없어 AI를 호출하지 않았다 (ANTHROPIC_API_KEY)")

    req = build_request(conn, task, params)
    if client is None:
        client = ai_client.make_client()
    res = ai_client.call(client, system=req["system"], user=req["user"], schema=req["schema"])

    error, message, output = res.error, res.message, None
    if error is None:
        problem = _SPECS[task][3](res.data, req["input"])
        if problem:
            error, message = "invalid_output", problem
        else:
            output = res.data

    action_seq = None
    if task == "review_explanation":  # 설명한 사람 액션 기록과 잇는다
        action_seq = view.incident_view(conn)["last_change"]["seq"]
    log_id = db.append_ai_log(
        conn, task=task, model=MODEL,
        inputs={"params": params, "system": req["system"], "user": req["user"], "schema": req["schema"]},
        output={"ok": error is None, "received": res.received, "output": output,
                "error": error, "message": message},
        action_seq=action_seq,
    )
    conn.commit()
    return AiResult(error is None, task, output, log_id, error, message)
