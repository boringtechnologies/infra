output "lambda_arn" {
  value = aws_lambda_function.lambda.arn
}

output "parent_resource_id" {
  value = aws_api_gateway_resource.parent.id
}

output "proxy_resource_id" {
  value = aws_api_gateway_resource.proxy.id
}
