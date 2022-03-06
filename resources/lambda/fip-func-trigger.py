import os

import boto3
import json

codepipeline_client = boto3.client('codepipeline')
CODEPIPELINE_NAME_PARAM = 'codepipelineName'


def lambda_handler(event, context):
    print("Triggering FIP Pipeline (Orchestrator)")
    print("Received event: " + json.dumps(event, indent=2))

    codepipeline_name = event[CODEPIPELINE_NAME_PARAM] if (CODEPIPELINE_NAME_PARAM in event) else os.environ[
        "CODEPIPELINE_NAME"]

    codepipeline_response = codepipeline_client.start_pipeline_execution(
        name=codepipeline_name
    )

    return {
        'statusCode': 200,
        'body': json.dumps(codepipeline_response)
    }
