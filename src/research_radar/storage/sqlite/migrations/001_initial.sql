CREATE TABLE IF NOT EXISTS research_fields (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL CHECK (length(trim(name)) > 0),
  slug TEXT NOT NULL UNIQUE CHECK (length(trim(slug)) > 0),
  description TEXT,
  core_keywords TEXT NOT NULL DEFAULT '[]',
  optional_keywords TEXT NOT NULL DEFAULT '[]',
  excluded_keywords TEXT NOT NULL DEFAULT '[]',
  intent_queries TEXT NOT NULL DEFAULT '[]',
  seed_papers TEXT NOT NULL DEFAULT '[]',
  seed_authors TEXT NOT NULL DEFAULT '[]',
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS institutions (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL CHECK (length(trim(name)) > 0),
  openalex_id TEXT,
  country TEXT,
  ror_id TEXT,
  type TEXT,
  homepage TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS venues (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL CHECK (length(trim(name)) > 0),
  short_name TEXT,
  type TEXT,
  issn TEXT NOT NULL DEFAULT '[]',
  publisher TEXT,
  ccf_rank TEXT,
  core_rank TEXT,
  quartile TEXT,
  openalex_id TEXT,
  homepage TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS academic_papers (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL CHECK (length(trim(title)) > 0),
  normalized_title TEXT NOT NULL CHECK (length(trim(normalized_title)) > 0),
  abstract TEXT,
  doi TEXT,
  arxiv_id TEXT,
  openalex_id TEXT,
  semantic_scholar_id TEXT,
  dblp_id TEXT,
  publication_date TEXT,
  year INTEGER,
  work_type TEXT,
  venue_id TEXT REFERENCES venues(id) ON DELETE SET NULL,
  citation_count INTEGER NOT NULL DEFAULT 0 CHECK (citation_count >= 0),
  url TEXT,
  pdf_url TEXT,
  source TEXT,
  source_ids TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS authors (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL CHECK (length(trim(name)) > 0),
  normalized_name TEXT NOT NULL CHECK (length(trim(normalized_name)) > 0),
  openalex_id TEXT,
  semantic_scholar_id TEXT,
  orcid TEXT,
  dblp_id TEXT,
  homepage TEXT,
  works_count INTEGER CHECK (works_count IS NULL OR works_count >= 0),
  citation_count INTEGER CHECK (citation_count IS NULL OR citation_count >= 0),
  primary_institution_id TEXT REFERENCES institutions(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS paper_authors (
  paper_id TEXT NOT NULL REFERENCES academic_papers(id) ON DELETE CASCADE,
  author_id TEXT NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
  author_position TEXT,
  author_order INTEGER CHECK (author_order IS NULL OR author_order > 0),
  is_corresponding INTEGER,
  raw_affiliation TEXT,
  institution_id TEXT REFERENCES institutions(id) ON DELETE SET NULL,
  PRIMARY KEY (paper_id, author_id)
);

CREATE TABLE IF NOT EXISTS paper_author_institutions (
  paper_id TEXT NOT NULL REFERENCES academic_papers(id) ON DELETE CASCADE,
  author_id TEXT NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
  institution_id TEXT NOT NULL REFERENCES institutions(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (paper_id, author_id, institution_id)
);

CREATE TABLE IF NOT EXISTS research_field_papers (
  research_field_id TEXT NOT NULL REFERENCES research_fields(id) ON DELETE CASCADE,
  paper_id TEXT NOT NULL REFERENCES academic_papers(id) ON DELETE CASCADE,
  relevance_score REAL CHECK (relevance_score IS NULL OR (relevance_score >= 0 AND relevance_score <= 1)),
  relevance_label TEXT CHECK (relevance_label IS NULL OR relevance_label IN ('core', 'related')),
  relevance_evidence TEXT NOT NULL DEFAULT '{}',
  discovery_source TEXT,
  first_discovered_at TEXT NOT NULL DEFAULT (datetime('now')),
  latest_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (research_field_id, paper_id)
);

CREATE TABLE IF NOT EXISTS research_field_sync_runs (
  id TEXT PRIMARY KEY,
  research_field_id TEXT NOT NULL REFERENCES research_fields(id) ON DELETE CASCADE,
  provider TEXT NOT NULL CHECK (length(trim(provider)) > 0),
  status TEXT NOT NULL CHECK (length(trim(status)) > 0),
  from_date TEXT,
  to_date TEXT,
  started_at TEXT NOT NULL DEFAULT (datetime('now')),
  completed_at TEXT,
  queries TEXT NOT NULL DEFAULT '[]',
  checkpoint TEXT NOT NULL DEFAULT '{}',
  candidates_retrieved INTEGER NOT NULL DEFAULT 0,
  papers_inserted INTEGER NOT NULL DEFAULT 0,
  papers_updated INTEGER NOT NULL DEFAULT 0,
  authors_inserted INTEGER NOT NULL DEFAULT 0,
  institutions_inserted INTEGER NOT NULL DEFAULT 0,
  venues_inserted INTEGER NOT NULL DEFAULT 0,
  paper_author_links_inserted INTEGER NOT NULL DEFAULT 0,
  collaborations_created INTEGER NOT NULL DEFAULT 0,
  duplicates_skipped INTEGER NOT NULL DEFAULT 0,
  failures INTEGER NOT NULL DEFAULT 0,
  partial_failures INTEGER NOT NULL DEFAULT 0,
  accepted_core INTEGER NOT NULL DEFAULT 0,
  accepted_related INTEGER NOT NULL DEFAULT 0,
  rejected INTEGER NOT NULL DEFAULT 0,
  error_summary TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS author_collaborations (
  research_field_id TEXT NOT NULL REFERENCES research_fields(id) ON DELETE CASCADE,
  author_a_id TEXT NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
  author_b_id TEXT NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
  total_collaboration_count INTEGER NOT NULL DEFAULT 0 CHECK (total_collaboration_count >= 0),
  field_collaboration_count INTEGER NOT NULL DEFAULT 0 CHECK (field_collaboration_count >= 0),
  first_collaboration_year INTEGER,
  latest_collaboration_year INTEGER,
  latest_collaboration_date TEXT,
  weighted_score REAL,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (research_field_id, author_a_id, author_b_id),
  CHECK (author_a_id < author_b_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS institutions_openalex_id_unique ON institutions(openalex_id) WHERE openalex_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS institutions_ror_id_unique ON institutions(ror_id) WHERE ror_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS venues_openalex_id_unique ON venues(openalex_id) WHERE openalex_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS academic_papers_openalex_id_unique ON academic_papers(openalex_id) WHERE openalex_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS academic_papers_doi_unique ON academic_papers(doi) WHERE doi IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS academic_papers_arxiv_id_unique ON academic_papers(arxiv_id) WHERE arxiv_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS authors_openalex_id_unique ON authors(openalex_id) WHERE openalex_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS authors_orcid_unique ON authors(orcid) WHERE orcid IS NOT NULL;

CREATE INDEX IF NOT EXISTS academic_papers_year_idx ON academic_papers(year);
CREATE INDEX IF NOT EXISTS academic_papers_publication_date_idx ON academic_papers(publication_date);
CREATE INDEX IF NOT EXISTS academic_papers_venue_id_idx ON academic_papers(venue_id);
CREATE INDEX IF NOT EXISTS academic_papers_normalized_title_year_idx ON academic_papers(normalized_title, year);
CREATE INDEX IF NOT EXISTS authors_normalized_name_idx ON authors(normalized_name);
CREATE INDEX IF NOT EXISTS authors_primary_institution_id_idx ON authors(primary_institution_id);
CREATE INDEX IF NOT EXISTS paper_authors_author_id_idx ON paper_authors(author_id);
CREATE INDEX IF NOT EXISTS paper_authors_institution_id_idx ON paper_authors(institution_id);
CREATE INDEX IF NOT EXISTS paper_author_institutions_author_id_idx ON paper_author_institutions(author_id);
CREATE INDEX IF NOT EXISTS paper_author_institutions_institution_id_idx ON paper_author_institutions(institution_id);
CREATE INDEX IF NOT EXISTS research_field_papers_paper_id_idx ON research_field_papers(paper_id);
CREATE INDEX IF NOT EXISTS research_field_papers_field_relevance_idx ON research_field_papers(research_field_id, relevance_score DESC);
CREATE INDEX IF NOT EXISTS research_field_sync_runs_field_started_idx ON research_field_sync_runs(research_field_id, started_at DESC);
CREATE INDEX IF NOT EXISTS research_field_sync_runs_field_status_idx ON research_field_sync_runs(research_field_id, status);
CREATE INDEX IF NOT EXISTS author_collaborations_field_idx ON author_collaborations(research_field_id);
