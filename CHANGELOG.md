# RS Planning Suite — Changelog

Suite-wide changes across Calendar → AOP Forecaster → Buyer's Input Sheet (BIS) → Sales Plan.
Newest first. Each entry names its commit.

---

## 2026-09-30

### Switched-off actions are hidden in Calendar and AOP; Landing gets Sign out / switch user
- **Asked (user):** "yes, hide the buttons in calendar and aop too" and "also add a log off or change user button in the landing page to switch profiles".
- **Calendar:** Run Reindex is hidden for a person whose `calendar_reindex` is switched off. `lib/api.js getRights`, and `App.jsx` passes `rights` to the tabs (`CalendarisedSalesTab`).
- **AOP Forecaster:** Sync into database (`DbSyncPanel`) and Promote to Planning / Unlock (`ResultsDashboard`) are hidden when `data_sync` / `aop_publish` is switched off. They use a new `lib/rights.js useCan(right)`, which asks `/api/auth/rights` once per page load. Standalone :8000, or no answer, means show the button; Landing still refuses the action.
- **Landing:** a "<name> · Sign out" button next to Users. It calls `POST /api/auth/logout`, which clears the session and the remember-me cookie, then goes to `/login?next=/` so someone else can sign in. On phones the top bar drops the brand name, username and "Theme" text, so it fits (it had already been 47 px too wide at 412 px).
- **Build:** both frontends rebuilt. `dist/` is not committed; 8010 serves the local build.

### Users & access: switch off important actions per person
- **Asked (user):** "give me a revoke access panel for admin for different rights like server action button and other important features".
- **Panel:** a new "Access to important actions" card on `/auth/users`, with one tick box per action for each person. Unticking switches the action off at once. Everyone has every action until an admin unticks it, admins always keep all of them, and switched-off accounts have none.
- **The six actions:** start / stop all servers (Master Switch); sync the data lake (Landing Sync now, AOP Sync into database); promote AOP to Planning or unlock it; Calendar Run Reindex; Re-Aligner Run and Re-phase & run; change the suite colour theme.
- **Enforced in Landing** (`landing_server.py` `GUARDED`), the one door to every app. Before a guarded request, Landing asks 8010 `GET /api/auth/rights`, which reads admin and active status fresh from the database, not the session, and returns 403 "An admin has switched off your access to: …" when the right is gone. If the check can't be made, the action is refused. Landing also greys out the Master Switch and Sync now for people without them.
- **Storage:** `RS Planning Platform/backend/data/user_rights.json`, shaped {user id: [revoked rights]}. It is local and git-ignored, and no database change was needed. API: `GET /api/auth/admin/rights`, `PUT /api/auth/admin/rights/{id}` {revoked}.
- **Left out on purpose:** the BIS sales / sell-through / history syncs. BIS calls them itself when it loads, so blocking them would break BIS for that person.
- **Tests:** `tests/test_rights.py`, `Landing/test_rights_guard.py`. Checked live: switching one action off for Planning01 applied at once (5 of 6); the admin's guarded request passed Landing; it was given back.

### Users & access: rename a username
- **Asked (user):** "i need a username rename option here".
- **What:** a **Rename** link under each name in the USER column of `/auth/users` (kept there so it stays visible when the table scrolls sideways on a narrow screen) changes the name the person signs in with. The server refuses a blank name, one over 64 characters, or one another account already has (ignoring case, so "Admin" and "admin" can't both exist). Renaming yourself updates your own session at once; anyone else sees the new name the next time they sign in.
- **Re-Aligner:** workspaces are now kept by account id, not username, so a renamed person keeps their plan, locks, overrides and history. Folders named by username before this change move to the id folder on that person's next visit.
- **Files:** `RS Planning Platform/backend/auth/routes.py` (`username_refusal`, PATCH accepts `username`), `static/admin-users.html`, `tests/test_admin_guard.py`; `AOP Realigner/server.py` (`who` returns (id, username), `Workspace(key, name)`), `test_workspaces.py`.

### AOP Re-Aligner: every signed-in user has their own copy
- **Asked (user):** "make it so each user gets their own copy".
- **How it works:** each request is tied to the RS Planning user signed in through Landing. The Re-Aligner asks the platform (`/api/auth/me`) who the forwarded session cookie belongs to, and caches the answer for a minute.
- **What each user gets:** their own **workspace** in `.cache/users/<name>/`, holding:
  - the plan, month locks and store overrides;
  - the revised file, result and exports;
  - running jobs and activity history.
- **Isolation:** one user's loads, locks, Re-phase & run and exports never touch another's. Jobs run with their own user's locks, and each user can run their own job at the same time as others.
- **Starting point:** a user's first visit starts from a **copy of the setup at that time**: the loaded plan, locks and overrides. After that it's theirs.
- **Local use:** direct use of `:8070` on this PC, with no sign-in, gets a separate "local" workspace.
- **Memory:** a workspace untouched for 2 hours frees its plan from memory, and it reloads on the next visit. An unexported result is dropped then. The Re-Aligner's top bar shows "Your workspace: <name>".
- **No Landing change or restart:** Landing already forwards the session cookie.
- **Checked:**
  - Your own browser tab was put in the `admin` workspace automatically, seeded with the 674,478-row plan, 4 locked months and 303 overrides.
  - `test_workspaces.py`: two users' locks and settings stay apart, job threads see their own locks, and idle unload and reload work.
  - `test_realign.py` still passes.
- Files: `AOP Realigner/server.py` (Workspace, `who()`, per-user `state` / `jobs` / `history`), `engine.py` (`locked()` per thread, `engine.LOCKED` still the fallback), `index.html`, `test_workspaces.py`.

### Users & access admin page; password reset accepts an email
- **Asked (user):** "email not sent - email should be there" and "give me an admin layout for setting user control up".
- **Why no reset email came:**
  - The value typed (an email) isn't a username, and the form only looked up usernames.
  - None of the 3 accounts (admin, planning01, planning02) has an email on file.
  - The server has no SMTP (email-sending) settings, so it can't send any email yet.
- **Fixes:**
  - **Forgot password** now also accepts the email on file. It still answers the same way whether or not the account exists.
  - **New Users & access page** at `/auth/users`, reached through a Users button on Landing that only admins see. On it an admin can:
    - see every account;
    - change email, role (planner / buyer / reviewer / approver), admin rights, and sign-in on/off, each saved immediately;
    - **set a temporary password**, generated or typed, which forces the person to pick their own at next sign-in;
    - add a person.
  - It also shows how many admins there are and whether reset email is set up, and explains the roles.
  - **Lock-out guards** (server side): an admin can't remove their own admin rights or switch themselves off, and the last active admin can't be removed.
  - **Email status:** an admin-only `GET /api/auth/admin/email-status` reports whether email is set up, never the settings themselves.
- **Checked:**
  - The admin endpoints return 401 without a sign-in, and the page sends anonymous visitors to sign-in.
  - Guard tests pass (`tests/test_admin_guard.py`).
  - A cookie forged with the public development key is still rejected after the 8010 restart.
- **Still needed for email resets:** SMTP settings on the server (SMTP_HOST / SMTP_USER / SMTP_PASSWORD / SMTP_FROM), and each person's email on the page. Until then, use **Set password**.
- Files: `RS Planning Platform/backend/auth/routes.py`, `app.py`, `static/admin-users.html`, `tests/test_admin_guard.py`; `Landing/index.html`.

### Re-phase: a comparable store needs both the SSG tag and a full last year
- **Asked (user):** "yes, require both the tag and a full last year".
- **Rule:** a store may lend its month shape only if it sold in the department's division in **every** re-phased month last year **and**, when the plan has an SSG TAG column, it is tagged SSG. Tagged stores left out are named in the summary.
- **Live plan:** 124 SSG-tagged stores become 121 comparable. The 3 left out are **BRN, SAH and SBW**: they're tagged SSG but have no last-year sales in the data at all, so they never had a shape to lend.
- **Results unchanged:** every department and all six test set-ups give the same numbers. LW_U_T-TOP still reproduces the workbook (304.07 / 316.26 / 96.73 / 55.71).
- Tests: a tagged store with a part-year history is left out.
- Files: `AOP Realigner/importer.py`, `rules.js`, `test_realign.py`, `docs/business-rules/REPHASE_DEPARTMENT_MONTHS.md` (G6).

### Re-Aligner Re-phase rebuilt as a generic planning rule, and tested across plan set-ups
- **Asked (user):** "i want it to be a generic planning tool and not a biased working ... made for one time purpose ... reverify and rebuild ... the logic base should be clear, try to test on different models".
- **Rebuilt:** these rules are in the rule-set doc §0 (G1–G10), the Rules page and the Summary shown with every run.
  - **Comparable stores:** with an SSG TAG column, a store counts as comparable if its tag starts with "SSG" (it used to be an exact match on "SSG"/"SSG-ANG"). Without that column, it's decided from the data: the store must have sold in the division in every window month last year. Before this, every store could lend its shape, even one that opened mid-year.
  - **Last-year months:** a month missing from the data, or only till date, is refused rather than used silently.
  - **Unlocked half-months:** reported instead of skipped silently.
  - **Summary:** every run comes with a Summary sheet, and its lines also show in step 2.
  - **Wording:** SSG-specific labels are now "comparable stores", and the workbook examples are gone from the help text.
- **A bias the tests caught:** a fixed mix typed for LW_U_T-TOP in JHM was also applied to ML_JEANS. A fixed mix is now keyed by store × department: an overrides row needs a DEPARTMENT, and one without it is refused. REF OLD stays a store-wide attribute. The workbook's overrides file was rebuilt with JHM's mix set for LW_U_T-TOP and re-uploaded.
- **Tested:**
  - **Every department in the live plan:** 176 departments; 175 run and 1 is correctly refused because it has no last year. All invariants hold: shares 100% (worst 4e-16), store totals kept, non-trading months 0, only comparable stores lend a shape.
  - **Independent cross-check:** a different model wrote its own implementation from the rules only, without the code. On 6 set-ups (a proxy shape, KIDS, MENS, a 3-month window, a plan without SSG TAG, a plan without SSG TAG/REF/CLUSTER) it matched **5,362/5,362 store-months** (max 5e-15 L).
  - **Full Method 2 path:** all six end to end with every check ok, and the other departments moved 0.
  - **Workbook regression:** still exact (303/303 stores).
  - **Unit tests added:** no-tag comparable rule, partial and missing month refusal, half-month note, and mix per department.
- Files: `AOP Realigner/importer.py`, `server.py` (`ly_partial`, notes into step 2 + Summary sheet), `index.html`, `rules.js`, `test_realign.py`, `docs/business-rules/REPHASE_DEPARTMENT_MONTHS.md` (§0).

### Re-Aligner: no "Replace this file" box after Re-phase & run
- **Asked (user):** "shouldn't this replace the file option be removed … now that the plan is remade accordingly".
- **Change:** when the step-2 file was built by Re-phase & run, the big drop box is replaced by one line: "Built by Re-phase & run – nothing to upload. To use your own edits, download Re-phase file, change it and upload it here", where "upload it here" is a small link.
- **Unchanged:**
  - An uploaded file still shows the drop box.
  - The edit-and-upload route stays: download the Re-phase file, change it (e.g. a hand-set store) and upload.
  - The upload route for other departments' hand-made revised plans stays.
- **How:** `server.job_rephase` marks the revised info `generated`, and `index.html renderRev` reads it.

### Re-Aligner Rules page: Method 2 written out in full
- **Asked (user):** "have you made sure that the rules are set for method 2". The Rules page was checked line by line against `importer.template_rephase` and `engine.verify`.
- **What was wrong:**
  - "What is kept" said the other departments always absorb, but Method 2 can keep them as they are.
  - "Checks" didn't describe the stay-as-they-are checks.
  - The re-phase details the code applies were missing:
    - The window is only the unlocked full months; P1/P2 halves have no last-year month.
    - Last year comes from the data-lake sales, a year earlier.
    - Only SSG stores lend a shape, and negative last-year values count as 0.
    - A month is "not trading" when the store has no plan in that division.
    - REF / SSG TAG / CLUSTER are read from the plan's own columns.
    - A fixed mix is rescaled to 100%.
    - Each re-phase comes with a "How it was built" sheet.
- **Now:**
  - "Method 2 – existing department changes" covers the file format and the absorb / stay-as-they-are option.
  - A new "Method 2 – Re-phase from last year" section covers Re-phase & run, the window, the shape cascade, non-trading months, store overrides and the audit sheet.
  - "Checks on every run" now includes the stay-as-they-are checks.
- File: `AOP Realigner/rules.js`.

### Re-Aligner Re-phase: store overrides make it match the hand-built plan exactly
- **Asked (user):** "Check why is there a slight difference between mine and your iteration and fine tune it". The app gave 304.10 / 316.09 / 96.28 / 56.30; the user's pivot is 304.07 / 316.26 / 96.73 / 55.71.
- **Why:** 286 of 303 stores already matched exactly. The gap came from two causes only:
  - **16 stores** take REF OLD's shape in the workbook. REF OLD isn't in the plan, the DB store master or Store Master.xlsx (1/16 in each), so the app used the cluster's SSG stores.
  - **JHM** is hand-typed, with Oct = 0 although it trades in Oct.
- **Fix, "Store overrides":** in Method 2 step 2, upload once (kept until cleared) a sheet with STORE NAME, REF OLD and optionally `<Month> %`.
  - REF OLD from the sheet is used before the cluster fallback.
  - A month % mix replaces that store's last-year shape, as given.
  - **Overrides template** lists the re-phase's stores, with the ones that need REF OLD first.
- **Result, in the app on the live plan:** with the workbook's REF OLD and JHM's typed mix, **Re-phase & run gives 304.07 / 316.26 / 96.73 / 55.71**, all 303 stores exact (max 2e-8 L), and all checks ok.
- Files: `AOP Realigner/importer.py` (`read_rephase_overrides`, `template_rephase_overrides`, `template_rephase(..., overrides)`), `server.py`, `index.html`, `rules.js`, `test_realign.py`, `docs/business-rules/REPHASE_DEPARTMENT_MONTHS.md`.

### AOP Re-Aligner: "Re-phase & run" takes a department to the final plan in one click
- **Asked (user):** "i just select the department to be executed and you do it on the second step by yourself and take it to the final plan".
- **How it works:** in Method 2's step 2, pick the department (and optionally the LY shape), then click **Re-phase & run**. The server does, as one job, what used to be three steps:
  1. Builds the re-phase from last year.
  2. Loads it as the step-2 revised plan, with the usual checks.
  3. Sets "other departments: stay as they are" and runs the realignment. The result, checks and downloads appear as after a normal run.
- **Re-phase file** still downloads the same file, for checking or editing it first.
- **Tested on the live plan** (LW_U_T-TOP with the LW_U_T-TOP F/S shape): 25 s, all checks passed.
  - LADIES moves only by LW_U_T-TOP's own change: Sep 550.21 → 304.10, Oct 222.56 → 316.09, Nov 0 → 96.28, Dec 0 → 56.30 L; 229 stores.
  - KIDS, MENS and Jan/Feb are unchanged.
- Files: `AOP Realigner/server.py` (`job_rephase`, `POST /api/rephase?dept=&mix=`), `index.html`, `rules.js`.

### Nightly sync now rebuilds the Calendar's day-wise sales too
- **Asked (user):** "yes, add day-wise to the nightly sync".
- **Before:** only the month-wise calendarised sales were rebuilt nightly. The day-wise ones changed only when someone ran Run Reindex → Day-wise by hand, and still sat on 26 Sep's data, which stopped at **27 Aug 2026**.
- **New job `calendar_reindex_dw`** (`sync/calendar_reindex_dw_sync.py`) runs in `sync/run_all.py`, after `calendar_reindex` and `calendar_check`. So it's part of the 05:00 task and of Sync now / Sync into database.
  - It uses the same calendar, stores and months as the month-wise job, and the Calendar's own day-wise output (store level, default metric).
  - It has its own sync-status row, so a day-wise failure never marks the month-wise rebuild failed. The shared calendar loading moved into `calendar_reindex_sync.calendar_inputs()`.
- **Bug fixed on the way (month cache):** a closed month is cached for good. August had been cached on 26 Sep from a day-wise file that ended on 27 Aug, because "closed" comes from the month-wise data. Every later day-wise run, nightly included, would have kept serving that 27-day August.
  - Day-wise months are now cached, or reused, only when their data reaches the month's last day (`scans._covers_month_end`). The month-wise rule is unchanged.
  - Tests: `RS Planning Platform/backend/tests/test_reindex_dw_cache.py` (3).

### Calendar: "Last synced" shows when the data was actually pulled
- **Bug (user, screenshot):** the Link Sales Data Source table showed Month-wise last synced "25 Sept, 10:40 am", although the data had been re-synced since (29 Sep, 13:09).
- **Cause:** the column showed when the list of linked months was last saved. Month-wise already had every month linked, so the daily syncs that rebuild its data never moved it.
- **Fix:** `GET /api/calendar/salesdata-link-selection/{mw|dw}` now also returns `dataSyncedAt`. That's the source's last snapshot rebuild, plus the last day-weights sync for day-wise. The column shows the later of the two.
- Month-wise now reads 29 Sep, 01:09 pm; day-wise is unchanged (29 Sep, 01:58 pm).
- Files: `RS Planning Platform/backend/calendar_engine/router.py`, `Calendar Engine/frontend/src/components/CalendarisedSalesTab/LinkStatusPanel.jsx` (+ rebuilt `dist/`).

### AOP Re-Aligner: "Re-phase from LY" builds the Method 2 file
- **Asked (user):** "yes, build the re-phase from LY generator".
- **Where:** Method 2, step 2. Pick the department and optionally the LY-shape department (any department with last-year sales, e.g. LW_U_T-TOP F/S), then click **Re-phase from LY**.
- **What it builds:** a Method 2 file where each store keeps its total for the unlocked months, re-split by last year's same months.
  - **Shape source:** the first SSG store of (the store itself, REF, REF OLD), else the cluster's SSG stores, else the store's planned phasing.
  - **Non-trading months** get 0 and the rest is rescaled.
  - **Audit sheet:** "How it was built" shows each store's source, LY, mix % and old/new values.
  - **Then:** upload it and run with "other departments: stay as they are".
- **New rule found in the workbook:** only SSG stores lend a shape. The workbook's LY pivot is filtered to SSG, so a non-SSG REF falls through to REF OLD.
- **Tested on `LW_U_T-TOP Working.xlsx`:**
  - With the workbook's LY and REF OLD: 286/286 formula stores exact, 16/17 exceptions (JHM is manual); 7,865/7,878 final rows exact, all 13 misses are JHM.
  - With live `sales.json` and no REF OLD column: 271/286 exact. The 15 REF-OLD stores use the cluster fallback, within 0.71 L.
  - Live plan: 772.77 L kept exactly.
  - Adding a REF OLD column to the plan makes every store exact.
- **Also:** Method 2's fallback mix no longer prints numpy's "mean of empty slice" warning (same maths). The Rules page has been updated.
- Files: `AOP Realigner/importer.py` (`template_rephase`), `server.py` (template route, `ly_departments` in state), `index.html`, `rules.js`, `engine.py`, `test_realign.py`, `docs/business-rules/REPHASE_DEPARTMENT_MONTHS.md` (R4, §8).

## 2026-09-29

### AOP Re-Aligner Method 2: tested against the re-phase rule set, and improved
- **Asked (user):** "compare it with the method 2 and improve the logic base through intense training and checking." The user chose "Test, then improve Method 2".
- **Test:** the new LW_U_T-TOP store months from `LW_U_T-TOP Working.xlsx` were fed to Method 2 against the file's 8th Aug LADIES plan (220,584 rows).
- **Fixes and additions:**
  - **Fallback mix:** a month the department had no plan in (Nov/Dec) now uses the average over the *revised* months that had one. Locked Jan/Feb no longer count. It was 2,896 row-months off by up to 0.075 L; now 0.
  - **New Run-card option "Other departments: stay as they are":** only the revised departments move, which suits a month re-phase. The default ("absorb") is unchanged. In this mode the checks confirm the other departments are untouched and the revised departments kept their season total; the store × division months show as info.
  - **Warning fix:** the "locked month ignored" warning now fires only for locked months the revised file contains. It had fired 6,864 times falsely.
- **Result:** with "stay as they are", all 7,878 LW_U_T-TOP rows match the workbook exactly in every month, the other 51 LADIES departments are untouched, and all checks are ok. Rule-set doc R8 was corrected (zeros counted, window months only), and §7 was added.
- Files: `AOP Realigner/engine.py`, `server.py` (`/api/option?absorb=`), `index.html`, `test_realign.py`, `docs/business-rules/REPHASE_DEPARTMENT_MONTHS.md`.

### Rule set: re-phase a department's plan across months (from LW_U_T-TOP Working.xlsx)
- **Asked (user):** "analyse this file thoroughly and build a generic rule set." The 554 MB workbook was read by streaming its XML, without opening it in Excel or loading whole sheets. Every step was checked against its saved values.
- **Written up:** `docs/business-rules/REPHASE_DEPARTMENT_MONTHS.md`. The method:
  - Keep each store's window total (Sep–Dec) for one department.
  - Re-split it by a store-level LY month mix: own mix for SSG / SSG-ANG stores, else REF → REF OLD → 0. The mix may come from a proxy department (here LW_U_T-TOP F/S).
  - Drop non-trading months and rescale the rest.
  - Split down to MRP × display by the old plan's month mix (the average of the planned months for months that had none, renormalised).
  - Re-price qty from the old ASP. Jan/Feb and every other department stay untouched.
  - The doc also lists the checks each run must pass.
- **Verified in the file:**
  - 303 stores; the window total is kept exactly (772.77 L); every mix is 100%.
  - MRP × display rows equal the store months exactly; Jan/Feb and the other departments are unchanged.
  - 16 of the 17 hand-typed "Exception" rows follow the non-trading-month rule exactly.
- **Open points:**
  - JHM's typed mix doesn't follow the rule.
  - F/S is used as the curve but has no plan of its own.
  - The workbook's final value + qty (Post) step is unfinished.
- No app code changed.

### BIS: the department filter search picks what you click
- **Bug (user):** "filter search not working properly, I cannot single out my selection." With no filter set, typing a search showed the matches ticked, and clicking one **hid** it (search "dupatta" → click → 235 other departments shown, dupatta gone).
- **Fix (Excel-style):** while searching with nothing picked yet, the matches start unticked. Clicking one **shows only that department**, and more clicks add or remove others. "(Select All Search Results)" shows only the matches. Without a search, unticking still hides just that one.
- **Check (sandbox):** "dupatta" → click → only L_EW_DUPATTA · then "kurti set" → click → DUPATTA + KURTI SET · Select All → all 198 · "kurti" + Select All Search Results → the 5 kurti departments · no search, untick DUPATTA → only it hidden.

### BIS sends inactive departments to Sales Plan as plan 0
- **Problem (from the post-sync check):** Sales Plan's LADIES TY ran +0.05 … +0.12 L a month over AOP. L_EW_BLOUSE is inactive in BIS, so BIS left it out of the push, and its share went to the other LADIES departments. But Sales Plan still planned it: a department with no BIS row falls back to the saved matrix value (or index 100), and Sales Plan's Department Master only follows BIS when someone presses its "Sync from Buyer's Input" button. So the share was counted twice.
- **Fix (user's choice: "BIS sends it as plan 0"):** BIS now pushes every inactive department with **−100% for each recorded month**. Sales Plan turns that into growth index 0, so TY = 0, with no change to the Sales Plan engine. Sales Plan's `sync-from-buyer` treats a department BIS sends only at −100% as **inactive**, so it stays greyed there instead of flipping to "active".
- **Check (BIS sandbox, push intercepted):** L_EW_BLOUSE is sent as −100% for Mar–Jun. 39 inactive departments = 156 rows at −100%, 944 rows in all. Sales Plan's live figures update at the next **Save** in BIS.

### Sales sync run on the new files, and the data checked through every app
- **Bug fixed on the way (BIS):** the sales job reused whatever local copy already existed, so it would have kept reading the old 5 Sep copy after the source moved to `master.parquet`. It also read a half-written copy while the history job was re-copying it ("File too short"). Both jobs now share one `_local_copy()`: refreshed only when the network file changes, written to a temp file and swapped in under a lock.
- **Sync:** the full data-lake sync ran (`run_all`: site master, store master, day shift, store actuals, day weights — cluster-days now to **28 Sep 2026**, calendar reindex, nightly accuracy check, festival dates, Listing / Delisting), all ok. BIS sales, history and sell-through re-synced from `master.parquet` / the complete 2 Sep sell-through.
- **What changed in the data:** Mar–Jun 2026 (the plan LY) and every month Sep 2025–Jul 2026 are **identical** to the 5 Sep file for KIDS / LADIES / MENS. Aug 2026 has tiny restatements (−0.01 … −0.07 L). Sep 2026 grows from ~5 to 28 days. So the AOP base, BIS LY and the plans are unchanged.
- **Every app ties to the raw file** (0.01 L tolerance, planted 0.02 L caught each time): Calendar department snapshot 398,433 store × dept × month cells (Mar–Sep 2026, ₹90,034.01 L) exact · Listing `sales.json` 170,394 cells exact · BIS department LY 743 cells (148 plan stores, ₹38,885.41 L) max 0.0001 L · Sales Plan actual LY 330,733 cells exact · MRP Re-apportionment 212,813 cells, 0.0 L.
- **Chain deep check 17 / 19**, the same two known misses (AOP V2 base vs the current calendar). BIS → Sales Plan = AOP target, 0.0 L. **Open item:** Sales Plan's LADIES TY is now +0.05…+0.12 L over target because L_EW_BLOUSE — inactive in BIS, so not pushed — is still planned in Sales Plan from its own LY with a fallback growth. It is counted in BIS's re-spread and again in Sales Plan. A fix is proposed; nothing changed, since it touches the Sales Plan engine.

### Every app reads the same, newest complete data-lake file (sales sync)
- **Change (user):** "sync the sales data and always pick the latest file from the folders to sync. Post sync, make sure that the data is flowing through all the apps consistently."
- **Found:** new exports landed today (29 Sep): month-wise `master.parquet` (22,769,780 rows, +392k), day-wise `…_20260929T043251` (bills to 28 Sep), and a sell-through file of **exactly 50,000 rows** (the previous one has 7,069,667 — a capped or partial export). The apps chose files in five different ways, so they would have split across files:
  - **BIS sales:** pinned to the 5 Sep copy.
  - **BIS sell-through:** newest by time with no check, so it would have taken the 50,000-row file.
  - **Listing:** newest by the date stamp in the file name, so it would have kept 5 Sep (`master.parquet` has no stamp), and `build_sales` would have crashed.
  - **Sync jobs (`store_actuals`, `day_weights`):** alphabetically-last name, which picked the **old** 28 Aug day-wise file.
  - **Nightly accuracy check:** would have compared the new snapshots with the old 5 Sep file.
  - **Sales Plan's `extract_dept_kpis`:** added up every sell-through export (each week counted 2–4 times).
- **Fix — one rule, `rs_common/lake_files.py`:** each folder holds full re-exports, so exactly one file is read — the newest by modified time, unless it is clearly incomplete (unreadable/still being written, missing columns, or fewer than 90% of the previous export's rows); then the last good one, with a note saying why. BIS (unpinned), the Calendar engine (and through it Sales Plan's snapshots, the AOP syncs and MRP Re-apportionment), the sync jobs, the nightly check and Listing all use it.
- **Picks today:** month-wise `master.parquet` · day-wise 29 Sep · sell-through the complete **2 Sep** export (the 50,000-row file is skipped: "only 50,000 rows vs 7,069,667").
- **Tests:** `rs_common/test_lake_files.py` (newest wins; truncated, column-short and half-written files are skipped). The existing reindex/sync tests pass.

### AOP Re-Aligner: you choose which months are locked
- **Change (user):** "make these locks dynamic for months so that it depends on the user if they want to get it locked or they want to get them changed accordingly. Also auto detect the months as per the original plan upload." Before, Jan and Feb were always locked (`FROZEN = ("Jan", "Feb")`, checked in 14 places), and nothing else could be.
- **Now:** the month chips under "Original plan" are the months found in the uploaded plan (its `<Month> Plan` columns — today Sep'26 … Feb'27 P2). Each chip is a lock button: click to lock (kept exactly as the original, value and qty) or unlock (changes with the realignment). A new plan starts with Jan / Feb locked, as before. A month the previous plan also had keeps your choice. The choice is saved (`.cache/locks.json`, gitignored) and survives restarts. Changing a lock re-checks the revised file and clears an earlier result, since it was realigned with the old locks.
- **How:** `engine.locked(m)` replaces every hard-coded Jan/Feb check; it reads `engine.LOCKED`, which the server sets from your choice, and falls back to Jan / Feb when nothing is set. **The realignment maths is unchanged:** it already kept "frozen" months as the original; only which months count as locked is now yours. Messages, the verify check ("Locked months untouched"), the comparison table header and the Rules panel say "locked months".
- **Check:** `test_realign.py` — all existing checks pass on the default. New check: locking Nov instead of Jan keeps every Nov value exactly as the original, and Jan takes the revised 99 (split 59.4 / 39.6). Live page: Dec'26 locked → chip and server locked; unlocked → back to Jan / Feb.

### Security: the platform no longer runs on a public session key (P0, no calculation changes)
- **Problem:** `SESSION_SECRET` was not set on the live server, so 8010 (and 8000) fell back to `"dev-only-change-me"`, which is written in the code. Every login session, 30-day remember-me cookie and password-reset link was signed with it: anyone with the code could forge an admin session. **Proven before the fix:** a cookie signed with the default key for a made-up user was accepted (`/api/auth/me` → 200).
- **Fix:** `auth.security.session_secret()` is the one rule (8010's SessionMiddleware, remember-me and reset links all use it; AOP 8000 applies the same check). With `APP_ENV=production`, a missing, default or short (<32 chars) secret **stops the app from starting**. Development keeps the documented dev key with a warning. A 64-character random `SESSION_SECRET` and `APP_ENV=production` are now Windows user environment variables on the server. They are never printed and not in any file. `.env.example` lists the names.
- **After the restart:** the same forged cookie is rejected (401). Landing, 8010, 8000 and 5050 answer normally. **Everyone had to sign in again once**, and old remember-me cookies and reset links stopped working.
- **Tests:** new `tests/test_session_secret.py` (3 pass: production refuses empty/default/short, accepts strong; development falls back with a warning). `test_router_mount` / `test_calendar_mount` log in to the live server as the fixture user `planner1`, which fails on this server's database (401) with or without this change.

### BIS: Save says whether Sales Plan received the plan
- **Found on the re-check:** after "reloaded and saved", Sales Plan still had the 09:01 push. The Save left no trace, and BIS gave no sign: a push that sent nothing (AOP not synced on the page, or no rows) was silent, and a successful one looked the same as a failed one.
- **Now** the Save button always reports the outcome: "Saved ✓ — N growth rows sent to Sales Plan", "Saved in this browser only — NOT sent to Sales Plan: <reason>", or "Growth NOT sent to Sales Plan (status – sign in again)". A save that was redirected to the sign-in page counts as a failure. Failures are also shown on automatic saves.
- Checked in the sandbox (its push cannot reach Sales Plan): Save → "Growth NOT sent to Sales Plan (501)"; with no AOP → "NOT sent … no AOP synced".

### Landing (7800) now restarts itself — the whole suite stays reachable
- **Problem (user: "the whole server went down" → "permafix this issue"):** Landing stopped when the Claude session that had started it was restarted. Every app is opened through Landing, so every link died, although the servers behind it (8010, 8000, 5050, 8060, 8070, 8123) were all still running. Nothing watched Landing: its own watchdog restarts the other apps, not itself. The four "RS Planning - … Server" scheduled tasks had **never run** (last run 1999): they fire "at system start-up" but only "when the user is logged on", which Windows never meets. The BIS task also points at an old copy of BIS (`…\Buyers Input Sheet`).
- **Fix:** `Landing/keep_alive.py` starts Landing in the background (no console window, no new browser tab — `--no-browser`) whenever port 7800 is down. The new scheduled task **"RS Planning - Keep Alive"** (`Landing/install_keep_alive.ps1`, current user, no admin) runs it at sign-in and every 2 minutes. Landing's own watchdog then brings back any app that is down within 30 s.
- **Check:** after installing, the task started Landing (result 0). Landing was then stopped on purpose and came back by itself in **24 s**. `/` → 302 to sign-in, `/login` 200, and all six apps answer.
- Not changed: the four old never-firing tasks (disabling them needs an admin window) and the "RS Planning Landing" Startup shortcut, which is harmless — whichever starts Landing second just exits.

### BIS: making a department inactive keeps the division on its AOP target
- **Bug (found on the re-check after the reload):** LADIES reached Sales Plan 0.01–0.08 L a month under AOP (Mar −0.0725, Apr −0.0636, May −0.0800, Jun −0.0137 L). L_EW_BLOUSE had been made inactive by hand; its planned sales were simply dropped instead of passing to the other departments. The toggle also never saved, so Sales Plan only got the change on the next reload.
- **Fix:** making a department inactive or active again rescales the other unlocked, active departments of that division by one factor, so the division lands exactly on its AOP target. Each department keeps its growth relative to the others, and locked cells are untouched. The change then saves and pushes like any edit. A plan already saved off target (like the current one) is put back on target when BIS opens — locally only, since opening pushes nothing — and a message asks for one **Save**.
- **Check (sandbox that cannot push):** inactivate → LADIES gap 0 in all four months, MENS untouched, kurti/dupatta growth ratio unchanged, 1 push. Re-activate → 0, pushed. A stale saved plan 1.5 L off → 0 after opening, no push, message shown.

### Sales Plan PW/W and SOR Deviation: block read from the imported files; SOR laid out like PW/W
- **Change (user):** "similar format for SOR deviation just like PW/W Deviation, and instead of the manual search bar in PW/W I want an auto detect from the file imported so that there is sanctity between modules, make this happen in both". The user chose month columns in the file.
- **PW/W:** the BLOCK search box (91 month combinations) is gone. The PPO Cont % file now carries one column per TY month (DEPARTMENT | ARTICLE NAME | FINAL MRP | Mar'27 | Apr'27 | …). Sync reads those headers (Excel dates, "Mar'27", "Mar-27", "Mar 2027", "2027-03" all work), detects the block (4 months Mar'27–Jun'27 → MAMJ; months must be consecutive plan months) and shows it read-only. Phase 1 and Phase 2 always run on that block. Phase 2 uses each month's own MRP mix; Phase 1 uses the block average. **The current single-column PPO Cont %.xlsx is refused** with a message showing the new columns, until it is re-saved with month columns.
- **SOR:** the two drag-drop boxes are replaced by PW/W's "Sync from Folder" panel. Both files are read from `SalesPlan\SOR Deviation\` (`Sales Plan Cont %.xlsx`, `Stock PPO Cont %.xlsx`), their months are detected the same way and must match, and the block is shown. A red note appears if SOR's block differs from PW/W's. The upload endpoints are gone.
- The standalone Sales Plan server also serves the deviation routes at `/api/planning/deviation/*`, which the pages call.
- **Check** (`SalesPlan/backend/engines/test_deviation_blocks.py`, on temp copies): wide PPO file → MAMJ with per-month mix; old single-column file refused; SOR files with matching months → MAMJ and "same as PW/W"; files with different months refused.

### Sales Plan MRP Re-apportionment: LY sales from the sales engine; page works again
- **Change (user):** "LY actual sales will be taken from the sales engine which is embedded in all the other apps, only the new MRP structure will be given, making sure that there are no mismatches in the actual sales structure." Before, the page wanted an uploaded .xlsb/.xlsx of sales.
- **Now:** the engine reads LY Mar–Jun 2026 from the Calendar engine's own data-lake file, using the Calendar reader (5 Sep 2026 export, the one every app uses), at store × division × department × MRP × display × attribute × month. The only upload is the MRP Mapping Master. Every store × department × month is tied to the Calendar department sales Sales Plan reads: **2,12,799 cells, max difference 0.0 L, ₹56,646.33 L both sides**. Run is blocked if the tie ever breaks. The sales template download and the Historical Sales folder are gone.
- **Bug fixed:** the page's backend router was never mounted in the platform (or the standalone Sales Plan server), so the page could not load anything (the old "MRP Re-apportionment page 404"). It is mounted now at `/api/planning/mrp-reapportionment`.
- **Check** (`SalesPlan/backend/engines/test_mrp_reapportionment.py`): a synthetic MRP structure on real engine sales (MSE_R/N T-SHIRT H/S, two lowest MRPs discontinued) re-apportions 3,327 rows into 9,469 with all 190 store totals unchanged. A planted 0.02 L error is caught.

### Sales Plan Division Plan shows the BIS plan, Mar–Jun 2027 only
- **Change (user):** "LY base should be imported from the data source and static once loaded" and "show the plan shown in BIS and not any day further". Before, the LY base was a typed-over constant (KIDS 54,237.27 L, an annual figure hard-coded in `division_plan.py`), and the plan was spread over a full Apr'27–Mar'28 year.
- **Now:** the page reads the AOP publish that BIS last pushed growth on (else the live saved version; today Version 2, publish 112). Per division and month (Mar'27–Jun'27) it shows the **LY base** (the publish's base, Mar–Jun 2026 like-for-like, read-only) and the **plan** (the publish's division target — BIS spreads every division exactly onto it). Growth is plan ÷ LY − 1 on the period totals: KIDS +12.9%, LADIES +11.6%, MENS +9.3%, total ₹38,882.54 L → ₹43,184.66 L (+11.1%).
- Removed: the editable LY base / growth / FY-start inputs, Add Row, Calculate, the 12-month spread, and the page's "Use This Version" panel (it only fed this page). Change the plan in BIS. Export CSV exports these months.

### BIS: Period 19 V 26 / 25 V 26 = growth on the period totals
- **Bug (user):** L_EW_DUPATTA's Period 19 V 26 read +96.1% while its hover said the period total grew +62%. The cell averaged the four monthly %s (+261.6, +91.1, +31.9, −0.4); the hover summed the ₹. **Fix:** division, department and attribute Period cells now use the summed ₹ behind the hover: DUPATTA +62.6% / +22.2%.
- **Check:** all 239 Period cells across the Buyer's Plan, Department, Attribute and Division views equal the hover's "Period total" (sandbox copy that cannot push).

### BIS: inactive departments show only on the Inactive Depts sheet
- **Bug (user):** a department made inactive by hand still showed as a greyed row in the Buyer's Plan as well as on the Inactive Depts sheet. It (and an attribute whose departments are all inactive) now shows only on the Inactive sheet, where the same toggle re-activates it. Checked in the sandbox: L_EW_DUPATTA made inactive → gone from Buyer's Plan, on the Inactive sheet; re-activated → back.

## 2026-09-28

### BIS: 19 V 26 and 25 V 26 compare Mar–Jun 2026 with the same months earlier
- **Change (user's call):** the "26" side of both history columns is now **Mar–Jun 2026**, the same months as the plan LY, and the "25" base is Mar–Jun 2025. Before, April–June were 2025 against 2024, because the columns used Apr–Mar financial years. Months outside Mar–Jun are unchanged (Jul'25–Feb'26 and a year earlier). Together with the entry below, every Mar–Jun cell now reads 2019 → 2026 or 2025 → 2026 for the same month.
- **Bug fixed along the way:** BIS matched division names by substring, so "CONSIGNMENT" (it contains "men") was counted as MENS. It added up to 7.2 L a month to MENS's 2025 base. Divisions now match on whole words.
- **Effect (MAMJ, same stores):** 19 V 26 MENS +26.0%, LADIES +47.0%, KIDS +25.9%; 25 V 26 MENS +7.5%, LADIES +15.0%, KIDS +14.4%. The same stores are used every month: 31 for 19 V 26 and 120 for 25 V 26. ML_JOGGERS: 0.62 → 1.76 Cr (19 V 26) and 4.75 → 5.49 Cr (25 V 26).
- **Check:** all 2,861 division and department × month cells (Mar–Jun, both columns) and the store counts equal an independent recompute from the raw file (max 0.005 L, planted 0.02 L caught). The hover labels follow (e.g. "Apr'25 → Apr'26"). Browsers re-sync by themselves (`hlflcohort19jjw`).

### BIS: 19 V 26 uses March 2019
- **Change (user's call):** the 19 V 26 base is now calendar 2019, so March is **Mar 2019**. Before, it was FY19's March, Mar 2020 (the lockdown month). Apr–Jun were already 2019. Buyers judge history on the same months as the plan period. 25 V 26 is unchanged.
- **Effect, ML_JOGGERS (same 31 stores):** the base for March goes from 0.1137 to 0.1696 Cr, and the Mar–Jun base from 0.56 to 0.62 Cr. The hover now reads "Mar'19 → Mar'26". Every browser re-syncs its history by itself (version tag `hlflcohort19`).
- **Check:** all 8 ML_JOGGERS 19 V 26 / 25 V 26 month values equal an independent recompute from the raw file.

### BIS: zero-sales departments, re-seed and clearer history hover (follow-up to the department LY fix)
- **Bug found after the reload:** a department with no sales in a month (e.g. winter lines in April) was missing from the new per-department figures, and BIS fell back to the old share estimate for it — MENS April's base read 43.16 Cr instead of 39.10, so BIS seeded MENS Apr at −0.35% and sent plans 51–405 L below AOP. **Fix:** once the sync has delivered a month, a missing department counts as 0. The seed fingerprint carries a version tag, so every browser re-seeds once (locked cells kept).
- **Hover on 19 V 26 / 25 V 26:** each line now names the real months and says it is same-store history, not the plan LY — e.g. ML_JOGGERS "Apr'19 Rs 0.13 Cr → Apr'25 Rs 0.31 Cr, same 31 stores". Before it said "FY19 → FY26", which read like the LY Actual Sales column (Mar–Jun 2026, 148 stores). Note: "19 V 26" compares Apr'19–Mar'20 with Apr'25–Mar'26; "25 V 26" compares Apr'24–Mar'25 with Apr'25–Mar'26.
- **Check (sandbox copy that cannot send to Sales Plan):** every division × month base = the division's actual total; all 12 plans = AOP target (max 2.5e-12 L); ML_JOGGERS LY 2.33 / 1.69 / 1.44 / 1.31 Cr at 7.52 / 10.00 / 10.00 / 9.97 %.

### BIS: departments show their own LY sales
- **Problem:** BIS only received division totals from its sales sync, so each department's monthly LY was estimated as its FY26 share of the division × the division base — every department took the division's seasonality. ML_JOGGERS MAMJ showed ₹6.3 Cr; its actual in the 148 plan stores is ₹6.77 Cr (Mar 2.3303 / Apr 1.6906 / May 1.4406 / Jun 1.3082 Cr).
- **Fix:** the sales sync also returns each department's LY per AOP month for the same 148 plan stores (`sec_actual_ly`, ₹ Cr to 6 dp); department rows, the magnifier and seeding use it (the share estimate stays as a fallback). The seed fingerprint includes a hash of these figures, so a change re-seeds with locked cells kept and every division still plans exactly to AOP. Saved browser copies without the new figures re-sync by themselves.
- **Check:** all 746 KIDS / LADIES / MENS department × month cells equal an independent recompute from the raw file (max 0.0022 L, planted 0.02 L caught). BIS departments sum to the division totals exactly for MENS and KIDS; LADIES is 0.02–0.03 L short from four tiny departments not in BIS's list (three LS_PC personal-care lines, LW_U_CORD SETS).
- The 19 V 26 / 25 V 26 history figures were re-verified at the same time: all 16 ML_JOGGERS values equal the recompute exactly (19 V 26 March = Mar 2020, FY19's March, by design).

### Suite revamp: "Ink and paper" look, three sister schemes, calmer screens
- **New colour schemes** (Landing → Theme; all apps follow): **Ink and paper** (the alternate design's ink chrome, deep teal accent, warm paper page — now the default and the saved choice), **Ink and clay** (terracotta), **Slate and harbour** (harbour blue), **Moss and linen** (moss green). All four meet WCAG AA for every text / fill pair (button text ≥ 8:1, accent on page ≥ 5:1). The five earlier schemes stay in the picker.
- **Type:** the shared theme script loads IBM Plex Sans (text), IBM Plex Mono and Fraunces (page titles) and exposes `--st-font-body / --st-font-mono / --st-font-display`; every app's base font now reads `var(--st-font-body, <old font>)`. Numbers stay in Plex Sans tabular figures so dense grids keep their widths.
- **Calmer screens (styling only — no logic, links or app-to-app navigation changed):**
  - Landing: serif title, one-line descriptions, flat core cards joined by arrows as a chain, slimmer tool cards.
  - Buyer's Input: the per-row "Active" pill is a quiet status dot (still the same on/off button), neutral section headers, flat KPI tiles, serif wordmark.
  - AOP: serif titles, flat cards, the stacked filter bars read as one area, Review growth grid with a light head and pastel month chips (the dense Output pivot keeps its dark head, whose controls are built for it).
  - Sales Plan, Calendar, NSO, Re-Aligner, Listing / Delisting Analyser: serif titles / wordmarks; Listing KPI captions wrap instead of running past the card.
- Checked in the browser: Landing, BIS (row switch still toggles), AOP home / Review / Results / Output (contrast audit clean on Review), Sales Plan home, Listing, Re-Aligner, NSO. Calendar builds; its screens need a sign-in to view.

### Cluster-wise actual vs reindexed report (no code change)
- Excel report (cluster × month, Jan–Aug) built from the Calendar's **day-wise** tables: actual by last-year month vs reindexed by plan month, shift, shift % and plan-day coverage, plus Detail, Conservation and Notes sheets.
- Finding: the **month-wise** reindex moves each last-year month whole into one plan month, so month by month it equals the actuals — real festival and weekday shifts across month boundaries only show at day level.
- Result (data to 27 Aug'26): every cluster conserves exactly (0.00 L); sales move only between Feb and Mar (e.g. N. EAST - PUJA +66 / −66 L, JH + MP + CG +43 / −43 L, JAMMU + RJ +29 / −29 L); Apr–Aug ≈ 0; Aug'27 87% covered. Sep–Nov (Puja / Diwali) need a newer day-wise export and a manual Run Reindex. ₹296.53 L of unclustered stores (closed / HO / warehouse / sites) is not calendarised.

### Nightly accuracy check of the calendarised sales
- Committed `ab9fabe`.
- New job `sync/calendar_check_sync.py`, run by the nightly sync right after the Calendar reindex (and by AOP's "Sync into database" button). Read-only; ~45 s; tolerance 0.01 L per cell:
  1. saved actuals = a fresh read of the raw month-wise export (store × division × month);
  2. saved reindexed = an independent recompute (each cluster's month map rebuilt from the saved day pairs);
  3. conservation: reindexed total = actual total per store × division;
  4. department tables = main tables (actual and reindexed);
  5. every cluster's day map covers each plan day once and reuses no LY day;
  6. every trading store with sales has a calendar cluster (closed stores, HO, warehouses and sites are listed, not shifted — 316 L on 28 Sep);
  plus a self-test: a planted 0.02 L error must be caught.
- A failure marks the run failed with the reason and keeps the per-check detail (`sync/common.py` now stores detail on failure too). The **Sales Sync** page shows "Accuracy check passed 8/8" (or FAILED) under the last sync, with each check on hover.
- First run 28 Sep 12:21: 8/8 pass, every difference 0.0 L.
- Also fixed `sync/test_calendar_reindex_sync.py`, broken by `267d1d6` (snapshot save gained a `suffix` argument).

### Deep check after the department split (no code change)
- 17 of 19 checks pass at 0.01 L (planted 0.02 L errors caught). Calendar department snapshots = totals (0.000000 L); AOP live = V2; BIS, Sales Plan, Attribute Master (DB = file, 978) and Listing / Delisting Analyser all on the new department names; 13 test suites pass.
- After BIS was opened at 12:07 it pushed the new names to Sales Plan (792 rows, AOP 112). Sales Plan now applies exactly AOP's growth (to 0.0003 pp); its SSG plan meets the AOP target within 0.05 L in Mar–May'27 and 0.92–1.16 L in Jun'27.
- The remaining difference is entirely V2's saved LY base vs today's Calendar data (Mar–May ≤ 0.045 L, likely V2's 2-decimal store rows; Jun'27 = the ODISHA calendar re-save). A new AOP version made live would bring both to zero.

### Split departments adopted across the suite — `7c0a1e2` (core), `f682b5d` (additional apps + rename), `4040f68` (attribute master DB)
The data lake's 5 Sep export re-classified six departments back to 2019; the parts add up exactly to the old department (store × month) and division totals are unchanged.

| Old | New |
|---|---|
| MSE_PYJAMA | MSE_HSR PYJAMA, MSE_TXTL PYJAMA |
| KB_T-SHIRT H/S | KB_R/N T-SHIRT H/S, KB_POLO T-SHIRT H/S |
| KB_BERMUDA | KB_HSR BERMUDA, KB_TXTL BERMUDA |
| LW_L_PALAZZO | LW_L_WES PALAZZO, LW_L_ETH PALAZZO |
| LW_L_JEGGING | LW_L_DNM JOGGER, LW_L_WVN JOGGER |
| L_IN_BRA | L_IN_BRA (smaller), L_IN_SPRT BRA |

- **BIS:** new sections (season inherited, FY26 LY split exactly), sales file re-pinned to the 5 Sep export so LY, 19 V 26 / 25 V 26 history and sell-through come from the new names. A saved plan or version on the old names hands each old department's growth, AOP seed, lock and hide state to its parts once, then saves so Sales Plan switches too. Division LY unchanged (388.87 Cr). Check: `node test_dept_split.js`.
- **Sales Plan:** master list on the new names with the right season (the auto-registered REGULAR copies removed); MRP plan split and department active states carried to the parts.
- **Attribute Master (`att master.xlsx`):** the 9 missing new departments added with their old department's section and season, the 5 old names removed (978 rows, one per department; ~618k empty formatted rows dropped).
- **Attribute Master in the database (`masterdata.attribute_master`):** loaded on the user's go-ahead. The table did not exist before — Sales Plan's attribute correction had been falling back to the Excel file — so the loader created it with the 978 rows and no old rows existed to delete. Sales Plan now reads the table (same content). `test_attribute_master.py` expects 978 in both.
- **Listing / Delisting Analyser** (renamed from "Listing / Delisting" on Landing, in the app and in the Re-Aligner): listing history hands each old department's flags to its parts for the months before the listing sheets switched names (Jan'26); the day-wise cache splits an old department's days by that store's month split from the month-wise export (exact per store × month) until a day-wise export with the new names lands. Sales, seasonality and suggestions rebuilt.
- **Verified:** BIS shows the new departments with LY, both history growths and sell-through, and no old names; a saved plan's migration gives each part its old department's exact growth and AOP seed. Listing's split day-wise sales equal the month-wise export in every store × month Jan'24–Jul'26 (max 0.002 L); listing history, sales, seasonality, windows and suggestions carry only the new names (the old ones appear only in the cache's split trace). Suggestions rebuilt: 338 delist, 155 relist.
- **Re-Aligner:** its plan already uses the new names; it reads the rebuilt Listing files and the updated Attribute Master.
- **NSO Distributor:** no names of its own — it uses the uploaded Sales Plan export (new names) and Attribute Master (upload the updated one).

### BIS: smoother section / attribute lock — `7042878`
- One padlock drawing for both states (was a text "○" swapping to a 🔒 emoji of a different size, so the cell jumped). The shackle drops when locked and lifts when unlocked, with a short pop; the growth input tints amber while locked. Animations play even though the table re-draws on each toggle, and are off for reduced-motion users. The button is keyboard-operable and keeps focus after the re-draw.

### Sales Plan uses AOP's 148-store LFL rule for SSG — `9f827f4`
- **Before:** Sales Plan's SSG stores = tag ends with "- Stores" + an ANG override = **121** stores, so its SSG totals could never equal AOP (KIDS Apr'27 ₹2,575 L vs ₹3,108 L).
- **Now:** `store_master.is_ssg` calls AOP's own `engine_v3.auto_tag` (trading store, opened by 31 Dec before the LY window) = **148** stores, the same set AOP and BIS plan on. The 27 added stores are the FY26 Q1–Q3 openings (Mar–Oct 2025); none dropped. ANG override removed (already inside the 148).
- **Check:** SSG LY = AOP base within 0.04 L for Mar–May'27 (e.g. KIDS Apr'27 2,825.51 vs 2,825.49 L); Jun'27 is ~1 L off per division (the known V2 ODISHA Jun'27 calendar difference). Every department with BIS growth plans at exactly +10.0% in Apr–Jun, as in AOP. Missing ref stores 134 → 106.
- **Still short of AOP TY by ~1–1.5%:** departments the data lake names differently from BIS get no growth (e.g. KB_R/N T-SHIRT H/S vs BIS KB_T-SHIRT H/S, MSE_HSR/TXTL PYJAMA vs MSE_PYJAMA, LW_L_WES/ETH PALAZZO vs LW_L_PALAZZO) — needs a department mapping decision.

### BIS: history hover not showing — `0b6f95e`
- **Problem:** the 19 V 26 / 25 V 26 hover and header store counts stayed blank in a browser that had opened BIS before `267d1d6`. BIS keeps the history in the browser (`ck_lfl_growth`) and only re-fetched it when the server's data version changed, so the old copy (no store counts, no ₹ values) was kept.
- **Fix:** a saved copy without store counts is treated as out of date and re-synced on open. Verified by planting an old copy and reloading: headers show "19 V 26 · 31 st" / "25 V 26 · 101–120 st", cells show the per-month ₹ Cr and period total.

### Sales Plan reads LY sales from the Calendar; Buyer's Input drives department status — `267d1d6`
- **Department Master:** "Sync from AOP Forecaster" is now **"Sync from Buyer's Input"**. KIDS / LADIES / MENS departments are active when live BIS plans them (96 / 57 / 39), inactive otherwise; GM / RETAIL are left as set. The AOP division-target loader stays as a small "Load AOP division targets" link.
- **Growth Matrix:** inactive departments are greyed, tagged INACTIVE and read-only; column fill skips them.
- **Sales Sync page:** the manual "Sync Sales" button and the Excel import (MAMJ'26, month locks, admin unlock) are removed. The page is read-only and shows the last nightly sync and the new department-level tables.
- **Sales Plan actuals:** store × department LY sales now come from the Calendar's department snapshots, refreshed nightly by `sync/calendar_reindex_sync.py` — **reindexed sales = plan base**, actual sales alongside. New snapshot kinds `actual_dept` / `trend_shifted_dept` (migration `d9f3b2a7c1e5`). They sum exactly to the existing month-wise snapshots (0.000000 L over 20,569 cells). First full plan built: 425 stores, Mar–Aug'27.
- 29 departments with sales but missing from Sales Plan's department list were auto-registered (incl. ₹36.5 Cr MENS pyjamas).
- **BIS 19 V 26 / 25 V 26:** header shows the like-for-like store count (per-month counts on hover); cell hover shows both years' ₹ Cr per month, store count and period total.

---

## 2026-09-26 — Planning-chain audit fixes — `5f551d7`

Audit tolerance 0.01 L per cell and total; every check also had to catch a planted 0.02 L error. Live AOP = Version 2 (publish 112).

**BIS**
- AOP growth is kept unrounded (was 2 dp → up to 0.15 L/cell off target); display stays 2 dp. Re-balancing no longer re-rounds.
- Seeding uses the LY of **active** departments only (hidden departments had left divisions up to 528.82 L short).
- Reopening keeps the buyer's edits: BIS re-seeds only when the AOP version changes (locked cells kept); "Re-seed plan" is the full reset.
- Pushes to Sales Plan only months BIS actually records, only once AOP is applied, stamped with the AOP publish id; a failed push is shown to the user. One push per AOP apply (was two).

**Calendar**
- Cluster names are case-insensitive: the last-saved spelling wins across all cluster tables (`adopt_cluster_spelling`); "Kashmir" → "KASHMIR".
- Month-cache key now includes the store → cluster map, so a renamed cluster isn't served stale months.

**AOP Forecaster**
- Review grid: fixed column widths, plain "All months" column, month selector; Results follow the same month pick.
- Store rows kept at 4 dp; "Base Calendar" label shows both calendar ids.
- Reindexed-base preview counts DND / CDIT / CONSIGNMENT in the division shares.
- **Lock to Planning:** locking a deleted / unsaved version now refuses with a message (it used to silently lock the latest saved version).

**Sales Plan**
- Plan engines read the live BIS growth on P1/P2 (months BIS doesn't record are hidden); GM / RETAIL stay editable.
- Division Plan: AOP months land exactly on the AOP target; fixed the Apr–Mar plan running Jul–Jun; Export CSV exports the plan on screen.

**Landing**
- Added the missing `/api/config/buyer-department-growth` route, so BIS growth reaches Sales Plan through the shared address.

### Known open items (reported, awaiting a decision)
- ~~Sales Plan SSG uses 121 stores~~ — fixed 28 Sep (`9f827f4`, 148 stores).
- NON FOOD: Sales Plan files it under RETAIL, AOP under GM.
- MRP Re-apportionment page returns 404.
- V2's Mar'27 base is not festival-shifted (141 L, accepted); 38 KLM departments have no BIS growth.
