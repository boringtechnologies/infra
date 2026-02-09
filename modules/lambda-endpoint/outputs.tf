output "lambda_arn" {
  value = aws_lambda_function.lambda.arn
}

output "integration_id" {
  value = aws_api_gateway_integration.post.id
}

output "api_endpoint" {
  value = "https://${var.rest_api_id}.execute-api.${var.region}.amazonaws.com/prod/${var.path_part}"
}