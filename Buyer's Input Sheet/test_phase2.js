// Checks otb-plan-app.html's _phase2Edit (Phase 2, 5 Oct 2026): a month edit keeps every department's Phase 1 block
// total and each month's division AOP; locked cells and the edited cell stay. Run: node test_phase2.js
const fs = require('fs'), assert = require('assert');
const html = fs.readFileSync(__dirname + '/otb-plan-app.html', 'utf8');
const src = html.slice(html.indexOf('/* Phase 2 edit'), html.indexOf('// Called on every individual cell commit'));
const AOP_MIS = [11, 0, 1, 2];
const LY = { a: [10, 12, 8, 6], b: [5, 5, 5, 5], c: [20, 18, 22, 15] };   // Cr per AOP month, in AOP_MIS order
const DVDATA = [{ id: 'mens', secs: Object.keys(LY).map(id => ({ id, nm: id.toUpperCase() })) }];
const S = { inputs: {}, locked: new Set(), hiddenSecs: new Set(), divLocked: new Set(), buyerSet: new Set(), aop: { mens: {} } };
const _secMonLY = (sec, dv, mi) => LY[sec.id][AOP_MIS.indexOf(mi)];
const document = { querySelector: () => null, activeElement: null };
const { _phase2Edit } = new Function('AOP_MIS', 'DVDATA', 'S', '_secMonLY', 'document', src + 'return {_phase2Edit};')(AOP_MIS, DVDATA, S, _secMonLY, document);

// Phase 1 state: every department +10% in every month, AOP = exactly that
for (const id in LY) AOP_MIS.forEach(mi => { S.inputs[id + '__' + mi] = 10; });
AOP_MIS.forEach((mi, j) => { S.aop.mens[mi] = Object.values(LY).reduce((a, l) => a + l[j] * 1.1, 0); });
const ty = (id, mi) => LY[id][AOP_MIS.indexOf(mi)] * (1 + S.inputs[id + '__' + mi] / 100);
const block = id => AOP_MIS.reduce((a, mi) => a + ty(id, mi), 0);
const before = Object.fromEntries(Object.keys(LY).map(id => [id, block(id)]));
S.locked.add('c__1');                                     // c's May is locked

const res = _phase2Edit('a', 11, 30);                     // a's Mar goes from +10% to +30%
assert.strictEqual(S.inputs.a__11, 30, 'edited cell stays');
assert.strictEqual(S.inputs.c__1, 10, 'locked cell stays');
assert.ok(!res.stuck, 'a has unlocked months left');
for (const id in LY) assert.ok(Math.abs(block(id) - before[id]) < 1e-6, `${id} block total kept`);
AOP_MIS.forEach(mi => assert.ok(Math.abs(Object.keys(LY).reduce((a, id) => a + ty(id, mi), 0) - S.aop.mens[mi]) < 1e-6, `AOP month ${mi} kept`));
assert.ok(S.inputs.a__0 < 10 && S.inputs.b__11 < 10, 'a gives up other months, others give up Mar');

// a with every other month locked can't keep its total - AOP wins and the page is told
[0, 1, 2].forEach(mi => S.locked.add('a__' + mi));
const r2 = _phase2Edit('a', 11, 50);
assert.ok(r2.stuck && r2.moved > 0, 'stuck reported');
AOP_MIS.forEach(mi => assert.ok(Math.abs(Object.keys(LY).reduce((a, id) => a + ty(id, mi), 0) - S.aop.mens[mi]) < 1e-6, `AOP month ${mi} still kept`));
// a whole group (the attribute pane) edited at once: a and b both set to +20% in Apr; c re-balances, block totals kept
[0, 1, 2].forEach(mi => S.locked.delete('a__' + mi));
const blk2 = Object.fromEntries(Object.keys(LY).map(id => [id, block(id)]));
const r3 = _phase2Edit(['a', 'b'], 0, 20);
assert.ok(S.inputs.a__0 === 20 && S.inputs.b__0 === 20, 'group cells set');
for (const id in LY) assert.ok(Math.abs(block(id) - blk2[id]) < 1e-6, `${id} block total kept (group edit)`);
AOP_MIS.forEach(mi => assert.ok(Math.abs(Object.keys(LY).reduce((a, id) => a + ty(id, mi), 0) - S.aop.mens[mi]) < 1e-6, `AOP month ${mi} kept (group edit)`));
assert.ok(!r3.stuck && r3.name === '2 departments');
console.log('phase 2 balancing checks passed');
