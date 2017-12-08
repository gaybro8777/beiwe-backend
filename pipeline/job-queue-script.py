# TODO create parent .sh file
# TODO put constants in the parent .sh file, pass them here
# TODO make errors block later commands from executing (string together with && or put || exit -1 everywhere
# TODO create an IAM role for the EC2 instance, probably
from time import sleep

import boto3


# Create a new IAM role for the compute environment 
comp_env_role = 'AWSBatchServiceRole'
comp_env_name = 'data-pipeline-env'
queue_name = 'data-pipeline-queue'
job_defn_name = 'data-pipeline-job-defn'

iam_client = boto3.client('iam')
resp = iam_client.create_role(
    RoleName=comp_env_role,
    AssumeRolePolicyDocument='file://assume-batch-role.json',
)
comp_env_role_arn = resp['Role']['Arn']
iam_client.put_role_policy(
    RoleName=comp_env_role,
    PolicyName='aws-batch-service-policy',
    PolicyDocument='file://batch-service-role.json',
)

# Create the batch compute environment
batch_client = boto3.client('batch')
batch_client.create_compute_environment(
    computeEnvironmentName=comp_env_name,
    type='MANAGED',
    computeResources='file://compute-env.json',
    serviceRole=comp_env_role_arn,
)

# Wait for the compute environment to be valid. If it is deemed invalid, exit
print('Waiting for compute environment...')
while True:
    resp = batch_client.describe_compute_environments(
        computeEnvironments=[comp_env_name],
    )
    status = resp['computeEnvironments'][0]['status']
    if status == 'VALID':
        break
    elif status == 'CREATING' or status == 'UPDATING':
        sleep(1)
        continue
    else:
        raise RuntimeError('Compute Environment is Invalid')

# Create the batch job queue
batch_client.create_job_queue(
    jobQueueName=queue_name,
    priority=1,
    computeEnvironmentOrder=[{'order': 0, 'computeEnvironment': comp_env_name}],
)

# Define a job definition
batch_client.register_job_definition(
    jobDefinitionName=job_defn_name,
    type='container',
    containerProperties='file://container-props.json',
)
