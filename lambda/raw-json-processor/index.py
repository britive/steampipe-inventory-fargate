import os
from json import JSONDecodeError

import boto3
import json
import gzip
from datetime import date, datetime


prefix = os.environ['prefix']
bucket = boto3.resource('s3').Bucket(os.environ['bucket'])

table_overrides = {
    'aws_vpc': 'aws_vpc_vpc'
}


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime, date)):
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    raise TypeError("Type %s not serializable" % type(obj))


def process_sns(record):
    key = record['s3']['object']['key']  # format is raw/yyyy/mm/dd/123456789012/aws_service_resource.json
    print(f'processing {key}')
    parts = key.split('/')
    timestamp = '/'.join(parts[1:4])
    name = parts[-1].split('.')[0]
    name = table_overrides.get(name, name)  # have to account for the special cases
    account = parts[4]
    ignore, service, resource = name.split('_', 2)

    try:
        original_contents = json.loads(bucket.Object(key).get()['Body'].read().decode('utf-8'))
    # JSONDecodeError will happen when the file is empty or has 1 or 2 random characters
    # (mostly due to errors when querying the AWS API)
    except JSONDecodeError as e:
        original_contents = None
    except Exception as e:
        raise e

    # if we loaded an empty file then there is nothing to process so we are done
    if not original_contents:
        print(f'object {key} is empty so no work to do')
        return

    # we know for sure that each object represents data for one account only - so that needs to become part of the name
    # Athena is expecting stacked json format (one line per json object) and is NOT expecting
    # an array of JSON objects. As a result we need to loop through each row in the results
    # list and write the JSON representation of that object/dict
    contents = ''
    for row in original_contents:
        row.pop('partition')  # we just do not need this field so lets not waste the space
        row['account'] = row.pop('account_id')  # just to get rid of the _id as it wastes space
        contents += json.dumps(
            row,
            indent=0,
            default=json_serial,
            separators=(',', ':')
        ).replace('\n', '') + '\n'

    # new key will be processed/yyyy/mm/dd/ec2/instance/yyyy-mm-dd-123456789012-ec2-instance.json.gz
    new_prefix = f"{prefix}/{timestamp}/{service}/{resource}"
    new_key = f"{new_prefix}/{timestamp.replace('/','-')}-{account}-{service}-{resource}.json.gz"

    bucket.Object(new_key).put(
        Body=gzip.compress(contents.encode('utf-8'))
    )

    print(f"processed key: {new_key}")


def process_sqs(record):
    message = json.loads(json.loads(record['body'])['Message'])
    for sns_record in message['Records']:
        process_sns(sns_record)


def handler(event, context):
    for record in event['Records']:
        process_sqs(record)
