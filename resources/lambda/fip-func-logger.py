import json
import time
import boto3
import botocore
from datetime import datetime
# from pytz import timezone
import dateutil.tz

def lambda_handler(event, context):
    print('Start')
    #test = 'fi-test-multiaz-log_' +str(time.time_ns()) + '.log'

    ssm_client = boto3.client('ssm')
    s3_client = boto3.client('s3')
    s3 = boto3.resource('s3')

    gp_resp_logger_fn = ssm_client.get_parameter(
        Name='fip-param-logger_filename'
    )
    gp_resp_fip_bucket = ssm_client.get_parameter(
        Name='fip-param-bucket_name'
    )
    log_file = '/tmp/' + gp_resp_logger_fn['Parameter']['Value']
    s3_bucket = gp_resp_fip_bucket['Parameter']['Value']
    s3_obj_key = 'logs/' + gp_resp_logger_fn['Parameter']['Value']

    try:
        s3.Object(s3_bucket, s3_obj_key).load()
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == "404":
            # The object does not exist.
            test = 'file not exists'
            try:
                open(log_file, 'w').close()
            except OSError as err:
                print('Failed creating the file: {0}'.format(err))
        # else:
        # Something else has gone wrong.
    else:
        # The object does exist.
        test = 'file exists'
        # response = s3_client.get_object(
        # Bucket=s3_bucket,
        # Key=s3_obj_key,
        # )
        s3_client.download_file(s3_bucket, s3_obj_key, log_file)

    dt = datetime.now()
    log_msg = '[' + dt.strftime('%Y-%m-%dT%H:%M:%S.%f%z') + '] (' + event['Source'] + ') ' + event['Message']
    wr = open(log_file, 'a')
    wr.write(log_msg + '\n')
    wr.close()

    # s3.Object(s3_bucket, s3_obj_key).put(Body=open(log_file, 'rb'))
    with open(log_file, 'rb') as rd:
        response = s3_client.put_object(
            Bucket=s3_bucket,
            Key=s3_obj_key,
            Body=rd
        )

    return {
        'statusCode': 200,
        'body': json.dumps(test)
    }
