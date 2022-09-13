import boto3
import time

athena = boto3.client('athena')


def execute_query(catalog, workgroup, query):
    printable_query = query.replace('\n', ' ')
    print(f"executing query: {printable_query}")
    execution_id = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={
            'Database': 'default',
            'Catalog': catalog
        },
        WorkGroup=workgroup
    )['QueryExecutionId']

    while True:
        time.sleep(1)
        response = athena.get_query_execution(
            QueryExecutionId=execution_id
        )['QueryExecution']

        status = response['Status']['State']
        if status in ['SUCCEEDED']:
            print('query succeeded')
            break
        if status in ['CANCELLED', 'FAILED']:
            print('resource creation error')
            print(response['Status']['StateChangeReason'])
            break
        if status in ['QUEUED', 'RUNNING']:
            continue


# we need to check if the database already exists and if not, create it
def create(helper, event):
    properties = event['ResourceProperties']
    catalog = properties['Catalog']
    database = properties['Database']
    workgroup = properties['Workgroup']
    try:
        athena.get_database(
            CatalogName=catalog,
            DatabaseName=database
        )
    except Exception as e:
        if f'Database {database} not found' in str(e):
            execute_query(catalog, workgroup, f'create database {database}')
        else:
            raise e

    return database


# no actions required on an update as one cannot update the name of the stack without re-creating it
def update(helper, event):
    pass


def delete(helper, event):
    properties = event['ResourceProperties']
    catalog = properties['Catalog']
    database = properties['Database']
    workgroup = properties['Workgroup']
    execute_query(catalog, workgroup, f'drop database {database} cascade')
