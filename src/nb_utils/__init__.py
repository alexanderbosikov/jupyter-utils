from .options import config
from . import jupyter

jupyter.enable()

# подмодуль -> extra-группа из pyproject (None — зависимости в основном наборе)
_lazy = {"bigquery": "bq", "redshift": None, "tableau": "tableau"}

def __getattr__(name):
    if name in _lazy:
        import importlib
        try:
            mod = importlib.import_module(f".{name}", __name__)
        except ModuleNotFoundError as e:
            extra = _lazy[name]
            if extra:
                raise ImportError(
                    f"Для nb_utils.{name} не хватает зависимостей ({e.name}). "
                    f"Установи: uv sync --extra {extra}"
                ) from e
            raise
        globals()[name] = mod
        return mod
    raise AttributeError(f"module 'nb_utils' has no attribute {name!r}")
