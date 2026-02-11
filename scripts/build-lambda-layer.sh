#!/bin/bash
set -e

LAYER_NAME=$1
REQUIREMENTS_FILE=$2
OUTPUT_DIR="./lambda-layers/${LAYER_NAME}"

echo "Building Lambda layer: ${LAYER_NAME}"

# Validate that requirements file exists and is a file
if [ ! -f "${REQUIREMENTS_FILE}" ]; then
    echo "ERROR: Requirements file '${REQUIREMENTS_FILE}' not found or is not a file"
    exit 1
fi

# Clean up only the python directory and zip, not requirements.txt
rm -rf ${OUTPUT_DIR}/python
rm -f ./lambda-layers/${LAYER_NAME}.zip
mkdir -p ${OUTPUT_DIR}/python

# Get absolute path for requirements file
REQUIREMENTS_ABS=$(cd "$(dirname "${REQUIREMENTS_FILE}")" && pwd)/$(basename "${REQUIREMENTS_FILE}")

# Build in Docker to match Lambda environment
docker run --rm \
  --entrypoint /bin/bash \
  -v ${REQUIREMENTS_ABS}:/requirements.txt:ro \
  -v $(pwd)/${OUTPUT_DIR}/python:/output \
  public.ecr.aws/lambda/python:3.13 \
  -c "pip install -r /requirements.txt -t /output"

# Zip it
cd ${OUTPUT_DIR}
zip -r ../${LAYER_NAME}.zip python/
cd ../../..

echo "Layer built: ./lambda-layers/${LAYER_NAME}.zip"