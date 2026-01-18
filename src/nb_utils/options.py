class BigQueryOptions:
    def __init__(self):
        self.project_id: str = "default_project_id"
        self.location: str = "US"
        self.max_bytes_billed_gb: int = 5
        self.verbose: bool = True

class NBUtilsOptions:
    def __init__(self):
        self.bigquery = BigQueryOptions()

options = NBUtilsOptions()