echo "main GP=" $GlobalParameter
aws lambda invoke --function-name fip-func-logger --payload '{"Source": "Orchest_Post", "Message": "Stage started"}' response.json

PARAM_SRC=$(aws ssm get-parameter --name "fip-parameters-source" | jq -r ".Parameter.Value")
PARAM=$(aws ssm get-parameter --name "${PARAM_SRC}")

export FIP_StopEventRuleName=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .StopEventRuleName")
export FIP_FailAz_Enable=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailAz.Enable")
export FIP_FailEks_Enable=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEks.Enable")

FAIL_STOP_FUNC_NM=fip-func-stop_inject

aws lambda remove-permission --function-name ${FAIL_STOP_FUNC_NM} --statement-id fip-func-stop_inject-permission

# TODO Change to dynamic ID detection?
aws events remove-targets --rule $FIP_StopEventRuleName --ids 1

# REMOVED Recovery/cleanups

bash snapshot.sh "Final Snapshot"

aws lambda invoke --function-name fip-func-logger --payload '{"Source": "Orchest_Post", "Message": "Stage completed"}' response.json

aws ssm put-parameter --name "fip-param-logger_filename" --type "String" --value "0" --overwrite