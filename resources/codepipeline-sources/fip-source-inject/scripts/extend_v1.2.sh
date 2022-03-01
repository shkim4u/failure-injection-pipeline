*BS Detach*

Public-Access-Admin:~/environment/script $ aws ec2 detach-volume —volume-id 'vol-0e5ce1351c7d5c196'
{
"AttachTime": "2021-04-29T12:25:55+00:00",
"Device": "/dev/xvdc",
"InstanceId": "i-0e6bf1b0713ee9be3",
"State": "detaching",
"VolumeId": "vol-0e5ce1351c7d5c196"
}
Public-Access-Admin:~/environment/script $ aws ec2 attach-volume --volume-id 'vol-0e5ce1351c7d5c196' --instance-id i-0e6bf1b0713ee9be3 —device /dev/xvdc
{
"AttachTime": "2021-04-29T12:26:27.063000+00:00",
"Device": "/dev/xvdc",
"InstanceId": "i-0e6bf1b0713ee9be3",
"State": "attaching",
"VolumeId": "vol-0e5ce1351c7d5c196"

aws ec2 describe-volumes —volume-id vol-0e5ce1351c7d5c196 | grep -i status

Public-Access-Admin:~/environment $ aws ec2 describe-volumes --volume-id 'vol-0e5ce1351c7d5c196' | grep -i State
"State": "attached",
"State": "in-use",


*RDS Delete*
aws rds delete-db-instance --db-instance-identifier fip-db-02-instance-1 —skip-final-snapshot

*Performance*
date; siege -v -d 0.1 -q --reps=once -c 10 -i -f siege_url.txt ; date



. scripts/common.sh

CurrentStage=Inject-EC2

PARAM_SRC=$(aws ssm get-parameter --name "fip-parameters-source" | jq -r ".Parameter.Value")
PARAM=$(aws ssm get-parameter --name "${PARAM_SRC}")

export FIP_RegionName=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .RegionName")

export FIP_FailEc2_Enable=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEc2.Enable")
export FIP_FailEc2_VpcId=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEc2.VpcId")
export FIP_FailEc2_IntervalSec=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEc2.IntervalSec")
export FIP_FailEc2_Iteration=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEc2.Iteration")
export FIP_FailEc2_Percent=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEc2.Percent")
export FIP_FailEc2_Action=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEc2.Action")
export FIP_FailEc2_TagName=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEc2.TagName")
export FIP_FailEc2_TagValue=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailEc2.TagValue")

export FIP_CrossAccount_RoleARN=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .CrossAccount_RoleARN")

# T_EC2_TAG_NM=$FIP_FailEc2_TagName
# T_EC2_TAG_VL=$FIP_FailEc2_TagValue
FAIL_EC2_PCT=$FIP_FailEc2_Percent

if [ -z "${FIP_FailEc2_TagName}" ]; then
  log ${CurrentStage} "NO target tag pair is defined, process will target ALL EC2 instances within target VPC"
else
  log ${CurrentStage} "Target tag pair (${FIP_FailEc2_TagName}:${FIP_FailEc2_TagValue}) is defined, process will target EC2 instances matching defined tag within target VPC"
  T_TAG_FILTER_PLACEHOLDER=Name=tag:${FIP_FailEc2_TagName},Values=${FIP_FailEc2_TagValue} 
fi

cross_account_on $FIP_CrossAccount_RoleARN
aws ec2 describe-instances --query 'Reservations[*].Instances[*].[InstanceId]' --filters Name=vpc-id,Values=${FIP_FailEc2_VpcId} Name=instance-state-name,Values=running ${T_TAG_FILTER_PLACEHOLDER} --output text > t_ec2_all.txt

# Select instances by tag
# aws ec2 describe-instances --query 'Reservations[*].Instances[*].[InstanceId]' --filters Name=tag:${T_EC2_TAG_NM},Values=${T_EC2_TAG_VL} Name=instance-state-name,Values=running --output text > t_ec2_all.txt

# Select EC2 instances by VPC ID
# aws ec2 describe-instances --query 'Reservations[*].Instances[*].[InstanceId]' --filters "Name=vpc-id,Values=${FAIL_VPC_ID}" --output text > t_ec2_all.txt

# Count total instances found, calculate target count to be stopped
T_EC2_INST_POP_CNT=$(wc -l < t_ec2_all.txt)

T_EC2_INST_SAMPLE_CNT=$(printf %.0f\\n "$(( 10 * FAIL_EC2_PCT/100*T_EC2_INST_POP_CNT ))e-1")
log ${CurrentStage} "Targeted failure percentage = ${FAIL_EC2_PCT}%"
log ${CurrentStage} "Instance(s) targeted = ${T_EC2_INST_POP_CNT} running, ${T_EC2_INST_SAMPLE_CNT} to be selected"

# Randomize and select targeted instances from found instances
T_EC2_INST_SAMPLE_INLINE=
T_EC2_INST_SAMPLE_ARR=$(shuf -n $T_EC2_INST_SAMPLE_CNT t_ec2_all.txt)
for i in ${T_EC2_INST_SAMPLE_ARR}
do
	T_EC2_INST_SAMPLE_INLINE="$i $T_EC2_INST_SAMPLE_INLINE"
done

if [ -z "$T_EC2_INST_SAMPLE_INLINE" ]; then
  log ${CurrentStage} "NO instance is selected"
else
  log ${CurrentStage} "ID(s) of instance(s) selected = ${T_EC2_INST_SAMPLE_INLINE}"

  if [ "$FIP_FailEc2_Action" = 'stop' ]; then
    # Stop target instances
    log ${CurrentStage} "Stopping selected instances..."

    cross_account_on $FIP_CrossAccount_RoleARN
    aws ec2 stop-instances --instance-ids $T_EC2_INST_SAMPLE_INLINE
  elif [ "$FIP_FailEc2_Action" = 'terminate' ]; then
    # Terminate target instances
    log ${CurrentStage} "Terminating selected instances..."

    cross_account_on $FIP_CrossAccount_RoleARN   
    aws ec2 terminate-instances --instance-ids $T_EC2_INST_SAMPLE_INLINE
  elif [ "$FIP_FailEc2_Action" = 'reboot' ]; then
    # Reboot target instances
    log ${CurrentStage} "Rebooting selected instances..."

    cross_account_on $FIP_CrossAccount_RoleARN
    aws ec2 reboot-instances --instance-ids $T_EC2_INST_SAMPLE_INLINE
  else
    log ${CurrentStage} "Invalid EC2 fail action defined in parameters, no action taken on selected instances"
  fi
fi
