-- Finzoria schema v1: demo workspaces, sessions, profile, preferences, accounts.
-- Money is stored as decimal strings; timestamps are UTC ISO-8601 instants.

CREATE TABLE workspaces (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    data_mode TEXT NOT NULL DEFAULT 'demo' CHECK (data_mode IN ('demo'))
);

CREATE TABLE sessions (
    token_hash TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX idx_sessions_workspace ON sessions(workspace_id);

CREATE TABLE profiles (
    workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL,
    institution TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE preferences (
    workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    language TEXT NOT NULL,
    display_currency TEXT NOT NULL,
    time_zone TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE accounts (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    currency TEXT NOT NULL,
    opening_balance TEXT NOT NULL,
    opening_date TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_accounts_workspace ON accounts(workspace_id);

-- Sanitized record of runtime model connection checks (no secrets, no prompts).
CREATE TABLE ai_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at TEXT NOT NULL,
    model TEXT NOT NULL,
    ok INTEGER NOT NULL CHECK (ok IN (0, 1)),
    outcome TEXT NOT NULL
);
