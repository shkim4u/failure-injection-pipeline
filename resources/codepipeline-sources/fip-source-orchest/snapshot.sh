# last modified : 20210424-01
# +) VpcID 

            echo "GP1=" $GlobalParameter
            echo "GP2=" $GlobalParameter2

log_lambda() {
  cross_account_off
  aws lambda invoke --function-name fip-func-logger --payload "{\"Source\": \"${2:-Inject-EC2}\", \"Message\": \"${1}\"}" response.json
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

cross_account_off

PARAM_SRC=$(aws ssm get-parameter --name "fip-parameters-source" | jq -r ".Parameter.Value")
PARAM=$(aws ssm get-parameter --name "${PARAM_SRC}")
FIP_CrossAccount_RoleARN=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .CrossAccount_RoleARN")

cross_account_on $FIP_CrossAccount_RoleARN

log_inst_ec2="$(aws ec2 describe-instances --query 'Reservations[*].Instances[*].{InstanceId:InstanceId,AvailabilityZone:Placement.AvailabilityZone,VpcId:VpcId,State:State.Name}' --output table)"
# use printf to escape newlines and tabs
log_inst_ec2=$(printf '%q' "$log_inst_ec2")
# remove POSIX $'' syntax
if [[ $t2 == $\'* ]] && [[ $t2 == *\' ]] && [[ ${#t2} -gt 2 ]]; then
  log_inst_ec2=${log_inst_ec2:2:-1}
fi

log_inst_rds_2="$(aws rds describe-db-clusters --query 'DBClusters[*].{ClusterId:DBClusterIdentifier, InstanceId:DBClusterMembers[*].DBInstanceIdentifier, IsClusterWriter:DBClusterMembers[*].IsClusterWriter}' --output table)"
# use printf to escape newlines and tabs
log_inst_rds_2=$(printf '%q' "$log_inst_rds_2")
# remove POSIX $'' syntax
if [[ $t2 == $\'* ]] && [[ $t2 == *\' ]] && [[ ${#t2} -gt 2 ]]; then
  log_inst_rds_2=${log_inst_rds_2:2:-1}
fi

log_inst_rds_1="$(aws rds describe-db-instances --query 'DBInstances[*].{InstanceId:DBInstanceIdentifier, ClusterId:DBClusterIdentifier, Status:DBInstanceStatus, AvailabilityZone:AvailabilityZone}' --output table)"
# use printf to escape newlines and tabs
log_inst_rds_1=$(printf '%q' "$log_inst_rds_1")
# remove POSIX $'' syntax
if [[ $t2 == $\'* ]] && [[ $t2 == *\' ]] && [[ ${#t2} -gt 2 ]]; then
  log_inst_rds_1=${log_inst_rds_1:2:-1}
fi

log_inst_elasticache="$(aws elasticache describe-replication-groups --query 'ReplicationGroups[*].{Cluster:ReplicationGroupId, Nodes:NodeGroups[*].NodeGroupMembers[*].CacheClusterId, Roles:NodeGroups[*].NodeGroupMembers[*].CurrentRole, AvailabilityZones:NodeGroups[*].NodeGroupMembers[*].PreferredAvailabilityZone}'  --output table)"
# use printf to escape newlines and tabs
log_inst_elasticache=$(printf '%q' "$log_inst_elasticache")
# remove POSIX $'' syntax
if [[ $t2 == $\'* ]] && [[ $t2 == *\' ]] && [[ ${#t2} -gt 2 ]]; then
  log_inst_elasticache=${log_inst_elasticache:2:-1}
fi


cross_account_on $FIP_CrossAccount_RoleARN
CODEBUILD_ROLE_ARN=$FIP_CrossAccount_RoleARN

#CODEBUILD_ROLE_ARN=$FIP_FailEks_Role
CREDENTIALS=$(aws sts assume-role --role-arn $CODEBUILD_ROLE_ARN --role-session-name codebuild-kubectl --duration-seconds 900)
AWS_ACCESS_KEY_ID="$(echo ${CREDENTIALS} | jq -r '.Credentials.AccessKeyId')"
AWS_SECRET_ACCESS_KEY="$(echo ${CREDENTIALS} | jq -r '.Credentials.SecretAccessKey')"
AWS_SESSION_TOKEN="$(echo ${CREDENTIALS} | jq -r '.Credentials.SessionToken')"
AWS_EXPIRATION=$(echo ${CREDENTIALS} | jq -r '.Credentials.Expiration')
EKS_CLUSTER_NAME=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEks.Cluster")

aws eks --region $FIP_RegionName update-kubeconfig --name $EKS_CLUSTER_NAME --kubeconfig /tmp/kubeconfig

log_inst_eks="$(kubectl get nodes)"
echo | tee -a $log_inst_eks

for row in $(kubectl get ns | awk '{print $1}' | sed 1d); do
    echo ">> namespace : ${row} "  | tee -a $log_inst_eks
    kubectl get pod -n ${row} | tee -a $log_inst_eks
    echo | tee -a $log_inst_eks
done

log_inst_eks=$(printf '%q' "$log_inst_eks")
# remove POSIX $'' syntax
if [[ $t2 == $\'* ]] && [[ $t2 == *\' ]] && [[ ${#t2} -gt 2 ]]; then
  log_inst_eks=${log_inst_eks:2:-1}
fi

log_msg="Taking snapshot listing of instances ${1}\n\nEC2 instances: \n${log_inst_ec2}\n\nRDS Clusters: \n${log_inst_rds_2}\n\nRDS Instances: \n${log_inst_rds_1}\n\nElasticache Nodes: \n${log_inst_elasticache}\n"

#cross account - off
cross_account_off
aws lambda invoke --function-name fip-func-logger --payload "{\"Source\": \"Inject\", \"Message\": \"${log_msg}\"}" response.json

echo -e "$log_msg"
