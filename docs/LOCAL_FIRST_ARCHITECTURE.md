# Research Radar Local-First Architecture

## Product Direction

Research Radar is evolving into a local-first academic search and scholar intelligence engine. A researcher must be able to install and use the open-source application without creating a Supabase account, operating PostgreSQL, running SQL manually, or exposing cloud credentials.

The default deployment model is:

```text
Browser
  -> localhost Research Radar server
  -> local application services
  -> SQLite database and local data directory
```

`localhost` is the supported product runtime, not a development workaround. Direct `file://` access is not supported because routing, API requests, fixtures, and dynamic assets require an HTTP environment.

## Architecture Principles

1. **Local-first, cloud-optional.** SQLite is the default storage backend. Supabase remains an optional deployment backend.
2. **One domain model.** SQLite and Supabase map the same Research Radar entities and normalized OpenAlex DTOs.
3. **Backend-neutral business logic.** Discovery, relevance filtering, deduplication, historical sync, checkpoints, and collaboration building depend on repository contracts, not transport details.
4. **No secrets in the browser.** Local API and Supabase browser clients are read-only. Service credentials stay in the backend process.
5. **Automatic first run.** A future `research-radar start` command owns local directory creation, migrations, server startup, and browser opening.
6. **Portable runtime.** The supported target is Python 3.11+ on Windows, macOS, and Linux without required Docker, PostgreSQL, Redis, or Neo4j.

## Target Components

```text
OpenAlexProvider
  -> normalized domain DTOs
  -> discovery and sync services
  -> ResearchRadarRepository
       -> SQLiteRepository (default)
       -> SupabaseRepository (optional)

Research Radar UI
  -> ResearchRadarDataSource
       -> LocalApiDataSource (default product runtime)
       -> FixtureDataSource (development and tests)
       -> SupabaseDataSource (optional cloud read model)
```

Provider code must not be copied into repositories. Repositories persist and query normalized domain objects; providers retrieve and normalize external records.

## Local Data Directory

Runtime data belongs in a platform-appropriate user data directory, represented here as `~/.research-radar/`:

```text
~/.research-radar/
  research-radar.db
  config.toml
  logs/
  cache/
  papers/
  exports/
```

The database and generated user data must not be written into the Git repository or `docs/`.

## Storage Contract

The SQLite schema will map the existing academic model:

- `research_fields`
- `institutions`
- `venues`
- `academic_papers`
- `authors`
- `paper_authors`
- `paper_author_institutions`
- `research_field_papers`
- `research_field_sync_runs`
- `author_collaborations`

SQLite migrations will run automatically and be versioned independently from Supabase SQL migrations. FTS5 will provide the first local search backend over paper title, abstract, venue, and author names, with BM25 ranking and structured filters. Vector search remains a future optional `SearchBackend`; it is not a prerequisite for the first local release.

## Repository Boundary

Application services should depend on a single repository protocol that covers:

```text
field CRUD and lookup
paper, author, institution, and venue upserts
field paper and authorship associations
sync run creation and checkpoint updates
field overview, paper, and author read models
scholar graph and detail read models
collaboration rebuilds
paper and author search
```

Backend selection occurs once during application startup. Storage-specific conditionals must not spread into provider, relevance, sync, API, or UI code.

## Local API Boundary

The local server will provide stable JSON endpoints under `/api`, including health, fields, sync, overview, papers, authors, graph, details, and search. The current Phase 4 UI already consumes the matching `ResearchRadarDataSource` methods. `LocalApiDataSource` maps those methods to the planned endpoints without embedding storage knowledge in components.

The local API is responsible for write authorization, input validation, migrations, scheduling, and secrets. The browser does not access SQLite directly.

## Configuration And Secrets

The default `config.toml` will select `storage.backend = "sqlite"`. An OpenAlex API key is optional. Supabase URL and service credentials are only required when the user explicitly selects the Supabase backend, and service credentials never enter frontend assets or responses.

## Scheduling

A local scheduler abstraction will run while the server is active and perform catch-up checks on startup. GitHub Actions remains an optional deployment mechanism, not a dependency of the local product.

## Current Phase 4 Status

Phase 4A is backend-neutral:

- Overview, Papers, Authors, Scholar Graph, and detail drawers call only the DataSource interface.
- Fixture mode is explicit and visibly labelled; it cannot silently masquerade as production data.
- `LocalApiDataSource` and `SupabaseDataSource` are adapters, not UI dependencies.
- Time range, filters, graph limits, and URL state are expressed as adapter-neutral query values.

No SQLite database, local API server, scheduler, packaging, or CLI is implemented in Phase 4A. Those belong to Phase 5.

## Phase 5 Boundary

Phase 5 will implement the local data directory, SQLite migrations and repository, FTS5 search, local API, configuration, CLI commands, automatic browser startup, first-field onboarding, and scheduler. It must preserve the existing OpenAlex provider and normalized domain logic and must not modify the Daily Paper Reader core pipeline.
