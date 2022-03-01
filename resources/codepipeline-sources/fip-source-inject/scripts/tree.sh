source ./fail_action

PARAM_SRC=$(aws ssm get-parameter --name "fip-parameters-source" | jq -r ".Parameter.Value")
PLAN_DIR='./output/fip-scenario-plan'
ACTUAL_DIR='./output/fip-scenario-actual'
#BASE_DIR=$ACTUAL_DIR

# plan - validation & storing parameters
# actual - targetting. timestamp, duration (from file), probing/monitoring, logging, report
# reporting - future feature
# etc - auto discovery 
# SLA - 

#Ftype
#AZ
#RDS
#ec2, Tagging, non-tagging(%)
        #EKS - labelling, non-labelling (cluster),  
        #SSM -

_mkdir(){
    echo sudo mkdir -p ${1} | sh
}

fip_scheduler()
{
    MODE=$1
    MODE="${MODE:-plan}"
    BASE_DIR="${BASE_DIR:-$PLAN_DIR}"

    if ( test $MODE != 'plan' ); then MODE='actual'; BASE_DIR=$ACTUAL_DIR; fi

    #echo "sudo mkdir $BASE_DIR" | sh
    _mkdir $BASE_DIR

    for PARAM in ${PARAM_SRC}
    do
            if ( test $MODE = 'actual' ); then TS=$(date '+_[%Y-%m-%d][%H:%M:%S]'); else TS= ;fi
            
            P_DIR=$(echo ${PARAM}${TS})
            echo "sudo mkdir -p $BASE_DIR/${P_DIR}" | sh

            if [ "${PARAM:0:+4}" = 'wait' ]; then
                    if ( test $MODE = 'actual' ); then v_sleep="$(echo $PARAM | awk -F: {'print $2'})" ; sleep $v_sleep ; fi
                    continue
            fi

            SCN=$(aws ssm get-parameter --name "${PARAM}")
            if [ -z "$SCN" ]; then
                    continue
            fi

            FTYPE=$(echo $SCN | jq -r ".Parameter.Value | fromjson" | grep Fail | sed 's/[ ",:{]//g')
            for F in ${FTYPE}
            do
                    F_Enable=$(echo $SCN | jq -r ".Parameter.Value | fromjson | .${F}.Enable")
                    if [ "$F_Enable" = 'no' ]; then
                            continue
                    fi

                    if ( test $MODE = 'actual' ); then TS=$(date '+_[%Y-%m-%d][%H:%M:%S]'); else TS= ;fi 
                    PP_DIR=$(echo ${F}${TS})
                    echo "sudo mkdir -p ${BASE_DIR}/${P_DIR}/${PP_DIR}" | sh

                    F_DurationSec=$(echo $SCN | jq -r ".Parameter.Value | fromjson | .${F}.DurationSec")
                    if [ -z "$F_DurationSec" -o $F_DurationSec = 'null' ]; then
                            continue
                    fi

                    #eks
                    if [ "$F" = 'FailEks' ]; then
                            FIP_FailEks_TagName=$(echo $SCN | jq -r ".Parameter.Value | fromjson | .FailEks.TagName")
                            FIP_FailEks_TagValue=$(echo $SCN | jq -r ".Parameter.Value | fromjson | .FailEks.TagValue")

                            # failover
                            for row in $(aws ssm describe-parameters --parameter-filters Key=tag:${FIP_FailEks_TagName},Values=${FIP_FailEks_TagValue} | jq -r '.Parameters[] | @base64'); do
                                _jq() {
                                echo ${row} | base64 --decode | jq -r ${1}
                                }
                                name=$(_jq '.Name')
                                value=$(aws ssm get-parameters --names "${name}" | jq -r .Parameters[0].Value)
                                echo -e "$value" > ${name}.yaml

                                if ( test $MODE = 'actual' ); then TS=$(date '+_[%Y-%m-%d][%H:%M:%S]'); else TS= ;fi 
                                T_DIR=$BASE_DIR/${P_DIR}/${PP_DIR}/Failover/${name}${TS}
                                _mkdir $T_DIR

                                #action
                                if ( test $MODE = 'actual' ); then FailEks_action ${T_DIR} failover ${name} ;fi 
                                
                            done

                            # duration
                            if ( test $MODE = 'actual' ); then TS=$(date '+_[%Y-%m-%d][%H:%M:%S]'); else TS= ;fi 
                            T_DIR="${BASE_DIR}/${P_DIR}/${PP_DIR}/Duration_Sec:${F_DurationSec}${TS}"
                            _mkdir $T_DIR

                            #action
                            if ( test $MODE = 'actual' ); then FailEks_action ${T_DIR} duration ${F_DurationSec} ${name} ;fi 

                            # failback
                            for row in $(aws ssm describe-parameters --parameter-filters Key=tag:${FIP_FailEks_TagName},Values=${FIP_FailEks_TagValue} | jq -r '.Parameters[] | @base64'); do
                                _jq() {
                                echo ${row} | base64 --decode | jq -r ${1}
                                }
                                name=$(_jq '.Name')
                                value=$(aws ssm get-parameters --names "${name}" | jq -r .Parameters[0].Value)

                                if ( test $MODE = 'actual' ); then TS=$(date '+_[%Y-%m-%d][%H:%M:%S]'); else TS= ;fi 
                                T_DIR="$BASE_DIR/${P_DIR}/${PP_DIR}/Failback/${name}${TS}"
                                _mkdir $T_DIR

                                #action
                                if ( test $MODE = 'actual' ); then FailEks_action $T_DIR failback ${name} ;fi 
                            done

                    else 
                        #action failover
                        if ( test $MODE = 'actual' ); then TS=$(date '+_[%Y-%m-%d][%H:%M:%S]'); else TS= ;fi 
                        T_DIR="$BASE_DIR/${P_DIR}/${PP_DIR}/Failover${TS}"
                        _mkdir $T_DIR
                        
                        FUNCTION_NAME=${F}_action
                        if ( test $MODE = 'actual' ); then $FUNCTION_NAME $T_DIR failover ;fi 

                        #action duration, for az, rds, may need to modify the start time. 
                        if ( test $MODE = 'actual' ); then TS=$(date '+_[%Y-%m-%d][%H:%M:%S]'); else TS= ;fi 
                        T_DIR="$BASE_DIR/${P_DIR}/${PP_DIR}/Duration_Sec:${F_DurationSec}${TS}"
                        _mkdir $T_DIR #for az & rds, may skip

                        if ( test $MODE = 'actual' ); then $FUNCTION_NAME $T_DIR duration ${F_DurationSec} ;fi 

                        #action failback
                        if ( test $MODE = 'actual' ); then TS=$(date '+_[%Y-%m-%d][%H:%M:%S]'); else TS= ;fi 
                        T_DIR="$BASE_DIR/${P_DIR}/${PP_DIR}/Failback${TS}"
                        _mkdir $T_DIR #for az & rds, may skip
                        #echo "sudo mkdir -p $BASE_DIR/${P_DIR}/${PP_DIR}/Failback/" | sh
                        #action
                        if ( test $MODE = 'actual' ); then $FUNCTION_NAME $T_DIR Failback ;fi 

                    fi
                    # future feature
                    #if [ "$F" = 'FailSSM_Mixed' ]; then
                    #        echo 'FailSSM Mixed'
                    #fi
            done
    done
}

echo start
fip_scheduler $1
