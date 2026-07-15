from datetime import date, datetime, timedelta

import polars as pl
from tqdm.auto import tqdm

import nb_utils.options as options
from nb_utils.sql import _notebook_ns


def run_query(query, connection=None, params=None):
    """Выполняет запрос через соединение любого типа (по умолчанию — активное)."""
    cfg = options.resolve(connection)
    if cfg.type == "bigquery":
        from nb_utils import bigquery
        return bigquery.run_query(query, cfg, params)
    if cfg.type == "redshift":
        from nb_utils import redshift
        return redshift.run_query(query, cfg, params)
    raise TypeError(f"Неизвестный тип соединения: {cfg.type!r}")


def _to_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _periods(start, end, step_days):
    step = timedelta(days=step_days)
    cur = start
    while cur < end:
        win_end = min(cur + step, end)
        yield cur, win_end
        cur = win_end


def run_query_by_period(query, start_date, end_date, step_days=7, connection=None, params=None):
    """Выполняет запрос по окнам дат и склеивает результаты в один DataFrame.

    В шаблоне доступны {{ period_start }} и {{ period_end }} (ISO-строки дат).
    Окна полуоткрытые [period_start, period_end), поэтому фильтр пиши как
        where dt >= '{{ period_start }}' and dt < '{{ period_end }}'
    end_date в выборку не входит. Ctrl+C возвращает собранное к этому моменту.
    Запросы без результата (DML) пропускаются; если результатов нет — None.
    """
    start, end = _to_date(start_date), _to_date(end_date)
    if start >= end:
        raise ValueError(f"start_date {start} должен быть меньше end_date {end}")
    base = {**(_notebook_ns() or {}), **(params or {})}
    windows = list(_periods(start, end, step_days))
    dfs = []
    try:
        with tqdm(windows, desc="Периоды", unit="окно") as pbar:
            for win_start, win_end in pbar:
                pbar.set_postfix_str(f"{win_start} → {win_end}")
                df = run_query(query, connection, {
                    **base,
                    "period_start": win_start.isoformat(),
                    "period_end": win_end.isoformat(),
                })
                if df is not None:
                    dfs.append(df)
    except KeyboardInterrupt:
        print(f"🚫 Прервано; собрано окон: {len(dfs)} из {len(windows)}")
    if not dfs:
        return None
    return pl.concat(dfs, how="vertical_relaxed")
