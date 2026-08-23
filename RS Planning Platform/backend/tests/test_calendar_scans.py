import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calendar_engine.scans import get_salesdata_link, get_salesdata_link_daywise


def test_get_salesdata_link_returns_expected_shape():
    result = get_salesdata_link(force_refresh=True)
    assert result["ok"] is True
    assert "months" in result and "stores" in result and "dateRange" in result
    assert isinstance(result["months"], list)


def test_get_salesdata_link_daywise_returns_expected_shape():
    result = get_salesdata_link_daywise(force_refresh=True)
    assert result["ok"] is True
    assert "gaps" in result  # daywise-only field, month-wise link has no gap detection
    assert isinstance(result["gaps"], list)
