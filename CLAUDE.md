# jupyter-utils

Личный пакет `nb_utils` для работы с данными в Jupyter Lab: запросы к BigQuery и Redshift через cell-магику `%%sql`, публикация данных в Tableau.

## Окружение и команды

- Менеджер — **uv** (`uv sync`, `uv add <pkg>`), сборка hatchling, Python ≥ 3.12.
- Зависимости всех бэкендов (Redshift, BigQuery, Tableau) — dependency-groups `rs`/`bq`/`tableau`; активный стек задаётся в `tool.uv.default-groups` в pyproject.toml (сейчас `["dev", "rs"]`) и ставится обычным `uv sync`. Без группы подмодуль при обращении даёт ImportError с подсказкой.
- Тесты: `uv run pytest` (покрыт `options.py`); остальное проверяется вручную в Jupyter Lab.
- `notebooks/` и `*.ipynb` в корне — личные scratch-анализы, к коду пакета отношения не имеют: не трогать и не учитывать при работе над пакетом.

## Архитектура

```
src/nb_utils/
├── __init__.py      # side effects при import: регистрирует магики + itables
├── options.py       # config — глобальный синглтон настроек (nb_utils.config)
├── jupyter/         # магики %%sql и %connect, enable()
├── bigquery/        # run_query/run_file (polars), авто-relogin gcloud ADC
├── redshift/        # run_query/run_file (polars), пул соединений, IAM или user/password
└── tableau/         # Connection (context manager), publish/insert/delete hyper
```

Ключевые механики:

- **`import nb_utils` имеет побочные эффекты**: регистрирует `%connect` и включает `itables.init_notebook_mode` (последнее — только в notebook-ядре, не в консольном IPython; вне IPython не делает ничего). Ошибки инициализации печатаются предупреждением, см. `jupyter/enable.py`.
- **Именованные соединения** в `~/.config/nb_utils.toml`: секции `[connections.<имя>]` с обязательным `type = bigquery|redshift` (алиасы bq/rs), сколько угодно профилей к одной БД. Верхнеуровневый `default = "<имя>"` выбирает соединение при импорте. В строковых значениях подставляются переменные окружения `${VAR}` (незаданная — предупреждение, литерал остаётся). `config.reload()` перечитывает файл; встроенные пустые соединения `bq` и `rs` есть всегда, `config.bigquery`/`config.redshift` — legacy-алиасы на них.
- **`%connect <имя>`** выбирает соединение и регистрирует `%%sql` (до этого `%%sql` нет, если не задан `default`); без аргумента — выводит список. **`%%sql`** выполняет ячейку через активное соединение (`config.active()`), результат кладёт в `df_temp` (или в имя из `df_name=...`) и показывает через display.
- **Запросы — jinja2-шаблоны** (`sql.py`): `{{ var }}`, `{% if %}`, `{% for %}`. Скаляры вставляются как есть (кавычки для строк пишутся руками, как в dbt), list/tuple/set — в SQL-кортеж для `in` с экранированием строк. В `%%sql` переменные берутся из пространства имён ноутбука; в `run_query`/`run_file` — из `params=`, а без него тоже из ноутбука (`prepare_query`).
- `run_query`/`run_file` клиентов принимают `connection=` — имя из конфига или объект опций; `None` = активное соединение (резолвится через `options.resolve()` с проверкой типа).
- **Redshift держит пул соединений** (ключ — параметры подключения): перед переиспользованием `select 1`-проверка, TTL простоя `connection_ttl_sec` (600с), autocommit включён, при отмене запроса соединение выбрасывается из пула, atexit закрывает всё. Пароль — `password` или `password_cmd` (shell-команда, например чтение из Keychain).
- **BigQuery**: возвращает polars (через Arrow), клиенты кэшируются per-project; при `RefreshError` (протухший ADC-токен) автоматически запускается `gcloud auth application-default login` и запрос повторяется.
- Подмодули `bigquery`/`redshift`/`tableau` грузятся лениво через `__getattr__` в `__init__.py` — тяжёлые зависимости не тянутся, пока не нужны.
- Оба клиента поддерживают отмену запроса по `KeyboardInterrupt` (Redshift — через `pg_cancel_backend`) и прогресс-бар tqdm для больших выгрузок; при dtype-конфликте между чанками Redshift используется `vertical_relaxed` concat.
- SQL-подсветка ячеек `%%sql` в JupyterLab — labextension `jupyterlabs-sql-codemirror` (зависимость проекта, кода в пакете не требует).

## Конвенции

- **polars — формат результата везде.** Оба клиента возвращают polars DataFrame; pandas в кодовую базу не возвращать.
- Пользовательский вывод (print в клиентах) — на русском, с эмодзи-маркерами (`▶`, `✓`, `🚫`, `⚠️`); придерживаться этого стиля.
- BigQuery: перед выполнением всегда dry-run с оценкой объёма сканирования и подтверждением, если превышен `config.bigquery.max_bytes_billed_gb` — не убирать эту защиту.
