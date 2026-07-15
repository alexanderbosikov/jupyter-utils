import tableauserverclient as tsc
import uuid
import nb_utils.options as options

class Connection:
    def __enter__(self):
        serverurl = options.config.tableau.server_url
        sitename = options.config.tableau.site_name
        tokenName = options.config.tableau.token_name
        tokenSecret = options.config.tableau.token_secret

        self.tableau_auth = tsc.PersonalAccessTokenAuth(tokenName, tokenSecret, sitename)
        self.server = tsc.Server(serverurl, use_server_version=True)
        self.server.auth.sign_in(self.tableau_auth)
        return self.server

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.server.auth.sign_out()

def get_datasources(server):
    all_datasources = list(tsc.Pager(server.datasources))
    datasources = []
    for datasource in all_datasources:
        datasources.append({
            "id": datasource.id,
            "name": datasource.name,
            "owner_id": datasource.owner_id,
            "project_id": datasource.project_id,
            "project_name": datasource.project_name
        })
    return datasources

def get_datasource_by_id(server, datasource_id):
    datasource = server.datasources.get_by_id(datasource_id)
    return datasource

def overwrite_datasource(server, datasource, hyper_file):
    job = server.datasources.publish(datasource, hyper_file, "Overwrite", as_job=True)

    print(f"Overwrite job posted (ID: {job.id})")
    job = server.jobs.wait_for_job(job)
    print("Job finished successfully")
    return datasource

def delete_data(server, datasource, table_name, column_name, start_date, end_date):
    actions = [
        {
            "action": "delete",
            "target-table": table_name,
            "condition": {
                "op": "and",
                "args": [{
                    "op": "gte",
                    "target-col": column_name,
                    "const": {
                        "type": "string",
                        "v": start_date
                    }
                },{
                    "op": "lte",
                    "target-col": column_name,
                    "const": {
                        "type": "string",
                        "v": end_date
                    }
                }]
                
            }
        }
    ]
    request_id = str(uuid.uuid4())

    job = server.datasources.update_hyper_data(
        datasource,
        request_id=request_id,
        actions=actions
    )

    print(f"Delete job posted (ID: {job.id})")
    job = server.jobs.wait_for_job(job)
    print("Job finished successfully")

def insert_data(server, datasource, table_name, hyper_file):
    actions = [
        {
            "action": "insert",
            "source-table": table_name,
            "target-table": table_name
        }
    ]
    request_id = str(uuid.uuid4())

    job = server.datasources.update_hyper_data(
        datasource,
        request_id=request_id,
        actions=actions,
        payload=hyper_file
    )
    print(f"Insert job posted (ID: {job.id})")
    job = server.jobs.wait_for_job(job)
    print("Job finished successfully")

def create_datasource_on_server(server, project_id, hyper_file):
    new_datasource = tsc.DatasourceItem(project_id)
    print("DS ID", new_datasource.id)
    job = server.datasources.publish(new_datasource, hyper_file, "CreateNew", as_job=True)

    print(f"Create job posted (ID: {job.id})")
    job = server.jobs.wait_for_job(job)
    print("Job finished successfully")
    return new_datasource