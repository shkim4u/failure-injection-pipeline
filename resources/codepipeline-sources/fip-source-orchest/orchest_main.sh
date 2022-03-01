aws lambda invoke --function-name fip-func-logger --payload '{"Source": "Orchest", "Message": "Stage started"}' response.json

PARAM_SRC=$(aws ssm get-parameter --name "fip-parameters-source" | jq -r ".Parameter.Value")
PARAM=$(aws ssm get-parameter --name "${PARAM_SRC}")

export FIP_StopEventRuleName=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .StopEventRuleName")

FAIL_STOP_EVT_RULE_ID=$FIP_StopEventRuleName
FAIL_STOP_EVT_RULE_ARN=$(aws events describe-rule --name ${FAIL_STOP_EVT_RULE_ID} | jq -r .Arn)
FAIL_STOP_FUNC_NM=fip-func-stop_inject
FAIL_STOP_FUNC_ARN=$(aws lambda get-function --function-name ${FAIL_STOP_FUNC_NM} | jq -r .Configuration.FunctionArn)

# TODO Add check before running new add-permission
aws lambda add-permission --function-name ${FAIL_STOP_FUNC_NM} --statement-id fip-func-stop_inject-permission --action 'lambda:InvokeFunction' --principal events.amazonaws.com --source-arn $FAIL_STOP_EVT_RULE_ARN

# TODO Add check before running new put-targets
aws events put-targets --rule $FAIL_STOP_EVT_RULE_ID --targets "[{\"Id\": \"1\", \"Arn\": \"${FAIL_STOP_FUNC_ARN}\"}]"

export INJECT_PIPE_EXEC_ID=$(aws codepipeline start-pipeline-execution --name fip-pipeline-inject | jq -r '.pipelineExecutionId')
# TODO Need to check against errors
echo INJECT_PIPE_EXEC_ID = $INJECT_PIPE_EXEC_ID;

aws lambda invoke --function-name fip-func-logger --payload "{\"Source\": \"Orchest\", \"Message\": \"Injection pipeline triggered (Execution ID: ${INJECT_PIPE_EXEC_ID})\"}" response.json

while true; do
    sleep 5
    export INJECT_PIPE_EXEC_STATUS=$(aws codepipeline get-pipeline-execution --pipeline-name fip-pipeline-inject --pipeline-execution-id $INJECT_PIPE_EXEC_ID | jq -r '.pipelineExecution.status')
    # echo $INJECT_PIPE_EXEC_STATUS
    if [ "$INJECT_PIPE_EXEC_STATUS" != "InProgress" ]; then
        break
    fi
done
echo INJECT_PIPE_EXEC_STATUS = $INJECT_PIPE_EXEC_STATUS;

aws lambda invoke --function-name fip-func-logger --payload "{\"Source\": \"Orchest\", \"Message\": \"Injection pipeline ended with status: ${INJECT_PIPE_EXEC_STATUS}\"}" response.json
aws lambda invoke --function-name fip-func-logger --payload '{"Source": "Orchest", "Message": "Stage completed"}' response.json
