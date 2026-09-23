const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function sandbox() {
  const timers = new Map();
  let nextTimer = 0;
  const listeners = new Map();
  const context = {
    window: {
      location: { origin: 'https://tester.github.io', hostname: 'tester.github.io', pathname: '/papers/', href: 'https://tester.github.io/papers/' },
      addEventListener: (name, fn) => listeners.set(name, fn),
      removeEventListener: (name) => listeners.delete(name),
    },
    document: { readyState: 'loading', addEventListener() {} },
    console: { warn() {}, error() {}, log() {} },
    URL, AbortController,
    setTimeout(fn, ms) { const id = ++nextTimer; timers.set(id, { fn, ms }); return id; },
    clearTimeout: (id) => timers.delete(id),
    setInterval() { return 1; }, clearInterval() {},
  };
  vm.createContext(context);
  return { context, timers, listeners };
}

function secretSandbox() {
  const s = sandbox();
  const code = fs.readFileSync('app/secret.session.js', 'utf8')
    .replace(/\}\)\(\);\s*$/, 'window.probe = {fetchStaticSecretPayload, pingChatModels, init, resolveRerankerConfig, RERANKER_PROFILES};})();');
  vm.runInContext(code, s.context);
  return s;
}

const response = (status, data) => ({
  ok: status >= 200 && status < 300, status, statusText: status === 401 ? 'Unauthorized' : '',
  json: async () => data, text: async () => 'test response',
});

async function testSecretReadFailuresAndRetry() {
  const { context, timers } = secretSandbox();
  let calls = 0;
  context.fetch = async () => { calls++; return response(503); };
  await assert.rejects(context.window.probe.fetchStaticSecretPayload(), /503/);
  assert.equal(calls, 2);
  context.fetch = async () => response(404);
  assert.equal(await context.window.probe.fetchStaticSecretPayload(), null);
  const payload = { salt: 'salt', iv: 'iv', ciphertext: 'cipher' };
  calls = 0;
  context.fetch = async () => ++calls === 1 ? response(503) : response(200, payload);
  assert.equal(await context.window.probe.fetchStaticSecretPayload(), payload);
  assert.equal(calls, 2);
  context.fetch = async () => response(200, null);
  await assert.rejects(context.window.probe.fetchStaticSecretPayload());
  context.fetch = async () => { throw new TypeError('Failed to fetch'); };
  await assert.rejects(context.window.probe.fetchStaticSecretPayload(), /Failed to fetch/);
  assert.equal(timers.size, 0);
}

async function testDeepSeekTimeoutAndHttpError() {
  const { context, timers } = secretSandbox();
  context.fetch = (_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(options.signal.reason));
  });
  const entries = [{ model: 'deepseek-v4-flash', apiKey: 'test-only', baseUrl: 'https://api.deepseek.com' }];
  const pending = context.window.probe.pingChatModels(entries, null);
  const timer = [...timers.values()].find(t => t.ms === 20000);
  assert.ok(timer);
  timer.fn();
  await assert.rejects(pending, { message: 'DeepSeek 连接测试超时，请稍后重试' });
  assert.equal(timers.size, 0);
  context.fetch = async () => response(401);
  await assert.rejects(context.window.probe.pingChatModels(entries, null), /HTTP 401/);
}

async function testSecretErrorUiPreservesPasswordAndCanRetry() {
  const { context } = secretSandbox();
  const nodes = {};
  const makeNode = () => ({
    style: {}, classList: { add() {}, remove() {}, toggle() {} }, listeners: {},
    addEventListener(name, fn) { this.listeners[name] = fn; },
  });
  nodes['secret-gate-overlay'] = makeNode();
  const modal = nodes['secret-gate-modal'] = makeNode();
  let html = '';
  Object.defineProperty(modal, 'innerHTML', { get: () => html, set(value) {
    html = value;
    for (const match of value.matchAll(/id="([^"]+)"/g)) nodes[match[1]] = makeNode();
  } });
  const stored = new Map([['dpr_secret_password_v1', 'saved-password']]);
  context.window.localStorage = { getItem: k => stored.get(k), removeItem: k => stored.delete(k) };
  context.document.getElementById = id => nodes[id] || null;
  context.requestAnimationFrame = fn => fn();
  context.fetch = async () => response(503);
  context.window.probe.init();
  for (let i = 0; i < 30; i++) await Promise.resolve();
  assert.match(html, /暂时无法读取密钥配置/);
  assert.equal(html.includes('新配置指引'), false);
  assert.equal(stored.get('dpr_secret_password_v1'), 'saved-password');
  context.fetch = async () => response(404);
  const retry = nodes['secret-load-retry'];
  retry.listeners.click({ currentTarget: retry });
  for (let i = 0; i < 30; i++) await Promise.resolve();
  assert.match(html, /新配置指引/);
}

async function testResetWaitsForAcknowledgement() {
  const { context, listeners } = sandbox();
  context.window.DPR_ACCESS_MODE = 'full';
  context.window.prompt = () => 'RESET_ALL';
  let release, calls = 0;
  context.window.DPRWorkflowRunner = { runWorkflowByKey() {
    calls++;
    return new Promise(resolve => { release = resolve; });
  } };
  const code = fs.readFileSync('app/subscriptions.manager.js', 'utf8')
    .replace('__test: {', '__test: {runResetContent, setResetButton: b => {resetContentBtn=b;},');
  vm.runInContext(code, context);
  const api = context.window.SubscriptionsManager.__test;
  const button = { disabled: false };
  api.setResetButton(button);
  const msg = { textContent: '', style: {} };
  const pending = api.runResetContent(msg);
  assert.equal(/已发起|已提交/.test(msg.textContent), false);
  assert.equal(button.disabled, true);
  assert.ok(listeners.has('beforeunload'));
  await api.runResetContent(msg);
  assert.equal(calls, 1);
  release(false);
  await pending;
  assert.equal(/已发起|已提交/.test(msg.textContent), false);
  assert.equal(button.disabled, false);
  assert.equal(listeners.has('beforeunload'), false);
  context.window.DPRWorkflowRunner.runWorkflowByKey = async () => true;
  await api.runResetContent(msg);
  assert.match(msg.textContent, /已提交/);
  context.window.DPRWorkflowRunner.runWorkflowByKey = async () => { throw new Error('offline'); };
  await api.runResetContent(msg);
  assert.match(msg.textContent, /offline/);
  assert.equal(button.disabled, false);
}

async function testWorkflowReturnsDispatchResultBeforeMonitoring() {
  for (const [status, monitorFailure] of [[204, false], [403, false], [204, true]]) {
    const { context } = sandbox();
    context.window.decoded_secret_private = { github: { token: 'test-only' } };
    context.fetch = async (url, init = {}) => {
      if (url.endsWith('/dispatches')) return response(status);
      if (url.includes('event=workflow_dispatch')) return monitorFailure ? response(503) : new Promise(() => {});
      if (url.includes('/runs?')) return response(200, { workflow_runs: [] });
      return response(200, { default_branch: 'main', fork: true });
    };
    const code = fs.readFileSync('app/workflows.runner.js', 'utf8')
      .replace(/\n  return \{\n/, '\n  return {\n    dispatchAndMonitor, setUi: (s,r) => {statusEl=s;runsEl=r;},\n');
    vm.runInContext(code, context);
    const api = context.window.DPRWorkflowRunner;
    const statusEl = { textContent: '', style: {}, classList: { toggle() {} } };
    api.setUi(statusEl, { innerHTML: '' });
    let settled = false, value;
    api.dispatchAndMonitor({ key: 'reset-content', id: 'reset-content.yml' }).then(v => { settled = true; value = v; });
    for (let i = 0; i < 50; i++) await Promise.resolve();
    assert.equal(settled, true, 'dispatch acknowledgement must not wait for run-list polling');
    assert.equal(value, status === 204);
    if (monitorFailure) assert.match(statusEl.textContent, /任务已提交，但读取进度失败/);
  }
}

async function testLegacyLocalRerankerMovesToCloud() {
  const {context} = secretSandbox();
  const value = context.window.probe.resolveRerankerConfig({rerankerLLM:{profile:'local-qwen3-0.6b',provider:'local',baseUrl:'http://localhost:9999',apiKey:'private-local-test'}});
  assert.equal(value.provider,'public_zwwen');
  assert.equal(value.baseUrl,'https://zwwen.online/rerank');
  assert.equal(value.apiKey,'');
  assert.equal(context.window.probe.RERANKER_PROFILES.some(p => p.provider==='local'),false);
}

(async () => {
  for (const test of [testLegacyLocalRerankerMovesToCloud, testSecretReadFailuresAndRetry, testDeepSeekTimeoutAndHttpError, testSecretErrorUiPreservesPasswordAndCanRetry,
    testResetWaitsForAcknowledgement, testWorkflowReturnsDispatchResultBeforeMonitoring]) {
    await test();
    console.log(test.name + ' passed');
  }
})().catch(error => { console.error(error); process.exit(1); });
