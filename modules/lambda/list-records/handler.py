import json
import os
from pymongo import MongoClient
from bson import ObjectId

# MongoDB settings
DATABASE_NAME = "vinyl_collection"
RECORDS_COLLECTION = "records"

def lambda_handler(event, context):
    """
    Lambda function to retrieve vinyl records from MongoDB.
    Supports ?record=<catalog_number> parameter to get a specific record.
    """
    
    origin = event.get("headers", {}).get("origin", "")
    allowed_origins = ["https://records.boring.tech", "http://localhost:3000"]
    cors_origin = origin if origin in allowed_origins else "null"

    # Preflight OPTIONS request
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
        # Get MongoDB URI from environment variable
        mongodb_uri = os.environ.get("MONGODB_URI")
        
        if not mongodb_uri:
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': cors_origin
                },
                'body': json.dumps({
                    'error': 'MONGODB_URI environment variable not set'
                })
            }
        
        # Connect to MongoDB
        client = MongoClient(mongodb_uri)
        db = client[DATABASE_NAME]
        records_collection = db[RECORDS_COLLECTION]
        
        # Get query parameters
        query_params = event.get('queryStringParameters', {}) or {}
        
        # Build MongoDB query
        query = {}
        
        # Check for specific record parameter
        if query_params.get('record'):
            query['catalog_number'] = query_params['record']
            # Get single record
            record = records_collection.find_one(query)
            client.close()
            
            if record:
                # Convert ObjectId to string
                record['id'] = str(record['_id'])
                del record['_id']
                
                return {
                    'statusCode': 200,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': cors_origin,
                        'Access-Control-Allow-Credentials': 'true'
                    },
                    'body': json.dumps({'record': record})
                }
            else:
                return {
                    'statusCode': 404,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': cors_origin,
                        'Access-Control-Allow-Credentials': 'true'
                    },
                    'body': json.dumps({
                        'error': f"Record '{query_params['record']}' not found"
                    })
                }
        
        # Optional filters for listing all records
        if query_params.get('artist'):
            query['artist'] = {'$regex': query_params['artist'], '$options': 'i'}
        if query_params.get('needs_review'):
            query['needs_review'] = query_params['needs_review']
        
        # Retrieve all records matching query
        records_cursor = records_collection.find(query)
        records = []
        for record in records_cursor:
            # Convert ObjectId to string
            record['id'] = str(record['_id'])
            del record['_id']
            records.append(record)
        client.close()
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': cors_origin,
                'Access-Control-Allow-Credentials': 'true'
            },
            'body': json.dumps({
                'records': records,
                'count': len(records)
            })
        }
    
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': cors_origin,
                'Access-Control-Allow-Credentials': 'true'
            },
            'body': json.dumps({
                'error': str(e)
            })
        }