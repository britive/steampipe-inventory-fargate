import boto3

s3 = boto3.resource('s3')


# no op
def create(helper, event):
    pass


# no op
def update(helper, event):
    pass


def delete(helper, event):
    properties = event['ResourceProperties']
    bucket_name = properties['BucketName']
    s3.Bucket(bucket_name).objects.all().delete()
