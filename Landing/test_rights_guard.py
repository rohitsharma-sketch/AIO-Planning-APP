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
print("all rights-guard checks passed")
