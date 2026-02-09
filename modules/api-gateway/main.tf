resource "aws_api_gateway_rest_api" "boring_api" {
  name        = "boring-api"
  description = "REST API for boring Lambdas"
  endpoint_configuration {
    types = ["REGIONAL"]
  }
}