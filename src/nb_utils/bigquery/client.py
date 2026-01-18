from google.cloud import bigquery
from google.cloud import bigquery_storage
from tqdm.notebook import tqdm
import pandas as pd
from nb_utils import options

def run_query(query):
    cfg = options.bigquery
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
    use_storage = temp_table.num_rows >= max_rows
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