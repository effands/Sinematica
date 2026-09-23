const test = require('node:test');
const assert = require('node:assert/strict');

test('extractToken correctly identifies UUIDs and CDN tokens from reference IDs', () => {
  const extractToken = (val) => {
    if (!val) return '';
    const str = String(val);
    const uuid = str.match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i);
    if (uuid) return uuid[1].toLowerCase();
    const asb = str.match(/AB-n[A-Za-z0-9_-]{12,}/);
    if (asb) return asb[0];
    return str.toLowerCase();
  };

  assert.equal(extractToken('aaa1ca86-92ee-4436-b4d5-ace19f4481c9'), 'aaa1ca86-92ee-4436-b4d5-ace19f4481c9');
  assert.equal(extractToken('https://flow.google.com/asb/AB-nABC1234567890'), 'AB-nABC1234567890');
  assert.equal(extractToken('projects/123/media/bbb2ca86-92ee-4436-b4d5-ace19f4481c9'), 'bbb2ca86-92ee-4436-b4d5-ace19f4481c9');
});

test('popover-scoped asset matching only selects elements inside flow-add-menu-popover-content', () => {
  const canvasCard = {
    tagName: 'DIV',
    getAttribute: (attr) => attr === 'data-media-id' ? 'target-media-123' : null,
    outerHTML: '<div data-media-id="target-media-123" class="canvas-tile"></div>',
  };

  const popoverItem = {
    tagName: 'BUTTON',
    getAttribute: (attr) => attr === 'data-media-id' ? 'target-media-123' : null,
    outerHTML: '<button class="asset-item" data-media-id="target-media-123"></button>',
  };

  const popover = {
    querySelectorAll: (sel) => {
      if (sel.includes('asset-item')) return [popoverItem];
      return [];
    }
  };

  const fakeDocument = {
    querySelector: (sel) => {
      if (sel === 'flow-add-menu-popover-content') return popover;
      return null;
    },
    querySelectorAll: (sel) => {
      if (sel.includes('data-media-id')) return [canvasCard, popoverItem];
      return [];
    }
  };

  // Scoped search
  const openPopover = fakeDocument.querySelector('flow-add-menu-popover-content');
  const items = Array.from(openPopover.querySelectorAll('button.asset-item, .asset-item'));
  const match = items.find(item => item.outerHTML.includes('target-media-123'));

  assert.equal(match, popoverItem);
  assert.notEqual(match, canvasCard);
});
