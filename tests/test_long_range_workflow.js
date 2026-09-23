const assert = require('node:assert/strict');
global.window = {};
require('../app/workflows.runner.js');
const build = window.DPRWorkflowRunner.__test.buildQuickFetchRequest;
for (const days of [90, 365]) {
  const result = build(days, {dispatchInputs: {profile_tag: 'ATSP,SR', fetch_days: '999'}});
  assert.equal(result.key, 'daily-now');
  assert.equal(result.inputs.fetch_days, String(days));
  assert.equal(result.inputs.fetch_mode, 'skims');
  assert.equal(result.inputs.profile_tag, 'ATSP,SR');
}
assert.equal(build(30, {fetchMode: 'standard'}).inputs.fetch_mode, 'standard');
for (const bad of [0, -1, 366, '365x', 90.5, Infinity]) assert.throws(() => build(bad));
console.log('long-range workflow tests passed');
