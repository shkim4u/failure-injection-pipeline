# 20210617 added
log_lambda() {
  #cross off
  cross_account_off 	
  aws lambda invoke --function-name fip-func-logger --payload "{\"Source\": \"${2:-Post-AZ}\", \"Message\": \"${1}\"}" response.json
}

cross_account_on() {
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

PARAM_SRC=$(aws ssm get-parameter --name "fip-parameters-source" | jq -r ".Parameter.Value")
PARAM=$(aws ssm get-parameter --name "${PARAM_SRC}")

export FIP_CrossAccount_RoleARN=$(echo $PARAM | tr '\r\n' ' ' | jq -r ".Parameter.Value | fromjson | .CrossAccount_RoleARN")

export FIP_RegionName=$(echo $PARAM | tr '\r\n' ' ' |  jq -r ".Parameter.Value | fromjson | .RegionName")
export FIP_FailAz_Enable=$(echo $PARAM | tr '\r\n' ' ' | jq -r ".Parameter.Value | fromjson | .FailAz.Enable")
export FIP_FailAz_AzName=$(echo $PARAM | tr '\r\n' ' ' | jq -r ".Parameter.Value | fromjson | .FailAz.AzName")
export FIP_FailAz_VpcId=$(echo $PARAM | tr '\r\n' ' '| jq -r ".Parameter.Value | fromjson | .FailAz.VpcId")

#NACL Clearance 
cross_account_on $FIP_CrossAccount_RoleARN
AccountID=`echo $FIP_CrossAccount_RoleARN | awk -F: '{print $5}'`

Rollback_Parameters=`aws ssm get-parameters-by-path --path "/fip/$AccountID" --recursive | jq -r '.Parameters[] | .Name' | tr '\r\n' ' ' | wc -w`

if [ ${Rollback_Parameters} -gt 0 ]; then
	echo Rollback Parameters Founded, Performing Clearance. 

	# install required module
	pip install -r fail-az-requirements.txt

    python ./fail_az.py --region $FIP_RegionName --vpc-id $FIP_FailAz_VpcId --az-name $FIP_FailAz_AzName --post-rollback True
fi

	#1 switch role to target account
	#2 parameter store existance check 
	#3 존재시, rollback python 수행 (region parameter, )

#param_name='/fip/' + AccountID + '/save_for_rollback'
#param_name='/fip/' + AccountID + '/chaos_nacl_id'
#param_name='/fip/' + AccountID + '/filtered_original_asg'
#param_name='/fip/' + AccountID + '/eks_single_az_asg'

#for key in $(aws ssm get-parameters-by-path --path "/fip" --recursive | jq -r '.Parameters[] | .Name' | tr '\r\n' ' '); do aws ssm delete-parameter --name ${key}; done

#aws ssm get-parameters-by-path --path "/fip/" --recursive | jq -r '.Parameters[] | .Name' | tr '\r\n' ' ' | grep -E "chaos|fip"

