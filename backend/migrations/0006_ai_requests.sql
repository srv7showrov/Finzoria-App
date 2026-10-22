-- One row per model request attempt made by this app (chat rounds, invoice extraction,
-- connection checks), including failed attempts. Used for local request guards and for
-- reporting counts. It is NOT the provider's quota.
CREATE TABLE ai_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT REFERENCES workspaces(id) ON DELETE CASCADE,
    at TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    purpose TEXT NOT NULL CHECK (purpose IN ('chat', 'invoice', 'check')),
    ok INTEGER NOT NULL CHECK (ok IN (0, 1)),
    error_code TEXT
);
CREATE INDEX idx_ai_requests_at ON ai_requests(at);

ALTER TABLE assistant_messages ADD COLUMN model_requests INTEGER NOT NULL DEFAULT 0;
