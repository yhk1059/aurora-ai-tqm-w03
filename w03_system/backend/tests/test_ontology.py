"""온톨로지 정의의 일관성 확인 (business-model.md §8)."""

import json
import re

from backend.core import ontology as o


def test_counts():
    assert len(o.OBJECT_TYPES) == 11
    assert len(o.RELATIONS) == 17
    assert len([k for k in o.ACTIONS]) == 9
    assert len(o.TASK_TYPES) == 8


def test_action_and_role_keys():
    assert set(o.ACTIONS) == {
        "open_incident", "register_claim", "resolve_claim", "register_news", "submit_agenda",
        "committee_decision", "apply_reply", "plan_decision", "reset",
    }
    assert set(o.ROLES) == {"quality_owner", "quality_committee", "scm"}


def test_relation_endpoints_are_object_types():
    for key, rel in o.RELATIONS.items():
        assert rel["from"] and rel["to"], key
        for t in rel["from"] + rel["to"]:
            assert t in o.OBJECT_TYPES, (key, t)
        for link in rel["to_links"]:
            assert link in o.RELATIONS, (key, link)
        for s in rel["default_source"]:
            assert s in o.SOURCES, (key, s)
    # 확인 수준·수량은 SHIPPED_TO만 쓴다
    assert [k for k, r in o.RELATIONS.items() if r["uses_confirmation"]] == ["SHIPPED_TO"]
    assert [k for k, r in o.RELATIONS.items() if r["uses_quantity"]] == ["SHIPPED_TO"]


def test_state_machines_consistent_and_reachable():
    assert set(o.STATE_MACHINES) == {"batch", "claim", "task", "plan", "shipped_to"}
    for kind, m in o.STATE_MACHINES.items():
        states = set(m["states"])
        assert len(states) == len(m["states"]), kind
        assert set(m["initial"]) <= states, kind
        for t in m["transitions"]:
            assert t["from"] in states and t["to"] in states, (kind, t)
        reached = set(m["initial"])
        frontier = list(reached)
        while frontier:
            s = frontier.pop()
            for t in m["transitions"]:
                if t["from"] == s and t["to"] not in reached:
                    reached.add(t["to"])
                    frontier.append(t["to"])
        assert reached == states, (kind, states - reached)


def test_state_values():
    assert o.STATE_MACHINES["batch"]["states"] == [
        "정상", "관찰", "관찰해제", "기준초과(미상신)", "상신중", "회수진행", "부분회수", "조사계속", "재상신 후보",
    ]
    assert o.STATE_MACHINES["plan"]["states"] == ["초안", "확정", "기각", "대체됨"]
    assert o.STATE_MACHINES["shipped_to"]["states"] == o.CONFIRMATION_LEVELS
    for ot in o.OBJECT_TYPES.values():
        if ot["state"]:
            assert ot["state"]["kind"] in o.STATE_MACHINES
            assert ot["state"]["attribute"] in {a["key"] for a in ot["stored"]}


def test_actions_roles_and_applied_date():
    for key, a in o.ACTIONS.items():
        assert a["roles"], key
        for r in a["roles"]:
            assert r in o.ROLES, (key, r)
        input_keys = [i["key"] for i in a["inputs"]]
        if key == "reset":
            assert set(a["roles"]) == set(o.ROLES)
            continue
        assert "applied_date" in input_keys, key
        ad = next(i for i in a["inputs"] if i["key"] == "applied_date")
        assert ad["required"] and ad["type"] == "date"
        for t in a["creates_tasks"]:
            assert t in o.TASK_TYPES, (key, t)


def test_rule_references_exist():
    refs = []
    for a in o.ACTIONS.values():
        refs += a["rules"]
    for p in o.AUTO_PROCESSES.values():
        refs += p["rules"]
    for ot in o.OBJECT_TYPES.values():
        for d in ot["derived"]:
            refs += d["rules"]
    for tt in o.TASK_TYPES.values():
        refs += tt["rules"]
    for r in refs:
        assert r in o.RULES, r
    for rid, rule in o.RULES.items():
        assert rule["places"] and set(rule["places"]) <= set(o.PLACES), rid


def test_assumption_thresholds_have_refs():
    thresholds = [r["threshold"] for r in o.RULES.values() if r["threshold"]] + [o.TASK_DEADLINE]
    assert thresholds
    for th in thresholds:
        assert th["source"] in o.SOURCES
        if th["source"] == "가정":
            assert re.fullmatch(r"A-\d{2}", th["ref"]), th
    assert o.rule_def("R2")["threshold"]["value"] == 10
    assert o.rule_def("R2")["threshold"]["source"] == "원본"
    assert o.rule_def("R6")["threshold"]["ref"] == "A-07"
    assert o.rule_def("R6-1")["threshold"]["ref"] == "A-12"
    assert o.rule_def("R10")["threshold"]["ref"] == "A-04"
    assert o.rule_def("R10-1")["threshold"]["ref"] == "A-13"
    assert o.rule_def("R10-3")["threshold"]["value"] == 12 and o.rule_def("R10-3")["threshold"]["ref"] == "A-19"
    assert o.TASK_DEADLINE["value"] == 7 and o.TASK_DEADLINE["ref"] == "A-17"


def test_task_types_allowed_results():
    results = {k: [r["result"] for r in v["allowed_results"]] for k, v in o.TASK_TYPES.items()}
    assert results == {
        "출하 경위 확인": ["경위 확인됨", "확인 불가"],
        "출하처 확인": ["출하 확인", "영향없음", "확인 불가"],
        "안내 대상 결정": ["회수 배치 고객만", "관찰·해제 배치 고객 포함"],
        "재공급 요청": [],
        "수주 급감 확인": ["순서 유지", "우선 공급 요청"],
        "원인 조사": ["원인 확인", "원인 미확인"],
        "능력 확보 검토": ["확보 방안 있음", "확보 방안 없음", "확인 불가"],
        "결과 통보": ["확인함"],
    }
    for name, tt in o.TASK_TYPES.items():
        assert tt["departments"] and set(tt["departments"]) <= set(o.DEPARTMENTS), name
        assert o.AI_UNINTERPRETABLE not in results[name]


def test_can_transition():
    assert o.can_transition("batch", "관찰해제", "관찰") is True
    assert o.can_transition("batch", "회수진행", "관찰") is False
    assert o.can_transition("batch", "정상", "기준초과(미상신)") is True
    assert o.can_transition("plan", "확정", "초안") is False
    assert o.can_transition("unknown", "a", "b") is False


def test_lookup_functions():
    assert o.action_def("committee_decision")["roles"] == ["quality_committee"]
    assert o.action_def("nope") is None
    assert o.task_type_def("출하처 확인")["code"] == "T-02"
    assert o.task_type_def("nope") is None
    assert o.rule_def("R12")["places"] == ["권한 원칙"]
    assert o.rule_def("R99") is None


def test_to_dict_serializable():
    d = o.to_dict()
    text = json.dumps(d, ensure_ascii=False)
    assert "기준초과(미상신)" in text
    d["actions"].clear()  # 복사본이라 원본 정의는 바뀌지 않는다
    assert len(o.ACTIONS) == 9
