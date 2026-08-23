from db.base import SessionLocal
from db.editor import put_growth


def test_put_growth_logs_a_data_change(test_user):
    from sqlalchemy import select
    from db.models.audit import DataChange

    session = SessionLocal()
    before = session.execute(select(DataChange)).scalars().all()
    put_growth(session, [{"row_key": "RETAIL", "values": {"May'27": 12.5}}], test_user.id, "planner")
    after = session.execute(select(DataChange)).scalars().all()
    assert len(after) == len(before) + 1
    assert after[-1].old_value is None
    assert after[-1].new_value == "12.5"

    # revert
    put_growth(session, [{"row_key": "RETAIL", "values": {"May'27": None}}], test_user.id, "planner")
    session.close()


def test_non_admin_non_approver_gets_403(client, test_user):
    client.post("/api/auth/login", json={"username": "test_planner", "password": "testpass123"})
    r = client.get("/api/audit/data-changes")
    assert r.status_code == 403
