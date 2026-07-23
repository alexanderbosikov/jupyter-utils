"""Дисковый кэш результатов запросов (parquet), переживающий рестарт kernel.

Ключ — хэш отрендеренного SQL + идентификатор соединения: смена запроса (или БД)
меняет ключ автоматически. Для «данные в БД обновились, запрос тот же» — TTL или
явный refresh на стороне run_query.
"""
import hashlib
import json
import time
from pathlib import Path

import polars as pl

CACHE_DIR = Path.home() / ".cache" / "nb_utils" / "queries"


def _key(rendered_sql, connection_id):
    h = hashlib.sha256()
    h.update(rendered_sql.encode("utf-8"))
    h.update(b"\x00")
    h.update((connection_id or "").encode("utf-8"))
    return h.hexdigest()[:16]


def _paths(key):
    return CACHE_DIR / f"{key}.parquet", CACHE_DIR / f"{key}.json"


def _fmt_age(saved_at):
    sec = max(0.0, time.time() - saved_at)
    if sec < 90:
        return "только что"
    if sec < 5400:
        return f"{int(sec / 60)} мин назад"
    if sec < 129600:
        return f"{int(sec / 3600)} ч назад"
    return f"{int(sec / 86400)} дн назад"


def load(rendered_sql, connection_id, ttl_sec):
    """(df, meta) из кэша, если он есть и не истёк по TTL; иначе None.

    ttl_sec <= 0 (или None) — без истечения (инвалидируется только сменой запроса).
    """
    key = _key(rendered_sql, connection_id)
    pq, js = _paths(key)
    if not pq.exists() or not js.exists():
        return None
    try:
        meta = json.loads(js.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if ttl_sec and ttl_sec > 0 and (time.time() - meta.get("saved_at", 0)) > ttl_sec:
        return None
    try:
        df = pl.read_parquet(pq)
    except Exception:
        return None
    return df, meta


def save(rendered_sql, connection_id, df):
    """Сохраняет df в кэш (parquet) + сайдкар-метаданные (json)."""
    key = _key(rendered_sql, connection_id)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pq, js = _paths(key)
    df.write_parquet(pq)
    meta = {
        "sql": rendered_sql,
        "connection": connection_id,
        "rows": df.height,
        "saved_at": time.time(),
    }
    js.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    return meta


def clear(older_than_days=None):
    """Удаляет кэш запросов. Возвращает число удалённых наборов.

    older_than_days=None — весь кэш; иначе только записи старше N дней (по saved_at
    из метаданных, при их отсутствии — по mtime parquet-файла).
    """
    if not CACHE_DIR.exists():
        return 0
    cutoff = None if older_than_days is None else time.time() - older_than_days * 86400
    removed = 0
    for pq in CACHE_DIR.glob("*.parquet"):
        js = pq.with_suffix(".json")
        if cutoff is not None:
            try:
                saved_at = json.loads(js.read_text()).get("saved_at")
            except (OSError, json.JSONDecodeError):
                saved_at = None
            if saved_at is None:
                saved_at = pq.stat().st_mtime
            if saved_at >= cutoff:
                continue  # свежее порога — оставляем
        pq.unlink(missing_ok=True)
        js.unlink(missing_ok=True)
        removed += 1
    return removed
