ALTER TABLE research_fields ADD COLUMN auto_sync INTEGER NOT NULL DEFAULT 1;
ALTER TABLE research_fields ADD COLUMN sync_frequency TEXT NOT NULL DEFAULT 'daily';
ALTER TABLE research_fields ADD COLUMN last_visited_at TEXT;

CREATE INDEX IF NOT EXISTS research_fields_enabled_auto_sync_idx
  ON research_fields(enabled, auto_sync, sync_frequency);

CREATE INDEX IF NOT EXISTS research_field_papers_first_discovered_idx
  ON research_field_papers(research_field_id, first_discovered_at);
