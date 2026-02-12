import json
import os
from pymongo import MongoClient
from bson import ObjectId

# MongoDB settings
DATABASE_NAME = "vinyl_collection"
USERS_COLLECTION = "users"

def lambda_handler(event, context):
    """
    Lambda function to retrieve users from MongoDB.
    Supports ?user=username parameter to get a specific user.
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
        users_collection = db[USERS_COLLECTION]
        
        # Get query parameters
        query_params = event.get('queryStringParameters', {}) or {}
        
        # Build MongoDB query
        query = {}
        if query_params.get('user'):
            query['username'] = query_params['user']
            # Get single user
            user = users_collection.find_one(query)
            client.close()
            
            if user:
                # Convert ObjectId to string
                user['id'] = str(user['_id'])
                del user['_id']
                
                return {
                    'statusCode': 200,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': cors_origin
                    },
                    'body': json.dumps({'user': user})
                }
            else:
                return {
                    'statusCode': 404,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': cors_origin
                    },
                    'body': json.dumps({
                        'error': f"User '{query_params['user']}' not found"
                    })
                }
        
        # Get all users
        users_cursor = users_collection.find({})
        users = []
        for user in users_cursor:
            # Convert ObjectId to string
            user['id'] = str(user['_id'])
            del user['_id']
            users.append(user)
        client.close()
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': cors_origin
            },
            'body': json.dumps({
                'users': users,
                'count': len(users)
            })
        }
    
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': cors_origin
            },
            'body': json.dumps({
                'error': str(e)
            })
        }