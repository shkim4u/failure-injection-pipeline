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

PARAM_SRC=$(aws ssm get-parameter --name "fip-parameters-source" | jq -r ".Parameter.Value")
PARAM=$(aws ssm get-parameter --name "${PARAM_SRC}")

export FIP_RegionName=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .RegionName")

export FIP_FailEks_DurationSec=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEks.DurationSec")
export FIP_FailEks_Cluster=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEks.Cluster")
export FIP_FailEks_Role=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEks.Role")

# cross account
export FIP_CrossAccount_RoleARN=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .CrossAccount_RoleARN")

# Install eksctl
curl --silent --location "https://github.com/weaveworks/eksctl/releases/latest/download/eksctl_$(uname -s)_amd64.tar.gz" | tar xz -C /tmp
mv /tmp/eksctl /usr/local/bin

# Install kubectl
curl -LO "https://storage.googleapis.com/kubernetes-release/release/$(curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x ./kubectl
mv ./kubectl /usr/local/bin/kubectl

# Default variables that were used on the blog post (you can change them to fit your needs)
# AWS_REGION=us-west-2
# EKS_CLUSTER_NAME=blogpost
AWS_REGION=$FIP_RegionName
EKS_CLUSTER_NAME=$FIP_FailEks_Cluster

## # Add environment variables to bash_profile
## echo "export AWS_REGION=${AWS_REGION}" | tee -a ~/.bash_profile
## echo "export EKS_CLUSTER_NAME=${EKS_CLUSTER_NAME}" | tee -a ~/.bash_profile
## 
## # Export cluster ARN (this variable will be used later)
## export EKS_CLUSTER_ARN=$(aws eks describe-cluster --region $AWS_REGION --name $EKS_CLUSTER_NAME | jq -r '.cluster.arn')
## echo "export EKS_CLUSTER_ARN=${EKS_CLUSTER_ARN}" | tee -a ~/.bash_profile
## 
## # Export node group role name (this variable will be used later)
## export STACK_NAME=$(eksctl get nodegroup --region $AWS_REGION --cluster $EKS_CLUSTER_NAME -o json | jq -r '.[].StackName')
## export EKS_ROLE_NAME=$(aws cloudformation describe-stack-resources --region $AWS_REGION --stack-name $STACK_NAME | jq -r '.StackResources[] | select(.ResourceType=="AWS::IAM::Role") | .PhysicalResourceId')
## echo "export EKS_ROLE_NAME=${EKS_ROLE_NAME}" | tee -a ~/.bash_profile
## 
## # Load environment variables
## source ~/.bash_profile
## 
## # Create kubeconfig file
## #aws eks update-kubeconfig --name $EKS_CLUSTER_NAME --kubeconfig /tmp/kubeconfig
## aws eks --region $AWS_REGION update-kubeconfig --name $EKS_CLUSTER_NAME --kubeconfig /tmp/kubeconfig

# cross account - on
#aws sts assume-role --role-arn "arn:aws:iam::183377045228:role/fip-cross" --role-session-name AWSCLI-Session | tee credential_temp.json
aws sts assume-role --role-arn $FIP_CrossAccount_RoleARN --role-session-name AWSCLI-Session | tee credential_temp.json
export AWS_ACCESS_KEY_ID=$(jq -r .Credentials.AccessKeyId credential_temp.json)
export AWS_SECRET_ACCESS_KEY=$(jq -r .Credentials.SecretAccessKey credential_temp.json)
export AWS_SESSION_TOKEN=$(jq -r .Credentials.SessionToken credential_temp.json)
CODEBUILD_ROLE_ARN=$FIP_CrossAccount_RoleARN

#CODEBUILD_ROLE_ARN=$FIP_FailEks_Role
CREDENTIALS=$(aws sts assume-role --role-arn $CODEBUILD_ROLE_ARN --role-session-name codebuild-kubectl --duration-seconds 900)
AWS_ACCESS_KEY_ID="$(echo ${CREDENTIALS} | jq -r '.Credentials.AccessKeyId')"
AWS_SECRET_ACCESS_KEY="$(echo ${CREDENTIALS} | jq -r '.Credentials.SecretAccessKey')"
AWS_SESSION_TOKEN="$(echo ${CREDENTIALS} | jq -r '.Credentials.SessionToken')"
AWS_EXPIRATION=$(echo ${CREDENTIALS} | jq -r '.Credentials.Expiration')

aws eks --region $AWS_REGION update-kubeconfig --name $EKS_CLUSTER_NAME --kubeconfig /tmp/kubeconfig

cross_account_off

# cat /tmp/kubeconfig
# kubectl --kubeconfig /tmp/kubeconfig apply -f $FAIL_EKS_CM_YML
for row in $(aws ssm describe-parameters --parameter-filters Key=tag:fip,Values=yes | jq -r '.Parameters[] | @base64'); do
    _jq() {
     echo ${row} | base64 --decode | jq -r ${1}
    }

	name=$(_jq '.Name')
	value=$(aws ssm get-parameters --names "${name}" | jq -r .Parameters[0].Value)
	echo -e "$value" > ${name}.yaml

    cross_account_on $FIP_CrossAccount_RoleARN
    kubectl --kubeconfig /tmp/kubeconfig apply -f ${name}.yaml
    cross_account_off
done

sleep $FIP_FailEks_DurationSec

# TODO better apply -- don't depend on param
cross_account_off

# kubectl --kubeconfig /tmp/kubeconfig delete -f $FAIL_EKS_CM_YML
for row in $(aws ssm describe-parameters --parameter-filters Key=tag:fip,Values=yes | jq -r '.Parameters[] | @base64'); do
    _jq() {
     echo ${row} | base64 --decode | jq -r ${1}
    }

	name=$(_jq '.Name')
	value=$(aws ssm get-parameters --names "${name}" | jq -r .Parameters[0].Value)
	echo -e "$value" > ${name}.yaml
    
    cross_account_on $FIP_CrossAccount_RoleARN
    kubectl --kubeconfig /tmp/kubeconfig delete -f ${name}.yaml
    cross_account_off
done