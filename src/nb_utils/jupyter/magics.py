from IPython.core.magic import register_cell_magic, register_line_magic

from nb_utils.sql import apply_default_limit, render_query

_sql_registered = False


def _parse_line(line):
    opts = {}
    for part in line.split():
        if "=" in part:
            key, value = part.split("=", 1)
            opts[key] = value
        else:
            opts[part] = True  # голый флаг: %%sql cache / refresh
    return opts


def _flag(opts, name):
    """None если флаг не задан; иначе bool (cache=0/false/no — выключить)."""
    if name not in opts:
        return None
    v = opts[name]
    return True if v is True else str(v).lower() not in ("0", "false", "no")


def register_sql_magic():
    global _sql_registered
    if _sql_registered:
        return

    @register_cell_magic
    def sql(line, cell):
        import nb_utils.options as options
        from nb_utils.query import run_query, run_query_by_period

        ipy = get_ipython()
        opts = _parse_line(line)
        cfg = options.config.active()
        if "limit" in opts:
            try:
                limit = int(opts["limit"])
            except ValueError:
                print(f"❌ limit должен быть числом, получено {opts['limit']!r}")
                return
        else:
            limit = options.config.default_limit
        cache = _flag(opts, "cache")
        refresh = bool(_flag(opts, "refresh"))
        cache_ttl = int(opts["cache_ttl"]) if "cache_ttl" in opts else None
        try:
            if "start_date" in opts and "end_date" in opts:
                # период рендерится внутри run_query_by_period (там появляются
                # {{ period_start }}/{{ period_end }}), сырую ячейку не трогаем.
                # Лимит здесь не применяем — это режим массовой выгрузки по окнам.
                df = run_query_by_period(
                    cell,
                    opts["start_date"],
                    opts["end_date"],
                    step_days=int(opts.get("step", 7)),
                    connection=cfg,
                    cache=cache, cache_ttl=cache_ttl, refresh=refresh,
                )
            else:
                query, limited = apply_default_limit(render_query(cell, ipy.user_ns), limit)
                if limited:
                    print(f"⚠️ применён лимит {limit} строк (%%sql limit=0 чтобы снять)")
                df = run_query(query, cfg, cache=cache, cache_ttl=cache_ttl, refresh=refresh)
        except (NameError, ValueError) as e:
            print(f"❌ {e}")
            return
        except KeyboardInterrupt:
            return  # сообщение уже напечатал клиент
        if df is None:
            return
        ipy.user_ns[opts.get("df_name") or "df_temp"] = df
        display(df)

    _sql_registered = True


def register_magics():
    import nb_utils.options as options

    @register_line_magic
    def connect(line):
        name = line.strip()
        conns = options.config.connections
        if not name:
            print("Доступные соединения:")
            for conn_name, conn in conns.items():
                marker = "→" if conn_name == options.config.connection else " "
                print(f" {marker} {conn_name} ({conn.type})")
            return
        if name not in conns:
            print(f"❌ Неизвестное соединение: '{name}'. Доступные: {', '.join(conns)}")
            return
        options.config.connection = name
        register_sql_magic()
        print(f"✓ Соединение: {name} ({conns[name].type})")

    # default в конфиге уже выбрал соединение — %%sql доступна сразу
    if options.config.connection:
        register_sql_magic()
