"""Server-only model adapters: Anthropic (official `anthropic` SDK) and Google Gemini
(official `google-genai` SDK). FINZORIA_AI_PROVIDER selects one; there is no automatic
fallback between providers.

Keys and models come from FINZORIA_* settings only. Clients are built with an explicit
key and base URL so they never inherit credentials or endpoints from other tools'
environment variables (ANTHROPIC_*, GOOGLE_API_KEY, GEMINI_API_KEY, GOOGLE_GENAI_*).
SDK retries are disabled so every request attempt is visible and counted. Nothing here
returns the key, raw provider error bodies, or prompts to callers.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

import anthropic
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from ..config import Settings

ConnectionState = Literal["unavailable", "configured_unverified", "connected", "failed"]

SMOKE_MAX_TOKENS = 64


@dataclass(frozen=True)
class SmokeResult:
    """ok is True only for a usable text reply. "connected_no_text" means the authenticated
    request succeeded but returned no usable text (for example the output budget was used up
    by thinking), so connectivity is proven but a usable response is not."""

    ok: bool
    outcome: str  # short, sanitized code such as "ok", "connected_no_text" or "authentication_error"
    details: str = ""  # sanitized: finish reason and token counts only


class AnthropicAdapter:
    provider = "anthropic"
    requests_per_turn = 6
    requests_per_minute: int | None = None
    requests_per_day: int | None = None

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.anthropic_api_key
        self.model = settings.anthropic_model
        self._base_url = settings.anthropic_base_url
        self._client: anthropic.Anthropic | None = None
        _apply_limits(self, settings)

    @property
    def configured(self) -> bool:
        return bool(self._api_key and self.model)

    def missing_configuration(self) -> list[str]:
        missing = []
        if not self._api_key:
            missing.append("FINZORIA_ANTHROPIC_API_KEY")
        if not self.model:
            missing.append("FINZORIA_ANTHROPIC_MODEL")
        return missing

    def client(self) -> anthropic.Anthropic:
        if not self.configured:
            raise RuntimeError("Anthropic connection is not configured")
        if self._client is None:
            self._client = anthropic.Anthropic(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=30.0,
                max_retries=0,
            )
        return self._client

    def smoke_test(self) -> SmokeResult:
        """One low-token real request. Returns a sanitized outcome code."""
        if not self.configured:
            return SmokeResult(False, "not_configured")
        try:
            response = self.client().messages.create(
                model=self.model,  # type: ignore[arg-type]
                max_tokens=SMOKE_MAX_TOKENS,
                output_config={"effort": "low"},
                messages=[{"role": "user", "content": "Reply with the single word: ready"}],
            )
        except anthropic.AuthenticationError:
            return SmokeResult(False, "authentication_error")
        except anthropic.PermissionDeniedError:
            return SmokeResult(False, "permission_error")
        except anthropic.NotFoundError:
            return SmokeResult(False, "model_not_found")
        except anthropic.RateLimitError:
            return SmokeResult(False, "rate_limited")
        except anthropic.BadRequestError:
            return SmokeResult(False, "bad_request")
        except anthropic.APIStatusError as exc:
            if exc.status_code == 402:
                return SmokeResult(False, "billing_error")
            return SmokeResult(False, f"api_error_{exc.status_code}")
        except anthropic.APIConnectionError:
            return SmokeResult(False, "connection_error")
        if response.stop_reason == "refusal":
            return SmokeResult(False, "refusal")
        has_text = any(block.type == "text" and block.text.strip() for block in response.content)
        details = f"stop_reason={response.stop_reason}"
        return SmokeResult(True, "ok", details) if has_text else SmokeResult(False, "connected_no_text", details)


GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/"
GEMINI_TIMEOUT_MS = 60_000
# Gemini counts thinking tokens against max_output_tokens (official "Gemini thinking" docs), so a
# 64-token cap can be consumed entirely by thinking and return no text (finish MAX_TOKENS). The
# check therefore asks for low thinking (the documented way to reduce thinking) with a 1,024-token
# cap: still one small request. The finish reason and token counts are reported.
GEMINI_SMOKE_MAX_TOKENS = 1024
GEMINI_SMOKE_THINKING = "LOW"
# Owner-observed free-tier limits for the candidate Flash models (AI Studio, 2026-10):
# 5 requests/minute, 20 requests/day. Account observations, not provider guarantees;
# override with FINZORIA_AI_REQUESTS_PER_MINUTE / _PER_DAY.
GEMINI_DEFAULT_PER_MINUTE = 5
GEMINI_DEFAULT_PER_DAY = 20
GEMINI_DEFAULT_PER_TURN = 4


def gemini_error_code(exc: Exception) -> str:
    """Sanitized code for a google-genai or transport error (never the provider message)."""
    if isinstance(exc, genai_errors.APIError):
        status = str(getattr(exc, "status", "") or "").upper()
        text = str(getattr(exc, "message", "") or "")
        if exc.code == 429 or status == "RESOURCE_EXHAUSTED":
            return "quota_exhausted"
        if exc.code == 400 and ("API_KEY_INVALID" in text or "API key not valid" in text):
            return "authentication_error"
        if exc.code == 400 and "location is not supported" in text.lower():
            return "permission_error"
        mapping = {400: "bad_request", 401: "authentication_error", 403: "permission_error", 404: "model_not_found",
                   408: "timeout", 503: "overloaded", 504: "timeout"}
        return mapping.get(exc.code, f"provider_error_{exc.code}")
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return "timeout"
    if "connect" in name or "network" in name:
        return "connection_error"
    return "provider_error"


def gemini_failure_details(exc: Exception, elapsed_s: float) -> str:
    """Sanitized diagnostics for a failed request: the exception class (e.g. httpx ConnectTimeout =
    no TCP/TLS connection in time; ReadTimeout = connected, no reply in time), the HTTP code and
    provider status if a response arrived (e.g. 504 DEADLINE_EXCEEDED), and the elapsed time.
    Never the provider message, the request or the key."""
    parts = [f"cause={type(exc).__name__}"]
    if isinstance(exc, genai_errors.APIError):
        parts.append(f"http={exc.code}")
        if getattr(exc, "status", None):
            parts.append(f"status={exc.status}")
    parts.append(f"elapsed={elapsed_s:.1f}s timeout={GEMINI_TIMEOUT_MS // 1000}s")
    return " ".join(parts)


def gemini_details(response: object) -> str:
    """Sanitized diagnostics: finish reason and token counts (no text, no prompts)."""
    candidates = getattr(response, "candidates", None) or []
    reason = getattr(candidates[0], "finish_reason", None) if candidates else None
    usage_md = getattr(response, "usage_metadata", None)
    return (f"finish_reason={getattr(reason, 'name', reason)} thoughts_tokens={getattr(usage_md, 'thoughts_token_count', None)} "
            f"output_tokens={getattr(usage_md, 'candidates_token_count', None)}")


class GeminiAdapter:
    """Google Gemini Developer API (AI Studio key) through the official google-genai SDK."""

    provider = "gemini"
    requests_per_turn = GEMINI_DEFAULT_PER_TURN
    requests_per_minute: int | None = GEMINI_DEFAULT_PER_MINUTE
    requests_per_day: int | None = GEMINI_DEFAULT_PER_DAY

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.gemini_api_key
        self.model = settings.gemini_model
        self._client: genai.Client | None = None
        _apply_limits(self, settings)

    @property
    def configured(self) -> bool:
        return bool(self._api_key and self.model)

    def missing_configuration(self) -> list[str]:
        missing = []
        if not self._api_key:
            missing.append("FINZORIA_GEMINI_API_KEY")
        if not self.model:
            missing.append("FINZORIA_GEMINI_MODEL")
        return missing

    def client(self) -> genai.Client:
        if not self.configured:
            raise RuntimeError("Gemini connection is not configured")
        if self._client is None:
            self._client = genai.Client(
                api_key=self._api_key,
                vertexai=False,
                http_options=genai_types.HttpOptions(
                    base_url=GEMINI_BASE_URL,
                    api_version="v1beta",
                    timeout=GEMINI_TIMEOUT_MS,
                    retry_options=genai_types.HttpRetryOptions(attempts=1),  # no hidden retries
                ),
            )
        return self._client

    def smoke_test(self) -> SmokeResult:
        """Exactly one small real request. Returns a sanitized outcome code."""
        if not self.configured:
            return SmokeResult(False, "not_configured")
        started = time.monotonic()
        try:
            response = self.client().models.generate_content(
                model=self.model,  # type: ignore[arg-type]
                contents="Reply with the single word: ready",
                config=genai_types.GenerateContentConfig(
                    max_output_tokens=GEMINI_SMOKE_MAX_TOKENS,
                    thinking_config=genai_types.ThinkingConfig(thinking_level=GEMINI_SMOKE_THINKING),
                    automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
        except Exception as exc:  # noqa: BLE001 - sanitized code only
            # "timeout" alone cannot tell a network problem from a slow model: report which one.
            return SmokeResult(False, gemini_error_code(exc), gemini_failure_details(exc, time.monotonic() - started))
        if getattr(response.prompt_feedback, "block_reason", None):
            return SmokeResult(False, "refusal")
        candidates = response.candidates or []
        if not candidates:
            return SmokeResult(False, "malformed_response")
        parts = (candidates[0].content.parts if candidates[0].content else None) or []
        has_text = any(p.text and p.text.strip() and not p.thought for p in parts)
        details = gemini_details(response)
        return SmokeResult(True, "ok", details) if has_text else SmokeResult(False, "connected_no_text", details)


ModelAdapter = AnthropicAdapter | GeminiAdapter


class UnsupportedProviderAdapter:
    """FINZORIA_AI_PROVIDER names an unknown provider: the assistant stays unavailable."""

    provider = "unsupported"
    model: str | None = None
    configured = False
    requests_per_turn = 0
    requests_per_minute: int | None = None
    requests_per_day: int | None = None

    def missing_configuration(self) -> list[str]:
        return ["FINZORIA_AI_PROVIDER"]

    def smoke_test(self) -> SmokeResult:
        return SmokeResult(False, "not_configured")


def _apply_limits(adapter: object, settings: Settings) -> None:
    for attr, value in (("requests_per_minute", settings.ai_requests_per_minute),
                        ("requests_per_day", settings.ai_requests_per_day),
                        ("requests_per_turn", settings.ai_requests_per_turn)):
        if value:
            setattr(adapter, attr, value)


def build_adapter(settings: Settings) -> AnthropicAdapter | GeminiAdapter | UnsupportedProviderAdapter:
    if settings.ai_provider == "gemini":
        return GeminiAdapter(settings)
    if settings.ai_provider == "anthropic":
        return AnthropicAdapter(settings)
    return UnsupportedProviderAdapter()


def connection_status(adapter, latest_check: dict[str, object] | None) -> dict[str, object]:  # type: ignore[no-untyped-def]
    """Sanitized status for the UI and /api/health."""
    limits = {"per_minute": adapter.requests_per_minute, "per_day": adapter.requests_per_day,
              "per_turn": adapter.requests_per_turn}
    if not adapter.configured:
        return {
            "state": "unavailable",
            "reason": "not_configured",
            "provider": adapter.provider,
            "missing": adapter.missing_configuration(),
            "last_check": None,
        }
    state: ConnectionState = "configured_unverified"
    if latest_check and latest_check.get("model") == adapter.model:
        state = "connected" if latest_check.get("ok") else "failed"
    return {"state": state, "reason": None, "provider": adapter.provider, "missing": [], "model": adapter.model,
            "last_check": latest_check, "local_request_limits": limits}
