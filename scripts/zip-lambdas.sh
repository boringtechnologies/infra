#!/bin/bash
set -e

BASE_DIR="../modules/lambda"

for LAMBDA_DIR in "$BASE_DIR"/*/; do
    DIR_NAME=$(basename "$LAMBDA_DIR")
    TARGET_ZIP="lambda.zip"  # just name it in the current folder

    echo "Building zip for Lambda '$DIR_NAME' -> $LAMBDA_DIR$TARGET_ZIP"

    # Remove old zip if it exists
    rm -f "$LAMBDA_DIR$TARGET_ZIP"

    # Change into the Lambda folder and zip handler.py into lambda.zip
    (cd "$LAMBDA_DIR" && zip -j "$TARGET_ZIP" handler.py)

    echo "Created $LAMBDA_DIR$TARGET_ZIP for $DIR_NAME"
done

echo "All Lambda zips created successfully!"