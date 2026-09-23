const test = require('node:test');
const assert = require('node:assert/strict');

test('extractToken handles full CDN URLs, project media paths, and raw UUIDs', () => {
  const extractToken = (val) => {
    if (!val) return '';
    const str = String(val);
    const uuid = str.match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i);
    if (uuid) return uuid[1].toLowerCase();
    const asb = str.match(/AB-n[A-Za-z0-9_-]{12,}/);
    if (asb) return asb[0];
    return str.toLowerCase();
  };

  assert.equal(extractToken('https://flow-content.google/image/59e62d13-222c-425a-8cdd-a0ccf9a2a0a5?Expires=123'), '59e62d13-222c-425a-8cdd-a0ccf9a2a0a5');
  assert.equal(extractToken('projects/proj-123/media/3cf4d439-84d9-4e0a-8320-84ba7886d5c3'), '3cf4d439-84d9-4e0a-8320-84ba7886d5c3');
  assert.equal(extractToken('59e62d13-222c-425a-8cdd-a0ccf9a2a0a5'), '59e62d13-222c-425a-8cdd-a0ccf9a2a0a5');
});

test('item matcher checks img.src, item title text, and attributes', () => {
  const item1 = {
    innerText: 'Two people leaping into canal\nImage',
    outerHTML: '<button class="asset-item"><img src="https://flow-content.google/image/59e62d13-222c-425a-8cdd-a0ccf9a2a0a5?Expires=123"></button>',
    querySelector: (sel) => sel === 'img' ? { src: 'https://flow-content.google/image/59e62d13-222c-425a-8cdd-a0ccf9a2a0a5?Expires=123' } : null,
    getAttribute: () => null
  };

  const item2 = {
    innerText: 'Character contact sheet design\nImage',
    outerHTML: '<button class="asset-item"><img src="https://flow-content.google/image/3cf4d439-84d9-4e0a-8320-84ba7886d5c3?Expires=123"></button>',
    querySelector: (sel) => sel === 'img' ? { src: 'https://flow-content.google/image/3cf4d439-84d9-4e0a-8320-84ba7886d5c3?Expires=123' } : null,
    getAttribute: () => null
  };

  const items = [item1, item2];
  const targetToken = '59e62d13-222c-425a-8cdd-a0ccf9a2a0a5';

  const matched = items.find(item => {
    const img = item.querySelector('img');
    const imgSrc = (img?.src || img?.currentSrc || '').toLowerCase();
    const text = (item.innerText || item.textContent || '').toLowerCase();
    const html = (item.outerHTML || '').toLowerCase();
    return imgSrc.includes(targetToken) || text.includes(targetToken) || html.includes(targetToken);
  });

  assert.equal(matched, item1);
});
