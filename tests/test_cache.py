import json

import polars as pl

import nb_utils.cache as c


def test_key_sensitive_to_sql_and_conn():
    k = c._key("select 1", "rs:h:db")
    assert k == c._key("select 1", "rs:h:db")      # стабилен
    assert k != c._key("select 2", "rs:h:db")      # смена SQL
    assert k != c._key("select 1", "bq:proj")      # смена соединения


def test_save_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "CACHE_DIR", tmp_path)
    df = pl.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    c.save("select 1", "rs:h:db", df)
    hit = c.load("select 1", "rs:h:db", ttl_sec=0)
    assert hit is not None
    got, meta = hit
    assert got.equals(df) and meta["rows"] == 3


def test_load_miss_on_different_sql(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "CACHE_DIR", tmp_path)
    c.save("select 1", "rs:h:db", pl.DataFrame({"a": [1]}))
    assert c.load("select 2", "rs:h:db", ttl_sec=0) is None  # смена запроса — промах


def test_ttl_expiry(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "CACHE_DIR", tmp_path)
    c.save("select 1", "rs:h:db", pl.DataFrame({"a": [1]}))
    js = next(tmp_path.glob("*.json"))
    meta = json.loads(js.read_text())
    meta["saved_at"] = 0  # очень старый
    js.write_text(json.dumps(meta))
    assert c.load("select 1", "rs:h:db", ttl_sec=3600) is None      # истёк по TTL
    assert c.load("select 1", "rs:h:db", ttl_sec=0) is not None     # без TTL — есть


def test_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "CACHE_DIR", tmp_path)
    c.save("select 1", "rs:h:db", pl.DataFrame({"a": [1]}))
    assert c.clear() == 1
    assert c.load("select 1", "rs:h:db", ttl_sec=0) is None


def test_clear_older_than_days(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "CACHE_DIR", tmp_path)
    c.save("old", "rs:h:db", pl.DataFrame({"a": [1]}))
    c.save("fresh", "rs:h:db", pl.DataFrame({"a": [2]}))
    # состарить только запись "old"
    old_js = tmp_path / f"{c._key('old', 'rs:h:db')}.json"
    meta = json.loads(old_js.read_text())
    meta["saved_at"] = 0
    old_js.write_text(json.dumps(meta))

    assert c.clear(older_than_days=1) == 1               # удалена только старая
    assert c.load("old", "rs:h:db", ttl_sec=0) is None
    assert c.load("fresh", "rs:h:db", ttl_sec=0) is not None


def test_run_query_cache_flow(tmp_path, monkeypatch):
    import nb_utils.options as o
    import nb_utils.query as q

    monkeypatch.setattr(c, "CACHE_DIR", tmp_path)

    class Cfg:
        type = "redshift"
        host = "h"
        database = "db"

    monkeypatch.setattr(o, "resolve", lambda conn=None, required_type=None: Cfg())

    calls = {"n": 0}

    def fake_dispatch(query, cfg, params, verbose):
        calls["n"] += 1
        return pl.DataFrame({"x": [calls["n"]]})

    monkeypatch.setattr(q, "_dispatch", fake_dispatch)

    df1 = q.run_query("select 1", cache=True)
    df2 = q.run_query("select 1", cache=True)          # из кэша, бэкенд не трогаем
    assert calls["n"] == 1 and df1.equals(df2)

    q.run_query("select 1", cache=True, refresh=True)  # принудительный перезапрос
    assert calls["n"] == 2

    q.run_query("select 2", cache=True)                # другой SQL — снова бэкенд
    assert calls["n"] == 3

    q.run_query("select 1", cache=False)               # cache=False — всегда бэкенд
    assert calls["n"] == 4
