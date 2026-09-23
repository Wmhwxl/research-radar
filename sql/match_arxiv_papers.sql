-- ============================================================
-- Supabase RPC 函数定义（含日期过滤参数）
-- ============================================================
-- 长窗口修复：关键词先用已有 search_tsv GIN 过滤，保留原有分词和评分语义；
-- 精确向量只排序 id/距离，选完 Top-K 后才读取论文正文。
-- PL/pgSQL + custom plan 避免可空日期参数在通用计划中退化为全表过滤。
-- 仅检索函数使用有限超时，不修改角色权限、RLS 或全局超时。
-- 前置条件：arxiv_papers.search_tsv 由标题/摘要的 english tsvector 同步生成，
-- 已有 idx_arxiv_papers_search_tsv GIN 与 published B-tree 索引。
--
-- 使用方式：
--   在 Supabase SQL Editor 中执行以下语句。
--   新增参数均带 DEFAULT NULL，旧客户端调用（不传日期）不受影响。
-- ============================================================

-- 1. 精确向量检索（无索引，全表扫描 → 加日期过滤后仅扫窗口内行）
CREATE OR REPLACE FUNCTION match_arxiv_papers_exact(
  query_embedding vector,
  match_count     int,
  filter_published_start timestamptz DEFAULT NULL,
  filter_published_end   timestamptz DEFAULT NULL
)
RETURNS TABLE (
  id                text,
  title             text,
  abstract          text,
  authors           jsonb,
  primary_category  text,
  categories        jsonb,
  published         timestamptz,
  link              text,
  pdf_url           text,
  source            text,
  similarity        float8
)
LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path = public, extensions
SET plan_cache_mode = force_custom_plan
SET jit = off
SET statement_timeout = '60s'
AS $$
BEGIN
  RETURN QUERY
  WITH nearest AS MATERIALIZED (
    SELECT p.id, p.embedding <=> query_embedding AS distance
    FROM public.arxiv_papers p
    WHERE p.embedding IS NOT NULL
      AND (filter_published_start IS NULL OR p.published >= filter_published_start)
      AND (filter_published_end IS NULL OR p.published < filter_published_end)
    -- +0 阻止以后新增 ANN 索引时静默改用近似结果，保留 exact 语义。
    ORDER BY (p.embedding <=> query_embedding) + 0, p.id
    LIMIT match_count
  )
  SELECT p.id, p.title, p.abstract, p.authors, p.primary_category,
         p.categories, p.published, p.link, p.pdf_url, p.source,
         1 - n.distance AS similarity
  FROM nearest n
  JOIN public.arxiv_papers p ON p.id = n.id
  ORDER BY n.distance, n.id;
END;
$$;

-- 2. ANN 向量检索（使用 HNSW / IVFFlat 索引）
CREATE OR REPLACE FUNCTION match_arxiv_papers(
  query_embedding vector,
  match_count     int,
  filter_published_start timestamptz DEFAULT NULL,
  filter_published_end   timestamptz DEFAULT NULL
)
RETURNS TABLE (
  id                text,
  title             text,
  abstract          text,
  authors           jsonb,
  primary_category  text,
  categories        jsonb,
  published         timestamptz,
  link              text,
  pdf_url           text,
  source            text,
  similarity        float8
)
LANGUAGE sql STABLE
AS $$
  SELECT
    p.id,
    p.title,
    p.abstract,
    p.authors,
    p.primary_category,
    p.categories,
    p.published,
    p.link,
    p.pdf_url,
    p.source,
    1 - (p.embedding <=> query_embedding) AS similarity
  FROM arxiv_papers p
  WHERE p.embedding IS NOT NULL
    AND (filter_published_start IS NULL OR p.published >= filter_published_start)
    AND (filter_published_end   IS NULL OR p.published <  filter_published_end)
  ORDER BY p.embedding <=> query_embedding
  LIMIT match_count;
$$;

-- 3. BM25 全文检索
CREATE OR REPLACE FUNCTION match_arxiv_papers_bm25(
  query_text      text,
  match_count     int,
  filter_published_start timestamptz DEFAULT NULL,
  filter_published_end   timestamptz DEFAULT NULL
)
RETURNS TABLE (
  id                text,
  title             text,
  abstract          text,
  authors           jsonb,
  primary_category  text,
  categories        jsonb,
  published         timestamptz,
  link              text,
  pdf_url           text,
  source            text,
  similarity        float8,
  score             float8
)
LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path = public, extensions
SET plan_cache_mode = force_custom_plan
SET jit = off
SET statement_timeout = '30s'
AS $$
DECLARE
  search_query tsquery := plainto_tsquery('english', query_text);
BEGIN
  RETURN QUERY
  WITH ranked AS MATERIALIZED (
    SELECT p.id,
      ts_rank_cd(
        to_tsvector('english', coalesce(p.title, '') || ' ' || coalesce(p.abstract, '')),
        search_query
      ) AS rank_score
    FROM public.arxiv_papers p
    WHERE p.search_tsv @@ search_query
      AND (filter_published_start IS NULL OR p.published >= filter_published_start)
      AND (filter_published_end IS NULL OR p.published < filter_published_end)
    ORDER BY rank_score DESC, p.id
    LIMIT match_count
  )
  SELECT p.id, p.title, p.abstract, p.authors, p.primary_category,
         p.categories, p.published, p.link, p.pdf_url, p.source,
         0::float8 AS similarity, r.rank_score::float8 AS score
  FROM ranked r
  JOIN public.arxiv_papers p ON p.id = r.id
  ORDER BY r.rank_score DESC, r.id;
END;
$$;

-- PostgREST 必须重新读取函数级 timeout 配置；不变更角色级配置。
NOTIFY pgrst, 'reload schema';
