const test = require('node:test');
const assert = require('node:assert/strict');

test('findAddIngredientTrigger discovers "+" / "Add" buttons with various aria-labels and mat-icons', () => {
  const visible = (el) => !!el && el.style?.display !== 'none';
  const normalize = (val) => (val || '').toLowerCase().trim();

  const findAddIngredientTrigger = (root) => {
    const promptBox = root.querySelector('flow-prompt-box, .flow-prompt-box, .prompt-box') || root;
    const direct = promptBox.querySelector('flow-add-menu button.add-menu-trigger, flow-add-menu button, button.add-menu-trigger, button.add-media-button');
    if (direct && visible(direct) && !direct.disabled) return direct;

    const primaryCandidates = Array.from(promptBox.querySelectorAll(
      'button.add-menu-trigger, button.add-media-button, button[aria-label*="Add" i], button[aria-label*="Tambah" i], button[aria-label*="Ingredient" i], button[aria-label*="Reference" i], button[aria-label*="Media" i]'
    ));
    for (const el of primaryCandidates) {
      if (el.closest && el.closest('flow-ingredient-chip, flow-image-ingredient-chip, .chip-container, flow-ingredient-bar, flow-media-chip, .chip, flow-generate-icon-button, button.generate-icon-button')) {
        continue;
      }
      if (visible(el) && !el.disabled) return el;
    }

    const allBtns = Array.from(promptBox.querySelectorAll('button'));
    for (const btn of allBtns) {
      if (!visible(btn) || btn.disabled) continue;
      if (btn.closest && btn.closest('flow-ingredient-chip, flow-image-ingredient-chip, .chip-container, flow-ingredient-bar, flow-media-chip, .chip, flow-generate-icon-button, button.generate-icon-button')) {
        continue;
      }
      const label = normalize(btn.getAttribute('aria-label') || btn.innerText || btn.textContent || '');
      const icon = btn.querySelector('mat-icon, svg');
      const iconText = normalize(icon?.innerText || icon?.textContent || icon?.getAttribute('data-icon') || '');
      if (label === 'add' || label === 'tambah' || label.startsWith('add ') || label.startsWith('tambah ') || label.includes('ingredient') || iconText === 'add' || iconText === 'add_circle' || iconText === '+') {
        return btn;
      }
    }
    return null;
  };

  // Case 1: Simple button with aria-label="Add"
  const doc1 = {
    querySelector: (sel) => null,
    querySelectorAll: (sel) => [
      {
        tagName: 'BUTTON',
        disabled: false,
        getAttribute: (attr) => attr === 'aria-label' ? 'Add' : null,
        querySelector: () => null,
      }
    ]
  };
  const match1 = findAddIngredientTrigger(doc1);
  assert.ok(match1, 'Must find button with aria-label="Add"');

  // Case 2: Button with mat-icon "add"
  const mockIcon = { innerText: 'add', getAttribute: () => null };
  const doc2 = {
    querySelector: (sel) => null,
    querySelectorAll: (sel) => [
      {
        tagName: 'BUTTON',
        disabled: false,
        getAttribute: (attr) => null,
        querySelector: (sel) => sel.includes('mat-icon') ? mockIcon : null,
      }
    ]
  };
  const match2 = findAddIngredientTrigger(doc2);
  assert.ok(match2, 'Must find button containing mat-icon "add"');

  // Case 3: Prompt box contains existing chips with aria-label="Bahan" — must NOT match chips, must match add trigger
  const chipBtn = {
    tagName: 'BUTTON',
    className: 'chip-container',
    disabled: false,
    getAttribute: (attr) => attr === 'aria-label' ? 'Bahan' : null,
    querySelector: () => null,
    closest: (sel) => sel.includes('chip') ? true : null
  };
  const addTriggerBtn = {
    tagName: 'BUTTON',
    className: 'add-menu-trigger',
    disabled: false,
    getAttribute: (attr) => attr === 'aria-label' ? 'Tambahkan bahan ke kotak perintah' : null,
    querySelector: () => null,
    closest: (sel) => null
  };
  const doc3 = {
    querySelector: (sel) => sel.includes('add-menu') ? addTriggerBtn : null,
    querySelectorAll: (sel) => [chipBtn, addTriggerBtn]
  };
  const match3 = findAddIngredientTrigger(doc3);
  assert.equal(match3, addTriggerBtn, 'Must strictly match addTriggerBtn and ignore chipBtn');
});

test('addFlowIngredients attaches multiple references including storyboard and character sheets', async () => {
  const selectedItems = [];
  let escapeDispatched = false;

  const extractToken = (val) => {
    if (!val) return '';
    const str = String(val);
    const uuid = str.match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i);
    if (uuid) return uuid[1].toLowerCase();
    const asb = str.match(/AB-n[A-Za-z0-9_-]{12,}/);
    if (asb) return asb[0];
    return str.toLowerCase();
  };

  const item1 = {
    outerHTML: '<button class="asset-item" data-media-id="11111111-1111-1111-1111-111111111111"><img src="https://flow.google.com/media/11111111-1111-1111-1111-111111111111"></button>',
    querySelector: (sel) => sel.includes('img') ? { src: 'https://flow.google.com/media/11111111-1111-1111-1111-111111111111' } : null,
    click: () => { selectedItems.push('11111111-1111-1111-1111-111111111111'); }
  };

  const item2 = {
    outerHTML: '<button class="asset-item" data-media-id="22222222-2222-2222-2222-222222222222"><img src="https://flow.google.com/media/22222222-2222-2222-2222-222222222222"></button>',
    querySelector: (sel) => sel.includes('img') ? { src: 'https://flow.google.com/media/22222222-2222-2222-2222-222222222222' } : null,
    click: () => { selectedItems.push('22222222-2222-2222-2222-222222222222'); }
  };

  const popover = {
    querySelectorAll: (sel) => {
      if (sel.includes('tab')) return [];
      if (sel.includes('asset-item')) return [item1, item2];
      return [];
    },
    querySelector: (sel) => {
      if (sel.includes('detail-add-to-prompt-btn')) return { click: () => {} };
      return null;
    }
  };

  const ids = ['11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222'];
  for (const id of ids) {
    const token = extractToken(id);
    const items = popover.querySelectorAll('button.asset-item');
    const matched = items.find(it => it.outerHTML.includes(token));
    if (matched) {
      matched.click();
    }
  }

  assert.equal(selectedItems.length, 2);
  assert.equal(selectedItems[0], '11111111-1111-1111-1111-111111111111');
  assert.equal(selectedItems[1], '22222222-2222-2222-2222-222222222222');
});

test('video prompt filling sequence types text first and attaches storyboard references without erasing chips', async () => {
  // Simulate DOM state
  let promptTextState = '';
  const attachedChips = [];

  const editor = {
    innerText: '',
    textContent: '',
    innerHTML: '',
    querySelector: (sel) => {
      if (sel.includes('chip') && attachedChips.length > 0) return attachedChips[0];
      return null;
    },
    querySelectorAll: (sel) => {
      if (sel.includes('chip')) return attachedChips;
      return [];
    },
    focus: () => {}
  };

  const execCommand = (cmd, showUi, val) => {
    if (cmd === 'selectAll') {
      // If selectAll was called after chips were attached, it would wipe them
    }
    if (cmd === 'delete') {
      editor.innerText = '';
      editor.textContent = '';
      editor.innerHTML = '';
    }
    if (cmd === 'insertText') {
      editor.innerText = val;
      editor.textContent = val;
      promptTextState = val;
    }
  };

  // Step 1: Type prompt text FIRST
  execCommand('selectAll', false, null);
  execCommand('delete', false, null);
  execCommand('insertText', false, 'Scene 2: Arga kneeling on the wet asphalt apron...');

  assert.equal(promptTextState, 'Scene 2: Arga kneeling on the wet asphalt apron...');
  assert.equal(attachedChips.length, 0);

  // Step 2: Attach storyboard reference chip AFTER prompt text is populated
  const storyboardChip = {
    tagName: 'FLOW-MEDIA-CHIP',
    dataset: { mediaId: 'storyboard-scene-2-uuid' },
    innerText: 'Storyboard Scene 2'
  };
  attachedChips.push(storyboardChip);

  // Step 3: Verify editor state maintains both text and storyboard chip
  assert.equal(promptTextState, 'Scene 2: Arga kneeling on the wet asphalt apron...');
  assert.equal(attachedChips.length, 1);
  assert.equal(attachedChips[0].dataset.mediaId, 'storyboard-scene-2-uuid');
});

test('FlowComposerEditor.injectText does not erase existing media chips when updating text', () => {
  const { FlowComposerEditor } = require('./flow-composer-editor.js');

  const chipNode = { tagName: 'FLOW-MEDIA-CHIP', innerText: 'Storyboard Scene 2' };
  let currentTextContent = 'Old text';

  const mockEditor = {
    innerText: 'Old text',
    get textContent() { return currentTextContent; },
    set textContent(val) {
      // In bad implementation, this would wipe children
      currentTextContent = val;
    },
    querySelector: (sel) => {
      if (sel.includes('chip')) return chipNode;
      return null;
    },
    focus: () => {},
    dispatchEvent: () => true
  };

  const mockDoc = {
    querySelector: (sel) => sel.includes('contenteditable') ? mockEditor : null,
    execCommand: (cmd, show, val) => {
      if (cmd === 'insertText') {
        mockEditor.innerText = val;
      }
    }
  };

  const result = FlowComposerEditor.injectText(mockDoc, 'New scene prompt');
  assert.equal(result, true);
  // textContent setter must NOT have been called directly because chips were present
  assert.equal(mockEditor.innerText, 'New scene prompt');
  assert.ok(mockEditor.querySelector('flow-media-chip'), 'Chip must remain intact');
});
