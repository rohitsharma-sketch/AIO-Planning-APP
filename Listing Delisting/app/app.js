// Reads app/kb.json (listing history), app/sales.json (SL_V by store/department/month), and
// app/risk.json (delisting-risk scores, built by scripts/build_risk_scores.py), and renders
// one of three views: by-department heatmap, by-store heatmap, or a risk-ranked list. Each
// heatmap cell's fill shade = relative sales value (darker = higher, within the rendered
// rows); each cell's bottom border tags listing status (green = listed, red = unlisted,
// gray = no data). Clicking any row opens a single store×department trendline drill-down
// (native SVG, no charting lib). See PRD_LOGIC.md for all three schemas.

let kb = null;
let sales = null;
let risk = null;
let seasonality = null;

// --- Generic sortable-column-headers helper -----------------------------------------------
// Click a <th data-key="..."> to sort by that field; click again to flip direction. Wired into
// every list-style table (Change Events, Delisting Risk, Seasonality's two ranked tables) --
// not the two heatmap grids, whose columns are fixed calendar months, not sortable data series.

function makeSortState() { return { key: null, dir: 1 }; }

function sortRows(rows, state, keyFor) {
  if (!state.key) return rows;
  const sorted = rows.slice().sort((a, b) => {
    const va = keyFor(a, state.key), vb = keyFor(b, state.key);
    const cmp = typeof va === 'string' ? va.localeCompare(vb) : (va - vb);
    return cmp * state.dir;
  });
  return sorted;
}

function sortableTh(label, key, state, numeric = false) {
  const active = state.key === key;
  const arrow = active ? (state.dir === 1 ? ' ▲' : ' ▼') : '';
  const cls = 'sortable' + (numeric ? ' num' : '') + (active ? ' sorted' : '');
  return `<th data-key="${escapeAttr(key)}" class="${cls}">${escapeHtml(label)}${arrow}</th>`;
}

function wireSortableHeaders(tableEl, state, onSort) {
  tableEl.addEventListener('click', e => {
    const th = e.target.closest('th[data-key]');
    if (!th) return;
    const key = th.dataset.key;
    state.dir = state.key === key ? -state.dir : 1;
    state.key = key;
    onSort();
  });
}
let mode = 'by-dept';

const statusEl = document.getElementById('status');
const gridEl = document.getElementById('grid');
const deptInput = document.getElementById('dept-input');
const storeInput = document.getElementById('store-input');

Promise.all([
  fetch('kb.json').then(r => r.json()),
  fetch('sales.json').then(r => r.json()),
  fetch('risk.json').then(r => r.json()),
  fetch('seasonality.json').then(r => r.json()),
  fetch('stores.json').then(r => r.ok ? r.json() : {}).catch(() => ({})),
]).then(([kbData, salesData, riskData, seasonalityData, storesData]) => {
    storeMeta = storesData.stores || {};
    kb = kbData;
    sales = salesData;
    risk = riskData;
    seasonality = seasonalityData;
    document.getElementById('dept-list').innerHTML =
      kb.departments.map(d => `<option value="${escapeAttr(d)}">`).join('');
    document.getElementById('store-list').innerHTML =
      kb.stores.map(s => `<option value="${escapeAttr(s)}" label="${escapeAttr(storeLabel(s))}">`).join('');
    statusEl.textContent = `Loaded ${kb.stores.length} stores × ${kb.departments.length} departments × ${kb.months.length} months. Pick one above to render.`;

    selectedStores = setupMultiselect({
      toggleId: 'store-ms-toggle', panelId: 'store-ms-panel',
      options: kb.stores, label: 'stores', onChange: renderEvents,
    });
    selectedDepts = setupMultiselect({
      toggleId: 'dept-ms-toggle', panelId: 'dept-ms-panel',
      options: kb.departments, label: 'departments', onChange: renderEvents,
    });
    seasonDeptSelect = setupSingleSelect({
      toggleId: 'season-dept-toggle', panelId: 'season-dept-panel',
      options: kb.departments, placeholder: 'Pick a department…',
      onChange: renderSeasonality,
    });
  })
  .catch(err => {
    statusEl.textContent = 'Failed to load data: ' + err;
  });

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    mode = btn.dataset.mode;
    document.getElementById('dept-picker-wrap').hidden = mode !== 'by-dept';
    document.getElementById('store-picker-wrap').hidden = mode !== 'by-store';
    document.getElementById('grid-legend').hidden = mode !== 'by-dept' && mode !== 'by-store';
    document.getElementById('events-controls').hidden = mode !== 'events';
    document.getElementById('risk-controls').hidden = mode !== 'risk';
    document.getElementById('seasonality-controls').hidden = mode !== 'seasonality';
    document.getElementById('grid-hint').hidden = mode !== 'by-dept' && mode !== 'by-store';
    gridEl.hidden = mode !== 'by-dept' && mode !== 'by-store';
    eventsTableEl.hidden = mode !== 'events';
    document.getElementById('events-count').hidden = mode !== 'events';
    riskTableEl.hidden = mode !== 'risk';
    document.getElementById('risk-count').hidden = mode !== 'risk';
    document.getElementById('season-wrap').hidden = mode !== 'seasonality';
    if (mode === 'events') {
      statusEl.hidden = true;
      renderEvents();
    } else if (mode === 'risk') {
      statusEl.hidden = true;
      renderRisk();
    } else if (mode === 'seasonality') {
      statusEl.hidden = true;
      renderSeasonality(seasonDeptSelect.get());
    } else {
      gridEl.innerHTML = '';
      statusEl.textContent = 'Pick one above to render.';
      statusEl.hidden = false;
    }
  });
});

deptInput.addEventListener('change', () => renderByDept(deptInput.value));
storeInput.addEventListener('change', () => renderByStore(storeInput.value));
let seasonDeptSelect; // initialized once kb.departments is loaded, see Promise.all().then() below

function renderByDept(dept) {
  if (!kb || !kb.departments.includes(dept)) return;
  const rows = kb.stores
    .filter(store => kb.data[store] && kb.data[store][dept])
    .map(store => [store, dept, kb.data[store][dept], m => sales.data[store]?.[dept]?.[m]]);
  render(`Department: ${dept}`, rows, inSeasonBadge(dept, latestCompleteMonth()));
}

function renderByStore(store) {
  if (!kb || !kb.data[store]) return;
  const rows = Object.entries(kb.data[store])
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([dept, history]) => [store, dept, history, m => sales.data[store]?.[dept]?.[m]]);
  render(`Store: ${store}`, rows);
}

// Dynamic In-season / Off-season badge for a department, evaluated against ONE specific,
// contextually relevant month (2026-09-21 rework — replaces the static season_category badge
// everywhere it appeared). The static category (regular/summer/lt_winter/hvy_winter/prewinter/
// occasional) still drives the answer via a fixed calendar-month window per category (see
// IN_SEASON_WINDOWS below, mirrors scripts/build_risk_scores.py's Python version exactly) — it's
// just de-emphasized to the tooltip instead of being the primary label. One shared helper, called
// with the contextually right month in each of the 5 places it appears (By Department/By Store
// grids and the Seasonality tab use the latest-complete-month anchor; Change Events uses each
// row's own event month; Delisting Risk uses each row's own trend_through_month). See
// PRD_LOGIC.md for the exact windows and the business rationale.
const IN_SEASON_WINDOWS = {
  summer: new Set(['Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct']),
  prewinter: new Set(['Aug', 'Sep', 'Oct']),
  lt_winter: new Set(['Oct', 'Nov', 'Dec', 'Jan', 'Feb']),
  hvy_winter: new Set(['Oct', 'Nov', 'Dec', 'Jan', 'Feb']),
  // regular/occasional/missing category: no entry here = always in-season (see isInSeason).
};

function calMonth(monthLabel) {
  return monthLabel.slice(0, 3); // "Dec'25" / "Sep'26(Till Date)" -> "Dec" / "Sep"
}

// True (in-season) unless the department's season_category has a fixed window that excludes
// this calendar month. Missing/null category defaults to always-in-season, same as 'regular'.
function isInSeason(dept, monthLabel) {
  const cat = seasonality && seasonality.departments[dept] && seasonality.departments[dept].season_category;
  const window = IN_SEASON_WINDOWS[cat];
  return !window || window.has(calMonth(monthLabel));
}

// Latest COMPLETE month in kb.months (skips a trailing partial "(Till Date)" month) — the one
// consistent reference point for views that don't have a more specific month of their own
// (By Department/By Store grids, Seasonality tab), same anchor logic as build_risk_scores.py.
function latestCompleteMonth() {
  if (!kb) return null;
  const last = kb.months[kb.months.length - 1];
  return last.includes('(Till Date)') ? kb.months[kb.months.length - 2] : last;
}

function inSeasonBadge(dept, monthLabel) {
  if (!seasonality || !monthLabel) return '';
  const d = seasonality.departments[dept];
  const cat = (d && d.season_category) || 'unknown';
  const inSeason = isInSeason(dept, monthLabel);
  const cls = inSeason ? 'season-in' : 'season-off';
  const label = inSeason ? 'In season' : 'Off season';
  const tip = `${cat} — ${inSeason ? 'in season' : 'off season'} for ${monthLabel}`;
  return `<span class="season-badge ${cls}" title="${escapeAttr(tip)}">${escapeHtml(label)}</span>`;
}

// Low/Medium/High severity badge for a flagged risk combo — tertiles of the flagged score
// distribution itself, computed in build_risk_scores.py (see risk.json's params.risk_tier_cutoffs
// for the exact cutoffs used), not arbitrary round-number thresholds.
function riskBadge(tier) {
  const cls = 'risk-' + tier.toLowerCase();
  return `<span class="risk-badge ${cls}">${escapeHtml(tier)}</span>`;
}

function render(title, rows, titleBadge) {
  if (rows.length === 0) {
    statusEl.textContent = `${title}: no data.`;
    gridEl.innerHTML = '';
    return;
  }
  statusEl.hidden = true;

  // Per-row max sales value, so each row's shading reads relative to its own scale.
  const rowMaxes = rows.map(([, , history, getSale]) =>
    Math.max(0, ...[...history].map((_, i) => getSale(kb.months[i]) || 0)));

  const monthsHtml = kb.months.map(m => `<th>${m}</th>`).join('');
  const rowsHtml = rows.map(([store, dept, history, getSale], rowIdx) => {
    const rowLabel = mode === 'by-dept' ? store : dept;
    const rowBadge = mode === 'by-store' ? ' ' + inSeasonBadge(dept, latestCompleteMonth()) : '';
    const rowMax = rowMaxes[rowIdx];
    const cells = [...history].map((ch, i) => {
      const statusCls = ch === 'Y' ? 'y' : ch === 'N' ? 'n' : 'dot';
      const val = getSale(kb.months[i]) || 0;
      const alpha = rowMax > 0 ? Math.min(1, val / rowMax) : 0;
      const bg = val > 0 ? `background-color: rgba(var(--st-accent-rgb,79,122,102),${(0.12 + 0.75 * alpha).toFixed(2)});` : '';
      const tip = `${rowLabel} — ${kb.months[i]} — ${statusCls === 'y' ? 'Listed' : statusCls === 'n' ? 'Unlisted' : 'No listing data'}${val ? ', sales ' + val.toLocaleString('en-IN') : ''} (click row for trend)`;
      return `<td class="cell ${statusCls}" style="${bg}" title="${escapeAttr(tip)}"></td>`;
    }).join('');
    return `<tr data-store="${escapeAttr(store)}" data-dept="${escapeAttr(dept)}" class="drillable">` +
      `<td class="row-label" title="${escapeAttr(rowLabel)}">${escapeHtml(rowLabel)}${rowBadge}</td>${cells}</tr>`;
  }).join('');
  gridEl.innerHTML = `<thead><tr><th class="row-label">${escapeHtml(title)} ${titleBadge || ''}</th>${monthsHtml}</tr></thead><tbody>${rowsHtml}</tbody>`;
}

// --- Store×Dept trendline drill-down ---------------------------------------

gridEl.addEventListener('click', e => {
  const tr = e.target.closest('tr[data-store]');
  if (!tr) return;
  openDrilldown(tr.dataset.store, tr.dataset.dept);
});

const modalEl = document.getElementById('drill-modal');
const modalTitleEl = document.getElementById('drill-title');
const modalSubEl = document.getElementById('drill-sub');

// RS Planning store master (stores.json, built from the planning DB by the daily sync):
// cluster, LfL / Ramp / NSO class, opening date, status - one store vocabulary with AOP / BIS.
let storeMeta = {};
function storeLabel(s) {
  const m = storeMeta[s];
  return m ? [s, m.name !== s && m.name, m.cluster, m.type].filter(Boolean).join(' · ') : s;
}
function storeLine(s) {
  const m = storeMeta[s];
  if (!m) return '';
  return [m.name !== s && m.name, m.cluster && `Cluster ${m.cluster}`, m.type, m.opened && `opened ${m.opened}`, m.status]
    .filter(Boolean).join(' · ');
}
const modalChartEl = document.getElementById('drill-chart');

document.getElementById('drill-close').addEventListener('click', closeDrilldown);
modalEl.addEventListener('click', e => { if (e.target === modalEl) closeDrilldown(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDrilldown(); });

function closeDrilldown() { modalEl.hidden = true; }

function openDrilldown(store, dept) {
  const history = kb.data[store]?.[dept];
  if (!history) return;
  modalTitleEl.textContent = `${store} — ${dept}`;
  modalSubEl.textContent = storeLine(store);
  const points = [...history].map((ch, i) => ({
    month: kb.months[i],
    status: ch === 'Y' ? 'y' : ch === 'N' ? 'n' : 'dot',
    value: sales.data[store]?.[dept]?.[kb.months[i]] || 0,
  }));
  modalChartEl.innerHTML = trendSvg(points);
  modalEl.hidden = false;
}

function trendSvg(points) {
  const W = 900, H = 280, padL = 60, padR = 20, padT = 20, padB = 60;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const maxVal = Math.max(1, ...points.map(p => p.value));
  const x = i => padL + (points.length <= 1 ? 0 : i * plotW / (points.length - 1));
  const y = v => padT + plotH - (v / maxVal) * plotH;
  const statusColor = { y: 'var(--y)', n: 'var(--n)', dot: 'var(--dot)' };

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ');
  const areaPath = `${linePath} L${x(points.length - 1).toFixed(1)},${(padT + plotH).toFixed(1)} L${x(0).toFixed(1)},${(padT + plotH).toFixed(1)} Z`;

  const dots = points.map((p, i) => {
    const cx = x(i).toFixed(1), cy = y(p.value).toFixed(1);
    return `<circle cx="${cx}" cy="${cy}" r="4" fill="${statusColor[p.status]}" stroke="#fff" stroke-width="1">` +
      `<title>${escapeHtml(p.month)} — ${p.status === 'y' ? 'Listed' : p.status === 'n' ? 'Unlisted' : 'No listing data'} — sales ${p.value.toLocaleString('en-IN')}</title></circle>`;
  }).join('');

  const yTicks = [0, 0.5, 1].map(f => {
    const v = maxVal * f, yy = y(v).toFixed(1);
    return `<line x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}" stroke="var(--color-border)"/>` +
      `<text x="${padL - 8}" y="${yy}" text-anchor="end" dominant-baseline="middle" font-size="10" fill="var(--color-muted-foreground)">${Math.round(v).toLocaleString('en-IN')}</text>`;
  }).join('');

  const xLabels = points.map((p, i) =>
    `<text x="${x(i).toFixed(1)}" y="${H - padB + 14}" font-size="9" fill="var(--color-muted-foreground)" text-anchor="end" transform="rotate(-60 ${x(i).toFixed(1)},${H - padB + 14})">${escapeHtml(p.month)}</text>`
  ).join('');

  return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}">
    ${yTicks}
    <path d="${areaPath}" fill="rgba(var(--st-accent-rgb,79,122,102),0.12)" stroke="none"/>
    <path d="${linePath}" fill="none" stroke="var(--st-accent,#4F7A66)" stroke-width="2"/>
    ${dots}
    ${xLabels}
  </svg>`;
}

// --- Listing-change events list ---------------------------------------------
// Every Y<->N transition in the listing history (dot/no-data months are skipped on
// either side, so a coverage gap never counts as a "change"), paired with the sales
// value in the month before and the month the change took effect.

let allEvents = null;
const eventsTableEl = document.getElementById('events-table');
const eventsCountEl = document.getElementById('events-count');
const eventsTypeFilter = document.getElementById('events-type-filter');
const eventsSort = document.getElementById('events-sort');
const eventsSeasonFilter = document.getElementById('events-season-filter');
const eventsShowZeroImpact = document.getElementById('events-show-zero-impact');
[eventsTypeFilter, eventsSort, eventsSeasonFilter, eventsShowZeroImpact].forEach(el => el.addEventListener('input', renderEvents));

// Minimal multi-select: a toggle button that opens a searchable checkbox panel.
// No selection = no filter (matches everything), same as the old empty-text-input behavior.
function setupMultiselect({ toggleId, panelId, options, label, onChange }) {
  const toggle = document.getElementById(toggleId);
  const panel = document.getElementById(panelId);
  const search = panel.querySelector('.multiselect-search');
  const optionsEl = panel.querySelector('.multiselect-options');
  const selected = new Set();

  function renderOptions(filterText) {
    const q = filterText.trim().toUpperCase();
    const matches = options.filter(o => !q || o.toUpperCase().includes(q));
    optionsEl.innerHTML = matches.length === 0
      ? '<div class="no-match">No matches</div>'
      : matches.slice(0, 200).map(o =>
          `<label><input type="checkbox" value="${escapeAttr(o)}" ${selected.has(o) ? 'checked' : ''}> ${escapeHtml(o)}</label>`
        ).join('');
  }

  function updateToggleLabel() {
    toggle.textContent = selected.size === 0 ? `All ${label}` : `${selected.size} ${label} selected`;
    toggle.classList.toggle('has-selection', selected.size > 0);
  }

  toggle.addEventListener('click', () => {
    const willOpen = panel.hidden;
    document.querySelectorAll('.multiselect-panel').forEach(p => { p.hidden = true; });
    panel.hidden = !willOpen;
    if (willOpen) { search.value = ''; renderOptions(''); search.focus(); }
  });
  search.addEventListener('input', () => renderOptions(search.value));
  optionsEl.addEventListener('change', e => {
    if (e.target.type !== 'checkbox') return;
    e.target.checked ? selected.add(e.target.value) : selected.delete(e.target.value);
    updateToggleLabel();
    onChange();
  });
  document.addEventListener('click', e => {
    if (!panel.hidden && !e.target.closest(`#${toggleId}, #${panelId}`)) panel.hidden = true;
  });

  renderOptions('');
  return selected;
}

// Single-select variant of the same widget: same searchable panel look, but clicking an option
// immediately picks it and closes the panel (no checkboxes, no accumulating multiple picks) --
// for pickers like Seasonality's department selector, which show one entity's detail view, not
// a filterable list of many rows.
function setupSingleSelect({ toggleId, panelId, options, placeholder, onChange }) {
  const toggle = document.getElementById(toggleId);
  const panel = document.getElementById(panelId);
  const search = panel.querySelector('.multiselect-search');
  const optionsEl = panel.querySelector('.multiselect-options');
  let selected = null;

  function renderOptions(filterText) {
    const q = filterText.trim().toUpperCase();
    const matches = options.filter(o => !q || o.toUpperCase().includes(q));
    optionsEl.innerHTML = matches.length === 0
      ? '<div class="no-match">No matches</div>'
      : matches.slice(0, 200).map(o =>
          `<div class="option${o === selected ? ' selected' : ''}" data-value="${escapeAttr(o)}">${escapeHtml(o)}</div>`
        ).join('');
  }

  function updateToggleLabel() {
    toggle.textContent = selected || placeholder;
    toggle.classList.toggle('has-selection', !!selected);
  }

  toggle.addEventListener('click', () => {
    const willOpen = panel.hidden;
    document.querySelectorAll('.multiselect-panel').forEach(p => { p.hidden = true; });
    panel.hidden = !willOpen;
    if (willOpen) { search.value = ''; renderOptions(''); search.focus(); }
  });
  search.addEventListener('input', () => renderOptions(search.value));
  optionsEl.addEventListener('click', e => {
    const opt = e.target.closest('.option');
    if (!opt) return;
    // The whole widget sits inside a bare <label> with no `for` -- per spec its implicit
    // associated control is the first labelable descendant (the toggle button). A plain <div>
    // has no native click action, so without this the browser ALSO synthesizes a click on that
    // button right after this one, immediately reopening/re-toggling the panel we just closed.
    e.preventDefault();
    selected = opt.dataset.value;
    updateToggleLabel();
    panel.hidden = true;
    onChange(selected);
  });
  document.addEventListener('click', e => {
    if (!panel.hidden && !e.target.closest(`#${toggleId}, #${panelId}`)) panel.hidden = true;
  });

  renderOptions('');
  updateToggleLabel();
  return { get: () => selected };
}

let selectedStores, selectedDepts;

function computeEvents() {
  const events = [];
  for (const store of kb.stores) {
    const depts = kb.data[store];
    if (!depts) continue;
    for (const dept in depts) {
      const hist = depts[dept];
      let prevIdx = -1, prevCh = null;
      for (let i = 0; i < hist.length; i++) {
        const ch = hist[i];
        if (ch === '.') continue;
        if (prevCh !== null && ch !== prevCh) {
          const salesBefore = sales.data[store]?.[dept]?.[kb.months[prevIdx]] || 0;
          const salesAfter = sales.data[store]?.[dept]?.[kb.months[i]] || 0;
          events.push({
            store, dept, monthIdx: i,
            fromMonth: kb.months[prevIdx], toMonth: kb.months[i],
            toStatus: ch, salesBefore, salesAfter, impact: Math.abs(salesAfter - salesBefore),
          });
        }
        prevCh = ch; prevIdx = i;
      }
    }
  }
  return events;
}

function renderEvents() {
  if (!kb || !sales) { eventsCountEl.hidden = false; eventsCountEl.textContent = 'Loading…'; return; }
  if (!allEvents) allEvents = computeEvents();

  const typeQ = eventsTypeFilter.value;
  const seasonQ = eventsSeasonFilter.value;

  let rows = allEvents.filter(e =>
    (selectedStores.size === 0 || selectedStores.has(e.store)) &&
    (selectedDepts.size === 0 || selectedDepts.has(e.dept)) &&
    (typeQ === 'all' || e.toStatus === typeQ) &&
    (seasonQ === 'all' || (seasonQ === 'in') === isInSeason(e.dept, e.toMonth)));

  // Zero-impact events (₹0 sales both before and after the status flip) are hidden by default -
  // they're a listing-flag change with no corresponding sales activity, usually just noise in
  // the source master data rather than a real merchandising event. Hidden count is still
  // reported below so this is transparent, not a silent drop.
  const zeroImpactCount = rows.filter(e => e.salesBefore === 0 && e.salesAfter === 0).length;
  if (!eventsShowZeroImpact.checked) {
    rows = rows.filter(e => !(e.salesBefore === 0 && e.salesAfter === 0));
  }

  rows = eventsSortState.key
    ? sortRows(rows, eventsSortState, (e, k) => e[k])
    : rows.slice().sort((a, b) =>
        eventsSort.value === 'impact' ? b.impact - a.impact : b.monthIdx - a.monthIdx);

  const CAP = 300;
  const shown = rows.slice(0, CAP);
  const hiddenNote = !eventsShowZeroImpact.checked && zeroImpactCount > 0
    ? ` (${zeroImpactCount} zero-impact event${zeroImpactCount === 1 ? '' : 's'} hidden — check the box above to see them.)`
    : '';
  eventsCountEl.hidden = false;
  eventsCountEl.textContent = (rows.length > CAP
    ? `Showing top ${CAP} of ${rows.length} matching events — narrow the filters to see others.`
    : `${rows.length} matching event${rows.length === 1 ? '' : 's'}.`) + hiddenNote;

  const rowsHtml = shown.map(e => {
    const changeLabel = e.toStatus === 'N' ? 'Delisted' : 'Relisted';
    const changeCls = e.toStatus === 'N' ? 'n' : 'y';
    return `<tr data-store="${escapeAttr(e.store)}" data-dept="${escapeAttr(e.dept)}" class="drillable">
      <td>${escapeHtml(e.store)}</td>
      <td>${escapeHtml(e.dept)} ${inSeasonBadge(e.dept, e.toMonth)}</td>
      <td><span class="chip ${changeCls}">&nbsp;</span> ${changeLabel}</td>
      <td>${escapeHtml(e.fromMonth)} &rarr; ${escapeHtml(e.toMonth)}</td>
      <td class="num">${e.salesBefore.toLocaleString('en-IN')}</td>
      <td class="num">${e.salesAfter.toLocaleString('en-IN')}</td>
    </tr>`;
  }).join('');

  eventsTableEl.innerHTML = `<thead><tr>
    ${sortableTh('Store', 'store', eventsSortState)}
    ${sortableTh('Department', 'dept', eventsSortState)}
    ${sortableTh('Change', 'toStatus', eventsSortState)}
    ${sortableTh('Month', 'monthIdx', eventsSortState, true)}
    ${sortableTh('Sales before', 'salesBefore', eventsSortState, true)}
    ${sortableTh('Sales after', 'salesAfter', eventsSortState, true)}
  </tr></thead><tbody>${rowsHtml}</tbody>`;
}

const eventsSortState = makeSortState();
wireSortableHeaders(eventsTableEl, eventsSortState, renderEvents);

eventsTableEl.addEventListener('click', e => {
  const tr = e.target.closest('tr[data-store]');
  if (!tr) return;
  openDrilldown(tr.dataset.store, tr.dataset.dept);
});

// --- Delisting Risk list -----------------------------------------------------
// Ranked list from app/risk.json (built by scripts/build_risk_scores.py): store×dept combos
// still Listed today whose recent in-season months (of the last 3 complete months) have fallen
// 50%+ short of this combo's own prior in-season average — using FIXED calendar-month
// in-season windows per department season_category (2026-09-21 rework, replaces the earlier
// continuous seasonal-index method). An off-season dip produces no signal at all, by
// construction. See PRD_LOGIC.md for the exact rule and known limitations (small samples, the
// partial "till date" month, department-wide season_category applied per store).

const riskTableEl = document.getElementById('risk-table');
const riskCountEl = document.getElementById('risk-count');
const riskSearchEl = document.getElementById('risk-search');
const riskTierFilter = document.getElementById('risk-tier-filter');
riskSearchEl.addEventListener('input', renderRisk);
riskTierFilter.addEventListener('input', renderRisk);

const RISK_CAP = 300;

function renderRisk() {
  if (!risk) { riskCountEl.hidden = false; riskCountEl.textContent = 'Loading…'; return; }

  const q = riskSearchEl.value.trim().toUpperCase();
  const tierQ = riskTierFilter.value;
  let rows = q
    ? risk.flagged.filter(r => r.store.toUpperCase().includes(q) || r.dept.toUpperCase().includes(q))
    : risk.flagged;
  if (tierQ !== 'all') {
    rows = rows.filter(r => r.risk_tier === tierQ);
  }
  if (riskSortState.key) rows = sortRows(rows, riskSortState, (r, k) => r[k]);

  riskCountEl.hidden = false;
  riskCountEl.textContent = rows.length > RISK_CAP
    ? `Showing top ${RISK_CAP} of ${rows.length} at-risk combos (by risk score) — narrow the search to see others. ${risk.flagged_count} flagged out of ${risk.scored_count} currently-Listed combos evaluated.`
    : `${rows.length} at-risk combo${rows.length === 1 ? '' : 's'}. ${risk.flagged_count} flagged out of ${risk.scored_count} currently-Listed combos evaluated.`;

  const shown = rows.slice(0, RISK_CAP);
  const rowsHtml = shown.map(r => `<tr data-store="${escapeAttr(r.store)}" data-dept="${escapeAttr(r.dept)}" class="drillable">
    <td>${escapeHtml(r.store)}</td>
    <td>${escapeHtml(r.dept)}</td>
    <td class="num">${(r.risk_score * 100).toFixed(0)}% ${riskBadge(r.risk_tier)}</td>
    <td>${escapeHtml(r.reason)}</td>
    <td class="num">${r.baseline_avg.toLocaleString('en-IN')} &rarr; ${r.recent_avg.toLocaleString('en-IN')}</td>
    <td class="num">${r.history_months_used} in-season mo (through ${escapeHtml(r.trend_through_month)})</td>
  </tr>`).join('');

  riskTableEl.innerHTML = `<thead><tr>
    ${sortableTh('Store', 'store', riskSortState)}
    ${sortableTh('Department', 'dept', riskSortState)}
    ${sortableTh('Risk', 'risk_score', riskSortState, true)}
    ${sortableTh('Reason', 'reason', riskSortState)}
    ${sortableTh('Prior in-season avg → recent avg sales', 'recent_avg', riskSortState, true)}
    ${sortableTh('In-season history used', 'history_months_used', riskSortState, true)}
  </tr></thead><tbody>${rowsHtml}</tbody>`;
}

const riskSortState = makeSortState();
wireSortableHeaders(riskTableEl, riskSortState, renderRisk);

riskTableEl.addEventListener('click', e => {
  const tr = e.target.closest('tr[data-store]');
  if (!tr) return;
  openDrilldown(tr.dataset.store, tr.dataset.dept);
});

// --- Seasonality (calendar-month aggregated across years) -------------------
// From app/seasonality.json (built by scripts/build_seasonality.py): per department, average
// sales per calendar month pooled across all available years, plus average month-to-month
// growth % for each of the 12 transitions. Backs two business questions -- see PRD_LOGIC.md:
//   1. Listing/delisting timing: which calendar months are historically weak (delist/relist
//      candidates), ranked by % below the department's own annual average.
//   2. Best growth periods: which month-to-month transitions historically grow the most (bank
//      on this window), ranked by average growth %, each showing how many years support it.

const seasonStatusEl = document.getElementById('season-status');
const seasonChartEl = document.getElementById('season-chart');
const seasonGrowthTableEl = document.getElementById('season-growth-table');
const seasonWeakTableEl = document.getElementById('season-weak-table');
const growthSortState = makeSortState();
const weakSortState = makeSortState();
wireSortableHeaders(seasonGrowthTableEl, growthSortState, () => renderSeasonality(seasonDeptSelect.get()));
wireSortableHeaders(seasonWeakTableEl, weakSortState, () => renderSeasonality(seasonDeptSelect.get()));

function renderSeasonality(dept) {
  if (!seasonality) { seasonStatusEl.hidden = false; seasonStatusEl.textContent = 'Loading…'; return; }
  const d = seasonality.departments[dept];
  if (!dept || !d) {
    seasonStatusEl.hidden = false;
    seasonStatusEl.textContent = 'Pick a department above to see its seasonality.';
    seasonChartEl.innerHTML = '';
    seasonGrowthTableEl.innerHTML = '';
    seasonWeakTableEl.innerHTML = '';
    return;
  }

  const months = seasonality.calendar_months;
  const bars = months.map(m => ({
    month: m, avg: d.avg_sales_by_month[m] || 0, years: d.years_count_by_month[m] || 0,
  }));
  seasonStatusEl.hidden = false;
  seasonStatusEl.innerHTML = `${escapeHtml(dept)} ${inSeasonBadge(dept, latestCompleteMonth())} — average sales by calendar month, pooled across ${Math.max(0, ...bars.map(b => b.years))} years of history (annual average: ${Math.round(d.overall_avg_monthly_sales).toLocaleString('en-IN')}).`;
  seasonChartEl.innerHTML = seasonBarSvg(bars);

  const GROWTH_TOP = 5;
  let growthTop = d.growth_transitions.slice(0, GROWTH_TOP);
  if (growthSortState.key) growthTop = sortRows(growthTop, growthSortState, (t, k) => t[k]);
  const growthRows = growthTop.map(t => `<tr>
    <td title="Month-over-month growth arriving into ${escapeAttr(t.month)}, from ${escapeAttr(t.from_month)}">${escapeHtml(t.month)}</td>
    <td class="num">+${t.avg_growth_pct.toFixed(1)}%</td>
    <td class="num">${t.years} yr${t.years === 1 ? '' : 's'}</td>
  </tr>`).join('');
  seasonGrowthTableEl.innerHTML = d.growth_transitions.length
    ? `<thead><tr>
        ${sortableTh('Month', 'month', growthSortState)}
        ${sortableTh('Avg growth', 'avg_growth_pct', growthSortState, true)}
        ${sortableTh('Years behind it', 'years', growthSortState, true)}
      </tr></thead><tbody>${growthRows}</tbody>`
    : '<tbody><tr><td>No usable transitions (insufficient/zero-base history).</td></tr></tbody>';

  const WEAK_TOP = 5;
  let weakTop = d.weak_months.slice(0, WEAK_TOP);
  if (weakSortState.key) weakTop = sortRows(weakTop, weakSortState, (w, k) => w[k]);
  const weakRows = weakTop.map(w => `<tr>
    <td>${escapeHtml(w.month)}</td>
    <td class="num">${w.pct_vs_annual_avg.toFixed(1)}%</td>
    <td class="num">${Math.round(w.avg_sales).toLocaleString('en-IN')}</td>
    <td class="num">${w.years} yr${w.years === 1 ? '' : 's'}</td>
  </tr>`).join('');
  seasonWeakTableEl.innerHTML = d.weak_months.length
    ? `<thead><tr>
        ${sortableTh('Month', 'month', weakSortState)}
        ${sortableTh('vs. annual avg', 'pct_vs_annual_avg', weakSortState, true)}
        ${sortableTh('Avg sales', 'avg_sales', weakSortState, true)}
        ${sortableTh('Years behind it', 'years', weakSortState, true)}
      </tr></thead><tbody>${weakRows}</tbody>`
    : '<tbody><tr><td>No usable months (insufficient history).</td></tr></tbody>';
}

function seasonBarSvg(bars) {
  const W = 900, H = 280, padL = 60, padR = 20, padT = 20, padB = 30;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const maxVal = Math.max(1, ...bars.map(b => b.avg));
  const slot = plotW / bars.length;
  const barW = slot * 0.6;
  const y = v => padT + plotH - (v / maxVal) * plotH;

  const rects = bars.map((b, i) => {
    const cx = padL + slot * (i + 0.5);
    const yy = y(b.avg).toFixed(1);
    const h = (padT + plotH - y(b.avg)).toFixed(1);
    const tip = `${b.month} — avg sales ${Math.round(b.avg).toLocaleString('en-IN')} (${b.years} year${b.years === 1 ? '' : 's'} of data)`;
    return `<rect x="${(cx - barW / 2).toFixed(1)}" y="${yy}" width="${barW.toFixed(1)}" height="${h}" fill="var(--color-primary)" opacity="${b.years === 0 ? 0.15 : 0.85}">` +
      `<title>${escapeHtml(tip)}</title></rect>`;
  }).join('');

  const xLabels = bars.map((b, i) => {
    const cx = (padL + slot * (i + 0.5)).toFixed(1);
    return `<text x="${cx}" y="${H - padB + 16}" font-size="11" fill="var(--color-muted-foreground)" text-anchor="middle">${escapeHtml(b.month)}</text>`;
  }).join('');

  const yTicks = [0, 0.5, 1].map(f => {
    const v = maxVal * f, yy = y(v).toFixed(1);
    return `<line x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}" stroke="var(--color-border)"/>` +
      `<text x="${padL - 8}" y="${yy}" text-anchor="end" dominant-baseline="middle" font-size="10" fill="var(--color-muted-foreground)">${Math.round(v).toLocaleString('en-IN')}</text>`;
  }).join('');

  return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}">${yTicks}${rects}${xLabels}</svg>`;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function escapeAttr(s) { return escapeHtml(s); }
