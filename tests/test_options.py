import pytest

import nb_utils.options as o


def make_config(tmp_path, monkeypatch, text):
    f = tmp_path / "nb_utils.toml"
    f.write_text(text)
    monkeypatch.setattr(o, "CONFIG_FILE", f)
    return o.NBUtilsOptions()


def test_builtin_connections_without_file(tmp_path, monkeypatch):
    monkeypatch.setattr(o, "CONFIG_FILE", tmp_path / "missing.toml")
    cfg = o.NBUtilsOptions()
    assert set(cfg.connections) == {"bq", "rs"}
    assert cfg.connections["bq"].type == "bigquery"
    assert cfg.connections["rs"].type == "redshift"
    assert cfg.connection is None


def test_named_connections_and_defaults(tmp_path, monkeypatch):
    cfg = make_config(tmp_path, monkeypatch, """
[connections.rs_prod]
type = "redshift"
host = "prod-host"
user = "reader"
""")
    conn = cfg.connections["rs_prod"]
    assert conn.host == "prod-host"
    assert conn.port == 5439  # незаданное поле берёт дефолт
    assert conn.connection_ttl_sec == 600


def test_type_aliases(tmp_path, monkeypatch):
    cfg = make_config(tmp_path, monkeypatch, """
[connections.a]
type = "rs"

[connections.b]
type = "BQ"
""")
    assert cfg.connections["a"].type == "redshift"
    assert cfg.connections["b"].type == "bigquery"


def test_unknown_type_skipped(tmp_path, monkeypatch, capsys):
    cfg = make_config(tmp_path, monkeypatch, """
[connections.x]
type = "mysql"
""")
    assert "x" not in cfg.connections
    assert "type должен быть" in capsys.readouterr().out


def test_unknown_key_warns(tmp_path, monkeypatch, capsys):
    make_config(tmp_path, monkeypatch, """
[connections.rs_x]
type = "redshift"
bogus = 1
""")
    assert "неизвестный параметр bogus" in capsys.readouterr().out


def test_default_selects_connection(tmp_path, monkeypatch):
    cfg = make_config(tmp_path, monkeypatch, """
default = "rs_prod"

[connections.rs_prod]
type = "redshift"
""")
    assert cfg.connection == "rs_prod"


def test_bad_default_warns(tmp_path, monkeypatch, capsys):
    cfg = make_config(tmp_path, monkeypatch, 'default = "nope"\n')
    assert cfg.connection is None
    assert "нет такого соединения" in capsys.readouterr().out


def test_env_expansion(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("RS_USER", "reader")
    monkeypatch.delenv("RS_MISSING", raising=False)
    cfg = make_config(tmp_path, monkeypatch, """
[connections.rs_x]
type = "redshift"
user = "${RS_USER}"
password = "${RS_MISSING}"
port = 5439
""")
    conn = cfg.connections["rs_x"]
    assert conn.user == "reader"
    assert conn.password == "${RS_MISSING}"  # незаданная переменная остаётся литералом
    assert conn.port == 5439
    assert "RS_MISSING не задана" in capsys.readouterr().out


def test_tableau_section(tmp_path, monkeypatch):
    cfg = make_config(tmp_path, monkeypatch, """
[tableau]
server_url = "https://tab.example.com"
""")
    assert cfg.tableau.server_url == "https://tab.example.com"


def test_legacy_aliases(tmp_path, monkeypatch):
    monkeypatch.setattr(o, "CONFIG_FILE", tmp_path / "missing.toml")
    cfg = o.NBUtilsOptions()
    assert cfg.redshift is cfg.connections["rs"]
    assert cfg.bigquery is cfg.connections["bq"]


def test_resolve(tmp_path, monkeypatch):
    cfg = make_config(tmp_path, monkeypatch, """
default = "rs_x"

[connections.rs_x]
type = "redshift"

[connections.bq_x]
type = "bigquery"
""")
    monkeypatch.setattr(o, "config", cfg)
    assert o.resolve() is cfg.connections["rs_x"]  # None -> активное
    assert o.resolve("bq_x") is cfg.connections["bq_x"]  # по имени
    obj = cfg.connections["rs_x"]
    assert o.resolve(obj) is obj  # объект как есть
    with pytest.raises(TypeError):
        o.resolve("bq_x", "redshift")
    with pytest.raises(KeyError):
        o.resolve("nope")


def test_active_without_connection_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(o, "CONFIG_FILE", tmp_path / "missing.toml")
    cfg = o.NBUtilsOptions()
    with pytest.raises(RuntimeError):
        cfg.active()


def test_password_cmd(tmp_path, monkeypatch):
    conn = o.RedshiftOptions()
    conn.password_cmd = "echo s3cret"
    assert conn.get_password() == "s3cret"
    conn2 = o.RedshiftOptions()
    conn2.password = "plain"
    assert conn2.get_password() == "plain"
