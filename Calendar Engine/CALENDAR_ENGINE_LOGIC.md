# Calendar Engine — Logic Handover

Business rules, domain formulas, and verified data for Calendar Engine specifically. Structure/deployment/ops facts live in the companion doc, `CALENDAR_ENGINE_ARCHITECTURE.md`, in this same folder. Last compiled 2026-09-22.

---

## What this app does, in one paragraph

Calendar Engine builds a day-by-day mapping from a "reference" year's real sales calendar (e.g. 2026) onto a "future" year's calendar (e.g. 2027), so that festival-driven demand shifts — Diwali falling on a different date, Eid moving by the lunar cycle, etc. — get carried forward correctly instead of naively assuming "the same calendar month next year behaves the same." Downstream, SalesPlan and AOP Forecaster read this mapping (directly or via a snapshot) to reindex real historical sales onto the future calendar for planning purposes.

## Propagation rules (the "who changes when I edit one thing" model)

- **Cross-cluster cascade** (live editor, same session): editing Pre/Core/Post on a festival in one cluster propagates to every OTHER cluster's festival with the exact same name (`handleDayFieldChange` in `CalendarisationTab/index.jsx`). This is what enforces the standing rule below.
- **Manual-intervention override, added 2026-09-22**: a per-(cluster, festival) **Independent** checkbox. When set, that one row is excluded from the cascade in BOTH directions — editing it doesn't push out to other clusters' same-named festival, and editing one of those doesn't overwrite it. Every other festival on that cluster stays fully synced as before; this only ever takes one (cluster, festival) pair out of the shared window. Persisted as `independent` on both `cluster_profile_festivals` (live) and `calendar_cluster_festivals` (locked), specifically so it survives a "Load & Preview" round-trip instead of silently resetting to synced.
- **Cross-template auto-copy**: picking a festival from the real `FESTIVAL_DB` autocomplete auto-copies it into every other saved/locked calendar's same-named cluster, each resolved to ITS OWN ref/fut year — purely additive, never overwrites an existing row.
- **"Sync Festival Structure to All Templates"** (manual button, Festival Master toolbar): pushes the CURRENT full festival structure (every cluster's list, as it stands right now) into every OTHER saved template. Only a cluster name common to both sides gets its list REPLACED — a cluster unique to either side is left untouched. Re-dates via the festival's own day/month shifted onto each target's year (not `FESTIVAL_DB`'s generic default), so a deliberately customized date survives the sync. Does **not** filter by engine (V1/V2) or year-pair — it already reaches every saved calendar regardless, which is broader than "just the sibling engine of the same year-pair" (see Open design items below for a more targeted version that's been discussed but not built). Does **not** touch a target's locked day-map — only "Create Calendar + Lock & Save" on that specific template regenerates the actual day-by-day mapping.
- **"Locked" preview autosave**: while a locked template is loaded via "Load & Preview", every live festival-list edit autosaves into that template's storage too (festival list only — the day-map stays exactly as last generated until Create Calendar + Lock & Save reruns). "Load & Preview" itself does NOT write to the DB on its own — a stale reload can make a removed festival appear to "come back"; verify against the rendered table, not just a DB query, when checking whether something persisted.

**Standing rule**: no two clusters may shift the same festival by a different number of days, UNLESS one of them is explicitly marked Independent for that festival. Re-check this any time a festival is added to a cluster's profile.

## Calendar generation rules

- **Overlap resolution** (changed 2026-09-18): when two festivals' windows land on the same date, resolve by `|position|` ascending then window size ascending — each festival's own anchor (pos 0) always wins its own date. Genuine calendar coincidences (e.g. Eid al-Fitr vs Bihu, Raksha Bandhan vs Milad-un-Nabi) are expected, not a bug to "fix more correctly."
- **Month-containment rule**: non-core-festival days must never shift into a different calendar month than their future date — only core (anchored) festivals may cross months, since they follow their real lunar/astronomical date. When a future month's own reference-day pool runs short, reuse the nearest already-used reference day from that SAME month (`sharedRef: true`) rather than borrow an unused day from an adjacent month.
- **Core/non-core distinction — removed entirely (2026-09-18)**: every festival on a cluster's list is now core, no exceptions. `CORE_FESTIVALS_BY_CLUSTER` is deleted; `coreFestivalNamesFor()` always returns null.
- **Pre/Core/Post windowing formula** (`engine.js`):
  ```js
  for (pos = -pre; pos <= post + core - 1; pos++)
    category = pos < 0 ? 'Pre' : pos < core ? 'Core' : 'Post'
  ```
  Core anchor is always `pos = 0`. Output labels are suffixed per category (e.g. "Holi (Pre)").

### V1 vs V2 engines

Separate generation paths, not the same calendar relabeled — switching the engine dropdown only affects newly-generated calendars; an existing locked template keeps whatever algorithm produced it (check `calendars.engine`: `calendarisation-v1` or `calendarisation-v2`).

- **V1**: strict same-month-only matching for every non-festival day.
- **V2**: a strict 4-tier hierarchy per non-festive TY day (business rule confirmed 2026-09-22, `engine.js`'s `_v2Remap`, commit `<pending>`):
  1. **Round A**: own month's residual (unused) reference-day pool.
  2. **Round A2**: same-month **reuse** (`sharedRef: true`) of an already-committed reference day — checked BEFORE ever considering another month at all. Since every real Gregorian month has spare days to reuse, this tier resolves nearly everything on its own.
  3. **Round B**: adjacent-month pool ONLY (`moPri`'s preferred direction tried to completion first, then the other direction) — never a third month.
  4. **Exception**: a bounded reuse restricted to the same 3 months as tiers 1–3 (own + both adjacent) — never expands further. Distinctly labeled `'Same/Adjacent Month Reuse (Exception)'`; should essentially never fire given tier 2 resolves almost everything first.
- **`maxShift` (default 45 days) is a secondary quality-control constraint for `repairExcessiveShifts`, never a month-adjacency substitute** — 45 days is looser than "1 adjacent month" (~31 days), so relying on it to catch a month-boundary violation was always unsound. `repairExcessiveShifts` can no longer "fix" a boundary violation because the 4-tier hierarchy above never produces one in the first place; it only tightens an already-eligible same/adjacent-month match.
- **Both V1 and V2 must call `repairExcessiveShifts`** on their final assignment before output. V2 was missing this call until fixed 2026-09-18 (commit `30474c7`) — a calendar locked before that fix has no repair applied at all.

**Non-festive month-adjacency bug — FIXED 2026-09-22.** The previous V2 had an unrestricted final "Fallback" tier: when both same-month and adjacent-month pools were exhausted, it grabbed the nearest still-available reference day from **anywhere in the year** with no month cap at all — confirmed live via a user report: BIHAR cluster, "2026 → 2027 Calendar - All" (locked 2026-09-17), 3 of March 2026's days mapped to January/February 2027 instead of March 2027 (`'Nearest Available Date (Cross-Month)'`). Two of the three were UNDER `maxShift` (45 days) and would never have been caught by `repairExcessiveShifts` even after regenerating — proving `maxShift` was never a valid proxy for month-adjacency. Replaced with the 4-tier hierarchy above (root cause + tests in `Calendar Engine/frontend/src/lib/engine.test.mjs`, run via `node src/lib/engine.test.mjs`). **A locked calendar generated before this fix still carries the old bad mappings — it must be regenerated** (Version Setting → Create Calendar → Calendarisation tab's own Create Calendar → Lock & Save, same name to overwrite) to pick up the corrected non-festive assignment; confirmed live against BIHAR's real festival config that a fresh V2 regeneration no longer produces the reported rows.
**Side effect of the corrected priority order**: because same-month reuse (tier 2) can resolve almost any non-festive day on its own, V2's adjacent-month tier (3) now fires far less often than before — this is the direct, intended consequence of the confirmed priority ("same-month reuse checked before ever borrowing from an adjacent month"), not a regression.

**All "- All"-named locked calendars regenerated under the fix, 2026-09-22**: "2026 → 2027 Calendar - All" (id `1790058208234`), "2025 → 2026 Calendar - All" (id `1790058760980`, previously on V1 since it was saved before V2 existed), and "2024 → 2025 Calendar" (id `1790058825523`, same). Each regenerated via Load & Preview → Create Calendar (engine V2) → Save Changes to [name] (overwrites in place under a NEW numeric id — the backend has no partial-update endpoint, it's always delete-then-recreate; the name stays the same so anything referencing it by name is unaffected). Verified 0 validation errors and 0 month-adjacency violations on all 3 before saving. **"2026 → 2027 Calendar - Version 1" (id `1789556012651`) was deliberately left untouched** — it's explicitly the V1-engine representative by name/design (see the Core/non-core policy history above), not a candidate for this fix.

## Reindex / data-pipeline facts

- A single reference day can legitimately map to two future days (same-month reuse via `sharedRef`) — any ref→fut join must be a proper table merge over `calendar_day_pairs`, never a `{ref_date: fut_date}` dict (a dict silently drops the second mapping, last-wins).
- A duplicate `ref_date` in `calendar_day_pairs` is not automatically a bug — check `mappingPriority`/`sharedRef` intent before calling it drift.
- Whenever a festival's date changes, check whether any OTHER festival's date is DERIVED from it (Nuakhai = Ganesh Chaturthi+1; Kali Puja = same day as Diwali; Shraad's end = day before Navratri's start) and re-verify those too.
- **Month-wise double-counting bug — fixed 2026-09-22, commit `8d975fb`**: `_fetch_raw_monthwise()` and 2 other call sites in `scans.py` globbed every `.parquet` file in `PARQUET_DIR` and concatenated them, with no "latest export only" guard (day-wise already had this via `_latest_daywise_files()`). With 2 overlapping full-history re-exports sitting in the folder, every month-wise reindexed total was counted ~2x. Fixed with `_latest_monthwise_files()`, applied at all 3 read sites (link scan, `get_source_schema`, `_fetch_raw_monthwise`). AOP Forecaster's own actuals sync was never affected (separate, correct `sync.common.latest_file()` implementation). Verified live: file count read dropped 2→1, and Month Wise Matrix row totals now tie out exactly to actual sales.

### Month Wise Matrix (new feature, 2026-09-22)

For a chosen store, splits each REFERENCE month's actual sales total across TY months, **proportional to how many of that reference month's real calendar days landed in each TY month**, per the locked calendar's own day-map. This is a day-COUNT proportional split, not a measured intra-month sales pattern — month-wise source has no day-of-month field at all, so the calendar's day-map is the only available signal for how a month's total should divide when a festival shift splits it across two TY months (e.g. a reference month whose days split 90%/10% between two TY months shows the same 90%/10% split of its actual sales total).

- Computed in `fwdSplitByCluster` (`CalendarisedSalesTab/index.jsx`'s `fetchCalendarMaps()`) — the forward-direction companion to the pre-existing `refMonthsByCluster` (which answers "which LY months fed this TY month"; `fwdSplitByCluster` answers "where did this LY month's days go").
- **Requires a calendar to be selected** in the "Calendar to Reindex" dropdown — it's purely calendar-derived, no completed reindex run needed, but a page showing only a cached snapshot (no calendar picked yet) will show a visible "select a calendar" warning instead of guessing or silently rendering blank.
- Store Filter is a true multi-select (checkbox dropdown, search + Select All/Clear) — each selected store renders its own stacked block. "Download XLSX (All Stores)" always covers every store regardless of the preview selection, via the `xlsx` (SheetJS) dependency.

## Festival date sourcing discipline

Never invent or estimate a real calendrical festival date. Only use a date the user has explicitly verified, or one mathematically/tithi-derived from another already-verified date, with the derivation stated explicitly. A brand-new festival with no anchor and no user-supplied date → ask, don't guess, even under time pressure.

### Verified 2026 → 2027 festival dates

Re-audited in full 2026-09-18 against Wikipedia/DrikPanchang/multiple Panchang sites — treat as needing periodic re-verification, not permanently settled.

| Festival | 2026 (ref) | 2027 (fut) | Note |
|---|---|---|---|
| Holi | 2026-03-04 | 2027-03-22 | verified |
| Eid al-Fitr | 2026-03-20 | 2027-03-09 | moon-sighting dependent, ±1 day |
| Eid al-Adha | 2026-05-27 | 2027-05-17 | 2026 is J&K's date; majority-state is 2026-05-28 — deliberate regional choice |
| Rath Yatra | 2026-07-16 | 2027-07-05 | fixed 2026-09-18, was a full year shifted |
| Raksha Bandhan | 2026-08-28 | 2027-08-17 | fixed 2026-09-18, 2026 value had actually been 2025's date |
| Nuakhai | 2026-08-23 | 2027-09-11 | verified |
| Shraad (Pitru Paksha start) | 2026-09-26 | 2027-09-15 | derived from Navratri's start; must re-derive whenever Navratri's date changes |
| Navratri (Ghatasthapana) | 2026-10-11 | 2027-09-30 | fixed 2026-09-18, was off by 8 days |
| Dussehra (Vijayadashami) | 2026-10-20 | 2027-10-09 | fixed 2026-09-18, was off by 8 days |
| Diwali | 2026-11-08 | 2027-10-29 | verified (fixed 2026-09-17 — was a data-entry duplicate of Dussehra's date) |
| Chhath Puja | 2026-11-15 | 2027-11-05 | 2027-11-04 is DrikPanchang's main day, 11-05 is the closing day — deliberate |
| Milad-un-Nabi | 2026-08-26 | 2027-08-15 | fixed 2026-09-18, was off ~9-10 days (lunar drift not applied) |
| Basant Panchami | 2026-01-23 | 2027-02-11 | fixed 2026-09-18, was a full year shifted |
| Makar Sankranti | 2026-01-14 | 2027-01-15 | fixed 2026-09-18, off by 1 day |
| Durga Puja (WB/N.EAST) | covered by Navratri window | — | not a separate entry — do not add separately |

**Recurring bug pattern seen 2026-09-17/18**: several festivals showed the identical signature — the stored future-year value matched what should have been the date one cycle earlier ("everything shifted by one year"), or a straight data-entry duplicate of another festival's date. When a festival appears missing from output despite being in the profile, check for duplicate `ref_date`s in `cluster_profile_festivals` first.

**Real clusters (region tags actually in use)**: Kashmir, UP+NCR, UP+BIHAR-PUJA, BIHAR, JAMMU+RJ, ODISHA, N.EAST-PUJA, N.EAST, JH+MP+CG, WB — only `north`, `east`, `bengal` tags in use across these 10; no South India/Gujarat/Maharashtra cluster exists despite `FESTIVAL_DB` carrying those tags for completeness. N.EAST/N.EAST-PUJA are tagged `bengal` in live data (existing data, not a bug to silently fix).

## Open design items (discussed, not yet built)

Raised by the user 2026-09-22, alongside the Independent-override feature above:

1. **Automatic V1/V2 sync for the same year-pair.** User's stated preference: a manual button (not fully automatic on every edit) that's scoped specifically to the sibling engine's template for the same year-pair (not every saved template, unlike the existing "Sync Festival Structure to All Templates"), plus an "out of sync" badge/warning shown when the two have diverged since the last sync. Not yet built — would need: (a) a lookup for "the other engine's calendar with the same refYear/futYear," (b) a diff function comparing live structure against that sibling's saved structure, (c) a badge component, (d) a scoped version of the sync push.
2. **Bulk festival→cluster import**, modeled on Store-Cluster Mapping's file-upload + diff-preview UX (`StoreMappingPanel.jsx`'s `importStoreCluster` flow: upload a file, see added/removed/reassigned before committing). Not yet built — the current "Copy festivals from..." dropdown only replaces one cluster's ENTIRE list from another cluster; there's no way to import "just this one festival, into these N clusters" without hand-editing each cluster.

---

## Change Log

- **2026-09-22**: Doc created, compiled from session memory (Logic Base / Architecture Base) covering the day this session ran: month-wise double-counting bug fix, Month Wise Matrix feature (incl. its blank-split fix and multi-select correction), Festival Master button-row layout fix, per-cluster Independent override feature, and the V2 Fallback-tier root-cause investigation for the March→January outlier report. Open design items (V1/V2 auto-sync, bulk festival import) captured but not started.
