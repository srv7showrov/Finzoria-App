"""Three explicitly fictional demonstration transfer routes (demo fixtures).

Timings are calendar days under demo assumptions, not business days, and do not
describe any real provider. Routes are offered only from BDT source accounts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal

from ..errors import DomainError
from ..money import CURRENCY_PRECISION, quantize

QUOTE_TTL_MINUTES = 15
ROUTE_SOURCE_CURRENCY = "BDT"


@dataclass(frozen=True)
class TransferRoute:
    code: str
    fee: Decimal  # in ROUTE_SOURCE_CURRENCY
    delivery_days: int
    assumption: str  # stable key; the UI translates it


ROUTES: dict[str, TransferRoute] = {
    "A": TransferRoute("A", Decimal("1000.00"), 2, "instant_school_credit_after_arrival"),
    "B": TransferRoute("B", Decimal("1500.00"), 1, "credit_on_arrival"),
    "C": TransferRoute("C", Decimal("500.00"), 8, "credit_on_arrival"),
}


@dataclass(frozen=True)
class RouteCost:
    route: TransferRoute
    principal: Decimal
    fee: Decimal
    total: Decimal
    initiation: date
    arrival: date


def get_route(code: str) -> TransferRoute:
    route = ROUTES.get(code)
    if route is None:
        raise DomainError(422, "unknown_route", "Choose demonstration route A, B or C.")
    return route


def require_route_currency(source_currency: str) -> None:
    if source_currency != ROUTE_SOURCE_CURRENCY:
        raise DomainError(
            422, "no_route", f"Demonstration routes are only available from {ROUTE_SOURCE_CURRENCY} accounts."
        )


def principal_for(recipient_amount: Decimal, rate: Decimal, source_currency: str) -> Decimal:
    """Source amount needed so the recipient receives at least recipient_amount.
    Rounded UP to the source currency's minor unit so delivery is never short."""
    exponent = Decimal(1).scaleb(-CURRENCY_PRECISION[source_currency])
    return (recipient_amount / rate).quantize(exponent, rounding=ROUND_CEILING)


def cost(route: TransferRoute, recipient_amount: Decimal, rate: Decimal, source_currency: str, initiation: date) -> RouteCost:
    require_route_currency(source_currency)
    principal = principal_for(recipient_amount, rate, source_currency)
    fee = quantize(route.fee, source_currency)
    return RouteCost(route, principal, fee, principal + fee, initiation, initiation + timedelta(days=route.delivery_days))
