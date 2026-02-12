import json
import os
import math
from pymongo import MongoClient

# MongoDB settings
DATABASE_NAME = "vinyl_collection"
RECORDS_COLLECTION = "records"

DEFAULT_PAGE = 1
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

def _to_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def _parse_sort(query_params):
    # sort=artist|title|catalog_number|year|created_at|updated_at|_id
    # order=asc|desc
    sort_key = (query_params.get("sort") or "_id").strip()
    order = (query_params.get("order") or "desc").strip().lower()

    field = ALLOWED_SORT_FIELDS.get(sort_key, "_id")
    direction = 1 if order == "asc" else -1
    return [(field, direction)]

def lambda_handler(event, context):
    """
    Lambda function to retrieve vinyl records from MongoDB.
    Supports:
      - ?record=<catalog_number> : get a specific record
      - Listing filters: ?artist=<partial>&needs_review=<...>
      - Pagination: ?page=1&per_page=50
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

        # If requesting a single record by catalog number, keep old behavior (no pagination)
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
                "body": json.dumps({"error": f"Record '{catno}' not found"})
            }

        # -----------------------
        # Build query (filters)
        # -----------------------
        query = {}

        if query_params.get("artist"):
            query["artist"] = {"$regex": query_params["artist"], "$options": "i"}
            
        # NEW: title filter (partial, case-insensitive)
        if query_params.get("title"):
            query["title"] = {"$regex": query_params["title"], "$options": "i"}

        # note: your param name here is spelled "catalog_number" to match your request
        if query_params.get("catalog_number"):
            query["catalog_number"] = {"$regex": query_params["catalog_number"], "$options": "i"}

        if query_params.get("needs_review") is not None:
            # If your DB stores needs_review as boolean, consider normalizing this:
            # e.g. "true"/"false" -> True/False
            nr = str(query_params["needs_review"]).strip().lower()
            if nr in ("true", "1", "yes"):
                query["needs_review"] = True
            elif nr in ("false", "0", "no"):
                query["needs_review"] = False
            else:
                # fall back to raw value if you intentionally store strings
                query["needs_review"] = query_params["needs_review"]

        # -----------------------
        # Pagination params
        # -----------------------
        page = _to_int(query_params.get("page"), DEFAULT_PAGE)
        per_page = _to_int(query_params.get("per_page"), DEFAULT_PER_PAGE)

        if page < 1:
            page = 1
        if per_page < 1:
            per_page = DEFAULT_PER_PAGE
        if per_page > MAX_PER_PAGE:
            per_page = MAX_PER_PAGE

        skip = (page - 1) * per_page

        # Sorting
        sort_spec = _parse_sort(query_params)

        # Total count for pagination metadata
        total = records_collection.count_documents(query)
        total_pages = max(1, math.ceil(total / per_page)) if per_page else 1

        # Query page
        cursor = (
            records_collection
            .find(query)
            .sort(sort_spec)
            .skip(skip)
            .limit(per_page)
        )

        records = []
        for r in cursor:
            r["id"] = str(r["_id"])
            del r["_id"]
            records.append(r)

        client.close()

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": cors_origin,
                "Access-Control-Allow-Credentials": "true"
            },
            "body": json.dumps({
                "records": records,
                "count": len(records),  # count on this page
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
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