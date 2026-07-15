import datetime as dt

import polars as pl
import pytest

import nb_utils.query as q


def test_periods_exact_multiple():
    ps = list(q._periods(dt.date(2026, 1, 1), dt.date(2026, 1, 15), 7))
    assert ps == [
        (dt.date(2026, 1, 1), dt.date(2026, 1, 8)),
        (dt.date(2026, 1, 8), dt.date(2026, 1, 15)),
    ]


def test_periods_remainder_window_shorter():
    ps = list(q._periods(dt.date(2026, 1, 1), dt.date(2026, 1, 10), 7))
    assert ps[-1] == (dt.date(2026, 1, 8), dt.date(2026, 1, 10))


def test_run_query_by_period_concats_and_injects(monkeypatch):
    calls = []

    def fake_run_query(query, connection=None, params=None, verbose=True):
        assert verbose is False  # цикл глушит рутинные принты клиентов
        calls.append((params["period_start"], params["period_end"]))
        return pl.DataFrame({"win": [params["period_start"]]})

    monkeypatch.setattr(q, "run_query", fake_run_query)
    df = q.run_query_by_period("select ...", "2026-01-01", "2026-01-15", step_days=7)
    assert calls == [("2026-01-01", "2026-01-08"), ("2026-01-08", "2026-01-15")]
    assert df["win"].to_list() == ["2026-01-01", "2026-01-08"]


def test_run_query_by_period_accepts_dates_and_extra_params(monkeypatch):
    seen = {}

    def fake_run_query(query, connection=None, params=None, verbose=True):
        seen.update(params)
        return None

    monkeypatch.setattr(q, "run_query", fake_run_query)
    df = q.run_query_by_period(
        "select ...", dt.date(2026, 1, 1), dt.date(2026, 1, 3),
        step_days=30, params={"uid": 42},
    )
    assert df is None  # все окна вернули None (DML)
    assert seen["uid"] == 42
    assert seen["period_end"] == "2026-01-03"  # окно обрезано по end_date


def test_run_query_by_period_bad_range():
    with pytest.raises(ValueError):
        q.run_query_by_period("select 1", "2026-01-02", "2026-01-01")
