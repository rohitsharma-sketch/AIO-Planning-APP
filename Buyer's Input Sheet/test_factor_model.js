// Checks otb-plan-app.html's weighted factor model (factor builder, 7 Oct 2026): single driver = its slab multiplier,
// several = weighted geometric mean, missing data re-weighted, rules in card order, small-department damping, clamp.
// Run: node test_factor_model.js
const fs = require('fs'), assert = require('assert');
const html = fs.readFileSync(__dirname + '/otb-plan-app.html', 'utf8');
const src = html.slice(html.indexOf('const FM_DRIVERS='), html.indexOf('// end weighted factor model'));
const { _weightedFactor, _fmQuant, _fmCut, _contFactor } = new Function(src + 'return {_weightedFactor,_fmQuant,_fmCut,_contFactor};')();
const near = (a, b, m) => assert.ok(Math.abs(a - b) < 1e-9, `${m}: ${a} vs ${b}`);

const slabs = { st: [{ from: null, label: 'Low', mult: 0.9 }, { from: 0.1, label: 'High', mult: 1.1 }],
  growth: [{ from: null, label: 'Low', mult: 1.0 }, { from: 0.5, label: 'High', mult: 0.95 }],
  fill: [{ from: null, label: 'Low', mult: 1.05 }, { from: 0.7, label: 'Good', mult: 0.97 }] };
const model = (on, extra = {}) => ({ drivers: ['st', 'growth', 'fill'].map(k => ({ key: k, on: k in on, weight: on[k] || 0, slabs: slabs[k] })),
  rules: [], shrink_k: 0, clamp: [0.5, 2], ...extra });
const x = { st: 0.103, gr: 0.174, fill: 0.857 };   // M_IN_BRIEF: High / Low / Good

// one driver alone = its slab's multiplier
near(_weightedFactor(x, model({ st: 100 }), 1).f, 1.1, 'single driver');
// weights 50/30/20 -> 1.10^0.5 x 1.00^0.3 x 0.97^0.2
near(_weightedFactor(x, model({ st: 50, growth: 30, fill: 20 }), 1).f, Math.pow(1.1, 0.5) * Math.pow(0.97, 0.2), 'weighted geometric mean');
// only the ratio of weights counts
near(_weightedFactor(x, model({ st: 5, growth: 3, fill: 2 }), 1).f, _weightedFactor(x, model({ st: 50, growth: 30, fill: 20 }), 1).f, 'weights relative');
// a driver with no data is left out, the rest re-weighted
near(_weightedFactor({ st: 0.103, gr: 0.174, fill: null }, model({ st: 50, growth: 50, fill: 50 }), 1).f, Math.pow(1.1, 0.5), 'missing re-weighted');
assert.ok(_weightedFactor({ st: null, gr: null, fill: null }, model({ st: 1 }), 1).none, 'no data -> neutral');
// rules: a floor for low fill; the first driver's rule wins a conflict
const low = { st: 0.02, gr: 0.6, fill: 0.4 };       // Low ST, High growth, Low fill
const m1 = model({ st: 50, growth: 50 }, { rules: [{ driver: 'fill', op: 'below', value: 0.5, kind: 'min', f: 0.97 }] });
near(_weightedFactor(low, m1, 1).f, 0.97, 'floor applied');
const m2 = model({ st: 50, growth: 50 }, { rules: [{ driver: 'growth', op: 'atleast', value: 0.5, kind: 'max', f: 0.9 },
  { driver: 'fill', op: 'below', value: 0.5, kind: 'min', f: 0.97 }] });
m2.drivers = [m2.drivers[1], m2.drivers[0], m2.drivers[2]];   // growth has priority
near(_weightedFactor(low, m2, 1).f, Math.min(Math.sqrt(0.9 * 0.95), 0.9), 'higher-priority cap kept, later floor skipped');
// small departments damped toward 1.00 (half strength at LY = k), then the clamp
near(_weightedFactor(x, model({ st: 100 }, { shrink_k: 0.2 }), 0.2).f, 1.05, 'damping halves the effect');
near(_weightedFactor(x, model({ st: 100 }, { clamp: [0.8, 1.05] }), 1).f, 1.05, 'clamp');
// percentile slabs: starts come from the division's own values (linear between ranks)
near(_fmQuant([0.02, 0.06, 0.1, 0.14, 0.3], 50), 0.1, 'median');
near(_fmQuant([0.02, 0.06, 0.1, 0.14, 0.3], 25), 0.06, 'P25');
near(_fmQuant([0.1, 0.2], 50), 0.15, 'between two');
const pm = model({ st: 100 });
pm.drivers[0] = { ...pm.drivers[0], by: 'pct', slabs: [{ from: null, label: 'Low', mult: 0.9 }, { pct: 50, label: 'Top half', mult: 1.1 }] };
const cut = _fmCut(pm, { st: [0.02, 0.06, 0.1, 0.14, 0.3] });
near(cut.drivers[0].slabs[1].from, 0.1, 'pct start resolved to the division median');
near(_weightedFactor({ st: 0.103, gr: null, fill: null }, cut, 1).f, 1.1, 'above the median -> top slab');
near(_weightedFactor({ st: 0.08, gr: null, fill: null }, cut, 1).f, 0.9, 'below the median -> bottom slab');
assert.strictEqual(_fmCut(model({ st: 1 }), {}).drivers[0].slabs, slabs.st, 'value drivers untouched');
// continuous: each driver against the division median, raised to its strength; growth compared as (1+g)/(1+median)
const med = { st: 0.1, gr: 0.1, fill: 0.7 }, lim = { drivers: [], rules: [], shrink_k: 0, clamp: [0.5, 2] };
near(_contFactor({ st: 0.12, gr: 0.32, fill: 0.7 }, med, { st: 0.25, growth: 0.2, fill: 0 }, lim, 1).f,
  Math.pow(1.2, 0.25) * Math.pow(1.32 / 1.1, 0.2), 'continuous product');
near(_contFactor({ st: 0.1, gr: 0.1, fill: 0.7 }, med, { st: 1, growth: 1, fill: 1 }, lim, 1).f, 1, 'at the median -> 1.00');
near(_contFactor({ st: 0.05, gr: null, fill: 0.35 }, med, { st: 0, growth: 1, fill: -0.5 }, lim, 1).f, Math.pow(0.5, -0.5), 'strength 0 off, missing skipped, negative strength protects low fill');
assert.ok(_contFactor({ st: null, gr: null, fill: null }, med, { st: 1 }, lim, 1).none, 'no data -> neutral');
near(_contFactor({ st: 0.3, gr: 0.1, fill: 0.7 }, med, { st: 1 }, { ...lim, clamp: [0.8, 1.2] }, 1).f, 1.2, 'shared clamp applies');
// 19V26 beside 25V26; with agree on, growth only counts when both sit on the same side of their division median
const med2 = { ...med, gb: -0.2 };
near(_contFactor({ gr: 0.32, gb: 0.0 }, med2, { growth: 0.5, base: 0.5 }, lim, 1).f, Math.pow(1.32 / 1.1, 0.5) * Math.pow(1 / 0.8, 0.5), 'both comparables count');
near(_contFactor({ gr: 0.32, gb: 0.0 }, med2, { growth: 0.5, base: 0.5, agree: true }, lim, 1).f, Math.pow(1.32 / 1.1, 0.5) * Math.pow(1 / 0.8, 0.5), 'agree: both above -> kept');
const split = _contFactor({ st: 0.12, gr: 0.32, gb: -0.4 }, med2, { st: 0.25, growth: 0.5, base: 0.5, agree: true }, lim, 1);
assert.ok(split.split, 'disagreement detected');
near(split.f, Math.pow(1.2, 0.25), 'agree: they disagree -> growth ignored, sell-thru kept');
near(_contFactor({ gr: 0.32, gb: null }, med2, { growth: 0.5, base: 0.5, agree: true }, lim, 1).f, Math.pow(1.32 / 1.1, 0.5), 'one comparable only -> kept');
near(_contFactor({ gr: 0.32, gb: -0.4 }, med2, { growth: 0.5, base: 0, agree: true }, lim, 1).f, 1, 'agreement still checked with the 19V26 strength at 0');
console.log('factor model checks passed');
