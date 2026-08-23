import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "..", "Tentative AOP Forecaster"))

import datetime


def test_planner_can_create_list_get_delete_calendar(planner_client):
    payload = {
        "id": 9991112223, "name": "Test Calendar A", "refYear": 2030, "futYear": 2031,
        "savedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(), "engine": "v2",
        "clusters": [{
            "name": "TestCluster", "region": "north",
            "festivals": [{"id": 1, "name": "Test Festival", "refDate": "2030-03-01", "futDate": "2031-03-05",
                           "pre": 2, "core": 1, "post": 3}],
        }],
        "dayMap": {"TestCluster": [["2030-01-01", "2031-01-01"], ["2030-01-02", "2031-01-02"]]},
    }
    r = planner_client.post("/api/calendar/calendar-library", json=payload)
    assert r.status_code == 200, r.text

    r = planner_client.get("/api/calendar/calendar-library")
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()]
    assert 9991112223 in ids

    r = planner_client.get("/api/calendar/calendar-library/9991112223")
    assert r.status_code == 200
    detail = r.json()
    assert detail["clusters"][0]["festivals"][0]["name"] == "Test Festival"
    assert detail["dayMap"]["TestCluster"] == [["2030-01-01", "2031-01-01"], ["2030-01-02", "2031-01-02"]]
    assert detail["mappingSummary"] == [{"cluster": "TestCluster", "totalDays": 2}]

    r = planner_client.delete("/api/calendar/calendar-library/9991112223")
    assert r.status_code == 200
    r = planner_client.get("/api/calendar/calendar-library/9991112223")
    assert r.status_code == 404


def test_buyer_cannot_create_calendar(buyer_client):
    payload = {"id": 9991112224, "name": "X", "refYear": 2030, "futYear": 2031,
               "savedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "clusters": [], "dayMap": {}}
    r = buyer_client.post("/api/calendar/calendar-library", json=payload)
    assert r.status_code == 403
