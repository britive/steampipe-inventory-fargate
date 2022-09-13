import os
import boto3
import time
import json

workgroup = os.environ['workgroup']
bucket_name = os.environ['bucket']
bucket = boto3.resource('s3').Bucket(bucket_name)
database = os.environ['database']
athena = boto3.client('athena')
catalog = 'AwsDataCatalog'
prefix = os.environ['prefix']

datatype_mappings = {
    'cidr': 'string',
    'inet': 'string',
    'boolean': 'boolean',
    'timestamp with time zone': 'timestamp',
    'bigint': 'bigint',
    'text': 'string',
    'double precision': 'double',
    'jsonb': 'string'
}

skip_columns = [
    'partition'
]

table_overrides = {
    'vpc': 'vpc_vpc'
}


def execute_query(query):
    printable_query = query.replace('\n', ' ')
    print(f"executing query: {printable_query}")
    execution_id = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={
            'Database': database,
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


def format_metadata():
    metadata = json.loads(bucket.Object('config/table_metadata.json').get()['Body'].read().decode('utf-8'))
    tables = {}
    for row in metadata:
        table = row['table_name'].replace('aws_', '')
        table = table_overrides.get(table, table)  # have to handle the special cases for table names
        column = row['column_name']
        datatype = datatype_mappings[row['data_type']]

        if column in skip_columns:
            continue

        # removing the "_id" as that is was the raw JSON processor does to save space
        if column == 'account_id':
            column = 'account'

        # handle some known JSON format data types
        if column == 'akas':
            datatype = 'array<string>'

        if column == 'tags_src':
            datatype = 'array<struct<Key:string,Value:string>>'

        if table not in tables.keys():
            tables[table] = {}
        tables[table][column] = datatype
    return tables


def get_expected_tables():
    raw_tables = bucket.Object('config/tables.txt').get()['Body'].read().decode('utf-8').split('\n')
    tables = []
    for raw_table in raw_tables:
        if raw_table.startswith('aws_'):
            table = raw_table.split('|')[0]
            table = table.replace('aws_', '')
            table = table_overrides.get(table, table)  # have to handle the special cases for table names
            tables.append(table)
    return sorted(tables)


def get_actual_tables():
    params = {
        'CatalogName': catalog,
        'DatabaseName': database
    }

    tables = []

    while True:
        response = athena.list_table_metadata(**params)
        tables += [t['Name'].replace('_snapshots', '') for t in response['TableMetadataList'] if t['Name'].endswith('_snapshots')]
        token = response.get('NextToken')
        if not token:
            break
        params['NextToken'] = token

    return tables


def delete_tables(tables):
    for table in tables:
        execute_query(f'drop view {table}')
        execute_query(f'drop table {table}_snapshots')


def build_fields(columns):
    fields = []
    for column, datatype in dict(sorted(columns.items())).items():
        fields.append(f'`{column}` {datatype}')
    return ',\n'.join(fields)


def replace_template_and_execute(template, replacements):
    for key, value in replacements.items():
        template = template.replace(f'#{key}#', value)
    execute_query(template)


def create_tables(tables, metadata):
    for table in tables:
        print(f'attempting to create table {table}')
        service, resource = table.split('_', 1)
        fields = build_fields(metadata[table])

        replacements = {
            'service': service,
            'resource': resource,
            'bucket': bucket_name,
            'prefix': prefix,
            'fields': fields
        }

        templates = ['template-table.sql', 'template-view.sql']

        for template in templates:
            with open(template, 'r') as f:
                template_contents = f.read()
            replace_template_and_execute(template_contents, replacements)


def handler(event, context):
    metadata = format_metadata()
    expected_tables = get_expected_tables()
    actual_tables = get_actual_tables()

    creates = list(set(expected_tables) - set(actual_tables))
    deletes = list(set(actual_tables) - set(expected_tables))

    if len(creates) > 0:
        create_tables(creates, metadata)

    if len(deletes) > 0:
        delete_tables(deletes)




