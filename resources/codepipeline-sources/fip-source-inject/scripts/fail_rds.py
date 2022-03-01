"""
Script to force an RDS reboot with failover to another AZ.
Rebooting a DB instance restarts the database engine service.
Rebooting a DB instance results in a momentary outage,
during which the DB instance status is set to rebooting.

To perform the reboot with a failover, Amazon RDS instance
must be configured for Multi-AZ.

When you force a failover of your DB instance, Amazon RDS
automatically switches to a standby replica in another Availability
Zone, and updates the DNS record for the DB instance to point to the
standby DB instance. As a result, you need to clean up and re-establish
any existing connections to your DB instance.

Important: When you force a failover from one Availability Zone to another
when you reboot the Availability Zone change might not be reflected
in the AWS Management Console and in calls to the AWS CLI
and RDS API, for several minutes.
https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_RebootInstance.html
"""
import argparse
import logging
import boto3

from pythonjsonlogger import jsonlogger

def setup_logging(log_level):
    logger = logging.getLogger(__name__)
    logger.setLevel(log_level)
    json_handler = logging.StreamHandler()
    file_handler = logging.FileHandler('rds.log')

    formatter = jsonlogger.JsonFormatter(
        fmt='%(asctime)s %(levelname)s %(name)s %(message)s'
    )
    json_handler.setFormatter(formatter)
    logger.addHandler(json_handler)

    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


def get_arguments():
    parser = argparse.ArgumentParser(
        description='Force RDS failover if master is in a particular AZ or if database ID provided',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--region', type=str, required=True,
                        help='The AWS region of choice.')
    parser.add_argument('--rds-id', type=str, default="",
                        help='The Id of the RDS database to failover.')
    parser.add_argument('--vpc-id', type=str, default="",
                        help='The VPC ID of where the DB is.')
    parser.add_argument('--az-name', type=str, default="",
                        help='The name of the AZ where the DB master is.')
    parser.add_argument('--tag-name', type=str, default='fip',
                        help='The tag name of instances to be affected during blackout')
    parser.add_argument('--tag-value', type=str, default='yes',
                        help='The tag value of instances to be affected during blackout')
    parser.add_argument('--log-level', type=str, default='INFO',
                        help='Python log level. INFO, DEBUG, etc.')

    return parser.parse_args()


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
                
        if rds_db['DBSubnetGroup']['VpcId'] == vpc_id:
            if rds_db['AvailabilityZone'] == az_name and rds_db['MultiAZ']:
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
                    continue
                
                # if RDS master is multi-az and in blackholed AZ
                # force reboot with failover
                confirm ='c'
                if confirm == 'c':
                    logger.info('Force reboot/failover')
                    rds_client.reboot_db_instance(
                        DBInstanceIdentifier=rds_db['DBInstanceIdentifier'],
                        ForceFailover=True
                    )
                else:
                    logger.info('Failover aborted')


def force_failover_rds_id(rds_client, rds_id):
    logger = logging.getLogger(__name__)
    # Find RDS master instances within the AZ
    rds_dbs = rds_client.describe_db_instances(
        DBInstanceIdentifier=rds_id,
    )
    for rds_db in rds_dbs['DBInstances']:
        if rds_db['MultiAZ']:
            logger.info(
                'MultiAZ enabled database found: %s', rds_id
            )
            # if RDS master is multi-az and in blackholed AZ
            # force reboot with failover
            confirm ='c'
            if confirm == 'c':
                logger.info('Force reboot/failover')
                rsp = rds_client.reboot_db_instance(
                    DBInstanceIdentifier=rds_db['DBInstanceIdentifier'],
                    ForceFailover=True
                )
                return {
                    'primary_az': rsp['DBInstance']['AvailabilityZone'],
                    'secondary_az': rsp['DBInstance']['SecondaryAvailabilityZone']
                }
            else:
                logger.info('Failover aborted')


def force_failover_rds_aurora(rds_client, vpc_id, az_name, tag_name, tag_value):
    logger = logging.getLogger(__name__)
    # Find Aurora clusters
    rds_clusters = rds_client.describe_db_clusters()
    for rds_cluster in rds_clusters['DBClusters']:
        logger.info('DEBUG Found Aurora cluster %s', rds_cluster['DBClusterIdentifier'])
        # Check cluster info
        if rds_cluster['Status'] == 'available' and rds_cluster['MultiAZ']:
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
            if rds_cluster_tag_correct:
                logger.info('DEBUG Cluster has pre-defined tagging')
                # Find cluster writer instances
                # WARNING!
                #   The following assumes cluster has only 1 writer
                #   Modification required to safely process multi-writer clusters
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
                        # if rds_cluster_instance['DBInstanceStatus'] == 'available' and rds_cluster_instance['DBSubnetGroup']['VpcId'] == vpc_id and rds_cluster_instance['AvailabilityZone'] == az_name:
                        if rds_cluster_instance['DBInstanceStatus'] == 'available':
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


def run(region, rds_id, az_name, vpc_id, tag_name, tag_value, log_level='INFO'):
    setup_logging(log_level)
    logger = logging.getLogger(__name__)
    logger.info('Setting up rds client for region %s ', region)
    rds_client = boto3.client('rds', region_name=region)
    # if rds_id:
        # response = force_failover_rds_id(rds_client, rds_id)
    # else:
        # response = force_failover_rds(rds_client, vpc_id, az_name)
    force_failover_rds_aurora(rds_client, vpc_id, az_name, tag_name, tag_value)
    force_failover_rds(rds_client, vpc_id, az_name, tag_name, tag_value)
    # print(response)


def entry_point():
    args = get_arguments()
    print(args)
    run(
        args.region,
        args.rds_id,
        args.az_name,
        args.vpc_id,
        args.tag_name,
        args.tag_value,
        args.log_level
    )


if __name__ == '__main__':
    entry_point()
