#!/usr/bin/env python

"""fail_nw.py: Executes FIP scenarios on AWS networking"""

__version__ = "0.0.1"
__status__ = "Development"
__date__ = ""

import logging
import sys
import time
import json
from json.decoder import JSONDecodeError
import boto3
import botocore.exceptions
from botocore.exceptions import ClientError
from pythonjsonlogger import jsonlogger
import argparse

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

flags = {}

"""Application variables"""
flags['PARAM_STORE_CONFIG_SOURCE_NAME'] = "fip-parameters-source"
flags['PARAM_STORE_RECOVERY_NAME'] = "/fip/recovery/failnw" # Fip/Exec/Nw/RecoveryRecords
flags['LOCAL_LOG_FILE_NAME'] = "fail-nw.log" # fail-nw.log
flags['STABILIZING_PERIOD_SECS'] = 120 # 120

"""Developmental overrides"""
flags['LOAD_PARAMS_FROM_FILE'] = False # fip-parameters.json
# flags['LOAD_RECOVERY_FROM_FILE'] = "recovery.json" # recovery.json
flags['LOAD_RECOVERY_FROM_FILE'] = False # recovery.json
# flags['PARAM_STORE_REGION'] = "ap-southeast-2"

def setup_logging(log_level):
    logger = logging.getLogger(__name__)
    logger.setLevel(log_level)
    json_handler = logging.StreamHandler()
    file_handler = logging.FileHandler(flags['LOCAL_LOG_FILE_NAME'])

    #formatter = jsonlogger.JsonFormatter(
    #    fmt='%(asctime)s %(levelname)s %(name)s %(message)s'
    #)

    formatter = jsonlogger.JsonFormatter(
        fmt='%(asctime)s %(levelname)s %(message)s'
    )

    json_handler.setFormatter(formatter)
    # logger.addHandler(json_handler)

    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

def print_log(msg):
    print(msg)
    logger.info(msg)

def get_arguments():
    parser = argparse.ArgumentParser(
        description='Executes FIP scenarios on AWS networking',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--region', type=str, required=True,
                        help='The AWS region which FIP controller resides in')
    parser.add_argument('--recover-only', default=False, action='store_true',
                        help='Skip failure actions and execute recovery procedures only')
    return parser.parse_args()

class FipParams:
    @staticmethod
    def get_parameters(param_store_region):
        # TODO: Test/handle errors in loading parameters
        if flags['LOAD_PARAMS_FROM_FILE']:
            print_log("[DEV] Loading parameters from local file")
            file = open(flags['LOAD_PARAMS_FROM_FILE'])
            return json.load(file)
        else:
            try:
                print_log("Checking Parameter Store for configuration (Region: %s)" % param_store_region)
                client = boto3.client('ssm', region_name=param_store_region)
                response = client.get_parameter(Name=flags['PARAM_STORE_CONFIG_SOURCE_NAME'])
            except client.exceptions.ParameterNotFound as error:
                print_log("[ERR] Parameter store \"%s\" not found. Check your FIP configuration." % flags['PARAM_STORE_CONFIG_SOURCE_NAME'])
                raise error
            
            try:
                print_log("Retrieving configuration (Parameter Store: %s)" % response['Parameter']['Value'])
                response = client.get_parameter(Name=response['Parameter']['Value'])
                return json.loads(response['Parameter']['Value'])
            except client.exceptions.ParameterNotFound as error:
                print_log("[ERR] Parameter store \"%s\" not found. Verify that paramater store named in by \"%s\" exists." % (response['Parameter']['Value'], flags['PARAM_STORE_CONFIG_SOURCE_NAME']))
                raise error

class FipNetWorkExecutorRecovery:
    # @staticmethod
    # def write_f(value):
    
    @staticmethod
    def write_sp(param_store_region, value):
        client = boto3.client('ssm', region_name=param_store_region)
        response = client.put_parameter(
            # DataType='text',
            Name=flags['PARAM_STORE_RECOVERY_NAME'],
            Value=value,
            Type='String',
            Overwrite=True,
            Tier='Intelligent-Tiering'
        )
    
    @staticmethod
    def init(param_store_region):
        print_log("Initializing Parameter Store based recovery (Region: %s)" % param_store_region)
        recovery_list = []
        # FipNetWorkExecutorRecovery.set(param_store_region, json.dumps(recovery_list, indent=4, default = str))
        return recovery_list
    
    @staticmethod
    def set(param_store_region, recovery_list):
        if flags['LOAD_RECOVERY_FROM_FILE']:
            print_log("[DEV] Initializing local file for recovery")
            with open(flags['LOAD_RECOVERY_FROM_FILE'], mode='w', encoding='utf-8') as f:
                json.dump(recovery_list, f)
        else:
            # print_log("Setting recovery record...")
            FipNetWorkExecutorRecovery.write_sp(param_store_region, recovery_list)
            # 20220204
            # print("bring written")
            # print_log(recovery_list)
        
        return recovery_list

class FipNetworkExecutor:
    """
    Flow controls
    |
    v
    """
    
    def __init__(self, param_store_region):
        self.param_store_region = param_store_region
        # f = open('fip-parameters.json')
        # self.params_json = json.load(f)
        self.params = FipParams.get_parameters(param_store_region)
        # TODO: If parameters are invalid or incomplete, throw exception
        # TODO: (Low Priority) Hash param to check if param changed during failure execution
        # TODO: (Low Priority) More robust error-recovery?
        
        # Create separate sessions for all AWS accounts supplied in config
        if isinstance(self.params['CrossAccount_RoleARN'], list):
            accounts = self.params['CrossAccount_RoleARN']
        else: # Backward compatibility for old-style parameter
              # TODO: Update the rest of FIP code to use newer param
            accounts = []
            accounts.append({
                "RoleArn": self.params['CrossAccount_RoleARN'],
                "RegionName": self.params['RegionName']
            })
        self.create_sessions(accounts)
        
        self.recovery_list = FipNetWorkExecutorRecovery.init(param_store_region)
        
        # If running directly from __init__, then the calls would be next
        # self.do_actions()
        # self.do_recovery()
        
        # for key, value in self.sessions.items():
            # print_log(key)
            # print_log(value)
        
        # self.session = self.get_session(self.params_json['CrossAccount_RoleARN'])
        # self.test_list_vpcs2()
        
    
    def run(self):
        print_log('FIP Network Executor started.')
        self.do_actions()
        print_log('FIP Network Executor ended.')
        
    def run_recovery(self):
        print_log('FIP Network Executor (Recovery) started.')
        self.do_recovery()
        print_log('FIP Network Executor (Recovery) ended.')
    
    def do_actions(self):
        for idx, action in enumerate(self.params['Actions']):
            print_log("Performing action #%s..." % str(idx + 1))
            
            # TODO: (Low Priority) Switch to match-case if Python 3.10 is available
            if action['Type'] == 'delay':
                self.do_delay(action['DurationSec'])
            elif action['Type'] == 'tgw':
                self.do_tgw(action['VpcTagName'], action['VpcTagValue'])
            # elif action['Type'] == 'igw':
                # self.do_igw(action['VpcTagName'], action['VpcTagValue'])
            elif action['Type'] == 'natgw':
                self.do_natgw(action['VpcTagName'], action['VpcTagValue'])
            elif action['Type'] == 'vpc_endpoint':
                self.do_vpc_endpoint(action['VpcTagName'], action['VpcTagValue']) # What about recovering endpoints that require 3rd-party acceptance/confirmation?
            else:
                print_log(". Invalid action type (Type: %s)" % action['Type'])
        
        print_log('Actions completed. Concluding...')
        time.sleep(flags['STABILIZING_PERIOD_SECS']) # 120
    
    def do_recovery(self):
        print_log("Performing recovery...")
        
        # 20220204
        # print("self.param_store_region is %s" % self.param_store_region)
        
        # recovery_list = self.recovery_list
        # TODO: Implement proper sourcing, with error detection
        client = boto3.client('ssm', region_name=self.param_store_region)
        response = client.get_parameter(Name=flags['PARAM_STORE_RECOVERY_NAME'])
        recovery_list = json.loads(response['Parameter']['Value'])
        
        # 20220204
        # print_log(json.dumps(recovery_list, indent=4, default = str))
        
        for recovery in recovery_list:
            self.session = self.sessions[recovery['SessionKey']]
            print_log(". Using session: %s" % recovery['SessionKey'])
            print_log(json.dumps(recovery['Details'], indent=4, default = str))
            
            if recovery['Type'] == 'tgw':
                print_log('. . Re-creating TGW VPC attachment...')
                self.create_tgw_vpc_attachment(recovery['Details'])
            elif recovery['Type'] == 'igw':
                print_log('. . Re-attaching Internet gateway...')
                self.attach_internet_gateway(recovery['Details'])
            elif recovery['Type'] == 'natgw':
                print_log('. . Re-creating NAT gateway...')
                self.create_nat_gateway(recovery['Details'])
            elif recovery['Type'] == 'vpc_endpoint':
                print_log('. . Re-creating VPC endpoint...')
                self.create_vpc_endpoint(recovery['Details'])
            else:
                print_log(". . Invalid recovery action type (Type: %s)" % recovery['Type'])
            
            delattr(self, 'session')
        
        print_log('Recovery completed. Concluding...')
        time.sleep(flags['STABILIZING_PERIOD_SECS']) # 120

    def append_recovery(self, new_obj):
        self.recovery_list.append(new_obj)
        FipNetWorkExecutorRecovery.set(self.param_store_region, json.dumps(self.recovery_list, indent=4, default = str))
        # 20220204
        # print("current class var")
        # print_log(json.dumps(self.recovery_list, indent=4, default = str))

    """
    Workers/utils
    |
    v
    """
    
    def create_sessions(self, accounts): 
        """Creates separate sessions for each supplied account credentials."""
        
        self.sessions = {}
        for idx, acct in enumerate(accounts):
            print_log("Creating new API session (RoleArn=%s, RegionName=%s)" % (acct['RoleArn'], acct['RegionName']))
            acct_cred = self.assume_role(acct['RoleArn'])
            session = boto3.Session(
                aws_access_key_id = acct_cred['AccessKeyId'],
                aws_secret_access_key = acct_cred['SecretAccessKey'],
                aws_session_token = acct_cred['SessionToken'],
                region_name = acct['RegionName']
            )
            
            session_wrapper = {}
            key = acct['RegionName'] + acct['RoleArn']
            session_wrapper['idx'] = idx
            session_wrapper['key'] = key
            session_wrapper['role_arn'] = acct['RoleArn']
            session_wrapper['region_name'] = acct['RegionName']
            session_wrapper['session'] = session
            self.sessions[key] = session_wrapper
    
    def do_delay(self, durSec):
        print_log(". Delaying for %s sec(s)..." % durSec)
        time.sleep(int(durSec))
    
    def do_tgw(self, tag_name, tag_value):
        print_log('. Imparing TGW...')
        
        for key in self.sessions:
            self.session = self.sessions[key]
            print (". . Finding VPC in supplied account %s..." % self.sessions[key]['key'])
            vpcs = self.describe_vpcs(tag_name, [tag_value])
            for vpc in vpcs:
                print (". . . VPC found (CidrBlock: %s, VpcId: %s)" %  (vpc['CidrBlock'], vpc['VpcId']))
                # List TGW attachments, and delete
                tgw_vpc_attachments = self.describe_tgw_vpc_attachments(vpc_ids=[vpc['VpcId']])
                for tgw_vpc_attachment in tgw_vpc_attachments:
                    print (". . . . TGW VPC attachment found, deleting (TransitGatewayAttachmentId: %s)" %  tgw_vpc_attachment['TransitGatewayAttachmentId'])
                    
                    recovery_obj = {}
                    recovery_obj['Type'] = 'tgw'
                    recovery_obj['SessionKey'] = self.sessions[key]['key']
                    recovery_obj['Details'] = tgw_vpc_attachment
                    self.append_recovery(recovery_obj)
                    
                    self.delete_tgw_vpc_attachment(tgw_vpc_attachment['TransitGatewayAttachmentId'])
            delattr(self, 'session')
    
    def do_igw(self, tag_name, tag_value):
        print_log(". Imparing IGW...")
        
        for key in self.sessions:
            self.session = self.sessions[key]
            print (". . Finding VPC in supplied account %s..." % self.sessions[key]['key'])
            vpcs = self.describe_vpcs(tag_name, [tag_value])
            for vpc in vpcs:
                print (". . . VPC found (CidrBlock: %s, VpcId: %s)" %  (vpc['CidrBlock'], vpc['VpcId']))
                # List IGW, and detach
                igws = self.describe_internet_gateways(vpc_ids=[vpc['VpcId']])
                for igw in igws:
                    print (". . . . IGW found, detaching (InternetGatewayId: %s, VpcId: %s)" %  (igw['InternetGatewayId'], igw['Attachments'][0]['VpcId'])) # Q: Can VPCs have multiple IGW attachments?
                    
                    recovery_obj = {}
                    recovery_obj['Type'] = 'igw'
                    recovery_obj['SessionKey'] = self.sessions[key]['key']
                    recovery_obj['Details'] = igw
                    self.append_recovery(recovery_obj)
                    
                    self.detach_internet_gateway(igw['InternetGatewayId'], igw['Attachments'][0]['VpcId'])
            delattr(self, 'session')
    
    def do_natgw(self, tag_name, tag_value):
        print_log(". Imparing NAT GW...")
        
        for key in self.sessions:
            self.session = self.sessions[key]
            print (". . Finding VPC in supplied account %s..." % self.sessions[key]['key'])
            vpcs = self.describe_vpcs(tag_name, [tag_value])
            for vpc in vpcs:
                print (". . . VPC found (CidrBlock: %s, VpcId: %s)" %  (vpc['CidrBlock'], vpc['VpcId']))
                # List NAT GW, and delete
                natgws = self.describe_nat_gateways(vpc_ids=[vpc['VpcId']])
                for natgw in natgws:
                    print (". . . . NATGW found, detaching (NatGatewayId: %s, VpcId: %s, AllocationId = %s)" %  (natgw['NatGatewayId'], natgw['VpcId'], natgw['NatGatewayAddresses'][0]['AllocationId']))
                    
                    recovery_obj = {}
                    recovery_obj['Type'] = 'natgw'
                    recovery_obj['SessionKey'] = self.sessions[key]['key']
                    recovery_obj['Details'] = natgw
                    self.append_recovery(recovery_obj)
                    
                    self.delete_nat_gateway(natgw['NatGatewayId'])
            delattr(self, 'session')
    
    def do_vpc_endpoint(self, tag_name, tag_value):
        print_log(". Imparing VPC endpoint...")
        
        for key in self.sessions:
            self.session = self.sessions[key]
            print (". . Finding VPC in supplied account %s..." % self.sessions[key]['key'])
            vpcs = self.describe_vpcs(tag_name, [tag_value])
            for vpc in vpcs:
                print (". . . VPC found (CidrBlock: %s, VpcId: %s)" %  (vpc['CidrBlock'], vpc['VpcId']))
                # List VPC endpoints, and delete
                vpc_endpoints = self.describe_vpc_endpoints(vpc_ids=[vpc['VpcId']])
                for vpc_endpoint in vpc_endpoints:
                    print (". . . . VPC endpoint found, detaching (VpcEndpointId: %s, VpcId: %s)" %  (vpc_endpoint['VpcEndpointId'], vpc_endpoint['VpcId']))
                    
                    recovery_obj = {}
                    recovery_obj['Type'] = 'vpc_endpoint'
                    recovery_obj['SessionKey'] = self.sessions[key]['key']
                    recovery_obj['Details'] = vpc_endpoint
                    self.append_recovery(recovery_obj)
                    
                    self.delete_vpc_endpoint(vpc_endpoint['VpcEndpointId'])
            delattr(self, 'session')
    
    def do_recovery_f(self):
        with open('recovery.json', 'r') as f:
            try:
                recovery_objs = json.load(f)
        
                for idx, recovery_obj in enumerate(recovery_objs):
                    print_log("Performing recovery #%s..." % str(idx + 1))
                    self.session = self.sessions[int(recovery_obj['AccountIdx'])]
                    
                    if recovery_obj['Type'] == 'tgw':
                        self.create_tgw_vpc_attachment(recovery_obj['Details'])
                    elif recovery_obj['Type'] == 'igw':
                        # self.do_igw(action['TagName'], action['TagValue'])
                        print_log('RECOVERING')
                    else:
                        print_log("Invalid recovery action type (Type: %s)" % recovery_obj['Type'])
                    
                    delattr(self, 'session')
            
            except JSONDecodeError:
                print_log('No recovery details found')
    
    def append_recovery_f(self, new_obj):
        with open('recovery.json', 'r+') as f:
            try:
                obj = json.load(f)
            except JSONDecodeError:
                obj = []
            obj.append(new_obj)
            f.seek(0)
            json.dump(obj, f, indent=4, default = str)
            f.truncate()

    """
    Devs
    |
    v
    """
    
    def test_list_vpcs(self):
        # self.session = self.sessions[0]
        for idx, session in enumerate(self.sessions):
            self.session = session
            print ("Finding VPC in supplied account #%s..." % str(idx + 1))
            TAG = 'fip-target'
            TAG_VALUES = ['yes']
            MAX_ITEMS = 10
            vpcs = self.describe_vpcs(TAG, TAG_VALUES, MAX_ITEMS)
            delattr(self, 'session')
            # print_log(json.dumps(vpcs, indent=4, sort_keys=True))
            for vpc in vpcs:
                print ("\tVPC found (CidrBlock: %s, VpcId: %s)" %  (vpc['CidrBlock'], vpc['VpcId']))
            print_log('\t... done')
            
    def test_list_vpcs2(self):
        print ('Finding VPC...')
        # TAG = 'fip-target'
        # TAG_VALUES = ['yes']
        TAG = ''
        TAG_VALUES = []
        MAX_ITEMS = 10
        vpcs = self.describe_vpcs(TAG, TAG_VALUES, MAX_ITEMS)
        delattr(self, 'session')
        # print_log(json.dumps(vpcs, indent=4, sort_keys=True))
        for vpc in vpcs:
            print ("\tVPC found (CidrBlock: %s, VpcId: %s)" %  (vpc['CidrBlock'], vpc['VpcId']))
        print_log('\t... done')
    
    """
    AWS API accessors
    |
    v
    """
    
    def assume_role(self, role_arn):
        """Retrieves session credential for given IAM role."""
        
        client = boto3.client('sts')
        response = client.assume_role(
            RoleArn = role_arn,
            RoleSessionName = "FIP-Netw-Exec",
            # TODO-Immediate: Experiment with tags
            # Tags=[
                # {
                    # 'Key': 'string',
                    # 'Value': 'string'
                # },
            # ]
        )
        return response['Credentials']
        
        """
        session = {}
        session['session'] = boto3.Session(
            aws_access_key_id = response['Credentials']['AccessKeyId'],
            aws_secret_access_key = response['Credentials']['SecretAccessKey'],
            aws_session_token = response['Credentials']['SessionToken']
            # region_name = 'REGION'
        )
        session['region'] = self.params_json['RegionName']
        return session
        """
    
    def describe_vpcs(self, tag_name=None, tag_values=None, max_items='50'):
        try:
            filters = []
            if tag_name:
                filters.append({
                    'Name': f'tag:{tag_name}',
                    'Values': tag_values
                })
            
            # creating paginator object for describe_vpcs() method
            vpc_client = self.session['session'].client("ec2", region_name=self.session['region_name'])
            paginator = vpc_client.get_paginator('describe_vpcs')

            # creating a PageIterator from the paginator
            response_iterator = paginator.paginate(
                Filters=filters,
                PaginationConfig={'MaxItems': max_items})

            full_result = response_iterator.build_full_result()

            vpc_list = []

            for page in full_result['Vpcs']:
                vpc_list.append(page)

        except ClientError:
            logger.exception('Could not describe VPCs.')
            raise
        else:
            return vpc_list
    
    def describe_tgw_vpc_attachments(self, tag_name=None, tag_values=None, vpc_ids=None, max_items='50'):
        try:
            filters = []
            filters.append({
                    'Name': 'state',
                    'Values': ['initiatingRequest', 'pending', 'pendingAcceptance', 'available', 'modifying', 'rollingBack']
                })
            if tag_name:
                filters.append({
                    'Name': f'tag:{tag_name}',
                    'Values': tag_values
                })
            if vpc_ids:
                # If vpc_id == string
                filters.append({
                    'Name': 'vpc-id',
                    'Values': vpc_ids
                })
                # If vpc_id == array of strings *NOT IMPLEMENTED
            
            
            # creating paginator object for describe_transit_gateway_vpc_attachments() method
            vpc_client = self.session['session'].client("ec2", region_name=self.session['region_name'])
            paginator = vpc_client.get_paginator('describe_transit_gateway_vpc_attachments')

            # creating a PageIterator from the paginator
            response_iterator = paginator.paginate(
                Filters=filters,
                PaginationConfig={'MaxItems': max_items})

            full_result = response_iterator.build_full_result()

            tgw_vpc_attachment_list = []

            for page in full_result['TransitGatewayVpcAttachments']:
                tgw_vpc_attachment_list.append(page)

        except ClientError:
            logger.exception('Could not describe TGW VPC attachments.')
            raise
        else:
            return tgw_vpc_attachment_list
    
    def delete_tgw_vpc_attachment(self, tgw_id):
        try:
            vpc_client = self.session['session'].client("ec2", region_name=self.session['region_name'])
            response = vpc_client.delete_transit_gateway_vpc_attachment(
                # DryRun=True, # REMOVE BEFORE FLIGHT
                TransitGatewayAttachmentId=tgw_id
            )
        except ClientError as e:
            if e.response['Error']['Code'] == 'DryRunOperation':
                print('DryRun flag was set')
                pass
            else:
                logger.exception('Could not delete TGW attachment from VPC.')
                raise
        else:
            return response
    
    def create_tgw_vpc_attachment(self, tgw_vpc_att_dets):
        try:
            vpc_client = self.session['session'].client("ec2", region_name=self.session['region_name'])
            response = vpc_client.create_transit_gateway_vpc_attachment(
                # DryRun=True, # REMOVE BEFORE FLIGHT
                TransitGatewayId = tgw_vpc_att_dets['TransitGatewayId'],
                VpcId = tgw_vpc_att_dets['VpcId'],
                SubnetIds = tgw_vpc_att_dets['SubnetIds'],
                Options={
                    'DnsSupport': tgw_vpc_att_dets['Options']['DnsSupport'],
                    'Ipv6Support': tgw_vpc_att_dets['Options']['Ipv6Support']
                    # 'ApplianceModeSupport': tgw_vpc_att_dets['Options']['ApplianceModeSupport'] # ApplianceModeSupport needs to be dynamic, sometimes is not set/available
                },
                TagSpecifications=[
                    {
                        'ResourceType': 'transit-gateway-attachment',
                        'Tags': tgw_vpc_att_dets['Tags']
                    },
                ],
            )

        except ClientError as e:
            if e.response['Error']['Code'] == 'DryRunOperation':
                print('DryRun flag was set')
                pass
            else:
                logger.exception('Could not attach TGW to VPC.')
                raise
        else:
            return response
    
    def describe_internet_gateways(self, tag_name=None, tag_values=None, vpc_ids=None, max_items='50'):
        try:
            filters = []
            filters.append({
                    'Name': 'attachment.state',
                    'Values': ['available']
                })
            if tag_name:
                filters.append({
                    'Name': f'tag:{tag_name}',
                    'Values': tag_values
                })
            if vpc_ids:
                # If vpc_id == string
                filters.append({
                    'Name': 'attachment.vpc-id',
                    'Values': vpc_ids
                })
                # If vpc_id == array of strings *NOT IMPLEMENTED
            
            
            # creating paginator object for describe-internet-gateways() method
            vpc_client = self.session['session'].client("ec2", region_name=self.session['region_name'])
            paginator = vpc_client.get_paginator('describe_internet_gateways')

            # creating a PageIterator from the paginator
            response_iterator = paginator.paginate(
                Filters=filters,
                PaginationConfig={'MaxItems': max_items})

            full_result = response_iterator.build_full_result()

            igw_list = []

            for page in full_result['InternetGateways']:
                igw_list.append(page)

        except ClientError:
            logger.exception('Could not describe IGW.')
            raise
        else:
            return igw_list
    
    def detach_internet_gateway(self, igw_id, vpc_id):
        try:
            vpc_client = self.session['session'].client("ec2", region_name=self.session['region_name'])
            response = vpc_client.detach_internet_gateway(
                # DryRun=True, # REMOVE BEFORE FLIGHT
                InternetGatewayId=igw_id,
                VpcId=vpc_id
            )
        except ClientError as e:
            if e.response['Error']['Code'] == 'DryRunOperation':
                print('DryRun flag was set')
                pass
            else:
                logger.exception('Could not detach IGW from VPC.')
                raise
        else:
            return response
    
    def describe_nat_gateways(self, tag_name=None, tag_values=None, vpc_ids=None, max_items='50'):
        try:
            filters = []
            filters.append({
                    'Name': 'state',
                    'Values': ['available']
                })
            if tag_name:
                filters.append({
                    'Name': f'tag:{tag_name}',
                    'Values': tag_values
                })
            if vpc_ids:
                # If vpc_id == string
                filters.append({
                    'Name': 'vpc-id',
                    'Values': vpc_ids
                })
                # If vpc_id == array of strings *NOT IMPLEMENTED
            
            # creating paginator object for describe_transit_gateway_vpc_attachments() method
            vpc_client = self.session['session'].client("ec2", region_name=self.session['region_name'])
            paginator = vpc_client.get_paginator('describe_nat_gateways')

            # creating a PageIterator from the paginator
            response_iterator = paginator.paginate(
                Filters=filters,
                PaginationConfig={'MaxItems': max_items})

            full_result = response_iterator.build_full_result()

            natgw_list = []

            for page in full_result['NatGateways']:
                natgw_list.append(page)

        except ClientError:
            logger.exception('Could not describe NAT gateways.')
            raise
        else:
            return natgw_list
    
    def delete_nat_gateway(self, natgw_id):
        try:
            vpc_client = self.session['session'].client("ec2", region_name=self.session['region_name'])
            response = vpc_client.delete_nat_gateway(
                # Unknown parameter in input: "DryRun", must be one of: NatGatewayId
                # DryRun=True, # REMOVE BEFORE FLIGHT
                NatGatewayId=natgw_id
            )
        except ClientError as e:
            if e.response['Error']['Code'] == 'DryRunOperation':
                print('DryRun flag was set')
                pass
            else:
                logger.exception('Could not delete NAT gateway.')
                raise
        # else:
            # return response
    
    def create_nat_gateway(self, natgw_dets):
        try:
            vpc_client = self.session['session'].client("ec2", region_name=self.session['region_name'])
            response_crngw = vpc_client.create_nat_gateway(
                # DryRun=True, # REMOVE BEFORE FLIGHT
                AllocationId=natgw_dets['NatGatewayAddresses'][0]['AllocationId'], # Q: Can NATGW have multiple addresses?
                SubnetId=natgw_dets['SubnetId']
                # TagSpecifications=[ # Boto3 NATGW tag-on-creation is borked??!
                    # {
                        # 'ResourceType': 'natgateway',
                        # 'Tags': natgw_dets['Tags']
                    # },
                # ],
            )
            response = vpc_client.create_tags(
                Resources=[response_crngw['NatGateway']['NatGatewayId']],
                Tags=natgw_dets['Tags']
            )

        except ClientError as e:
            if e.response['Error']['Code'] == 'DryRunOperation':
                print('DryRun flag was set')
                pass
            else:
                logger.exception('Could not create NAT gateway.')
                raise
        else:
            return response
    
    def describe_vpc_endpoints(self, tag_name=None, tag_values=None, vpc_ids=None, max_items='50'):
        try:
            filters = []
            filters.append({
                    'Name': 'vpc-endpoint-state',
                    'Values': ['available']
                })
            if tag_name:
                filters.append({
                    'Name': f'tag:{tag_name}',
                    'Values': tag_values
                })
            if vpc_ids:
                # If vpc_id == string
                filters.append({
                    'Name': 'vpc-id',
                    'Values': vpc_ids
                })
                # If vpc_id == array of strings *NOT IMPLEMENTED
            
            # creating paginator object for describe_transit_gateway_vpc_attachments() method
            vpc_client = self.session['session'].client("ec2", region_name=self.session['region_name'])
            paginator = vpc_client.get_paginator('describe_vpc_endpoints')

            # creating a PageIterator from the paginator
            response_iterator = paginator.paginate(
                Filters=filters,
                PaginationConfig={'MaxItems': max_items})

            full_result = response_iterator.build_full_result()

            vpc_endpoint_list = []

            for page in full_result['VpcEndpoints']:
                vpc_endpoint_list.append(page)

        except ClientError:
            logger.exception('Could not describe VPC endpoints.')
            raise
        else:
            return vpc_endpoint_list
    
    def delete_vpc_endpoint(self, vpc_endpoint_id):
        try:
            vpc_client = self.session['session'].client("ec2", region_name=self.session['region_name'])
            response = vpc_client.delete_vpc_endpoints(
                # DryRun=True, # REMOVE BEFORE FLIGHT
                VpcEndpointIds=[vpc_endpoint_id]
            )
        except ClientError as e:
            if e.response['Error']['Code'] == 'DryRunOperation':
                print('DryRun flag was set')
                pass
            else:
                logger.exception('Could not delete VPC endpoint.')
                raise
        else:
            return response
    
    def create_vpc_endpoint(self, vpc_endpoint_dets):
        try:
            vpc_client = self.session['session'].client("ec2", region_name=self.session['region_name'])
            response = vpc_client.create_vpc_endpoint(
                # DryRun=True, # REMOVE BEFORE FLIGHT
                VpcEndpointType=vpc_endpoint_dets['VpcEndpointType'],
                VpcId=vpc_endpoint_dets['VpcId'],
                ServiceName=vpc_endpoint_dets['ServiceName'],
                PolicyDocument=vpc_endpoint_dets['PolicyDocument'],
                RouteTableIds=vpc_endpoint_dets['RouteTableIds'],
                SubnetIds=vpc_endpoint_dets['SubnetIds'],
                SecurityGroupIds=vpc_endpoint_dets['Groups'],
                PrivateDnsEnabled=vpc_endpoint_dets['PrivateDnsEnabled'],
                TagSpecifications=[
                    {
                        'ResourceType': 'vpc-endpoint',
                        'Tags': vpc_endpoint_dets['Tags']
                    },
                ],
            )

        except ClientError as e:
            if e.response['Error']['Code'] == 'DryRunOperation':
                print('DryRun flag was set')
                pass
            else:
                logger.exception('Could not create NAT gateway.')
                raise
        else:
            return response

def init(param_store_region):
    global args
    
    log_level = "INFO"
    setup_logging(log_level)
    logger = logging.getLogger(__name__)
    
    executor = FipNetworkExecutor(param_store_region)
    
    if args.recover_only:
        executor.run_recovery()
    else:
        executor.run()

args = get_arguments()
if args.region:
    param_store_region = args.region
elif flags['PARAM_STORE_REGION']:
    print_log("[DEV] Overriding Parameter Store region to %s" % flags['PARAM_STORE_REGION'])
    param_store_region = flags['PARAM_STORE_REGION']
else:
    sys.exit("Unexpected fault. Param Store region not provided")

# 20220204
# print("param_store_region is %s" % param_store_region)

init(param_store_region)

"""
Miscellaneous notes and whatever below:

Py naming conv.: module_name, package_name, ClassName, method_name, ExceptionName, function_name, GLOBAL_CONSTANT_NAME, global_var_name, instance_var_name, function_parameter_name, local_var_name

print_log(json.dumps(HERE, indent=4, default = str))

"""