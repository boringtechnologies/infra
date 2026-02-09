terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.6.0"
}

# Default provider (no alias) - used by modules
provider "aws" {
  region  = var.region
  profile = var.aws_profile
}

# US East 1 provider for CloudFront certificates
provider "aws" {
  alias   = "us_east_1"
  region  = "us-east-1"
  profile = var.aws_profile
}

data "aws_caller_identity" "current" {}

# Add this - lookup your existing Route53 hosted zone
data "aws_route53_zone" "boring" {
  name         = "boring.tech"
  private_zone = false
}

# Shared API Gateway
module "api_gateway" {
  source = "./modules/api-gateway"
}

locals {
  # Define lambda configurations with env and layers
  lambda_configs = {
    "list-records" = {
      environment = "common"
      layers      = ["common"]
    }
    "update-records" = {
      environment = "common"
      layers      = ["common"]
    }
  }

  # Map layer names to ARNs
  layer_arns = {
    "stripe" = aws_lambda_layer_version.stripe.arn
    "common" = aws_lambda_layer_version.common.arn
  }

  # Environment variable sets
  env_vars_common = {
    ACCOUNT_ALIAS    = var.account_alias
    CRYPTLEX_API_KEY = var.cryptlex_api_key
    BASE_URL         = var.base_url
  }

  env_vars_dev = merge(local.env_vars_common, {
    STRIPE_SECRET_KEY        = var.stripe_secret_key_dev
    WEBHOOK_SIGNING_SECRET   = var.webhook_signing_secret_dev
    PRICE_CENTS              = tostring(var.stripe_price_cents)
    PRODUCT_ID               = var.stripe_product_id
  })

  env_vars_production = merge(local.env_vars_common, {
    STRIPE_SECRET_KEY        = var.stripe_secret_key_prod
    WEBHOOK_SIGNING_SECRET   = var.webhook_signing_secret_prod
    PRICE_CENTS              = tostring(var.stripe_price_cents)
    PRODUCT_ID               = var.stripe_product_id
  })
}

module "lambdas" {
  source   = "./modules/lambda-endpoint"
  for_each = local.lambda_configs # This loops through all lambda names

  lambda_name      = "boring-${each.key}"
  lambda_zip_path  = "./modules/lambda/${each.key}/lambda.zip"
  role_arn         = module.iam.lambda_exec_role_arn
  region           = var.region
  path_part        = each.key
  
  rest_api_id        = module.api_gateway.rest_api_id
  parent_resource_id = module.api_gateway.root_resource_id
  execution_arn      = module.api_gateway.execution_arn

  # Use configured layers
  layers = [
    for layer_name in each.value.layers : local.layer_arns[layer_name]
  ]

  # Use environment-specific variables
  environment_variables = (
    each.value.environment == "dev" ? local.env_vars_dev :
    each.value.environment == "production" ? local.env_vars_production :
    local.env_vars_common
  )
}

# API Gateway Deployment
resource "aws_api_gateway_deployment" "boring_api_deploy" {
  depends_on = [module.lambdas]

  rest_api_id = module.api_gateway.rest_api_id

  lifecycle {
    create_before_destroy = true
  }
}

# API Gateway Stage
resource "aws_api_gateway_stage" "prod" {
  rest_api_id   = module.api_gateway.rest_api_id
  stage_name    = "prod"
  deployment_id = aws_api_gateway_deployment.boring_api_deploy.id
}

# API Gateway Custom Domain
resource "aws_api_gateway_domain_name" "api" {
  domain_name              = "api.boring.com"
  regional_certificate_arn = aws_acm_certificate_validation.wildcard.certificate_arn

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = {
    Name      = "boring API Domain"
    Project   = "boring"
    ManagedBy = "Terraform"
  }
}

# Base Path Mapping - maps the domain to your API Gateway stage
resource "aws_api_gateway_base_path_mapping" "api" {
  api_id      = module.api_gateway.rest_api_id
  stage_name  = aws_api_gateway_stage.prod.stage_name
  domain_name = aws_api_gateway_domain_name.api.domain_name
}

# Route53 A Record for api.boring.com
resource "aws_route53_record" "api" {
  zone_id = data.aws_route53_zone.boring.zone_id
  name    = "api.boring.com"
  type    = "A"

  alias {
    name                   = aws_api_gateway_domain_name.api.regional_domain_name
    zone_id                = aws_api_gateway_domain_name.api.regional_zone_id
    evaluate_target_health = false
  }
}

# Output the custom domain URL
output "api_custom_domain" {
  value = "https://${aws_api_gateway_domain_name.api.domain_name}"
}

# This automatically creates outputs for ALL lambdas
output "lambda_endpoints" {
  value = {
    for name in keys(local.lambda_configs) :
    name => "https://${module.api_gateway.api_id}.execute-api.${var.region}.amazonaws.com/${aws_api_gateway_stage.prod.stage_name}/${name}"
  }
}


# Certificate for all *.boring.com sites (if using custom domains)
resource "aws_acm_certificate" "boring_wildcard" {
  provider          = aws.us_east_1
  domain_name       = "*.boring.com"
  subject_alternative_names = [
    "boring.com",
    "*.dev.boring.com"
  ]
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name      = "boring Wildcard Certificate"
    Project   = "boring"
    ManagedBy = "Terraform"
  }
}

# DNS validation for wildcard certificate
resource "aws_route53_record" "wildcard_validation" {
  for_each = {
    for dvo in aws_acm_certificate.boring_wildcard.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = data.aws_route53_zone.boring.zone_id
}

resource "aws_acm_certificate_validation" "wildcard" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.boring_wildcard.arn
  validation_record_fqdns = [for record in aws_route53_record.wildcard_validation : record.fqdn]
}

# Define all your NextJS sites with pipeline config
locals {
  nextjs_sites = {
    boring-web = { 
      domain_name   = "boring.tech"
      github_repo   = "boringtechnologies/boring-web"
      github_branch = "prod"
      enable_cicd   = true
      basic_auth    = {
        enabled = false
      }
    }
    psych-web = { 
      domain_name   = "boringpsych.com"
      github_repo   = "boringtechnologies/psych-web"
      github_branch = "prod"
      enable_cicd   = true
      basic_auth    = {
        enabled = false
      }
    }
    bca-web = { 
      domain_name   = "boringmd.org"
      github_repo   = "boringtechnologies/bca-web"
      github_branch = "prod"
      enable_cicd   = true
      basic_auth    = {
        enabled = false
      }
    }
    medspa-web = { 
      domain_name   = "jouvencemedicalspa.com"
      github_repo   = "boring-dev/portal"
      github_branch = "prod"
      enable_cicd   = true
      basic_auth    = {
        enabled  = false
      }
    }
    docs = {
      domain_name   = "docs.boring.tech"
      github_repo   = "boring-dev/docs"
      github_branch = "prod"
      enable_cicd   = true
      basic_auth    = {
        enabled = false
      }
    }
    records = {
      domain_name   = "records.boring.tech"
      github_repo   = ""
      github_branch = ""
      enable_cicd   = false
      basic_auth    = {
        enabled = false
      }
    }
  }
}

# Create all NextJS sites
module "nextjs_sites" {
  source   = "./modules/nextjs-static-site"
  for_each = local.nextjs_sites

  bucket_name         = "boring-${each.key}"
  domain_name         = each.value.domain_name
  acm_certificate_arn = aws_acm_certificate_validation.wildcard.certificate_arn
  route53_zone_id     = data.aws_route53_zone.boring.zone_id
  price_class         = "PriceClass_100"

  # Add basic auth configuration
  basic_auth_enabled  = each.value.basic_auth.enabled
  basic_auth_username = try(each.value.basic_auth.username, "")
  basic_auth_password = try(each.value.basic_auth.password, "")
}

# Output all site URLs
output "nextjs_sites" {
  value = {
    for key, site in module.nextjs_sites :
    key => {
      url                = site.website_url
      bucket_name        = site.bucket_name
      cloudfront_id      = site.cloudfront_id
      cloudfront_domain  = site.cloudfront_domain_name
    }
  }
}

# CodeStar connection to GitHub (one-time setup)
resource "aws_codestarconnections_connection" "github" {
  name          = "boring-github"
  provider_type = "GitHub"
}

# S3 bucket for pipeline artifacts
resource "aws_s3_bucket" "pipeline_artifacts" {
  bucket = "boring-pipeline-artifacts"
}

resource "aws_s3_bucket_public_access_block" "pipeline_artifacts" {
  bucket = aws_s3_bucket.pipeline_artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Create pipelines for all NextJS sites
module "nextjs_pipelines" {
  source   = "./modules/nextjs-pipeline"
  for_each = { for k, v in local.nextjs_sites : k => v if v.enable_cicd }

  project_name            = "boring-${each.key}"
  github_repo             = each.value.github_repo
  github_branch           = each.value.github_branch
  s3_bucket               = module.nextjs_sites[each.key].bucket_name
  codestar_connection_arn = aws_codestarconnections_connection.github.arn
  artifact_bucket         = aws_s3_bucket.pipeline_artifacts.bucket

  environment_variables = {
    S3_BUCKET          = module.nextjs_sites[each.key].bucket_name
    CLOUDFRONT_DIST_ID = module.nextjs_sites[each.key].cloudfront_id
    DEPLOY_ENV         = each.key == "dev-website" ? "dev" : "production"
  }
}

# Build Lambda layers using local-exec
resource "null_resource" "build_stripe_layer" {
  triggers = {
    requirements = filemd5("${path.module}/lambda-layers/stripe-layer/requirements.txt")
  }

  provisioner "local-exec" {
    command = "${path.module}/scripts/build-lambda-layer.sh stripe-layer lambda-layers/stripe-layer/requirements.txt"
  }
}

# Stripe Lambda Layer
resource "aws_lambda_layer_version" "stripe" {
  depends_on = [null_resource.build_stripe_layer]
  
  filename   = "${path.module}/lambda-layers/stripe-layer.zip"
  layer_name = "boring-stripe-layer"
  
  compatible_runtimes = ["python3.13"]
}

# Common Python Layer (requests, etc.)
resource "null_resource" "build_common_layer" {
  triggers = {
    requirements = filemd5("${path.module}/lambda-layers/common-layer/requirements.txt")
  }

  provisioner "local-exec" {
    command = "${path.module}/scripts/build-lambda-layer.sh common-layer lambda-layers/common-layer/requirements.txt"
  }
}

resource "aws_lambda_layer_version" "common" {
  depends_on = [null_resource.build_common_layer]
  
  filename   = "${path.module}/lambda-layers/common-layer.zip"
  layer_name = "boring-common-layer"
  
  compatible_runtimes = ["python3.13"]
}

# KMS Key for Lambda encryption
resource "aws_kms_key" "lambda_encryption" {
  description             = "KMS key for boring Lambda encryption"
  deletion_window_in_days = 10
  enable_key_rotation     = true

  tags = {
    Name      = "boring Lambda Encryption Key"
    Project   = "boring"
    ManagedBy = "Terraform"
  }
}

# KMS Key Alias
resource "aws_kms_alias" "lambda_encryption" {
  name          = "alias/boring-cookie-kms-key"
  target_key_id = aws_kms_key.lambda_encryption.key_id
}

# KMS Key Policy (allow Lambda to use it)
resource "aws_kms_key_policy" "lambda_encryption" {
  key_id = aws_kms_key.lambda_encryption.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Enable IAM User Permissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "Allow Lambda to use the key"
        Effect = "Allow"
        Principal = {
          AWS = module.iam.lambda_exec_role_arn
        }
        Action = [
          "kms:Decrypt",
          "kms:Encrypt",
          "kms:GenerateDataKey",
          "kms:DescribeKey"
        ]
        Resource = "*"
      }
    ]
  })
}