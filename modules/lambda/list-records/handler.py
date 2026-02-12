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
    
    origin = event.get("headers", {}).get("origin", "")  # Note lowercase in API Gateway
    allowed_origins = ["https://theskillplace.com", "http://localhost:3000"]
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
    
    try:
        # Get MongoDB URI from environment variable
        mongodb_uri = os.environ.get("MONGODB_URI")
        
        if not mongodb_uri:
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
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
            record = records_collection.find_one(query, {'_id': 0})
            client.close()
            
            if record:
                return {
                    'statusCode': 200,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({'record': record})
                }
            else:
                return {
                    'statusCode': 404,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
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
        records = list(records_collection.find(query, {'_id': 0}))
        client.close()
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
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
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': str(e)
            })
        }