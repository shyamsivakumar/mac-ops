'use strict';

const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const { provenRecoveryCommand } = require('./scripts/srw_deploy.cjs');

const source = fs.readFileSync(path.join(__dirname, 'scripts/srw_deploy.cjs'), 'utf8');
assert.strictEqual(provenRecoveryCommand([]), true);
assert.strictEqual(provenRecoveryCommand(['scripts/docker_start.sh']), true);
assert.strictEqual(provenRecoveryCommand(['/app/scripts/docker_start.sh']), false);
assert.strictEqual(provenRecoveryCommand(['scripts/docker_start.sh', '--extra']), false);
assert.strictEqual(provenRecoveryCommand(['node']), false);
assert.match(source, /\$\{provenRecoveryCommand\.toString\(\)\}/);
assert.match(source, /if \(!provenRecoveryCommand\(process\.argv\.slice\(2\)\)\) throw new Error\('recovery_start_command_unproven'\)/);
assert.ok(source.includes('ENTRYPOINT ["node","/usr/local/lib/srw-recovery.cjs"]\\nCMD ["scripts/docker_start.sh"]'));
console.log('srw228 recovery guard checks passed');
