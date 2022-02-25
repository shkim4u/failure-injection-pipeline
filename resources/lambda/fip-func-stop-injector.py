import json
import boto3

def lambda_handler(event, context):
    # TODO implement
    ssm_client = boto3.client('ssm')
    cp_client = boto3.client('codepipeline')
    gps_resp = cp_client.get_pipeline_state(
        name='fip-pipeline-inject'
    )
    spe_resp = cp_client.stop_pipeline_execution(
        pipelineName=gps_resp['pipelineName'],
        pipelineExecutionId=gps_resp['stageStates'][0]['latestExecution']['pipelineExecutionId'],
        abandon=True
    )

    return {
        'statusCode': 200,
        'body': json.dumps(spe_resp)
    }
