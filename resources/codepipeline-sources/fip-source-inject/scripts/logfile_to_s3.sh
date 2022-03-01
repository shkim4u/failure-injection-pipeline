. scripts/common.sh

cross_account_off
S3_BUCKETNAME=$(aws ssm get-parameter --name "fip-param-bucket_name" | jq -r ".Parameter.Value")
S3_LOGNAME=$(aws ssm get-parameter --name "fip-param-logger_filename" | jq -r ".Parameter.Value")
FN=${S3_LOGNAME}_${1}

mv ${1} ${FN}
aws s3 cp $FN s3://${S3_BUCKETNAME}/logs/${FN}


