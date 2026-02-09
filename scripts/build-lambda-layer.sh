#!/bin/bash
set -e

LAYER_NAME=$1
REQUIREMENTS_FILE=$2
OUTPUT_DIR="./lambda-layers/${LAYER_NAME}"

echo "Building Lambda layer: ${LAYER_NAME}"

# Clean up only the python directory and zip, not requirements.txt
rm -rf ${OUTPUT_DIR}/python
rm -f ./lambda-layers/${LAYER_NAME}.zip
mkdir -p ${OUTPUT_DIR}/python

# Build in Docker to match Lambda environment
docker run --rm \
  --entrypoint /bin/bash \
  -v $(pwd)/${REQUIREMENTS_FILE}:/requirements.txt \
  -v $(pwd)/${OUTPUT_DIR}/python:/output \
  public.ecr.aws/lambda/python:3.13 \
  -c "pip install -r /requirements.txt -t /output"

# Zip it
cd ${OUTPUT_DIR}
zip -r ../${LAYER_NAME}.zip python/
cd ../../..

echo "Layer built: ./lambda-layers/${LAYER_NAME}.zip"
