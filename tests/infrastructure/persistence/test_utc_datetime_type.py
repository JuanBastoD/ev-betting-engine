from datetime import datetime, timedelta, timezone

import pytest

from src.infrastructure.persistence.models import UTCDateTime

_TYPE = UTCDateTime()


def test_process_bind_param_passes_through_none() -> None:
    assert _TYPE.process_bind_param(None, dialect=None) is None


def test_process_bind_param_converts_non_utc_aware_datetime_to_utc() -> None:
    minus_three = timezone(timedelta(hours=-3))
    value = datetime(2026, 8, 15, 17, 0, tzinfo=minus_three)

    bound = _TYPE.process_bind_param(value, dialect=None)

    assert bound == datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc)


def test_process_bind_param_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _TYPE.process_bind_param(datetime(2026, 8, 15, 17, 0), dialect=None)


def test_process_result_value_passes_through_none() -> None:
    assert _TYPE.process_result_value(None, dialect=None) is None


def test_process_result_value_reattaches_utc_to_a_naive_value() -> None:
    # This is exactly what SQLite/aiosqlite hands back after stripping tzinfo.
    naive = datetime(2026, 8, 15, 20, 0)

    restored = _TYPE.process_result_value(naive, dialect=None)

    assert restored == datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc)


def test_process_result_value_normalizes_a_non_utc_aware_value() -> None:
    # This is what asyncpg/Postgres hands back for TIMESTAMPTZ.
    minus_three = timezone(timedelta(hours=-3))
    value = datetime(2026, 8, 15, 17, 0, tzinfo=minus_three)

    restored = _TYPE.process_result_value(value, dialect=None)

    assert restored == datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc)
