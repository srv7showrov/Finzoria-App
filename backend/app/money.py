"""Money primitives. All amounts are Decimal; they cross the API as strings.

Binary floating point is never used for money. Each currency has a documented
minor-unit precision; amounts are quantized with ROUND_HALF_EVEN only at
explicit rounding points.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

# ISO 4217 minor units for the baseline currencies.
CURRENCY_PRECISION: dict[str, int] = {
    "BDT": 2,
    "USD": 2,
    "AUD": 2,
    "EUR": 2,
    "CNY": 2,
    "INR": 2,
    "GBP": 2,
    "AED": 2,
    "SAR": 2,
    "JPY": 0,
}
SUPPORTED_CURRENCIES: tuple[str, ...] = tuple(CURRENCY_PRECISION)

_DECIMAL_STRING = re.compile(r"^-?\d{1,15}(\.\d{1,8})?$")


class MoneyError(ValueError):
    """Raised for invalid money input; the message is safe to show users."""


def validate_currency(code: str) -> str:
    if code not in CURRENCY_PRECISION:
        raise MoneyError(f"Unsupported currency: {code!r}")
    return code


def parse_decimal(value: str) -> Decimal:
    """Parse a plain decimal string ("1234.50"). Rejects floats, exponents, NaN and infinity."""
    if not isinstance(value, str):
        raise MoneyError("Amounts must be sent as decimal strings")
    text = value.strip()
    if not _DECIMAL_STRING.fullmatch(text):
        raise MoneyError("Enter a plain decimal number, for example 1250.00")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - guarded by the regex
        raise MoneyError("Invalid decimal number") from exc
    if not result.is_finite():  # pragma: no cover - guarded by the regex
        raise MoneyError("Amount must be finite")
    return result


def quantize(amount: Decimal, currency: str) -> Decimal:
    exponent = Decimal(1).scaleb(-CURRENCY_PRECISION[validate_currency(currency)])
    return amount.quantize(exponent, rounding=ROUND_HALF_EVEN)


def parse_amount(value: str, currency: str, *, allow_negative: bool = False) -> Decimal:
    """Parse an amount and require it to fit the currency's minor units exactly."""
    amount = parse_decimal(value)
    if amount < 0 and not allow_negative:
        raise MoneyError("Amount cannot be negative")
    if quantize(amount, currency) != amount:
        digits = CURRENCY_PRECISION[currency]
        raise MoneyError(f"{currency} amounts allow at most {digits} decimal places")
    return amount


def to_string(amount: Decimal, currency: str) -> str:
    return format(quantize(amount, currency), "f")
