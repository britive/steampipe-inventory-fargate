#!/bin/bash
aws s3 cp s3://$INVENTORY_BUCKET/config/steps.sh .
aws s3 cp s3://$INVENTORY_BUCKET/config/tables.txt .
chmod u+x steps.sh
./steps.sh