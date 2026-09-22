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
  assert.equal(FlowProject.isProjectComposerUrl(`https://other.google.com/project/${proj}`, proj), false);
});

test('buildProjectUrl formats the full Flow project URL', () => {
  const proj = 'aaa1ca86-92ee-4436-b4d5-ace19f4481c9';
  assert.equal(FlowProject.buildProjectUrl(proj), `https://flow.google.com/project/${proj}`);
});
