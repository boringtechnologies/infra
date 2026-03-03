resource "aws_api_gateway_rest_api" "boring_api" {
  name        = "boring-api"
  description = "REST API for boring Lambdas"

  binary_media_types = ["multipart/form-data", "image/*", "application/octet-stream"]

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}