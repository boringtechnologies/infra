import base64
import hashlib
import hmac
import json
import os
import time

import bcrypt
from bson import ObjectId
from pymongo import MongoClient

DATABASE_NAME = os.environ.get("FALCON_DB_NAME", "falconmdpa")
USERS_COLLECTION = "users"

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


def _create_jwt(payload, secret, expires_in=86400):
    header_b64 = (
        base64.urlsafe_b64encode(
            json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode()
        )
        .rstrip(b"=")
        .decode()
    )

    payload_copy = dict(payload)
    payload_copy["exp"] = int(time.time()) + expires_in
    payload_copy["iat"] = int(time.time())
    payload_b64 = (
        base64.urlsafe_b64encode(
            json.dumps(payload_copy, separators=(",", ":")).encode()
        )
        .rstrip(b"=")
        .decode()
    )

    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()

    return f"{header_b64}.{payload_b64}.{sig_b64}"


def _json_response(status_code, body, headers):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", **headers},
        "body": json.dumps(body),
    }


def lambda_handler(event, context):
    origin = (event.get("headers") or {}).get("origin", "")
    cors_headers = _cors_headers(origin)

    http_method = event.get("httpMethod", "")
    proxy = (event.get("pathParameters") or {}).get("proxy", "")

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
        users_coll = db[USERS_COLLECTION]

        try:
            if http_method == "POST" and proxy == "register":
                return _register(body, users_coll, cors_headers)
            elif http_method == "POST" and proxy == "login":
                return _login(body, users_coll, cors_headers)
            else:
                return _json_response(404, {"error": "Not found"}, cors_headers)
        finally:
            client.close()

    except Exception as e:
        return _json_response(500, {"error": str(e)}, cors_headers)


def _register(body, users_coll, cors_headers):
    email_addr = body.get("email", "").strip().lower()
    username = body.get("username", "").strip()
    password = body.get("password", "")

    if not email_addr or not username or not password:
        return _json_response(
            400,
            {"error": "email, username, and password are required"},
            cors_headers,
        )

    if users_coll.find_one({"$or": [{"email": email_addr}, {"username": username}]}):
        return _json_response(409, {"error": "User already exists"}, cors_headers)

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

    user_doc = {
        "email": email_addr,
        "username": username,
        "password": hashed,
        "createdAt": int(time.time() * 1000),
    }

    result = users_coll.insert_one(user_doc)
    user_id = str(result.inserted_id)

    jwt_secret = os.environ.get("JWT_SECRET", "")
    token = _create_jwt(
        {"id": user_id, "email": email_addr, "username": username}, jwt_secret
    )

    return _json_response(
        201,
        {
            "message": "User registered successfully",
            "token": token,
            "user": {"id": user_id, "email": email_addr, "username": username},
        },
        cors_headers,
    )


def _login(body, users_coll, cors_headers):
    email_addr = body.get("email", "").strip().lower()
    username = body.get("username", "").strip()
    password = body.get("password", "")

    if not password or (not email_addr and not username):
        return _json_response(
            400,
            {"error": "email or username, and password are required"},
            cors_headers,
        )

    query = {}
    if email_addr:
        query["email"] = email_addr
    else:
        query["username"] = username

    user = users_coll.find_one(query)

    if not user or not bcrypt.checkpw(
        password.encode("utf-8"), user["password"].encode("utf-8")
    ):
        return _json_response(401, {"error": "Invalid credentials"}, cors_headers)

    user_id = str(user["_id"])
    jwt_secret = os.environ.get("JWT_SECRET", "")
    token = _create_jwt(
        {
            "id": user_id,
            "email": user.get("email", ""),
            "username": user.get("username", ""),
        },
        jwt_secret,
    )

    return _json_response(
        200,
        {
            "message": "Login successful",
            "token": token,
            "user": {
                "id": user_id,
                "email": user.get("email", ""),
                "username": user.get("username", ""),
            },
        },
        cors_headers,
    )
