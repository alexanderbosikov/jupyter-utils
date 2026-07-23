from datetime import date, datetime, timedelta

import polars as pl
from tqdm.auto import tqdm

import nb_utils.options as options
from nb_utils.sql import _notebook_ns, prepare_query


def _conn_id(cfg):
    """Стабильный идентификатор соединения для ключа кэша."""
    if cfg.type == "redshift":
        return f"rs:{cfg.host}:{cfg.database}"
    if cfg.type == "bigquery":
        return f"bq:{cfg.project_id}"
    return cfg.type


def _dispatch(query, cfg, params, verbose):
    if cfg.type == "bigquery":
        from nb_utils import bigquery
        return bigquery.run_query(query, cfg, params, verbose)
    if cfg.type == "redshift":
        from nb_utils import redshift
        return redshift.run_query(query, cfg, params, verbose)
    raise TypeError(f"Неизвестный тип соединения: {cfg.type!r}")


def run_query(query, connection=None, params=None, cache=None, cache_ttl=None,
              refresh=False, verbose=True):
    """Выполняет запрос через соединение любого типа (по умолчанию — активное).

    Кэш (переживает рестарт kernel; ключ — хэш отрендеренного SQL + соединение):
    - cache: кэшировать результат на диск. None → config.cache_default.
    - refresh=True: игнорировать кэш и перезаписать (когда данные в БД обновились).
    - cache_ttl: TTL в секундах. None → config.cache_ttl_sec; <=0 — без истечения.
    Смена текста запроса/параметров меняет ключ автоматически. DML (df=None) не кэшируется.
    """
    cfg = options.resolve(connection)
    use_cache = options.config.cache_default if cache is None else cache
    if not use_cache:
        return _dispatch(query, cfg, params, verbose)

    from nb_utils import cache as _cache
    rendered = prepare_query(query, params)
    conn_id = _conn_id(cfg)
    ttl = options.config.cache_ttl_sec if cache_ttl is None else cache_ttl
    if not refresh:
        hit = _cache.load(rendered, conn_id, ttl)
        if hit is not None:
            df, meta = hit
            if verbose:
                print(f"✓ из кэша: {meta['rows']:,} строк ({_cache._fmt_age(meta['saved_at'])}); "
                      "refresh=True — перезапросить")
            return df
    df = _dispatch(query, cfg, params, verbose)
    if df is not None:
        _cache.save(rendered, conn_id, df)
    return df


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


def run_query_by_period(query, start_date, end_date, step_days=7, connection=None,
                        params=None, cache=None, cache_ttl=None, refresh=False):
    """Выполняет запрос по окнам дат и склеивает результаты в один DataFrame.

    В шаблоне доступны {{ period_start }} и {{ period_end }} (ISO-строки дат).
    Окна полуоткрытые [period_start, period_end), поэтому фильтр пиши как
        where dt >= '{{ period_start }}' and dt < '{{ period_end }}'
    end_date в выборку не входит. Ctrl+C возвращает собранное к этому моменту.
    Запросы без результата (DML) пропускаются; если результатов нет — None.

    Кэш (см. run_query): кэшируется итоговый склеенный результат; ключ — запрос +
    окно (start/end/step) + соединение. Прочие jinja-переменные из ноутбука в ключ
    не входят — при их смене используй refresh=True.
    """
    start, end = _to_date(start_date), _to_date(end_date)
    if start >= end:
        raise ValueError(f"start_date {start} должен быть меньше end_date {end}")

    use_cache = options.config.cache_default if cache is None else cache
    cache_sql = f"{query}\n-- period {start}:{end}:{step_days}"
    conn_id = None
    if use_cache:
        conn_id = _conn_id(options.resolve(connection))
        if not refresh:
            from nb_utils import cache as _cache
            ttl = options.config.cache_ttl_sec if cache_ttl is None else cache_ttl
            hit = _cache.load(cache_sql, conn_id, ttl)
            if hit is not None:
                df, meta = hit
                print(f"✓ из кэша: {meta['rows']:,} строк ({_cache._fmt_age(meta['saved_at'])}); "
                      "refresh=True — перезапросить")
                return df

    base = {**(_notebook_ns() or {}), **(params or {})}
    windows = list(_periods(start, end, step_days))
    dfs = []
    total_rows = 0
    try:
        with tqdm(windows, desc="Периоды", unit="окно") as pbar:
            for win_start, win_end in pbar:
                pbar.set_postfix_str(f"{win_start} → {win_end}, строк: {total_rows:,}")
                df = run_query(query, connection, {
                    **base,
                    "period_start": win_start.isoformat(),
                    "period_end": win_end.isoformat(),
                }, cache=False, verbose=False)
                if df is not None:
                    dfs.append(df)
                    total_rows += len(df)
                    pbar.set_postfix_str(f"{win_start} → {win_end}, строк: {total_rows:,}")
    except KeyboardInterrupt:
        print(f"🚫 Прервано; собрано окон: {len(dfs)} из {len(windows)}")
    if not dfs:
        return None
    result = pl.concat(dfs, how="vertical_relaxed")
    if use_cache:
        from nb_utils import cache as _cache
        _cache.save(cache_sql, conn_id, result)
    return result
