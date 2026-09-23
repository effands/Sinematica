const test = require('node:test');
const assert = require('node:assert/strict');
const { FlowTaskExecutor } = require('./flow-executor.js');

test('ensureProject does not click home button or new-project button when already in a project URL', async () => {
  let homeClicked = false;
  let newProjectClicked = false;

  const fakeDocument = {
    querySelector: (sel) => {
      if (sel === '.ProseMirror') return {};
      if (sel.includes('home') || sel.includes('flow-logo')) {
        return {
          click: () => { homeClicked = true; },
          closest: () => null,
          getBoundingClientRect: () => ({ left: 0, top: 0, width: 10, height: 10 })
        };
      }
      if (sel.includes('new-project')) {
        return {
          click: () => { newProjectClicked = true; },
          closest: () => null,
          getBoundingClientRect: () => ({ left: 0, top: 0, width: 10, height: 10 })
        };
      }
      return null;
    },
    querySelectorAll: () => [],
  };

  const origWindow = globalThis.window;
  const origDoc = globalThis.document;

  globalThis.window = {
    location: { href: 'https://flow.google.com/project/aaa1ca86-92ee-4436-b4d5-ace19f4481c9' }
  };
  globalThis.document = fakeDocument;

  try {
    const executor = new FlowTaskExecutor({});
    const res = await executor.ensureProject();
    assert.equal(res, true);
    assert.equal(homeClicked, false, 'ensureProject must NEVER click home button when in a project');
    assert.equal(newProjectClicked, false, 'ensureProject must NEVER click new-project button when in a project');
  } finally {
    globalThis.window = origWindow;
    globalThis.document = origDoc;
  }
});

test('ensureProject redirects from /character subpath back to root project composer', async () => {
  let currentHref = 'https://flow.google.com/u/2/project/fc52263d-bdba-4979-92a6-60aa6b63a8e3/character';
  let redirectedUrl = '';

  const fakeDocument = {
    querySelector: (sel) => (sel === '.ProseMirror' ? {} : null),
    querySelectorAll: () => [],
  };

  const origWindow = globalThis.window;
  const origDoc = globalThis.document;

  globalThis.window = {
    location: {
      get href() { return currentHref; },
      set href(val) { currentHref = val; redirectedUrl = val; }
    }
  };
  globalThis.document = fakeDocument;

  try {
    const executor = new FlowTaskExecutor({});
    await executor.ensureProject();
    assert.equal(redirectedUrl, 'https://flow.google.com/u/2/project/fc52263d-bdba-4979-92a6-60aa6b63a8e3');
  } finally {
    globalThis.window = origWindow;
    globalThis.document = origDoc;
  }
});
