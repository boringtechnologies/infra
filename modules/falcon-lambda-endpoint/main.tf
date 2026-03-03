resource "aws_lambda_function" "lambda" {
  function_name    = var.lambda_name
  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)
  handler          = var.handler
  runtime          = var.runtime
  role             = var.role_arn
  layers           = var.layers
  timeout          = var.timeout

  environment {
    variables = var.environment_variables
  }

  tags = {
    Project   = "boring"
    ManagedBy = "Terraform"
  }
}

# Top-level resource (e.g., /user, /banner, /property)
resource "aws_api_gateway_resource" "parent" {
  rest_api_id = var.rest_api_id
  parent_id   = var.parent_resource_id
  path_part   = var.path_part
}

# Greedy proxy resource for all sub-paths (e.g., /user/{proxy+})
resource "aws_api_gateway_resource" "proxy" {
  rest_api_id = var.rest_api_id
  parent_id   = aws_api_gateway_resource.parent.id
  path_part   = "{proxy+}"
}

# ANY method on proxy resource (handles GET, POST, PUT, DELETE, PATCH, etc.)
resource "aws_api_gateway_method" "proxy_any" {
  rest_api_id   = var.rest_api_id
  resource_id   = aws_api_gateway_resource.proxy.id
  http_method   = "ANY"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "proxy_any" {
  rest_api_id             = var.rest_api_id
  resource_id             = aws_api_gateway_resource.proxy.id
  http_method             = aws_api_gateway_method.proxy_any.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.lambda.invoke_arn
}

# Lambda Permission for API Gateway
resource "aws_lambda_permission" "apigw_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.execution_arn}/*/*"
}
