class BigQueryOptions:
    def __init__(self):
        self.project_id: str = "project_id"
        self.location: str = "US"
        self.max_bytes_billed_gb: int = 5
        self.min_rows_for_storage_api = 100000
        self.verbose: bool = True

class TableauOptions:
    def __init__(self):
        self.server_url: str = None
        self.site_name: str = None
        self.token_name: str = None
        self.token_secret: str = None

class NBUtilsOptions:
    def __init__(self):
        self.bigquery = BigQueryOptions()
        self.tableau = TableauOptions()

config = NBUtilsOptions()