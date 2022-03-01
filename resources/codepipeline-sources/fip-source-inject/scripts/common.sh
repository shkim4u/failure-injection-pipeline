# last modified : 20210425-01

cross_account_off() {
	unset AWS_ACCESS_KEY_ID
	unset AWS_SECRET_ACCESS_KEY
	unset AWS_SESSION_TOKEN
}

cross_account_on() {
    if [ -z "$1" ]; then
        cross_account_off

        PARAM_SRC=$(aws ssm get-parameter --name "fip-parameters-source" | jq -r ".Parameter.Value")
        PARAM=$(aws ssm get-parameter --name "${PARAM_SRC}")
        export FIP_CrossAccount_RoleARN=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .CrossAccount_RoleARN")
    else
        export FIP_CrossAccount_RoleARN=$1
    fi

	aws sts assume-role --role-arn $FIP_CrossAccount_RoleARN --role-session-name AWSCLI-Session | tee credential_temp.json
	export AWS_ACCESS_KEY_ID=$(jq -r .Credentials.AccessKeyId credential_temp.json)
	export AWS_SECRET_ACCESS_KEY=$(jq -r .Credentials.SecretAccessKey credential_temp.json)
	export AWS_SESSION_TOKEN=$(jq -r .Credentials.SessionToken credential_temp.json)
}

log() {
  cross_account_off
  echo [${1}] ${2}
  aws lambda invoke --function-name fip-func-logger --payload "{\"Source\": \"${1}\", \"Message\": \"${2}\"}" response.json > /dev/null
}

get_param() {
  flag_all=false

}