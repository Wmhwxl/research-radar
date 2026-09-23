const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');

const DPRSiteStats = require('../app/site-stats.js');

function createStorage() {
  const data = new Map();
  return {
    getItem(key) {
      return data.has(key) ? data.get(key) : null;
    },
    setItem(key, value) {
      data.set(key, String(value));
    },
    removeItem(key) {
      data.delete(key);
    },
  };
}

function createElement() {
  return {
    hidden: true,
    textContent: '',
    innerHTML: '',
    attributes: new Map(),
    setAttribute(name, value) {
      this.attributes.set(name, String(value));
    },
    removeAttribute(name) {
      this.attributes.delete(name);
    },
  };
}

function createDocument(elements, readyState = 'complete') {
  const listeners = new Map();
  return {
    readyState,
    querySelector(selector) {
      return elements[selector] || null;
    },
    addEventListener(type, handler) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(handler);
    },
    dispatch(type) {
      const handlers = listeners.get(type) || [];
      handlers.forEach((handler) => handler());
    },
    getListeners(type) {
      return listeners.get(type) || [];
    },
  };
}

function createStatDom() {
  const elements = {
    '[data-dpr-site-stats]': createElement(),
    '[data-dpr-daily-readers]': createElement(),
    '[data-dpr-yesterday-readers]': createElement(),
    '[data-dpr-fork-count]': createElement(),
    '[data-dpr-history-chart]': createElement(),
    '[data-dpr-history-range]': createElement(),
    '[data-dpr-history-peak]': createElement(),
  };
  return {
    elements,
    document: createDocument(elements),
  };
}

function createFetchStub(handlers) {
  const calls = [];
  async function fetchStub(url, options = {}) {
    calls.push({ url, options });
    for (const handler of handlers) {
      const matched = handler.match(url, options);
      if (matched) return handler.reply(url, options, calls.length - 1);
    }
    throw new Error(`unexpected fetch: ${url}`);
  }
  fetchStub.calls = calls;
  return fetchStub;
}

function jsonResponse(ok, payload, status = ok ? 200 : 500) {
  return {
    ok,
    status,
    async json() {
      return payload;
    },
  };
}

function emptyResponse(ok, status = ok ? 201 : 500) {
  return {
    ok,
    status,
    async json() {
      return {};
    },
  };
}

function makeHistoryRows(entries) {
  return entries.map(([visitDate, readerCount]) => ({
    visit_date: visitDate,
    reader_count: readerCount,
  }));
}

function buildStats(options = {}) {
  const dom = options.dom || createStatDom();
  const storage = options.storage || createStorage();
  const fetch = options.fetch;
  const clock = options.now;
  const windowLike = {
    document: dom.document,
    localStorage: storage,
    fetch,
    crypto: webcrypto,
    DPR_SITE_STATS_CONFIG: options.config,
  };
  return {
    dom,
    storage,
    stats: DPRSiteStats.createSiteStats({
      window: windowLike,
      document: dom.document,
      localStorage: storage,
      fetch,
      crypto: webcrypto,
      githubToken: options.githubToken,
      config: options.config,
      now: clock,
    }),
  };
}

async function testForkRequestUsesGithubTokenWhenAvailable() {
  const fetch = createFetchStub([
    {
      match: (url) => url.includes('/site_daily_reader_events'),
      reply: async () => emptyResponse(true, 201),
    },
    {
      match: (url) => url.includes('/site_daily_reader_counts'),
      reply: async () => jsonResponse(true, makeHistoryRows([['2026-07-19', 1]])),
    },
    {
      match: (url) => url.includes('api.github.com/repos/ziwenhahaha/daily-paper-reader'),
      reply: async (_url, options) => {
        assert.equal(options.headers.Authorization, 'Bearer github-test-token');
        return jsonResponse(true, { forks_count: 2 });
      },
    },
  ]);
  const built = buildStats({
    fetch,
    githubToken: 'github-test-token',
    now: () => new Date('2026-07-19T03:00:00Z'),
  });

  const result = await built.stats.init();
  assert.equal(result.ok, true);
}

async function testBeijingCrossDayUsesLocalDateBoundary() {
  const postDates = [];
  const countUrls = [];
  const fetch = createFetchStub([
    {
      match: (url) => url.includes('/site_daily_reader_events'),
      reply: async () => emptyResponse(true, 201),
    },
    {
      match: (url) => url.includes('/site_daily_reader_counts'),
      reply: async (url) => {
        countUrls.push(url);
        const today = new URL(url).searchParams.getAll('visit_date')[1].replace('lte.', '');
        return jsonResponse(true, makeHistoryRows([[today, 7]]));
      },
    },
    {
      match: (url) => url.includes('api.github.com/repos/ziwenhahaha/daily-paper-reader'),
      reply: async () => jsonResponse(true, { forks_count: 9 }),
    },
  ]);
  const storage = createStorage();
  const domA = createStatDom();
  const first = buildStats({
    dom: domA,
    storage,
    fetch,
    now: () => new Date('2026-07-19T15:59:59Z'),
  });
  const domB = createStatDom();
  const second = buildStats({
    dom: domB,
    storage,
    fetch,
    now: () => new Date('2026-07-19T16:00:00Z'),
  });

  assert.equal(DPRSiteStats.getBeijingDateString('2026-07-19T15:59:59Z'), '2026-07-19');
  assert.equal(DPRSiteStats.getBeijingDateString('2026-07-19T16:00:00Z'), '2026-07-20');

  await first.stats.init();
  postDates.push(storage.getItem(DPRSiteStats.DEFAULTS.storageKeys.successDate));
  await second.stats.init();
  postDates.push(storage.getItem(DPRSiteStats.DEFAULTS.storageKeys.successDate));

  const postCalls = fetch.calls.filter((call) => call.url.includes('/site_daily_reader_events'));
  assert.equal(postCalls.length, 2, 'crossing midnight in Beijing should POST again for the new day');
  assert.equal(postDates[0], '2026-07-19');
  assert.equal(postDates[1], '2026-07-20');
  assert.deepEqual(
    new URL(countUrls[0]).searchParams.getAll('visit_date'),
    ['gte.2026-07-06', 'lte.2026-07-19'],
  );
  assert.deepEqual(
    new URL(countUrls[1]).searchParams.getAll('visit_date'),
    ['gte.2026-07-07', 'lte.2026-07-20'],
  );
}

async function testSameDayPostIsIdempotentAfterFirstSuccess() {
  const fetch = createFetchStub([
    {
      match: (url) => url.includes('/site_daily_reader_events'),
      reply: async (_url, options) => {
        assert.equal(options.method, 'POST');
        assert.equal(
          options.headers.Prefer,
          'return=minimal',
          'POST should request a minimal response without requiring raw-table SELECT access',
        );
        const body = JSON.parse(options.body);
        assert.match(body.visitor_hash, /^[a-f0-9]{64}$/);
        assert.equal(body.visit_date, '2026-07-19');
        return emptyResponse(true, 201);
      },
    },
    {
      match: (url) => url.includes('/site_daily_reader_counts'),
      reply: async () =>
        jsonResponse(
          true,
          makeHistoryRows([
            ['2026-07-06', 1],
            ['2026-07-18', 11],
            ['2026-07-19', 12],
          ]),
        ),
    },
    {
      match: (url) => url.includes('api.github.com/repos/ziwenhahaha/daily-paper-reader'),
      reply: async () => jsonResponse(true, { forks_count: 1491 }),
    },
  ]);
  const built = buildStats({
    fetch,
    now: () => new Date('2026-07-19T03:00:00Z'),
  });

  await built.stats.init();
  await built.stats.init();

  const postCalls = fetch.calls.filter((call) => call.url.includes('/site_daily_reader_events'));
  const countCalls = fetch.calls.filter((call) => call.url.includes('/site_daily_reader_counts'));
  const githubCalls = fetch.calls.filter((call) => call.url.includes('api.github.com/repos/ziwenhahaha/daily-paper-reader'));

  assert.equal(postCalls.length, 1, 'same-day re-init should not POST again after the first success');
  assert.equal(countCalls.length, 2, 'each init should refresh the 14-day history once');
  assert.equal(githubCalls.length, 1, 'fork count should come from cache within 6 hours');
  assert.equal(
    built.storage.getItem(DPRSiteStats.DEFAULTS.storageKeys.successDate),
    '2026-07-19',
  );
  assert.equal(built.dom.elements['[data-dpr-site-stats]'].hidden, false);
  assert.equal(built.dom.elements['[data-dpr-daily-readers]'].textContent, '12');
  assert.equal(built.dom.elements['[data-dpr-yesterday-readers]'].textContent, '11');
  assert.equal(built.dom.elements['[data-dpr-fork-count]'].textContent, '1,491');
  assert.equal(built.dom.elements['[data-dpr-history-range]'].textContent, '7/6-7/19');
  assert.equal(built.dom.elements['[data-dpr-history-peak]'].textContent, '12');
  assert.match(built.dom.elements['[data-dpr-history-chart]'].innerHTML, /<svg[\s\S]*aria-hidden="true"/);
  assert.match(built.dom.elements['[data-dpr-history-chart]'].innerHTML, /class="dpr-home-history-area"/);
  assert.match(built.dom.elements['[data-dpr-history-chart]'].innerHTML, /class="dpr-home-history-line"/);
  assert.match(built.dom.elements['[data-dpr-history-chart]'].innerHTML, /<circle /);
}

async function testHistoryFetchPadsMissingDatesAcrossMonth() {
  let capturedUrl = '';
  const fetch = createFetchStub([
    {
      match: (url) => url.includes('/site_daily_reader_counts'),
      reply: async (url) => {
        capturedUrl = url;
        return jsonResponse(
          true,
          makeHistoryRows([
            ['2026-02-27', 3],
            ['2026-03-02', 9],
          ]),
        );
      },
    },
  ]);
  const built = buildStats({
    fetch,
    config: {
      historyDays: 4,
    },
  });

  const result = await built.stats.fetchDailyReaderCount('2026-03-02');

  assert.equal(result.ok, true);
  assert.equal(result.readerCount, 9);
  assert.equal(result.todayCount, 9);
  assert.equal(result.yesterdayCount, 0);
  assert.deepEqual(result.history, [
    { date: '2026-02-27', count: 3 },
    { date: '2026-02-28', count: 0 },
    { date: '2026-03-01', count: 0 },
    { date: '2026-03-02', count: 9 },
  ]);

  const params = new URL(capturedUrl).searchParams;
  assert.deepEqual(params.getAll('visit_date'), ['gte.2026-02-27', 'lte.2026-03-02']);
  assert.equal(params.get('order'), 'visit_date.asc');
  assert.equal(params.get('limit'), '4');
}

async function testDuplicateConflictCountsAsRecorded() {
  let postAttempts = 0;
  const fetch = createFetchStub([
    {
      match: (url) => url.includes('/site_daily_reader_events'),
      reply: async () => {
        postAttempts += 1;
        return emptyResponse(false, 409);
      },
    },
    {
      match: (url) => url.includes('/site_daily_reader_counts'),
      reply: async () => jsonResponse(true, makeHistoryRows([['2026-07-19', 6]])),
    },
    {
      match: (url) => url.includes('api.github.com/repos/ziwenhahaha/daily-paper-reader'),
      reply: async () => jsonResponse(true, { forks_count: 7 }),
    },
  ]);
  const built = buildStats({
    fetch,
    now: () => new Date('2026-07-19T03:00:00Z'),
  });

  const first = await built.stats.init();
  const second = await built.stats.init();

  assert.equal(first.ok, true);
  assert.equal(second.ok, true);
  assert.equal(postAttempts, 1);
  assert.equal(
    built.storage.getItem(DPRSiteStats.DEFAULTS.storageKeys.successDate),
    '2026-07-19',
  );
}

async function testPaperPageStillRecordsDailyReaderWithoutHomeTargets() {
  const document = createDocument({});
  const storage = createStorage();
  const fetch = createFetchStub([
    {
      match: (url) => url.includes('/site_daily_reader_events'),
      reply: async () => emptyResponse(true, 201),
    },
  ]);
  const stats = DPRSiteStats.createSiteStats({
    window: { document, localStorage: storage, fetch, crypto: webcrypto },
    document,
    localStorage: storage,
    fetch,
    crypto: webcrypto,
    now: () => new Date('2026-07-19T03:00:00Z'),
  });

  const result = await stats.init();

  assert.equal(result.ok, true);
  assert.equal(result.displayed, false);
  assert.equal(fetch.calls.length, 1);
  assert.ok(fetch.calls[0].url.includes('/site_daily_reader_events'));
}

async function testPostFailureDoesNotPersistSuccessDate() {
  let postAttempts = 0;
  const fetch = createFetchStub([
    {
      match: (url) => url.includes('/site_daily_reader_events'),
      reply: async () => {
        postAttempts += 1;
        return emptyResponse(false, 500);
      },
    },
    {
      match: (url) => url.includes('/site_daily_reader_counts'),
      reply: async () => jsonResponse(true, makeHistoryRows([['2026-07-19', 99]])),
    },
    {
      match: (url) => url.includes('api.github.com/repos/ziwenhahaha/daily-paper-reader'),
      reply: async () => jsonResponse(true, { forks_count: 88 }),
    },
  ]);
  const built = buildStats({
    fetch,
    now: () => new Date('2026-07-19T03:00:00Z'),
  });

  await built.stats.init();
  await built.stats.init();

  assert.equal(postAttempts, 2, 'POST should be retried if the earlier same-day attempt failed');
  assert.equal(built.storage.getItem(DPRSiteStats.DEFAULTS.storageKeys.successDate), null);
  assert.equal(built.dom.elements['[data-dpr-site-stats]'].hidden, true);
}

async function testForkCacheExpiresAfterSixHours() {
  let githubForkCount = 10;
  let todayReaderCount = 5;
  const fetch = createFetchStub([
    {
      match: (url) => url.includes('/site_daily_reader_events'),
      reply: async () => emptyResponse(true, 201),
    },
    {
      match: (url) => url.includes('/site_daily_reader_counts'),
      reply: async (url) => {
        const today = new URL(url).searchParams.getAll('visit_date')[1].replace('lte.', '');
        return jsonResponse(true, makeHistoryRows([[today, todayReaderCount]]));
      },
    },
    {
      match: (url) => url.includes('api.github.com/repos/ziwenhahaha/daily-paper-reader'),
      reply: async () => jsonResponse(true, { forks_count: githubForkCount }),
    },
  ]);
  const storage = createStorage();
  const first = buildStats({
    storage,
    fetch,
    now: () => new Date('2026-07-19T00:00:00Z'),
  });
  await first.stats.init();

  githubForkCount = 11;
  todayReaderCount = 6;
  const second = buildStats({
    storage,
    fetch,
    now: () => new Date('2026-07-19T03:00:00Z'),
  });
  await second.stats.init();

  githubForkCount = 15;
  todayReaderCount = 7;
  const third = buildStats({
    storage,
    fetch,
    now: () => new Date('2026-07-19T07:00:01Z'),
  });
  await third.stats.init();

  const githubCalls = fetch.calls.filter((call) => call.url.includes('api.github.com/repos/ziwenhahaha/daily-paper-reader'));
  assert.equal(githubCalls.length, 2, 'fork cache should be reused inside 6 hours and refreshed after expiry');
  assert.equal(third.dom.elements['[data-dpr-fork-count]'].textContent, '15');
}

async function testFailureKeepsStatsHidden() {
  const fetch = createFetchStub([
    {
      match: (url) => url.includes('/site_daily_reader_events'),
      reply: async () => emptyResponse(true, 201),
    },
    {
      match: (url) => url.includes('/site_daily_reader_counts'),
      reply: async () => jsonResponse(true, makeHistoryRows([['2026-07-19', 21]])),
    },
    {
      match: (url) => url.includes('api.github.com/repos/ziwenhahaha/daily-paper-reader'),
      reply: async () => emptyResponse(false, 503),
    },
  ]);
  const built = buildStats({
    fetch,
    now: () => new Date('2026-07-19T03:00:00Z'),
  });

  const result = await built.stats.init();
  assert.equal(result.ok, false);
  assert.equal(result.reason, 'fork-failed');
  assert.equal(built.dom.elements['[data-dpr-site-stats]'].hidden, true);
}

function testBrowserGlobalExposureAndAutoInitHook() {
  const source = fs.readFileSync(require.resolve('../app/site-stats.js'), 'utf8');
  const dom = createStatDom();
  const storage = createStorage();
  const sandbox = {
    console,
    TextEncoder,
    Intl,
    Date,
    Promise,
    setTimeout,
    clearTimeout,
    Uint8Array,
    Math,
    window: {
      document: dom.document,
      localStorage: storage,
      crypto: webcrypto,
      DPR_SITE_STATS_CONFIG: {
        forkCacheMs: 1,
      },
      fetch: async (url) => {
        if (url.includes('/site_daily_reader_events')) return emptyResponse(true, 201);
        if (url.includes('/site_daily_reader_counts')) {
          return jsonResponse(true, makeHistoryRows([['2026-07-19', 2]]));
        }
        if (url.includes('api.github.com/repos/ziwenhahaha/daily-paper-reader')) return jsonResponse(true, { forks_count: 3 });
        throw new Error(`unexpected fetch: ${url}`);
      },
    },
  };
  sandbox.globalThis = sandbox;
  sandbox.document = sandbox.window.document;
  sandbox.crypto = webcrypto;

  vm.runInNewContext(source, sandbox, { filename: 'app/site-stats.js' });

  assert.ok(sandbox.window.DPRSiteStats, 'browser global build should expose window.DPRSiteStats');
  assert.ok(
    sandbox.window.document.getListeners('dpr-docsify-ready').length >= 1,
    'browser global build should listen for dpr-docsify-ready re-init',
  );
}

Promise.resolve()
  .then(testBeijingCrossDayUsesLocalDateBoundary)
  .then(testSameDayPostIsIdempotentAfterFirstSuccess)
  .then(testHistoryFetchPadsMissingDatesAcrossMonth)
  .then(testForkRequestUsesGithubTokenWhenAvailable)
  .then(testDuplicateConflictCountsAsRecorded)
  .then(testPaperPageStillRecordsDailyReaderWithoutHomeTargets)
  .then(testPostFailureDoesNotPersistSuccessDate)
  .then(testForkCacheExpiresAfterSixHours)
  .then(testFailureKeepsStatsHidden)
  .then(testBrowserGlobalExposureAndAutoInitHook)
  .then(() => {
    console.log('site stats tests passed');
  })
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
