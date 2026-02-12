import json
import os
import math
import re
from pymongo import MongoClient
from bson.objectid import ObjectId


# MongoDB settings
DATABASE_NAME = "vinyl_collection"
RECORDS_COLLECTION = "records"


DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 200  # safety cap


ALLOWED_SORT_FIELDS = {
    "artist": "artist",
    "title": "title",
    "catalog_number": "catalog_number",
    "year": "year",
    "created_at": "created_at",
    "updated_at": "updated_at",
    "_id": "_id",
}

USERID_FIELD_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")  # adjust if needed

def _apply_user_like_dislike_filters(query, query_params):
    """
    Supports dynamic query params like:
      ?<userId>_like=<value>
      ?<userId>_dislike=<value>

    Adds regex match filters on fields named "<userId>_like" / "<userId>_dislike".
    """
    for key, value in (query_params or {}).items():
        if value is None:
            continue

        if not (key.endswith("_like") or key.endswith("_dislike")):
            continue

        # Extract userId from "<userId>_like" / "<userId>_dislike"
        user_id = key.rsplit("_", 1)[0]  # splits off "like"/"dislike"

        # Prevent Mongo field-path tricks
        if not USERID_FIELD_RE.match(user_id):
            continue

        # Extra hardening: block dot/$ even if regex changed later
        if "." in user_id or "$" in user_id:
            continue

        # Optional: ignore empty strings
        s = str(value).strip()
        if not s:
            continue

        # Add dynamic field filter
        query[key] = {"$regex": s, "$options": "i"}

    return query


def _to_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_sort(query_params):
    """
    Parse sort parameters from query string.
    Returns: (field_name, direction)
    """
    sort_key = (query_params.get("sort") or "_id").strip()
    order = (query_params.get("order") or "desc").strip().lower()

    field = ALLOWED_SORT_FIELDS.get(sort_key, "_id")
    direction = 1 if order == "asc" else -1
    return field, direction


def _build_cursor_query(query, cursor, sort_field, direction):
    """
    Add cursor-based filtering to the existing query.
    For cursor pagination, we need to filter records that come after the cursor value.
    """
    if not cursor:
        return query

    try:
        # Cursor format: "field_value|_id"
        # This ensures uniqueness even if sort field has duplicates
        parts = cursor.split("|", 1)
        if len(parts) != 2:
            return query

        field_value, id_str = parts
        cursor_id = ObjectId(id_str)

        # Build range query based on sort direction
        cursor_query = query.copy()

        if direction == 1:  # ascending
            # Get records where sort_field > cursor_value OR (sort_field == cursor_value AND _id > cursor_id)
            cursor_query["$or"] = [
                {sort_field: {"$gt": field_value}},
                {sort_field: field_value, "_id": {"$gt": cursor_id}}
            ]
        else:  # descending
            # Get records where sort_field < cursor_value OR (sort_field == cursor_value AND _id < cursor_id)
            cursor_query["$or"] = [
                {sort_field: {"$lt": field_value}},
                {sort_field: field_value, "_id": {"$lt": cursor_id}}
            ]

        return cursor_query

    except Exception:
        # If cursor parsing fails, return original query
        return query


def _generate_cursor(record, sort_field):
    """
    Generate a cursor token from a record.
    Format: "field_value|_id"
    """
    field_value = record.get(sort_field, "")
    record_id = record.get("_id")
    return f"{field_value}|{record_id}"


def lambda_handler(event, context):
    """
    Lambda function to retrieve vinyl records from MongoDB.
    Supports:
      - ?record=<catalog_number> : get a specific record
      - Listing filters: ?artist=<partial>&title=<partial>&needs_review=<...>
      - Cursor-based pagination: ?cursor=<token>&per_page=50
      - Sorting: ?sort=artist&order=asc
    """

    origin = event.get("headers", {}).get("origin", "")
    allowed_origins = ["https://records.boring.tech", "http://localhost:3000"]
    cors_origin = origin if origin in allowed_origins else "null"

    http_method = event.get("httpMethod", "")
    if http_method == "OPTIONS":
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

    try:
        mongodb_uri = os.environ.get("MONGODB_URI")
        if not mongodb_uri:
            return {
                "statusCode": 500,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": cors_origin
                },
                "body": json.dumps({"error": "MONGODB_URI environment variable not set"})
            }

        client = MongoClient(mongodb_uri)
        db = client[DATABASE_NAME]
        records_collection = db[RECORDS_COLLECTION]

        query_params = event.get("queryStringParameters", {}) or {}

        # Single record lookup (unchanged)
        if query_params.get("record"):
            catno = query_params["record"]
            record = records_collection.find_one({"catalog_number": catno})
            client.close()

            if record:
                record["id"] = str(record["_id"])
                del record["_id"]
                return {
                    "statusCode": 200,
                    "headers": {
                        "Content-Type": "application/json",
                        "Access-Control-Allow-Origin": cors_origin,
                        "Access-Control-Allow-Credentials": "true"
                    },
                    "body": json.dumps({"record": record})
                }

            return {
                "statusCode": 404,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": cors_origin,
                    "Access-Control-Allow-Credentials": "true"
                },
                "body": json.dumps({"error": f"Record \'{catno}\' not found"})
            }

        # -----------------------
        # Build query (filters)
        # -----------------------
        query = {}

        if query_params.get("artist"):
            query["artist"] = {"$regex": query_params["artist"], "$options": "i"}

        if query_params.get("title"):
            query["title"] = {"$regex": query_params["title"], "$options": "i"}

        if query_params.get("catalog_number"):
            query["catalog_number"] = {"$regex": query_params["catalog_number"], "$options": "i"}

        if query_params.get("needs_review") is not None:
            nr = str(query_params["needs_review"]).strip().lower()
            if nr in ("true", "1", "yes"):
                query["needs_review"] = True
            elif nr in ("false", "0", "no"):
                query["needs_review"] = False

        query = _apply_user_like_dislike_filters(query, query_params)

        # -----------------------
        # Cursor-based pagination
        # -----------------------
        cursor = query_params.get("cursor")
        per_page = _to_int(query_params.get("per_page"), DEFAULT_PER_PAGE)

        if per_page < 1:
            per_page = DEFAULT_PER_PAGE
        if per_page > MAX_PER_PAGE:
            per_page = MAX_PER_PAGE

        # Parse sort parameters
        sort_field, direction = _parse_sort(query_params)

        # Apply cursor filtering
        cursor_query = _build_cursor_query(query, cursor, sort_field, direction)

        # Fetch one extra record to determine if there are more results
        limit = per_page + 1

        cursor_db = (
            records_collection
            .find(cursor_query)
            .sort([(sort_field, direction), ("_id", direction)])  # Always include _id for stable sorting
            .limit(limit)
        )

        records = []
        for r in cursor_db:
            records.append(r)

        client.close()

        # Check if there are more results
        has_more = len(records) > per_page
        if has_more:
            records = records[:per_page]  # Remove the extra record

        # Generate next cursor from the last record
        next_cursor = None
        if has_more and records:
            last_record = records[-1]
            next_cursor = _generate_cursor(last_record, sort_field)

        # Convert ObjectId to string for JSON serialization
        for r in records:
            r["id"] = str(r["_id"])
            del r["_id"]

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": cors_origin,
                "Access-Control-Allow-Credentials": "true"
            },
            "body": json.dumps({
                "records": records,
                "count": len(records),
                "pagination": {
                    "per_page": per_page,
                    "next_cursor": next_cursor,
                    "has_more": has_more
                }
            })
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": cors_origin,
                "Access-Control-Allow-Credentials": "true"
            },
            "body": json.dumps({"error": str(e)})
        }
