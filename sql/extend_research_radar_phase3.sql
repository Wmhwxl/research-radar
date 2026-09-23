-- ============================================================
-- Research Radar Phase 3 additive schema extension
-- ============================================================
-- Adds relevance evidence, resumable sync checkpoints, and full
-- paper-author-institution links without altering Daily Paper Reader tables.
-- ============================================================

alter table public.research_field_papers
  add column if not exists relevance_label text,
  add column if not exists relevance_evidence jsonb not null default '{}'::jsonb;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'research_field_papers_relevance_label_allowed'
      and conrelid = 'public.research_field_papers'::regclass
  ) then
    alter table public.research_field_papers
      add constraint research_field_papers_relevance_label_allowed
      check (relevance_label is null or relevance_label in ('core', 'related'));
  end if;
end;
$$;

alter table public.research_field_sync_runs
  add column if not exists checkpoint jsonb not null default '{}'::jsonb,
  add column if not exists accepted_core int not null default 0,
  add column if not exists accepted_related int not null default 0,
  add column if not exists rejected int not null default 0;

create table if not exists public.paper_author_institutions (
  paper_id uuid not null references public.academic_papers(id) on delete cascade,
  author_id uuid not null references public.authors(id) on delete cascade,
  institution_id uuid not null references public.institutions(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (paper_id, author_id, institution_id)
);

create index if not exists paper_author_institutions_author_id_idx
  on public.paper_author_institutions (author_id);

create index if not exists paper_author_institutions_institution_id_idx
  on public.paper_author_institutions (institution_id);

alter table public.paper_author_institutions enable row level security;

grant select on table public.paper_author_institutions to anon, authenticated;
grant select, insert, update, delete on table public.paper_author_institutions to service_role;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'paper_author_institutions'
      and policyname = 'public read research radar paper author institutions'
  ) then
    create policy "public read research radar paper author institutions"
    on public.paper_author_institutions
    for select
    to anon, authenticated
    using (true);
  end if;
end;
$$;

notify pgrst, 'reload schema';
