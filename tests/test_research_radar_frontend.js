const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { performance } = require('node:perf_hooks');
const API = require('../app/research-radar-api.js');
const State = require('../app/research-radar-state.js');
const Graph = require('../app/research-radar-graph.js');
const Papers = require('../app/research-radar-papers.js');
const Detail = require('../app/research-radar-detail-panel.js');

function fixtureFetch(url) {
  const filename = path.join(process.cwd(), String(url));
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(fs.readFileSync(filename, 'utf8'))) });
}

async function testFixtureDataSourceContract() {
  const source = new API.FixtureDataSource({ fetchImpl: fixtureFetch });
  const fields = await source.listResearchFields();
  assert.equal(fields.length, 1);
  const fieldId = fields[0].id;
  const overview = await source.getFieldOverview(fieldId, { startYear: 2022, endYear: 2026 });
  assert.equal(overview.demo_fixture, true);
  assert.equal(overview.paper_count, 10);
  assert.equal(overview.author_count, 10);
  const papers = await source.getFieldPapers(fieldId, { startYear: 2024, endYear: 2026, relevanceLabel: 'core', sort: 'newest' });
  assert.ok(papers.items.every((paper) => paper.year >= 2024 && paper.relevance_label === 'core'));
  const authors = await source.getFieldAuthors(fieldId, { startYear: 2026, endYear: 2026, minimumPapers: 1 });
  assert.ok(authors.items.length > 0);
  assert.ok(authors.items.every((author) => author.first_field_year === 2026));
  const graph = await source.getScholarGraph(fieldId, { startYear: 2025, endYear: 2026, maxNodes: 500 });
  assert.ok(graph.nodes.length > 0 && graph.edges.length > 0);
  assert.ok(graph.edges.every((edge) => edge.first_year >= 2025));
  const author = await source.getAuthorDetail(fieldId, 'a1', { startYear: 2022, endYear: 2026 });
  assert.equal(author.name, 'Alice Morgan');
  assert.ok(author.papers.length === 5 && author.collaborators.length > 0);
  const collaboration = await source.getCollaborationDetail(fieldId, 'a2', 'a1', { startYear: 2022, endYear: 2026 });
  assert.equal(collaboration.shared_paper_count, 3);
}

function testExplicitSourceModeAndNoFallback() {
  assert.throws(() => API.createDataSource({}), /explicitly configured/);
  assert.throws(() => API.createDataSource({ mode: 'supabase' }), /not configured/);
  assert.equal(API.createDataSource({ mode: 'fixture', fetchImpl: fixtureFetch }).mode, 'fixture');
  assert.equal(API.createDataSource({ mode: 'local', fetchImpl: fixtureFetch }).mode, 'local');
}

function testUrlStateRoundTrip() {
  let state = State.defaults(2026);
  state.tab = 'graph'; state.field = 'fixture-field-imr'; state.range = 'custom';
  state.startYear = 2023; state.endYear = 2025; state.maxNodes = 1000; state.coreOnly = true;
  state.graphSearch = 'Alice Morgan';
  const parsed = State.parseHash(State.serialize(state), 2026);
  assert.equal(parsed.tab, 'graph');
  assert.equal(parsed.startYear, 2023);
  assert.equal(parsed.endYear, 2025);
  assert.equal(parsed.maxNodes, 1000);
  assert.equal(parsed.coreOnly, true);
  assert.equal(parsed.graphSearch, 'Alice Morgan');
  state.view = 'search'; state.searchTab = 'authors';
  const searchState = State.parseHash(State.serialize(state), 2026);
  assert.equal(searchState.view, 'search');
  assert.equal(searchState.searchTab, 'authors');
  assert.deepEqual(State.applyRange(state, '3y', 2026), { ...state, range: '3y', startYear: 2024, endYear: 2026 });
}

function testGraphScalingAndLargeElementBuilds() {
  assert.ok(Graph.nodeSize(1) < Graph.nodeSize(4));
  assert.ok(Graph.nodeSize(400) <= 44);
  assert.ok(Graph.edgeWidth(25) <= 7);
  [300, 500, 1000].forEach((count) => {
    const nodes = Array.from({ length: count }, (_, i) => ({ id: `a${i}`, name: `Author ${i}`, field_paper_count: i % 20 + 1 }));
    const edges = Array.from({ length: count - 1 }, (_, i) => ({ source: `a${i}`, target: `a${i + 1}`, field_collaboration_count: i % 5 + 1 }));
    const start = performance.now();
    const elements = Graph.buildElements({ nodes, edges });
    const elapsed = performance.now() - start;
    assert.equal(elements.length, count * 2 - 1);
    assert.ok(elapsed < 1000, `${count}-node element build took ${elapsed}ms`);
  });
}

function testGraphResizeContract() {
  const source = fs.readFileSync('app/research-radar-graph.js', 'utf8');
  assert.ok(source.includes('new ResizeObserver'));
  assert.ok(source.includes('cy.resize()'));
  assert.ok(source.includes('resizeObserver.disconnect()'));
}

function testRenderingSecurityAndDrawerPayloads() {
  assert.equal(Papers.safeUrl('javascript:alert(1)'), '');
  assert.ok(Papers.safeUrl('https://example.com/paper').startsWith('https://'));
  const html = Papers.render({ total: 1, items: [{ title: '<img>', authors: [], year: 2026, venue: 'Demo', relevance_label: 'core', relevance_score: .9, citation_count: null, external_url: 'javascript:bad' }] }, State.defaults(2026));
  assert.ok(html.includes('&lt;img&gt;'));
  assert.ok(!html.includes('href="javascript:'));
  const drawer = Detail.renderAuthor({ id: 'a1', name: 'Alice', primary_institution: null, field_paper_count: 1, total_works: 2, citation_count: 3, first_field_year: 2025, latest_field_year: 2026, collaborators: [{ id: 'a2', name: 'Bo', shared_paper_count: 1 }], papers: [] });
  assert.ok(drawer.includes('Institution unavailable'));
  assert.ok(drawer.includes('data-author-id="a2"'));
}

function testStaticIntegrationContract() {
  const html = fs.readFileSync('index.html', 'utf8');
  const docsify = html.indexOf("path: 'app/vendor/docsify/4/lib/docsify.min.js'");
  ['research-radar-icons.js', 'research-radar-api.js', 'research-radar-state.js', 'research-radar-graph.js', 'research-radar.js'].forEach((asset) => {
    const index = html.indexOf(`path: 'app/${asset}?v=20260922-rr65-3'`);
    assert.ok(index > 0 && index < docsify, `${asset} should load before Docsify`);
  });
  assert.ok(html.includes("path: 'app/research-radar.css?v=20260922-rr65-3'"));
  assert.ok(fs.readFileSync('docs/_sidebar.md', 'utf8').includes('#/research-radar/'));
  assert.ok(fs.readFileSync('docs/research-radar/README.md', 'utf8').includes('research-radar-root'));
  const app = fs.readFileSync('app/research-radar.js', 'utf8');
  assert.ok(app.includes('rr-sidebar'));
  assert.ok(app.includes('Create Research Field'));
  assert.ok(app.includes('Setting up your research radar'));
  assert.ok(app.includes('Understanding your research field'));
  assert.ok(app.includes('rr-command-modal'));
  assert.ok(app.includes('rr-toast-region'));
  assert.ok(app.includes('aria-label="Search papers, authors, and research fields"'));
  assert.ok(app.includes('requestId !== self.tabLoadId'));
  assert.ok(app.includes('rr-theme-'));
  assert.ok(!app.includes('SUPABASE_SERVICE_KEY'));
  assert.ok(app.includes("classList.toggle('rr-page', isRoute())"));
  assert.ok(app.includes("setProperty('display', 'none', 'important')"));
  assert.ok(fs.readFileSync('app/research-radar.css', 'utf8').includes('.rr-page #paper-chat-container'));
  assert.ok(fs.readFileSync('app/research-radar.css', 'utf8').includes('@media (max-width:900px)'));
  assert.ok(fs.readFileSync('app/research-radar.css', 'utf8').includes('@media (max-width:600px)'));
}

function testPhase65ProductUiContracts() {
  const app = fs.readFileSync('app/research-radar.js', 'utf8');
  const css = fs.readFileSync('app/research-radar.css', 'utf8');
  const papers = fs.readFileSync('app/research-radar-papers.js', 'utf8');
  const authors = fs.readFileSync('app/research-radar-authors.js', 'utf8');
  const graph = fs.readFileSync('app/research-radar-graph.js', 'utf8');
  const detail = fs.readFileSync('app/research-radar-detail-panel.js', 'utf8');
  assert.ok(app.includes('rr-home-hero') && app.includes('rr-field-cards'));
  assert.ok(app.includes('rr-modal-backdrop') && app.includes('Advanced options'));
  assert.ok(app.includes('role="tablist"') && app.includes('aria-selected'));
  assert.ok(app.includes('ctrlKey') && app.includes("event.key !== 'Tab'"));
  assert.ok(papers.includes('data-toggle-filters') && papers.includes('data-clear-state'));
  assert.ok(authors.includes('Search authors') && authors.includes('rr-avatar'));
  assert.ok(graph.includes('rr-graph-toolbar') && graph.includes('data-graph-action="fit"'));
  assert.ok(detail.includes('rr-drawer-profile') && detail.includes('rr-avatar-large'));
  assert.ok(css.includes('--rr-surface-secondary') && css.includes('--rr-danger'));
  assert.ok(css.includes('.rr-app[data-theme="dark"]'));
  assert.ok(css.includes('.rr-toast') && css.includes('.rr-command-modal'));
  assert.ok(css.includes('.rr-list-skeleton') && css.includes('.rr-graph-skeleton'));
  assert.ok(css.includes('overflow-x:hidden'));
  assert.ok(css.includes('.rr-drawer-open .rr-graph-primary-filters'));
  assert.ok(!graph.includes('wheelSensitivity'));
}

async function testSupabaseDataSourceUsesAnonRpcContract() {
  const calls = [];
  const source = new API.SupabaseDataSource({ url: 'https://example.supabase.co', anonKey: 'anon-test-only', fetchImpl(url, options) {
    calls.push({ url, options });
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ items: [] }) });
  }});
  await source.getScholarGraph('field-id', { startYear: 2024, endYear: 2026, maxNodes: 500, coreOnly: true });
  assert.ok(calls[0].url.endsWith('/rest/v1/rpc/get_research_field_scholar_graph'));
  assert.equal(calls[0].options.headers.apikey, 'anon-test-only');
  assert.ok(!JSON.stringify(calls[0]).includes('service_role'));
  const body = JSON.parse(calls[0].options.body);
  assert.equal(body.p_max_nodes, 500);
  assert.equal(body.p_core_only, true);
}

async function testLocalApiDataSourceContract() {
  const calls = [];
  const source = new API.LocalApiDataSource({ baseUrl: 'http://127.0.0.1:8765', fetchImpl(url, options) {
    calls.push({ url, options });
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ items: [] }) });
  }});
  await source.getFieldPapers('field/one', { startYear: 2024, endYear: 2026, relevanceLabel: 'core', search: 'graph' });
  assert.ok(calls[0].url.startsWith('http://127.0.0.1:8765/api/research-fields/field%2Fone/papers?'));
  assert.ok(calls[0].url.includes('start_year=2024'));
  assert.ok(calls[0].url.includes('relevance_label=core'));
  assert.equal(calls[0].options.headers.Accept, 'application/json');
  assert.ok(!JSON.stringify(calls[0]).toLowerCase().includes('supabase'));
}

Promise.resolve()
  .then(testFixtureDataSourceContract)
  .then(testExplicitSourceModeAndNoFallback)
  .then(testUrlStateRoundTrip)
  .then(testGraphScalingAndLargeElementBuilds)
  .then(testGraphResizeContract)
  .then(testRenderingSecurityAndDrawerPayloads)
  .then(testStaticIntegrationContract)
  .then(testPhase65ProductUiContracts)
  .then(testSupabaseDataSourceUsesAnonRpcContract)
  .then(testLocalApiDataSourceContract)
  .then(() => console.log('research radar frontend tests passed'))
  .catch((error) => { console.error(error); process.exit(1); });
