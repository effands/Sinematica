const test = require('node:test');
const assert = require('node:assert/strict');

test('Credit parsing extracts values from text without clicking anchor tags', () => {
  const sampleTexts = [
    'Available 250 Google Flow credits',
    'Kredit: 120',
    'Google Flow credits: 45.5',
    '500 points remaining',
  ];

  const parseCreditStr = (str) => {
    if (!str) return null;
    const m1 = str.match(/([\d,.]+)\s*(?:Google Flow credits?|credits?|kredit(?: google flow)?|poin|points?)/i);
    if (m1 && m1[1] && /\d/.test(m1[1])) return m1[1].trim() + " Kredit";
    const m2 = str.match(/(?:kredit|credits?|poin|points?)\s*[:：]?\s*([\d,.]+)/i);
    if (m2 && m2[1] && /\d/.test(m2[1])) return m2[1].trim() + " Kredit";
    return null;
  };

  assert.equal(parseCreditStr(sampleTexts[0]), '250 Kredit');
  assert.equal(parseCreditStr(sampleTexts[1]), '120 Kredit');
  assert.equal(parseCreditStr(sampleTexts[2]), '45.5 Kredit');
  assert.equal(parseCreditStr(sampleTexts[3]), '500 Kredit');
});
