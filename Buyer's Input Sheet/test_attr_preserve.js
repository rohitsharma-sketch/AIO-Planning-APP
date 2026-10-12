// Checks otb-plan-app.html (user, 2026-10-12: "preserve the buyer's input and accomodate the attribute changes"):
// the re-balance holds buyer-entered departments while plain-share ones can absorb it, falls back to moving everyone
// with their mix kept (and says so), an attribute edit keeps its departments' mix, and Phase 2 holds buyer months.
// Run: node test_attr_preserve.js
const fs = require('fs'), assert = require('assert');
const html = fs.readFileSync(__dirname + '/otb-plan-app.html', 'utf8');
const cut = (a, b) => html.slice(html.indexOf(a), html.indexOf(b));
const src = cut('const _attrMode=', 'function setAttrBlockGrowth') + cut('function _divReapp(', '/* Attribute Summary = ')
  + cut('/* Phase 2 edit', '// Called on every individual cell commit');
const AOP_MIS = [11, 0, 1, 2], MO = ['Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar'];
const LY = { a: [10, 10, 10, 10], b: [10, 10, 10, 10], c: [20, 20, 20, 20] };
const DV = { id: 'mens', nm: 'MENS', secs: Object.keys(LY).map(id => ({ id, nm: id.toUpperCase(), attr: id === 'c' ? 'X' : 'Y' })) };
const S = { inputs: {}, locked: new Set(), hiddenSecs: new Set(), divLocked: new Set(), buyerSet: new Set(), aop: { mens: {} } };
const _secMonLY = (sec, dv, mi) => LY[sec.id][AOP_MIS.indexOf(mi)];
const toasts = [], document = { querySelector: () => null, activeElement: null };
const localStorage = { getItem: () => null, setItem: () => {} };
const f = new Function('AOP_MIS', 'MO', 'DVDATA', 'S', '_secMonLY', 'document', 'localStorage', 'toast', 'refresh', 'setTimeout',
  src + 'return {_divReapp,_attrScale,_phase2Edit};');   // setTimeout runs at once here: one toast per edit call
const { _divReapp, _attrScale, _phase2Edit } = f(AOP_MIS, MO, [DV], S, _secMonLY, document, localStorage, m => toasts.push(m), () => {}, fn => fn());
const ty = (id, mi) => LY[id][AOP_MIS.indexOf(mi)] * (1 + (S.inputs[id + '__' + mi] ?? 0) / 100);
const tot = mi => Object.keys(LY).reduce((x, id) => x + ty(id, mi), 0);
const reset = () => { S.inputs = {}; S.locked = new Set(); S.buyerSet = new Set(); toasts.length = 0;
  AOP_MIS.forEach(mi => { S.aop.mens[mi] = 44; for (const id in LY) S.inputs[id + '__' + mi] = 10; }); };

// 1. b was typed by the buyer (+30%); a is edited to +20%: c (plain share) absorbs, b holds, AOP kept
reset();
AOP_MIS.forEach(mi => { S.inputs['b__' + mi] = 30; }); S.buyerSet.add('b');
AOP_MIS.forEach(mi => { S.inputs['a__' + mi] = 20; _divReapp(DV, mi, 'a'); });
AOP_MIS.forEach(mi => assert.ok(Math.abs(tot(mi) - 44) < 1e-9, 'AOP kept'));
assert.strictEqual(S.inputs.b__11, 30, 'buyer-entered b holds');
assert.ok(Math.abs(S.inputs.c__11 - ((44 - 12 - 13) / 20 - 1) * 100) < 1e-9, 'plain-share c absorbs');
assert.strictEqual(toasts.length, 0, 'no warning when the plain share could absorb it');

// 2. not enough room (a +250%): everything unlocked moves together, b keeps its gap to c, and the page is told
reset();
AOP_MIS.forEach(mi => { S.inputs['b__' + mi] = 30; }); S.buyerSet.add('b');
AOP_MIS.forEach(mi => { S.inputs['a__' + mi] = 250; _divReapp(DV, mi, 'a'); });
AOP_MIS.forEach(mi => assert.ok(Math.abs(tot(mi) - 44) < 1e-9, 'AOP kept in the fallback'));
assert.ok(Math.abs(ty('b', 11) / ty('c', 11) - 13 / 22) < 1e-9, 'b and c scaled together (mix kept)');
assert.ok(toasts.length === AOP_MIS.length && toasts.every(t => /B \(/.test(t)), 'buyer-entered move reported (once per edit call)');

// 3. keep the mix: attribute Y (a +15%, b +5%) set to +12% -> both scale by one factor, the gap kept
reset();
AOP_MIS.forEach(mi => { S.inputs['a__' + mi] = 15; S.inputs['b__' + mi] = 5; });
const sc = _attrScale(DV, DV.secs.filter(s => s.attr === 'Y'), AOP_MIS, 12);
sc.forEach(c => { S.inputs[c.k] = c.g; });
const ga = S.inputs.a__11, gb = S.inputs.b__11;
assert.ok(Math.abs((ty('a', 11) + ty('b', 11)) / 20 - 1.12) < 1e-9, 'attribute lands on +12%');
assert.ok(Math.abs((1 + ga / 100) / (1 + gb / 100) - 1.15 / 1.05) < 1e-9 && ga > gb, 'a stays ahead of b by the same ratio');

// 4. Phase 2: c is buyer-entered; a's Mar edit is absorbed by b (plain), c's months hold
reset();
S.buyerSet.add('c');
const before = Object.fromEntries(Object.keys(LY).map(id => [id, AOP_MIS.reduce((x, mi) => x + ty(id, mi), 0)]));
_phase2Edit('a', 11, 30);
AOP_MIS.forEach(mi => assert.ok(Math.abs(S.inputs['c__' + mi] - 10) < 1e-9, 'buyer-entered c holds its months'));
AOP_MIS.forEach(mi => assert.ok(Math.abs(tot(mi) - 44) < 1e-6, 'AOP month kept'));
for (const id in LY) assert.ok(Math.abs(AOP_MIS.reduce((x, mi) => x + ty(id, mi), 0) - before[id]) < 1e-6, id + ' block total kept');
console.log('attribute / buyer-input preservation checks passed');
