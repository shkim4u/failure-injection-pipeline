. scripts/common.sh

CurrentStage=Inject-SSM

PARAM_SRC=$(aws ssm get-parameter --name "fip-parameters-source" | jq -r ".Parameter.Value")
PARAM=$(aws ssm get-parameter --name "${PARAM_SRC}")

export FIP_CrossAccount_RoleARN=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .CrossAccount_RoleARN")
export FIP_RegionName=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .RegionName")

export FIP_SSM_Cpu_Enable=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailSSM.EnableCPU")
export FIP_SSM_Memory_Enable=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailSSM.EnableMemory")
export FIP_SSM_Network_Enable=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailSSM.EnableNetwork")
export FIP_SSM_Source=$(echo $PARAM | jq -r ".Parameter.Value | fromjson | .FailSSM.ParameterSource")

PARAM_SSM=$(aws ssm get-parameter --name "${FIP_SSM_Source}")

if [ "$FIP_SSM_Cpu_Enable" = 'yes' ]; then

  FIP_SSM_CPU_DuracSec=$(echo $PARAM_SSM | jq -r ".Parameter.Value | fromjson | .CpuStress.DurationSec")
  FIP_SSM_CPU_TagName=$(echo $PARAM_SSM | jq -r ".Parameter.Value | fromjson | .CpuStress.TagName")
  FIP_SSM_CPU_TagValue=$(echo $PARAM_SSM | jq -r ".Parameter.Value | fromjson | .CpuStress.TagValue")

  log ${CurrentStage} "CPU Stress Target tag pair (${FIP_SSM_CPU_TagName}:${FIP_SSM_CPU_TagValue}) is defined, process will target EC2 instances matching defined tag within target VPC for ${FIP_SSM_CPU_DuracSec} sec"

  cross_account_on $FIP_CrossAccount_RoleARN
  echo aws ssm send-command --document-name \"AWSFIS-Run-CPU-Stress\" --document-version \"1\" --targets \'[\{\"Key\":\"tag:${FIP_SSM_CPU_TagName}\"\,\"Values\":[\"${FIP_SSM_CPU_TagValue}\"]}]\' --parameters \'\{\"CPU\":[\"0\"]\,\"InstallDependencies\":[\"True\"]\,\"DurationSeconds\":[\"${FIP_SSM_CPU_DuracSec}\"]}\' --timeout-seconds 600 --max-concurrency \"100%\" --max-errors \"0\" --region ${FIP_RegionName} | tee cpu-cmd.sh
  sh cpu-cmd.sh

else
  log ${CurrentStage} "SSM CPU Stress unslected"
fi

if [ "$FIP_SSM_Memory_Enable" = 'yes' ]; then

  FIP_SSM_Memory_DuracSec=$(echo $PARAM_SSM | jq -r ".Parameter.Value | fromjson | .MemoryStress.DurationSec")
  FIP_SSM_Memory_Percent=$(echo $PARAM_SSM | jq -r ".Parameter.Value | fromjson | .MemoryStress.Percent")
  FIP_SSM_Memory_TagName=$(echo $PARAM_SSM | jq -r ".Parameter.Value | fromjson | .MemoryStress.TagName")
  FIP_SSM_Memory_TagValue=$(echo $PARAM_SSM | jq -r ".Parameter.Value | fromjson | .MemoryStress.TagValue")

  log ${CurrentStage} "Memory Stress Target tag pair (${FIP_SSM_Memory_TagName}:${FIP_SSM_Memory_TagValue}) is defined, process will target EC2 instances matching defined tag within target VPC for ${FIP_SSM_Memory_DuracSec} sec"

  cross_account_on $FIP_CrossAccount_RoleARN
  echo aws ssm send-command --document-name \"AWSFIS-Run-Memory-Stress\" --document-version \"2\" --targets \'[\{\"Key\":\"tag:${FIP_SSM_Memory_TagName}\"\,\"Values\":[\"${FIP_SSM_Memory_TagValue}\"]}]\' --parameters \'\{\"Workers\":[\"1\"],\"InstallDependencies\":[\"True\"]\,\"DurationSeconds\":[\"${FIP_SSM_Memory_DuracSec}\"]\,\"Percent\":[\"${FIP_SSM_Memory_Percent}\"]}\' --timeout-seconds 600 --max-concurrency \"50\" --max-errors \"0\" --region ${FIP_RegionName} | tee memory-cmd.sh
  sh memory-cmd.sh

else
  log ${CurrentStage} "SSM Memory Stress unslected"
fi


if [ "$FIP_SSM_Disk_Enable" = 'yes' ]; then

  FIP_SSM_Disk_DuracSec=$(echo $PARAM_SSM | jq -r ".Parameter.Value | fromjson | .DiskStress.DurationSec")
  FIP_SSM_Disk_Path=$(echo $PARAM_SSM | jq -r ".Parameter.Value | fromjson | .DiskStress.Path")
  
  FIP_SSM_Disk_TagName=$(echo $PARAM_SSM | jq -r ".Parameter.Value | fromjson | .DiskStress.TagName")
  FIP_SSM_Disk_TagValue=$(echo $PARAM_SSM | jq -r ".Parameter.Value | fromjson | .DiskStress.TagValue")

  log ${CurrentStage} "Disk Stress Target tag pair (${FIP_SSM_Disk_TagName}:${FIP_SSM_Disk_TagValue}) is defined, process will target EC2 instances matching defined tag within target VPC for ${FIP_SSM_Disk_DuracSec} sec"

  cross_account_on $FIP_CrossAccount_RoleARN

  #aws ssm send-command --targets '[{"Key":"tag:fip-ssm","Values":["yes"]}]' --document-name "AWS-RunShellScript" --comment "IO Burst Run" --parameters commands="while true; do sudo dd if=/dev/zero of=testfile bs=100M count=5; done" --timeout-seconds 60
  echo aws ssm send-command --targets \'[\{\"Key\":\"tag:${FIP_SSM_Disk_TagName}\"\,\"Values\":[\"${FIP_SSM_Disk_TagValue}\"]}]\' --document-name \"AWS-RunShellScript\" --comment \"IO Burst Run01\" --parameters commands=\"while true\; do sudo dd if=/dev/zero of=$FIP_SSM_Disk_Path/testfile-01 bs=100M count=5\; done\" --timeout-seconds 60 | tee disk-cmd-01.sh
  commandId1=$(sh disk-cmd-01.sh | grep "CommandId" |awk -F: {'print $2'}| sed 's/[ ",]//g')

  echo aws ssm send-command --targets \'[\{\"Key\":\"tag:${FIP_SSM_Disk_TagName}\"\,\"Values\":[\"${FIP_SSM_Disk_TagValue}\"]}]\' --document-name \"AWS-RunShellScript\" --comment \"IO Burst Run02\" --parameters commands=\"while true\; do sudo dd if=/dev/zero of=$FIP_SSM_Disk_Path/testfile-02 bs=100M count=5\; done\" --timeout-seconds 60 | tee disk-cmd-02.sh
  commandId2=$(sh disk-cmd-02.sh | grep "CommandId" |awk -F: {'print $2'}| sed 's/[ ",]//g')
  
  echo aws ssm send-command --targets \'[\{\"Key\":\"tag:${FIP_SSM_Disk_TagName}\"\,\"Values\":[\"${FIP_SSM_Disk_TagValue}\"]}]\' --document-name \"AWS-RunShellScript\" --comment \"IO Burst Run03\" --parameters commands=\"while true\; do sudo dd if=/dev/zero of=$FIP_SSM_Disk_Path/testfile-03 bs=100M count=5\; done\" --timeout-seconds 60 | tee disk-cmd-03.sh
  commandId3=$(sh disk-cmd-03.sh | grep "CommandId" |awk -F: {'print $2'}| sed 's/[ ",]//g')
  
  echo aws ssm send-command --targets \'[\{\"Key\":\"tag:${FIP_SSM_Disk_TagName}\"\,\"Values\":[\"${FIP_SSM_Disk_TagValue}\"]}]\' --document-name \"AWS-RunShellScript\" --comment \"IO Burst Run04\" --parameters commands=\"while true\; do sudo dd if=/dev/zero of=$FIP_SSM_Disk_Path/testfile-04 bs=100M count=5\; done\" --timeout-seconds 60 | tee disk-cmd-04.sh
  commandId4=$(sh disk-cmd-04.sh | grep "CommandId" |awk -F: {'print $2'}| sed 's/[ ",]//g')
  
  sleep $FIP_SSM_Disk_DuracSec

  aws ssm cancel-command --command-id $commandId1
  aws ssm cancel-command --command-id $commandId2
  aws ssm cancel-command --command-id $commandId3
  aws ssm cancel-command --command-id $commandId4

  echo aws ssm send-command --targets \'[\{\"Key\":\"tag:${FIP_SSM_Disk_TagName}\"\,\"Values\":[\"${FIP_SSM_Disk_TagValue}\"]}]\' --document-name \"AWS-RunShellScript\" --comment \"IO Burst Run\" --parameters commands=\"sudo rm -f $FIP_SSM_Disk_Path/testfile\" --timeout-seconds 60 | tee disk-rollback.sh
  sh disk-rollback.sh

else
  log ${CurrentStage} "SSM Disk Stress unslected"
fi

if [ "$FIP_SSM_Network_Enable" = 'yes' ]; then

  FIP_SSM_Network_DuracSec=$(echo $PARAM_SSM | jq -r ".Parameter.Value | fromjson | .NetworkLatency.DurationSec")
  FIP_SSM_Network_DelayMillisec=$(echo $PARAM_SSM | jq -r ".Parameter.Value | fromjson | .NetworkLatency.DelayMillisec")
  FIP_SSM_Network_Interface=$(echo $PARAM_SSM | jq -r ".Parameter.Value | fromjson | .NetworkLatency.Interface")
  FIP_SSM_Network_TagName=$(echo $PARAM_SSM | jq -r ".Parameter.Value | fromjson | .NetworkLatency.TagName")
  FIP_SSM_Network_TagValue=$(echo $PARAM_SSM | jq -r ".Parameter.Value | fromjson | .NetworkLatency.TagValue")

  log ${CurrentStage} "Network Stress Target tag pair (${FIP_SSM_Network_TagName}:${FIP_SSM_Network_TagValue}) is defined, process will target EC2 instances matching defined tag within target VPC for ${FIP_SSM_Network_DuracSec} sec"

  cross_account_on $FIP_CrossAccount_RoleARN

  echo aws ssm send-command --targets \'[\{\"Key\":\"tag:${FIP_SSM_Disk_TagName}\"\,\"Values\":[\"${FIP_SSM_Disk_TagValue}\"]}]\' --document-name \"AWS-RunShellScript\" --comment \"atd daemon installation\" --parameters commands=\"sudo yum -y install at\" --timeout-seconds 60 | tee atd-cmd.sh
  sh atd-cmd.sh

  sleep 5

  echo aws ssm send-command --document-name \"AWSFIS-Run-Network-Latency\" --document-version \"2\" --targets \'[\{\"Key\":\"tag:${FIP_SSM_Network_TagName}\"\,\"Values\":[\"${FIP_SSM_Network_TagValue}\"]}]\' --parameters \'\{\"Interface\":[\"${FIP_SSM_Network_Interface}\"]\,\"DelayMilliseconds\":[\"${FIP_SSM_Network_DelayMillisec}\"]\,\"DurationSeconds\":[\"${FIP_SSM_Network_DuracSec}\"]\,\"InstallDependencies\":[\"True\"]}\' --timeout-seconds 600 --max-concurrency \"50\" --max-errors \"0\" --region ${FIP_RegionName} | tee network-cmd.sh
  sh network-cmd.sh
 
else
  log ${CurrentStage} "SSM Network Delay unslected"
fi