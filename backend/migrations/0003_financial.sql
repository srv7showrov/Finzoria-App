-- Stage B: actual transactions, planning entries, bills, contributions, goals,
-- reserve policy, FX snapshots, rate targets, quotes, payment proposals,
-- executions, refunds and activity events. Every private table carries
-- workspace_id. Money and rates are decimal strings; dates are YYYY-MM-DD;
-- timestamps are UTC ISO-8601 instants.

-- Posted actual money movements. Opening balances are NOT transactions.
CREATE TABLE transactions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('income', 'expense', 'contribution', 'payment', 'fee')),
    direction TEXT NOT NULL CHECK (direction IN ('credit', 'debit')),
    category TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    amount TEXT NOT NULL,
    currency TEXT NOT NULL,
    occurred_on TEXT NOT NULL,
    source_type TEXT,
    source_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_transactions_ws ON transactions(workspace_id, occurred_on);
-- A contribution or execution can produce each kind of transaction only once.
CREATE UNIQUE INDEX uq_transactions_source ON transactions(workspace_id, source_type, source_id, kind)
    WHERE source_type IS NOT NULL;

-- Planning entries (forecast only, never actual cash).
CREATE TABLE budget_entries (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
    category TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    amount TEXT NOT NULL,
    currency TEXT NOT NULL,
    start_date TEXT NOT NULL,
    recurrence TEXT NOT NULL CHECK (recurrence IN ('none', 'monthly')),
    end_date TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_budget_entries_ws ON budget_entries(workspace_id);

CREATE TABLE bills (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    payee TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'tuition',
    amount TEXT NOT NULL,
    currency TEXT NOT NULL,
    due_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'settled', 'cancelled')),
    version INTEGER NOT NULL DEFAULT 1,
    settled_on TEXT,
    settled_by_execution_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_bills_ws ON bills(workspace_id);

CREATE TABLE contributions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    contributor TEXT NOT NULL,
    amount TEXT NOT NULL,
    currency TEXT NOT NULL,
    expected_date TEXT NOT NULL,
    certainty TEXT NOT NULL CHECK (certainty IN ('expected', 'uncertain')),
    status TEXT NOT NULL CHECK (status IN ('expected', 'received', 'cancelled')),
    received_on TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_contributions_ws ON contributions(workspace_id);

CREATE TABLE savings_goals (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    target_amount TEXT NOT NULL,
    allocated_amount TEXT NOT NULL,
    currency TEXT NOT NULL,
    target_date TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_goals_ws ON savings_goals(workspace_id);

-- Minimum balance (floor) kept in one source account, in that account's currency.
CREATE TABLE reserve_policies (
    workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    floor_amount TEXT NOT NULL,
    strict INTEGER NOT NULL DEFAULT 1 CHECK (strict IN (0, 1)),
    updated_at TEXT NOT NULL
);

-- Rate snapshots: rate = units of quote currency per one unit of base currency.
CREATE TABLE fx_snapshots (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    base_currency TEXT NOT NULL,
    quote_currency TEXT NOT NULL,
    rate TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('fixture', 'manual')),
    source TEXT NOT NULL,
    as_of TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_fx_ws_pair ON fx_snapshots(workspace_id, base_currency, quote_currency, as_of);

-- Saved rate thresholds, evaluated only when the user refreshes ("checked on refresh").
CREATE TABLE rate_targets (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    base_currency TEXT NOT NULL,
    quote_currency TEXT NOT NULL,
    threshold TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('at_or_above', 'at_or_below')),
    created_at TEXT NOT NULL
);

-- Fictional demonstration quotes (not provider quotes).
CREATE TABLE quotes (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    route TEXT NOT NULL,
    source_currency TEXT NOT NULL,
    target_currency TEXT NOT NULL,
    rate TEXT NOT NULL,
    rate_snapshot_id TEXT NOT NULL,
    fee TEXT NOT NULL,
    delivery_days INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE payment_proposals (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    bill_id TEXT NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
    source_account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    quote_id TEXT NOT NULL REFERENCES quotes(id),
    status TEXT NOT NULL CHECK (status IN ('draft', 'ready_for_review', 'approved', 'executed_simulated', 'cancelled', 'failed', 'expired')),
    version INTEGER NOT NULL,
    terms TEXT NOT NULL,
    terms_hash TEXT NOT NULL,
    approved_version INTEGER,
    approved_hash TEXT,
    approved_at TEXT,
    status_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_proposals_ws ON payment_proposals(workspace_id, status);

CREATE TABLE executions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    proposal_id TEXT NOT NULL REFERENCES payment_proposals(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('executed_simulated')),
    result TEXT NOT NULL,
    created_at TEXT NOT NULL
);
-- One successful execution per proposal, and each key maps to one execution.
CREATE UNIQUE INDEX uq_executions_proposal ON executions(proposal_id);
CREATE UNIQUE INDEX uq_executions_key ON executions(workspace_id, idempotency_key);

CREATE TABLE refunds (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    execution_id TEXT NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
    amount TEXT NOT NULL,
    currency TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE activity_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    details TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_events_ws ON activity_events(workspace_id, id);
