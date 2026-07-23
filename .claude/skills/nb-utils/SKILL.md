---
name: nb-utils
description: Как правильно писать Python-код и Jupyter-ноутбуки с пакетом nb_utils (jupyter-utils) — запросы к Redshift/BigQuery через %%sql и run_query, jinja2-шаблоны в SQL, дефолтный лимит и кэш результатов, запросы по окнам дат, оформление ноутбука для HTML/PDF-экспорта (report_style), публикация в Tableau. Использовать всегда при написании кода/ноутбуков, где есть nb_utils, %%sql, run_query, run_query_by_period, report_style или выгрузка/экспорт данных.
---

# nb_utils: запросы к данным из ноутбуков

## Базовое

```python
import nb_utils                     # side effects: регистрирует %connect и %%sql, включает itables
from nb_utils import run_query, run_query_by_period, config
```

- Соединения описаны в `~/.config/nb_utils.toml` (`[connections.<имя>]`, `type = bigquery|redshift`, алиасы `bq`/`rs`); `default = "<имя>"` активирует соединение при импорте. `config.reload()` перечитывает файл.
- `%connect` без аргумента — список соединений, `%connect <имя>` — переключение. Магика `%%sql` доступна только после выбора соединения (через default или %connect).
- **Все результаты — polars DataFrame.** Никогда не конвертировать в pandas; для тяжёлой пост-обработки предпочитать lazy API (`df.lazy()`).

## Запросы

```python
df = run_query("select ...")                          # активное соединение
df = run_query("select ...", connection="rs_prod")    # именованное из конфига
df = run_query(Path("query.sql").read_text())         # запрос из файла (run_file нет)
```

В ноутбуке — магика (результат кладётся в `df_temp` и показывается через display):

```
%%sql
select ...
```

Опции в строке магики (через пробел): `df_name=my_df` — имя переменной результата (иначе `df_temp`); `limit=N` / `limit=0` — лимит на ячейку (см. ниже); `cache` / `refresh` / `cache_ttl=N` — кэш (см. ниже); `start_date=... end_date=... step=7` — режим по окнам дат.

## Дефолтный лимит

Обычный `%%sql` дописывает `limit N` к SELECT/WITH, если своего `limit` нет — по `config.default_limit` (дефолт 1000); при срабатывании печатает `⚠️`. Переопределить на ячейку — `%%sql limit=5000`, снять — `%%sql limit=0`. **Не** применяется к `run_query` и к режиму по окнам (`start_date=/end_date=`). Если выборка выглядит «ровно 1000 строк» — скорее всего сработал дефолтный лимит.

## Кэш результатов

Результат можно кэшировать на диск (parquet, `~/.cache/nb_utils/queries/`) — переживает рестарт kernel:

```python
df = run_query(sql, cache=True)                  # 1-й раз выполнит и сохранит, потом — из кэша
df = run_query(sql, cache=True, refresh=True)     # данные в БД обновились — перезапросить
df = run_query(sql, cache=True, cache_ttl=3600)   # TTL, сек (None → config.cache_ttl_sec)
```

- Ключ — хэш **отрендеренного** SQL + соединение: смена текста/параметров запроса инвалидирует кэш сама; «запрос тот же, данные обновились» — по TTL (дефолт 24ч) или `refresh=True`.
- `cache=None` (дефолт) → `config.cache_default` (дефолт **False**). Из магики — `%%sql cache` / `%%sql refresh`.
- Первый прогон **не быстрее** (miss → полный запрос → сохранение); ускоряются повторные запуски и после рестарта kernel.
- DML (без результата) не кэшируется. Очистка — `nb_utils.clear_cache()` или `clear_cache(older_than_days=N)`. Файлы сами не удаляются.

## Jinja2-шаблоны в SQL

Каждый запрос — jinja2-шаблон (`{{ var }}`, `{% if %}`, `{% for %}`). Правила подстановки:

- Скаляры вставляются «как есть» — **кавычки для строк/дат писать руками**, как в dbt: `where dt >= '{{ start_date }}' and user_id = {{ uid }}`
- list/tuple/set разворачиваются в SQL-кортеж с экранированием строк — для `in`: `where country in {{ countries }}`
- Откуда берутся переменные: в `%%sql` — из пространства имён ноутбука; в `run_query` — из `params={...}`, а если `params` не передан — тоже из ноутбука.
- Неопределённая переменная — ошибка (StrictUndefined), а не молчаливый пропуск.

## Запросы по окнам дат (большие выгрузки)

```python
df = run_query_by_period(query, "2026-01-01", "2026-07-01", step_days=7)
```

- В шаблоне обязательны `{{ period_start }}` / `{{ period_end }}` (ISO-строки дат).
- Окна **полуоткрытые** `[start, end)` — фильтр писать строго так:
  `where dt >= '{{ period_start }}' and dt < '{{ period_end }}'` (не `between`, не `<=`).
- `end_date` в выборку не входит. Ctrl+C возвращает собранное к этому моменту. Результаты склеиваются `vertical_relaxed`.
- Из магики: `%%sql start_date=2026-01-01 end_date=2026-07-01 step=7`.

## Особенности бэкендов

- **Redshift**: пул соединений с TTL, отмена запроса по Ctrl+C через `pg_cancel_backend`. `current_timestamp` возвращает timestamptz — `datediff` с ним падает, использовать `getdate()`/`sysdate` или каст `::timestamp`.
- **BigQuery**: перед выполнением всегда dry-run с оценкой сканирования и подтверждением при превышении `config.bigquery.max_bytes_billed_gb` — эту защиту не отключать и не обходить. Протухший ADC-токен переавторизуется автоматически.
- Подмодули ленивые: ImportError с подсказкой = не установлена dependency-group (`uv sync --group bq` и т.п.).

## Tableau

```python
from nb_utils import tableau

with tableau.Connection() as server:
    ds = tableau.get_datasource_by_id(server, datasource_id)
    tableau.overwrite_datasource(server, ds, "data.hyper")      # полная замена
    tableau.insert_data(server, ds, "Extract", "data.hyper")    # дозапись
    tableau.delete_data(server, ds, "Extract", "dt", "2026-01-01", "2026-01-31")  # удаление по датам
    tableau.get_datasources(server)                             # список источников
```

Креды — секция `[tableau]` в `~/.config/nb_utils.toml` (server_url, site_name, token_name, token_secret).

## Экспорт отчётов (HTML/PDF)

`nb_utils.report_style()` в ячейке — оформление ноутбука для экспорта nbconvert: колонка контента по центру, графики на всю ширину, кнопка «скрыть код», боковое оглавление-дерево со сворачиваемыми ветками. Действует **только в экспорте** (в живом JupyterLab вид не меняет). Экспортировать через File → Save and Export As → HTML с **Disable sanitize** — иначе JupyterLab вырежет `<style>`/`<script>`/кнопки, и ничего не применится. Параметры: `max_width`, `center`, `wide_plots`, `code_toggle`, `toc`, `avoid_breaks`. Ставить вызов можно в любом месте ячейки (сам себя отображает). Таблицы itables в HTML интерактивны при наличии интернета; в WebPDF — статичное превью.

## Стиль в ноутбуках

- SQL внутри `%%sql`/запросов: CTE вместо вложенных подзапросов, snake_case, нижний регистр ключевых слов; алиасы у колонок — только когда в запросе больше одного источника.
- Результат `%%sql` без `df_name=` перезаписывает `df_temp` — для промежуточных результатов, которые нужны дальше, всегда задавать `df_name=`.
- Пользовательский вывод (print) — на русском с эмодзи-маркерами `▶ ✓ 🚫 ⚠️`.
