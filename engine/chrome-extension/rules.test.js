const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

test('all AI Sandbox requests use the API-key-approved legacy referrer', () => {
  const rules = JSON.parse(
    fs.readFileSync(path.join(__dirname, 'rules.json'), 'utf8'),
  );

  assert.equal(rules.length, 1);
  assert.equal(rules[0].condition.initiatorDomains, undefined);

  for (const rule of rules) {
    const headers = Object.fromEntries(
      rule.action.requestHeaders.map(item => [item.header, item.value]),
    );
    assert.equal(headers.Referer, 'https://labs.google/');
    assert.equal(headers.Origin, 'https://labs.google');
  }
});
