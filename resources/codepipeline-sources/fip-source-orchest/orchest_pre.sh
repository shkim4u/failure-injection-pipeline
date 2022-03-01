LOGNAME=fip-log_$(date +%s%N).log
aws ssm put-parameter --name "fip-param-logger_filename" --type "String" --value "$LOGNAME" --overwrite

log_lambda() {
  cross_account_off
  aws lambda invoke --function-name fip-func-logger --payload "{\"Source\": \"${2:-Orchest_Pre}\", \"Message\": \"${1}\"}" response.json
}

cross_account_on() {
	# later, rolearn comes in as parameter 
	#PARAM_SRC=$(aws ssm get-parameter --name "fip-parameters-source" | jq -r ".Parameter.Value")
	#PARAM=$(aws ssm get-parameter --name "${PARAM_SRC}")
	#FIP_CrossAccount_RoleARN=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .CrossAccount_RoleARN")

	aws sts assume-role --role-arn $1 --role-session-name AWSCLI-Session | tee credential_temp.json
	export AWS_ACCESS_KEY_ID=$(jq -r .Credentials.AccessKeyId credential_temp.json)
	export AWS_SECRET_ACCESS_KEY=$(jq -r .Credentials.SecretAccessKey credential_temp.json)
	export AWS_SESSION_TOKEN=$(jq -r .Credentials.SessionToken credential_temp.json)
}

cross_account_off() {
	unset AWS_ACCESS_KEY_ID
	unset AWS_SECRET_ACCESS_KEY
	unset AWS_SESSION_TOKEN
}

cross_account_off
aws lambda invoke --function-name fip-func-logger --payload '{"Source": "Orchest_Pre", "Message": "Stage started"}' response.json

PARAM_SRC=$(aws ssm get-parameter --name "fip-parameters-source" | jq -r ".Parameter.Value")
PARAM=$(aws ssm get-parameter --name "${PARAM_SRC}")

# test param src
if [ -z "$PARAM" ]; then
  log_lambda "CRITICAL: Configuration parameters NOT found, fip-parameters-source might not be pointing to a valid parameter store"
  exit 1
fi

FIP_RegionName=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .RegionName")

FIP_FailAz_Enable=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailAz.Enable")
FIP_FailAz_AzName=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailAz.AzName")
FIP_FailAz_VpcId=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailAz.VpcId")
FIP_FailAz_DurationSec=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailAz.DurationSec")
FIP_FailAz_TagName=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailAz.TagName")
FIP_FailAz_TagValue=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailAz.TagValue")

FIP_FailEc2_Enable=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEc2.Enable")
FIP_FailEc2_IntervalSec=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEc2.IntervalSec")
FIP_FailEc2_Iteration=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEc2.Iteration")
FIP_FailEc2_Percent=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEc2.Percent")
FIP_FailEc2_Action=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEc2.Action")
FIP_FailEc2_TagName=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEc2.TagName")
FIP_FailEc2_TagValue=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEc2.TagValue")

FIP_FailRds_Enable=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailRds.Enable")
FIP_FailRds_IntervalSec=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailRds.IntervalSec")
FIP_FailRds_Iteration=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailRds.Iteration")
FIP_FailRds_TagName=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailRds.TagName")
FIP_FailRds_TagValue=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailRds.TagValue")

FIP_FailEks_Enable=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEks.Enable")
FIP_FailEks_DurationSec=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEks.DurationSec")
FIP_FailEks_Cluster=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEks.Cluster")
FIP_FailEks_Role=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEks.Role")
FIP_FailEks_Config=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEks.Config")

# cross account
FIP_CrossAccount_RoleARN=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .CrossAccount_RoleARN")

aws lambda invoke --function-name fip-func-logger --payload '{"Source": "Orchest_Pre", "Message": "Validating parameters..."}' response.json

# cross account - on
cross_account_on $FIP_CrossAccount_RoleARN

# check Region
ret=$(aws ec2 describe-regions --filters Name=region-name,Values=$FIP_RegionName)
if ! [ $(echo $ret | jq '.Regions | length') -eq 1 ]; then
    cross_account_off
    aws lambda invoke --function-name fip-func-logger --payload '{"Source": "Orchest_Pre", "Message": "CRITICAL ... Region Name is not valid or inaccessible by your account"}' response.json
	exit 1
fi

# REMOVED FailAz checks

cross_account_off

aws lambda invoke --function-name fip-func-logger --payload '{"Source": "Orchest_Pre", "Message": "Parameters validated"}' response.json
aws lambda invoke --function-name fip-func-logger --payload '{"Source": "Orchest_Pre", "Message": "Stage completed"}' response.json
