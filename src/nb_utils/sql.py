import re

_VAR_RE = re.compile(r"\{\{\s*([A-Za-z_]\w*)\s*\}\}")


def _to_sql(value):
    """list/tuple/set -> SQL-кортеж для IN (строки в кавычках), остальное — как есть."""
    if isinstance(value, (list, tuple, set)):
        items = ", ".join(
            "'" + v.replace("'", "''") + "'" if isinstance(v, str) else str(v)
            for v in value
        )
        return f"({items})"
    return str(value)


def render_query(query, params):
    """Подставляет {{ var }} из params (словарь или user_ns ноутбука).

    Скаляры вставляются как есть (кавычки для строк пиши сам, как в dbt):
        where dt >= '{{ start_date }}' and user_id = {{ uid }}
    Списки/кортежи разворачиваются в SQL-кортеж:
        where country in {{ countries }}
    """
    def sub(m):
        name = m.group(1)
        if name not in params:
            raise NameError(f"{{{{ {name} }}}}: нет такой переменной")
        return _to_sql(params[name])
    return _VAR_RE.sub(sub, query)
