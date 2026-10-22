-- Stage C: AI assistant conversations, concise tool activity, pending actions that only
-- the user can confirm, funding application tracker and checklist state.

CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_conversations_ws ON conversations(workspace_id, updated_at);

-- Final user/assistant texts only. Hidden reasoning and raw provider payloads are never stored.
CREATE TABLE assistant_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('concise', 'detailed')),
    language TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ok', 'failed', 'refused', 'incomplete')),
    error_code TEXT,
    model TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_assistant_messages_conv ON assistant_messages(conversation_id, id);

-- Tool name, validated input and a concise result; enough to audit, nothing secret.
CREATE TABLE assistant_tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    message_id INTEGER REFERENCES assistant_messages(id) ON DELETE CASCADE,
    round INTEGER NOT NULL,
    tool_name TEXT NOT NULL,
    input_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ok', 'error', 'rejected')),
    created_at TEXT NOT NULL
);
CREATE INDEX idx_tool_calls_conv ON assistant_tool_calls(conversation_id, id);

-- Changes prepared by the assistant. Nothing is saved until the user confirms in the UI.
CREATE TABLE assistant_actions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    kind TEXT NOT NULL CHECK (kind IN ('budget_entry', 'bill', 'contribution')),
    payload TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'confirmed', 'dismissed', 'failed')),
    result_id TEXT,
    status_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_assistant_actions_ws ON assistant_actions(workspace_id, status);

CREATE TABLE funding_applications (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (status IN ('planning', 'applied', 'awarded', 'declined', 'withdrawn')),
    deadline TEXT,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_funding_applications_ws ON funding_applications(workspace_id);

CREATE TABLE checklist_state (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    item_key TEXT NOT NULL,
    done INTEGER NOT NULL CHECK (done IN (0, 1)),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, item_key)
);
