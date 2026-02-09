import boto3
import base64
import os
import requests
import json

kms_client = boto3.client("kms")
KEY_ALIAS = "alias/boring-cookie-kms-key"

BASE_URL = "https://api.cryptlex.com/v3"
CRYPTLEX_API_KEY = os.environ.get("CRYPTLEX_API_KEY")
ACCOUNT_ALIAS = os.environ.get("ACCOUNT_ALIAS", "boring")

def lambda_handler(event, context):

    headers = event.get("headers", {})

    print("Headers:", headers)

    cookie_header = headers.get("cookie") or headers.get("Cookie")
    cookie_token = get_token_from_cookie(cookie_header)
    print("Incoming cookies token:", cookie_token)

    origin = event.get("headers", {}).get("origin", "")  # Note lowercase in API Gateway
    allowed_origins = ["https://portal.boring.com", "https://portal.dev.boring.com", "http://localhost:3000"]
    cors_origin = origin if origin in allowed_origins else "null"

    # Preflight OPTIONS request
    if event["httpMethod"] == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": cors_origin,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": "OPTIONS,POST,GET",
                "Access-Control-Allow-Headers": "Content-Type,Authorization",
            },
            "body": ""
        }

    validated = validate_cookie(cookie_token)
    if not validated:
        return {
            "statusCode": 401,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": cors_origin,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": "OPTIONS,POST,GET",
                "Access-Control-Allow-Headers": "Content-Type,Authorization"
            },
            "body": json.dumps({"errorReason": "invalid_cookie", "errorMessage": "Invalid cookie"})
        }

    try:
        body = json.loads(event.get("body") or "{}")
        organization_description = body.get("organizationName")
        organization_id = body.get("organizationId")

        organization = update_org_name(organization_description, organization_id)

        if "errorMessage" in organization:
            body = organization["errorMessage"]
            status = organization.get("statusCode", 400)
        else:
            status = 200
            body = organization

        return {
            "statusCode": status,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": cors_origin,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": "OPTIONS,POST,GET",
                "Access-Control-Allow-Headers": "Content-Type,Authorization"
            },
            "body": json.dumps(body)
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": cors_origin,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": "OPTIONS,POST,GET",
                "Access-Control-Allow-Headers": "Content-Type,Authorization"
            },
            "body": str(e)
        }

def update_org_name(organization_description, organization_id):
    url = f"{BASE_URL}/organizations/{organization_id}"
    headers = {
        "Authorization": f"Bearer {CRYPTLEX_API_KEY}",
        "Content-Type": "application/json"
    }
    print("updating organization with description:", organization_description)
    payload = {
        "description": organization_description
    }
    resp = requests.patch(url, json=payload, headers=headers)

    if resp.status_code == 400:
        return {
            "errorMessage": "Error editing organization",
            "statusCode": 400
        }

    print("Response from update organization:", resp.status_code, resp.text)
    resp.raise_for_status()
    return resp.json()

def get_token_from_cookie(cookie_header):
    if not cookie_header:
        return None
    cookies = cookie_header.split(";")
    for cookie in cookies:
        cookie = cookie.strip()
        if cookie.startswith("token="):
            return cookie[len("token="):]
    return None

def validate_cookie(encrypted_cookie):
    """
    Decrypts the encrypted cookie and checks if userRole is 'organization-admin'.
    Returns True if valid, False otherwise.
    """
    try:
        ciphertext_blob = base64.b64decode(encrypted_cookie)
        resp = kms_client.decrypt(CiphertextBlob=ciphertext_blob)
        plaintext = resp["Plaintext"]
        payload = json.loads(plaintext)
        return payload.get("userRole") == "organization-admin"
    except Exception as e:
        print(f"Cookie validation failed: {e}")
        return False