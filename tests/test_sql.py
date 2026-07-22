import pytest

from nb_utils.sql import apply_default_limit, render_query


def test_scalars_raw():
    q = render_query("where dt >= '{{ d }}' and uid = {{uid}}", {"d": "2026-01-01", "uid": 42})
    assert q == "where dt >= '2026-01-01' and uid = 42"


def test_identifiers():
    assert render_query("from {{ table }}", {"table": "fct_orders"}) == "from fct_orders"


def test_collections_to_tuple_with_escaping():
    q = render_query("in {{ xs }}", {"xs": ["US", "o'brien", 7]})
    assert q == "in ('US', 'o''brien', 7)"


def test_missing_var_raises():
    with pytest.raises(NameError):
        render_query("select {{ missing }}", {})


def test_whitespace_insensitive():
    assert render_query("{{x}} {{ x }}", {"x": 1}) == "1 1"


def test_jinja_control_blocks():
    q = render_query(
        "select * from t{% if flag %} where x in {{ xs }}{% endif %}",
        {"flag": True, "xs": [1, 2]},
    )
    assert q == "select * from t where x in (1, 2)"
    q = render_query("select * from t{% if flag %} where 1{% endif %}", {"flag": False})
    assert q == "select * from t"


def test_template_syntax_error():
    with pytest.raises(ValueError):
        render_query("{% if %}", {})


def test_prepare_query():
    from nb_utils.sql import prepare_query
    assert prepare_query("select 1") == "select 1"  # без шаблона params не нужны
    assert prepare_query("select {{ x }}", {"x": 5}) == "select 5"
    with pytest.raises(NameError):  # шаблон есть, params нет, IPython не запущен
        prepare_query("select {{ x }}")


def test_limit_appended_to_select():
    q, applied = apply_default_limit("select * from t", 1000)
    assert applied and q == "select * from t\nlimit 1000"


def test_limit_applies_to_with():
    q, applied = apply_default_limit("with c as (select 1) select * from c", 100)
    assert applied and q.endswith("\nlimit 100")


def test_limit_zero_or_none_noop():
    assert apply_default_limit("select 1", 0) == ("select 1", False)
    assert apply_default_limit("select 1", None) == ("select 1", False)


def test_limit_not_applied_when_already_present():
    for q in ("select * from t limit 10", "select * from t LIMIT 5 offset 20", "select 1 limit all"):
        assert apply_default_limit(q, 1000) == (q, False)


def test_limit_skips_non_select():
    for q in ("insert into t values (1)", "create table t as select 1", "explain select 1"):
        assert apply_default_limit(q, 1000) == (q, False)


def test_limit_strips_trailing_semicolon():
    q, applied = apply_default_limit("select * from t;  ", 50)
    assert applied and q == "select * from t\nlimit 50"


def test_limit_ignores_inner_limit():
    q, applied = apply_default_limit("select * from (select 1 limit 3) s", 1000)
    assert applied and q.endswith("s\nlimit 1000")


def test_limit_after_leading_comment():
    q, applied = apply_default_limit("-- note\nselect * from t", 10)
    assert applied and q.endswith("\nlimit 10")
