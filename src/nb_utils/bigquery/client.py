from google.cloud import bigquery
from google.auth.exceptions import DefaultCredentialsError, RefreshError
import polars as pl
import pyarrow as pa
from tqdm.auto import tqdm
import nb_utils.options as options
from nb_utils.sql import render_query
from .auth import relogin_adc

_clients: dict[str, bigquery.Client] = {}


def _get_client(cfg):
    if cfg.project_id not in _clients:
        _clients[cfg.project_id] = bigquery.Client(project=cfg.project_id)
    return _clients[cfg.project_id]


def run_file(path, connection=None, params=None):
    with open(path) as f:
        return run_query(f.read(), connection, params)


def run_query(query, connection=None, params=None):
    if params:
        query = render_query(query, params)
    cfg = options.resolve(connection, "bigquery")
    try:
        return _run(cfg, query)
    except (RefreshError, DefaultCredentialsError):
        relogin_adc()
        _clients.clear()  # клиенты держат старые credentials
        return _run(cfg, query)


def _run(cfg, query):
    client = _get_client(cfg)

    # --- DRY RUN ---
    dry_cfg = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    print("▶ Проверка запроса...")
    dry_job = client.query(query, job_config=dry_cfg)

    scanned_gb = dry_job.total_bytes_processed / (1024**3)
    print(f"📊 Запрос обработает ~{scanned_gb:.2f} GB")

    # Пользовательское ограничение
    if scanned_gb > cfg.max_bytes_billed_gb:
        ans = input(f"⚠️ Запрос сканирует {scanned_gb:.2f} GB (> {cfg.max_bytes_billed_gb} GB). Продолжить? (y/n): ").strip().lower()
        if ans != "y":
            print("🚫 Отменено.")
            return None

    # --- ВЫПОЛНЕНИЕ ЗАПРОСА ---
    print("▶ Выполняю запрос...")
    job = client.query(query)
    row_iter = job.result()

    # DML/DDL: результата-таблицы нет
    if job.destination is None:
        rows = job.num_dml_affected_rows
        if rows is not None:
            print(f"✓ {job.statement_type} выполнен. Затронуто строк: {rows:,}")
        else:
            print(f"✓ Выполнено ({job.statement_type})")
        return None

    temp_table = client.get_table(job.destination)
    use_storage = temp_table.num_rows >= cfg.min_rows_for_storage_api

    # --- REST API ---
    if not use_storage:
        print(f"📦 Использую REST API ({temp_table.num_rows:,} строк)")
        df = pl.from_arrow(row_iter.to_arrow(create_bqstorage_client=False))
        print(f"✓ Готово, строк: {len(df):,} (REST API)")
        return df

    # --- STORAGE API ---
    print(f"🚀 Использую Storage API ({temp_table.num_rows:,} строк)")
    from google.cloud import bigquery_storage
    bqstorage_client = bigquery_storage.BigQueryReadClient()
    arrow_iter = row_iter.to_arrow_iterable(bqstorage_client=bqstorage_client)

    batches = []
    total_rows = 0
    for batch in tqdm(arrow_iter, desc="Загрузка", unit="chunk", dynamic_ncols=True, mininterval=0.2):
        batches.append(batch)
        total_rows += batch.num_rows

    df = pl.from_arrow(pa.Table.from_batches(batches))
    print(f"✓ Готово, строк: {total_rows:,} (Storage API)")
    return df
