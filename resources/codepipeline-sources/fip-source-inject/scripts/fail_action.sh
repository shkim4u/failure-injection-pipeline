#include
#common/logging

# plan - validation & storing parameters
# actual - timestamp, duration (from file), probing/monitoring, logging, report
# reporting - future feature

FailSSM_CpuStress_action()
{
    T_DIR=$1
    action=$2
    echo "---> ssm cpu $1 $2"
    case $action in
        failover)
            echo ssm cpu $T_DIR $action
            ;;
        duration)
            echo ssm cpu $T_DIR $action
            ;;
        failback)
            echo ssm cpu $T_DIR $action
            ;;
        *)
            ;;
    esac
}

FailSSM_MemoryStress_action()
{
    T_DIR=$1
    action=$2
    echo "---> ssm memory $1 $2"
    case $action in
        failover)
            echo ssm memory $T_DIR $action
            ;;
        duration)
            echo ssm memory $T_DIR $action
            ;;
        failback)
            echo ssm cpu $T_DIR $action
            ;;
        *)
            ;;
    esac
}

FailSSM_MemoryStress_action()
{
    T_DIR=$1
    action=$2
    echo "---> ssm memory $1 $2"
    case $action in
        failover)
            echo ssm memory $T_DIR $action
            ;;
        duration)
            echo ssm memory $T_DIR $action
            ;;
        failback)
            echo ssm memory $T_DIR $action
            ;;
        *)
            ;;
    esac
}

FailSSM_NetworkLatency_action()
{
    T_DIR=$1
    action=$2
    echo "---> ssm network $1 $2"
    case $action in
        failover)
            echo ssm network $T_DIR $action
            ;;
        duration)
            echo ssm network $T_DIR $action
            ;;
        failback)
            echo ssm network $T_DIR $action
            ;;
        *)
            ;;
    esac
}

FailSSM_DiskStress_action()
{
    T_DIR=$1
    action=$2
    echo "---> ssm disk $1 $2"
    case $action in
        failover)
            echo ssm disk $T_DIR $action
            ;;
        duration)
            echo ssm disk $T_DIR $action
            ;;
        failback)
            echo ssm disk $T_DIR $action
            ;;
        *)
            ;;
    esac
}

FailEc2_action()
{
    T_DIR=$1
    action=$2
    echo "ec2 $1 $2"
    case $action in
        failover)
            echo ec2 $T_DIR $action
            ;;
        duration)
            echo ec2 $T_DIR $action
            ;;
        failback)
            echo ec2 $T_DIR $action
            ;;
        *)
            ;;
    esac
}

FailEks_action()
{
    T_DIR=$1
    action=$2
    echo "---> eks $1 $2"
    case $action in
        failover)
            echo eks $T_DIR $action
            ;;
        duration)
            echo eks $T_DIR $action
            ;;
        failback)
            echo eks $T_DIR $action
            ;;
        *)
            ;;
    esac
}

FailRds_action()
{
    T_DIR=$1
    action=$2
    echo "---> rds $1 $2"
    case $action in
        failover)
            echo rds $T_DIR $action
            ;;
        duration)
            echo rds $T_DIR $action
            ;;
        failback)
            echo rds $T_DIR $action
            ;;
        *)
            ;;
    esac
}

FailAz_action()
{
    T_DIR=$1
    action=$2
    echo "---> az $1 $2"
    case $action in
        failover)
            echo az $T_DIR $action
            ;;
        duration)
            echo az $T_DIR $action
            ;;
        failback)
            echo az $T_DIR $action
            ;;
        *)
            ;;
    esac
}

FailSSM_action()
{
    T_DIR=$1
    action=$2
    echo "ssm $1 $2"
}

FailEBS_action()
{
    T_DIR=$1
    action=$2
    echo "ebs $1 $2"
}
