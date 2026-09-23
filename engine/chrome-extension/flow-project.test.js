const assert = require('node:assert/strict');
const test = require('node:test');

const { FlowProject } = require('./flow-project.js');

test('detectProjectIdFromUrl extracts 36-character UUID from standard and edit Flow URLs', () => {
  const rootUrl = 'https://flow.google.com/project/aaa1ca86-92ee-4436-b4d5-ace19f4481c9';
  assert.equal(FlowProject.detectProjectIdFromUrl(rootUrl), 'aaa1ca86-92ee-4436-b4d5-ace19f4481c9');

  const editUrl = 'https://flow.google.com/project/aaa1ca86-92ee-4436-b4d5-ace19f4481c9/edit/asset-123';
  assert.equal(FlowProject.detectProjectIdFromUrl(editUrl), 'aaa1ca86-92ee-4436-b4d5-ace19f4481c9');

  const legacyUrl = 'https://labs.google/fx/tools/flow/project/81aa0e61-0a4c-4fed-b089-d4e2e54e06f8';
  assert.equal(FlowProject.detectProjectIdFromUrl(legacyUrl), '81aa0e61-0a4c-4fed-b089-d4e2e54e06f8');

  const invalidUrl = 'https://flow.google.com/home';
  assert.equal(FlowProject.detectProjectIdFromUrl(invalidUrl), null);
});

test('extractActiveProjectId prioritizes active Flow tabs over inactive tabs', () => {
  const tabs = [
    { url: 'https://flow.google.com/project/11111111-1111-1111-1111-111111111111', active: false, lastAccessed: 100 },
    { url: 'https://flow.google.com/project/22222222-2222-2222-2222-222222222222', active: true, lastAccessed: 200 },
  ];
  assert.equal(FlowProject.extractActiveProjectId(tabs), '22222222-2222-2222-2222-222222222222');
});

test('isProjectComposerUrl correctly identifies project root versus subpaths', () => {
  const proj = 'aaa1ca86-92ee-4436-b4d5-ace19f4481c9';
  assert.equal(FlowProject.isProjectComposerUrl(`https://flow.google.com/project/${proj}`, proj), true);
  assert.equal(FlowProject.isProjectComposerUrl(`https://flow.google.com/project/${proj}/`, proj), true);
  assert.equal(FlowProject.isProjectComposerUrl(`https://flow.google.com/u/2/project/${proj}`, proj), true);
  assert.equal(FlowProject.isProjectComposerUrl(`https://flow.google.com/u/0/project/${proj}/`, proj), true);
  assert.equal(FlowProject.isProjectComposerUrl(`https://flow.google.com/project/${proj}/edit/123`, proj), false);
  assert.equal(FlowProject.isProjectComposerUrl(`https://flow.google.com/u/2/project/${proj}/edit/123`, proj), false);
  assert.equal(FlowProject.isProjectComposerUrl(`https://flow.google.com/u/2/project/${proj}/character`, proj), false);
  assert.equal(FlowProject.isProjectComposerUrl(`https://other.google.com/project/${proj}`, proj), false);
});

test('isProjectRootUrl validates strict project root without subpaths', () => {
  const proj = 'aaa1ca86-92ee-4436-b4d5-ace19f4481c9';
  assert.equal(FlowProject.isProjectRootUrl(`https://flow.google.com/project/${proj}`), true);
  assert.equal(FlowProject.isProjectRootUrl(`https://flow.google.com/u/2/project/${proj}`), true);
  assert.equal(FlowProject.isProjectRootUrl(`https://flow.google.com/u/2/project/${proj}/`), true);
  assert.equal(FlowProject.isProjectRootUrl(`https://flow.google.com/u/2/project/${proj}/character`), false);
  assert.equal(FlowProject.isProjectRootUrl(`https://flow.google.com/u/2/project/${proj}/actors`), false);
  assert.equal(FlowProject.isProjectRootUrl(`https://flow.google.com/u/2/project/${proj}/edit/123`), false);
  assert.equal(FlowProject.isProjectRootUrl(`https://flow.google.com/home`), false);
});

test('normalizeToProjectRootUrl strips subpaths like /character and /edit back to root composer', () => {
  const proj = 'cc8d713a-967f-4cec-bdea-7148d64c8821';
  assert.equal(
    FlowProject.normalizeToProjectRootUrl(`https://flow.google.com/u/2/project/${proj}/character`),
    `https://flow.google.com/u/2/project/${proj}`
  );
  assert.equal(
    FlowProject.normalizeToProjectRootUrl(`https://flow.google.com/project/${proj}/edit/abc-123`),
    `https://flow.google.com/project/${proj}`
  );
  assert.equal(
    FlowProject.normalizeToProjectRootUrl(`https://flow.google.com/u/3/project/${proj}`),
    `https://flow.google.com/u/3/project/${proj}`
  );
});

test('buildProjectUrl formats the full Flow project URL and preserves user prefix', () => {
  const proj = 'aaa1ca86-92ee-4436-b4d5-ace19f4481c9';
  assert.equal(FlowProject.buildProjectUrl(proj), `https://flow.google.com/project/${proj}`);
  assert.equal(FlowProject.buildProjectUrl(proj, '/u/3'), `https://flow.google.com/u/3/project/${proj}`);
  assert.equal(FlowProject.buildProjectUrl(proj, 'https://flow.google.com/u/3/project/other-123'), `https://flow.google.com/u/3/project/${proj}`);
  assert.equal(FlowProject.extractUserPrefix('https://flow.google.com/u/3/project/aaa1ca86-92ee-4436-b4d5-ace19f4481c9'), '/u/3');
  assert.equal(FlowProject.extractUserPrefix('https://flow.google.com/project/aaa1ca86-92ee-4436-b4d5-ace19f4481c9'), '');
});
