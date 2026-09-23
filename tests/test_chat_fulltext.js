const assert = require('node:assert/strict');
global.window = {};
require('../app/chat.discussion.js');
const api = window.PrivateDiscussionChat.__test;
(async () => {
  const body = '# Introduction\n' + 'A theorem and its complete proof. '.repeat(200);
  global.fetch = async () => ({ok: true, text: async () => body});
  const full = await api.loadPaperContext('20250910-20260909/2510.17595v1', () => '摘要');
  assert.equal(full.content, body);
  assert.equal(full.isFullText, true);
  assert.ok(api.paperContextMessage(full).includes('PDF抽取的论文全文'));
  global.fetch = async () => ({ok: false, status: 404});
  const fallback = await api.loadPaperContext('missing', () => '只有摘要');
  assert.equal(fallback.isFullText, false);
  assert.ok(api.paperContextMessage(fallback).includes('不是论文全文'));
  assert.ok(!api.paperContextMessage(fallback).includes('完整纯文本'));
  global.fetch = async () => ({ok: true, text: async () => '<html>error</html>'.repeat(200)});
  assert.equal((await api.loadPaperContext('bad', () => '摘要')).isFullText, false);
  global.fetch = async (url) => url.endsWith('.txt')
    ? {ok: false, status: 404}
    : {ok: true, text: async () => JSON.stringify({status: 'unavailable', reason: '该版本已撤回'})};
  const withdrawn = await api.loadPaperContext('withdrawn', () => '摘要');
  assert.ok(api.paperContextMessage(withdrawn).includes('该版本已撤回'));
  console.log('chat fulltext tests passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
