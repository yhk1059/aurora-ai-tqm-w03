"""AI 단발 호출 4종. 네트워크를 쓰지 않는다: 호출은 주입한 가짜 client로 대신한다."""

import json
from types import SimpleNamespace

import pytest

from backend.ai import client as ai_client
from backend.ai import tasks
from backend.core import db, ontology, scenario

BATCHES = ["B-02-2602-01", "B-02-2603-01"]

GOOD = {
    "agenda_summary": {"headline": "요약", "key_points": ["쟁점"],
                       "options": [{"option": "전면 회수", "impact_points": ["a"]},
                                   {"option": "부분 회수", "impact_points": ["b"]},
                                   {"option": "조사계속", "impact_points": ["c"]}],
                       "uncertainties": ["C-105 출하처 미확인"],
                       "evidence": [{"source": "원본", "text": "기준 10% — quality_policy_cv"}]},
    "review_explanation": {"explanation": "보도는 판정 근거가 아니다. 상태 변화 없음.", "conclusion": "유지"},
    "notice_draft": {"draft": "안내문", "recipients": ["C-101"]},
}


class FakeClient:
    """messages.create(**kwargs)만 흉내 낸다. 받은 요청을 calls에 남긴다."""

    def __init__(self, payload=None, stop_reason="end_turn", exc=None):
        self.payload, self.stop_reason, self.exc, self.calls = payload, stop_reason, exc, []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        text = json.dumps(self.payload, ensure_ascii=False) if self.payload is not None else ""
        return SimpleNamespace(stop_reason=self.stop_reason, stop_details=None,
                               content=[SimpleNamespace(type="text", text=text)])


def _snapshot(conn):
    return {t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t}").fetchall()]
            for t in ("objects", "links", "action_log")}


@pytest.fixture
def no_key(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(ai_client, "ENV_PATH", tmp_path / ".env")


@pytest.fixture
def opened(conn):
    """시연 1-2 시점(사건 열림, 상신 전 — 안건 요약을 만드는 때)."""
    scenario.run_scenario(conn, "demo1", upto="1-1")
    return conn


@pytest.fixture
def recalled(conn):
    """시연 1-5까지 (회수진행, 안내 대상 결정됨, 수주 급감 확인 작업 열림)."""
    scenario.run_scenario(conn, "demo1", upto="1-5")
    return conn


def _task_id(conn, type_):
    return next(t["id"] for t in db.list_objects(conn, "task") if t["attrs"]["type"] == type_ and t["state"] == "열림")


def _allowed(req):
    return req["schema"]["properties"]["result"]["enum"]


# --- 키 없음 ---

def test_no_key(no_key, recalled):
    assert ai_client.is_available() is False
    params = {"agenda_summary": {"batch_ids": BATCHES},
              "classify_reply": {"task_id": _task_id(recalled, "수주 급감 확인"), "reply_text": "순서 유지"},
              "review_explanation": {}, "notice_draft": {}}
    for task in tasks.TASKS:
        r = tasks.run_task(recalled, task, params[task])
        assert (r.ok, r.error, r.output, r.log_id) == (False, "no_key", None, None)
    assert db.list_ai_log(recalled) == []


def test_key_from_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("ANTHROPIC_API_KEY=test-value\n", encoding="utf-8")
    monkeypatch.setattr(ai_client, "ENV_PATH", env)
    assert ai_client.is_available() is True
    env.write_text("ANTHROPIC_API_KEY=\n", encoding="utf-8")
    assert ai_client.is_available() is False


# --- 회신 분류의 허용 목록 (ontology에서) ---

def test_classify_allowed_shipping(opened):
    req = tasks.build_request(opened, "classify_reply",
                              {"task_id": _task_id(opened, "출하처 확인"), "reply_text": "확인 불가"})
    assert _allowed(req) == ["출하 확인", "영향없음", "확인 불가", ontology.AI_UNINTERPRETABLE]


def test_classify_allowed_order_drop(recalled):
    req = tasks.build_request(recalled, "classify_reply",
                              {"task_id": _task_id(recalled, "수주 급감 확인"), "reply_text": "우선 공급 요청"})
    assert _allowed(req) == ["순서 유지", "우선 공급 요청", "해석 불가"]


def test_classify_no_result_task_rejected(recalled):
    with pytest.raises(ValueError):
        tasks.build_request(recalled, "classify_reply",
                            {"task_id": _task_id(recalled, "재공급 요청"), "reply_text": "x"})


# --- 정상 응답 ---

def test_classify_ok_and_logged(opened):
    tid = _task_id(opened, "출하처 확인")
    reply = "C-105 출하 사실 확인, 수량 기록 없음"
    fake = FakeClient({"result": "출하 확인", "evidence_sentence": "C-105 출하 사실 확인", "note": "수량 기록 없음"})
    before = _snapshot(opened)
    r = tasks.run_task(opened, "classify_reply", {"task_id": tid, "reply_text": reply}, client=fake)
    assert r.ok and r.error is None
    assert set(r.output) == {"result", "evidence_sentence", "note"} and r.output["result"] == "출하 확인"
    assert _snapshot(opened) == before

    call = fake.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert reply in call["messages"][0]["content"]

    (log,) = db.list_ai_log(opened)
    assert log["seq"] == r.log_id and log["task"] == "classify_reply" and log["model"] == "claude-opus-5-5"
    assert log["inputs"]["system"] == call["system"] and reply in log["inputs"]["user"]
    assert log["output"]["ok"] is True and log["output"]["output"] == r.output


@pytest.mark.parametrize("task,params", [
    ("agenda_summary", {"batch_ids": BATCHES}),
    ("review_explanation", {}),
    ("notice_draft", {}),
])
def test_other_tasks_ok(recalled, task, params):
    before = _snapshot(recalled)
    r = tasks.run_task(recalled, task, params, client=FakeClient(GOOD[task]))
    assert r.ok and r.output == GOOD[task] and r.log_id is not None
    assert _snapshot(recalled) == before
    assert db.list_ai_log(recalled)[-1]["task"] == task


def test_notice_recipients_from_sales_decision(recalled):
    req = tasks.build_request(recalled, "notice_draft", {})
    assert req["input"]["recipients"] == ["C-101", "C-102", "C-103", "C-104", "C-108"]
    bad = tasks.run_task(recalled, "notice_draft", {}, client=FakeClient({"draft": "x", "recipients": ["C-999"]}))
    assert bad.error == "invalid_output"


def _agenda_with(**over):
    return {**GOOD["agenda_summary"], **over}


@pytest.mark.parametrize("bad", [
    _agenda_with(options=GOOD["agenda_summary"]["options"][:2]),                      # 대안 하나 빠짐
    _agenda_with(options=GOOD["agenda_summary"]["options"] + [{"option": "전면 회수", "impact_points": []}]),  # 중복
    _agenda_with(headline=" "),
    _agenda_with(key_points=["a"] * 4),
    _agenda_with(uncertainties=["a"] * 5),
    _agenda_with(evidence=[{"source": "원본", "text": "a"}] * 6),
    _agenda_with(options=[{"option": o, "impact_points": ["a"] * 3} for o in ("전면 회수", "부분 회수", "조사계속")]),
])
def test_agenda_output_rejected_when_too_long_or_incomplete(opened, bad):
    """목록 길이 상한은 스키마가 아니라 서버 확인에서 건다. 넘으면 결과로 쓰지 않고 기록만 남긴다."""
    r = tasks.run_task(opened, "agenda_summary", {"batch_ids": BATCHES}, client=FakeClient(bad))
    assert not r.ok and r.error == "invalid_output" and r.output is None and r.log_id is not None


def test_agenda_output_at_limits_ok(opened):
    full = _agenda_with(key_points=["a"] * 3, uncertainties=["a"] * 4,
                        evidence=[{"source": "시스템", "text": "a"}] * 5,
                        options=[{"option": o, "impact_points": ["a", "b"]} for o in ("전면 회수", "부분 회수", "조사계속")])
    assert tasks.run_task(opened, "agenda_summary", {"batch_ids": BATCHES}, client=FakeClient(full)).ok


# --- 비정상 응답 ---

def test_classify_result_outside_list(opened):
    tid = _task_id(opened, "출하처 확인")
    fake = FakeClient({"result": "회수 승인", "evidence_sentence": "", "note": ""})
    r = tasks.run_task(opened, "classify_reply", {"task_id": tid, "reply_text": "아무 말"}, client=fake)
    assert (r.ok, r.error, r.output) == (False, "invalid_output", None)
    assert db.list_ai_log(opened)[-1]["output"]["ok"] is False


@pytest.mark.parametrize("stop,err", [("refusal", "refusal"), ("max_tokens", "max_tokens")])
def test_bad_stop_reason(opened, stop, err):
    fake = FakeClient(GOOD["agenda_summary"], stop_reason=stop)
    r = tasks.run_task(opened, "agenda_summary", {"batch_ids": BATCHES}, client=fake)
    assert (r.ok, r.error, r.output) == (False, err, None)
    (log,) = db.list_ai_log(opened)
    assert log["output"]["received"]["stop_reason"] == stop and log["output"]["output"] is None
    assert "user" in log["inputs"]


def test_exception_becomes_api_error(opened):
    before = _snapshot(opened)
    r = tasks.run_task(opened, "agenda_summary", {"batch_ids": BATCHES}, client=FakeClient(exc=RuntimeError("boom")))
    assert (r.ok, r.error, r.output) == (False, "api_error", None)
    assert _snapshot(opened) == before


# --- 입력 내용 ---

def test_agenda_input_has_judgment_facts(opened):
    user = tasks.build_request(opened, "agenda_summary", {"batch_ids": BATCHES})["user"]
    for s in ("11.9%", "11.6%", "≥ 10%", "미상신 경과일", '"미상신 경과일": 91', '"미상신 경과일": 51', "C-105",
              "확인요청중", "회수 대상", '"150,745"', '"17,900"'):
        assert s in user, s


def test_agenda_input_after_rejection(conn):
    """3-6 재상신 직전: 거절 사유와 그 뒤 조사 회신이 입력에 들어간다."""
    scenario.run_scenario(conn, "demo3b", upto="3-6a")
    prior = tasks.build_request(conn, "agenda_summary", {"batch_ids": BATCHES})["input"]["이전 결정"]
    assert prior["이전 거절 결정"]["사유"]
    assert any(e.get("유형") == "회신" for e in prior["거절 뒤 새 근거"])


def test_review_input_after_news(conn):
    scenario.run_scenario(conn, "demo2", upto="2-1")
    req = tasks.build_request(conn, "review_explanation", {})
    assert "R3" in req["user"] and "상태 변화 없음" in req["user"]
    assert req["input"]["state_changes"] == "상태 변화 없음"
    assert any(k.startswith("보도 원문") for k in req["input"])


def test_review_input_has_no_section_refs(conn):
    """액션 기록의 rule 칸에 있는 문서 절 번호("§4-5")는 AI 입력에 넣지 않는다. 지시문에만 "§"가 한 번 나온다."""
    scenario.run_scenario(conn, "demo2", upto="2-1")
    assert any(c.get("rule") == "§4-5" for a in db.list_action_log(conn) for c in a["changes"])
    req = tasks.build_request(conn, "review_explanation", {})
    assert "§" not in json.dumps(req["input"], ensure_ascii=False)
    assert "R3" in req["user"]


def test_review_input_after_pending_claim(conn):
    scenario.run_scenario(conn, "demo2", upto="2-2a")
    req = tasks.build_request(conn, "review_explanation", {})
    user = req["user"]
    for s in ("R6-2", "R7-1", "확정 시 불량률", "0.5%"):
        assert s in user, s
    assert req["input"]["state_changes"] == [{"배치": "B-02-2602-03", "이전": "관찰해제", "이후": "관찰", "규칙": "R6-2"}]


def test_review_logs_action_seq(conn):
    scenario.run_scenario(conn, "demo2", upto="2-1")
    r = tasks.run_task(conn, "review_explanation", {}, client=FakeClient(GOOD["review_explanation"]))
    human = [a for a in db.list_action_log(conn) if a["action"] == "register_news"][-1]
    assert db.list_ai_log(conn)[-1]["action_seq"] == human["seq"] and r.ok


def test_unknown_task_and_no_incident(conn):
    with pytest.raises(ValueError):
        tasks.run_task(conn, "decide_recall", {}, client=FakeClient({}))
    with pytest.raises(ValueError):
        tasks.run_task(conn, "agenda_summary", {"batch_ids": BATCHES}, client=FakeClient({}))


def test_agenda_input_has_no_release_date_for_over_threshold(opened):
    """기준초과 배치에는 관찰 해제 예정일이 없고, AI 입력에서 키 자체가 빠진다 (null도 넣지 않는다)."""
    req = tasks.build_request(opened, "agenda_summary", {"batch_ids": BATCHES})
    assert "관찰 해제 예정일" not in req["user"] and "해제 기준" not in req["user"]
