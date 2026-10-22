"""Fictional demo scenario seeded into each new workspace (demo fixed test
scenario). Dates are relative to the workspace's "today" so the simulation clock
2026-10-19 reproduces the fixture exactly: tuition due 2026-10-25 and the family
contribution expected 2026-10-20."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

from .bills import create_bill
from .budget import create_entry
from .funding import create_contribution, create_goal, set_reserve
from .rates import seed_fixture_rates

# Arithmetic fixture: 45000 - (10000 + 12000 + 6500 + 2500 + 1500) = 12500 BDT per month.
DEMO_BUDGET = (
    ("income", "income", "Part-time work and family support", "45000.00"),
    ("expense", "rent", "Rent", "10000.00"),
    ("expense", "food", "Food", "12000.00"),
    ("expense", "transport", "Transport", "6500.00"),
    ("expense", "phone", "Phone and internet", "2500.00"),
    ("expense", "books", "Books and supplies", "1500.00"),
)


def seed_demo(conn: sqlite3.Connection, workspace_id: str, bdt_account_id: str, now: datetime, today: date) -> None:
    seed_fixture_rates(conn, workspace_id, now)
    set_reserve(conn, workspace_id, bdt_account_id, "20000.00", now)
    create_bill(conn, workspace_id, description="Tuition installment (demo)", payee="Example University (fictional)",
                category="tuition", amount="1000.00", currency="AUD", due_date=(today + timedelta(days=6)).isoformat(), now=now)
    create_contribution(conn, workspace_id, account_id=bdt_account_id, contributor="Family (demo)", amount="10000.00",
                        expected_date=(today + timedelta(days=1)).isoformat(), certainty="expected", now=now)
    month_start = today.replace(day=1).isoformat()
    for kind, category, description, amount in DEMO_BUDGET:
        create_entry(conn, workspace_id, kind=kind, category=category, description=description, amount=amount,
                     currency="BDT", start_date=month_start, recurrence="monthly", end_date=None, now=now)
    create_goal(conn, workspace_id, name="Emergency fund (demo)", target_amount="50000.00", allocated_amount="5000.00",
                currency="BDT", target_date=None, now=now)
