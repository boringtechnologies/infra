import base64
import email
import email.policy
import hashlib
import hmac
import json
import os
import time

import boto3
from bson import ObjectId
from pymongo import MongoClient

DATABASE_NAME = os.environ.get("FALCON_DB_NAME", "falconmdpa")
PROPERTIES_COLLECTION = "properties"
UPLOADS_BUCKET = os.environ.get("UPLOADS_BUCKET", "")

ALLOWED_ORIGINS = [
    "https://dev.falconmdpa.com",
    "https://falconmdpa.com",
    "http://localhost:3000",
]

ALLOWED_SORT_FIELDS = {"createdAt", "price", "address", "_id"}


def _cors_headers(origin):
    cors_origin = origin if origin in ALLOWED_ORIGINS else "null"
    return {
        "Access-Control-Allow-Origin": cors_origin,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE",
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
    }


def _b64url_decode(s):
    s = s.replace("-", "+").replace("_", "/")
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.b64decode(s)


def _verify_jwt(token, secret):
    """Verify a JWT token (HS256). Returns decoded payload or None if invalid."""
    try:
        parts = token.strip().split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected_sig = hmac.new(
            secret.encode("utf-8"), signing_input, hashlib.sha256
        ).digest()
        actual_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        if payload.get("exp") and payload["exp"] < time.time():
            return None
        return payload
    except Exception:
        return None


def _require_auth(event, cors_headers):
    """Extract and verify Bearer token. Returns (payload, None) or (None, error_response)."""
    headers = event.get("headers") or {}
    auth_header = (
        headers.get("Authorization") or headers.get("authorization") or ""
    )
    if not auth_header:
        return None, _json_response(401, {"error": "No token provided"}, cors_headers)
    token = auth_header.replace("Bearer ", "").strip()
    jwt_secret = os.environ.get("JWT_SECRET", "")
    payload = _verify_jwt(token, jwt_secret)
    if payload is None:
        return None, _json_response(
            401, {"error": "Invalid or expired token"}, cors_headers
        )
    return payload, None


def _json_response(status_code, body, headers):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", **headers},
        "body": json.dumps(body),
    }


def _doc_to_dict(doc):
    doc["id"] = str(doc["_id"])
    del doc["_id"]
    return doc


def _parse_multipart(body_bytes, content_type):
    """Parse multipart/form-data. Returns (fields_dict, files_dict)."""
    msg_bytes = f"Content-Type: {content_type}\r\n\r\n".encode() + body_bytes
    msg = email.message_from_bytes(msg_bytes, policy=email.policy.compat32)

    fields = {}
    files = {}

    for part in msg.get_payload():
        if isinstance(part, str):
            continue

        cd = part.get("Content-Disposition", "")
        params = {}
        for item in cd.split(";")[1:]:
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                params[k.strip()] = v.strip().strip('"')

        name = params.get("name", "")
        filename = params.get("filename", "")
        payload = part.get_payload(decode=True)

        if filename:
            files.setdefault(name, []).append(
                {
                    "filename": filename,
                    "data": payload,
                    "content_type": part.get_content_type(),
                }
            )
        elif name:
            fields[name] = (
                payload.decode("utf-8", errors="replace") if payload else ""
            )

    return fields, files


def _upload_to_s3(data, filename, content_type):
    """Upload file to S3 and return the uploads path string."""
    bucket = UPLOADS_BUCKET
    if not bucket:
        return f"uploads/{filename}"
    key = f"uploads/{filename}"
    s3 = boto3.client("s3")
    s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
    return key


def _parse_property_body(event):
    """Parse request body (JSON or multipart). Returns (property_data_dict, image_paths_list)."""
    headers = event.get("headers") or {}
    content_type = (
        headers.get("Content-Type") or headers.get("content-type") or "application/json"
    )
    body_raw = event.get("body") or ""

    if event.get("isBase64Encoded") and body_raw:
        body_bytes = base64.b64decode(body_raw)
    else:
        body_bytes = (
            body_raw.encode("utf-8") if isinstance(body_raw, str) else body_raw
        )

    image_paths = []

    if "multipart/form-data" in content_type:
        fields, files = _parse_multipart(body_bytes, content_type)
        try:
            property_data = json.loads(fields.get("propertyData", "{}"))
        except json.JSONDecodeError:
            property_data = {}
        for file_list in files.values():
            for f in file_list:
                path = _upload_to_s3(f["data"], f["filename"], f["content_type"])
                image_paths.append(path)
    else:
        try:
            property_data = json.loads(body_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            property_data = {}

    return property_data, image_paths


def lambda_handler(event, context):
    origin = (event.get("headers") or {}).get("origin", "")
    cors_headers = _cors_headers(origin)

    http_method = event.get("httpMethod", "")
    proxy = (event.get("pathParameters") or {}).get("proxy", "")
    proxy_parts = proxy.split("/")

    if http_method == "OPTIONS":
        return {"statusCode": 200, "headers": cors_headers, "body": ""}

    try:
        mongodb_uri = os.environ.get("MONGODB_URI")
        if not mongodb_uri:
            return _json_response(500, {"error": "MONGODB_URI not set"}, cors_headers)

        client = MongoClient(mongodb_uri)
        db = client[DATABASE_NAME]
        props_coll = db[PROPERTIES_COLLECTION]

        try:
            if http_method == "GET" and proxy == "properties":
                return _list_properties(event, props_coll, cors_headers)

            elif (
                http_method == "GET"
                and proxy_parts[0] == "property"
                and len(proxy_parts) == 2
            ):
                return _get_property(proxy_parts[1], props_coll, cors_headers)

            elif http_method == "POST" and proxy == "add-property":
                _, err = _require_auth(event, cors_headers)
                if err:
                    return err
                return _add_property(event, props_coll, cors_headers)

            elif (
                http_method == "PUT"
                and proxy_parts[0] == "modify-property"
                and len(proxy_parts) == 2
            ):
                _, err = _require_auth(event, cors_headers)
                if err:
                    return err
                return _modify_property(proxy_parts[1], event, props_coll, cors_headers)

            elif (
                http_method == "DELETE"
                and proxy_parts[0] == "delete"
                and len(proxy_parts) == 2
            ):
                _, err = _require_auth(event, cors_headers)
                if err:
                    return err
                return _delete_property(proxy_parts[1], props_coll, cors_headers)

            else:
                return _json_response(404, {"error": "Not found"}, cors_headers)
        finally:
            client.close()

    except Exception as e:
        return _json_response(500, {"error": str(e)}, cors_headers)


def _list_properties(event, props_coll, cors_headers):
    query_params = event.get("queryStringParameters") or {}
    query = {}

    address = query_params.get("address")
    if address:
        query["address"] = {"$regex": address, "$options": "i"}

    sort_by = query_params.get("sortBy", "createdAt")
    order = query_params.get("order", "desc")

    if sort_by not in ALLOWED_SORT_FIELDS:
        sort_by = "createdAt"
    direction = 1 if order == "asc" else -1

    properties = [
        _doc_to_dict(p) for p in props_coll.find(query).sort(sort_by, direction)
    ]
    return _json_response(200, {"properties": properties}, cors_headers)


def _get_property(property_id, props_coll, cors_headers):
    try:
        obj_id = ObjectId(property_id)
    except Exception:
        return _json_response(400, {"error": "Invalid property ID"}, cors_headers)
    prop = props_coll.find_one({"_id": obj_id})
    if not prop:
        return _json_response(404, {"error": "Property not found"}, cors_headers)
    return _json_response(200, {"property": _doc_to_dict(prop)}, cors_headers)


def _add_property(event, props_coll, cors_headers):
    property_data, image_paths = _parse_property_body(event)

    existing_images = property_data.get("images", [])
    if not isinstance(existing_images, list):
        existing_images = []
    property_data["images"] = existing_images + image_paths
    property_data["createdAt"] = int(time.time() * 1000)

    result = props_coll.insert_one(property_data)
    property_data.pop("_id", None)
    property_data["id"] = str(result.inserted_id)

    return _json_response(
        201, {"message": "Property added", "property": property_data}, cors_headers
    )


def _modify_property(property_id, event, props_coll, cors_headers):
    try:
        obj_id = ObjectId(property_id)
    except Exception:
        return _json_response(400, {"error": "Invalid property ID"}, cors_headers)

    property_data, image_paths = _parse_property_body(event)

    if image_paths:
        existing_images = property_data.get("images", [])
        if not isinstance(existing_images, list):
            existing_images = []
        property_data["images"] = existing_images + image_paths

    property_data["updatedAt"] = int(time.time() * 1000)
    property_data.pop("_id", None)
    property_data.pop("id", None)

    result = props_coll.update_one({"_id": obj_id}, {"$set": property_data})
    if result.matched_count == 0:
        return _json_response(404, {"error": "Property not found"}, cors_headers)
    return _json_response(200, {"message": "Property updated"}, cors_headers)


def _delete_property(property_id, props_coll, cors_headers):
    try:
        obj_id = ObjectId(property_id)
    except Exception:
        return _json_response(400, {"error": "Invalid property ID"}, cors_headers)
    result = props_coll.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        return _json_response(404, {"error": "Property not found"}, cors_headers)
    return _json_response(200, {"message": "Property deleted"}, cors_headers)
