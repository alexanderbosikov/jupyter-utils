from IPython.core.magic import register_cell_magic, register_line_magic

from nb_utils.sql import render_query

_sql_registered = False


def _parse_line(line):
    df_name = None
    for part in line.split():
        if part.startswith("df_name="):
            df_name = part.split("=", 1)[1]
    return df_name


def _run_query(cfg, query):
    if cfg.type == "bigquery":
        from nb_utils import bigquery
        return bigquery.run_query(query, cfg)
    if cfg.type == "redshift":
        from nb_utils import redshift
        return redshift.run_query(query, cfg)
    print(f"❌ Неизвестный тип соединения: {cfg.type!r}")
    return None


def register_sql_magic():
    global _sql_registered
    if _sql_registered:
        return

    @register_cell_magic
    def sql(line, cell):
        import nb_utils.options as options
        ipy = get_ipython()
        df_name = _parse_line(line)
        try:
            query = render_query(cell, ipy.user_ns)
        except NameError as e:
            print(f"❌ {e}")
            return
        df = _run_query(options.config.active(), query)
        if df is None:
            return
        ipy.user_ns[df_name or "df_temp"] = df
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
