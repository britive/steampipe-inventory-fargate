#!/bin/bash

# for local dev we need to save the passed in env vars so we can revert back to them
# for the s3 cp calls at the end
if [[ -z "${AWS_ACCESS_KEY_ID}" ]]; then
  echo "using ecs container credentials"
else
  echo "saving env var aws creds as we are testing locally"
  BACKUP_AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID}"
  BACKUP_AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY}"
  BACKUP_AWS_SESSION_TOKEN="${AWS_SESSION_TOKEN}"
fi

# assume the role for inventory scanning - even if we are doing local dev/testing
# we can assume this role and overwrite the passed in env vars

echo "assuming role"
creds=$(aws sts assume-role --role-arn arn:aws:iam::"${INVENTORY_ACCOUNT}":role/"$INVENTORY_ROLE" --role-session-name steampipe-inventory --output text --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]')
export AWS_ACCESS_KEY_ID=$(echo $creds | cut -d ' ' -f1)
export AWS_SECRET_ACCESS_KEY=$(echo $creds | cut -d ' ' -f2)
export AWS_SESSION_TOKEN=$(echo $creds | cut -d ' ' -f3)
aws sts get-caller-identity --output text


# we need to determine the mgmt account id for at least 1 of the API calls (organizations_account)
mgmt_account=$(aws organizations describe-organization --output text --query 'Organization.MasterAccountId')

# loop over all tables and query them across all regions
cat tables.txt | while read row
do
	echo "$row"
	table=$(echo "$row" | cut -d '|' -f1)
	override_query=$(echo "$row" | cut -d '|' -f2)
	query="select * from $table"

	if [[ "$table" != "$override_query" ]]; then
	  query=$override_query
	fi

  # the s3 calls seem to error out sometimes when including all the regions
  # and we dont really need all the regions for the calls to work (even though
  # steampipe will perform the de-duplication)
  # so lets shuffle the config files
	if [[ "$table" == "aws_s3_bucket" ]]; then
	  mv ~/.steampipe/config/aws.spc ~/.steampipe/config/aws.spc.multi-region
	  mv ~/.steampipe/config/aws.spc.single-region ~/.steampipe/config/aws.spc
	fi

	if [[ "$table" == "aws_organizations_account"  ]] && [[ "$INVENTORY_ACCOUNT" == "$mgmt_account" ]]; then
	  steampipe query "$query" --output json > ./inventory/"$table".json
	elif [[ "$table" != "aws_organizations_account"  ]]; then
	  steampipe query "$query" --output json > ./inventory/"$table".json
	fi

  # and now we need to unshuffle the config files if we just queries for s3 buckets
	if [[ "$table" == "aws_s3_bucket" ]]; then
	  mv ~/.steampipe/config/aws.spc ~/.steampipe/config/aws.spc.single-region
	  mv ~/.steampipe/config/aws.spc.multi-region ~/.steampipe/config/aws.spc
	fi

done

if [[ -z "${BACKUP_AWS_ACCESS_KEY_ID}" ]]; then # we are in a fargate task so just unset the env vars we set before to get back to the default ecs container credentials
  echo "unsetting aws credential env vars to get back to pulling from EcsContainer"
  unset AWS_ACCESS_KEY_ID
  unset AWS_SECRET_ACCESS_KEY
  unset AWS_SESSION_TOKEN
else # we are in local dev so store the env vars passed in
  echo "restoring passed in env vars for local dev"
  AWS_ACCESS_KEY_ID="${BACKUP_AWS_ACCESS_KEY_ID}"
  AWS_SECRET_ACCESS_KEY="${BACKUP_AWS_SECRET_ACCESS_KEY}"
  AWS_SESSION_TOKEN="${BACKUP_AWS_SESSION_TOKEN}"
fi

aws s3 cp inventory/ s3://"$INVENTORY_BUCKET"/raw/"$INVENTORY_DATE"/"$INVENTORY_ACCOUNT"/ --recursive
