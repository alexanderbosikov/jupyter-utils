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
