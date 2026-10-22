-- Explicit links between one planned occurrence and the actual transaction that
-- fulfilled it. A fulfilled occurrence leaves cash-flow projections; the plan itself
-- is unchanged so planned-versus-actual comparisons keep both amounts.
CREATE TABLE plan_fulfilments (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    entry_id TEXT NOT NULL REFERENCES budget_entries(id) ON DELETE CASCADE,
    occurrence_date TEXT NOT NULL,
    transaction_id TEXT NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, entry_id, occurrence_date)
);
CREATE UNIQUE INDEX uq_plan_fulfilments_txn ON plan_fulfilments(transaction_id);
