import atexit
import time

import redshift_connector
import polars as pl
from tqdm.auto import tqdm
import nb_utils.options as options
from nb_utils.sql import prepare_query

_CHUNK_SIZE = 10000

# ключ — параметры подключения, значение — (соединение, время последнего использования)
_pool: dict[tuple, tuple] = {}


def _pool_key(cfg):
    return (cfg.host, cfg.port, cfg.database, cfg.user, cfg.iam, cfg.cluster_identifier, cfg.region)


def _safe_close(conn):
    try:
        conn.close()
    except Exception:
        pass


def _new_connection(cfg):
    kwargs = dict(
        host=cfg.host,
        port=cfg.port,
        database=cfg.database,
    )
    if cfg.iam:
        kwargs.update(
            iam=True,
            cluster_identifier=cfg.cluster_identifier,
            region=cfg.region,
            db_user=cfg.user,
        )
    else:
        kwargs.update(user=cfg.user, password=cfg.get_password())
    conn = redshift_connector.connect(**kwargs)
    conn.autocommit = True
    return conn


def get_connection(connection=None):
    """Живое соединение из пула; протухшее (TTL) или мёртвое пересоздаётся."""
    cfg = options.resolve(connection, "redshift")
    key = _pool_key(cfg)
    entry = _pool.pop(key, None)
    if entry is not None:
        conn, last_used = entry
        if time.monotonic() - last_used > cfg.connection_ttl_sec:
            _safe_close(conn)
        else:
            try:
                with conn.cursor() as cur:
                    cur.execute("select 1")
            except Exception:
                _safe_close(conn)
            else:
                _pool[key] = (conn, time.monotonic())
                return conn
    conn = _new_connection(cfg)
    _pool[key] = (conn, time.monotonic())
    return conn


def _evict(cfg, conn):
    """Убирает соединение из пула и закрывает — после отмены запроса ему нельзя доверять."""
    if _pool.get(_pool_key(cfg), (None,))[0] is conn:
        del _pool[_pool_key(cfg)]
    _safe_close(conn)


def close_connections():
    for conn, _ in _pool.values():
        _safe_close(conn)
    _pool.clear()


atexit.register(close_connections)


def _cancel_backend(pid, cfg):
    try:
        # отдельное соединение: основное занято выполняющимся запросом
        c = _new_connection(cfg)
        with c.cursor() as cur:
            cur.execute(f"SELECT pg_cancel_backend({pid})")
        c.close()
    except Exception:
        pass


def run_query(query, connection=None, params=None, verbose=True):
    log = print if verbose else (lambda *args: None)
    query = prepare_query(query, params)
    cfg = options.resolve(connection, "redshift")
    conn = get_connection(cfg)
    with conn.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        backend_pid = cursor.fetchone()[0]

        log("▶ Выполняю запрос...")
        try:
            cursor.execute(query)
        except KeyboardInterrupt:
            _cancel_backend(backend_pid, cfg)
            _evict(cfg, conn)
            print("🚫 Запрос отменён")
            raise

        if cursor.description is None:
            rows = cursor.rowcount
            log(f"✓ Выполнено. Затронуто строк: {rows if rows >= 0 else '?'}")
            return None

        cols = [d[0] for d in cursor.description]
        first_batch = cursor.fetchmany(cfg.min_rows_for_progress)

        if len(first_batch) < cfg.min_rows_for_progress:
            df = pl.DataFrame(first_batch, schema=cols, orient="row", infer_schema_length=None)
            log(f"✓ Готово, строк: {len(df)}")
            return df

        dfs = [pl.DataFrame(first_batch, schema=cols, orient="row", infer_schema_length=None)]
        total_rows = len(first_batch)

        try:
            with tqdm(desc="Загрузка", unit="строк", dynamic_ncols=True, mininterval=0.2) as pbar:
                pbar.update(total_rows)
                while True:
                    batch = cursor.fetchmany(_CHUNK_SIZE)
                    if not batch:
                        break
                    dfs.append(pl.DataFrame(batch, schema=cols, orient="row", infer_schema_length=None))
                    total_rows += len(batch)
                    pbar.update(len(batch))
        except KeyboardInterrupt:
            _cancel_backend(backend_pid, cfg)
            _evict(cfg, conn)
            print("🚫 Загрузка прервана")
            raise

        # vertical_relaxed: типы чанков могут различаться (например, Null-колонка
        # в первом чанке против значений в следующих)
        df = pl.concat(dfs, how="vertical_relaxed")
        log(f"✓ Готово, строк: {total_rows:,}")
        return df
