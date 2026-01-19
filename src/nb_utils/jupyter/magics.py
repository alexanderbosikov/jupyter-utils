from IPython.core.magic import register_cell_magic
from nb_utils.bigquery import run_query

def register_bq_magic():
    @register_cell_magic
    def bq(line, cell):
        args = line.split()
        max_gb = 5
        page_size = 20
        df_name = None
    
        for part in args:
            if part.startswith("df_name="):
                df_name = str(part.split("=")[1])
    
        query = cell
        df = run_query(query)

        ipy = get_ipython()
        if df_name:
            ipy.user_ns[df_name] = df
        else:
            ipy.user_ns['df_temp'] = df

        display(df)