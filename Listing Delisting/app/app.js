'use strict';
// Listing / Delisting Impact Analysis - RS Planning (tabs revamped 2026-09-26).
// Everything here is read from JSON built by the daily data-lake sync (scripts/*.py, see PRD_LOGIC.md):
//   kb.json          listing history, one Y / N / . flag per store x department x month
//   sales.json       month-wise SL_V per store x department (the month-wise data-lake export)
//   windows.json     season windows per category, festival windows per cluster (Calendar app), per-department
//                    window benchmarks + festival lift, day-wise vs month-wise reconciliation, sources
//   suggestions.json like-for-like delist / held / relist suggestions, each with the exact dates, days, sums
//                    and years it was computed from (the drill-down shows them)
//   stores.json      RS Planning store master (name, cluster, LfL / Ramp / NSO, opening date, status)

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmtN = n => Math.round(n || 0).toLocaleString('en-IN');
function fmtR(v) {
  const a = Math.abs(v || 0);
  if (a >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`;
  if (a >= 1e5) return `₹${(v / 1e5).toFixed(1)} L`;
  return `₹${fmtN(v)}`;
}
const fmtRate = v => `${fmtR(v)}/day`;
const pct = v => v == null ? '—' : `${Math.round(v * 100)}%`;
const compact = v => !v ? '' : v >= 1e5 ? (v / 1e5).toFixed(v >= 1e6 ? 0 : 1) + 'L' : v >= 1e3 ? Math.round(v / 1e3) + 'k' : String(Math.round(v));
const dmy = s => { const [y, m, d] = s.split('-'); return `${+d} ${MON[+m - 1]} ${y}`; };
const span = (a, b) => `${dmy(a)} – ${dmy(b)}`;
const WLABEL = { in: 'In-season', normal: 'Normal', off: 'Off-season' };
const wchip = t => t ? `<span class="wchip w-${t}">${WLABEL[t]}</span>` : '';
const CAT = { summer: 'Summer', prewinter: 'Pre-winter', lt_winter: 'Light winter', hvy_winter: 'Heavy winter', regular: 'Regular', occasional: 'Occasional' };
const tierBadge = t => `<span class="risk-badge risk-${t.toLowerCase()}">${t}</span>`;
const DIVISION_OF_PREFIX = {
  M: 'Mens', ME: 'Mens', ML: 'Mens', MSE: 'Mens', MU: 'Mens', MW: 'Mens',
  L: 'Ladies', LW: 'Ladies', LWW: 'Ladies',
  KB: 'Kids', KBW: 'Kids', KG: 'Kids', KGW: 'Kids', KI: 'Kids', KIW: 'Kids', KW: 'Kids', 'BOYS DESIGNER': 'Kids', 'GIRLS DESIGNER': 'Kids',
};
const DIVISIONS = ['Mens', 'Ladies', 'Kids', 'Other'];
const divisionOf = dept => DIVISION_OF_PREFIX[dept.split('_')[0].trim().toUpperCase()] || 'Other';   // Accessories, Raincoat, Fabric…

let kb, sales, win, sug, storeMeta = {}, mode = 'overview';
const view = $('#view');
const catOf = d => win.departments[d]?.category || 'regular';
const typeOf = (d, monthLabel) => win.categories[catOf(d)]?.type[monthLabel.slice(0, 3)];
const catLabel = d => CAT[catOf(d)] || catOf(d);
function storeLabel(s) {
  const m = storeMeta[s];
  return m ? [s, m.name !== s && m.name, m.cluster, m.type].filter(Boolean).join(' · ') : s;
}
function storeLine(s) {
  const m = storeMeta[s];
  if (!m) return '';
  return [m.name !== s && m.name, m.cluster && `Cluster ${m.cluster}`, m.type, m.opened && `opened ${m.opened}`, m.status].filter(Boolean).join(' · ');
}
function latestCompleteIdx() {
  const n = kb.months.length - 1;
  return kb.months[n].includes('(Till Date)') ? n - 1 : n;
}
const sale = (s, d, m) => sales.data[s]?.[d]?.[m] || 0;

// one lookup: store|dept -> its suggestion (delist / held / relist), used for row badges and the drill-down
const sugIndex = new Map();
const KIND = { delist: 'Delist', held: 'Held', relist: 'Relist' };
const sugBadge = (s, d) => { const x = sugIndex.get(`${s}|${d}`); return x ? ` <span class="sug-badge sug-${x.kind}">${KIND[x.kind]}</span>` : ''; };

// ---------------------------------------------------------------- sorting + CSV helpers

const makeSort = (key = null, dir = 1) => ({ key, dir });
function sortRows(rows, st, keyFor) {
  if (!st.key) return rows;
  return rows.slice().sort((a, b) => {
    const va = keyFor(a, st.key), vb = keyFor(b, st.key);
    return (typeof va === 'string' ? va.localeCompare(vb) : (va ?? -Infinity) - (vb ?? -Infinity)) * st.dir;
  });
}
function th(label, key, st, num, title) {
  const on = st.key === key;
  return `<th data-sort="${key}" class="sortable${num ? ' num' : ''}${on ? ' sorted' : ''}"${title ? ` title="${esc(title)}"` : ''}>${label}${on ? (st.dir === 1 ? ' ▲' : ' ▼') : ''}</th>`;
}
function downloadCsv(name, header, rows) {
  const q = v => { const s = String(v ?? ''); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const csv = '﻿' + [header, ...rows].map(r => r.map(q).join(',')).join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  a.download = name;
  document.body.append(a); a.click(); a.remove();
}
const options = (vals, cur, all) => `<option value="">${all}</option>` + vals.map(v => `<option ${v === cur ? 'selected' : ''} value="${esc(v)}">${esc(v)}</option>`).join('');
const catOptions = cur => `<option value="">All season categories</option>` + Object.keys(win.categories).sort()
  .map(c => `<option value="${c}" ${c === cur ? 'selected' : ''}>${esc(CAT[c] || c)}</option>`).join('');

// ---------------------------------------------------------------- load

Promise.all(['kb.json', 'sales.json', 'windows.json', 'suggestions.json', 'stores.json'].map(f =>
  fetch(f).then(r => { if (!r.ok) throw new Error(`${f}: ${r.status}`); return r.json(); })
    .catch(e => { if (f === 'stores.json') return {}; throw e; })))
  .then(([k, s, w, g, st]) => {
    kb = k; sales = s; win = w; sug = g; storeMeta = st.stores || {};
    for (const kind of ['delist', 'held', 'relist']) for (const r of sug[kind]) sugIndex.set(`${r.store}|${r.dept}`, { kind, r });
    $('#dept-list').innerHTML = kb.departments.map(d => `<option value="${esc(d)}">`).join('');
    $('#store-list').innerHTML = kb.stores.map(s => `<option value="${esc(s)}" label="${esc(storeLabel(s))}">`).join('');
    show('overview');
  })
  .catch(err => { view.innerHTML = `<p class="err">Couldn't load the data: ${esc(err.message)}. The daily sync builds these files - check the Data sync panel on Landing.</p>`; });

document.querySelectorAll('.tab-btn').forEach(b => b.addEventListener('click', () => show(b.dataset.mode)));

function show(m) {
  mode = m;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === m));
  if (!kb) return;
  VIEWS[m].controls();
  VIEWS[m].results();
}

// every control carries data-f="<state>.<field>"; a change updates that field and redraws only the results
view.addEventListener('input', e => {
  const f = e.target.dataset.f;
  if (!f) return;
  const [k, field] = f.split('.');
  ST[k][field] = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
  if (e.target.dataset.redraw) VIEWS[mode].controls();   // controls whose options depend on this value
  VIEWS[mode].results();
});
view.addEventListener('click', e => {
  const act = e.target.closest('[data-act]');
  if (act) { ACTIONS[act.dataset.act](act); return; }
  const h = e.target.closest('th[data-sort]');
  if (h) {
    const st = ST[h.closest('table').dataset.state].sort;
    st.dir = st.key === h.dataset.sort ? -st.dir : (h.classList.contains('num') ? -1 : 1);
    st.key = h.dataset.sort;
    VIEWS[mode].results();
    return;
  }
  const go = e.target.closest('[data-go]');
  if (go) { if (go.dataset.kind) ST.sug.kind = go.dataset.kind; show(go.dataset.go); return; }
  const tr = e.target.closest('tr[data-store][data-dept]');
  if (tr) openDrill(tr.dataset.store, tr.dataset.dept);
});
view.addEventListener('keydown', e => {
  const tr = e.target.closest('tr[data-store][data-dept]');
  if (tr && e.key === 'Enter') openDrill(tr.dataset.store, tr.dataset.dept);
});

const ST = {
  sug: { kind: 'delist', q: '', div: '', cat: '', cl: '', tier: '', sort: makeSort() },
  grid: { dept: '', store: '', show: 'values', order: 'total', q: '', cl: '', div: '', cat: '' },
  ev: { q: '', type: 'all', win: '', div: '', zero: false, sort: makeSort('monthIdx', -1) },
  sea: { dept: '' },
  data: { cl: '', year: '' },
};
const ACTIONS = {
  kind: el => { ST.sug.kind = el.dataset.kind; ST.sug.sort = makeSort(); VIEWS.suggestions.controls(); VIEWS.suggestions.results(); },
  'sug-csv': () => exportSuggestions(),
  'ev-csv': () => exportEvents(),
  'open-dept': el => { ST.grid.dept = el.dataset.dept; show('by-dept'); },
};
const CAP = 300;

// ---------------------------------------------------------------- listing-change events (month-level)

let allEvents = null;
function computeEvents() {
  const out = [];
  for (const store of kb.stores) {
    const depts = kb.data[store];
    if (!depts) continue;
    for (const dept in depts) {
      const h = depts[dept];
      let pi = -1, pc = null;
      for (let i = 0; i < h.length; i++) {
        const ch = h[i];
        if (ch === '.') continue;
        if (pc !== null && ch !== pc) {
          const before = sale(store, dept, kb.months[pi]), after = sale(store, dept, kb.months[i]);
          out.push({ store, dept, div: divisionOf(dept), monthIdx: i, fromMonth: kb.months[pi], toMonth: kb.months[i],
            toStatus: ch, before, after, win: typeOf(dept, kb.months[i]) });
        }
        pc = ch; pi = i;
      }
    }
  }
  return out;
}
const events = () => allEvents || (allEvents = computeEvents());
const realEvent = e => !(e.before === 0 && e.after === 0);

// ---------------------------------------------------------------- views

const VIEWS = {
  // ------------------------------------------------ Overview
  overview: {
    controls() { view.innerHTML = '<div id="res"></div>'; },
    results() {
      const li = latestCompleteIdx(), L = kb.months[li];
      let listedNow = 0, listedPrev = 0;
      const listedByMonth = new Array(kb.months.length).fill(0);
      const byDiv = Object.fromEntries(DIVISIONS.map(d => [d, { listed: 0, delists: 0, relists: 0, sd: 0, stake: 0, sr: 0, exp: 0 }]));
      const stores = new Set(), depts = new Set();
      for (const s of kb.stores) for (const d in (kb.data[s] || {})) {
        const h = kb.data[s][d];
        for (let i = 0; i < h.length; i++) if (h[i] === 'Y') listedByMonth[i]++;
        if (h[li] === 'Y') { listedNow++; byDiv[divisionOf(d)].listed++; stores.add(s); depts.add(d); }
        if (h[li - 1] === 'Y') listedPrev++;
      }
      const real = events().filter(realEvent);
      const del = new Array(kb.months.length).fill(0), rel = new Array(kb.months.length).fill(0);
      for (const e of real) (e.toStatus === 'N' ? del : rel)[e.monthIdx]++;
      const monthEv = real.filter(e => e.monthIdx === li);
      for (const e of monthEv) byDiv[e.div][e.toStatus === 'N' ? 'delists' : 'relists']++;
      for (const r of sug.delist) { const v = byDiv[divisionOf(r.dept)]; v.sd++; v.stake += r.shortfall_month; }
      for (const r of sug.relist) { const v = byDiv[divisionOf(r.dept)]; v.sr++; v.exp += r.expected_sales; }
      const stake = sug.delist.reduce((a, r) => a + r.shortfall_month, 0), exp = sug.relist.reduce((a, r) => a + r.expected_sales, 0);
      const delta = listedNow - listedPrev;
      const kpi = (lbl, val, sub, go) => `<div class="ov-kpi${go ? ' link' : ''}"${go ? ` data-go="${go}"` : ''}><div class="lbl">${lbl}</div><div class="val">${val}</div><div class="sub">${sub}</div></div>`;
      const nd = r => `<tr class="drillable" tabindex="0" data-store="${esc(r.store)}" data-dept="${esc(r.dept)}">`;
      const wn = Object.entries(win.windows_now).sort(([a], [b]) => a.localeCompare(b)).map(([c, w]) => {
        const n = Object.values(win.departments).filter(d => d.category === c).length;
        return `<tr><td>${esc(CAT[c] || c)}</td><td class="num">${n}</td><td>${wchip(w.current.type)}</td>
          <td>${wchip(w.evaluate.type)} <span class="muted">${span(w.evaluate.from, w.evaluate.to)}</span></td>
          <td>${wchip(w.next.type)} <span class="muted">from ${dmy(w.next.from)}</span></td></tr>`;
      }).join('');
      const divRows = DIVISIONS.map(d => { const v = byDiv[d]; return `<tr><td>${d}</td><td class="num">${fmtN(v.listed)}</td><td class="num">${fmtN(v.delists)}</td>
        <td class="num">${fmtN(v.relists)}</td><td class="num">${fmtN(v.sd)}</td><td class="num">${fmtR(v.stake)}</td><td class="num">${fmtN(v.sr)}</td><td class="num">${fmtR(v.exp)}</td></tr>`; }).join('');
      const topD = sug.delist.slice(0, 8).map(r => `${nd(r)}<td>${esc(r.store)}</td><td>${esc(r.dept)}</td><td>${wchip(r.window.type)}</td>
        <td class="num">${fmtRate(r.benchmark.rate)} → ${fmtRate(r.window.rate)}</td><td class="num dn">−${fmtR(r.shortfall_month)}</td><td>${tierBadge(r.tier)}</td></tr>`).join('');
      const topR = sug.relist.slice(0, 8).map(r => `${nd(r)}<td>${esc(r.store)}</td><td>${esc(r.dept)}</td><td>${wchip(r.target.type)} <span class="muted">${span(r.target.from, r.target.to)}</span></td>
        <td class="num">${pct(r.vs_peers)}</td><td class="num up">+${fmtR(r.expected_sales)}</td></tr>`).join('');
      $('#res').innerHTML = `
        <p class="ov-month">Latest complete listing month <strong>${esc(L)}</strong> · day-wise sales through <strong>${dmy(sug.anchor)}</strong> ·
          suggestions built ${esc(sug.generated_at.replace('T', ' '))} · <button class="linkish" data-go="data">sources &amp; checks →</button></p>
        <div class="ov-kpis">
          ${kpi('Listed combos', fmtN(listedNow), `<span class="${delta >= 0 ? 'up' : 'dn'}">${delta >= 0 ? '+' : ''}${fmtN(delta)}</span> vs ${esc(kb.months[li - 1])} · ${fmtN(stores.size)} stores · ${fmtN(depts.size)} depts`, 'by-dept')}
          ${kpi(`Changes in ${esc(L)}`, `${fmtN(monthEv.filter(e => e.toStatus === 'N').length)} / ${fmtN(monthEv.filter(e => e.toStatus === 'Y').length)}`, 'delisted / relisted, excl. zero-sales flag flips', 'events')}
          ${kpi('Delist suggestions', fmtN(sug.counts.delist), `${fmtN(sug.counts.delist_by_tier.High)} high · ${fmtR(stake)}/month below own same-window benchmark`, 'suggestions')}
          ${kpi('Relist opportunities', fmtN(sug.counts.relist), `${fmtR(exp)} expected in their coming season window`, 'suggestions')}
          ${kpi('Held — off-season read', fmtN(sug.counts.held), 'weak now, but the season starts soon: review then, not now', 'suggestions')}
        </div>
        <div class="ov-grid">
          <div class="ov-card wide"><h3>Season windows now <span class="hint">each category judged only against its own window in earlier years; festival days removed (Calendar app)</span></h3>
            <table><thead><tr><th>Season category</th><th class="num">Departments</th><th>Today</th><th>Suggestions judged on</th><th>Next window</th></tr></thead><tbody>${wn}</tbody></table></div>
          <div class="ov-card wide"><h3>By division <span class="hint">listing in ${esc(L)} · suggestions as of ${dmy(sug.anchor)}</span></h3>
            <table><thead><tr><th>Division</th><th class="num">Listed</th><th class="num">Delisted</th><th class="num">Relisted</th><th class="num">Delist sugg.</th><th class="num">Shortfall / month</th><th class="num">Relist sugg.</th><th class="num">Relist expected</th></tr></thead><tbody>${divRows}</tbody></table></div>
          <div class="ov-card"><h3>Top delist suggestions <button class="more" data-go="suggestions">See all →</button></h3>
            ${topD ? `<table><thead><tr><th>Store</th><th>Department</th><th>Window</th><th class="num">Before → now</th><th class="num">Shortfall / mo</th><th>Severity</th></tr></thead><tbody>${topD}</tbody></table>` : '<p class="ov-empty">None.</p>'}</div>
          <div class="ov-card"><h3>Top relist opportunities <button class="more" data-go="suggestions" data-kind="relist">See all →</button></h3>
            ${topR ? `<table><thead><tr><th>Store</th><th>Department</th><th>Coming window</th><th class="num">vs peers</th><th class="num">Expected</th></tr></thead><tbody>${topR}</tbody></table>` : '<p class="ov-empty">None.</p>'}</div>
          <div class="ov-card wide"><h3>Listing over time <span class="hint">listed combos per month, with delists and relists (excl. zero-sales flag flips)</span></h3>${listingSvg(listedByMonth, del, rel, li)}
            <div class="ov-legend"><span><i style="background:var(--color-primary)"></i>Listed combos</span><span><i style="background:var(--n)"></i>Delisted</span><span><i style="background:var(--y)"></i>Relisted</span></div></div>
        </div>`;
    },
  },

  // ------------------------------------------------ Suggestions
  suggestions: {
    controls() {
      const s = ST.sug, rows = sug[s.kind];
      const clusters = [...new Set(rows.map(r => r.cluster))].sort();
      const seg = k => `<button class="seg-btn${s.kind === k ? ' on' : ''}" data-act="kind" data-kind="${k}">${KIND[k]} <b>${fmtN(sug.counts[k])}</b></button>`;
      const p = sug.params;
      const rule = {
        delist: `Listed today and through its latest window, yet selling at ≤ ${pct(p.delist_ratio)} of its <b>own</b> rate on the <b>same dates</b> in the years it was on the floor (in a store open 12+ months) — and at ≤ ${pct(p.delist_relative)} of how its cluster's other stores moved over those dates. Festival days are removed on both sides; rates are per festival-free trading day.`,
        held: `Would qualify as delist, but only on an <b>off-season</b> read, and the department's in-season starts within ${p.relist_lookahead_days} days. Not a delist call — review once the season is running.`,
        relist: `Delisted today, the department's in-season (or normal) window starts within ${p.relist_lookahead_days} days, and the last time this store sold it in that window it sold at ≥ ${pct(p.relist_vs_peers)} of its cluster peers' median. Expected = its own rate then × the window's festival-free days + festival days at the department's festival lift.`,
      }[s.kind];
      view.innerHTML = `<section class="bar">
          <div class="seg" role="tablist">${seg('delist')}${seg('relist')}${seg('held')}</div>
          <input data-f="sug.q" value="${esc(s.q)}" placeholder="Search store or department…" aria-label="Search">
          <select data-f="sug.div" aria-label="Division">${options(DIVISIONS, s.div, 'All divisions')}</select>
          <select data-f="sug.cat" aria-label="Season category">${catOptions(s.cat)}</select>
          <select data-f="sug.cl" aria-label="Calendar cluster">${options(clusters, s.cl, 'All clusters')}</select>
          ${s.kind !== 'relist' ? `<select data-f="sug.tier" aria-label="Severity">${options(['High', 'Medium', 'Low'], s.tier, 'All severities')}</select>` : ''}
          <button class="btn" data-act="sug-csv">Export CSV</button>
        </section>
        <p class="rule">${rule} <span class="muted">Click a row for the exact dates, days and sums behind it.</span></p>
        <div id="res"></div>`;
    },
    results() {
      const s = ST.sug, q = s.q.trim().toUpperCase();
      let rows = sug[s.kind].filter(r => (!q || r.store.includes(q) || r.dept.toUpperCase().includes(q) || storeLabel(r.store).toUpperCase().includes(q))
        && (!s.div || divisionOf(r.dept) === s.div) && (!s.cat || r.category === s.cat) && (!s.cl || r.cluster === s.cl) && (!s.tier || r.tier === s.tier));
      const key = (r, k) => ({ store: r.store, dept: r.dept, rate: r.window?.rate, bench: r.benchmark?.rate, ratio: r.ratio, peers: r.peers?.ratio,
        rel: r.relative, short: r.shortfall_month, tier: { High: 3, Medium: 2, Low: 1 }[r.tier], next: r.next_window?.from,
        target: r.target?.from, own: r.evidence?.rate, med: r.peers?.median_rate, vs: r.vs_peers, exp: r.expected_sales, last: r.last_listed }[k]);
      rows = sortRows(rows, s.sort, key);
      const total = s.kind === 'relist' ? rows.reduce((a, r) => a + r.expected_sales, 0) : rows.reduce((a, r) => a + r.shortfall_month, 0);
      const st = s.sort, cells = r => `<td>${esc(r.store)}<div class="sub">${esc(storeMeta[r.store]?.name && storeMeta[r.store].name !== r.store ? storeMeta[r.store].name : '')} ${esc(r.cluster)}</div></td>
        <td>${esc(r.dept)}<div class="sub">${esc(divisionOf(r.dept))} · ${esc(CAT[r.category] || r.category)}</div></td>`;
      let head, body;
      if (s.kind === 'relist') {
        head = `${th('Store', 'store', st)}${th('Department', 'dept', st)}${th('Coming window', 'target', st)}${th('Last time in that window', 'own', st, 1)}
          ${th('Cluster peers (median)', 'med', st, 1)}${th('vs peers', 'vs', st, 1)}${th('Expected', 'exp', st, 1, 'Festival-free days at its own rate + festival days at the department festival lift')}${th('Last listed', 'last', st)}`;
        body = rows.slice(0, CAP).map(r => `<tr class="drillable" tabindex="0" data-store="${esc(r.store)}" data-dept="${esc(r.dept)}">${cells(r)}
          <td>${wchip(r.target.type)}<div class="sub">${span(r.target.from, r.target.to)}</div></td>
          <td class="num">${fmtRate(r.evidence.rate)}<div class="sub">${r.evidence.year}, ${r.evidence.days} days</div></td>
          <td class="num">${fmtRate(r.peers.median_rate)}<div class="sub">${r.peers.stores} stores · ${esc(r.peers.basis)}</div></td>
          <td class="num up">${pct(r.vs_peers)}</td><td class="num up">+${fmtR(r.expected_sales)}</td><td>${esc(r.last_listed)}</td></tr>`).join('');
      } else {
        head = `${th('Store', 'store', st)}${th('Department', 'dept', st)}<th>Window judged</th>${th('Same dates before', 'bench', st, 1, 'Festival-free rate on the same dates in the years it was on the floor')}
          ${th('Now', 'rate', st, 1)}${th('Own vs before', 'ratio', st, 1)}${th('Peers vs before', 'peers', st, 1, "Its cluster's other stores, same department, same dates")}
          ${th('Shortfall / month', 'short', st, 1)}${th('Severity', 'tier', st, 1)}${s.kind === 'held' ? th('Season starts', 'next', st) : ''}`;
        body = rows.slice(0, CAP).map(r => `<tr class="drillable" tabindex="0" data-store="${esc(r.store)}" data-dept="${esc(r.dept)}">${cells(r)}
          <td>${wchip(r.window.type)}<div class="sub">${span(r.window.from, r.window.to)}</div></td>
          <td class="num">${fmtRate(r.benchmark.rate)}<div class="sub">${r.benchmark.years.map(y => y.year).join(', ')}</div></td>
          <td class="num">${fmtRate(r.window.rate)}<div class="sub">${r.window.days} days</div></td>
          <td class="num dn">${pct(r.ratio)}</td><td class="num">${pct(r.peers.ratio)}<div class="sub">${r.peers.stores} stores · ${esc(r.peers.basis)}</div></td>
          <td class="num dn">−${fmtR(r.shortfall_month)}</td><td>${tierBadge(r.tier)}</td>${s.kind === 'held' ? `<td>${wchip(r.next_window.type)}<div class="sub">${dmy(r.next_window.from)}</div></td>` : ''}</tr>`).join('');
      }
      $('#res').innerHTML = `<p class="count">${fmtN(rows.length)} ${KIND[s.kind].toLowerCase()} row${rows.length === 1 ? '' : 's'}${rows.length > CAP ? ` — showing the first ${CAP}; filter or export for the rest` : ''} ·
          ${s.kind === 'relist' ? `${fmtR(total)} expected` : `${fmtR(total)}/month shortfall`} ·
          <span class="muted">${fmtN(sug.counts.scored)} listed combos had a clean same-window benchmark (${fmtN(sug.counts.funnel.listed_now)} listed now → ${fmtN(sug.counts.funnel.listed_through_window)} listed through their window → ${fmtN(sug.counts.funnel.store_traded_window)} in a store trading it → ${fmtN(sug.counts.funnel.with_benchmark)} with earlier years in a store already open 12 months)</span></p>
        ${rows.length ? `<div class="tbl-wrap"><table class="tbl" data-state="sug"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>` : '<p class="ov-empty">Nothing matches these filters.</p>'}`;
    },
  },

  // ------------------------------------------------ By Department / By Store (shared grid)
  'by-dept': gridView('dept'),
  'by-store': gridView('store'),

  // ------------------------------------------------ Change Events
  events: {
    controls() {
      const s = ST.ev;
      view.innerHTML = `<section class="bar">
          <input data-f="ev.q" value="${esc(s.q)}" placeholder="Search store or department…" aria-label="Search">
          <select data-f="ev.type" aria-label="Change"><option value="all">Delisted and relisted</option><option value="N" ${s.type === 'N' ? 'selected' : ''}>Delisted only</option><option value="Y" ${s.type === 'Y' ? 'selected' : ''}>Relisted only</option></select>
          <select data-f="ev.div" aria-label="Division">${options(DIVISIONS, s.div, 'All divisions')}</select>
          <select data-f="ev.win" aria-label="Window at the change"><option value="">Any window</option>${['in', 'normal', 'off'].map(t => `<option value="${t}" ${s.win === t ? 'selected' : ''}>Changed in ${WLABEL[t].toLowerCase()}</option>`).join('')}</select>
          <label class="check"><input type="checkbox" data-f="ev.zero" ${s.zero ? 'checked' : ''}> include zero-sales flag flips</label>
          <button class="btn" data-act="ev-csv">Export CSV</button>
        </section>
        <p class="rule">Every Y ↔ N flip in the listing history, with the department's sales in the month before and the month of the change (month-wise export). The window is the department's season window in the month of the change.</p>
        <div id="res"></div>`;
    },
    results() {
      const rows = filteredEvents();
      const d = rows.filter(e => e.toStatus === 'N'), r = rows.filter(e => e.toStatus === 'Y');
      const st = ST.ev.sort;
      const body = sortRows(rows, st, (e, k) => e[k]).slice(0, CAP).map(e => `<tr class="drillable" tabindex="0" data-store="${esc(e.store)}" data-dept="${esc(e.dept)}">
        <td>${esc(e.store)}</td><td>${esc(e.dept)}${sugBadge(e.store, e.dept)}</td><td>${e.div}</td>
        <td><span class="chip ${e.toStatus === 'N' ? 'n' : 'y'}">&nbsp;</span> ${e.toStatus === 'N' ? 'Delisted' : 'Relisted'}</td>
        <td>${esc(e.fromMonth)} → ${esc(e.toMonth)}</td><td>${wchip(e.win)}</td><td class="num">${fmtR(e.before)}</td><td class="num">${fmtR(e.after)}</td></tr>`).join('');
      $('#res').innerHTML = `<p class="count">${fmtN(rows.length)} events${rows.length > CAP ? ` — showing ${CAP}, export for all` : ''} ·
          <b>${fmtN(d.length)}</b> delisted (${fmtR(d.reduce((a, e) => a + e.before, 0))} the month before) ·
          <b>${fmtN(r.length)}</b> relisted (${fmtR(r.reduce((a, e) => a + e.after, 0))} the month of relisting)</p>
        ${rows.length ? `<div class="tbl-wrap"><table class="tbl" data-state="ev"><thead><tr>${th('Store', 'store', st)}${th('Department', 'dept', st)}${th('Division', 'div', st)}
          ${th('Change', 'toStatus', st)}${th('Month', 'monthIdx', st, 1)}${th('Window', 'win', st)}${th('Sales month before', 'before', st, 1)}${th('Sales month of change', 'after', st, 1)}</tr></thead>
          <tbody>${body}</tbody></table></div>` : '<p class="ov-empty">No events match.</p>'}`;
    },
  },

  // ------------------------------------------------ Seasonality
  seasonality: {
    controls() {
      view.innerHTML = `<section class="bar"><input list="dept-list" data-f="sea.dept" value="${esc(ST.sea.dept)}" placeholder="Type a department…" aria-label="Department"></section>
        <p class="rule">Festival-free sales per trading store-day, ${win.params.years[0]}–${win.params.years.at(-1)} pooled, so a festival's shifting date never moves a month's number.
          Each month is compared only with its <b>own window's</b> benchmark (in-season with in-season, off-season with off-season); festivals get their own lift vs normal days.</p>
        <div id="res"></div>`;
    },
    results() {
      const dep = ST.sea.dept.trim().toUpperCase(), d = win.departments[dep];
      if (!d) { $('#res').innerHTML = `<p class="ov-empty">${dep ? 'No festival-free sales history for that department.' : 'Pick a department above.'}</p>`; return; }
      const c = win.categories[d.category];
      const wrows = ['in', 'normal', 'off'].filter(t => d.windows[t]).map(t => { const w = d.windows[t]; return `<tr><td>${wchip(t)}</td><td>${w.months.join(', ')}</td>
        <td class="num">${fmtRate(w.rate)}</td><td class="num">${fmtN(w.days)}</td><td class="num">${fmtR(w.sales)}</td></tr>`; }).join('');
      const mrows = d.months.map(m => { const v = m.vs_window, cls = v == null ? '' : v < 0.85 ? 'dn' : v > 1.15 ? 'up' : '';
        return `<tr><td>${m.month}</td><td>${wchip(m.type)}</td><td class="num">${fmtRate(m.rate)}</td><td class="num ${cls}">${pct(v)}</td>
          <td class="num">${fmtN(m.days)}</td><td class="num">${fmtR(m.sales)}</td><td class="num muted">${c.index[m.month].toFixed(2)}</td></tr>`; }).join('');
      const frows = d.festivals.map(f => `<tr><td>${esc(f.festival)}</td><td class="num ${f.lift >= 1.15 ? 'up' : f.lift <= 0.85 ? 'dn' : ''}">${f.lift.toFixed(2)}×</td>
        <td class="num">${fmtRate(f.festival_sales / f.festival_days)}</td><td class="num">${fmtRate(f.normal_rate)}</td><td class="num">${fmtN(f.festival_days)}</td><td class="num">${f.stores}</td></tr>`).join('');
      $('#res').innerHTML = `<h2 class="h2">${esc(dep)} <span class="muted">· ${esc(divisionOf(dep))} · ${esc(CAT[d.category] || d.category)} season category</span></h2>
        <div class="ov-card">${seasonSvg(d)}<div class="ov-legend">${['in', 'normal', 'off'].map(t => `<span>${wchip(t)}</span>`).join('')}<span>dashed line = that window's benchmark</span></div></div>
        <div class="ov-grid" style="margin-top:12px">
          <div class="ov-card"><h3>Window benchmarks <span class="hint">what each month is compared with</span></h3>
            <table><thead><tr><th>Window</th><th>Months</th><th class="num">Benchmark</th><th class="num">Store-days</th><th class="num">Sales</th></tr></thead><tbody>${wrows}</tbody></table></div>
          <div class="ov-card"><h3>Festival lift <span class="hint">festival days vs the same stores' normal days, same months</span></h3>
            ${frows ? `<table><thead><tr><th>Festival</th><th class="num">Lift</th><th class="num">Festival days</th><th class="num">Normal days</th><th class="num">Store-days</th><th class="num">Stores</th></tr></thead><tbody>${frows}</tbody></table>` : '<p class="ov-empty">No festival sales recorded.</p>'}</div>
          <div class="ov-card wide"><h3>Month by month <span class="hint">vs its own window benchmark · red = weak (&lt; 85%), green = strong (&gt; 115%) · category index = chain-wide ${esc(CAT[d.category] || d.category)} month vs its yearly average</span></h3>
            <table><thead><tr><th>Month</th><th>Window</th><th class="num">Festival-free rate</th><th class="num">vs window</th><th class="num">Store-days</th><th class="num">Sales</th><th class="num">Category index</th></tr></thead><tbody>${mrows}</tbody></table></div>
        </div>`;
    },
  },

  // ------------------------------------------------ Data & checks
  data: {
    controls() {
      const clusters = [...new Set(win.festivals.map(f => f.cluster))].sort(), years = [...new Set(win.festivals.map(f => String(f.year)))].sort();
      view.innerHTML = `<div id="src"></div>
        <section class="bar" style="margin-top:14px"><strong>Festival windows</strong>
          <select data-f="data.cl" aria-label="Cluster">${options(clusters, ST.data.cl, 'All clusters')}</select>
          <select data-f="data.year" aria-label="Year">${options(years, ST.data.year, 'All years')}</select></section>
        <div id="res"></div>`;
      const s = sug.sources, dly = s.daily, cal = s.calendar, p = sug.params;
      const bad = win.reconciliation.filter(r => !r.partial && Math.abs(r.diff_pct) > 0.5);
      const recon = win.reconciliation.map(r => `<tr class="${r.partial ? 'muted' : Math.abs(r.diff_pct) > 0.5 ? 'warnrow' : ''}"><td>${esc(r.month)}${r.partial ? ' (partial)' : ''}</td>
        <td class="num">${fmtR(r.day_wise)}</td><td class="num">${fmtR(r.month_wise)}</td><td class="num">${r.diff_pct.toFixed(2)}%</td></tr>`).join('');
      const catRows = Object.entries(win.categories).sort().map(([c, v]) => `<tr><td>${esc(CAT[c] || c)}</td>${MON.map(m => `<td class="num w-cell w-${v.type[m]}" title="${WLABEL[v.type[m]]}">${v.index[m].toFixed(2)}</td>`).join('')}</tr>`).join('');
      $('#src').innerHTML = `<div class="ov-grid">
        <div class="ov-card"><h3>Where every number comes from</h3><table><tbody>
          <tr><td>Day-wise sales</td><td><code>${esc(dly.source_file)}</code><div class="sub">${esc(dly.source_folder)} · ${fmtN(dly.rows_read)} rows read → ${fmtN(dly.rows_out)} store × dept × days · ${esc(dly.date_min)} to ${esc(dly.date_max)} · cached ${esc(dly.built_at.replace('T', ' '))}</div></td></tr>
          <tr><td>Listing</td><td>kb.json · ${esc(kb.months[0])} – ${esc(kb.months.at(-1))} · ${fmtN(kb.stores.length)} stores × ${fmtN(kb.departments.length)} departments<div class="sub">yearly Directory Listing workbooks (data/listing)</div></td></tr>
          <tr><td>Festivals</td><td>Calendar app: <code>${esc(cal.festival_master)}</code> (Pre / Core / Post per cluster) on <code>${esc(cal.dates)}</code><div class="sub">${cal.clusters.length} clusters · ${fmtN(cal.stores_mapped)} stores mapped via <code>${esc(cal.store_clusters)}</code> · ${esc(cal.unmapped_rule)}${cal.missing_dates.length ? ` · missing dates: ${esc(cal.missing_dates.join(', '))}` : ''}</div></td></tr>
          <tr><td>Season category</td><td>${esc(s.season_category)}</td></tr>
          <tr><td>Suggestions</td><td>built ${esc(sug.generated_at.replace('T', ' '))} · anchor ${dmy(sug.anchor)} · benchmark years ${p.years.join(', ')}</td></tr>
        </tbody></table></div>
        <div class="ov-card"><h3>Rules in force</h3><table><tbody>
          <tr><td>Season windows</td><td>in-season if a month's index ≥ ${p.in_season_index}, off-season if ≤ ${p.off_season_index}, else normal</td></tr>
          <tr><td>Window judged</td><td>the latest run of one window type, ≥ ${p.min_window_days} and ≤ ${p.max_window_days} days; the store must trade on ≥ ${pct(p.coverage)} of its festival-free days, and a benchmark year counts only if the store had been open ≥ 12 months before it began (no launch surges)</td></tr>
          <tr><td>Delist</td><td>≤ ${pct(p.delist_ratio)} of its own same-dates benchmark and ≤ ${pct(p.delist_relative)} of its peers' change; benchmark ≥ ₹${fmtN(p.min_benchmark_monthly)}/month; ≥ ${p.min_peers} peers in the cluster, else all stores</td></tr>
          <tr><td>Held</td><td>an off-season read when the in-season starts within ${p.relist_lookahead_days} days</td></tr>
          <tr><td>Relist</td><td>≥ ${pct(p.relist_vs_peers)} of its cluster peers' median the last time it sold in that window; expected ≥ ₹${fmtN(p.min_relist_value)}</td></tr>
        </tbody></table></div>
        <div class="ov-card"><h3>Check: day-wise vs month-wise export <span class="hint">${bad.length ? `${bad.length} month(s) differ by > 0.5%` : 'all complete months within 0.5%'}</span></h3>
          <div class="tbl-wrap short"><table><thead><tr><th>Month</th><th class="num">Day-wise</th><th class="num">Month-wise</th><th class="num">Difference</th></tr></thead><tbody>${recon}</tbody></table></div></div>
        <div class="ov-card"><h3>Season windows by category <span class="hint">festival-free index vs the category's yearly average</span></h3>
          <div class="tbl-wrap"><table><thead><tr><th>Category</th>${MON.map(m => `<th class="num">${m}</th>`).join('')}</tr></thead><tbody>${catRows}</tbody></table></div>
          <div class="ov-legend">${['in', 'normal', 'off'].map(t => `<span>${wchip(t)}</span>`).join('')}</div></div>
      </div>`;
    },
    results() {
      const rows = win.festivals.filter(f => (!ST.data.cl || f.cluster === ST.data.cl) && (!ST.data.year || String(f.year) === ST.data.year))
        .sort((a, b) => a.from.localeCompare(b.from) || a.cluster.localeCompare(b.cluster));
      $('#res').innerHTML = `<p class="count">${fmtN(rows.length)} festival windows — these days are removed from every season benchmark and suggestion for stores in that cluster.</p>
        <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Cluster</th><th>Festival</th><th>Date</th><th>Window removed</th><th class="num">Pre / Core / Post</th><th>Date source</th></tr></thead><tbody>${
        rows.slice(0, 600).map(f => `<tr><td>${esc(f.cluster)}</td><td>${esc(f.festival)}</td><td>${dmy(f.date)}</td><td>${span(f.from, f.to)}</td>
          <td class="num">${f.pre} / ${f.core} / ${f.post}</td><td class="muted">${esc(f.date_source)}</td></tr>`).join('')}</tbody></table></div>`;
    },
  },
};

// ---------------------------------------------------------------- grid (By Department / By Store)

function gridView(kind) {
  return {
    controls() {
      const s = ST.grid, pick = kind === 'dept' ? s.dept : s.store;
      const clusters = [...new Set(Object.values(storeMeta).map(m => m.cluster).filter(Boolean))].sort();
      view.innerHTML = `<section class="bar">
          <input list="${kind}-list" data-f="grid.${kind}" value="${esc(pick)}" placeholder="Type a ${kind === 'dept' ? 'department' : 'store'}…" aria-label="${kind === 'dept' ? 'Department' : 'Store'}">
          <input data-f="grid.q" value="${esc(s.q)}" placeholder="Filter rows…" aria-label="Filter rows">
          ${kind === 'dept' ? `<select data-f="grid.cl" aria-label="Cluster">${options(clusters, s.cl, 'All clusters')}</select>`
            : `<select data-f="grid.div" aria-label="Division">${options(DIVISIONS, s.div, 'All divisions')}</select><select data-f="grid.cat" aria-label="Season category">${catOptions(s.cat)}</select>`}
          <select data-f="grid.order" aria-label="Order"><option value="total" ${s.order === 'total' ? 'selected' : ''}>Biggest last 12 months first</option>
            <option value="latest" ${s.order === 'latest' ? 'selected' : ''}>Biggest latest month first</option><option value="name" ${s.order === 'name' ? 'selected' : ''}>A–Z</option></select>
          <select data-f="grid.show" aria-label="Cells"><option value="values" ${s.show === 'values' ? 'selected' : ''}>Show ₹ in cells</option><option value="heat" ${s.show === 'heat' ? 'selected' : ''}>Shading only</option></select>
        </section>
        <p class="rule">Cell shade = sales relative to that row's best month · bottom border = listing
          <span class="chip y">&nbsp;</span>listed <span class="chip n">&nbsp;</span>unlisted <span class="chip dot">&nbsp;</span>no record ·
          top border = season window ${wchip('in')} ${wchip('normal')} ${wchip('off')} · badges show a current suggestion. Click a row for its trend and the reasons.</p>
        <div id="res"></div>`;
    },
    results() {
      const s = ST.grid, pick = (kind === 'dept' ? s.dept : s.store).trim().toUpperCase();
      const ok = kind === 'dept' ? kb.departments.includes(pick) : !!kb.data[pick];
      if (!ok) { $('#res').innerHTML = `<p class="ov-empty">${pick ? `No ${kind === 'dept' ? 'department' : 'store'} called “${esc(pick)}”.` : `Type a ${kind === 'dept' ? 'department' : 'store'} above.`}</p>`; return; }
      const li = latestCompleteIdx(), M = kb.months, q = s.q.trim().toUpperCase();
      let rows = (kind === 'dept' ? kb.stores.filter(st => kb.data[st]?.[pick]).map(st => [st, pick]) : Object.keys(kb.data[pick]).map(d => [pick, d]))
        .filter(([st, d]) => (!q || (kind === 'dept' ? storeLabel(st) : d).toUpperCase().includes(q))
          && (kind !== 'dept' || !s.cl || storeMeta[st]?.cluster === s.cl)
          && (kind !== 'store' || ((!s.div || divisionOf(d) === s.div) && (!s.cat || catOf(d) === s.cat))))
        .map(([st, d]) => {
          const vals = M.map(m => sale(st, d, m));
          return { st, d, flags: kb.data[st][d], vals, total: vals.slice(Math.max(0, li - 11), li + 1).reduce((a, v) => a + v, 0), latest: vals[li] };
        });
      rows.sort((a, b) => s.order === 'name' ? (kind === 'dept' ? a.st.localeCompare(b.st) : a.d.localeCompare(b.d)) : (b[s.order] - a[s.order]));
      const listed = rows.filter(r => r.flags[li] === 'Y').length, tot = rows.reduce((a, r) => a + r.total, 0);
      const head = M.map(m => `<th class="${kind === 'dept' ? `wt-${typeOf(pick, m)}` : ''}">${esc(m.replace('(Till Date)', '*'))}</th>`).join('');
      const body = rows.map(r => {
        const max = Math.max(0, ...r.vals);
        const cells = r.vals.map((v, i) => {
          const f = r.flags[i], cls = f === 'Y' ? 'y' : f === 'N' ? 'n' : 'dot', a = max > 0 ? v / max : 0;
          const bg = v > 0 ? `background:rgba(var(--st-accent-rgb,79,122,102),${(0.08 + 0.6 * a).toFixed(2)})` : '';
          return `<td class="cell ${cls} wt-${typeOf(r.d, M[i])}" style="${bg}" title="${esc(`${M[i]} · ${f === 'Y' ? 'listed' : f === 'N' ? 'unlisted' : 'no listing record'} · ${fmtR(v)} · ${WLABEL[typeOf(r.d, M[i])]}`)}">${s.show === 'values' ? compact(v) : ''}</td>`;
        }).join('');
        const label = kind === 'dept' ? `${esc(r.st)} <span class="sub">${esc(storeMeta[r.st]?.cluster || '')}</span>` : `${esc(r.d)} <span class="sub">${esc(catLabel(r.d))}</span>`;
        return `<tr class="drillable" tabindex="0" data-store="${esc(r.st)}" data-dept="${esc(r.d)}"><td class="row-label">${label}${sugBadge(r.st, r.d)}</td>
          <td class="num tot">${fmtR(r.total)}</td>${cells}</tr>`;
      }).join('');
      $('#res').innerHTML = `<p class="count">${kind === 'dept' ? `${esc(pick)} · ${esc(divisionOf(pick))} · ${esc(catLabel(pick))}` : esc(storeLabel(pick))} —
          ${fmtN(rows.length)} rows · ${fmtN(listed)} listed in ${esc(M[li])} · ${fmtR(tot)} in the last 12 complete months</p>
        <div class="tbl-wrap grid-wrap"><table class="grid"><thead><tr><th class="row-label">${kind === 'dept' ? 'Store' : 'Department'}</th><th class="num">Last 12 mo</th>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
    },
  };
}

// ---------------------------------------------------------------- events: filter + export

function filteredEvents() {
  const s = ST.ev, q = s.q.trim().toUpperCase();
  return events().filter(e => (s.zero || realEvent(e)) && (s.type === 'all' || e.toStatus === s.type) && (!s.div || e.div === s.div)
    && (!s.win || e.win === s.win) && (!q || e.store.includes(q) || e.dept.toUpperCase().includes(q)));
}
function exportEvents() {
  downloadCsv('listing change events.csv', ['Store', 'Department', 'Division', 'Change', 'From month', 'To month', 'Window', 'Sales month before', 'Sales month of change'],
    sortRows(filteredEvents(), ST.ev.sort, (e, k) => e[k]).map(e => [e.store, e.dept, e.div, e.toStatus === 'N' ? 'Delisted' : 'Relisted', e.fromMonth, e.toMonth, WLABEL[e.win], Math.round(e.before), Math.round(e.after)]));
}
function exportSuggestions() {
  const k = ST.sug.kind, rows = sug[k];
  if (k === 'relist') {
    downloadCsv('relist suggestions.csv', ['Store', 'Department', 'Division', 'Season category', 'Cluster', 'Window', 'From', 'To', 'Festival-free days', 'Evidence year', 'Evidence from', 'Evidence to', 'Evidence days', 'Evidence sales', 'Own rate/day', 'Peers', 'Peer basis', 'Peer median rate/day', 'vs peers', 'Expected festival-free', 'Expected festival', 'Expected total', 'Last listed'],
      rows.map(r => [r.store, r.dept, divisionOf(r.dept), r.category, r.cluster, r.target.type, r.target.from, r.target.to, r.target.festival_free_days, r.evidence.year, r.evidence.from, r.evidence.to, r.evidence.days, r.evidence.sales, r.evidence.rate, r.peers.stores, r.peers.basis, r.peers.median_rate, r.vs_peers, r.expected_festival_free, r.expected_festival, r.expected_sales, r.last_listed]));
  } else {
    downloadCsv(`${k} suggestions.csv`, ['Store', 'Department', 'Division', 'Season category', 'Cluster', 'Window', 'From', 'To', 'Days', 'Sales', 'Rate/day', 'Benchmark years', 'Benchmark days', 'Benchmark sales', 'Benchmark rate/day', 'Own vs before', 'Peers', 'Peer basis', 'Peers vs before', 'Relative', 'Shortfall/month', 'Severity', 'Next window', 'Next from'],
      rows.map(r => [r.store, r.dept, divisionOf(r.dept), r.category, r.cluster, r.window.type, r.window.from, r.window.to, r.window.days, r.window.sales, r.window.rate, r.benchmark.years.map(y => `${y.year} (${y.from}..${y.to}, ${y.days}d, ${y.sales})`).join('; '), r.benchmark.days, r.benchmark.sales, r.benchmark.rate, r.ratio, r.peers.stores, r.peers.basis, r.peers.ratio, r.relative, r.shortfall_month, r.tier, r.next_window.type, r.next_window.from]));
  }
}

// ---------------------------------------------------------------- drill-down: trend + why

const modal = $('#drill-modal');
$('#drill-close').addEventListener('click', () => { modal.hidden = true; });
modal.addEventListener('click', e => { if (e.target === modal) modal.hidden = true; });
document.addEventListener('keydown', e => { if (e.key === 'Escape') modal.hidden = true; });

function openDrill(store, dept) {
  const h = kb.data[store]?.[dept] || '';
  $('#drill-title').textContent = `${store} — ${dept}`;
  $('#drill-sub').textContent = [storeLine(store), `${divisionOf(dept)} · ${catLabel(dept)} season category`].filter(Boolean).join(' · ');
  const pts = kb.months.map((m, i) => ({ m, f: h[i] || '.', v: sale(store, dept, m), t: typeOf(dept, m) }));
  const x = sugIndex.get(`${store}|${dept}`);
  $('#drill-body').innerHTML = trendSvg(pts) + `<div class="ov-legend">${['in', 'normal', 'off'].map(t => `<span>${wchip(t)}</span>`).join('')}
      <span><i style="background:var(--y)"></i>listed</span><span><i style="background:var(--n)"></i>unlisted</span><span><i style="background:var(--dot)"></i>no record</span></div>` +
    (x ? why(x.kind, x.r) : `<p class="why muted">No current suggestion for this store × department.</p>`);
  modal.hidden = false;
}

function festivalsIn(cluster, a, b) {
  return win.festivals.filter(f => (cluster === 'ALL' || f.cluster === cluster) && f.to >= a && f.from <= b)
    .reduce((acc, f) => { const k = `${f.festival} ${f.year}`; if (!acc.some(x => x.k === k)) acc.push({ k, f }); return acc; }, []).map(x => x.f);
}
function festList(cluster, a, b) {
  const fs = festivalsIn(cluster, a, b);
  return fs.length ? fs.map(f => `${esc(f.festival)} ${span(f.from, f.to)}`).join(' · ') : 'none';
}
function why(kind, r) {
  const src = sug.sources.daily;
  const foot = `<p class="src">Source: day-wise export <code>${esc(src.source_file)}</code> (${esc(src.date_min)} – ${esc(src.date_max)}), festival windows from the Calendar app (cluster ${esc(r.cluster === 'ALL' ? 'none mapped — every cluster’s festivals removed' : r.cluster)}), listing from kb.json. Rates = SL_V per festival-free trading store-day.</p>`;
  if (kind === 'relist') {
    const e = r.evidence;
    return `<div class="why"><h3>Why relist <span class="sug-badge sug-relist">Relist</span></h3><ol>
      <li>Delisted now (last listed <b>${esc(r.last_listed)}</b>). Its department's ${wchip(r.target.type)} window runs <b>${span(r.target.from, r.target.to)}</b>.</li>
      <li>The last time it sold in that window — <b>${span(e.from, e.to)}</b> — it made <b>${fmtR(e.sales)}</b> over <b>${e.days}</b> festival-free trading days = <b>${fmtRate(e.rate)}</b>.</li>
      <li>Its cluster peers' median over the same dates: <b>${fmtRate(r.peers.median_rate)}</b> (${r.peers.stores} stores, ${esc(r.peers.basis)}) → it sold at <b>${pct(r.vs_peers)}</b> of that.</li>
      <li>Expected in the coming window: ${r.target.festival_free_days} festival-free days × ${fmtRate(e.rate)} = <b>${fmtR(r.expected_festival_free)}</b>${r.festival_days.length ? ` + festival days (${r.festival_days.map(f => `${esc(f.festival)} ${f.days}d at ${f.lift}×`).join(', ')}) = <b>${fmtR(r.expected_festival)}</b>` : ''} → <b>${fmtR(r.expected_sales)}</b>.</li>
      <li>Festival days left out of the evidence: ${festList(r.cluster, e.from, e.to)}.</li></ol>${foot}</div>`;
  }
  const w = r.window, b = r.benchmark;
  return `<div class="why"><h3>Why ${kind === 'held' ? 'held' : 'delist'} <span class="sug-badge sug-${kind}">${KIND[kind]}</span> ${tierBadge(r.tier)}</h3><ol>
    <li>Window judged: ${wchip(w.type)} <b>${span(w.from, w.to)}</b> — <b>${fmtR(w.sales)}</b> over <b>${w.days}</b> festival-free trading days = <b>${fmtRate(w.rate)}</b>.</li>
    <li>Same dates in the years it was on the floor:<table class="mini"><thead><tr><th>Year</th><th>Dates</th><th class="num">Trading days</th><th class="num">Sales</th><th class="num">Rate</th></tr></thead><tbody>${
      b.years.map(y => `<tr><td>${y.year}</td><td>${span(y.from, y.to)}</td><td class="num">${y.days}</td><td class="num">${fmtR(y.sales)}</td><td class="num">${fmtRate(y.sales / y.days)}</td></tr>`).join('')}
      <tr class="tot"><td colspan="2">Benchmark</td><td class="num">${b.days}</td><td class="num">${fmtR(b.sales)}</td><td class="num">${fmtRate(b.rate)}</td></tr></tbody></table></li>
    <li>Own: ${fmtRate(w.rate)} ÷ ${fmtRate(b.rate)} = <b>${pct(r.ratio)}</b> of its benchmark (rule: ≤ ${pct(sug.params.delist_ratio)}).</li>
    <li>Peers — the same department in ${r.peers.stores} other stores (${esc(r.peers.basis)}), same dates: <b>${pct(r.peers.ratio)}</b> of their benchmark. So this store did <b>${pct(r.relative)}</b> as well as its peers (rule: ≤ ${pct(sug.params.delist_relative)}) — a store-specific fall, not a department or regional one.</li>
    <li>Shortfall vs its own benchmark: (${fmtRate(b.rate)} − ${fmtRate(w.rate)}) × 30 = <b>${fmtR(r.shortfall_month)}/month</b>.</li>
    <li>Festival days left out of the window: ${festList(r.cluster, w.from, w.to)}.</li>
    ${kind === 'held' ? `<li><b>Held:</b> this is an off-season read and the department's ${wchip(r.next_window.type)} starts <b>${dmy(r.next_window.from)}</b> — review once the season runs.</li>`
      : `<li>Next window: ${wchip(r.next_window.type)} from ${dmy(r.next_window.from)}.</li>`}</ol>${foot}</div>`;
}

// ---------------------------------------------------------------- charts (inline SVG)

function trendSvg(pts) {
  const W = 900, H = 250, pl = 60, pr = 16, pt = 14, pb = 56, n = pts.length;
  const max = Math.max(1, ...pts.map(p => p.v)), step = (W - pl - pr) / n;
  const x = i => pl + (i + 0.5) * step, y = v => pt + (H - pt - pb) * (1 - v / max);
  const band = pts.map((p, i) => `<rect x="${pl + i * step}" y="${pt}" width="${step}" height="${H - pt - pb}" class="band-${p.t}"/>`).join('');
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join(' ');
  const col = { Y: 'var(--y)', N: 'var(--n)', '.': 'var(--dot)' };
  const dots = pts.map((p, i) => `<circle cx="${x(i).toFixed(1)}" cy="${y(p.v).toFixed(1)}" r="4" fill="${col[p.f] || col['.']}" stroke="#fff"><title>${esc(p.m)} · ${fmtR(p.v)} · ${p.f === 'Y' ? 'listed' : p.f === 'N' ? 'unlisted' : 'no record'} · ${WLABEL[p.t]}</title></circle>`).join('');
  const ticks = [0, 0.5, 1].map(f => `<line x1="${pl}" x2="${W - pr}" y1="${y(max * f)}" y2="${y(max * f)}" stroke="var(--line)"/><text x="${pl - 6}" y="${y(max * f)}" text-anchor="end" dominant-baseline="middle" font-size="10" fill="var(--color-muted-foreground)">${fmtR(max * f)}</text>`).join('');
  const labels = pts.map((p, i) => `<text x="${x(i)}" y="${H - pb + 12}" font-size="9" fill="var(--color-muted-foreground)" text-anchor="end" transform="rotate(-55 ${x(i)},${H - pb + 12})">${esc(p.m.replace('(Till Date)', '*'))}</text>`).join('');
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Monthly sales with listing status and season windows">${band}${ticks}<path d="${line}" fill="none" stroke="var(--color-primary)" stroke-width="2"/>${dots}${labels}</svg>`;
}

function seasonSvg(d) {
  const W = 900, H = 240, pl = 64, pr = 16, pt = 14, pb = 28, step = (W - pl - pr) / 12;
  const max = Math.max(1, ...d.months.map(m => m.rate)), y = v => pt + (H - pt - pb) * (1 - v / max);
  const bars = d.months.map((m, i) => `<rect x="${pl + i * step + step * 0.18}" y="${y(m.rate)}" width="${step * 0.64}" height="${H - pb - y(m.rate)}" class="bar-${m.type}"><title>${m.month} · ${fmtRate(m.rate)} · ${WLABEL[m.type]} · ${pct(m.vs_window)} of its window</title></rect>`).join('');
  const bench = d.months.map((m, i) => { const w = d.windows[m.type]; return w ? `<line x1="${pl + i * step}" x2="${pl + (i + 1) * step}" y1="${y(w.rate)}" y2="${y(w.rate)}" stroke="var(--ink)" stroke-dasharray="4 3" opacity=".6"/>` : ''; }).join('');
  const labels = d.months.map((m, i) => `<text x="${pl + (i + 0.5) * step}" y="${H - 8}" font-size="11" text-anchor="middle" fill="var(--color-muted-foreground)">${m.month}</text>`).join('');
  const ticks = [0, 0.5, 1].map(f => `<line x1="${pl}" x2="${W - pr}" y1="${y(max * f)}" y2="${y(max * f)}" stroke="var(--line)"/><text x="${pl - 6}" y="${y(max * f)}" text-anchor="end" dominant-baseline="middle" font-size="10" fill="var(--color-muted-foreground)">${fmtR(max * f)}</text>`).join('');
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Festival-free sales per store-day by month">${ticks}${bars}${bench}${labels}</svg>`;
}

function listingSvg(listed, del, rel, li) {
  const W = 1000, H = 190, pl = 46, pr = 40, pt = 10, pb = 34, n = kb.months.length;
  const x = i => pl + (i + 0.5) * ((W - pl - pr) / n), bw = Math.max(2, (W - pl - pr) / n / 3);
  const maxL = Math.max(1, ...listed), maxE = Math.max(1, ...del, ...rel);
  const yL = v => pt + (H - pt - pb) * (1 - v / maxL), yE = v => pt + (H - pt - pb) * (1 - v / maxE), base = H - pb;
  const bars = kb.months.map((m, i) => `<rect x="${x(i) - bw}" y="${yE(del[i])}" width="${bw}" height="${base - yE(del[i])}" fill="var(--n)" opacity=".75"><title>${esc(m)}: ${del[i]} delisted</title></rect>` +
    `<rect x="${x(i)}" y="${yE(rel[i])}" width="${bw}" height="${base - yE(rel[i])}" fill="var(--y)" opacity=".75"><title>${esc(m)}: ${rel[i]} relisted</title></rect>`).join('');
  const line = listed.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${yL(v).toFixed(1)}`).join(' ');
  const dots = listed.map((v, i) => `<circle cx="${x(i)}" cy="${yL(v)}" r="${i === li ? 4 : 2}" fill="var(--color-primary)"><title>${esc(kb.months[i])}: ${fmtN(v)} listed</title></circle>`).join('');
  const labels = kb.months.map((m, i) => (i % 3 === 0 || i === n - 1) ? `<text x="${x(i)}" y="${H - 12}" text-anchor="middle" font-size="10" fill="var(--color-muted-foreground)">${esc(m.replace('(Till Date)', '*'))}</text>` : '').join('');
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Listed combos per month with delists and relists">
    <text x="${pl - 6}" y="${pt + 8}" text-anchor="end" font-size="10" fill="var(--color-muted-foreground)">${fmtN(maxL)}</text>
    <text x="${W - pr + 6}" y="${pt + 8}" font-size="10" fill="var(--color-muted-foreground)">${fmtN(maxE)}</text>
    <line x1="${pl}" x2="${W - pr}" y1="${base}" y2="${base}" stroke="var(--line)"/>${bars}<path d="${line}" fill="none" stroke="var(--color-primary)" stroke-width="2"/>${dots}${labels}</svg>`;
}
