# Lambda Execution Role
resource "aws_iam_role" "lambda_exec_role" {
  name = "boring_lambda_exec_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Effect = "Allow"
      Sid    = ""
    }]
  })
}

# Captioning Role
resource "aws_iam_role" "captioning_role" {
  name = "boring_captioning_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        AWS = aws_iam_role.lambda_exec_role.arn
      }
      Action = [
        "sts:AssumeRole",
        "sts:TagSession"
      ]
    }]
  })
}

resource "aws_iam_policy" "captioning_policy" {
  name        = "boring_captioning_policy"
  description = "Permissions for captioning role"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "transcribe:StartStreamTranscription",
        "transcribe:StartStreamTranscriptionWebSocket",
        "transcribe:StartTranscriptionJob",
        "transcribe:GetTranscriptionJob",
        "transcribe:ListTranscriptionJobs",
        "transcribe:TagResource",
        "transcribe:UntagResource"
      ]
      Resource = "*"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "captioning_attach" {
  role       = aws_iam_role.captioning_role.name
  policy_arn = aws_iam_policy.captioning_policy.arn
}

# Policy to allow Lambda to assume Captioning Role
resource "aws_iam_policy" "lambda_captioning_assume" {
  name = "boring_lambda_captioning_assume"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "sts:AssumeRole",
        "sts:TagSession"
      ]
      Resource = aws_iam_role.captioning_role.arn
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_captioning_attach" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.lambda_captioning_assume.arn
}

# Attach basic execution policy
resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}
