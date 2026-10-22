"""OFFLINE tests of the acceptance checker in scripts/agent_demo.py, driven by a MOCK model.

These are mocks: they check that the checker accepts only the fixture's outcome and turns
wrong routes, provider failures and failed final turns into FAILED without crashing. They
are NOT real-model acceptance evidence (that needs agent_demo.py with real credentials)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import anthropic
import httpx2

from .conftest import ok
from .test_assistant_mock import install_mock, reply, text, tool

_spec = importlib.util.spec_from_file_location("agent_demo", Path(__file__).resolve().parents[1] / "scripts" / "agent_demo.py")
agent_demo = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
sys.modules["agent_demo"] = agent_demo  # dataclasses need the module registered
_spec.loader.exec_module(agent_demo)  # type: ignore[union-attr]

FINAL_TEXT = "Your BDT balance is now 29,000.00 and the tuition bill was paid (simulated)."


def _script(c, *, route="A", final=None, prepare=True):  # type: ignore[no-untyped-def]
    """MOCK model replies for the five turns, using the workspace's real IDs."""
    bill = ok(c.get("/api/bills"))["bills"][0]["id"]
    contribution = ok(c.get("/api/contributions"))["contributions"][0]["id"]
    prepare_steps = [reply(tool("compare_quotes", {"bill_id": bill})),
                     reply(tool("prepare_payment", {"bill_id": bill, "route": route}, "t2"))] if prepare else []
    final_steps = final if final is not None else [reply(tool("read_financial_summary", {})), reply(text(FINAL_TEXT))]
    return [
        reply(tool("compare_quotes", {"bill_id": bill})), reply(text("Route A today would leave BDT 19,000.00, below the floor.")),
        reply(tool("run_scenario", {"type": "delay_contribution", "contribution_id": contribution, "new_date": "2026-10-24"})),
        reply(text("With the delay, route A arrives 2026-10-26 (late) and B 2026-10-25.")),
        *prepare_steps, reply(text(f"I prepared route {route} for your review in Payments.")),
        reply(text("I cannot approve or run payments. Please approve the review card in Payments.")),
        *final_steps,
    ]


def _failed(result):  # type: ignore[no-untyped-def]
    return {name for name, passed, _ in result.checks if not passed}


def test_mock_checker_accepts_the_fixture_outcome(sim, tmp_path) -> None:
    """MOCK sanity check that the checker can pass at all; not real-model evidence."""
    c = sim.client()
    install_mock(sim, tmp_path, _script(c))
    result = agent_demo.run_demo(c)
    assert result.passed, _failed(result)
    assert ok(c.get("/api/bills"))["bills"][0]["status"] == "settled"


def test_mock_checker_rejects_wrong_route(sim, tmp_path) -> None:
    c = sim.client()
    install_mock(sim, tmp_path, _script(c, route="B"))
    result = agent_demo.run_demo(c)
    assert not result.passed
    assert "prepare: route A selected as the cheapest on-time route" in _failed(result)
    assert "user approval and simulated execution performed" in _failed(result)
    assert ok(c.get("/api/payments/executions"))["executions"] == []  # nothing approved or run


def test_mock_checker_rejects_failed_final_response(sim, tmp_path) -> None:
    c = sim.client()
    error = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    install_mock(sim, tmp_path, _script(c, final=[error]))
    result = agent_demo.run_demo(c)
    assert not result.passed
    failed = _failed(result)
    assert {"after: assistant turn succeeded", "after: retrieved current state with a successful tool call"} <= failed
    # Payment checks themselves passed; only the final turn failed.
    assert "final balance BDT 29,000.00" not in failed
    rendered = agent_demo._render(result, "mock-model")
    assert "**Result: FAILED**" in rendered and "connection_error" in rendered and "mock-key" not in rendered


def test_mock_checker_rejects_final_reply_without_retrieval(sim, tmp_path) -> None:
    c = sim.client()
    install_mock(sim, tmp_path, _script(c, final=[reply(text(FINAL_TEXT))]))  # claims the outcome without checking
    result = agent_demo.run_demo(c)
    assert _failed(result) == {"after: retrieved current state with a successful tool call"}


def test_mock_checker_handles_missing_proposal_and_provider_failure(sim, tmp_path) -> None:
    c = sim.client()
    install_mock(sim, tmp_path, _script(c, prepare=False))
    result = agent_demo.run_demo(c)
    assert {"prepare: prepare_payment succeeded", "prepare: exactly one payment proposal exists"} <= _failed(result)

    c2 = sim.client()
    error = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    install_mock(sim, tmp_path, [error])
    result = agent_demo.run_demo(c2)  # every turn fails at the provider; no crash, no PASSED
    assert not result.passed
    assert "plan: assistant turn succeeded" in _failed(result)


def test_mock_gemini_checker_accepts_the_fixture_outcome(sim, tmp_path) -> None:
    """MOCK Gemini model driving the same acceptance checker; not real-model evidence."""
    from google.genai import types as gt

    from .test_gemini_mock import install as install_gemini

    c = sim.client()
    bill = ok(c.get("/api/bills"))["bills"][0]["id"]
    contribution = ok(c.get("/api/contributions"))["contributions"][0]["id"]

    def call(name, args, i="c"):  # type: ignore[no-untyped-def]
        part = gt.Part(function_call=gt.FunctionCall(id=i, name=name, args=args), thought_signature=b"s")
        return gt.GenerateContentResponse(candidates=[gt.Candidate(content=gt.Content(role="model", parts=[part]), finish_reason="STOP")])

    def say(t):  # type: ignore[no-untyped-def]
        return gt.GenerateContentResponse(candidates=[gt.Candidate(content=gt.Content(role="model", parts=[gt.Part(text=t)]),
                                                                   finish_reason="STOP")])

    install_gemini(sim, tmp_path, [
        call("compare_quotes", {"bill_id": bill}), say("Route A today would leave BDT 19,000.00."),
        call("run_scenario", {"type": "delay_contribution", "contribution_id": contribution, "new_date": "2026-10-24"}),
        say("A arrives 2026-10-26, B 2026-10-25."),
        call("compare_quotes", {"bill_id": bill}), call("prepare_payment", {"bill_id": bill, "route": "A"}, "c2"),
        say("Prepared route A for review."),
        say("Approval happens only in Payments."),
        call("read_financial_summary", {}), say(FINAL_TEXT),
    ], ai_requests_per_minute=1000, ai_requests_per_day=1000)
    result = agent_demo.run_demo(c)
    assert result.passed, _failed(result)
    assert result.model_requests == 10


def test_demo_pacing_waits_for_room_in_the_minute(sim, tmp_path) -> None:
    """Offline: the free-tier pacer waits while a whole turn would not fit the local minute count."""
    from app.ai import usage

    from .test_gemini_mock import install as install_gemini

    c = sim.client()
    install_gemini(sim, tmp_path, [None], ai_requests_per_minute=5, ai_requests_per_turn=4)
    clock = {"t": 0.0}
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["t"] += seconds

    usage.record(sim.db, workspace_id=None, provider="gemini", model="m", purpose="check", ok=True, error_code=None)
    agent_demo._pace(c, sleep=fake_sleep, now=lambda: clock["t"])
    assert sleeps == []  # 1 + 4 <= 5: no wait
    usage.record(sim.db, workspace_id=None, provider="gemini", model="m", purpose="check", ok=True, error_code=None)
    agent_demo._pace(c, sleep=fake_sleep, now=lambda: clock["t"])
    assert 30 <= len(sleeps) <= 36  # 2 + 4 > 5: waited (bounded at ~70 s)
