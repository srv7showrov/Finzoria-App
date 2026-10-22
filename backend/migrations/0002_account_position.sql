-- Explicit, stable display order for accounts. Seeded accounts share one created_at
-- and have random IDs, so neither can define order.
ALTER TABLE accounts ADD COLUMN position INTEGER NOT NULL DEFAULT 0;

-- Backfill existing rows in their original insertion order within each workspace.
UPDATE accounts SET position = (
    SELECT COUNT(*) FROM accounts AS earlier
    WHERE earlier.workspace_id = accounts.workspace_id
      AND (earlier.created_at < accounts.created_at
           OR (earlier.created_at = accounts.created_at AND earlier.rowid < accounts.rowid))
);
