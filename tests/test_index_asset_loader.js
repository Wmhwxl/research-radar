const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function extractAssetLoaderScript(html) {
  const scripts = [...String(html).matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
  const script = scripts.find((body) => body.includes('window.DPRLoadAssets'));
  assert.ok(script, 'index.html should contain DPRLoadAssets bootstrap script');
  return script;
}

async function runAssetLoader(hostname, assets, windowOverrides = {}, appendElement) {
  const appended = [];
  const fetches = [];
  const timers = new Set();
  const sandbox = {
    console,
    location: { hostname },
    window: { ...windowOverrides },
    fetch(url, options) {
      fetches.push({ url, options: options || {} });
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ ok: true }),
      });
    },
    setTimeout() {
      const id = Symbol('timer');
      timers.add(id);
      return id;
    },
    clearTimeout(id) {
      timers.delete(id);
    },
    document: {
      createElement(tagName) {
        return {
          tagName: String(tagName || '').toLowerCase(),
          remove() {},
          setAttribute(key, value) {
            this[key] = value;
          },
        };
      },
      head: {
        appendChild(el) {
          appended.push(el);
          if (typeof appendElement === 'function' && appendElement(el, appended)) return;
          if (typeof el.onload === 'function') setImmediate(el.onload);
        },
      },
    },
  };
  sandbox.window.fetch = sandbox.fetch;
  sandbox.window.setTimeout = sandbox.setTimeout;
  sandbox.window.clearTimeout = sandbox.clearTimeout;

  const script = extractAssetLoaderScript(fs.readFileSync('index.html', 'utf8'));
  vm.runInNewContext(script, sandbox, { filename: 'index.html' });
  await sandbox.window.DPRLoadAssets(assets);
  appended.fetches = fetches;
  appended.jsonPromises = sandbox.window.DPR_ASSET_JSON_PROMISES || {};
  return appended;
}

async function testLocalScriptRetriesAfterTransientFailure() {
  let scriptAttempts = 0;
  await runAssetLoader(
    'localhost',
    [{ type: 'script', path: 'app/zotero-chat-utils.js' }],
    {},
    (element) => {
      if (element.tagName !== 'script') return false;
      scriptAttempts += 1;
      if (scriptAttempts === 1) {
        setImmediate(element.onerror);
      } else {
        setImmediate(element.onload);
      }
      return true;
    },
  );

  assert.equal(scriptAttempts, 2, 'local scripts should retry once after a transient failure');
}

function testInitialLoadFailureCannotLeavePendingBlankScreen() {
  const html = fs.readFileSync('index.html', 'utf8');
  assert.match(html, /window\.DPRShowInitialLoadError\s*=\s*function/);
  assert.match(html, /app\.removeAttribute\(['"]data-dpr-pending['"]\)/);
  assert.match(html, /secretGate\.classList\.add\(['"]secret-gate-hidden['"]\)/);
  assert.match(html, /window\.DPRShowInitialLoadError\(err\)/);
  assert.match(
    html,
    /if\s*\(app\s*&&\s*app\.hasAttribute\(['"]data-dpr-pending['"]\)\)\s*return/,
    'window load fallback must not hide the splash while the app is still pending',
  );
}

async function testProjectAssetsPreferLocalOnCdnHosts() {
  const appended = await runAssetLoader('example.github.io', [
    { type: 'style', path: 'app/app.css' },
    { type: 'style', path: 'app/vendor/docsify/4/lib/themes/vue.css' },
    { type: 'script', path: 'app/dpr-sidebar.js' },
    { type: 'script', path: 'app/vendor/docsify/4/lib/docsify.min.js' },
  ]);
  const hrefs = appended.map((el) => el.href || el.src || '');

  assert.ok(hrefs.includes('app/app.css'));
  assert.ok(hrefs.includes('app/dpr-sidebar.js'));
  assert.ok(hrefs.includes('https://cdn.zwwen.online/app/vendor/docsify/4/lib/themes/vue.css'));
  assert.ok(hrefs.includes('https://cdn.zwwen.online/app/vendor/docsify/4/lib/docsify.min.js'));
}

async function testExplicitCdnBaseStillUsesVendorCdnOnly() {
  const appended = await runAssetLoader('127.0.0.1', [
    { type: 'script', path: 'app/dpr-sidebar.js' },
    { type: 'script', path: 'app/vendor/docsify/4/lib/docsify.min.js' },
  ], { DPR_CDN_BASE: 'https://assets.example.test' });
  const srcs = appended.map((el) => el.href || el.src || '');

  assert.ok(srcs.includes('app/dpr-sidebar.js'));
  assert.ok(srcs.includes('https://assets.example.test/app/vendor/docsify/4/lib/docsify.min.js'));
}

async function testVersionedAppAssetsUseImmutableCdnPath() {
  const appended = await runAssetLoader('example.github.io', [
    { type: 'style', path: 'app/app.css' },
    { type: 'script', path: 'app/dpr-sidebar.js' },
    { type: 'script', path: 'app/vendor/docsify/4/lib/docsify.min.js' },
  ], { DPR_APP_ASSET_VERSION: 'abc1234' });
  const urls = appended.map((el) => el.href || el.src || '');

  assert.ok(urls.includes('https://cdn.zwwen.online/dpr/assets/abc1234/app/app.css'));
  assert.ok(urls.includes('https://cdn.zwwen.online/dpr/assets/abc1234/app/dpr-sidebar.js'));
  assert.ok(urls.includes('https://cdn.zwwen.online/app/vendor/docsify/4/lib/docsify.min.js'));
}

async function testLatestIsRejectedAsAppAssetVersion() {
  const appended = await runAssetLoader('example.github.io', [
    { type: 'style', path: 'app/app.css' },
    { type: 'script', path: 'app/dpr-sidebar.js' },
  ], { DPR_APP_ASSET_VERSION: 'latest' });
  const urls = appended.map((el) => el.href || el.src || '');

  assert.ok(urls.includes('app/app.css'));
  assert.ok(urls.includes('app/dpr-sidebar.js'));
}

async function testJsonAssetsArePrefetchedWithAssetBatch() {
  const appended = await runAssetLoader('example.github.io', [
    { type: 'json', path: 'app/conference-stats.json' },
    { type: 'script', path: 'app/subscriptions.manager.js' },
  ]);
  const urls = appended.map((el) => el.href || el.src || '');

  assert.ok(!urls.includes('app/conference-stats.json'));
  assert.deepEqual(appended.fetches.map((item) => item.url), ['app/conference-stats.json']);
  assert.equal(appended.fetches[0].options.cache, 'force-cache');
  assert.ok(appended.jsonPromises['app/conference-stats.json']);
}

function testFeedbackModuleLoadsAfterGithubToken() {
  const html = fs.readFileSync('index.html', 'utf8');
  const tokenIndex = html.indexOf("path: 'app/subscriptions.github-token.js'");
  const feedbackIndex = html.indexOf("path: 'app/feedback.issue.js'");

  assert.ok(tokenIndex >= 0, 'GitHub token module should be loaded');
  assert.ok(feedbackIndex > tokenIndex, 'feedback module should load after GitHub token module');
}

Promise.resolve()
  .then(testLocalScriptRetriesAfterTransientFailure)
  .then(testProjectAssetsPreferLocalOnCdnHosts)
  .then(testExplicitCdnBaseStillUsesVendorCdnOnly)
  .then(testVersionedAppAssetsUseImmutableCdnPath)
  .then(testLatestIsRejectedAsAppAssetVersion)
  .then(testJsonAssetsArePrefetchedWithAssetBatch)
  .then(testFeedbackModuleLoadsAfterGithubToken)
  .then(testInitialLoadFailureCannotLeavePendingBlankScreen)
  .then(() => {
    console.log('index asset loader tests passed');
  })
  .catch((err) => {
    console.error(err);
    process.exit(1);
  });
