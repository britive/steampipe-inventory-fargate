# AWS Organization Inventory with SteamPipe and AWS Fargate

An AWS SAM template for deploying Steampipe in Fargate to take an inventory of selected AWS resources across
an entire AWS Organization.

The intent is that the solution will be invoked on a daily basis. The following actions will then be performed.

1. Collect a list of AWS accounts in the organization.
2. For each account, perform API calls against the AWS platform via Steampipe and store the results in S3 using a predetermined path/key naming convention.
3. Use Athena to query the data stored in S3.

## Deployment - Required IAM Role

NOTE: If you have another process for deploying roles in all AWS accounts (including the mgmt account) then review
the role details in `./role-deployment/inventory-role.yaml` and deploy the role via whatever process is already in place.

NOTE: StackSets must be enabled in the AWS Organization if you deploy the IAM roles via the process below.

As StackSets will not deploy to the management account we need to create a workaround for that. The workaround
is to upload the CloudFormation template to an S3 bucket in the management account and then reference it in another
template that deploys the StackSet as well as a nested stack.

NOTE: The commands below assume AWS credentials are provided as environment variables in the terminal window/session. Change to use profiles as needed.

With credentials for the management account...

~~~bash
aws cloudformation deploy --stack-name cloudformation-templates --region us-east-1 --template-file ./role-deployment/cloudformation-bucket.yaml
cfbucketname=$(aws cloudformation list-exports --region us-east-1 --output text --query 'Exports[?Name==`CloudFormationBucketName`][Value]')
aws s3 cp ./role-deployment/inventory-role.yaml s3://"$cfbucketname"/
~~~

Now we can deploy the stack that will create the needed IAM role in each account of the org.
Note that you will need to manually enter the AWS account ID of the account in which the inventory process will be deployed.

~~~
rootouid=$(aws organizations list-roots --output text --query 'Roots[0].[Id]' --region us-east-1)
inventoryaccountid=123456789012
aws cloudformation deploy \
    --stack-name steampipe-inventory-roles \
    --template-file ./role-deployment/deploy-inventory-roles-in-org.yaml \
	--parameter-overrides RootOuId="$rootouid" InventoryAccountId="$inventoryaccountid" \
    --region us-east-1 \
    --capabilities CAPABILITY_NAMED_IAM CAPABILITY_IAM
~~~

## Deploy the Steampipe Solution

It is assumed that an AWS account dedicated to this inventory process is being used. This solution can of course be deployed into another account as needed but
best practice would say to deploy into a newly created AWS account dedicated to this purpose.

NOTE: The commands below assume AWS credentials are provided as environment variables in the terminal window/session. Change to use profiles as needed.

NOTE: You may have to create the ECS Service Linked Role the first time you deploy if this is for a brand-new account.
It will be auto-created on first ECS use but the CF stack may fail the first time as the role takes non-zero amount
of time to become available.

If you want to create it beforehand do this...

~~~
aws iam create-service-linked-role --aws-service-name ecs.amazonaws.com
~~~

https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using-service-linked-roles.html

All commands below (including other sections) assume the stack name is `inventory`. Change as needed but ensure
the commands are updated accordingly.

### First Time

~~~bash
sam deploy --guided
~~~

Follow the on screen prompts to establish all the needed variables/info the first time and have it save the config to `samconfig.toml` (the default).

### Subsequent Times

Assuming the config is stored in `samconfig.toml` as `default` you can just...

~~~bash
sam deploy
~~~

Adjust the commands as needed to meet your requirements.

### Loading S3

For now we are just going to do this manually. In the future we could build a custom CF resource if needed.
~~~bash
bucket=$(aws cloudformation describe-stack-resource --stack-name inventory --logical-resource-id BucketInventory --output text --query 'StackResourceDetail.PhysicalResourceId')
aws s3 cp ./s3_content/config/table_metadata.json s3://$bucket/config/table_metadata.json
aws s3 cp ./s3_content/config/steps.sh s3://$bucket/config/steps.sh
aws s3 cp ./s3_content/config/tables.txt s3://$bucket/config/tables.txt
~~~

## Creating and Pushing the Docker Image

We have to build a docker image, so we can pre-package all the requirements to make future executions faster. 

Below are the steps to create the docker image locally and test it.

Check versions of steampipe and the aws plugin at the links below. The most recent versions will be
packaged inside the docker image.

* Steampipe: https://github.com/turbot/steampipe/releases and https://github.com/turbot/steampipe/blob/main/CHANGELOG.md
* AWS Plugin: https://hub.steampipe.io/plugins/turbot/aws and https://github.com/turbot/steampipe-plugin-aws/blob/main/CHANGELOG.md

Change `version` as required if future changes are made.

NOTE: Docker must be installing and running on the local machine.

~~~bash
cd docker
version=v1
repourl=$(aws cloudformation describe-stacks --stack-name inventory --output text --query 'Stacks[][Outputs]' | grep EcrRepository | cut -f2)
reponame=$(aws cloudformation describe-stack-resource --stack-name inventory --logical-resource-id RepositoryInventory --output text --query 'StackResourceDetail.PhysicalResourceId')
docker pull amazonlinux:latest
docker build -t $reponame:$version . --platform linux/amd64 --no-cache

# doing a full test - change the --env data as needed
# you must have AWS creds in the appropriate environment loaded as local env vars so we can pass them into the container
# NOTE: THIS MANUAL TESTING IS NOT REQUIRED TO DEPLOY THE SOLUTION BUT PROVIDED FOR CLARITY
docker run -it \
	--rm \
	--platform linux/amd64 \
	--env INVENTORY_BUCKET=<bucket>> \
	--env INVENTORY_DATE="2022/09/13" \
	--env INVENTORY_ACCOUNT=123456789012 \
	--env INVENTORY_ROLE=SteampipeInventory \
	--env AWS_ACCESS_KEY_ID \
	--env AWS_SECRET_ACCESS_KEY \
	--env AWS_SESSION_TOKEN \
	$reponame:$version \
	/bin/bash
# in the container...
./start.sh
~~~

Once we have a working local docker image we need to publish it into ECR.
This assumes that an ECR destination already exists in the appropriate account/region.
This would have been deployed via CloudFormation so pull the needed details from the stack.

~~~bash
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin $repourl
docker tag ${reponame}:$version ${repourl}:$version
docker push ${repourl}:$version
cd ..  # to get back to the base directory
~~~

If you made changes to the docker image and pushed a new version you will need to re-deploy the SAM template
so a new task definition gets created.

Update `samconfig.toml` to reflect the new version.

~~~bash
sam deploy
~~~

### Manually Invoke the Lambda Function to Start The Process for the First Time
~~~bash
lambda=$(aws cloudformation describe-stack-resource --stack-name inventory --logical-resource-id LambdaCollectAccounts --output text --query 'StackResourceDetail.PhysicalResourceId')
aws lambda invoke --function-name $lambda --invocation-type Event --qualifier prod response.json
cat response.json
rm response.json
~~~

### Check ECS Tasks

Navigate to the ECS services and select the newly deployed Fargate cluster. Review the tasks and ensure it is 1 per AWS account in the org.
Check the logs for a task and ensure that the resources are being queried.

### Query in Athena

Navigate to the Athena service. Select the `inventory` workgroup and `inventory` database.

Run a query to view the results: `select * from iam_user` as an example.

## Athena Table/View Creation

To create Athena tables/views we can read the metadata of the aws schema in the postgres db used by Steampipe.
You will need to have Steampipe installed along with the AWS plugin. Then you can run the following Steampipe query
to get the metadata into a usable format. Save the results of the below commands to the `./s3_content/config/table_metadata.json`
file and then upload that file to the appropriate S3 bucket.

NOTE: If you are adding new tables then upload the `table_metadata.json` file BEFORE `tables.txt` as a Lambda will trigger on `tables.txt` load 
and will reference `table_metadata.json`.

~~~bash
steampipe query "select table_name, column_name, data_type from information_schema.columns where table_schema = 'aws' and column_name <> '_ctx' order by table_name, ordinal_position" --output json > ./s3_content/config/table_metadata.json
bucket=$(aws cloudformation describe-stack-resource --stack-name inventory --logical-resource-id BucketInventory --output text --query 'StackResourceDetail.PhysicalResourceId')
aws s3 cp ./s3_content/config/table_metadata.json s3://$bucket/config/table_metadata.json
~~~

Then modify `./s3_content/tables.txt` to add the new table names and upload it. A Lambda will be triggered which will auto-create the Athena tables and views.

~~~bash
aws s3 cp ./s3_content/config/tables.txt s3://$bucket/config/tables.txt
~~~

### Adding New Tables/Resources
It is easy to add new resources/tables to the inventory collection process. We just have to update `./s3_content/config/tables.txt`
and copy that into the S3 bucket. A Lambda function will be triggered and will automatically create the necessary Athena resources.
On the next inventory collection run, the new table will be pulled into the process. 

NOTE: If you add a new table to the list ensure the metadata for that table is in `./s3_content/config/table_metadata.json` as that
information will be used to build the Athena resources. Upload `./s3_content/config/table_metadata.json` FIRST if changes are needed there.

~~~bash
# update ./s3_content/config/tables.txt then...
bucket=$(aws cloudformation describe-stack-resource --stack-name inventory --logical-resource-id BucketInventory --output text --query 'StackResourceDetail.PhysicalResourceId')
aws s3 cp ./s3_content/config/tables.txt s3://$bucket/config/tables.txt
~~~

## Alerts

An alerting process has been setup as part of the inventory process. 2 hours after the inventory process runs a Lambda function for alerting will run.
This function will review all records in a DynamoDB table and for each record it will run the associated Athena query. If results are returned from that
query an email will be delivered with the contents of the query. An example alert for GuardDuty can be found at `./alerts/guardduty.json`. You can manually create
that DynamoDB item 

## Stack Deletion
The SAM deployed stack will fully delete itself and clean up all resources.
Delete the other stacks as required.

