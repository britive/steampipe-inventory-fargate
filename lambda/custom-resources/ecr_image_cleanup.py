import boto3

ecr = boto3.client('ecr')


# no op
def create(helper, event):
    pass


# no op
def update(helper, event):
    pass


def delete(helper, event):
    properties = event['ResourceProperties']
    repo = properties['Repository']

    images = []
    params = {
        'repositoryName': repo
    }

    while True:
        response = ecr.list_images(**params)
        images += response['imageIds']
        token = response.get('nextToken')
        if not token:
            break
        params['nextToken'] = token

    if len(images) > 0:
        ecr.batch_delete_image(
            repositoryName=repo,
            imageIds=[{'imageDigest': x['imageDigest']} for x in images]
        )
