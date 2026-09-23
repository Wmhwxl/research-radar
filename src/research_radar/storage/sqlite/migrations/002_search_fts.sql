CREATE TABLE IF NOT EXISTS paper_search_documents (
  paper_id TEXT PRIMARY KEY REFERENCES academic_papers(id) ON DELETE CASCADE,
  title TEXT NOT NULL DEFAULT '',
  abstract TEXT NOT NULL DEFAULT '',
  venue_name TEXT NOT NULL DEFAULT '',
  author_names TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS paper_search_fts USING fts5(
  paper_id UNINDEXED,
  title,
  abstract,
  venue_name,
  author_names
);
