import os
import boto3
from datetime import datetime
import json


subnets = [os.environ['subnet1'], os.environ['subnet2']]
master_account_role_arn = os.environ['master_account_role_arn']
sg = os.environ['sg']
task_definition_family = os.environ['task_definition_family']
cluster = os.environ['cluster']

sts = boto3.client('sts')
ecs = boto3.client('ecs')


def get_accounts():
    raw_credentials = sts.assume_role(
        RoleArn=master_account_role_arn,
        RoleSessionName='steampipe-inventory-account-enumeration',
        DurationSeconds=900  # 15 minutes, the minimum
    )['Credentials']

    credentials = {
        'aws_access_key_id': raw_credentials['AccessKeyId'],
        'aws_secret_access_key': raw_credentials['SecretAccessKey'],
        'aws_session_token': raw_credentials['SessionToken']
    }

    orgs = boto3.client('organizations', **credentials)

    accounts = []
    params = {}

    while True:
        response = orgs.list_accounts(**params)
        accounts += response['Accounts']
        token = response.get('NextToken')
        if not token:
            break
        params['NextToken'] = token

    return [x['Id'] for x in accounts if x['Status'] == 'ACTIVE']


def handler(event, context):
    accounts = get_accounts()
    timestamp = datetime.today().strftime('%Y/%m/%d')

    # this will always pull the most recent task definition version
    task_definition = ecs.describe_task_definition(
        taskDefinition=task_definition_family
    )['taskDefinition']['taskDefinitionArn']

    for account in accounts:
        response = ecs.run_task(
            cluster=cluster,
            count=1,
            launchType='FARGATE',
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': subnets,
                    'securityGroups': [sg],
                    'assignPublicIp': 'ENABLED'
                }
            },
            overrides={
                'containerOverrides': [
                    {
                        'name': 'inventory',
                        'environment': [
                            {
                                'name': 'INVENTORY_DATE',
                                'value': timestamp
                            },
                            {
                                'name': 'INVENTORY_ACCOUNT',
                                'value': account
                            }
                        ]
                    }
                ]
            },
            taskDefinition=task_definition
        )
        print(json.dumps(response, default=str))
