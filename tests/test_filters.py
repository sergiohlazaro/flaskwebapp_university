from datetime import UTC, datetime, timedelta

import pytest

from website.filters import localtime, timeago

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize("delta,expected", [
    (timedelta(seconds=30), "hace un momento"),
    (timedelta(minutes=5), "hace 5 min"),
    (timedelta(hours=2), "hace 2 h"),
    (timedelta(days=1, hours=1), "ayer"),
    (timedelta(days=3), "hace 3 días"),
])
def test_timeago(delta, expected):
    assert timeago(NOW - delta, now=NOW) == expected


def test_timeago_old_dates_show_short_date():
    assert timeago(NOW - timedelta(days=10), now=NOW) == "07/11/2026"


def test_timeago_accepts_naive_datetimes_as_utc():
    naive = (NOW - timedelta(minutes=5)).replace(tzinfo=None)
    assert timeago(naive, now=NOW) == "hace 5 min"


def test_localtime_converts_utc_to_madrid():
    assert localtime(datetime(2026, 7, 1, 10, 0, tzinfo=UTC)) == "01/07/2026 12:00"


def test_localtime_winter_and_naive():
    assert localtime(datetime(2026, 11, 17, 21, 30)) == "17/11/2026 22:30"


def test_filters_handle_none():
    assert localtime(None) == ""
    assert timeago(None) == ""
