# jupyter-utils

Личный пакет `nb_utils` для работы с данными в Jupyter Lab: запросы к BigQuery и Redshift через cell-магику `%%sql`, публикация данных в Tableau.

## Окружение и команды

- Менеджер — **uv** (`uv sync`, `uv add <pkg>`), сборка hatchling, Python ≥ 3.12.
- Зависимости всех бэкендов (Redshift, BigQuery, Tableau) — dependency-groups `rs`/`bq`/`tableau`; активный стек задаётся в `tool.uv.default-groups` в pyproject.toml (сейчас `["dev", "rs", "pdf"]`) и ставится обычным `uv sync`. Без группы подмодуль при обращении даёт ImportError с подсказкой.
- Группа `pdf` — экспорт ноутбуков в PDF через `nbconvert[webpdf]` (headless-Chromium, без LaTeX). После первого `uv sync` на новой машине нужен разовый `uv run playwright install chromium`. Экспорт: File → Save and Export Notebook As → WebPDF, либо `uv run jupyter nbconvert --to webpdf <ноутбук>`.
- Тесты: `uv run pytest` (покрыт `options.py`); остальное проверяется вручную в Jupyter Lab.
- `notebooks/` и `*.ipynb` в корне — личные scratch-анализы, к коду пакета отношения не имеют: не трогать и не учитывать при работе над пакетом.

## Архитектура

```
src/nb_utils/
├── __init__.py      # side effects при import: регистрирует магики + itables
├── options.py       # config — глобальный синглтон настроек (nb_utils.config)
├── sql.py           # jinja2-рендеринг запросов (render_query/prepare_query)
├── query.py         # run_query (диспетчер по типу соединения), run_query_by_period
├── jupyter/         # магики %%sql и %connect, enable()
├── bigquery/        # run_query (polars), авто-relogin gcloud ADC
├── redshift/        # run_query (polars), пул соединений, IAM или user/password
└── tableau/         # Connection (context manager), publish/insert/delete hyper
```

Ключевые механики:

- **`import nb_utils` имеет побочные эффекты**: регистрирует `%connect` и включает `itables.init_notebook_mode(all_interactive=True, connected=True)` (последнее — только в notebook-ядре, не в консольном IPython; вне IPython не делает ничего). Ошибки инициализации печатаются предупреждением, см. `jupyter/enable.py`. `connected=True` — таблицы тянут DataTables с CDN, чтобы рендериться в HTML-экспорте nbconvert (offline-бандл `connected=False` не резолвится в standalone-файле, ES-модуль не грузится с `file://`); плата — нужен интернет при просмотре.
- **`nb_utils.report_style(max_width="60rem", center=True, wide_plots=True, code_toggle=True, toc=True, avoid_breaks=True)`** (`report.py`) — готовит ноутбук к HTML/PDF-экспорту, **отображает `<style>`/`<script>`/кнопки сразу через `display`** (side effect — можно ставить в любом месте ячейки). Колонка текста/кода/таблиц по центру; `wide_plots` — графики (вывод с `<img>`, `:has(img)`) на всю ширину контент-области; `code_toggle` — фикс-кнопка справа сверху скрывает/показывает весь код (класс `hide-code`); `toc` — боковое оглавление из заголовков markdown **деревом по уровням** (строится JS'ом), у веток с детьми каретка ▾/▸ сворачивает вложенные пункты **в самом оглавлении** (не в теле), бургер слева сворачивает сайдбар, при показе сайдбар сдвигает контент через `padding-left` тела (графики `max-width:100%` ужимаются сами); прячет `In[]/Out[]`-подписи; `avoid_breaks` — не рвёт блоки между страницами PDF. Шрифт кнопок/TOC — из `--jp-content-font-*` (совпадает с текстом ноутбука). Всё через `@media print` в PDF отключается (JS там нет). Селектор `body.jp-Notebook` применяет всё **только к экспорту nbconvert** (в живом JupyterLab body без этого класса). **Требует экспорта с «Disable sanitize»** — иначе JupyterLab вырежет `<style>`/`<script>`/кнопки. Проверено рендером в headless-Chromium (`_report_css` — чистая функция сборки CSS, покрыта тестами).
- **Именованные соединения** в `~/.config/nb_utils.toml`: секции `[connections.<имя>]` с обязательным `type = bigquery|redshift` (алиасы bq/rs), сколько угодно профилей к одной БД. Верхнеуровневый `default = "<имя>"` выбирает соединение при импорте. В строковых значениях подставляются переменные окружения `${VAR}` (незаданная — предупреждение, литерал остаётся). `config.reload()` перечитывает файл; встроенные пустые соединения `bq` и `rs` есть всегда, `config.bigquery`/`config.redshift` — legacy-алиасы на них.
- **`%connect <имя>`** выбирает соединение и регистрирует `%%sql` (до этого `%%sql` нет, если не задан `default`); без аргумента — выводит список. **`%%sql`** выполняет ячейку через активное соединение (`config.active()`), результат кладёт в `df_temp` (или в имя из `df_name=...`) и показывает через display.
- **Запросы — jinja2-шаблоны** (`sql.py`): `{{ var }}`, `{% if %}`, `{% for %}`. Скаляры вставляются как есть (кавычки для строк пишутся руками, как в dbt), list/tuple/set — в SQL-кортеж для `in` с экранированием строк. В `%%sql` переменные берутся из пространства имён ноутбука; в `run_query` — из `params=`, а без него тоже из ноутбука (`prepare_query`).
- `run_query` принимает `connection=` — имя из конфига или объект опций; `None` = активное соединение (резолвится через `options.resolve()` с проверкой типа). Запуск `.sql`-файла — `run_query(Path(...).read_text())`, отдельного `run_file` нет.
- **Кэш результатов** (`cache.py`): `run_query(..., cache=, cache_ttl=, refresh=)` сохраняет результат в parquet в `~/.cache/nb_utils/queries/` (ключ — хэш **отрендеренного** SQL + идентификатор соединения из `_conn_id`), переживает рестарт kernel. `cache=None` → `config.cache_default` (дефолт **False**); `cache_ttl=None` → `config.cache_ttl_sec` (дефолт 86400, `<=0` — без истечения); `refresh=True` — игнорировать кэш и перезаписать. Смена текста/параметров запроса меняет ключ → авто-инвалидация; «данные в БД обновились, запрос тот же» — по TTL или `refresh`. DML (`df=None`) не кэшируется. В `run_query_by_period` кэшируется итоговый склеенный df (ключ — запрос + окно `start:end:step` + соединение; окна внутри не кэшируются). Из магики — `%%sql cache` / `%%sql refresh` / `%%sql cache_ttl=N` (голые флаги, `cache=0` — выключить). Файлы **не самоудаляются** (TTL лишь гейтит чтение); `nb_utils.clear_cache()` сносит весь кэш, `clear_cache(older_than_days=N)` — только записи старше N дней (по `saved_at`, иначе mtime). Оба top-level ключа (`cache_default`, `cache_ttl_sec`) читаются из toml.
- **Redshift держит пул соединений** (ключ — параметры подключения): перед переиспользованием `select 1`-проверка, TTL простоя `connection_ttl_sec` (600с), autocommit включён, при отмене запроса соединение выбрасывается из пула, atexit закрывает всё. Пароль — `password` или `password_cmd` (shell-команда, например чтение из Keychain).
- **BigQuery**: возвращает polars (через Arrow), клиенты кэшируются per-project; при `RefreshError` (протухший ADC-токен) автоматически запускается `gcloud auth application-default login` и запрос повторяется.
- Подмодули `bigquery`/`redshift`/`tableau` грузятся лениво через `__getattr__` в `__init__.py` — тяжёлые зависимости не тянутся, пока не нужны.
- **Запросы по окнам дат**: `nb_utils.run_query_by_period(query, start_date, end_date, step_days)` рендерит `{{ period_start }}`/`{{ period_end }}` (полуоткрытые окна `[start, end)`) и склеивает результаты; из магики — `%%sql start_date=... end_date=... step=7`. Ctrl+C возвращает собранное.
- Отмена по `KeyboardInterrupt`: Redshift отменяет запрос через `pg_cancel_backend` и **пробрасывает исключение дальше** (магика его глушит); прогресс-бар tqdm для больших выгрузок; при dtype-конфликте между чанками Redshift используется `vertical_relaxed` concat.
- **Дефолтный лимит `%%sql`**: `config.default_limit` (дефолт 1000, top-level `default_limit` в toml) дописывает `limit N` к SELECT/WITH-запросам магии `%%sql`, если завершающего `limit` ещё нет. Логика — `sql.apply_default_limit`; при срабатывании печатается заметка `⚠️`. Не-SELECT (DML/DDL/explain) и запросы с уже имеющимся `limit` не трогаются. Переопределение на ячейку — `%%sql limit=N`, снятие — `%%sql limit=0`. Применяется **только** к обычному `%%sql` (не к `run_query` и не к режиму по периодам `start_date=/end_date=`).
- SQL-подсветка ячеек `%%sql` в JupyterLab — labextension `jupyterlabs-sql-codemirror` (зависимость проекта, кода в пакете не требует).

## Конвенции

- **polars — формат результата везде.** Оба клиента возвращают polars DataFrame; pandas в кодовую базу не возвращать.
- Пользовательский вывод (print в клиентах) — на русском, с эмодзи-маркерами (`▶`, `✓`, `🚫`, `⚠️`); придерживаться этого стиля.
- BigQuery: перед выполнением всегда dry-run с оценкой объёма сканирования и подтверждением, если превышен `config.bigquery.max_bytes_billed_gb` — не убирать эту защиту.
