import boto3
import os
import re
import json
import logging
import datetime

from time import sleep

logger = logging.getLogger()
logger.setLevel(logging.INFO)

################################################################################################
# Variables
################################################################################################
project_name	 	= os.environ['project_name']
region			 	= os.environ['region']
org_account_id		= os.environ['org_account_id']
member_role_name 	= os.environ['member_role_name']
session_name 		= f'{project_name}-report'


################################################################################################
# Regex
################################################################################################
is_account_id = re.compile('^[0-9]{12}$')

################################################################################################
# This function will make the datetime object serializable for json.dumps
################################################################################################
def datetime_handler(x):
    if isinstance(x, datetime.datetime):
        return x.isoformat()
    raise TypeError("Unknown type")

################################################################################################
# Create cross account credentials
################################################################################################
def create_client(account_id, region, service):
	retry_limit = 1
	retries = 0
	while True:
		try:
			sts_connection = boto3.client('sts')
			external_account = sts_connection.assume_role(
				RoleArn=f"arn:aws:iam::{account_id}:role/{member_role_name}",
				RoleSessionName=session_name
			)
			
			ACCESS_KEY = external_account['Credentials']['AccessKeyId']
			SECRET_KEY = external_account['Credentials']['SecretAccessKey']
			SESSION_TOKEN = external_account['Credentials']['SessionToken']

			# create service client using the assumed role credentials, e.g. S3
			client = boto3.client(
				service,
				aws_access_key_id=ACCESS_KEY,
				aws_secret_access_key=SECRET_KEY,
				aws_session_token=SESSION_TOKEN,
				region_name=region
			)
			break
		except Exception as e:
			print(f'Error creating {service} client  -- {account_id}')
			print(e)
			retries += 1
			if retries >= retry_limit:
				print(f'Retry limit of {retry_limit} attempts reached. Exiting...')
				exit(1)
			sleep(2)

	return client

################################################################################################
# Get available regions for account
################################################################################################
def get_available_regions(account_id):
	# Retrieve all of the available regions in an account.

	account_regions = []
	try:
		ec2 = create_client(account_id, 'us-east-1', 'ec2')

		params = {}
		params["AllRegions"] = False
		regions_dict = ec2.describe_regions(**params)
		all_regions = [region['RegionName'] for region in regions_dict['Regions']]
	except Exception as e:
		print(e)
		pass

	# Test to see if regions found are actually enabled.
	for region in all_regions:
		sts = create_client(account_id, region, 'sts')
		try:
			sts.get_caller_identity()
			account_regions.append(region)
		except ClientError as e:
			continue

	return account_regions


################################################################################################
# Make account name consistent
################################################################################################
def clean_account_name(account_name):
	chars_to_replace = "'\"()!@#$%^&*_+:;<>/?\\`~=,"
	for char in chars_to_replace:
		account_name = account_name.replace(char, "")
	return account_name.replace(" ", "-").lower()

################################################################################################
# Retry with exponential backoff
################################################################################################
def retry(e, message, retry_count, retry_limit):
	print(e)
	if retry_count > retry_limit:
		print(f'Reached limit of {retry_limit} retries: {message}. Exiting...')
		exit(1)
	else:
		print(f'Retrying in {2*retry_count} seconds: {message}')
		sleep(2*retry_count) # exponential backoff for rate limiting
	retry_count = retry_count + 1
	return retry_count