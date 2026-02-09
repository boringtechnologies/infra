'''
POST REQUEST FOR TEMP CREDS
{
  "body": "{\"activationId\": \"019a521a-d008-7fbc-a96b-79fe2d6a4af5\", \"status\": \"STARTED\"}"
}

POST REQUEST TO SIGNAL JOB END
{
  "body": "{\"activationId\": \"019a521a-d008-7fbc-a96b-79fe2d6a4af5\", \"status\": \"ENDED\", \"jobId\": \"f47ac10b-58cc-4372-a567-0e02b2c3d479\"}"
}
'''

import json
import requests
import boto3
import os
import time
import datetime
from datetime import datetime, timezone
import uuid

CRYPTLEX_API_KEY = os.environ["CRYPTLEX_API_KEY"]
ACCOUNT_ALIAS    = os.environ["ACCOUNT_ALIAS"]
BASE_URL         = os.environ["BASE_URL"]
MONTHLY_CAP      = 20

sts = boto3.client("sts")
ROLE_ARN = "arn:aws:iam::710831443439:role/boring_captioning_role"

# Create DynamoDB client
dynamodb = boto3.resource("dynamodb")
usage_table = dynamodb.Table("usage_log")
overview_table = dynamodb.Table("org_overview")
    
def lambda_handler(event, context):
    body = json.loads(event.get("body") or "{}")
    activation_id = body.get("activationId")
    status = body.get("status")
    job_id = body.get("jobId")

    print("Activation ID: ", activation_id)
    print("Status: ", status)
    
    # Validate request parameters
    if not activation_id:
        return {
            'statusCode': 400,
            'body': json.dumps({"error": "Missing activationId"})
        }
        
    if status not in ["STARTED", "ENDED"]:
        return {
            'statusCode': 400,
            'body': json.dumps({"error": "Invalid status, must be 'STARTED' or 'ENDED'"})
        }
        
    if status == "STARTED":
        job_id = str(uuid.uuid4())
    elif not job_id:
        return {
            'statusCode': 400,
            'body': json.dumps({"error": "Transcription job ENDED must also include jobId"})
        }

    # Validate activation_id and transcription caps
    license_key, organization_id = get_license_from_activation(activation_id)

    if status == "ENDED":
        record_time(activation_id, organization_id, status, job_id)
        return {
            'statusCode': 200,
            'body': json.dumps({"message": "Job end time recorded", "jobId": job_id})
        }
    
    usage = check_transcription_cap(organization_id)
    if usage > MONTHLY_CAP:
        return {
            'statusCode': 400,
            'body': json.dumps({"error": "Monthly transcription cap exceeded"})
        }
    
    creds = generate_captioning_keys(license_key)
    creds["Expiration"] = creds["Expiration"].isoformat()
    
    record_time(activation_id, organization_id, status, job_id)

    return {
        'statusCode': 200,
        'body': json.dumps({
            "message": "Success",
            "jobId": job_id,
            "activationId": activation_id,
            "temporaryCreds": creds
        })
    }
    
def record_time(activation_id, organization_id, status, job_id):
    now = datetime.now()
        
    item = {
        "job_id": job_id,
        "activation_id": activation_id,
        "timestamp": int(time.time() * 1000),
        "organization_id": organization_id,
        "status": status,
        "date": now.strftime("%Y-%m"),
        "accounted": False
    }

    try:
        usage_table.put_item(Item=item)
        print("Start time written successfully - ", str(activation_id))
    except Exception as e:
        print("Error writing start time: " + str(e))

def get_license_from_activation(activation_id: str):
    url = f"https://api.cryptlex.com/v3/activations/{activation_id}"
    headers = {"Authorization": f"Bearer {CRYPTLEX_API_KEY}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    activation = resp.json()
    print("Activation ", activation)
    license_id = activation.get("licenseId") or activation.get("license", {}).get("key")
    
    url = f"https://api.cryptlex.com/v3/licenses/{license_id}"
    headers = {"Authorization": f"Bearer {CRYPTLEX_API_KEY}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    license = resp.json()
    organization_id = license.get("organization", {}).get("id")
    license_key = license.get("key")
    return license_key, organization_id

def generate_captioning_keys(license_key: str):
    response = sts.assume_role(
        RoleArn=ROLE_ARN,
        RoleSessionName=f"transcribe-session-{license_key[:8]}",
        Tags=[{"Key": "licenseKey", "Value": license_key}],
        TransitiveTagKeys=["licenseKey"],
        DurationSeconds=3600
    )
    return response["Credentials"]

def check_transcription_cap(organization_id):
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        response = overview_table.get_item(
            Key={
                "organization_id": organization_id,
                "month": month
            }
        )
        item = response.get("Item")
        if not item:
            return 0  # no usage yet this month
        return item.get("total_hours", 0)
    except Exception as e:
        print(f"Error fetching hours for org {organization_id}: {e}")
        return 0