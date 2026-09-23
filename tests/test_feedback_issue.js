const assert = require('node:assert/strict');

const feedback = require('../app/feedback.issue.js');

const {
  ISSUE_TYPES,
  TARGET_OWNER,
  TARGET_REPO,
  FEEDBACK_ANIMATION_MS,
  getFeedbackMotionStyles,
  normalizeSelectedTypes,
  buildIssueTitle,
  buildIssueBody,
  validateFeedbackForm,
  buildIssueDraftUrl,
  resolveGithubToken,
  classifyIssueError,
  submitIssueWithFallback,
} = feedback.__test;

function testFeedbackMotionStylesCoverEnterAndExit() {
  const hidden = getFeedbackMotionStyles(false);
  const visible = getFeedbackMotionStyles(true);

  assert.equal(FEEDBACK_ANIMATION_MS, 180);
  assert.equal(hidden.overlay.opacity, '0');
  assert.equal(hidden.panel.opacity, '0');
  assert.match(hidden.panel.transform, /translateY\(12px\)/);
  assert.equal(visible.overlay.opacity, '1');
  assert.equal(visible.panel.opacity, '1');
  assert.equal(visible.panel.transform, 'translateY(0) scale(1)');
}

function buildValidForm(overrides = {}) {
  return {
    types: ['体验问题', '功能新增'],
    title: '侧栏切换后计数不同步',
    content: '切换标签后，当前日期的计数没有立即刷新。',
    confirmPublic: true,
    ...overrides,
  };
}

function testNormalizeSelectedTypesKeepsCanonicalOrder() {
  assert.deepEqual(
    normalizeSelectedTypes(['其他', '功能新增', '功能新增', '体验问题', '无效项']),
    ['功能新增', '体验问题', '其他'],
  );
  assert.deepEqual(normalizeSelectedTypes(new Set(['BUG反馈', '论文 / 会议数据'])), [
    'BUG反馈',
    '论文 / 会议数据',
  ]);
  assert.deepEqual(ISSUE_TYPES.length, 5);
}

function testBuildIssueTitleUsesStrictPrefixFormat() {
  assert.equal(
    buildIssueTitle(['体验问题', '功能新增'], '  [其他]  侧栏宽度在窄屏下异常  '),
    '[功能新增|体验问题] 侧栏宽度在窄屏下异常',
  );
  assert.equal(buildIssueTitle([], '没有类型'), '');
}

function testBuildIssueBodyStaysMinimal() {
  assert.equal(
    buildIssueBody('\n第一行\r\n第二行\n'),
    '第一行\n第二行',
  );
}

function testValidateFeedbackFormRequiresTypeAndConfirmation() {
  const invalid = validateFeedbackForm(buildValidForm({
    types: [],
    confirmPublic: false,
  }));

  assert.equal(invalid.valid, false);
  assert.equal(invalid.errors.types, '请至少选择一个反馈类型。');
  assert.equal(invalid.errors.confirmPublic, '请先确认将公开提交。');

  const valid = validateFeedbackForm(buildValidForm());
  assert.equal(valid.valid, true);
  assert.equal(valid.formattedTitle, '[功能新增|体验问题] 侧栏切换后计数不同步');
  assert.equal(valid.body, '切换标签后，当前日期的计数没有立即刷新。');
}

function testBuildIssueDraftUrlTargetsFixedRepo() {
  const url = new URL(buildIssueDraftUrl({
    title: '[功能新增|体验问题] 标题',
    body: '正文内容',
  }));

  assert.equal(url.origin, 'https://github.com');
  assert.equal(url.pathname, `/${TARGET_OWNER}/${TARGET_REPO}/issues/new`);
  assert.equal(url.searchParams.get('title'), '[功能新增|体验问题] 标题');
  assert.equal(url.searchParams.get('body'), '正文内容');
}

function testResolveGithubTokenPrefersDecodedSecretPrivate() {
  const token = resolveGithubToken({
    decoded_secret_private: {
      github: {
        token: 'secret-token',
      },
    },
    SubscriptionsGithubToken: {
      loadGithubToken() {
        return { token: 'fallback-token' };
      },
    },
  });

  assert.equal(token, 'secret-token');
}

function testClassifyIssueError() {
  assert.equal(classifyIssueError({ status: 401 }), 'auth');
  assert.equal(classifyIssueError({ status: 403 }), 'auth');
  assert.equal(classifyIssueError({ status: 404 }), 'auth');
  assert.equal(classifyIssueError({ status: 422 }), 'validation');
  assert.equal(classifyIssueError({ status: 500 }), 'unknown');
}

async function testSubmitIssueUsesApiWhenTokenAvailable() {
  const calls = [];
  const result = await submitIssueWithFallback(
    buildValidForm(),
    {
      root: {
        decoded_secret_private: {
          github: {
            token: 'secret-token',
          },
        },
      },
      fetchImpl: async (url, init) => {
        calls.push({ url, init });
        return {
          ok: true,
          json: async () => ({
            number: 12,
            html_url: 'https://github.com/ziwenhahaha/daily-paper-reader/issues/12',
          }),
        };
      },
      openDraft: false,
    },
  );

  assert.equal(result.mode, 'api');
  assert.equal(result.issueNumber, 12);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, 'https://api.github.com/repos/ziwenhahaha/daily-paper-reader/issues');
  assert.equal(calls[0].init.headers.Authorization, 'token secret-token');

  const payload = JSON.parse(calls[0].init.body);
  assert.deepEqual(payload, {
    title: '[功能新增|体验问题] 侧栏切换后计数不同步',
    body: '切换标签后，当前日期的计数没有立即刷新。',
  });
}

async function testSubmitIssueFallsBackToDraftWhenNoToken() {
  let openedUrl = '';
  const result = await submitIssueWithFallback(
    buildValidForm(),
    {
      root: {
        open(url) {
          openedUrl = url;
          return {};
        },
      },
    },
  );

  assert.equal(result.mode, 'draft');
  assert.match(result.message, /未检测到可用 GitHub Token/);
  assert.equal(openedUrl, result.draftUrl);

  const url = new URL(openedUrl);
  assert.equal(url.pathname, `/${TARGET_OWNER}/${TARGET_REPO}/issues/new`);
  assert.equal(url.searchParams.get('body'), '切换标签后，当前日期的计数没有立即刷新。');
}

async function testBlockedDraftDoesNotNavigateCurrentPage() {
  let assignedUrl = '';
  const result = await submitIssueWithFallback(
    buildValidForm(),
    {
      root: {
        open() {
          return null;
        },
        location: {
          assign(url) {
            assignedUrl = url;
          },
        },
      },
    },
  );

  assert.equal(result.mode, 'draft');
  assert.equal(result.opened, false);
  assert.equal(assignedUrl, '');
  assert.match(result.message, /再次点击提交按钮/);
}

async function testSubmitIssueFallsBackGracefullyOnAuthFailure() {
  let openedUrl = '';
  const result = await submitIssueWithFallback(
    buildValidForm(),
    {
      root: {
        SubscriptionsGithubToken: {
          loadGithubToken() {
            return { token: 'stored-token' };
          },
        },
        open(url) {
          openedUrl = url;
          return {};
        },
      },
      fetchImpl: async () => ({
        ok: false,
        status: 403,
        json: async () => ({
          message: 'Resource not accessible by personal access token',
        }),
      }),
    },
  );

  assert.equal(result.mode, 'draft');
  assert.equal(result.errorKind, 'auth');
  assert.match(result.message, /缺少仓库或 Issues 权限/);
  assert.equal(openedUrl, result.draftUrl);
}

async function run() {
  testFeedbackMotionStylesCoverEnterAndExit();
  testNormalizeSelectedTypesKeepsCanonicalOrder();
  testBuildIssueTitleUsesStrictPrefixFormat();
  testBuildIssueBodyStaysMinimal();
  testValidateFeedbackFormRequiresTypeAndConfirmation();
  testBuildIssueDraftUrlTargetsFixedRepo();
  testResolveGithubTokenPrefersDecodedSecretPrivate();
  testClassifyIssueError();
  await testSubmitIssueUsesApiWhenTokenAvailable();
  await testSubmitIssueFallsBackToDraftWhenNoToken();
  await testBlockedDraftDoesNotNavigateCurrentPage();
  await testSubmitIssueFallsBackGracefullyOnAuthFailure();
}

run().then(() => {
  console.log('test_feedback_issue.js passed');
}).catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
