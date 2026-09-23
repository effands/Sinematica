const test = require('node:test');
const assert = require('node:assert/strict');

test('Multi-lingual label finder matches English, Indonesian, and icon-prefixed tokens', () => {
  const normalize = (value) => (value || '').toLowerCase().trim();
  
  const matchToggle = (elementText, needle) => {
    const normText = normalize(elementText);
    const normNeedle = normalize(needle);
    const parts = normText.split(/[\s\n\r_-]+/);
    
    // Direct or part match
    if (parts.includes(normNeedle) || normText === normNeedle) return true;
    
    // Multi-lingual synonyms
    if (normNeedle === 'video') return parts.includes('video') || normText.includes('videocam');
    if (normNeedle === 'image') return parts.includes('image') || parts.includes('gambar') || normText.includes('image');
    if (normNeedle === 'ingredients') return parts.includes('ingredients') || parts.includes('bahan') || parts.includes('ingredient');
    if (normNeedle === 'frames') return parts.includes('frames') || parts.includes('frame') || parts.includes('bingkai');
    if (/^\d+s$/.test(normNeedle)) {
      const secNum = normNeedle.replace('s', '');
      return parts.includes(normNeedle) || parts.includes(`${secNum}s`) || parts.includes(`${secNum}dtk`) || parts.includes(secNum) || normText.includes(`${secNum} dtk`);
    }
    if (normNeedle === '16:9') return normText.includes('16:9') || parts.includes('16:9');
    if (normNeedle === '9:16') return normText.includes('9:16') || parts.includes('9:16');
    if (normNeedle === 'x1') return normText.includes('x1') || parts.includes('x1') || parts.includes('1');
    return false;
  };

  // English tests
  assert.equal(matchToggle('videocam\nVideo', 'video'), true);
  assert.equal(matchToggle('image\nImage', 'image'), true);
  assert.equal(matchToggle('chrome_extension\nIngredients', 'ingredients'), true);
  assert.equal(matchToggle('8s', '8s'), true);

  // Indonesian tests
  assert.equal(matchToggle('image\nGambar', 'image'), true);
  assert.equal(matchToggle('chrome_extension\nBahan', 'ingredients'), true);
  assert.equal(matchToggle('crop_free\nFrame', 'frames'), true);
  assert.equal(matchToggle('4 dtk', '4s'), true);
  assert.equal(matchToggle('6 dtk', '6s'), true);
  assert.equal(matchToggle('8 dtk', '8s'), true);
  assert.equal(matchToggle('10 dtk', '10s'), true);
  assert.equal(matchToggle('crop_16_9\n16:9', '16:9'), true);
  assert.equal(matchToggle('crop_9_16\n9:16', '9:16'), true);
  assert.equal(matchToggle('x1', 'x1'), true);
});
