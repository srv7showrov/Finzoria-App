"""Pydantic request models. Unknown fields are rejected."""

from __future__ import annotations

from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .money import SUPPORTED_CURRENCIES

SUPPORTED_LANGUAGES = ("en", "zh-Hans", "bn", "hi", "ar", "de")
_TIME_ZONES = frozenset(available_timezones())


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProfileUpdate(StrictModel):
    display_name: str = Field(min_length=1, max_length=80)
    institution: str = Field(default="", max_length=120)


class PreferencesUpdate(StrictModel):
    language: str
    display_currency: str
    time_zone: Ref

    @field_validator("language")
    @classmethod
    def _language(cls, value: str) -> str:
        if value not in SUPPORTED_LANGUAGES:
            raise ValueError("Unsupported language")
        return value

    @field_validator("display_currency")
    @classmethod
    def _currency(cls, value: str) -> str:
        if value not in SUPPORTED_CURRENCIES:
            raise ValueError("Unsupported currency")
        return value

    @field_validator("time_zone")
    @classmethod
    def _time_zone(cls, value: str) -> str:
        if value not in _TIME_ZONES:
            raise ValueError("Unknown IANA time zone")
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:  # pragma: no cover - guarded above
            raise ValueError("Unknown IANA time zone") from exc
        return value


# --- Stage B request bodies. Amounts and rates are decimal strings (numbers are rejected). ---

Category = Annotated[str, Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")]
Text = Annotated[str, Field(max_length=200)]
IsoDate = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
OptionalDate = Annotated[str | None, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
Amount = Annotated[str, Field(max_length=32)]
Code = Annotated[str, Field(min_length=3, max_length=3)]
Ref = Annotated[str, Field(max_length=64)]


class TransactionCreate(StrictModel):
    account_id: Ref
    kind: Literal["income", "expense"]
    category: Category
    description: Text = ""
    amount: Amount
    occurred_on: IsoDate


class ChatRequest(StrictModel):
    conversation_id: Ref | None = None
    message: str = Field(min_length=1, max_length=4000)
    mode: Literal["concise", "detailed"] = "concise"


class InvoiceText(StrictModel):
    text: str = Field(min_length=1, max_length=8000)


class OccurrenceRecord(StrictModel):
    occurrence_date: IsoDate
    account_id: Ref
    occurred_on: IsoDate


class BudgetEntryCreate(StrictModel):
    kind: Literal["income", "expense"]
    category: Category
    description: Text = ""
    amount: Amount
    currency: Code
    start_date: IsoDate
    recurrence: Literal["none", "monthly"]
    end_date: OptionalDate = None


class ContributionCreate(StrictModel):
    account_id: Ref
    contributor: str = Field(min_length=1, max_length=80)
    amount: Amount
    expected_date: IsoDate
    certainty: Literal["expected", "uncertain"]


class ContributionReceive(StrictModel):
    received_on: OptionalDate = None


class GoalCreate(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    target_amount: Amount
    allocated_amount: str = Field(default="0", max_length=32)
    currency: Code
    target_date: OptionalDate = None


class GoalAllocation(StrictModel):
    allocated_amount: Amount


class ReserveUpdate(StrictModel):
    account_id: Ref
    floor_amount: Amount


class ManualRateCreate(StrictModel):
    base: Code
    quote: Code
    rate: Amount


class RateTargetCreate(StrictModel):
    base: Code
    quote: Code
    threshold: Amount
    direction: Literal["at_or_above", "at_or_below"]


class RateScenario(StrictModel):
    base: Code
    quote: Code
    amount: Amount
    change_percent: str = Field(max_length=16)


class Scenario(StrictModel):
    type: Literal["delay_contribution", "change_expense"]
    contribution_id: Ref | None = None
    new_date: OptionalDate = None
    entry_id: Ref | None = None
    new_amount: Amount | None = None


class BillBody(StrictModel):
    description: str = Field(min_length=1, max_length=120)
    payee: str = Field(min_length=1, max_length=120)
    category: Literal["tuition", "campus", "housing", "other"] = "tuition"
    amount: Amount
    currency: Code
    due_date: IsoDate


class ProposalCreate(StrictModel):
    bill_id: Ref
    source_account_id: Ref
    route: Literal["A", "B", "C"]


class ProposalApprove(StrictModel):
    version: int = Field(ge=1)
    terms_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProposalExecute(StrictModel):
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


class RefundCreate(StrictModel):
    amount: Amount
    reason: str = Field(min_length=1, max_length=200)


class FundingApplicationIn(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    provider: str = Field(default="", max_length=120)
    status: Literal["planning", "applied", "awarded", "declined", "withdrawn"] = "planning"
    deadline: OptionalDate = None
    notes: str = Field(default="", max_length=500)


class ChecklistUpdate(StrictModel):
    done: bool


class WorkIncomeIn(StrictModel):
    hourly_rate: Amount
    hours_per_week: Amount
    weeks: int = Field(ge=1, le=104)
    currency: Code
    basis: Literal["gross", "net"]
    deduction_percent: Amount = "0"


class ResetConfirm(StrictModel):
    confirm: Literal["RESET"]


class DeleteConfirm(StrictModel):
    confirm: Literal["DELETE"]
