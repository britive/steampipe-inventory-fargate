from crhelper import CfnResource
import athena_database
import ecr_image_cleanup
import s3_object_nuker

helper = CfnResource()

valid_resource_types = [
    'Custom::AthenaDatabase',
    'Custom::EcrImageCleanup',
    'Custom::S3ObjectNuker'
]


@helper.create
def create(event, context):
    resource_type = event['ResourceType']
    if resource_type == 'Custom::AthenaDatabase':
        return athena_database.create(helper, event)
    if resource_type == 'Custom::EcrImageCleanup':
        return ecr_image_cleanup.create(helper, event)
    if resource_type == 'Custom::S3ObjectNuker':
        return s3_object_nuker.create(helper, event)


@helper.update
def update(event, context):
    resource_type = event['ResourceType']
    if resource_type == 'Custom::AthenaDatabase':
        return athena_database.update(helper, event)
    if resource_type == 'Custom::EcrImageCleanup':
        return ecr_image_cleanup.update(helper, event)
    if resource_type == 'Custom::S3ObjectNuker':
        return s3_object_nuker.update(helper, event)


@helper.delete
def delete(event, context):
    resource_type = event['ResourceType']
    if resource_type == 'Custom::AthenaDatabase':
        return athena_database.delete(helper, event)
    if resource_type == 'Custom::EcrImageCleanup':
        return ecr_image_cleanup.delete(helper, event)
    if resource_type == 'Custom::S3ObjectNuker':
        return s3_object_nuker.delete(helper, event)


def handler(event, context):
    resource_type = event['ResourceType']
    if resource_type not in valid_resource_types:
        raise Exception(f'invalid ResourceType of {resource_type}')
    helper(event, context)
