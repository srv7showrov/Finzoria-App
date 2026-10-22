"""Exchange-rate snapshots and conversion.

A rate is "units of quote currency per one unit of base currency". Lookups use the
latest snapshot for the exact pair, or the exact inverse of the latest snapshot for
the reversed pair (labelled as derived). Anything else is an unsupported pair: no
silent rate of 1 and no chained cross rates. The same currency always converts at 1.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal, localcontext

from ..errors import DomainError
from ..money import parse_amount, parse_decimal, quantize, to_string, validate_currency
from .common import iso, new_id

RATE_PLACES = Decimal("0.0000000001")  # derived inverse rates keep 10 decimal places

FIXTURE_SOURCE = "Finzoria fixture set (fictional test rate, not market data)"
MANUAL_SOURCE = "Manual planning rate entered by the user"

# Labeled fixture set used by the demo scenarios.
FIXTURE_RATES: tuple[tuple[str, str, str], ...] = (
    ("BDT", "AUD", "0.0125"),
    ("USD", "AUD", "1.5"),
)


@dataclass(frozen=True)
class Rate:
    base: str
    quote: str
    rate: Decimal
    snapshot_id: str | None
    mode: str  # identity | fixture | manual
    source: str
    as_of: str | None
    derived: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "base": self.base,
            "quote": self.quote,
            "rate": format(self.rate, "f"),
            "snapshot_id": self.snapshot_id,
            "mode": self.mode,
            "source": self.source,
            "as_of": self.as_of,
            "derived": self.derived,
        }


class UnsupportedPair(DomainError):
    def __init__(self, base: str, quote: str) -> None:
        super().__init__(
            422,
            "unsupported_pair",
            f"No rate is available for {base} to {quote}. Add a manual planning rate first.",
            base=base,
            quote=quote,
        )


def validate_rate(value: str) -> Decimal:
    rate = parse_decimal(value)
    if rate <= 0:
        raise DomainError(422, "invalid_rate", "Rates must be positive numbers.")
    return rate


def add_snapshot(
    conn: sqlite3.Connection,
    workspace_id: str,
    base: str,
    quote: str,
    rate: str,
    mode: str,
    source: str,
    as_of: datetime,
    now: datetime,
) -> str:
    validate_currency(base)
    validate_currency(quote)
    if base == quote:
        raise DomainError(422, "same_currency", "A currency always converts to itself at 1.")
    validate_rate(rate)
    snapshot_id = new_id("fx")
    conn.execute(
        "INSERT INTO fx_snapshots (id, workspace_id, base_currency, quote_currency, rate, mode, source, as_of, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (snapshot_id, workspace_id, base, quote, rate, mode, source, iso(as_of), iso(now)),
    )
    return snapshot_id


def _latest(conn: sqlite3.Connection, workspace_id: str, base: str, quote: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, rate, mode, source, as_of FROM fx_snapshots"
        " WHERE workspace_id = ? AND base_currency = ? AND quote_currency = ?"
        " ORDER BY as_of DESC, created_at DESC, rowid DESC LIMIT 1",
        (workspace_id, base, quote),
    ).fetchone()


def get_rate(conn: sqlite3.Connection, workspace_id: str, base: str, quote: str) -> Rate:
    validate_currency(base)
    validate_currency(quote)
    if base == quote:
        return Rate(base, quote, Decimal(1), None, "identity", "Same currency", None)
    row = _latest(conn, workspace_id, base, quote)
    if row is not None:
        return Rate(base, quote, Decimal(row["rate"]), row["id"], row["mode"], row["source"], row["as_of"])
    row = _latest(conn, workspace_id, quote, base)
    if row is not None:
        with localcontext() as ctx:
            ctx.prec = 34
            inverse = (Decimal(1) / Decimal(row["rate"])).quantize(RATE_PLACES, rounding=ROUND_HALF_EVEN)
        return Rate(base, quote, inverse.normalize(), row["id"], row["mode"], row["source"], row["as_of"], derived=True)
    raise UnsupportedPair(base, quote)


def get_snapshot(conn: sqlite3.Connection, workspace_id: str, snapshot_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, base_currency, quote_currency, rate, mode, source, as_of FROM fx_snapshots"
        " WHERE workspace_id = ? AND id = ?",
        (workspace_id, snapshot_id),
    ).fetchone()


def convert(amount: Decimal, rate: Rate) -> Decimal:
    """Convert and round once, to the target currency's minor unit (ROUND_HALF_EVEN)."""
    return quantize(amount * rate.rate, rate.quote)


def list_snapshots(conn: sqlite3.Connection, workspace_id: str) -> list[dict[str, object]]:
    rows = conn.execute(
        "SELECT id, base_currency, quote_currency, rate, mode, source, as_of FROM fx_snapshots"
        " WHERE workspace_id = ? ORDER BY as_of DESC, created_at DESC, rowid DESC",
        (workspace_id,),
    ).fetchall()
    latest_per_pair: set[tuple[str, str]] = set()
    result = []
    for r in rows:
        pair = (r["base_currency"], r["quote_currency"])
        result.append(
            {
                "id": r["id"],
                "base": r["base_currency"],
                "quote": r["quote_currency"],
                "rate": r["rate"],
                "mode": r["mode"],
                "source": r["source"],
                "as_of": r["as_of"],
                "current": pair not in latest_per_pair,
            }
        )
        latest_per_pair.add(pair)
    return result


def seed_fixture_rates(conn: sqlite3.Connection, workspace_id: str, now: datetime) -> None:
    for base, quote, rate in FIXTURE_RATES:
        add_snapshot(conn, workspace_id, base, quote, rate, "fixture", FIXTURE_SOURCE, now, now)


# --- saved thresholds ("checked on refresh", never background monitoring) ----------


def create_target(conn: sqlite3.Connection, workspace_id: str, base: str, quote: str, threshold: str, direction: str,
                  now: datetime) -> str:
    validate_currency(base)
    validate_currency(quote)
    validate_rate(threshold)
    target_id = new_id("tgt")
    conn.execute(
        "INSERT INTO rate_targets (id, workspace_id, base_currency, quote_currency, threshold, direction, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (target_id, workspace_id, base, quote, threshold, direction, iso(now)),
    )
    return target_id


def list_targets(conn: sqlite3.Connection, workspace_id: str, now: datetime) -> list[dict[str, object]]:
    rows = conn.execute(
        "SELECT id, base_currency, quote_currency, threshold, direction FROM rate_targets WHERE workspace_id = ?"
        " ORDER BY created_at, rowid", (workspace_id,),
    ).fetchall()
    result = []
    for r in rows:
        try:
            rate = get_rate(conn, workspace_id, r["base_currency"], r["quote_currency"])
        except UnsupportedPair:
            rate = None
        threshold = Decimal(r["threshold"])
        met = None if rate is None else (rate.rate >= threshold if r["direction"] == "at_or_above" else rate.rate <= threshold)
        result.append({
            "id": r["id"], "base": r["base_currency"], "quote": r["quote_currency"], "threshold": r["threshold"],
            "direction": r["direction"], "met": met, "current_rate": None if rate is None else rate.as_dict(),
            "checked_at": iso(now), "check_mode": "on_refresh",
        })
    return result


def delete_target(conn: sqlite3.Connection, workspace_id: str, target_id: str) -> None:
    deleted = conn.execute("DELETE FROM rate_targets WHERE workspace_id = ? AND id = ?", (workspace_id, target_id)).rowcount
    if deleted != 1:
        raise DomainError(404, "not_found", "Rate target not found.")


def rate_scenario(conn: sqlite3.Connection, workspace_id: str, base: str, quote: str, amount: str, change_percent: str) -> dict[str, object]:
    """What if the rate moved by change_percent? Nothing is saved; no outcome is predicted."""
    value = parse_amount(amount, base)
    change = parse_decimal(change_percent)
    if not Decimal(-90) <= change <= Decimal(90):
        raise DomainError(422, "invalid_change", "Use a change between -90 and 90 percent.")
    rate = get_rate(conn, workspace_id, base, quote)
    shifted = Rate(base, quote, rate.rate * (Decimal(100) + change) / Decimal(100), rate.snapshot_id, rate.mode,
                   rate.source, rate.as_of, rate.derived)
    now_value, then_value = convert(value, rate), convert(value, shifted)
    return {
        "saved": False, "prediction": False, "amount": to_string(value, base), "base": base, "quote": quote,
        "change_percent": format(change, "f"), "current_rate": rate.as_dict(), "scenario_rate": format(shifted.rate, "f"),
        "current_value": to_string(now_value, quote), "scenario_value": to_string(then_value, quote),
        "difference": to_string(then_value - now_value, quote),
    }
