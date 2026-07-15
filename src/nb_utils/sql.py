import jinja2


def _to_sql(value):
    """list/tuple/set -> SQL-кортеж для IN (строки в кавычках), остальное — как есть."""
    if isinstance(value, (list, tuple, set)):
        items = ", ".join(
            "'" + v.replace("'", "''") + "'" if isinstance(v, str) else str(v)
            for v in value
        )
        return f"({items})"
    return str(value)


_env = jinja2.Environment(undefined=jinja2.StrictUndefined, finalize=_to_sql)


def render_query(query, params):
    """Рендерит запрос как jinja-шаблон: {{ var }}, {% if %}, {% for %} и т.д.

    Скаляры вставляются как есть (кавычки для строк пиши сам, как в dbt):
        where dt >= '{{ start_date }}' and user_id = {{ uid }}
    Списки/кортежи разворачиваются в SQL-кортеж:
        where country in {{ countries }}
    """
    try:
        return _env.from_string(query).render(params)
    except jinja2.UndefinedError as e:
        raise NameError(f"{e}: нет такой переменной") from e
    except jinja2.TemplateSyntaxError as e:
        raise ValueError(f"Ошибка в jinja-шаблоне запроса: {e}") from e


def _notebook_ns():
    try:
        from IPython import get_ipython
    except ImportError:
        return None
    ipy = get_ipython()
    return ipy.user_ns if ipy is not None else None


def prepare_query(query, params=None):
    """Рендерит {{ ... }} из params, а если их нет — из переменных ноутбука."""
    if params is not None:
        return render_query(query, params)
    if "{{" not in query and "{%" not in query:
        return query
    ns = _notebook_ns()
    if ns is None:
        raise NameError(
            "В запросе есть jinja-шаблон, но params не переданы, а IPython не запущен"
        )
    return render_query(query, ns)
