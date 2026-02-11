import json
import os
from pymongo import MongoClient

# MongoDB settings
DATABASE_NAME = "vinyl_collection"
RECORDS_COLLECTION = "records"

def lambda_handler(event, context):
    """
    Lambda function to update vinyl records in MongoDB via POST.
    Requires catalog_number to identify the record.
    Updates any fields provided in the request body.
    Supports user-specific fields: {user_id}_like, {user_id}_dislike, {user_id}_favorite
    """
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
        
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': 'Invalid JSON in request body'
                })
            }
        
        # Validate that catalog_number is provided
        if 'catalog_number' not in body:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': 'catalog_number is required to identify the record'
                })
            }
        
        catalog_number = body.pop('catalog_number')
        
        # Check if there are fields to update
        if not body:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': 'No fields provided to update'
                })
            }
        
        # Convert string booleans to actual booleans for user-specific fields
        for key in list(body.keys()):
            # Handle {user_id}_like, {user_id}_dislike, {user_id}_favorite
            if key.endswith('_like') or key.endswith('_dislike') or key.endswith('_favorite'):
                value = body[key]
                if isinstance(value, str):
                    if value.lower() == 'true':
                        body[key] = True
                    elif value.lower() == 'false':
                        body[key] = False
                    # Otherwise keep as-is if it's already a boolean
        
        # Connect to MongoDB
        client = MongoClient(mongodb_uri)
        db = client[DATABASE_NAME]
        records_collection = db[RECORDS_COLLECTION]
        
        # Update the record
        result = records_collection.update_one(
            {'catalog_number': catalog_number},
            {'$set': body}
        )
        
        client.close()
        
        # Check if record was found and updated
        if result.matched_count == 0:
            return {
                'statusCode': 404,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': f"Record with catalog_number '{catalog_number}' not found"
                })
            }
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'message': 'Record updated successfully',
                'catalog_number': catalog_number,
                'modified_count': result.modified_count,
                'updated_fields': list(body.keys())
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