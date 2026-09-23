-- ============================================================
-- Research Radar normalized academic entity schema
-- ============================================================
-- Additive migration only:
-- - Does not alter existing Daily Paper Reader paper tables.
-- - Does not replace existing retrieval RPCs.
-- - Provides normalized entities for field-level historical discovery.
-- ============================================================

create extension if not exists pgcrypto;

create or replace function public.set_research_radar_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists public.research_fields (
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
  updated_at timestamptz not null default now(),
  constraint research_fields_slug_not_blank check (length(btrim(slug)) > 0),
  constraint research_fields_name_not_blank check (length(btrim(name)) > 0)
);

create table if not exists public.institutions (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  openalex_id text,
  country text,
  ror_id text,
  type text,
  homepage text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint institutions_name_not_blank check (length(btrim(name)) > 0)
);

create table if not exists public.venues (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  short_name text,
  type text,
  issn jsonb not null default '[]'::jsonb,
  publisher text,
  ccf_rank text,
  core_rank text,
  quartile text,
  openalex_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint venues_name_not_blank check (length(btrim(name)) > 0)
);

create table if not exists public.academic_papers (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  normalized_title text not null,
  abstract text,
  doi text,
  arxiv_id text,
  openalex_id text,
  semantic_scholar_id text,
  dblp_id text,
  publication_date date,
  year int,
  venue_id uuid references public.venues(id) on delete set null,
  citation_count int not null default 0,
  url text,
  pdf_url text,
  source text,
  source_ids jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint academic_papers_title_not_blank check (length(btrim(title)) > 0),
  constraint academic_papers_normalized_title_not_blank check (length(btrim(normalized_title)) > 0),
  constraint academic_papers_citation_count_nonnegative check (citation_count >= 0)
);

create table if not exists public.authors (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  normalized_name text not null,
  openalex_id text,
  semantic_scholar_id text,
  orcid text,
  dblp_id text,
  homepage text,
  works_count int,
  citation_count int,
  primary_institution_id uuid references public.institutions(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint authors_name_not_blank check (length(btrim(name)) > 0),
  constraint authors_normalized_name_not_blank check (length(btrim(normalized_name)) > 0),
  constraint authors_works_count_nonnegative check (works_count is null or works_count >= 0),
  constraint authors_citation_count_nonnegative check (citation_count is null or citation_count >= 0)
);

create table if not exists public.paper_authors (
  paper_id uuid not null references public.academic_papers(id) on delete cascade,
  author_id uuid not null references public.authors(id) on delete cascade,
  author_position text,
  author_order int,
  is_corresponding boolean,
  raw_affiliation text,
  institution_id uuid references public.institutions(id) on delete set null,
  primary key (paper_id, author_id),
  constraint paper_authors_author_order_positive check (author_order is null or author_order > 0)
);

create table if not exists public.research_field_papers (
  research_field_id uuid not null references public.research_fields(id) on delete cascade,
  paper_id uuid not null references public.academic_papers(id) on delete cascade,
  relevance_score float8,
  discovery_source text,
  first_discovered_at timestamptz not null default now(),
  latest_seen_at timestamptz not null default now(),
  primary key (research_field_id, paper_id),
  constraint research_field_papers_relevance_score_range
    check (relevance_score is null or (relevance_score >= 0 and relevance_score <= 1)),
  constraint research_field_papers_seen_order
    check (latest_seen_at >= first_discovered_at)
);

create table if not exists public.research_field_sync_runs (
  id uuid primary key default gen_random_uuid(),
  research_field_id uuid not null references public.research_fields(id) on delete cascade,
  provider text not null,
  status text not null,
  from_date date,
  to_date date,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  queries jsonb not null default '[]'::jsonb,
  candidates_retrieved int not null default 0,
  papers_inserted int not null default 0,
  papers_updated int not null default 0,
  authors_inserted int not null default 0,
  institutions_inserted int not null default 0,
  venues_inserted int not null default 0,
  paper_author_links_inserted int not null default 0,
  collaborations_created int not null default 0,
  duplicates_skipped int not null default 0,
  failures int not null default 0,
  partial_failures int not null default 0,
  error_summary jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint research_field_sync_runs_provider_not_blank check (length(btrim(provider)) > 0),
  constraint research_field_sync_runs_status_not_blank check (length(btrim(status)) > 0),
  constraint research_field_sync_runs_date_order check (from_date is null or to_date is null or to_date >= from_date),
  constraint research_field_sync_runs_completion_order check (completed_at is null or completed_at >= started_at),
  constraint research_field_sync_runs_counts_nonnegative check (
    candidates_retrieved >= 0
    and papers_inserted >= 0
    and papers_updated >= 0
    and authors_inserted >= 0
    and institutions_inserted >= 0
    and venues_inserted >= 0
    and paper_author_links_inserted >= 0
    and collaborations_created >= 0
    and duplicates_skipped >= 0
    and failures >= 0
    and partial_failures >= 0
  )
);

create table if not exists public.author_collaborations (
  research_field_id uuid not null references public.research_fields(id) on delete cascade,
  author_a_id uuid not null references public.authors(id) on delete cascade,
  author_b_id uuid not null references public.authors(id) on delete cascade,
  total_collaboration_count int not null default 0,
  field_collaboration_count int not null default 0,
  first_collaboration_year int,
  latest_collaboration_year int,
  latest_collaboration_date date,
  weighted_score float8,
  updated_at timestamptz not null default now(),
  primary key (research_field_id, author_a_id, author_b_id),
  constraint author_collaborations_distinct_ordered_authors check (author_a_id < author_b_id),
  constraint author_collaborations_counts_nonnegative check (
    total_collaboration_count >= 0
    and field_collaboration_count >= 0
  ),
  constraint author_collaborations_year_order check (
    first_collaboration_year is null
    or latest_collaboration_year is null
    or latest_collaboration_year >= first_collaboration_year
  )
);

-- Identity and deduplication foundations.
create unique index if not exists institutions_openalex_id_unique
  on public.institutions (openalex_id);

create unique index if not exists institutions_ror_id_unique
  on public.institutions (ror_id);

create unique index if not exists venues_openalex_id_unique
  on public.venues (openalex_id);

create unique index if not exists academic_papers_openalex_id_unique
  on public.academic_papers (openalex_id);

create unique index if not exists academic_papers_doi_unique
  on public.academic_papers (doi);

create unique index if not exists academic_papers_arxiv_id_unique
  on public.academic_papers (arxiv_id);

create unique index if not exists authors_openalex_id_unique
  on public.authors (openalex_id);

create unique index if not exists authors_orcid_unique
  on public.authors (orcid);

-- Query indexes.
create index if not exists academic_papers_year_idx
  on public.academic_papers (year);

create index if not exists academic_papers_publication_date_idx
  on public.academic_papers (publication_date);

create index if not exists academic_papers_venue_id_idx
  on public.academic_papers (venue_id);

create index if not exists academic_papers_normalized_title_year_idx
  on public.academic_papers (normalized_title, year);

create index if not exists academic_papers_source_idx
  on public.academic_papers (source);

create index if not exists authors_primary_institution_id_idx
  on public.authors (primary_institution_id);

create index if not exists paper_authors_author_id_idx
  on public.paper_authors (author_id);

create index if not exists paper_authors_institution_id_idx
  on public.paper_authors (institution_id);

create index if not exists research_field_papers_paper_id_idx
  on public.research_field_papers (paper_id);

create index if not exists research_field_papers_field_relevance_idx
  on public.research_field_papers (research_field_id, relevance_score desc);

create index if not exists research_field_papers_field_latest_seen_idx
  on public.research_field_papers (research_field_id, latest_seen_at desc);

create index if not exists research_field_sync_runs_field_started_idx
  on public.research_field_sync_runs (research_field_id, started_at desc);

create index if not exists research_field_sync_runs_field_status_idx
  on public.research_field_sync_runs (research_field_id, status);

create index if not exists author_collaborations_field_idx
  on public.author_collaborations (research_field_id);

create index if not exists author_collaborations_field_author_a_idx
  on public.author_collaborations (research_field_id, author_a_id);

create index if not exists author_collaborations_field_author_b_idx
  on public.author_collaborations (research_field_id, author_b_id);

do $$
begin
  if not exists (
    select 1 from pg_trigger
    where tgname = 'research_fields_set_updated_at'
      and tgrelid = 'public.research_fields'::regclass
  ) then
    create trigger research_fields_set_updated_at
    before update on public.research_fields
    for each row execute function public.set_research_radar_updated_at();
  end if;

  if not exists (
    select 1 from pg_trigger
    where tgname = 'institutions_set_updated_at'
      and tgrelid = 'public.institutions'::regclass
  ) then
    create trigger institutions_set_updated_at
    before update on public.institutions
    for each row execute function public.set_research_radar_updated_at();
  end if;

  if not exists (
    select 1 from pg_trigger
    where tgname = 'venues_set_updated_at'
      and tgrelid = 'public.venues'::regclass
  ) then
    create trigger venues_set_updated_at
    before update on public.venues
    for each row execute function public.set_research_radar_updated_at();
  end if;

  if not exists (
    select 1 from pg_trigger
    where tgname = 'academic_papers_set_updated_at'
      and tgrelid = 'public.academic_papers'::regclass
  ) then
    create trigger academic_papers_set_updated_at
    before update on public.academic_papers
    for each row execute function public.set_research_radar_updated_at();
  end if;

  if not exists (
    select 1 from pg_trigger
    where tgname = 'authors_set_updated_at'
      and tgrelid = 'public.authors'::regclass
  ) then
    create trigger authors_set_updated_at
    before update on public.authors
    for each row execute function public.set_research_radar_updated_at();
  end if;

  if not exists (
    select 1 from pg_trigger
    where tgname = 'author_collaborations_set_updated_at'
      and tgrelid = 'public.author_collaborations'::regclass
  ) then
    create trigger author_collaborations_set_updated_at
    before update on public.author_collaborations
    for each row execute function public.set_research_radar_updated_at();
  end if;
end;
$$;

alter table public.research_fields enable row level security;
alter table public.institutions enable row level security;
alter table public.venues enable row level security;
alter table public.academic_papers enable row level security;
alter table public.authors enable row level security;
alter table public.paper_authors enable row level security;
alter table public.research_field_papers enable row level security;
alter table public.research_field_sync_runs enable row level security;
alter table public.author_collaborations enable row level security;

grant select on table public.research_fields to anon, authenticated;
grant select on table public.institutions to anon, authenticated;
grant select on table public.venues to anon, authenticated;
grant select on table public.academic_papers to anon, authenticated;
grant select on table public.authors to anon, authenticated;
grant select on table public.paper_authors to anon, authenticated;
grant select on table public.research_field_papers to anon, authenticated;
grant select on table public.research_field_sync_runs to anon, authenticated;
grant select on table public.author_collaborations to anon, authenticated;

grant select, insert, update, delete on table public.research_fields to service_role;
grant select, insert, update, delete on table public.institutions to service_role;
grant select, insert, update, delete on table public.venues to service_role;
grant select, insert, update, delete on table public.academic_papers to service_role;
grant select, insert, update, delete on table public.authors to service_role;
grant select, insert, update, delete on table public.paper_authors to service_role;
grant select, insert, update, delete on table public.research_field_papers to service_role;
grant select, insert, update, delete on table public.research_field_sync_runs to service_role;
grant select, insert, update, delete on table public.author_collaborations to service_role;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'research_fields'
      and policyname = 'public read research fields'
  ) then
    create policy "public read research fields"
    on public.research_fields
    for select
    to anon, authenticated
    using (true);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'institutions'
      and policyname = 'public read research radar institutions'
  ) then
    create policy "public read research radar institutions"
    on public.institutions
    for select
    to anon, authenticated
    using (true);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'venues'
      and policyname = 'public read research radar venues'
  ) then
    create policy "public read research radar venues"
    on public.venues
    for select
    to anon, authenticated
    using (true);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'academic_papers'
      and policyname = 'public read research radar papers'
  ) then
    create policy "public read research radar papers"
    on public.academic_papers
    for select
    to anon, authenticated
    using (true);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'authors'
      and policyname = 'public read research radar authors'
  ) then
    create policy "public read research radar authors"
    on public.authors
    for select
    to anon, authenticated
    using (true);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'paper_authors'
      and policyname = 'public read research radar paper authors'
  ) then
    create policy "public read research radar paper authors"
    on public.paper_authors
    for select
    to anon, authenticated
    using (true);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'research_field_papers'
      and policyname = 'public read research field papers'
  ) then
    create policy "public read research field papers"
    on public.research_field_papers
    for select
    to anon, authenticated
    using (true);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'research_field_sync_runs'
      and policyname = 'public read research field sync runs'
  ) then
    create policy "public read research field sync runs"
    on public.research_field_sync_runs
    for select
    to anon, authenticated
    using (true);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'author_collaborations'
      and policyname = 'public read research radar collaborations'
  ) then
    create policy "public read research radar collaborations"
    on public.author_collaborations
    for select
    to anon, authenticated
    using (true);
  end if;
end;
$$;

notify pgrst, 'reload schema';
