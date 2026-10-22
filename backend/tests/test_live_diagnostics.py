"""OFFLINE tests (MOCK model clients, no network) for the live-run diagnostics: connection-check
classification, bounded per-request timeouts, demo progress output, the read-only tool check and
interrupt handling. None of this is real-model evidence."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import httpx
import pytest
from google.genai import types as gt

from app.ai import assistant
from app.ai.adapter import GeminiAdapter

from .conftest import ORIGIN, make_settings, ok
from .test_gemini_mock import QUOTA, MockGenaiClient, fc, install, say

_spec = importlib.util.spec_from_file_location("agent_demo_diag", Path(__file__).resolve().parents[1] / "scripts" / "agent_demo.py")
agent_demo = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
sys.modules["agent_demo_diag"] = agent_demo
_spec.loader.exec_module(agent_demo)  # type: ignore[union-attr]

_smoke_spec = importlib.util.spec_from_file_location("ai_smoke_diag", Path(__file__).resolve().parents[1] / "scripts" / "ai_smoke_test.py")
ai_smoke = importlib.util.module_from_spec(_smoke_spec)  # type: ignore[arg-type]
_smoke_spec.loader.exec_module(ai_smoke)  # type: ignore[union-attr]


def thinking_only(thoughts=60):  # type: ignore[no-untyped-def]
    """MOCK: the output budget was spent on thinking; no visible text (finish MAX_TOKENS)."""
    return gt.GenerateContentResponse(
        candidates=[gt.Candidate(content=gt.Content(role="model", parts=[gt.Part(text="...", thought=True)]), finish_reason="MAX_TOKENS")],
        usage_metadata=gt.GenerateContentResponseUsageMetadata(thoughts_token_count=thoughts, candidates_token_count=0))


# --- connection check ------------------------------------------------------------------------


def test_connection_check_separates_connectivity_from_usable_text(tmp_path) -> None:
    adapter = GeminiAdapter(make_settings(tmp_path, ai_provider="gemini", gemini_api_key="k", gemini_model="m"))
    adapter._client = MockGenaiClient([thinking_only()])  # type: ignore[assignment]
    result = adapter.smoke_test()
    assert (result.ok, result.outcome) == (False, "connected_no_text")
    assert "finish_reason=MAX_TOKENS" in result.details and "thoughts_tokens=60" in result.details
    config = adapter._client.models.requests[0]["config"]  # type: ignore[union-attr]
    assert config.max_output_tokens == 1024 and config.thinking_config.thinking_level == gt.ThinkingLevel.LOW
    adapter._client = MockGenaiClient([say("ready")])  # type: ignore[assignment]
    assert adapter.smoke_test().ok is True


@pytest.mark.parametrize("reply, code, label", [
    (thinking_only(), 3, "CONNECTED BUT NO USABLE TEXT"),
    (say("ready"), 0, "PASSED"),
    (QUOTA, 1, "FAILED"),
])
def test_connection_check_script_exit_codes(tmp_path, monkeypatch, capsys, reply, code, label) -> None:
    settings = make_settings(tmp_path, ai_provider="gemini", gemini_api_key="secret-key-123", gemini_model="m")
    adapter = GeminiAdapter(settings)
    adapter._client = MockGenaiClient([reply])  # type: ignore[assignment]
    monkeypatch.setattr(ai_smoke, "load_settings", lambda: settings)
    monkeypatch.setattr(ai_smoke, "build_adapter", lambda _s: adapter)
    assert ai_smoke.main() == code
    out = capsys.readouterr().out
    assert out.startswith("Sending one model request") and f"{label}:" in out and "model requests sent=1" in out
    assert "secret-key-123" not in out  # key never printed
    assert len(adapter._client.models.requests) == 1  # type: ignore[union-attr]


# --- bounded per-request timeouts ---------------------------------------------------------------


def test_request_timeouts_are_clamped_to_the_turn_deadline(sim, tmp_path) -> None:
    """MOCK slow model: each request 'takes' 70 s on a fake clock. Requests start at 0, 70 and
    140 s; the third request's timeout is clamped to the 10 s left of the 150 s deadline, and no
    fourth request is started."""
    c = sim.client()
    models = install(sim, tmp_path, [fc("read_financial_summary", {}), fc("calculate_budget", {}, "c2"),
                                     fc("read_financial_summary", {}, "c3"), say("never")], ai_requests_per_minute=100)
    clock = {"t": 0.0}
    original = models.generate_content

    def slow(**kwargs):  # type: ignore[no-untyped-def]
        response = original(**kwargs)
        clock["t"] += 70  # each request takes 70 s
        return response

    models.generate_content = slow  # type: ignore[method-assign]
    ws = ok(c.get("/api/session"))["workspace_id"]
    ctx = assistant.TurnContext(ws, sim.db, sim.clock.today("Asia/Dhaka"), sim.clock.now(), "BDT", "en", "Asia/Dhaka")
    result = assistant.run_turn(sim.app.state.ai, ctx, None, "Balance and budget?", "concise", clock_seconds=lambda: clock["t"])
    timeouts = [r["config"].http_options.timeout for r in models.requests]
    assert timeouts == [60000, 60000, 10000]  # 150 - 140 = 10 s left for the third request
    assert (result["status"], result["error_code"], result["model_requests"]) == ("incomplete", "time_limit", 3)
    assert all(r["config"].http_options.retry_options.attempts == 1 for r in models.requests)
    assert models.requests[0]["config"].thinking_config.thinking_level == gt.ThinkingLevel.LOW


def test_detailed_mode_uses_medium_thinking_and_timeout_errors_are_reported(sim, tmp_path) -> None:
    c = sim.client()
    models = install(sim, tmp_path, [httpx.ReadTimeout("timed out")])
    result = ok(c.post("/api/assistant/chat", json={"message": "Hi", "mode": "detailed"}, headers=ORIGIN))
    assert (result["status"], result["error_code"], result["model_requests"]) == ("failed", "timeout", 1)
    assert models.requests[0]["config"].thinking_config.thinking_level == gt.ThinkingLevel.MEDIUM


# --- read-only tool check ------------------------------------------------------------------------


def test_tool_check_passes_on_a_real_round_trip_shape(sim, tmp_path, capsys) -> None:
    c = sim.client()
    models = install(sim, tmp_path, [fc("read_financial_summary", {}), say("Your BDT balance is 100,000.00.")],
                     ai_requests_per_minute=100)
    result = agent_demo.run_tool_check(c)
    assert result.passed, result.checks
    assert result.model_requests == 2 and len(models.requests) == 2
    out = capsys.readouterr().out
    assert "stage tool-check: sending assistant turn" in out and "HTTP 200 status=ok" in out
    assert "tools=read_financial_summary[ok]" in out and "model_requests=2" in out


@pytest.mark.parametrize("script, failing", [
    ([fc("read_financial_summary", {}), thinking_only()], "tool-check: final answer states the BDT 100,000 balance"),
    ([say("Your BDT balance is 100,000.00.")], "tool-check: read_financial_summary succeeded and returned BDT 100,000.00"),
    ([QUOTA], "tool-check: read_financial_summary succeeded and returned BDT 100,000.00"),
    ([fc("read_financial_summary", {}), fc("calculate_budget", {}, "c2"), say("late")],
     "tool-check: final answer states the BDT 100,000 balance"),
])
def test_tool_check_rejects_empty_missing_quota_and_overlong(sim, tmp_path, script, failing) -> None:
    c = sim.client()
    models = install(sim, tmp_path, script, ai_requests_per_minute=100)
    result = agent_demo.run_tool_check(c)
    assert not result.passed and failing in {n for n, passed, _ in result.checks if not passed}
    assert len(models.requests) <= agent_demo.TOOL_CHECK_MAX_REQUESTS


# --- progress and interruption -----------------------------------------------------------------


def test_pacing_announces_deliberate_waits(sim, tmp_path, capsys) -> None:
    from app.ai import usage

    c = sim.client()
    install(sim, tmp_path, [say("x")], ai_requests_per_minute=5, ai_requests_per_turn=4)
    for _ in range(2):
        usage.record(sim.db, workspace_id=None, provider="gemini", model="m", purpose="check", ok=True, error_code=None)
    clock = {"t": 0.0}
    agent_demo._pace(c, sleep=lambda s: clock.__setitem__("t", clock["t"] + s), now=lambda: clock["t"])
    out = capsys.readouterr().out
    assert "pacing: waiting for the local per-minute guard (2 requests in the last minute, limit 5" in out
    assert "waited ~70 s; continuing" in out


def test_interrupt_writes_partial_results_and_never_passes(tmp_path, monkeypatch, capsys) -> None:
    settings = make_settings(tmp_path, ai_provider="gemini", gemini_api_key="k", gemini_model="m")
    monkeypatch.setattr(agent_demo, "load_settings", lambda: settings)
    monkeypatch.setattr(agent_demo, "TOOL_CHECK_EVIDENCE", tmp_path / "tool-check.md")

    def interrupted(client, result):  # type: ignore[no-untyped-def]
        result.stage = "tool-check"
        result.model_requests = 1
        result.check("tool-check: something already checked", True)
        raise KeyboardInterrupt

    def fake_exit(code):  # type: ignore[no-untyped-def]
        raise SystemExit(code)

    monkeypatch.setattr(agent_demo, "run_tool_check", interrupted)  # no model call at all
    monkeypatch.setattr(agent_demo.os, "_exit", fake_exit)
    with pytest.raises(SystemExit) as stop:
        agent_demo.main(["--tool-check"])
    assert stop.value.code == 130
    evidence = (tmp_path / "tool-check.md").read_text(encoding="utf-8")
    assert "INTERRUPTED during stage 'tool-check'" in evidence and "acceptance NOT passed" in evidence
    assert "PASSED**" not in evidence
    out = capsys.readouterr().out
    assert "temporary database (your data is not used)" in out and "INTERRUPTED during stage 'tool-check'" in out
    assert "1 model requests reported" in out
    assert not (tmp_path / "test.sqlite3").exists()  # the configured database was never opened


def test_full_demo_progress_marks_each_stage(sim, tmp_path, capsys) -> None:
    c = sim.client()
    install(sim, tmp_path, [QUOTA], ai_requests_per_minute=100)
    result = agent_demo.run_demo(c)
    assert not result.passed
    out = capsys.readouterr().out
    for stage in ("plan", "delay", "prepare", "bypass"):
        assert f"stage {stage}: sending assistant turn" in out and f"stage {stage}: HTTP 200 status=failed error=quota_exhausted" in out
    assert "user action: contribution recorded" in out and "stopping: the prepared proposal does not match" in out


@pytest.mark.parametrize("error, cause", [
    (httpx.ConnectTimeout("connect"), "cause=ConnectTimeout"),
    (httpx.ReadTimeout("read"), "cause=ReadTimeout"),
    (httpx.PoolTimeout("pool"), "cause=PoolTimeout"),
])
def test_connection_check_says_which_timeout(tmp_path, error, cause) -> None:
    """MOCK: all transport timeouts share outcome "timeout"; the details name the phase."""
    adapter = GeminiAdapter(make_settings(tmp_path, ai_provider="gemini", gemini_api_key="k", gemini_model="m"))
    adapter._client = MockGenaiClient([error])  # type: ignore[assignment]
    result = adapter.smoke_test()
    assert (result.ok, result.outcome) == (False, "timeout")
    assert cause in result.details and "timeout=60s" in result.details and "elapsed=" in result.details


def test_connection_check_reports_provider_deadline_separately(tmp_path) -> None:
    from google.genai import errors as gerrors

    adapter = GeminiAdapter(make_settings(tmp_path, ai_provider="gemini", gemini_api_key="k", gemini_model="m"))
    adapter._client = MockGenaiClient([gerrors.ServerError(504, {"error": {"code": 504, "message": "Deadline expired",  # type: ignore[assignment]
                                                                           "status": "DEADLINE_EXCEEDED"}})])
    result = adapter.smoke_test()
    assert result.outcome == "timeout"
    assert "cause=ServerError http=504 status=DEADLINE_EXCEEDED" in result.details
    assert "Deadline expired" not in result.details  # provider message never echoed


def test_client_timeout_is_sixty_seconds_in_sdk_units(tmp_path) -> None:
    """HttpOptions.timeout is milliseconds; the SDK converts it to seconds for httpx."""
    from google.genai._api_client import get_timeout_in_seconds

    adapter = GeminiAdapter(make_settings(tmp_path, ai_provider="gemini", gemini_api_key="k", gemini_model="m"))
    options = adapter.client()._api_client._http_options  # builds the client; no request
    assert options.timeout == 60000 and get_timeout_in_seconds(options.timeout) == 60.0
