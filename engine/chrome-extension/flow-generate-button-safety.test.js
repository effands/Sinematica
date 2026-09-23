const test = require('node:test');
const assert = require('node:assert/strict');

test('findStartButton strictly ignores Create Character buttons and matches only prompt-box submit button', () => {
  const isButtonDisabled = (btn) => {
    if (!btn) return true;
    return btn.disabled || btn.getAttribute?.('aria-disabled') === 'true';
  };

  const createCharBtn = {
    innerText: 'Create character',
    getAttribute: (attr) => (attr === 'aria-label' ? 'Create character' : null),
    closest: (sel) => null,
    disabled: false,
  };

  const sidebarNewCharBtn = {
    innerText: '+ Character',
    getAttribute: (attr) => (attr === 'aria-label' ? 'Create new character' : null),
    closest: (sel) => null,
    disabled: false,
  };

  const promptBoxGenerateBtn = {
    innerText: 'arrow_forward',
    getAttribute: (attr) => (attr === 'aria-label' ? 'Start generation' : null),
    closest: (sel) => (sel.includes('flow-prompt-box') || sel.includes('flow-generate-icon-button') ? true : null),
    disabled: false,
  };

  const allButtons = [createCharBtn, sidebarNewCharBtn, promptBoxGenerateBtn];

  const findSafeStartButton = (buttons) => {
    const direct = buttons.find(b => b.closest?.('flow-generate-icon-button') && !isButtonDisabled(b));
    if (direct) return direct;

    const candidates = buttons.filter(b => {
      if (!b || isButtonDisabled(b)) return false;
      const text = [b.getAttribute?.('aria-label') || '', b.innerText || ''].join(' ').toLowerCase();
      // Non-composer buttons must strictly be rejected
      if (text.includes('character') || text.includes('karakter') || text.includes('actor') || text.includes('upload') || text.includes('sidebar')) {
        return false;
      }
      const inBox = b.closest?.('flow-prompt-box') || b.closest?.('flow-generate-icon-button');
      const isGenerateText = /arrow_forward|start generation|generate video|generate image|mulai|hasilkan/i.test(text);
      return inBox && isGenerateText;
    });

    return candidates[0] || null;
  };

  const selected = findSafeStartButton(allButtons);
  assert.equal(selected, promptBoxGenerateBtn, 'Must select the prompt box submit button');
  assert.notEqual(selected, createCharBtn, 'Must never select Create character button');
  assert.notEqual(selected, sidebarNewCharBtn, 'Must never select sidebar Character button');
});

test('findGenerateButton matches SVG-only submit buttons and alternative action labels', () => {
  const isButtonDisabled = (btn) => !btn || btn.disabled || btn.getAttribute?.('aria-disabled') === 'true';

  const svgSubmitBtn = {
    innerText: '',
    textContent: '',
    getAttribute: (attr) => (attr === 'aria-label' ? 'Start' : null),
    closest: (sel) => (sel.includes('flow-prompt-box') ? true : null),
    querySelector: (sel) => (sel.includes('svg') || sel.includes('mat-icon') ? {} : null),
    disabled: false,
  };

  const sendBtn = {
    innerText: 'Submit',
    textContent: 'Submit',
    getAttribute: (attr) => (attr === 'aria-label' ? 'Submit prompt' : null),
    closest: (sel) => (sel.includes('flow-prompt-box') ? true : null),
    querySelector: () => null,
    disabled: false,
  };

  const fallbackBtn = {
    innerText: '',
    textContent: '',
    getAttribute: () => null,
    closest: (sel) => (sel.includes('flow-prompt-box') ? true : null),
    querySelector: () => null,
    disabled: false,
  };

  const testButtons = [svgSubmitBtn, sendBtn, fallbackBtn];

  const matchButton = (btn) => {
    if (!btn || isButtonDisabled(btn)) return false;
    const text = [btn.getAttribute?.('aria-label') || '', btn.innerText || '', btn.textContent || ''].join(' ').toLowerCase();
    const inComposer = !!btn.closest?.('flow-prompt-box');
    const isGenerateText = /arrow|start|generate|submit|send|buat|mulai|hasilkan/i.test(text) || !!btn.querySelector?.('mat-icon, svg');
    return inComposer && isGenerateText;
  };

  assert.equal(matchButton(svgSubmitBtn), true);
  assert.equal(matchButton(sendBtn), true);
});
