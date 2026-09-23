const assert = require('node:assert/strict');

const {
  stripFrontMatter,
  buildShareMarkdown,
} = require('../app/gist-share-utils.js');

const samplePageMarkdown = `---
title: Attention Is All You Need
title_zh: 注意力即一切
authors: "Ashish Vaswani, Noam Shazeer"
date: 20170612
pdf: "https://arxiv.org/pdf/1706.03762v1"
tags: ["query:transformer", "query:attention"]
evidence: 提出Transformer纯注意力架构。
tldr: 经典论文。
abstract_en: |
  The dominant sequence transduction models...
---

## 摘要
中文摘要内容。

## Abstract
English abstract content.
`;

function testStripFrontMatter() {
  const parsed = stripFrontMatter(samplePageMarkdown);
  assert.equal(parsed.meta.title, 'Attention Is All You Need');
  assert.equal(parsed.meta.title_zh, '注意力即一切');
  assert.deepEqual(parsed.meta.tags, ['query:transformer', 'query:attention']);
  assert.ok(parsed.body.startsWith('## 摘要'));
  assert.ok(!parsed.body.startsWith('---'));
}

function testBuildShareMarkdownRemovesFrontMatterAndBuildsHeader() {
  const output = buildShareMarkdown({
    paperId: '201706/12/1706.03762v1-attention-is-all-you-need',
    pageMd: samplePageMarkdown,
    chatMessages: [
      { role: 'user', time: '10:00', content: '这篇论文的核心贡献是什么？' },
      { role: 'ai', time: '10:01', content: '核心是提出 Transformer。' },
    ],
    origin: 'https://ziwenhahaha.github.io/daily-paper-reader',
    generatedAt: '2026-03-09T08:00:00.000Z',
  });

  assert.ok(output.includes('# 注意力即一切'));
  assert.ok(output.includes('_Attention Is All You Need_'));
  assert.ok(output.includes('- **PDF**: https://arxiv.org/pdf/1706.03762v1'));
  assert.ok(output.includes('## 摘要'));
  assert.ok(output.includes('## Abstract'));
  assert.ok(output.includes('## 💬 Chat History（本机记录）'));
  assert.ok(!output.includes('\n---\ntitle:'));
  assert.ok(!output.includes('\ntitle: Attention Is All You Need\n'));
}

testStripFrontMatter();
testBuildShareMarkdownRemovesFrontMatterAndBuildsHeader();

console.log('gist share markdown tests passed');
