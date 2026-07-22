import os
import re
import subprocess
import tomllib
from pathlib import Path

CONFIG_FILE = Path.home() / ".config" / "nb_utils.toml"

_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

def _expand_env(value):
    """Подставляет ${VAR} из окружения во все строковые значения конфига."""
    if isinstance(value, str):
        def sub(m):
            var = m.group(1)
            if var in os.environ:
                return os.environ[var]
            print(f"⚠️ {CONFIG_FILE}: переменная окружения {var} не задана")
            return m.group(0)
        return _ENV_RE.sub(sub, value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value

_TYPE_ALIASES = {
    "bq": "bigquery",
    "bigquery": "bigquery",
    "rs": "redshift",
    "redshift": "redshift",
}

class BigQueryOptions:
    type = "bigquery"

    def __init__(self):
        self.project_id: str | None = None
        self.max_bytes_billed_gb: int = 5
        self.min_rows_for_storage_api: int = 100000

class RedshiftOptions:
    type = "redshift"

    def __init__(self):
        self.host: str | None = None
        self.port: int = 5439
        self.database: str | None = None
        self.user: str | None = None
        self.password: str | None = None
        self.password_cmd: str | None = None
        self.iam: bool = False
        self.cluster_identifier: str | None = None
        self.region: str | None = None
        self.min_rows_for_progress: int = 10000
        self.connection_ttl_sec: int = 600

    def get_password(self):
        if self.password_cmd:
            return subprocess.run(
                self.password_cmd, shell=True, capture_output=True, text=True, check=True
            ).stdout.strip()
        return self.password

class TableauOptions:
    def __init__(self):
        self.server_url: str | None = None
        self.site_name: str | None = None
        self.token_name: str | None = None
        self.token_secret: str | None = None

_OPTION_CLASSES = {"bigquery": BigQueryOptions, "redshift": RedshiftOptions}

class NBUtilsOptions:
    def __init__(self):
        self.connections: dict = {}
        self.tableau = TableauOptions()
        self.connection: str | None = None  # имя активного соединения
        self.reload()

    # legacy-алиасы на встроенные соединения (config.redshift.host = ...)
    @property
    def bigquery(self):
        return self.connections["bq"]

    @property
    def redshift(self):
        return self.connections["rs"]

    def active(self):
        """Опции активного соединения (выбранного через %connect или default в конфиге)."""
        if not self.connection:
            raise RuntimeError(
                "Соединение не выбрано: выполни %connect <имя> или задай default в конфиге"
            )
        return resolve(self.connection)

    def reload(self):
        """Перечитывает ~/.config/nb_utils.toml, сбрасывая соединения к дефолтам."""
        self.connections = {"bq": BigQueryOptions(), "rs": RedshiftOptions()}
        self.tableau = TableauOptions()
        self.default_limit = 1000  # дефолтный лимит строк для %%sql (0/None — без лимита)

        if not CONFIG_FILE.exists():
            return
        try:
            data = tomllib.loads(CONFIG_FILE.read_text())
        except (OSError, tomllib.TOMLDecodeError) as e:
            print(f"⚠️ Не удалось прочитать {CONFIG_FILE}: {e}")
            return
        data = _expand_env(data)

        for name, values in (data.get("connections") or {}).items():
            if not isinstance(values, dict):
                continue
            ctype = _TYPE_ALIASES.get(str(values.get("type", "")).lower())
            if ctype is None:
                print(f"⚠️ [connections.{name}]: type должен быть bigquery или redshift, получен {values.get('type')!r}")
                continue
            conn = _OPTION_CLASSES[ctype]()
            for key, value in values.items():
                if key == "type":
                    continue
                if hasattr(conn, key):
                    setattr(conn, key, value)
                else:
                    print(f"⚠️ [connections.{name}]: неизвестный параметр {key}")
            self.connections[name] = conn

        tableau = data.get("tableau")
        if isinstance(tableau, dict):
            for key, value in tableau.items():
                if hasattr(self.tableau, key):
                    setattr(self.tableau, key, value)
                else:
                    print(f"⚠️ [tableau]: неизвестный параметр {key}")

        dl = data.get("default_limit")
        if dl is not None:
            if isinstance(dl, int) and not isinstance(dl, bool) and dl >= 0:
                self.default_limit = dl
            else:
                print(f"⚠️ default_limit должен быть неотрицательным целым, получено {dl!r}")

        default = data.get("default") or data.get("connection")
        if default:
            if default in self.connections:
                self.connection = default
            else:
                print(f"⚠️ default = {default!r}: нет такого соединения в [connections]")

def resolve(connection=None, required_type=None):
    """Приводит None (активное) / имя / объект опций к объекту опций соединения."""
    cfg = connection
    if cfg is None:
        cfg = config.active()
    elif isinstance(cfg, str):
        if cfg not in config.connections:
            raise KeyError(
                f"Нет соединения {cfg!r}. Доступные: {', '.join(config.connections)}"
            )
        cfg = config.connections[cfg]
    if required_type and cfg.type != required_type:
        raise TypeError(f"Соединение имеет тип {cfg.type!r}, ожидался {required_type!r}")
    return cfg

config = NBUtilsOptions()
