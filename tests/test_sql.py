import pytest

from nb_utils.sql import render_query


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
