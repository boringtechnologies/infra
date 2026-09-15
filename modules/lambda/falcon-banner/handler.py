import base64
import hashlib
import hmac
import json
import os
import time

from bson import ObjectId
from pymongo import MongoClient

DATABASE_NAME = os.environ.get("FALCON_DB_NAME", "falconmdpa")
BANNERS_COLLECTION = "banners"

ALLOWED_ORIGINS = [
    "https://dev.falconmdpa.com",
    "https://falconmdpa.com",
    "http://localhost:3000",
]


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

        body_raw = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            body_raw = base64.b64decode(body_raw).decode("utf-8")
        try:
            body = json.loads(body_raw)
        except json.JSONDecodeError:
            body = {}

        client = MongoClient(mongodb_uri)
        db = client[DATABASE_NAME]
        banners_coll = db[BANNERS_COLLECTION]

        try:
            if http_method == "GET" and proxy == "get-all":
                return _get_all(banners_coll, cors_headers)

            elif http_method == "POST" and proxy == "add":
                _, err = _require_auth(event, cors_headers)
                if err:
                    return err
                return _add_banner(body, banners_coll, cors_headers)

            elif (
                http_method == "DELETE"
                and proxy_parts[0] == "delete"
                and len(proxy_parts) == 2
            ):
                _, err = _require_auth(event, cors_headers)
                if err:
                    return err
                return _delete_banner(proxy_parts[1], banners_coll, cors_headers)

            else:
                return _json_response(404, {"error": "Not found"}, cors_headers)
        finally:
            client.close()

    except Exception as e:
        return _json_response(500, {"error": str(e)}, cors_headers)


def _get_all(banners_coll, cors_headers):
    banners = [_doc_to_dict(b) for b in banners_coll.find({})]
    return _json_response(200, {"banners": banners}, cors_headers)


def _add_banner(body, banners_coll, cors_headers):
    if not body:
        return _json_response(
            400, {"error": "Request body is required"}, cors_headers
        )
    result = banners_coll.insert_one(body)
    body.pop("_id", None)
    body["id"] = str(result.inserted_id)
    return _json_response(
        201, {"message": "Banner added", "banner": body}, cors_headers
    )


def _delete_banner(banner_id, banners_coll, cors_headers):
    try:
        obj_id = ObjectId(banner_id)
    except Exception:
        return _json_response(400, {"error": "Invalid banner ID"}, cors_headers)
    result = banners_coll.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        return _json_response(404, {"error": "Banner not found"}, cors_headers)
    return _json_response(200, {"message": "Banner deleted"}, cors_headers)
