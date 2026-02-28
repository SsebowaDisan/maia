from api.services.agent.eval_suite import run_agent_eval_suite


def test_agent_eval_suite_meets_threshold_gates() -> None:
    report = run_agent_eval_suite()
    gates = report.get("gates") or {}
    assert bool(gates.get("overall_pass_rate"))
    assert bool(gates.get("ambiguity"))
    assert bool(gates.get("multi_intent"))
    assert bool(gates.get("delivery_completeness"))
    assert bool(gates.get("contradiction_risk"))
    assert bool(gates.get("fixtures_synced"))
    assert report.get("case_count") >= 5
