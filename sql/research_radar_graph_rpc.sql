-- Research Radar Phase 4B read models. All functions are read-only and run
-- with the caller's RLS permissions; the browser uses only the anon key.

create or replace function public.get_research_field_overview(
  p_field_id uuid, p_start_year int default null, p_end_year int default null
) returns jsonb language sql stable security invoker set search_path = public as $$
with fp as (
  select p.id, p.year, p.venue_id, rfp.relevance_label, rfp.relevance_score
  from research_field_papers rfp join academic_papers p on p.id = rfp.paper_id
  where rfp.research_field_id = p_field_id
    and (p_start_year is null or p.year >= p_start_year)
    and (p_end_year is null or p.year <= p_end_year)
), author_first as (
  select pa.author_id, min(fp.year) first_year from fp join paper_authors pa on pa.paper_id = fp.id group by pa.author_id
), pairs as (
  select distinct fp.id paper_id, least(a.author_id,b.author_id) author_a, greatest(a.author_id,b.author_id) author_b
  from fp join paper_authors a on a.paper_id=fp.id join paper_authors b on b.paper_id=fp.id and a.author_id<b.author_id
), recent as (
  select jsonb_agg(x order by x.year desc, x.title) items from (
    select p.id,p.title,p.year,v.name venue,rfp.relevance_label,rfp.relevance_score,
      coalesce((select jsonb_agg(jsonb_build_object('id',a.id,'name',a.name) order by pa.author_order) from paper_authors pa join authors a on a.id=pa.author_id where pa.paper_id=p.id),'[]'::jsonb) authors
    from research_field_papers rfp join academic_papers p on p.id=rfp.paper_id left join venues v on v.id=p.venue_id
    where rfp.research_field_id=p_field_id and rfp.relevance_label='core'
      and (p_start_year is null or p.year>=p_start_year) and (p_end_year is null or p.year<=p_end_year)
    order by p.year desc,p.title limit 6
  ) x
), active as (
  select jsonb_agg(x order by x.field_paper_count desc,x.name) items from (
    select a.id,a.name,i.name primary_institution,count(distinct fp.id)::int field_paper_count
    from fp join paper_authors pa on pa.paper_id=fp.id join authors a on a.id=pa.author_id left join institutions i on i.id=a.primary_institution_id
    group by a.id,a.name,i.name order by count(distinct fp.id) desc,a.name limit 6
  ) x
)
select jsonb_build_object(
  'paper_count',(select count(*) from fp),
  'author_count',(select count(*) from author_first),
  'institution_count',(select count(distinct pai.institution_id) from fp join paper_author_institutions pai on pai.paper_id=fp.id),
  'venue_count',(select count(distinct venue_id) from fp where venue_id is not null),
  'collaboration_count',(select count(*) from pairs),
  'yearly_paper_counts',coalesce((select jsonb_agg(jsonb_build_object('year',year,'count',count) order by year) from (select year,count(*)::int count from fp group by year) y),'[]'::jsonb),
  'yearly_new_author_counts',coalesce((select jsonb_agg(jsonb_build_object('year',first_year,'count',count) order by first_year) from (select first_year,count(*)::int count from author_first group by first_year) y),'[]'::jsonb),
  'recent_core_papers',coalesce((select items from recent),'[]'::jsonb),
  'active_authors',coalesce((select items from active),'[]'::jsonb)
); $$;

create or replace function public.get_research_field_papers(
  p_field_id uuid, p_start_year int default null, p_end_year int default null,
  p_search text default null, p_venue text default null, p_author text default null,
  p_relevance_label text default null, p_min_relevance float8 default null,
  p_sort text default 'newest', p_limit int default 50, p_offset int default 0
) returns jsonb language sql stable security invoker set search_path = public as $$
with rows as (
  select p.*,v.name venue,rfp.relevance_label,rfp.relevance_score
  from research_field_papers rfp join academic_papers p on p.id=rfp.paper_id left join venues v on v.id=p.venue_id
  where rfp.research_field_id=p_field_id
    and (p_start_year is null or p.year>=p_start_year) and (p_end_year is null or p.year<=p_end_year)
    and (p_search is null or p.title ilike '%'||p_search||'%')
    and (p_venue is null or v.name ilike '%'||p_venue||'%')
    and (p_author is null or exists(select 1 from paper_authors pa join authors a on a.id=pa.author_id where pa.paper_id=p.id and a.name ilike '%'||p_author||'%'))
    and (p_relevance_label is null or rfp.relevance_label=p_relevance_label)
    and (p_min_relevance is null or rfp.relevance_score>=p_min_relevance)
), page as (
  select * from rows order by
    case when p_sort='oldest' then year end asc,
    case when p_sort='relevance' then relevance_score end desc,
    case when p_sort='citations' then citation_count end desc,
    case when p_sort not in ('oldest','relevance','citations') then year end desc,
    title limit greatest(1,least(coalesce(p_limit,50),200)) offset greatest(coalesce(p_offset,0),0)
)
select jsonb_build_object('total',(select count(*) from rows),'items',coalesce((select jsonb_agg(jsonb_build_object(
  'id',p.id,'title',p.title,'year',p.year,'venue',p.venue,'relevance_label',p.relevance_label,
  'relevance_score',p.relevance_score,'citation_count',p.citation_count,'source',p.source,
  'external_url',coalesce(p.url,case when p.doi is not null then 'https://doi.org/'||p.doi end),
  'authors',coalesce((select jsonb_agg(jsonb_build_object('id',a.id,'name',a.name) order by pa.author_order) from paper_authors pa join authors a on a.id=pa.author_id where pa.paper_id=p.id),'[]'::jsonb)
) order by case when p_sort='oldest' then p.year end asc,case when p_sort<>'oldest' then p.year end desc,p.title) from page p),'[]'::jsonb)); $$;

create or replace function public.get_research_field_authors(
  p_field_id uuid, p_start_year int default null, p_end_year int default null,
  p_search text default null, p_institution text default null, p_min_papers int default 1,
  p_limit int default 50, p_offset int default 0
) returns jsonb language sql stable security invoker set search_path = public as $$
with fp as (
  select p.id,p.year from research_field_papers rfp join academic_papers p on p.id=rfp.paper_id
  where rfp.research_field_id=p_field_id and (p_start_year is null or p.year>=p_start_year) and (p_end_year is null or p.year<=p_end_year)
), stats as (
  select a.id,a.name,i.name primary_institution,a.works_count total_works,a.citation_count,
    count(distinct fp.id)::int field_paper_count,min(fp.year) first_field_year,max(fp.year) latest_field_year
  from fp join paper_authors pa on pa.paper_id=fp.id join authors a on a.id=pa.author_id left join institutions i on i.id=a.primary_institution_id
  where (p_search is null or a.name ilike '%'||p_search||'%') and (p_institution is null or i.name ilike '%'||p_institution||'%')
  group by a.id,a.name,i.name,a.works_count,a.citation_count having count(distinct fp.id)>=greatest(coalesce(p_min_papers,1),1)
), page as (select * from stats order by field_paper_count desc,name limit greatest(1,least(coalesce(p_limit,50),200)) offset greatest(coalesce(p_offset,0),0))
select jsonb_build_object('total',(select count(*) from stats),'items',coalesce((select jsonb_agg(to_jsonb(page) order by field_paper_count desc,name) from page),'[]'::jsonb)); $$;

create or replace function public.get_research_field_scholar_graph(
  p_field_id uuid, p_start_year int default null, p_end_year int default null,
  p_min_papers int default 1, p_min_collaborations int default 1,
  p_core_only boolean default false, p_max_nodes int default 500
) returns jsonb language sql stable security invoker set search_path = public as $$
with fp as (
  select p.id,p.year from research_field_papers rfp join academic_papers p on p.id=rfp.paper_id
  where rfp.research_field_id=p_field_id and (not p_core_only or rfp.relevance_label='core')
    and (p_start_year is null or p.year>=p_start_year) and (p_end_year is null or p.year<=p_end_year)
), all_nodes as (
  select a.id,a.name,i.name institution,count(distinct fp.id)::int field_paper_count,a.citation_count,min(fp.year) first_year,max(fp.year) latest_year
  from fp join paper_authors pa on pa.paper_id=fp.id join authors a on a.id=pa.author_id left join institutions i on i.id=a.primary_institution_id
  group by a.id,a.name,i.name,a.citation_count having count(distinct fp.id)>=greatest(coalesce(p_min_papers,1),1)
), nodes as (
  select * from all_nodes order by field_paper_count desc,name limit coalesce(greatest(p_max_nodes,1),2147483647)
), edges as (
  select a.author_id source,b.author_id target,count(distinct fp.id)::int field_collaboration_count,min(fp.year) first_year,max(fp.year) latest_year,
    jsonb_agg(distinct fp.id) shared_paper_ids
  from fp join paper_authors a on a.paper_id=fp.id join paper_authors b on b.paper_id=fp.id and a.author_id<b.author_id
  where exists(select 1 from nodes n where n.id=a.author_id) and exists(select 1 from nodes n where n.id=b.author_id)
  group by a.author_id,b.author_id having count(distinct fp.id)>=greatest(coalesce(p_min_collaborations,1),1)
)
select jsonb_build_object('total_nodes',(select count(*) from all_nodes),'nodes',coalesce((select jsonb_agg(to_jsonb(nodes) order by field_paper_count desc,name) from nodes),'[]'::jsonb),'edges',coalesce((select jsonb_agg(to_jsonb(edges)) from edges),'[]'::jsonb)); $$;

create or replace function public.get_research_field_author_detail(
  p_field_id uuid, p_author_id uuid, p_start_year int default null, p_end_year int default null
) returns jsonb language sql stable security invoker set search_path = public as $$
with fp as (
  select p.*,v.name venue,rfp.relevance_label from research_field_papers rfp join academic_papers p on p.id=rfp.paper_id left join venues v on v.id=p.venue_id
  where rfp.research_field_id=p_field_id and (p_start_year is null or p.year>=p_start_year) and (p_end_year is null or p.year<=p_end_year)
), mine as (select fp.* from fp join paper_authors pa on pa.paper_id=fp.id where pa.author_id=p_author_id), collabs as (
  select a.id,a.name,count(distinct mine.id)::int shared_paper_count from mine join paper_authors pa on pa.paper_id=mine.id and pa.author_id<>p_author_id join authors a on a.id=pa.author_id group by a.id,a.name order by shared_paper_count desc,a.name limit 10
)
select jsonb_build_object('id',a.id,'name',a.name,'primary_institution',i.name,'other_affiliations',coalesce((select jsonb_agg(distinct oi.name) from mine join paper_author_institutions pai on pai.paper_id=mine.id and pai.author_id=a.id join institutions oi on oi.id=pai.institution_id where oi.id is distinct from a.primary_institution_id),'[]'::jsonb),'total_works',a.works_count,'citation_count',a.citation_count,'openalex_url',case when a.openalex_id is not null then 'https://openalex.org/'||a.openalex_id end,'field_paper_count',(select count(*) from mine),'first_field_year',(select min(year) from mine),'latest_field_year',(select max(year) from mine),'collaborators',coalesce((select jsonb_agg(to_jsonb(collabs)) from collabs),'[]'::jsonb),'papers',coalesce((select jsonb_agg(jsonb_build_object('id',id,'title',title,'year',year,'venue',venue,'relevance_label',relevance_label) order by year desc,title) from mine),'[]'::jsonb)) from authors a left join institutions i on i.id=a.primary_institution_id where a.id=p_author_id; $$;

create or replace function public.get_research_field_collaboration_detail(
  p_field_id uuid, p_author_a_id uuid, p_author_b_id uuid,
  p_start_year int default null, p_end_year int default null
) returns jsonb language sql stable security invoker set search_path = public as $$
with shared as (
  select p.id,p.title,p.year,v.name venue,rfp.relevance_label from research_field_papers rfp join academic_papers p on p.id=rfp.paper_id left join venues v on v.id=p.venue_id
  where rfp.research_field_id=p_field_id and (p_start_year is null or p.year>=p_start_year) and (p_end_year is null or p.year<=p_end_year)
    and exists(select 1 from paper_authors pa where pa.paper_id=p.id and pa.author_id=p_author_a_id)
    and exists(select 1 from paper_authors pa where pa.paper_id=p.id and pa.author_id=p_author_b_id)
)
select jsonb_build_object('authors',(select jsonb_agg(jsonb_build_object('id',id,'name',name) order by name) from authors where id in (p_author_a_id,p_author_b_id)),'shared_paper_count',(select count(*) from shared),'first_year',(select min(year) from shared),'latest_year',(select max(year) from shared),'papers',coalesce((select jsonb_agg(to_jsonb(shared) order by year desc,title) from shared),'[]'::jsonb)); $$;

revoke all on function public.get_research_field_overview(uuid,int,int) from public;
revoke all on function public.get_research_field_papers(uuid,int,int,text,text,text,text,float8,text,int,int) from public;
revoke all on function public.get_research_field_authors(uuid,int,int,text,text,int,int,int) from public;
revoke all on function public.get_research_field_scholar_graph(uuid,int,int,int,int,boolean,int) from public;
revoke all on function public.get_research_field_author_detail(uuid,uuid,int,int) from public;
revoke all on function public.get_research_field_collaboration_detail(uuid,uuid,uuid,int,int) from public;
grant execute on function public.get_research_field_overview(uuid,int,int) to anon,authenticated;
grant execute on function public.get_research_field_papers(uuid,int,int,text,text,text,text,float8,text,int,int) to anon,authenticated;
grant execute on function public.get_research_field_authors(uuid,int,int,text,text,int,int,int) to anon,authenticated;
grant execute on function public.get_research_field_scholar_graph(uuid,int,int,int,int,boolean,int) to anon,authenticated;
grant execute on function public.get_research_field_author_detail(uuid,uuid,int,int) to anon,authenticated;
grant execute on function public.get_research_field_collaboration_detail(uuid,uuid,uuid,int,int) to anon,authenticated;
notify pgrst, 'reload schema';
