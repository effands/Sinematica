/**
 * Sinematica Flow Agent — Composer Editor Automation
 * Automates text prompt entry into React contenteditable editor.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.FlowComposerEditor = factory().FlowComposerEditor;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const FlowComposerEditor = {
    getEditorElement(doc) {
      const d = doc || (typeof document !== 'undefined' ? document : null);
      return d ? d.querySelector('[contenteditable="true"]') : null;
    },

    getStartButton(doc) {
      const d = doc || (typeof document !== 'undefined' ? document : null);
      return d ? d.querySelector('button[aria-label="Start generation"]') : null;
    },

    injectText(doc, text = '') {
      const d = doc || (typeof document !== 'undefined' ? document : null);
      if (!d) return false;
      const editor = this.getEditorElement(d);
      if (!editor) return false;

      try {
        if (typeof editor.focus === 'function') editor.focus();
        if (typeof d.execCommand === 'function') {
          d.execCommand('selectAll', false);
          d.execCommand('insertText', false, text);
        }

        const current = (editor.innerText || editor.textContent || '').trim();
        if (current !== text.trim()) {
          editor.textContent = text;
          if (typeof InputEvent !== 'undefined' && typeof editor.dispatchEvent === 'function') {
            editor.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, inputType: 'insertText', data: text }));
            editor.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
          }
        }
        return true;
      } catch (_) {
        return false;
      }
    }
  };

  return { FlowComposerEditor };
});
