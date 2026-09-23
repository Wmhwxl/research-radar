# TODO

## Skills 封装

- [ ] 新增项目内 skill：`.codex/skills/maintain-daily-paper-reader/SKILL.md`
- [ ] 在 skill 中沉淀仓库维护工作流：抓取、召回、排序、文档生成、前端工作流面板
- [ ] 明确 skill 使用边界：只读排查、流水线修改、workflow 修改、docs 生成修改
- [ ] 视稳定程度决定是否补充 `agents/openai.yaml`

## 多源论文推荐接入

### 目标

- [ ] 将推荐候选从单一 `arXiv / OpenReview` 扩展为多源聚合
- [ ] 保持现有 BM25、embedding、排序、LLM refine、docs 生成主链路可复用

### 数据模型统一

- [ ] 为论文池补充统一字段：`source`、`source_id`、`doi`、`canonical_url`、`pdf_url`
- [ ] 增加跨源外部 ID 字段：`arxiv_id`、`openalex_id`、`semantic_scholar_id`、`pmid`、`pmcid`、`dblp_id`
- [ ] 设计跨源去重规则：优先 DOI / arXiv ID / PMID / PMCID，其次标题 + 年份近似匹配
- [ ] 让非 arXiv 论文也能安全进入后续推荐与文档生成流程

### 抓取与召回

- [ ] 新增“多源 query 驱动抓取层”，按关键词 / intent queries 从外部学术源拉取候选
- [ ] 保留 arXiv 现有全局抓取能力，同时允许外部来源作为补充候选池
- [ ] 为每个来源增加独立的超时、重试、限流与开关配置

### 待接入渠道

- [ ] OpenAlex
- [ ] Semantic Scholar
- [ ] PubMed
- [ ] Papers with Code
- [ ] CrossRef
- [ ] Europe PMC
- [ ] bioRxiv
- [ ] DBLP

### 下游兼容

- [ ] 让 `Step 1` 原始论文池支持多源混合输出
- [ ] 让 BM25 / embedding 检索保留并透传来源信息
- [ ] 让排序与 LLM refine 能识别多源论文而不是默认 arXiv
- [ ] 让 docs 生成在缺少 PDF 时支持降级：abstract-only / external-link-only
- [ ] 让侧边栏与论文页展示真实来源，而不是默认显示 arXiv

### 测试与验收

- [ ] 为多源论文池解析增加单元测试
- [ ] 为跨源去重规则增加单元测试
- [ ] 为非 arXiv 论文进入推荐链路增加回归测试
- [ ] 为 docs 生成的无 PDF 降级路径增加测试

