"""
Script to simulate the lose of an AZ in an AWS Region
It is using Network ACL with deny all traffic
The script will rollback to the original state
And delete all created resources
Last Updated : 09242021, v1.4
"""
import argparse
import logging
import boto3
import botocore
import time
import json
import re
import os

from pythonjsonlogger import jsonlogger
from datetime import date, datetime

#Global Variable 
original_asg=[]
eks_single_az_asg={}
filtered_original_asg={}

def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError ("Type %s not serializable" % type(obj))

def stringToList(string,delimiter):
    listRes = list(string.split(delimiter))
    return listRes

def setup_logging(log_level):
    logger = logging.getLogger(__name__)
    logger.setLevel(log_level)
    json_handler = logging.StreamHandler()
    file_handler = logging.FileHandler('fail-az.log')

    #formatter = jsonlogger.JsonFormatter(
    #    fmt='%(asctime)s %(levelname)s %(name)s %(message)s'
    #)

    formatter = jsonlogger.JsonFormatter(
        fmt='%(asctime)s %(levelname)s %(message)s'
    )

    json_handler.setFormatter(formatter)
    logger.addHandler(json_handler)

    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

def get_arguments():
    parser = argparse.ArgumentParser(
        description='Simulate AZ failure: associate subnet(s) with a Chaos NACL that deny ALL Ingress and Egress traffic - blackhole',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--caller-region', type=str, required=True,
                        help='The AWS region of choice (caller)')
    parser.add_argument('--region', type=str, required=True,
                        help='The AWS region of choice')
    parser.add_argument('--vpc-id', type=str, required=True,
                        help='The VPC ID of choice')
    parser.add_argument('--az-name', type=str, required=True,
                        help='The name of the availability zone to blackout')
    parser.add_argument('--duration', type=int, default=60,
                        help='The duration, in seconds, of the blackout')
    parser.add_argument('--tag-name', type=str, default='fip',
                        help='The tag name of instances (RDS, ElastiCache) to be affected during blackout')
    parser.add_argument('--tag-value', type=str, default='yes',
                        help='The tag value of instances (RDS, ElastiCache) to be affected during blackout')
    parser.add_argument('--limit-asg', default=False, action='store_true',
                        help='Remove "failed" AZ from Auto Scaling Group (ASG)')
    parser.add_argument('--failover-rds', default=False, action='store_true',
                        help='Failover RDS if master in the blackout subnet')
    parser.add_argument('--failover-elasticache', default=False, action='store_true',
                        help='Failover Elasticache if primary in the blackout subnet')
    parser.add_argument('--log-level', type=str, default='INFO',
                        help='Python log level. INFO, DEBUG, etc.')
    parser.add_argument('--post-rollback', default=False,
                        help='Post Rollback')
    parser.add_argument('--recover-only', default=False, action='store_true',
                        help='Skip failure actions and execute recovery procedures only')
    parser.add_argument('--debug-no-harm', default=False, action='store_true',
                        help='(Debug Mode) Run read/describe commands only, skip commands that may alter target(s)')
    parser.add_argument('--do-nothing', default=False, action='store_true',
                        help='(Debug Mode) Do nothing')
    parser.add_argument('--norm', default=False, action='store_true',
                        help='Run switched failures only')
    parser.add_argument('--failover-eks', default=False, action='store_true',
                        help='Failover EKS')
    return parser.parse_args()

## test purpose 
def get_arguments_test():
    parser = argparse.ArgumentParser(
        description='Simulate AZ failure: associate subnet(s) with a Chaos NACL that deny ALL Ingress and Egress traffic - blackhole',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--region', type=str, default='ap-northeast-1',
                        help='The AWS region of choice')
    parser.add_argument('--vpc-id', type=str, default='vpc-00ada0692cfa29eed',
                        help='The VPC ID of choice')
    parser.add_argument('--az-name', type=str, default='ap-northeast-1c',
                        help='The name of the availability zone to blackout')
    parser.add_argument('--duration', type=int, default=10,
                        help='The duration, in seconds, of the blackout')
    parser.add_argument('--tag-name', type=str, default='fip',
                        help='The tag name of instances (RDS, ElastiCache) to be affected during blackout')
    parser.add_argument('--tag-value', type=str, default='yes',
                        help='The tag value of instances (RDS, ElastiCache) to be affected during blackout')
    parser.add_argument('--limit-asg', default=False, action='store_true',
                        help='Remove "failed" AZ from Auto Scaling Group (ASG)')
    parser.add_argument('--failover-rds', default=False, action='store_true',
                        help='Failover RDS if master in the blackout subnet')
    parser.add_argument('--failover-elasticache', default=False, action='store_true',
                        help='Failover Elasticache if primary in the blackout subnet')
    parser.add_argument('--log-level', type=str, default='INFO',
                        help='Python log level. INFO, DEBUG, etc.')
    parser.add_argument('--post-rollback', default=False,
                        help='Post Rollback')
    return parser.parse_args()

def create_chaos_nacl(ec2_client, vpc_id):
    logger = logging.getLogger(__name__)
    logger.info('Create a Chaos Network ACL')
    # Create a Chaos Network ACL
    chaos_nacl = ec2_client.create_network_acl(
        VpcId=vpc_id,
    )
    associations = chaos_nacl['NetworkAcl']
    chaos_nacl_id = associations['NetworkAclId']

    # Tagging the network ACL with chaos for obvious reasons
    ec2_client.create_tags(
        Resources=[
            chaos_nacl_id,
        ],
        Tags=[
            {
                'Key': 'Name',
                'Value': 'chaos-kong'
            },
        ]
    )
    # Create Egress and Ingress rule blocking all inbound and outbound traffic
    # Egress
    ec2_client.create_network_acl_entry(
        CidrBlock='0.0.0.0/0',
        Egress=True,
        PortRange={'From': 0, 'To': 65535, },
        NetworkAclId=chaos_nacl_id,
        Protocol='-1',
        RuleAction='deny',
        RuleNumber=100,
    )

    # Ingress
    ec2_client.create_network_acl_entry(
        CidrBlock='0.0.0.0/0',
        Egress=False,
        PortRange={'From': 0, 'To': 65535, },
        NetworkAclId=chaos_nacl_id,
        Protocol='-1',
        RuleAction='deny',
        RuleNumber=101,
    )
    return chaos_nacl_id

def get_subnets_to_chaos(ec2_client, vpc_id, az_name):
    logger = logging.getLogger(__name__)
    logger.info('Getting the list of subnets to fail')
    # Describe the subnet so you can see if it is in the AZ
    subnets_response = ec2_client.describe_subnets(
        Filters=[
            {
                'Name': 'availability-zone',
                'Values': [az_name]
            },
            {
                'Name': 'vpc-id',
                'Values': [vpc_id]
            }
        ]
    )
    subnets_to_chaos = [
        subnet['SubnetId'] for subnet in subnets_response['Subnets']
    ]
    return subnets_to_chaos

def get_nacls_to_chaos(ec2_client, subnets_to_chaos):
    logger = logging.getLogger(__name__)
    logger.info('Getting the list of NACLs to blackhole')

    # Find network acl associations mapped to the subnets_to_chaos
    acls_response = ec2_client.describe_network_acls(
        Filters=[
            {
                    'Name': 'association.subnet-id',
                    'Values': subnets_to_chaos
            }
        ]
    )
    network_acls = acls_response['NetworkAcls']

    # SAVE THEM so it can revert
    nacl_ids = []

    for nacl in network_acls:
        for nacl_ass in nacl['Associations']:
            if nacl_ass['SubnetId'] in subnets_to_chaos:
                nacl_ass_id, nacl_id = nacl_ass[
                    'NetworkAclAssociationId'], nacl_ass['NetworkAclId']
                nacl_ids.append((nacl_ass_id, nacl_id))

    return nacl_ids

def limit_auto_scaling(autoscaling_client, subnets_to_chaos):
    logger = logging.getLogger(__name__)
    logger.info('Limit autoscaling to the remaining subnets')

    global filtered_original_asg

    # Get info on all the AutoScalingGroups (ASGs) in the region
    response = autoscaling_client.describe_auto_scaling_groups()
    asgs = response['AutoScalingGroups']

    # Find the ASG we need to modify
    correct_asg = False
    for asg in asgs:
        asg_name = asg['AutoScalingGroupName']
        asg_subnets = asg['VPCZoneIdentifier'].split(',')

        #debug #kai
        logger.info('Limit autoscaling to the remaining subnets : [%s], [%s]', asg_name, asg_subnets)

        subnets_to_keep = list(set(asg_subnets)-set(subnets_to_chaos))

        # if the any of the subnets_to_chaos are in this ASG
        # then it is the ASG we will modify
        correct_asg = len(subnets_to_keep) < len(asg_subnets)
        #if correct_asg: break

    # If we find an impacted ASG, we remove the subnets for the "failed AZ".  
    # In a real AZ failure ASG would not put new instances into this AZ
        if correct_asg:
            try:
                vpczoneidentifier = ",".join(subnets_to_keep)
                response = autoscaling_client.update_auto_scaling_group(AutoScalingGroupName=asg_name, VPCZoneIdentifier=vpczoneidentifier)
                original_asg.append(asg)

                filtered_original_asg[asg_name]=[asg_subnets]

                #debug
                logger.info("append asg : [%s]", asg_name)
                continue
                #return asg
            except:
                logger.error("Unable to update ASG : %s", asg_name)
                continue
                #return None
        else:
            # If correct_asg is false, means ASG is not impacted, and is not an error
            #logger.error("Cannot find impacted ASG : %s", asg_name)
            continue
            #return None

def apply_chaos_config(ec2_client, nacl_ids, chaos_nacl_id):
    logger = logging.getLogger(__name__)
    logger.info('Saving original config & applying new chaos config')
    save_for_rollback = []
    # Modify the association of the subnets_to_chaos with the Chaos NetworkACL
    for nacl_ass_id, nacl_id in nacl_ids:
        logger.info('::::: Chaos-ing: nacl_ass_id: %s nacl_id: %s', nacl_ass_id, nacl_id)
        response = ec2_client.replace_network_acl_association(
            AssociationId=nacl_ass_id,
            NetworkAclId=chaos_nacl_id
        )
        logger.info('::::: Chaos-ed: NewAssociationId: %s', response['NewAssociationId'])
        save_for_rollback.append((response['NewAssociationId'], nacl_id))
    return save_for_rollback

def confirm_choice():
    logger = logging.getLogger(__name__)
    confirm = input(
        "!!WARNING!! [c]Confirm or [a]Abort Failover: ")
    if confirm != 'c' and confirm != 'a':
        print("\n Invalid Option. Please Enter a Valid Option.")
        return confirm_choice()
    logger.info('Selection: %s', confirm)
    return confirm

def force_failover_rds(rds_client, vpc_id, az_name, tag_name, tag_value):
    logger = logging.getLogger(__name__)
    # Find RDS master instances within the AZ

    rds_dbs = rds_client.describe_db_instances()
    for rds_db in rds_dbs['DBInstances']:
        #  Skip Aurora RDS
        if rds_db['Engine'].find("aurora") >= 0:
            logger.info('DEBUG "aurora" exists in DB instance\'s Engine attribute, skipping instance...')
            continue
        else:
            logger.info('DEBUG Not "aurora" instance found')
            logger.info('DEBUG > %s %s, %s, %s', rds_db['DBInstanceArn'], rds_db['DBSubnetGroup']['VpcId'], rds_db['AvailabilityZone'], rds_db['MultiAZ'])
                
        # if rds_db['DBSubnetGroup']['VpcId'] == vpc_id:
        
        if rds_db['AvailabilityZone'] == az_name and rds_db['MultiAZ'] == True:
            logger.info(
                'Database found in VPC: %s and AZ: %s', rds_db[
                    'DBInstanceIdentifier'], rds_db['AvailabilityZone']
            )

            # Check if cluster has pre-defined tagging
            rds_instance_tag_correct=False
            rds_instance_tags = rds_client.list_tags_for_resource(
                ResourceName=rds_db['DBInstanceArn']
            )
            for rds_instance_tag in rds_instance_tags['TagList']:
                logger.info('DEBUG TAGS FOUND> %s %s', rds_instance_tag['Key'], rds_instance_tag['Value'])
                # if rds_cluster_tag['Key'] == 'rdsfail' and rds_cluster_tag['Value'] == 'yes':
                if rds_instance_tag['Key'] == tag_name and rds_instance_tag['Value'] == tag_value:
                    rds_instance_tag_correct=True
            logger.info('DEBUG tag check flag %s', rds_instance_tag_correct)
            if rds_instance_tag_correct == True:
                logger.info('DEBUG Instance is targeted')
            else:
                logger.info('DEBUG Instance %s is NOT targeted by tag', rds_db['DBInstanceIdentifier'])
                #continue #0817-2021
            
            # if RDS master is multi-az and in blackholed AZ
            # force reboot with failover
            confirm ='c'
            if confirm == 'c':
                logger.info('before Force reboot/failover %s', rds_db['DBInstanceIdentifier'])
                rds_client.reboot_db_instance(
                    DBInstanceIdentifier=rds_db['DBInstanceIdentifier'],
                    ForceFailover=True
                )
                logger.info('after Force reboot/failover %s', rds_db['DBInstanceIdentifier'])
            else:
                logger.info('Failover aborted')
        else:
                logger.info('not_rds az or multi')
                logger.info('parameter [%s]',az_name)
                logger.info('rds [%s] [%s]',rds_db['AvailabilityZone'],rds_db['MultiAZ'])

        # else:
                # logger.info('not in vpc')

def force_failover_rds_aurora(rds_client, vpc_id, az_name, tag_name, tag_value):
    logger = logging.getLogger(__name__)
    # Find Aurora clusters
    rds_clusters = rds_client.describe_db_clusters()
    for rds_cluster in rds_clusters['DBClusters']:
        logger.info('DEBUG Found Aurora cluster %s', rds_cluster['DBClusterIdentifier'])
        # Check cluster info
        if rds_cluster['Status'] == 'available' and rds_cluster['MultiAZ'] and az_name in rds_cluster['AvailabilityZones']:
            logger.info('DEBUG Cluster is available, MultiAZ, and covers targeted AZ')
            # Check if cluster has pre-defined tagging
            rds_cluster_tag_correct=False
            rds_cluster_tags = rds_client.list_tags_for_resource(
                ResourceName=rds_cluster['DBClusterArn']
            )
            for rds_cluster_tag in rds_cluster_tags['TagList']:
                # if rds_cluster_tag['Key'] == 'rdsfail' and rds_cluster_tag['Value'] == 'yes':
                if rds_cluster_tag['Key'] == tag_name and rds_cluster_tag['Value'] == tag_value:
                    rds_cluster_tag_correct=True

            # for fail-az scenario, aurora within the targeted AZ will failover regardless untagged. Hence removing Tagging Validation Part.
            rds_cluster_tag_correct=True
            
            if rds_cluster_tag_correct:
                logger.info('DEBUG Cluster has pre-defined tagging')
                # Find cluster writer instances
                #   Aurora global clusters did not factor into consideration
                for rds_cluster_member in rds_cluster['DBClusterMembers']:
                    logger.info('DEBUG Cluster member %s found', rds_cluster_member['DBInstanceIdentifier'])
                    if rds_cluster_member['IsClusterWriter']:
                        logger.info('DEBUG Cluster member is a writer')
                        # Check cluster writer instance's AZ
                        rds_cluster_instances = rds_client.describe_db_instances(
                            DBInstanceIdentifier=rds_cluster_member['DBInstanceIdentifier']
                        )
                        rds_cluster_instance = rds_cluster_instances['DBInstances'][0]
                        #if rds_cluster_instance['DBInstanceStatus'] == 'available' and rds_cluster_instance['DBSubnetGroup']['VpcId'] == vpc_id and rds_cluster_instance['AvailabilityZone'] == az_name:
                        if rds_cluster_instance['DBInstanceStatus'] == 'available' and rds_cluster_instance['AvailabilityZone'] == az_name:
                            logger.info(
                                'MultiAZ database (Aurora) found in VPC: %s and AZ: %s ... failing over', 
                                rds_cluster_instance['DBInstanceIdentifier'], 
                                rds_cluster_instance['AvailabilityZone']
                            )
                            rds_client.failover_db_cluster(
                                DBClusterIdentifier=rds_cluster_instance['DBClusterIdentifier']
                            )
            else:
                logger.info('DEBUG Cluster is NOT targeted by tag')

def force_failover_elasticache(elasticache_client, az_name):
    logger = logging.getLogger(__name__)
    replication_groups = elasticache_client.describe_replication_groups()
    for replication in replication_groups['ReplicationGroups']:
        if replication['AutomaticFailover'] == 'enabled' and replication['ClusterEnabled'] == False:
            # find if primary node in blackout AZ
            for nodes in replication['NodeGroups']:
                for node in nodes['NodeGroupMembers']:  
                    if node['CurrentRole'] == 'primary' and node['PreferredAvailabilityZone'] == az_name:
                        ReplicationGroupId = replication['ReplicationGroupId']
                        NodeGroupId = node['CacheNodeId']
                        logger.info(
                            'cluster with ReplicationGroupId %s and NodeGroupId %s found with primary node in %s',
                            ReplicationGroupId,
                            NodeGroupId,
                            node['PreferredAvailabilityZone']
                        )
                        confirm ='c'
                        if confirm == 'c':
                            logger.info('Force automatic failover; no rollback possible')
                            elasticache_client.test_failover(
                                ReplicationGroupId=ReplicationGroupId,
                                NodeGroupId=NodeGroupId
                            )
                        else:
                            logger.info('Failover aborted')

def rollback(ec2_client, save_for_rollback, autoscaling_client):
    global filtered_original_asg

    logger = logging.getLogger(__name__)
    # logger.info('Rolling back Network ACL to original configuration')
    print('Rolling back Network ACL to original configuration')
    # Rollback the initial association

    for nacl_ass_id, nacl_id in save_for_rollback:
        print('::::: Chaos rollback > nacl_ass_id: %s nacl_id: %s' % (nacl_ass_id, nacl_id))
        ec2_client.replace_network_acl_association(
            AssociationId=nacl_ass_id,
            NetworkAclId=nacl_id
        )
        
    # if original_asg is not None:
        # logger.info('Rolling back AutoScalingGroup to original configuration')

        # for asg in original_asg:
            # asg_name = asg['AutoScalingGroupName']
            # asg_subnets = asg['VPCZoneIdentifier'].split(',')
            # vpczoneidentifier = ",".join(asg_subnets)
            # autoscaling_client.update_auto_scaling_group(AutoScalingGroupName=asg_name, VPCZoneIdentifier=vpczoneidentifier)
            # logger.info('Rolling back done= %s',asg_name)    
            
    if filtered_original_asg is not None:
        logger.info('Rolling back AutoScalingGroup to original configuration')

        # for k_asg, v_subnets in filtered_original_asg.items():
            # asg_name = k_asg
            # asg_subnets = v_subnets
            # vpczoneidentifier = ",".join(asg_subnets)
            # autoscaling_client.update_auto_scaling_group(AutoScalingGroupName=asg_name, VPCZoneIdentifier=vpczoneidentifier)
            # logger.info('Rolling back done= %s',asg_name)    

        for key, val in filtered_original_asg.items():
            print("key = {key}, value={value}".format(key=key,value=val))  
            logger.info('Rollback filtered original asg: %s, %s', key, val)
            asg_name=key
            asg_subnets=str(val).replace('[','').replace(']','')
            asg_subnets=asg_subnets.split(',')
            vpczoneidentifier = ",".join(asg_subnets).replace('\'','').replace(' ','')
            autoscaling_client.update_auto_scaling_group(AutoScalingGroupName=asg_name, VPCZoneIdentifier=vpczoneidentifier)
            logger.info('Rolling back done= %s',asg_name)
        
def post_rollback(region):
    logger = logging.getLogger(__name__)
    logger.info('Post Rolling back Network ACL to original configuration')
    # Rollback the initial association

    ec2_client = boto3.client('ec2', region_name=region)
    autoscaling_client = boto3.client('autoscaling', region_name=region)
    try:
        #save_for_rollback
        sts_client=boto3.client('sts').get_caller_identity()
        AccountID=sts_client['Account']

        ssm_client = boto3.client('ssm', region_name=region)

        param_name='/fip/' + AccountID + '/save_for_rollback'
        param_result = ssm_client.get_parameter(
            Name=param_name
        )
        save_for_rollback=param_result['Parameter']['Value']
        #save_for_rollback=str(save_for_rollback).replace('[','').replace(']','').replace('\'','')
        save_for_rollback=re.sub('[\[\]\' ]','',save_for_rollback)
        rset = stringToList(save_for_rollback,'),')
        for item in rset:
            #nacl_set=stringToList(item.replace('(','').replace(')','').replace(' ',''),',')
            nacl_set=stringToList(re.sub('[()\' ]','',item),',')

            ec2_client.replace_network_acl_association(
                AssociationId=nacl_set[0],
                NetworkAclId=nacl_set[1]
            )

        param_name='/fip/' + AccountID + '/filtered_original_asg'
        param_result = ssm_client.get_parameter(
            Name=param_name
        )

        p_filtered_original_asg=eval(param_result['Parameter']['Value'])

        if p_filtered_original_asg is not None:
            logger.info('Post Rolling back AutoScalingGroup to original configuration')

            for key, val in p_filtered_original_asg.items():
                #print("key = {key}, value={value}".format(key=key,value=val))  
                #logger.info('Rollback filtered original asg: %s, %s', key, val)
                asg_name=key
                #asg_subnets=str(val).replace('[','').replace(']','')
                asg_subnets=re.sub('[\[\]]','',str(val))
                asg_subnets=asg_subnets.split(',')
                vpczoneidentifier = ",".join(asg_subnets).replace('\'','').replace(' ','')
                autoscaling_client.update_auto_scaling_group(AutoScalingGroupName=asg_name, VPCZoneIdentifier=vpczoneidentifier)
                logger.info('Post Rolling back done= %s',asg_name)   

        return True
    
    except botocore.exceptions.ClientError as e:
        print(e)
        print("Failed post_rollback")
        return False
        # Rollback 

def delete_chaos_nacl(ec2_client, chaos_nacl_id):
    logger = logging.getLogger(__name__)
    logger.info('Deleting the Chaos NACL')
    # delete the Chaos NACL
    ec2_client.delete_network_acl(
        NetworkAclId=chaos_nacl_id
    )

def post_delete_chaos_nacl(region):
    logger = logging.getLogger(__name__)
    logger.info('Post Deleting the Chaos NACL')
    # delete the Chaos NACL
    ec2_client = boto3.client('ec2', region_name=region)

    try:
        #save_for_rollback
        sts_client=boto3.client('sts').get_caller_identity()
        AccountID=sts_client['Account']

        ssm_client = boto3.client('ssm', region_name=region)

        param_name='/fip/' + AccountID + '/chaos_nacl_id'
        param_result = ssm_client.get_parameter(
            Name=param_name
        )
        chaos_nacl_id=param_result['Parameter']['Value']

        ec2_client.delete_network_acl(
            NetworkAclId=chaos_nacl_id
        )

        return True
    
    except botocore.exceptions.ClientError as e:
        print(e)
        print("Failed delete chaos nacl")
        return False
        # Rollback 

def eks_single_az_failover(autoscaling_client, vpc_id, az_name, tag_name, tag_value):
    global eks_single_az_asg

    logger = logging.getLogger(__name__)
    logger.info('EKS Single-AZ Failover')

    eks_cluster_client = boto3.client('eks')
    eks_cluster_list = eks_cluster_client.list_clusters()
    #print(eks_cluster_list['clusters'])
    eks_eni_subnet={}

    for cluster in eks_cluster_list['clusters']:
        cluster_response=eks_cluster_client.describe_cluster(name=cluster)
        logger.info('EKS Single-AZ Failover cluster found: %s', cluster)
        eni_subnet=eks_endpoint_az_check(cluster,az_name)
        if eni_subnet is not None:
            eks_eni_subnet[cluster]=eni_subnet

    for key, val in eks_eni_subnet.items():
        print("key = {key}, value={value}".format(key=key,value=val))  
        logger.info('EKS Single-AZ Failover cluster found ENI subnet: %s, %s', key, val)

    paginator = autoscaling_client.get_paginator('describe_auto_scaling_groups')
    page_iterator = paginator.paginate(
        PaginationConfig={'PageSize': 100}
    )

    filtered_asgs = page_iterator.search(
        'AutoScalingGroups[] | [?contains(Tags[?Key==`{}`].Value, `{}`)]'.format(
            tag_name, tag_value)
    )

    for asg in filtered_asgs:
        asg_name=asg['AutoScalingGroupName']
        asg_az=asg['AvailabilityZones']
        asg_min=asg['MinSize']
        asg_desired=asg['DesiredCapacity']
        asg_subnet=asg['VPCZoneIdentifier']

        if len(asg_az) == 1 and az_name in asg_az:
            for key, val in eks_eni_subnet.items():
                if val in asg_subnet:
                    eks_single_az_asg[asg_name]=[asg_min,asg_desired]

                    logger.info('EKS Single-AZ Failover name : %s, subnet : %s, eni-subnet : %s, min : %s, desired %s', asg_name, asg_subnet, val, asg_min, asg_desired)

                    update_response = autoscaling_client.update_auto_scaling_group(
                        AutoScalingGroupName=asg_name,
                        MinSize=0,
                        DesiredCapacity=0,
                    )
                    break
                else:
                    logger.info('EKS Single-AZ Failover Not Done (different subnet) name : %s, subnet : %s, eni-subnet : %s, min : %s, desired %s', asg_name, asg_subnet, val, asg_min, asg_desired)

def eks_single_az_rollback(autoscaling_client):
    global eks_single_az_asg

    logger = logging.getLogger(__name__)
    logger.info('EKS Single-AZ Rollback')

    for key, val in eks_single_az_asg.items():
        #print("key = {key}, value={value}".format(key=key,value=val))  
        target_asg=key
        target_min=val[0]
        target_desired=val[1]

        logger.info('EKS Single-AZ Failback name : %s, min : %s, desired %s', target_asg, target_min, target_desired)

        update_response = autoscaling_client.update_auto_scaling_group(
            AutoScalingGroupName=target_asg,
                MinSize=target_min,
                DesiredCapacity=target_desired,
        )

def post_eks_single_az_rollback(region):
    logger = logging.getLogger(__name__)
    logger.info('Post EKS Single-AZ Rollback')

    autoscaling_client = boto3.client('autoscaling', region_name=region)

    try:
        #save_for_rollback
        sts_client=boto3.client('sts').get_caller_identity()
        AccountID=sts_client['Account']

        ssm_client = boto3.client('ssm', region_name=region)

        param_name='/fip/' + AccountID + '/eks_single_az_asg'
        param_result = ssm_client.get_parameter(
            Name=param_name
        )
        eks_single_az_asg=eval(param_result['Parameter']['Value'])

        for key, val in eks_single_az_asg.items():
            #print("key = {key}, value={value}".format(key=key,value=val))  
            target_asg=key
            target_min=val[0]
            target_desired=val[1]

            logger.info('Post EKS Single-AZ Failback name : %s, min : %s, desired %s', target_asg, target_min, target_desired)

            update_response = autoscaling_client.update_auto_scaling_group(
                AutoScalingGroupName=target_asg,
                    MinSize=target_min,
                    DesiredCapacity=target_desired,
            )
        return True
    
    except botocore.exceptions.ClientError as e:
        print(e)
        print("Failed POst eks single-az rollback")
        return False
        # Rollback 

def eks_endpoint_az_check(clustername, targetAZ):
    ec2 = boto3.resource('ec2')
    client = boto3.client('ec2')
    network_interface = ec2.NetworkInterface('id')
    description_value='Amazon EKS '+clustername

    response = client.describe_network_interfaces(
        Filters=[
            {
                'Name': 'description',
                'Values': [
                    description_value,
                ]
            },
            {
                'Name': 'availability-zone',
                'Values': [
                    targetAZ,
                ]                
            },
        ]
    )
    if len(response['NetworkInterfaces']) == 0 :
        return None
    else:
        return response['NetworkInterfaces'][0]['SubnetId']

def assume_role(role_arn):
    sts_client = boto3.client('sts')
    #role_arn = 'arn:aws:iam::' + account_id + ':role/' + account_role
    try:
        assumedRoleObject = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName="NewAccountRole"
        )
        
        return assumedRoleObject['Credentials']

    except botocore.exceptions.ClientError as e:
        print(e)
        print("Failed to Assume Role")
        # Rollback 

def save_rollback_param(region, save_for_rollback,chaos_nacl_id):
    global eks_single_az_asg
    global filtered_original_asg

    logger = logging.getLogger(__name__)
    logger.info('Save Rollback Parameters')

    result=boto3.client('sts').get_caller_identity()
    AccountID=result['Account']

    ssm_client = boto3.client('ssm')
    try:
        if save_for_rollback:
            param_name='/fip/' + AccountID + '/save_for_rollback'
            ssm_client.put_parameter(
                Name=param_name,
                Value=str(save_for_rollback),
                Type='String',
                Overwrite=True,
                Tier='Standard',
            )
        if chaos_nacl_id:
            param_name='/fip/' + AccountID + '/chaos_nacl_id'
            ssm_client.put_parameter(
                Name=param_name,
                Value=str(chaos_nacl_id),
                Type='String',
                Overwrite=True,
                Tier='Standard',
            )   
        if filtered_original_asg:
            param_name='/fip/' + AccountID + '/filtered_original_asg'
            ssm_client.put_parameter(
                Name=param_name,
                Value=str(filtered_original_asg),
                Type='String',
                Overwrite=True,
                Tier='Advanced',
            )
        if eks_single_az_asg:
            param_name='/fip/' + AccountID + '/eks_single_az_asg'
            ssm_client.put_parameter(
                Name=param_name,
                Value=str(eks_single_az_asg),
                Type='String',
                Overwrite=True,
                Tier='Advanced',
            )    
   
    except botocore.exceptions.ClientError as e:       
        #Rollback  
        print(e)
    
        ec2_client = boto3.client('ec2', region_name=region)
        autoscaling_client = boto3.client('autoscaling', region_name=region)
        rollback(ec2_client, save_for_rollback, autoscaling_client)
        delete_chaos_nacl(ec2_client, chaos_nacl_id)
        eks_single_az_rollback(autoscaling_client)

def save_rollback_param_alt(region, vpc_id, save_for_rollback,chaos_nacl_id):
    global args_glob
    
    global eks_single_az_asg
    global filtered_original_asg
    global recovery_list
    
    print('save_for_rollback')
    print(json.dumps(save_for_rollback, indent=4, default = str))
    
    # print ("A: %s" % os.getenv('AWS_ACCESS_KEY_ID'))
    # print ("A: %s" % os.getenv('AWS_SECRET_ACCESS_KEY'))
    # print ("A: %s" % os.getenv('AWS_SESSION_TOKEN'))
    # ENV_AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
    # ENV_AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
    # ENV_AWS_SESSION_TOKEN = os.getenv('AWS_SESSION_TOKEN')
    # del os.environ['AWS_ACCESS_KEY_ID']
    # del os.environ['AWS_SECRET_ACCESS_KEY']
    # del os.environ['AWS_SESSION_TOKEN']
    # print ("B: %s" % os.getenv('AWS_ACCESS_KEY_ID'))
    # print ("B: %s" % os.getenv('AWS_SECRET_ACCESS_KEY'))
    # print ("B: %s" % os.getenv('AWS_SESSION_TOKEN'))
    # print(json.dumps(boto3.client('sts').get_caller_identity(), indent=4, default = str))

    # f = open("~/.aws/credentials", "r")
    # print(f.read())
    # f = open("~/.aws/config", "r")
    # print(f.read())
    
    # os.rename('~/.aws/credentials', '~/.aws/credentials.bak')
    # os.rename('~/.aws/config', '~/.aws/config.bak')
    
    cred = boto3.client('sts').assume_role(RoleArn='arn:aws:iam::500574392968:role/fip-service_role',RoleSessionName='FAILAZ-NW')['Credentials']
    session = boto3.Session(
        aws_access_key_id = cred['AccessKeyId'],
        aws_secret_access_key = cred['SecretAccessKey'],
        aws_session_token = cred['SessionToken'],
        region_name = args_glob.caller_region
    )

    logger = logging.getLogger(__name__)
    logger.info('Save Rollback Parameters ALT')
    
    ssm_client = session.client('ssm')
        
    try:
        response = ssm_client.get_parameter(Name="/fip/recovery/failaz")
        if len(response['Parameter']['Value'].strip()):
            recovery_list = json.loads(response['Parameter']['Value'])
        else:
            recovery_list = []
    except ssm_client.exceptions.ParameterNotFound:
        recovery_list = []

    try:
        result=boto3.client('sts').get_caller_identity()
        AccountID=result['Account']
        
        recovery = {}
        recovery['Timestamp'] = datetime.now().isoformat()
        recovery['AccountArn'] = result['Arn']
        recovery['AccountId'] = result['Account']
        recovery['VpcId'] = vpc_id
        recovery['RollbackRecords'] = {}
        recovery['RollbackRecords']['save_for_rollback'] = save_for_rollback
        recovery['RollbackRecords']['chaos_nacl_id'] = chaos_nacl_id
        recovery['RollbackRecords']['filtered_original_asg'] = filtered_original_asg
        recovery['RollbackRecords']['eks_single_az_asg'] = eks_single_az_asg
        recovery_list.append(recovery)
        
        response = ssm_client.put_parameter(
            Name = "/fip/recovery/failaz",
            Value = json.dumps(recovery_list, indent=4, default = str),
            Type='String',
            Overwrite=True,
            Tier='Intelligent-Tiering'
        )
    except botocore.exceptions.ClientError as e:       
        #Rollback  
        print(e)
    
        # ec2_client = boto3.client('ec2', region_name=region)
        # autoscaling_client = boto3.client('autoscaling', region_name=region)
        # rollback(ec2_client, save_for_rollback, autoscaling_client)
        # delete_chaos_nacl(ec2_client, chaos_nacl_id)
        # eks_single_az_rollback(autoscaling_client)
        recover()

def delete_rollback_param(save_for_rollback,chaos_nacl_id):
    global eks_single_az_asg
    global filtered_original_asg

    logger = logging.getLogger(__name__)
    logger.info('Delete Rollback Parameters')

    result=boto3.client('sts').get_caller_identity()
    AccountID=result['Account']

    ssm_client = boto3.client('ssm')
    try:
        if save_for_rollback:
            param_name='/fip/' + AccountID + '/save_for_rollback'
            ssm_client.delete_parameter(
                Name=param_name
            )
        if chaos_nacl_id:
            param_name='/fip/' + AccountID + '/chaos_nacl_id'
            ssm_client.delete_parameter(
                Name=param_name
            )  
        if filtered_original_asg:
            param_name='/fip/' + AccountID + '/filtered_original_asg'
            ssm_client.delete_parameter(
                Name=param_name
            )
        if eks_single_az_asg:
            param_name='/fip/' + AccountID + '/eks_single_az_asg'
            ssm_client.delete_parameter(
                Name=param_name
            )        
    except botocore.exceptions.ClientError as e:
        print(e)

def run(region, az_name, vpc_id, duration, tag_name, tag_value, limit_asg, failover_rds, failover_elasticache, norm, failover_eks, log_level='INFO'):
    global original_asg

    setup_logging(log_level)
    logger = logging.getLogger(__name__)
        
    ec2_client = boto3.client('ec2', region_name=region)
    autoscaling_client = boto3.client('autoscaling', region_name=region)
    
    #norm block start
    if norm:
        logger.info('Setting up ec2 client for region %s ', region)

        chaos_nacl_id = create_chaos_nacl(ec2_client, vpc_id)
        subnets_to_chaos = get_subnets_to_chaos(ec2_client, vpc_id, az_name)
        nacl_ids = get_nacls_to_chaos(ec2_client, subnets_to_chaos)

        #kai
        limit_asg = True 
        # Limit AutoScalingGroup to no longer include failed AZ
        if limit_asg:
            #original_asg = limit_auto_scaling(autoscaling_client, subnets_to_chaos)
            limit_auto_scaling(autoscaling_client, subnets_to_chaos)
        else:
            original_asg = None

        # Blackhole networking to EC2 instances in failed AZ
        save_for_rollback = apply_chaos_config(ec2_client, nacl_ids, chaos_nacl_id)
        
        logger.info('DEBUG save_for_rollback %s', json.dumps(save_for_rollback))
        #logger.info('DEBUG original_asg %s', json.dumps(original_asg, default=json_serial))
        logger.info('DEBUG chaos_nacl_id %s', chaos_nacl_id)
        x = {
            "save_for_rollback": json.dumps(save_for_rollback),
            #"original_asg": json.dumps(original_asg, default=json_serial),
            "chaos_nacl_id": chaos_nacl_id
        }
        logger.info('DEBUG json_to_save %s', json.dumps(x))
    
        # if failover_eks:
            # eks_single_az_failover(autoscaling_client, vpc_id, az_name, tag_name, tag_value)
            # logger.info('EKS Single-AZ Failover Done')

        # save rollback parameters in the parameter store
        # save_rollback_param(region, save_for_rollback, chaos_nacl_id)
        save_rollback_param_alt(region, vpc_id, save_for_rollback, chaos_nacl_id)
    #norm block end
    
    # Fail-over RDS if in the "failed" AZ
    if failover_rds:
        rds_client = boto3.client('rds', region_name=region)
        logger.info('DEBUG tag %s value %s', tag_name, tag_value)
        force_failover_rds_aurora(rds_client, vpc_id, az_name, tag_name, tag_value)
        force_failover_rds(rds_client, vpc_id, az_name, tag_name, tag_value)
        logger.info('Failover RDS done')

    # Fail-over Elasticache if in the "failed" AZ
    if failover_elasticache:
        elasticache_client = boto3.client('elasticache', region_name=region)
        force_failover_elasticache(elasticache_client, az_name)
        logger.info('Failover Elasticache Done')

    #time.sleep(duration)
    
    # duration_limit=3500
    # tuple_val=divmod(duration, duration_limit)
    # logger.info('Duration Sleep : (%s x %s) + %s seconds', duration_limit, tuple_val[0], tuple_val[1])

    # for i in range(0,tuple_val[0]):
        # time.sleep(duration_limit)

    # time.sleep(tuple_val[1])
    
    #rollback procedure
    # rollback(ec2_client, save_for_rollback, autoscaling_client)
    # delete_chaos_nacl(ec2_client, chaos_nacl_id)
    # eks_single_az_rollback(autoscaling_client)

    #delete_rollback_parameters in the parameter store
    # delete_rollback_param(save_for_rollback, chaos_nacl_id)

def recover(recover_only = False):
    global recovery_list
    print("Running rollback procedures")
    
    ec2_client = boto3.client('ec2')
    autoscaling_client = boto3.client('autoscaling')
    
    cred = boto3.client('sts').assume_role(RoleArn='arn:aws:iam::500574392968:role/fip-service_role',RoleSessionName='FAILAZ-NW')['Credentials']
    session = boto3.Session(
        aws_access_key_id = cred['AccessKeyId'],
        aws_secret_access_key = cred['SecretAccessKey'],
        aws_session_token = cred['SessionToken'],
        region_name = args_glob.caller_region
    )
    
    if recover_only:
        ssm_client = session.client('ssm')
        response = ssm_client.get_parameter(Name="/fip/recovery/failaz")
        if len(response['Parameter']['Value'].strip()):
            rl = json.loads(response['Parameter']['Value'])
            print("Recovering from Parameter Store")
        # else:
            # print("Recovery list in Parameter Store is empty, forcing end of rollback procedures")
            # return
    else:
        rl = recovery_list
    
    global filtered_original_asg
    global eks_single_az_asg
    
    for recovery in rl:
        # Rollback procedures
        
        save_for_rollback = recovery['RollbackRecords']['save_for_rollback']
        chaos_nacl_id = recovery['RollbackRecords']['chaos_nacl_id']
        
        filtered_original_asg = recovery['RollbackRecords']['filtered_original_asg']
        eks_single_az_asg = recovery['RollbackRecords']['eks_single_az_asg']
        
        rollback(ec2_client, save_for_rollback, autoscaling_client)
        delete_chaos_nacl(ec2_client, chaos_nacl_id)
        eks_single_az_rollback(autoscaling_client)
    
def entry_point():
    global args_glob
    
    args = get_arguments()
    args_glob = args
    #args = get_arguments_test()
    print(args)

    # if(args.post_rollback):
        # if(post_rollback(args.region)) is True:
            # print('Post Rollback Success')
        # if(post_delete_chaos_nacl(args.region)) is True:
            # print('Post delete chaos_nacl Success')
        # if(post_eks_single_az_rollback(args.region)) is True:
            # print('Post eks single az rollback')
        # return
    # else:
        # print('set post_rollback False')
    
    if args.do_nothing:
        return
    
    if args.recover_only:
        recover(True)
    else:
        # print('Running for VpcId: %s...' % args.vpc_id)
        run(
            args.region,
            args.az_name,
            args.vpc_id,
            args.duration,
            args.tag_name,
            args.tag_value,
            args.limit_asg,
            args.failover_rds,
            args.failover_elasticache,
            args.norm,
            args.failover_eks,
            args.log_level
        )

if __name__ == '__main__':
    entry_point()
