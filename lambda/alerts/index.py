import boto3
import json
import os
import time

table = boto3.resource('dynamodb').Table(os.environ['table'])
athena = boto3.client('athena')
database = os.environ['database']
catalog = os.environ['catalog']
workgroup = os.environ['workgroup']
topic = boto3.resource('sns').Topic(os.environ['topic'])


def clean_results(results):
    columns = [c['Name'] for c in results['ResultSetMetadata']['ColumnInfo']]
    data = []

    first = True
    for row in results['Rows']:
        if first:  # skip the header row
            first = False
            continue

        item = [i.get('VarCharValue', None) for i in row['Data']]
        item2 = []
        for i in item:
            try:
                item2.append(json.loads(i))
            except:
                item2.append(i)

        data.append(dict(zip(columns, item2)))
    return data


def process_results(query, execution_id):
    params = {
        'QueryExecutionId': execution_id
    }
    results = []
    while True:
        response = athena.get_query_results(
            QueryExecutionId=execution_id
        )
        results += clean_results(response['ResultSet'])
        token = response.get('NextToken')
        if not token:
            break
        params['NextToken'] = token

    if len(results) == 0:
        print('no data returned for query')
        return

    # if we get here then we have to alert to the sns topic
    topic.publish(
        Message=json.dumps(results, indent=4, default=str),
        Subject=query['subject']
    )
    print('published the following json to topic')
    print(json.dumps(results, default=str))


def process(query):
    print('running the following query')
    print(query)
    execution_id = athena.start_query_execution(
        QueryString=query['query'],
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
        state = response['Status']['State']
        if state in ['SUCCEEDED']:
            break
        if state in ['QUEUED', 'RUNNING']:
            continue
        if state in ['CANCELLED']:
            print('query cancelled - skipping')
            return
        if state in ['FAILED']:
            print('query failed - error message below')
            print(json.dumps(response['Status']['StateChangeReason'], default=str))
            return

    # if we get here we have successful query - still could be no results
    process_results(query, execution_id)


def handler(event, context):
    queries = table.scan()['Items']
    for query in queries:
        process(query)
