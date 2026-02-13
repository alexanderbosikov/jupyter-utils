from google.cloud import bigquery
from google.cloud import bigquery_storage
from tqdm.notebook import tqdm
import pandas as pd
import nb_utils.options as options

def run_query(query):
    cfg = options.config.bigquery
    client = bigquery.Client(project=cfg.project_id)
    
    # --- DRY RUN ---
    dry_cfg = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    print("▶ Проверка запроса...")
    dry_job = client.query(query, job_config=dry_cfg)

    scanned_gb = dry_job.total_bytes_processed / (1024**3)
    
    print(f"📊 This query will process {scanned_gb:.2f} GB when run.")
    
    # Пользовательское ограничение
    if scanned_gb > cfg.max_bytes_billed_gb:
        ans = input(f"⚠️ Запрос сканирует {scanned_gb:.2f} GB (> {cfg.max_bytes_billed_gb} GB). Продолжить? (y/n): ").strip().lower()
        if ans != "y":
            print("🚫 Отменено.")
            return None

    # --- ВЫПОЛНЕНИЕ ЗАПРОСА ---
    use_storage = False
    print("▶ Выполняю запрос...")
    job = client.query(query)
    row_iter = job.result()

    # --- ОПРЕДЕЛЕНИЕ API ---
    destination = job.destination
    temp_table = client.get_table(destination)
    use_storage = temp_table.num_rows >= cfg.min_rows_for_storage_api
    if use_storage:
        print(f"🚀 Использую **Storage API** (ожидается {temp_table.num_rows} строк)")
    else:
        print(f"📦 Использую **REST API** (ожидается {temp_table.num_rows} строк)")

    # --- REST API ---
    if not use_storage:
        df = row_iter.to_dataframe(create_bqstorage_client=False)
        print(f"✓ Готово, строк: {len(df)} (REST API)")
        return df

    # --- STORAGE API ---
    bqstorage_client = bigquery_storage.BigQueryReadClient()
    arrow_iter = row_iter.to_arrow_iterable(bqstorage_client=bqstorage_client)

    dfs = []
    total_rows = 0

    for batch in tqdm(arrow_iter, desc="Downloading", unit="chunk", dynamic_ncols=True, mininterval=0.2):
        df_chunk = batch.to_pandas()
        dfs.append(df_chunk)
        total_rows += len(df_chunk)

    df = pd.concat(dfs, ignore_index=True)
    print(f"✓ Готово, строк: {total_rows} (Storage API)")
    return df

def run_query_2(query):
    """
    Универсальная функция для BigQuery:
    - SELECT → возвращает DataFrame
    - DML/DDL → выводит результат
    - Скрипты (BEGIN...END) → выводит результаты ВСЕХ DML/DDL + возвращает последний SELECT (если есть)
    """
    cfg = options.config.bigquery
    client = bigquery.Client(project=cfg.project_id)
    client = bigquery.Client(project='emerald-vent-680')

    # --- DRY RUN ---
    print("▶ Проверка запроса...")
    try:
        dry_job = client.query(query, job_config=bigquery.QueryJobConfig(dry_run=True))
        scanned_gb = dry_job.total_bytes_processed / (1024**3)
        print(f"📊 Запрос обработает ~{scanned_gb:.2f} GB")
        if scanned_gb > cfg.max_bytes_billed_gb:
            ans = input(f"⚠️ > {cfg.max_bytes_billed_gb} GB. Продолжить? (y/n): ").strip().lower()
            if ans != "y":
                print("🚫 Отменено.")
                return None
    except Exception as e:
        print(f"⚠️ Dry-run не удался (DDL/скрипт?): {e}")

    # --- Выполнение ---
    print("▶ Выполняю запрос...")
    job = client.query(query)
    job.result()  # ждём завершения

    # === Обработка в зависимости от типа ===

    if job.statement_type == "SELECT":
        # Одиночный SELECT
        return _fetch_dataframe(job, cfg.min_rows_for_storage_api, client)

    elif job.statement_type in ("INSERT", "UPDATE", "DELETE", "MERGE"):
        rows = job.num_dml_affected_rows or 0
        print(f"✓ {job.statement_type} выполнен. Затронуто строк: {rows:,}")
        return None

    elif job.ddl_operation_performed:
        # Одиночный DDL
        op = job.ddl_operation_performed
        target = job.ddl_target_table or job.ddl_target_routine
        target_str = str(target) if target else ""
        print(f"✓ {job.statement_type} {op}. {target_str}")
        return None

    elif job.num_child_jobs > 0:
        # === СКРИПТ: выводим ВСЕ дочерние операции ===
        print(f"▶ Скрипт с {job.num_child_jobs} дочерними заданиями")
        select_job = None
        printed_something = False

        for child in client.list_jobs(parent_job=job.job_id):
            if child.statement_type in ("INSERT", "UPDATE", "DELETE", "MERGE"):
                rows = child.num_dml_affected_rows or 0
                print(f"  → {child.statement_type}: {rows:,} строк изменено")
                printed_something = True

            elif child.ddl_operation_performed:
                op = child.ddl_operation_performed
                target = child.ddl_target_table or child.ddl_target_routine
                target_str = str(target) if target else ""
                print(f"  → {child.statement_type} {op}. {target_str}")
                printed_something = True

            elif child.statement_type == "SELECT":
                select_job = child  # запоминаем последний SELECT

        if not printed_something:
            print("  → Только DDL или ничего не изменилось")

        # Если был SELECT — возвращаем его результат
        if select_job:
            print("→ Возвращаю результат последнего SELECT")
            return _fetch_dataframe(select_job, cfg.min_rows_for_storage_api, client)
        else:
            print("→ Нет SELECT в скрипте")
            return None

    else:
        print("⚠️ Неизвестный тип запроса")
        return None


def _fetch_dataframe(job, max_rows, client):
    """Внутренняя функция для загрузки SELECT-результата (REST или Storage API)"""
    destination = job.destination
    if destination is None:
        print("⚠️ SELECT без destination")
        return None

    temp_table = client.get_table(destination)
    use_storage = temp_table.num_rows >= max_rows

    if use_storage:
        print(f"🚀 Storage API ({temp_table.num_rows:,} строк)")
        bqstorage_client = bigquery_storage.BigQueryReadClient()
        arrow_iter = job.to_arrow_iterable(bqstorage_client=bqstorage_client)
        dfs = []
        total_rows = 0

        for batch in tqdm(arrow_iter, desc="Загрузка", unit="chunk"):
            df_chunk = batch.to_pandas()
            dfs.append(df_chunk)
            total_rows += len(df_chunk)

        df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
        print(f"✓ Готово: {total_rows:,} строк (Storage API)")
    else:
        print(f"📦 REST API ({temp_table.num_rows:,} строк)")
        df = job.to_dataframe(create_bqstorage_client=False)
        print(f"✓ Готово: {len(df):,} строк (REST API)")

    return df