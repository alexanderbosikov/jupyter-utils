from .options import config
from .query import run_query, run_query_by_period
from .report import report_style
from . import jupyter

jupyter.enable()

# подмодуль -> dependency-group из pyproject; активный стек задаётся
# в tool.uv.default-groups
_lazy = {"bigquery": "bq", "redshift": "rs", "tableau": "tableau"}

def __getattr__(name):
    if name in _lazy:
        import importlib
        try:
            mod = importlib.import_module(f".{name}", __name__)
        except ModuleNotFoundError as e:
            raise ImportError(
                f"Для nb_utils.{name} не хватает зависимостей ({e.name}). "
                f"Установи: uv sync --group {_lazy[name]} "
                f"(или добавь группу в tool.uv.default-groups)"
            ) from e
        globals()[name] = mod
        return mod
    raise AttributeError(f"module 'nb_utils' has no attribute {name!r}")
