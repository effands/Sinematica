const { describe, it } = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

describe('Manifest V3 Declarations', () => {
  it('should include debugger, storage, scripting permissions and MAIN world content scripts', () => {
    const manifestPath = path.join(__dirname, 'manifest.json');
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));

    assert.ok(manifest.permissions.includes('debugger'), 'manifest should include debugger permission');
    assert.ok(manifest.permissions.includes('scripting'), 'manifest should include scripting permission');
    assert.ok(manifest.permissions.includes('storage'), 'manifest should include storage permission');
    assert.ok(manifest.permissions.includes('sidePanel'), 'manifest should include sidePanel permission');

    const mainWorldScript = manifest.content_scripts.find((cs) => cs.world === 'MAIN');
    assert.ok(mainWorldScript, 'manifest should have content_scripts with world MAIN');
    assert.ok(mainWorldScript.js.includes('flow-network-parser.js'), 'MAIN world should include flow-network-parser.js');
    assert.ok(mainWorldScript.js.includes('flow-interceptor.js'), 'MAIN world should include flow-interceptor.js');

    const isolatedScript = manifest.content_scripts.find((cs) => !cs.world || cs.world === 'ISOLATED');
    assert.ok(isolatedScript, 'manifest should have content_scripts for isolated world');
    assert.ok(isolatedScript.js.includes('flow-executor.js'), 'isolated world should include flow-executor.js');
    assert.ok(isolatedScript.js.includes('content.js'), 'isolated world should include content.js');

    const war = manifest.web_accessible_resources[0];
    assert.ok(war, 'web_accessible_resources should be declared');
    assert.ok(war.resources.includes('flow-network-parser.js'));
    assert.ok(war.resources.includes('flow-interceptor.js'));
    assert.ok(war.resources.includes('flow-executor.js'));
  });
});
