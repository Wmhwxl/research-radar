-- ============================================================
-- 预印本论文表 anon/authenticated 只读访问策略
-- ============================================================
--
-- 用途：
-- - 让前端和预印本检索链路使用 Supabase anon key 读取公开预印本论文表。
-- - 覆盖 arxiv / biorxiv / medrxiv / chemrxiv 四张同构表。
-- - 修复 medrxiv_papers、chemrxiv_papers 开启 RLS 但没有任何 SELECT policy，
--   导致 REST/RPC 返回 200 空数组（线上 medrxiv_papers 有 1033 行，anon 读到 0 行）。
-- - 同时把生产库里手工建立、仓库从未记录的 arxiv/biorxiv 策略固化成代码，消除配置漂移。
--
-- 安全边界：
-- - 仅开放 SELECT，不开放 INSERT / UPDATE / DELETE。
-- - 谓词用 true 而不是 source = '<src>'：这四张表是单源表，整表内容本来就公开；
--   而 sync.py:426 的 `_norm(x.get("source") or "supabase")` 兜底意味着一旦某条记录
--   缺 source 字段就会写入字面量 "supabase"，用等值谓词会让这类行对 anon 静默不可见，
--   正是本次要修的同一类故障。会议表用 source 正则是因为它们一表多会次、需要区分公开/非公开子集。
-- - match_*_papers_exact / _bm25 均为 SECURITY INVOKER 函数，会以调用者身份读表，
--   因此这里的表级 policy 就是 RPC 的可见性边界，无需额外放宽。
-- - 当前 RPC 会读取 embedding 列，因此对整表授予 SELECT。
--   如果未来不希望 anon 直接读取 embedding 列，需要把 RPC 迁到更受控的设计后再收紧列权限。
--
-- 幂等性：
-- - 全部语句可重复执行；policy 先 drop if exists 再 create。
-- - 单事务提交，中途失败自动回滚，不会出现"旧策略已删、新策略未建"的裸奔窗口。

begin;

grant usage on schema public to anon, authenticated;

-- 预印本表启用 RLS（已启用时为幂等空操作）
alter table public.arxiv_papers enable row level security;
alter table public.biorxiv_papers enable row level security;
alter table public.medrxiv_papers enable row level security;
alter table public.chemrxiv_papers enable row level security;

grant select on table public.arxiv_papers to anon, authenticated;
grant select on table public.biorxiv_papers to anon, authenticated;
grant select on table public.medrxiv_papers to anon, authenticated;
grant select on table public.chemrxiv_papers to anon, authenticated;

drop policy if exists "public read arxiv papers" on public.arxiv_papers;
create policy "public read arxiv papers"
on public.arxiv_papers
for select
to anon, authenticated
using (
  true
);

drop policy if exists "public read biorxiv papers" on public.biorxiv_papers;
create policy "public read biorxiv papers"
on public.biorxiv_papers
for select
to anon, authenticated
using (
  true
);

drop policy if exists "public read medrxiv papers" on public.medrxiv_papers;
create policy "public read medrxiv papers"
on public.medrxiv_papers
for select
to anon, authenticated
using (
  true
);

drop policy if exists "public read chemrxiv papers" on public.chemrxiv_papers;
create policy "public read chemrxiv papers"
on public.chemrxiv_papers
for select
to anon, authenticated
using (
  true
);

-- RPC execute grants（PostgreSQL 默认已把 EXECUTE 授予 PUBLIC，这里显式声明以保证可复现）
grant execute on function public.match_arxiv_papers_exact(vector, int, timestamptz, timestamptz)
to anon, authenticated;
grant execute on function public.match_arxiv_papers_bm25(text, int, timestamptz, timestamptz)
to anon, authenticated;

grant execute on function public.match_biorxiv_papers_exact(vector, int, timestamptz, timestamptz)
to anon, authenticated;
grant execute on function public.match_biorxiv_papers_bm25(text, int, timestamptz, timestamptz)
to anon, authenticated;

grant execute on function public.match_medrxiv_papers_exact(vector, int, timestamptz, timestamptz)
to anon, authenticated;
grant execute on function public.match_medrxiv_papers_bm25(text, int, timestamptz, timestamptz)
to anon, authenticated;

grant execute on function public.match_chemrxiv_papers_exact(vector, int, timestamptz, timestamptz)
to anon, authenticated;
grant execute on function public.match_chemrxiv_papers_bm25(text, int, timestamptz, timestamptz)
to anon, authenticated;

commit;
