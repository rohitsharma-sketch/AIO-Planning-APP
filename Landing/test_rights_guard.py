"""python test_rights_guard.py - each guarded button's real path maps to its right (Landing GUARDED, 2026-09-30)."""
from landing_server import Handler


def need(method, path):
    return next((r for m, rx, r in Handler.GUARDED if m == method and rx.search(path.split('?')[0])), None)


assert need("POST", "/api/launch-all") == need("POST", "/api/shutdown-all") == "servers"
assert need("POST", "/api/config/db-sync") == need("POST", "/api/aop/api/config/db-sync") == "data_sync"
assert need("GET", "/api/config/db-sync/status") is None and need("POST", "/api/config/db-sync/status") is None
assert need("POST", "/api/aop/api/promote-aop-targets?session_id=x") == "aop_publish"
assert need("POST", "/api/aop/api/unlock-aop-targets") == need("POST", "/api/aop/api/promote-aop-version/7") == "aop_publish"
assert need("POST", "/api/calendar/salesdata/reindex/start") == "calendar_reindex"
assert need("POST", "/api/calendar/salesdata/reindex/cache-status") is None     # a read, not a run
assert need("POST", "/realigner/api/run") == need("POST", "/realigner/api/rephase") == "realigner_run"
assert need("POST", "/realigner/api/rephase-overrides") is None and need("POST", "/realigner/api/locks") is None
assert need("POST", "/api/suite-theme") == "suite_theme" and need("GET", "/api/suite-theme.js") is None
assert need("POST", "/api/config/buyer-department-growth") == need("POST", "/buyer/api/config/buyer-department-growth") == "buyer_push"
assert need("GET", "/api/config/buyer-department-growth") is None              # Sales Plan's read stays open
assert need("POST", "/api/planning/mrp-reapportionment/mapping/upload") == "mrp_master"
assert need("GET", "/api/planning/mrp-reapportionment/mapping/download") is None   # export stays open
assert need("POST", "/api/planning/mrp-reapportionment/run") is None
assert need("POST", "/buyer/api/config/bis-plan-versions") == need("POST", "/buyer/api/planner/factor-table") == "buyer_push"
assert need("GET", "/buyer/api/config/bis-plan-versions") is None             # reading versions stays open
# a BIS buyer (2026-10-15): what they may reach
G, W = Handler._BUYER_GET.match, Handler._BUYER_WRITE.match
assert G("/buyer/") and G("/buyer/api/sync/sales") and G("/api/auth/me") and G("/api/bis/submissions") and G("/api/suite-theme.js")
assert not G("/aop/") and not G("/calendar/") and not G("/planning/") and not G("/api/planning/dept-sales/plan-summary") and not G("/nso/")
assert W("/api/bis/submissions") and W("/api/auth/logout") and W("/buyer/api/export/xlsx")
assert not W("/buyer/api/config/bis-plan-versions") and not W("/api/config/buyer-department-growth") and not W("/api/bis/submissions/x/review")
print("all rights-guard checks passed")
