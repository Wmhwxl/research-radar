# Research Radar Architecture Audit

This document is the Phase 0 architecture audit for extending Daily Paper Reader into Research Radar:

> Domain-aware Academic Discovery and Dynamic Scholar Intelligence System

The goal is to preserve Daily Paper Reader's existing daily paper recommendation and reading workflow, then add a separate Research Intelligence layer for long-range field discovery, authors, institutions, venues, and collaboration graphs.

## 1. Current Architecture

Daily Paper Reader is a GitHub Actions + GitHub Pages research tool. It uses Python scripts for data collection, retrieval, ranking, LLM scoring, and markdown generation; the deployed user experience is a static Docsify site under `docs/` with browser-side configuration, AI chat, Zotero, and workflow controls.

Current layers:

| Layer | Main files | Current role |
| --- | --- | --- |
| Static frontend | `index.html`, `app/docsify-plugin.js`, `app/dpr-sidebar.js`, `app/subscriptions.manager.js`, `app/subscriptions.smart-query.js`, `app/workflows.runner.js` | Docsify paper reader, sidebar, subscription/profile management, workflow trigger UI, local/GitHub workflow dispatch, Zotero and AI chat |
| Pipeline orchestration | `src/main.py` | Sequential Step 0-6 daily pipeline runner; controls fetch window, long-range mode, Supabase skip-fetch behavior, and profile filtering |
| Research profile parsing | `src/subscription_plan.py` | Converts `config.yaml` `subscriptions.intent_profiles` into BM25 queries, embedding queries, context queries, tags, and per-profile `paper_sources` |
| Source routing | `src/source_config.py`, `src/source_backend_router.py`, `src/supabase_source.py` | Resolves per-source Supabase backend config, routes queries by source, calls Supabase REST/RPC, merges multi-source query results |
| Retrieval | `src/2.1.retrieval_papers_bm25.py`, `src/2.2.retrieval_papers_embedding.py`, `src/2.3.retrieval_papers_rrf.py` | BM25 recall, embedding recall, and RRF fusion into a ranked candidate pool |
| Rerank | `src/3.rank_papers.py`, `src/reranker_api.py`, `src/model_loader.py` | Local or remote Qwen reranking; global candidate pool with RRF, lane guarantees, and budget controls |
| LLM relevance | `src/4.llm_refine_papers.py`, `src/llm.py` | DeepSeek/OpenAI-compatible structured scoring, bilingual evidence, TLDR, title translation, retry/recovery |
| Selection | `src/5.select_papers.py` | Deep/quick selection, carryover, seen-id filtering, per-mode caps, output to `archive/<date>/recommend/` |
| Docs generation | `src/6.generate_docs.py`, `src/paper_figures.py`, `src/daily_report_state.py` | Paper markdown pages, daily reports, home dashboard, sidebar merge, full-text fetch, figures/tables, daily state |
| Maintenance ingestion | `src/maintain/*`, `src/maintain/fetchers/*` | arXiv, bioRxiv, medRxiv, ChemRxiv, OpenReview/conference fetchers, embedding, Supabase sync and cleanup |
| Database SQL | `sql/*.sql` | One paper table per source, pgvector columns, FTS/RPC match functions, anon read policies |
| Automation | `.github/workflows/*.yml` | Daily recommendation, Supabase maintenance, conference retrieval, topic research, starter pack, sync, reset |
| Tests | `tests/*` | Python and JS regression tests for pipeline contracts, SQL contracts, frontend behavior, topic research, sync |

The main daily data flow is:

```text
config.yaml intent_profiles
  -> src/subscription_plan.py
  -> Step 1 fetch or Supabase read
  -> Step 2.1 BM25
  -> Step 2.2 embedding
  -> Step 2.3 RRF
  -> Step 3 reranker
  -> Step 4 LLM relevance
  -> Step 5 selection
  -> Step 6 docs generation
  -> docs/ static site
```

Important archive contract:

```text
archive/<DPR_RUN_DATE>/raw/
archive/<DPR_RUN_DATE>/filtered/
archive/<DPR_RUN_DATE>/rank/
archive/<DPR_RUN_DATE>/recommend/
```

`DPR_RUN_DATE` is an implicit path bus shared by all steps. Any Research Radar task should avoid overloading this daily contract unless it is intentionally feeding the existing reader pipeline.

## 2. Existing Features We Can Reuse

Research Radar should reuse these existing capabilities instead of rebuilding them:

- Research profile input: `subscriptions.intent_profiles` already has `tag`, `description`, `keywords`, `intent_queries`, `enabled`, `paused`, `temporary`, `scope`, `conference_only`, and `paper_sources`.
- Source backend abstraction: `source_config.py` and `source_backend_router.py` already support source keys and per-source Supabase backends.
- BM25 retrieval: `2.1.retrieval_papers_bm25.py` supports local BM25, Supabase BM25 RPC, source routing, date windows, shard fallback, and dynamic top-k.
- Embedding retrieval: `2.2.retrieval_papers_embedding.py` supports query embedding cache, Supabase exact vector RPC, source routing, date-window sharding, and local fallback.
- RRF fusion: `2.3.retrieval_papers_rrf.py` aligns BM25 and embedding lanes by stable query keys and fuses scores with `1 / (60 + rank)`.
- Reranker: `3.rank_papers.py` supports local Qwen3, public zwwen, SiliconFlow, global candidate pools, and configurable budgets.
- LLM relevance refinement: `4.llm_refine_papers.py` already generates field-specific relevance scores and explanations; useful for first-version historical `field_relevance_score`.
- Paper reading UI: `6.generate_docs.py`, `docsify-plugin.js`, and `dpr-sidebar.js` already provide paper pages, markdown rendering, AI reading, and reading state.
- Supabase pgvector/FTS: existing paper tables use `embedding vector(384)` and FTS RPC functions; Research Radar should add graph/intelligence tables alongside them.
- GitHub Actions/local dispatch: `workflows.runner.js` and `local_debug_server.py` already map frontend workflow actions to GitHub Actions or local Python commands.
- Zotero: `zotero-meta-utils.js` and page citation metadata should stay unchanged and can be reused by historical paper detail pages.

## 3. Current Limitations

Current limitations relative to Research Radar:

- Papers are the only first-class academic entity. Authors are stored as `authors jsonb` arrays in source paper tables.
- There is no stable author identity table, no OpenAlex author ID, and no ORCID/Semantic Scholar/DBLP identity fields.
- There is no normalized institution table, venue table, topic table, or paper-author join table.
- Current source tables are source-specific and paper-centric; they do not model one paper belonging to multiple research fields.
- Historical field discovery is currently implemented as arXiv/topic windows and starter packs, not as a structured five-year academic metadata sync.
- OpenAlex is listed as future work in `TODO.md`, but no `OpenAlexProvider` exists.
- Current deduplication is mostly ID/source oriented; multi-source DOI/OpenAlex/arXiv/title-year dedupe is not yet centralized.
- Collaboration graphs do not exist. Coauthor data cannot be queried without parsing per-paper JSON authors.
- Current SQL RPC functions return paper metadata only; they do not expose field stats, author stats, or graph edges.
- Frontend is a static Docsify app. Adding graph pages must fit this architecture rather than introducing a separate SPA framework.

## 4. Research Radar Target Architecture

Research Radar should be added as a parallel system that shares Research Profiles but does not replace Daily Paper Stream.

```text
Research Profile / Research Field
  |
  +-- Daily Paper Stream
  |     existing arXiv/OpenReview/Supabase -> BM25 -> embedding -> RRF -> rerank -> LLM -> docs
  |
  +-- Research Intelligence
        OpenAlexProvider
          -> normalized papers/authors/institutions/venues/topics
          -> research_field_papers
          -> paper_authors
          -> author_collaborations
          -> Field Explorer / Author List / Scholar Graph
```

The first Research Radar phase should add:

- A `ResearchField` model derived from but more explicit than `intent_profiles`.
- A provider layer under `src/providers/`, with `OpenAlexProvider` as the only concrete first implementation.
- A historical sync module under `src/research_radar/`.
- New additive Supabase tables for fields, normalized entities, relationships, sync runs, stats, and graph edges.
- New static frontend modules under `app/` that integrate with the existing Docsify shell.
- New GitHub Actions/local workflow entry for historical sync.

Do not alter Daily Paper Stream file contracts in MVP-1. Historical sync should write to Research Radar tables and frontend data endpoints, not to `archive/<date>/recommend/` unless explicitly projecting selected papers into the existing reader.

## 5. Database Migration Plan

Use additive migrations. Do not drop or rewrite existing source paper tables.

Recommended new SQL file:

```text
sql/create_research_radar_schema.sql
```

Core tables:

```sql
research_fields (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text not null unique,
  description text,
  core_keywords jsonb not null default '[]'::jsonb,
  optional_keywords jsonb not null default '[]'::jsonb,
  excluded_keywords jsonb not null default '[]'::jsonb,
  intent_queries jsonb not null default '[]'::jsonb,
  seed_papers jsonb not null default '[]'::jsonb,
  seed_authors jsonb not null default '[]'::jsonb,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

academic_papers (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  normalized_title text not null,
  abstract text,
  doi text,
  arxiv_id text,
  openalex_id text unique,
  semantic_scholar_id text,
  dblp_id text,
  publication_date date,
  year int,
  venue_id uuid,
  citation_count int,
  url text,
  pdf_url text,
  source text,
  source_ids jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

authors (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  normalized_name text not null,
  openalex_id text unique,
  semantic_scholar_id text,
  orcid text,
  dblp_id text,
  homepage text,
  works_count int,
  citation_count int,
  primary_institution_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

institutions (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  openalex_id text unique,
  country text,
  ror_id text,
  type text,
  homepage text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

venues (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  short_name text,
  type text,
  issn jsonb,
  publisher text,
  ccf_rank text,
  core_rank text,
  quartile text,
  openalex_id text unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

paper_authors (
  paper_id uuid not null references academic_papers(id) on delete cascade,
  author_id uuid not null references authors(id) on delete cascade,
  author_position text,
  author_order int,
  is_corresponding boolean,
  raw_affiliation text,
  institution_id uuid references institutions(id),
  primary key (paper_id, author_id)
);

research_field_papers (
  research_field_id uuid not null references research_fields(id) on delete cascade,
  paper_id uuid not null references academic_papers(id) on delete cascade,
  relevance_score float8,
  discovery_source text,
  first_discovered_at timestamptz not null default now(),
  latest_seen_at timestamptz not null default now(),
  primary key (research_field_id, paper_id)
);

author_collaborations (
  research_field_id uuid not null references research_fields(id) on delete cascade,
  author_a_id uuid not null references authors(id) on delete cascade,
  author_b_id uuid not null references authors(id) on delete cascade,
  total_collaboration_count int not null default 0,
  field_collaboration_count int not null default 0,
  first_collaboration_year int,
  latest_collaboration_year int,
  latest_collaboration_date date,
  weighted_score float8,
  updated_at timestamptz not null default now(),
  primary key (research_field_id, author_a_id, author_b_id),
  check (author_a_id < author_b_id)
);
```

Reserved for MVP-1 or near-follow-up:

```sql
topics
paper_topics
research_field_sync_runs
author_collaboration_papers
```

Compatibility approach:

- Existing `arxiv_papers`, `biorxiv_papers`, `*_openreview_papers`, conference tables, and `papers` remain unchanged.
- Existing RPC functions remain unchanged.
- Research Radar may link imported OpenAlex papers to existing source tables by DOI, arXiv ID, OpenAlex ID, or normalized title/year, but should not require existing tables to be rewritten.
- RLS/read policy should expose only read-safe Research Radar tables/functions to `anon`; writes should require service key in sync workflow.

## 6. OpenAlex Provider Design

Recommended new files:

```text
src/providers/__init__.py
src/providers/base.py
src/providers/openalex.py
src/research_radar/models.py
src/research_radar/normalization.py
```

Provider interface:

```python
class AcademicProvider(Protocol):
    name: str

    def search_works(
        self,
        *,
        query: str,
        from_publication_date: date,
        to_publication_date: date,
        per_page: int = 100,
        cursor: str = "*",
    ) -> ProviderPage[NormalizedPaper]:
        ...
```

As of the current OpenAlex API contract checked for Phase 2, `per_page=100` is the supported maximum. `per_page=200` was legacy behavior and should not be used for Research Radar.

Normalized DTOs:

```text
NormalizedPaper
NormalizedAuthor
NormalizedInstitution
NormalizedVenue
NormalizedTopic
```

OpenAlex mapping:

- Work ID -> `academic_papers.openalex_id`
- Work title -> `title`, `normalized_title`
- Work abstract inverted index -> `abstract`
- DOI -> `doi`
- `ids.arxiv` -> `arxiv_id`
- `primary_location.source` -> `venues`
- `authorships[].author.id` -> `authors.openalex_id`
- `authorships[].institutions[]` -> `institutions`
- `concepts` or `topics` -> `topics` / `paper_topics`
- `cited_by_count` -> `citation_count`
- `publication_date`, `publication_year`

Provider requirements:

- Cursor pagination.
- Historical sync must persist `meta.next_cursor` checkpoints so interrupted field discovery can resume without restarting the date window.
- Request timeout.
- Retry on 429/5xx with backoff.
- Optional polite email via `.env`, e.g. `OPENALEX_MAILTO`.
- Per-query and global page limits.
- Partial failure accounting.
- No direct insertion of raw OpenAlex JSON into core database rows.

## 7. Historical Sync Pipeline

Recommended command:

```text
python -m research_radar.sync_field_history --field-id <uuid> --years 5
```

Pipeline:

```text
Load research field
  -> build constrained OpenAlex queries
  -> fetch candidate works by year/date range
  -> normalize provider responses
  -> deduplicate papers
  -> upsert venues
  -> upsert institutions
  -> upsert authors
  -> upsert academic_papers
  -> upsert paper_authors
  -> compute first relevance score
  -> upsert research_field_papers
  -> rebuild author_collaborations for field
  -> record sync run stats
```

For the demo field `Incomplete Multimodal Recommendation`, query construction should avoid simple OR. First version should combine recommendation constraints with missing/modality constraints:

```text
(multimodal OR multi-modal)
AND (recommendation OR recommender OR recommenders)
AND (missing OR incomplete OR partial OR modality OR modalities OR completion)
```

Also use intent queries such as:

```text
papers studying multimodal recommender systems under missing modality conditions
methods for completing or estimating missing modalities in multimodal recommendation
robust multimodal recommendation with incomplete visual text or audio information
recommendation methods handling partially observed multimodal features
```

First-version relevance score:

```text
field_relevance_score =
  0.6 * constrained_keyword_score
  + 0.4 * existing semantic/rerank/LLM score when available
```

MVP-1 can start with a deterministic keyword/topic score, then optionally route candidate abstracts through existing Step 2/3/4 utilities in a later refinement. The important contract is to store the score in `research_field_papers.relevance_score` and keep raw provider matching evidence in sync-run logs or JSON debug artifacts.

Sync logging must include:

```text
field
date range
provider
queries
candidates retrieved
papers inserted
papers updated
authors inserted
institutions inserted
venues inserted
paper-author links inserted
collaborations created/updated
duplicates skipped
failures
partial failures
duration
```

Incremental sync:

- Initial sync defaults to 5 years.
- Store `research_field_sync_runs` with `started_at`, `completed_at`, `from_date`, `to_date`, provider, status, and counters.
- Later syncs use last successful `completed_at` / `to_date` and fetch only deltas.
- Do not implement five years as daily retrieval x 1825.

## 8. Scholar Graph Design

Database graph source:

- Nodes come from `authors`.
- Node size is author paper count in `research_field_papers` joined through `paper_authors`.
- Edges come from `author_collaborations`.
- Edge thickness is `field_collaboration_count` in MVP-1.
- Edge detail comes from a join table or query joining shared `paper_authors`.

Recommended SQL/RPC additions:

```text
sql/research_radar_graph_rpc.sql
```

Functions:

```text
get_research_field_overview(field_id, start_year, end_year)
get_research_field_papers(field_id, start_year, end_year, sort, filters)
get_research_field_authors(field_id, start_year, end_year)
get_research_field_scholar_graph(field_id, start_year, end_year, max_nodes)
get_author_detail(field_id, author_id, start_year, end_year)
get_collaboration_detail(field_id, author_a_id, author_b_id, start_year, end_year)
```

Frontend:

- Prefer Cytoscape.js for quick integration and robust interactions in a static page. Sigma.js is also viable, but Cytoscape has simpler node/edge event APIs and layout options for a few hundred to few thousand nodes.
- Add vendor asset under `app/vendor/cytoscape/` or use a local vendored minified file to match current offline/vendor style.
- Add `app/research-radar.js` and `app/research-radar.css`.
- Add Docsify route/page under `docs/research-radar/README.md` or a generated static shell that the JS module enhances.

Interactions:

- Zoom and pan from graph library.
- Hover shows compact author/edge tooltip.
- Node click opens side panel with author metadata, field paper count, recent papers, and top collaborators.
- Edge click opens side panel with coauthored papers and first/latest collaboration years.
- Start/end year filters in MVP-1; slider can be a later UI improvement.

No fake graph data in production. If demo data is needed, put it under `fixtures/research_radar/` and gate it behind an explicit demo flag.

## 9. File-level Modification Plan

Files to modify in Phase 1-5:

| File | Change |
| --- | --- |
| `.env.example` | Add `OPENALEX_MAILTO`, OpenAlex timeout/page limit envs, and Research Radar sync options |
| `requirements.txt` | Add only lightweight dependencies if needed; `requests` already exists, so MVP may need no new Python dependency |
| `config.yaml` | Add optional example `research_fields` only if needed; avoid modifying user runtime config by default |
| `src/source_config.py` | Possibly register OpenAlex as a metadata provider key, but avoid mixing provider metadata with existing Supabase paper-source backends unless necessary |
| `src/local_debug_server.py` | Map a new local Research Radar sync workflow to a Python command |
| `app/workflows.runner.js` | Add Research Radar sync workflow action, after backend exists |
| `index.html` | Load Research Radar JS/CSS only after the module exists |
| `app/app.css` | Add restrained styles for Field Explorer if not isolated in `research-radar.css` |
| `docs/_sidebar.md` or generator/templates | Add Research Radar entry only through stable template/generator path, not runtime docs churn |
| `README.md` | Later add Research Radar extension docs only after MVP behavior exists; preserve attribution/license |

New files to create:

```text
docs/RESEARCH_RADAR_ARCHITECTURE.md
sql/create_research_radar_schema.sql
sql/research_radar_graph_rpc.sql
src/providers/__init__.py
src/providers/base.py
src/providers/openalex.py
src/research_radar/__init__.py
src/research_radar/models.py
src/research_radar/normalization.py
src/research_radar/relevance.py
src/research_radar/dedupe.py
src/research_radar/db.py
src/research_radar/sync_field_history.py
src/research_radar/collaboration.py
src/research_radar/field_seed.py
app/research-radar.js
app/research-radar.css
docs/research-radar/README.md
.github/workflows/research-radar-sync.yml
tests/test_research_radar_openalex_provider.py
tests/test_research_radar_normalization.py
tests/test_research_radar_dedupe.py
tests/test_research_radar_collaboration.py
tests/test_research_radar_sql_contract.py
tests/test_research_radar_frontend.js
```

Files to keep untouched in MVP-1 unless a compatibility issue is proven:

```text
src/main.py
src/2.1.retrieval_papers_bm25.py
src/2.2.retrieval_papers_embedding.py
src/2.3.retrieval_papers_rrf.py
src/3.rank_papers.py
src/4.llm_refine_papers.py
src/5.select_papers.py
src/6.generate_docs.py
src/maintain/sync.py
existing sql/create_*_papers_schema.sql
existing sql/match_*_papers.sql
app/docsify-plugin.js
app/dpr-sidebar.js
app/zotero-*.js
```

These files are core Daily Paper Reader contracts. If later integration requires touching them, make narrow, tested changes only.

## 10. MVP Implementation Order

MVP-1 should proceed in small phases:

1. Phase 0: architecture audit. This document.
2. Phase 1: additive SQL schema and SQL contract tests.
3. Phase 2: provider interface and OpenAlexProvider with unit tests and one real request smoke test.
4. Phase 3: normalization, dedupe, and database upsert layer.
5. Phase 4: `sync_field_history(field_id)` for 5-year historical discovery, with sync-run counters and failure accounting.
6. Phase 5: collaboration builder from `paper_authors`, with deterministic ordering of `author_a_id < author_b_id`.
7. Phase 6: read RPCs for overview, papers, authors, and graph.
8. Phase 7: Field Explorer frontend tabs: Overview, Papers, Authors.
9. Phase 8: Scholar Graph frontend with node click and edge click detail panels.
10. Phase 9: integration workflow and local debug dispatch.
11. Phase 10: README extension docs after functionality is verified.

## 11. Compatibility Risks

Key risks and mitigations:

- Risk: Breaking daily recommendations by changing `intent_profiles`.
  - Mitigation: Add `research_fields` as a separate config/database concept; only map from existing profiles, do not rewrite them.
- Risk: Existing `authors jsonb` conflicts with normalized authors.
  - Mitigation: Keep source tables unchanged. Use new `authors` and `paper_authors` tables for Research Radar only.
- Risk: Duplicate paper records across OpenAlex/arXiv/conferences.
  - Mitigation: Centralize dedupe by DOI, OpenAlex ID, arXiv ID, then normalized title + year.
- Risk: Supabase schema changes affect old forks.
  - Mitigation: New SQL files are optional and additive. Existing workflows should not require Research Radar tables unless Research Radar sync is explicitly enabled.
- Risk: Public anon access exposes too much data.
  - Mitigation: Expose read-only aggregate/detail RPCs; keep sync/upsert service-key only.
- Risk: Graph data is expensive to compute in browser.
  - Mitigation: Precompute `author_collaborations` and serve filtered graph JSON from SQL/RPC.
- Risk: OpenAlex results are broad/noisy.
  - Mitigation: Use constrained query construction and relevance scoring; do not rely on `missing modality` alone.
- Risk: Static frontend becomes too large.
  - Mitigation: Lazy-load graph library and Research Radar assets only on Research Radar routes.
- Risk: No stable author identity for non-OpenAlex sources.
  - Mitigation: MVP uses OpenAlex Author ID first; only use normalized names for display/fallback, not identity merge.
- Risk: Long-running sync exceeds GitHub Actions limits.
  - Mitigation: Cursor pagination, page limits, incremental sync, persisted sync runs, and partial failure logs.

## 12. Testing Plan

Minimum tests before Phase 1 is considered done:

```text
python -m pytest tests/test_research_radar_sql_contract.py
python -m pytest tests/test_research_radar_normalization.py
python -m pytest tests/test_research_radar_dedupe.py
```

Minimum tests before OpenAlex Provider is considered done:

```text
python -m pytest tests/test_research_radar_openalex_provider.py
```

Smoke test with real OpenAlex request:

```text
python -m src.research_radar.sync_field_history --field-slug incomplete-multimodal-recommendation --years 1 --dry-run --max-pages 1
```

Minimum tests before graph is considered done:

```text
python -m pytest tests/test_research_radar_collaboration.py
python -m pytest tests/test_research_radar_sql_contract.py
node tests/test_research_radar_frontend.js
```

Full compatibility check after each phase:

```text
python -m pytest tests/test_main_pipeline.py tests/test_subscription_plan.py tests/test_source_config.py
python -m pytest tests/test_sync_workflow_contract.py tests/test_supabase_init_and_sync.py
node tests/test_subscriptions_manager.js
node tests/test_dpr_sidebar_v2.js
```

Before declaring MVP complete:

- Run lint/test/build equivalent available in this repo.
- Run at least one real OpenAlex request.
- Run a dry historical sync for `Incomplete Multimodal Recommendation`.
- Verify inserted authors use OpenAlex Author ID and are not duplicated by name variants.
- Verify existing Daily Paper Reader workflow files still pass contract tests.
- Verify existing docs/reader/Zotero frontend behavior is not touched by Research Radar assets.
