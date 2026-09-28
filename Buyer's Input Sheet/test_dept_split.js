// Checks otb-plan-app.html's _migrateDeptIds (department split, 28 Sep 2026). Run: node test_dept_split.js
const fs = require('fs'), assert = require('assert');
const html = fs.readFileSync(__dirname + '/otb-plan-app.html', 'utf8');
const src = html.slice(html.indexOf('const DEPT_SPLITS='), html.indexOf('var _deptMigrated'));
const { _migrateDeptIds } = new Function(src + 'return {_migrateDeptIds};')();

const st = {
  inputs: { mse_pyjama__0: 10.5, l_in_bra__0: 7, other__0: 3 },
  aopSeeds: { mse_pyjama__0: 10.5 },
  locked: new Set(['mse_pyjama__0', 'l_in_bra__1']),
  hiddenSecs: new Set(['kb_bermuda']),
  manualInactive: new Set(),
};
assert.strictEqual(_migrateDeptIds(st), true);
// A split department hands its growth, seed, lock and hide state to both parts and disappears.
assert.deepStrictEqual(st.inputs, { l_in_bra__0: 7, other__0: 3, mse_hsr_pyjama__0: 10.5, mse_txtl_pyjama__0: 10.5, l_in_sprt_bra__0: 7 });
assert.deepStrictEqual(st.aopSeeds, { mse_hsr_pyjama__0: 10.5, mse_txtl_pyjama__0: 10.5 });
assert.deepStrictEqual([...st.locked].sort(), ['l_in_bra__1', 'l_in_sprt_bra__1', 'mse_hsr_pyjama__0', 'mse_txtl_pyjama__0']);
assert.deepStrictEqual([...st.hiddenSecs].sort(), ['kb_hsr_bermuda', 'kb_txtl_bermuda']);
// A second pass changes nothing.
assert.strictEqual(_migrateDeptIds(st), false);
console.log('dept split migration checks passed');
